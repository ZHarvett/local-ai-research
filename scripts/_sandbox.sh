#!/usr/bin/env bash
# Run a harness command (npm, opencode, dsh, ...) inside bubblewrap with an isolation environment.
#
#   scripts/_sandbox.sh [options] -- COMMAND [ARGS...]
#
# Options:
#   --kind NAME     state directory third_party/harness-state/NAME (default: harness); it holds
#                   home/, config/, data/, cache/, state/ and tmp/, all writable
#   --no-net        --unshare-net (no network at all, not even loopback)
#   --bridge PORT   (repeatable) private network namespace with only a loopback interface; the
#                   host's 127.0.0.1:PORT is forwarded in through a Unix socket
#                   (python -m smallpc.netbridge). Everything else is "Network is unreachable",
#                   also for programs that ignore proxy settings.
#   --rw PATH       extra writable path (repeatable); must be inside the repo or be a scratch
#                   directory /tmp/local-ai-research-* or /dev/shm/local-ai-research-*
#   --path PATH     PATH inside the sandbox (default /usr/bin:/bin)
#   --env K=V       extra environment variable (repeatable)
#   --proxy PORT    HTTP(S)_PROXY=http://127.0.0.1:PORT, NO_PROXY=127.0.0.1,localhost
#   --npm           npm settings: repo-local cache, empty user/global config, no update notifier
#   --cwd DIR       working directory (default: the state home)
#   --print         print the bwrap command line, one argument per line, and exit
#
# What the sandbox does:
#   * the whole file system is read-only, /home and /tmp are empty tmpfs, /run/user is empty
#     (so the real ~/.config/opencode, ~/.dsh, ~/.npm and the desktop sockets are not visible);
#   * only the state directory and the --rw paths are writable;
#   * the environment is built from scratch (env -i): nothing of the caller's environment
#     (tokens, API keys, SSH_AUTH_SOCK, ...) is passed on;
#   * HOME, XDG_CONFIG_HOME, XDG_DATA_HOME, XDG_CACHE_HOME, XDG_STATE_HOME and TMPDIR point into the
#     state directory; own PID, IPC and UTS namespaces, new session (no controlling terminal).
# If bubblewrap does not work, this script exits 70 and runs nothing: there is no fallback.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$here/_common.sh"

kind="harness"
net=1
bridges=()
sandbox_path="/usr/bin:/bin"
proxy=""
npm=0
cwd=""
print=0
rw=()
extra_env=()
while [ $# -gt 0 ]; do
  case "$1" in
    --kind) kind="${2:?--kind needs a value}"; shift ;;
    --no-net) net=0 ;;
    --bridge) bridges+=("${2:?--bridge needs a port}"); shift ;;
    --rw) rw+=("${2:?--rw needs a value}"); shift ;;
    --path) sandbox_path="${2:?--path needs a value}"; shift ;;
    --env) extra_env+=("${2:?--env needs a value}"); shift ;;
    --proxy) proxy="${2:?--proxy needs a value}"; shift ;;
    --npm) npm=1 ;;
    --cwd) cwd="${2:?--cwd needs a value}"; shift ;;
    --print) print=1 ;;
    -h | --help) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    --) shift; break ;;
    *) die "unknown option: $1 (use -- before the command)" ;;
  esac
  shift
done
[ $# -ge 1 ] || die "no command given"
[[ "$kind" =~ ^[A-Za-z0-9._-]+$ ]] || die "invalid --kind: $kind"

state="$SMALLPC_REPO/third_party/harness-state/$kind"
mkdir -p "$state"/{home,config,data,cache,state,tmp}
cache_dir="$SMALLPC_REPO/third_party/npm-cache"
if [ "$npm" = 1 ]; then
  mkdir -p "$cache_dir"
  : >"$state/npmrc-user"
  : >"$state/npmrc-global"
fi

# writable paths: policy check (repo, or scratch directories named in CLAUDE.md)
allowed_rw() {
  case "$(realpath -m -- "$1")" in
    "$SMALLPC_REPO"/* | /tmp/local-ai-research-* | /dev/shm/local-ai-research-*) return 0 ;;
    *) return 1 ;;
  esac
}
rw_all=("$state")
[ "$npm" = 0 ] || rw_all+=("$cache_dir")
for p in "${rw[@]}"; do
  allowed_rw "$p" || die "--rw path is outside the repo and not a local-ai-research scratch dir: $p"
  [ -e "$p" ] || die "--rw path does not exist: $p"
  rw_all+=("$(realpath -- "$p")")
done

# ---- bubblewrap argv ----
bw=(bwrap --ro-bind / / --proc /proc --dev /dev --tmpfs /home --tmpfs /tmp --tmpfs /run/user
  --unshare-pid --unshare-ipc --unshare-uts --new-session --die-with-parent)
[ "$net" = 1 ] || bw+=(--unshare-net)
for p in "${rw_all[@]}"; do bw+=(--bind "$p" "$p"); done
bw+=(--chdir "${cwd:-$state/home}")

# ---- environment, built from scratch ----
env_args=(
  "PATH=$sandbox_path" "HOME=$state/home"
  "XDG_CONFIG_HOME=$state/config" "XDG_DATA_HOME=$state/data"
  "XDG_CACHE_HOME=$state/cache" "XDG_STATE_HOME=$state/state"
  "TMPDIR=$state/tmp" "LANG=C.UTF-8" "TERM=dumb" "NO_COLOR=1"
)
if [ -n "$proxy" ]; then
  env_args+=("HTTP_PROXY=http://127.0.0.1:$proxy" "HTTPS_PROXY=http://127.0.0.1:$proxy"
    "http_proxy=http://127.0.0.1:$proxy" "https_proxy=http://127.0.0.1:$proxy"
    "NO_PROXY=127.0.0.1,localhost" "no_proxy=127.0.0.1,localhost")
fi
if [ "$npm" = 1 ]; then
  env_args+=("npm_config_cache=$cache_dir" "npm_config_userconfig=$state/npmrc-user"
    "npm_config_globalconfig=$state/npmrc-global" "npm_config_update_notifier=false"
    "npm_config_audit=false" "npm_config_fund=false")
fi
env_args+=("${extra_env[@]}")

full=("${bw[@]}" env -i "${env_args[@]}" "$@")
py="$SMALLPC_REPO/.venv/bin/python"
bridge_args=()
if [ "${#bridges[@]}" -gt 0 ]; then
  [ "$net" = 1 ] || die "--bridge and --no-net exclude each other"
  for port in "${bridges[@]}"; do
    [[ "$port" =~ ^[0-9]+$ ]] || die "invalid --bridge port: $port"
    bridge_args+=(--bridge "$port:$state/bridge-$port.sock")
  done
  # bwrap runs inside a user+network namespace made by unshare (uid 0 there, mapped to this user)
  full=(unshare -Urn "$py" -I -m smallpc.netbridge run "${bridge_args[@]}" -- "${full[@]}")
fi
if [ "$print" = 1 ]; then
  printf '%s\n' "${full[@]}"
  exit 0
fi

# self-test first: a broken sandbox must stop the work, never degrade silently
if ! bwrap --ro-bind / / --unshare-pid --die-with-parent true 2>/dev/null; then
  echo "$(basename "$0"): bubblewrap does not work here; refusing to run anything unsandboxed" >&2
  exit 70
fi
if [ "${#bridges[@]}" -eq 0 ]; then
  exec "${full[@]}"
fi
host_pids=()
cleanup() { kill "${host_pids[@]}" 2>/dev/null || true; rm -f "$state"/bridge-*.sock; }
trap cleanup EXIT
for port in "${bridges[@]}"; do
  "$py" -I -m smallpc.netbridge host --sock "$state/bridge-$port.sock" --target "127.0.0.1:$port" &
  host_pids+=("$!")
done
for port in "${bridges[@]}"; do
  for _ in $(seq 1 100); do [ -S "$state/bridge-$port.sock" ] && break; sleep 0.05; done
  [ -S "$state/bridge-$port.sock" ] || die "bridge socket for port $port did not appear"
done
"${full[@]}"
