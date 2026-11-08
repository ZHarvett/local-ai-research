#!/usr/bin/env bash
# Clone/fetch mainline llama.cpp into third_party/llama.cpp, check out the newest b-tag, build
# llama-server, llama-bench and llama-cli with CUDA for sm_120, and write data/env/build-info.json.
#
#   scripts/build-llama.sh
#
# Runs for 15-40 minutes: start it through scripts/run-detached.sh. Not a GPU job (no GPU lock).
# Touches only third_party/ (gitignored) and data/env/build-info.json.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$here/_common.sh"

REMOTE="https://github.com/ggml-org/llama.cpp"
MIN_BUILD=12017
MAX_JOBS=6
FALLBACK_JOBS=4
SRC="$SMALLPC_REPO/third_party/llama.cpp"
BUILD="$SRC/build"
OUT="$SMALLPC_REPO/data/env/build-info.json"
TARGETS=(llama-server llama-bench llama-cli)

# nvcc is not on PATH system-wide; add it for this script only.
export PATH="/opt/cuda/bin:$PATH"

CMAKE_FLAGS=(
  -G Ninja
  -DGGML_CUDA=ON
  -DCMAKE_CUDA_ARCHITECTURES=120
  -DGGML_NATIVE=ON
  -DCMAKE_BUILD_TYPE=Release
  -DCMAKE_CUDA_COMPILER=/opt/cuda/bin/nvcc
  -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++
)

# ---------------------------------------------------------------- newest tags (before cloning)
echo "== listing upstream tags"
tags="$(git ls-remote --tags --refs "$REMOTE" | sed 's|.*refs/tags/||')"
tag="$(grep -E '^b[0-9]+$' <<<"$tags" | sort -V | tail -n 1)"
[ -n "$tag" ] || die "no bNNNNN release tag found upstream"
if [ "${tag#b}" -lt "$MIN_BUILD" ]; then
  die "newest upstream tag $tag is older than the required b$MIN_BUILD"
fi
# Semantic-version "stable" tags, if upstream has any: recorded only, never built.
stable_tag="$(grep -E '^v?[0-9]+\.[0-9]+\.[0-9]+$' <<<"$tags" | sort -V | tail -n 1 || true)"
echo "newest b-tag: $tag; newest semver tag: ${stable_tag:-none}"

# ---------------------------------------------------------------- clone / fetch / checkout
mkdir -p "$SMALLPC_REPO/third_party"
if [ -d "$SRC/.git" ]; then
  echo "== fetching into existing clone"
  git -C "$SRC" fetch --tags --force origin
else
  echo "== cloning $REMOTE"
  git clone "$REMOTE" "$SRC"
fi
git -C "$SRC" checkout --detach "refs/tags/$tag"
commit="$(git -C "$SRC" rev-parse HEAD)"
[ "$(git -C "$SRC" rev-parse "refs/tags/$tag^{commit}")" = "$commit" ] || die "checkout mismatch"
echo "checked out $tag = $commit"

# ---------------------------------------------------------------- configure
echo "== configure: cmake -S $SRC -B $BUILD ${CMAKE_FLAGS[*]}"
cmake -S "$SRC" -B "$BUILD" "${CMAKE_FLAGS[@]}"

# ---------------------------------------------------------------- build (retry once on OOM)
jobs="$MAX_JOBS"
oom_retry=false
t0="$(date +%s)"
buildlog="$BUILD/build-output.log"
build_once() {
  echo "== build: cmake --build $BUILD --target ${TARGETS[*]} -j $1"
  set +e
  cmake --build "$BUILD" --target "${TARGETS[@]}" -j "$1" 2>&1 | tee "$buildlog"
  local rc="${PIPESTATUS[0]}"
  set -e
  return "$rc"
}
if ! build_once "$jobs"; then
  if grep -q -i -E 'Killed|signal 9|out of memory|cannot allocate memory' "$buildlog"; then
    echo "== build looks OOM-killed; retrying once with $FALLBACK_JOBS jobs"
    oom_retry=true
    jobs="$FALLBACK_JOBS"
    build_once "$jobs" || die "build failed again with $jobs jobs"
  else
    die "build failed (not an OOM kill; see log above)"
  fi
fi
duration=$(($(date +%s) - t0))
echo "== build finished in ${duration}s with $jobs jobs"

# ---------------------------------------------------------------- build-info.json
for t in "${TARGETS[@]}"; do [ -x "$BUILD/bin/$t" ] || die "missing binary $BUILD/bin/$t"; done
mkdir -p "$(dirname "$OUT")"
cmake_v="$(cmake --version | head -n 1)"
ninja_v="ninja $(ninja --version)"
nvcc_v="$(nvcc --version | tail -n 2 | tr '\n' ' ' | sed 's/ *$//')"
gcc_v="$(/usr/bin/gcc --version | head -n 1)"
gxx_v="$(/usr/bin/g++ --version | head -n 1)"
python3 - "$OUT" "$tag" "$commit" "${stable_tag:-}" "$jobs" "$oom_retry" "$duration" \
  "$cmake_v" "$ninja_v" "$nvcc_v" "$gcc_v" "$gxx_v" "$BUILD/bin" "${CMAKE_FLAGS[@]}" <<'PY'
import datetime, hashlib, json, sys
(out, tag, commit, stable, jobs, oom, dur, cmake_v, ninja_v, nvcc_v, gcc_v, gxx_v,
 bindir, *flags) = sys.argv[1:]
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
targets = ["llama-server", "llama-bench", "llama-cli"]
info = {
    "tag": tag,
    "commit": commit,
    "newest_stable_tag": stable or None,
    "stable_tag_note": "semver tag recorded only; the newest bNNNNN tag is what is built",
    "remote": "https://github.com/ggml-org/llama.cpp",
    "build_date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "cmake_flags": flags,
    "path_prefix_in_script": "/opt/cuda/bin",
    "tools": {"cmake": cmake_v, "ninja": ninja_v, "nvcc": nvcc_v, "gcc": gcc_v,
              "g++ (CUDA host compiler)": gxx_v},
    "parallel_jobs": int(jobs),
    "oom_retry": oom == "true",
    "build_duration_seconds": int(dur),
    "binaries_sha256": {t: sha(f"{bindir}/{t}") for t in targets},
}
with open(out, "w") as f:
    json.dump(info, f, indent=2)
    f.write("\n")
PY
echo "== wrote $OUT"
cat "$OUT"
