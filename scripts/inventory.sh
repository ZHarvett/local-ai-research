#!/usr/bin/env bash
# WP1: read-only system inventory. Never uses sudo, installs nothing, changes no system state.
# Writes data/env/inventory-<UTC date>.json and docs/environment.md inside the repo.
# Safe to re-run. Missing commands/unreadable files are recorded as "unavailable".
# Privacy: username, hostname and home path are scrubbed (home -> "~").

set -u
set -o pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATE_UTC="$(date -u +%Y-%m-%d)"
STAMP_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
OUT_JSON="$REPO/data/env/inventory-$DATE_UTC.json"
OUT_MD="$REPO/docs/environment.md"
mkdir -p "$REPO/data/env" "$REPO/docs"

# Scratch dir for raw facts (allowed location per CLAUDE.md).
RAW="$(mktemp -d "/dev/shm/local-ai-research-inventory.XXXXXX" 2>/dev/null || mktemp -d)"
trap 'rm -rf "$RAW"' EXIT

have() { command -v "$1" >/dev/null 2>&1; }

# put <key> <command...>: run command, store stdout+stderr; "unavailable" if missing/failing.
put() {
  local key="$1"; shift
  if have "$1"; then
    "$@" >"$RAW/$key" 2>&1 || { [ -s "$RAW/$key" ] || echo "unavailable" >"$RAW/$key"; }
  else
    echo "unavailable" >"$RAW/$key"
  fi
}
# putf <key> <file>: copy a readable file.
putf() {
  if [ -r "$2" ]; then cat "$2" >"$RAW/$1" 2>/dev/null || echo "unavailable" >"$RAW/$1"
  else echo "unavailable" >"$RAW/$1"; fi
}

# ---- OS / CPU ----
putf os_release /etc/os-release
put kernel uname -r
put lscpu lscpu
for k in scaling_governor energy_performance_preference scaling_driver; do
  putf "cpu0_$k" "/sys/devices/system/cpu/cpu0/cpufreq/$k"
done
putf amd_pstate_status /sys/devices/system/cpu/amd_pstate/status
putf cpufreq_boost /sys/devices/system/cpu/cpufreq/boost
# governors/EPP across all cpus (unique values)
{ cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null | sort | uniq -c || true; } >"$RAW/all_governors"
{ cat /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference 2>/dev/null | sort | uniq -c || true; } >"$RAW/all_epp"

# ---- Memory ----
putf meminfo /proc/meminfo
put swapon swapon --show
put zramctl zramctl
putf swappiness /proc/sys/vm/swappiness
putf thp_enabled /sys/kernel/mm/transparent_hugepage/enabled
putf thp_defrag /sys/kernel/mm/transparent_hugepage/defrag
{ ulimit -l 2>&1 || echo unavailable; } >"$RAW/ulimit_l"
put devshm df -B1 --output=size,used,avail /dev/shm

# ---- Disks ----
put lsblk lsblk -o NAME,MODEL,SIZE,TYPE,FSTYPE,MOUNTPOINTS
put findmnt findmnt -o TARGET,SOURCE,FSTYPE,OPTIONS
put findmnt_data findmnt -T /mnt/data -o TARGET,SOURCE,FSTYPE,OPTIONS
put findmnt_repo findmnt -T "$REPO" -o TARGET,SOURCE,FSTYPE,OPTIONS
put df df -h
{ readlink -f "$HOME/Downloads" 2>/dev/null || echo unavailable; } >"$RAW/downloads_target"
{ [ -L "$HOME/Downloads" ] && echo symlink || echo not-a-symlink; } >"$RAW/downloads_is_link"
echo "$REPO" >"$RAW/repo_path"
put repo_df df -h --output=source,size,avail,target "$REPO"

# ---- GPU ----
put nvsmi_query nvidia-smi --query-gpu=name,driver_version,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max,power.limit,power.default_limit,power.max_limit,clocks.gr,clocks.max.gr,clocks.mem,clocks.max.mem,temperature.gpu,persistence_mode,memory.total,memory.used,pstate --format=csv,noheader
put nvsmi_q nvidia-smi -q
put nvsmi_head nvidia-smi
put nvsmi_compute nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
put nvsmi_apps nvidia-smi pmon -c 1
# Graphics (type G) clients; parse from plain nvidia-smi process table later.

# ---- Displays ----
{
  for c in /sys/class/drm/card*-*; do
    [ -e "$c/status" ] || continue
    card="$(basename "$c")"; card="${card%%-*}"
    ven="$(cat "/sys/class/drm/$card/device/vendor" 2>/dev/null || echo unavailable)"
    drv="$(basename "$(readlink -f "/sys/class/drm/$card/device/driver" 2>/dev/null)" 2>/dev/null || echo unavailable)"
    pci="$(basename "$(readlink -f "/sys/class/drm/$card/device" 2>/dev/null)" 2>/dev/null || echo unavailable)"
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(basename "$c")" "$card" "$(cat "$c/status" 2>/dev/null || echo unavailable)" "$ven" "$drv" "$pci"
  done
} >"$RAW/drm"

# ---- CUDA / compilers ----
{ command -v nvcc || true; [ -x /opt/cuda/bin/nvcc ] && echo /opt/cuda/bin/nvcc; } 2>/dev/null | awk '!s[$0]++' >"$RAW/nvcc_paths"
NVCC=""
if have nvcc; then NVCC="$(command -v nvcc)"; elif [ -x /opt/cuda/bin/nvcc ]; then NVCC=/opt/cuda/bin/nvcc; fi
if [ -n "$NVCC" ]; then
  "$NVCC" --version >"$RAW/nvcc_version" 2>&1 || echo unavailable >"$RAW/nvcc_version"
  "$NVCC" --list-gpu-arch >"$RAW/nvcc_gpu_arch" 2>&1 || echo unavailable >"$RAW/nvcc_gpu_arch"
else
  echo unavailable >"$RAW/nvcc_version"; echo unavailable >"$RAW/nvcc_gpu_arch"
fi
put pacman_cuda_gcc sh -c "pacman -Q 2>/dev/null | grep -E '^(cuda|gcc[0-9]*|g\+\+[0-9]*) '"
{
  for f in /usr/bin/gcc /usr/bin/g++ /usr/bin/gcc-[0-9]* /usr/bin/g++-[0-9]* /usr/bin/x86_64-pc-linux-gnu-gcc-[0-9]* /usr/bin/x86_64-pc-linux-gnu-g++-[0-9]*; do
    [ -x "$f" ] || continue
    printf '%s\t%s\n' "$f" "$("$f" -dumpfullversion 2>/dev/null || echo unavailable)"
  done
} >"$RAW/gcc_versions"
HC=""
for c in /opt/cuda/include/crt/host_config.h /usr/local/cuda/include/crt/host_config.h; do [ -r "$c" ] && HC="$c" && break; done
if [ -n "$HC" ]; then
  echo "$HC" >"$RAW/host_config_path"
  grep -n -E '__GNUC__ *(>|>=|<)|unsupported GNU version|gcc versions later than' "$HC" >"$RAW/host_config_grep" 2>/dev/null || echo unavailable >"$RAW/host_config_grep"
  # lines of the block following the GNUC guard, to see whether an #error is actually present
  awk '/__GNUC__ > [0-9]+/{f=1} f{print NR": "$0} /#endif.*__GNUC__ > [0-9]+/{f=0}' "$HC" >"$RAW/host_config_block" 2>/dev/null
else
  echo unavailable >"$RAW/host_config_path"; echo unavailable >"$RAW/host_config_grep"; : >"$RAW/host_config_block"
fi

# ---- Tools ----
tool_ver() { # name, command, args...
  local name="$1"; shift
  if have "$1"; then
    { "$@" 2>&1 | head -n 1; } >"$RAW/tool_$name" || true
    [ -s "$RAW/tool_$name" ] || echo unavailable >"$RAW/tool_$name"
  else echo unavailable >"$RAW/tool_$name"; fi
  { command -v "$1" 2>/dev/null || true; } >"$RAW/toolpath_$name"
}
tool_ver git git --version
tool_ver cmake cmake --version
tool_ver ninja ninja --version
tool_ver make make --version
tool_ver python3 python3 --version
tool_ver uv uv --version
tool_ver node node --version
tool_ver npm npm --version
tool_ver gh gh --version
tool_ver curl curl --version
tool_ver shellcheck shellcheck --version
tool_ver docker docker --version
tool_ver podman podman --version
if have gh; then gh auth status >"$RAW/gh_auth" 2>&1 || true; else echo unavailable >"$RAW/gh_auth"; fi

# ---- Existing llama.cpp / ollama ----
{ command -v llama-server || echo unavailable; } >"$RAW/llama_server"
{ command -v llama-cli || echo unavailable; } >"$RAW/llama_cli"
{ command -v ollama || echo unavailable; } >"$RAW/ollama_bin"
{ pacman -Qs llama 2>&1 || true; } >"$RAW/pacman_llama"
{ pacman -Qs ollama 2>&1 || true; } >"$RAW/pacman_ollama"
{
  for base in "$HOME" /mnt/data; do
    find "$base" -maxdepth 3 \( -iname '*llama.cpp*' -o -iname '*llama-cpp*' -o -iname '*ollama*' \) -not -path "$REPO/*" 2>/dev/null
  done
} >"$RAW/llama_dirs"

# ---- Background load ----
{ systemctl list-units --type=service --state=running --no-legend --plain 2>/dev/null || echo unavailable; } >"$RAW/sys_services"
{ systemctl --user list-units --type=service --state=running --no-legend --plain 2>/dev/null || echo unavailable; } >"$RAW/user_services"
{ ps -eo pid,rss,comm --sort=-rss 2>/dev/null | head -n 16 || echo unavailable; } >"$RAW/top_rss"
{ pgrep -l 'llama-server|llama-cli|ollama|sunshine|libvirtd|virtqemud|qemu|vllm' 2>/dev/null || true; } >"$RAW/watch_procs"

# ---- hwmon ----
{
  for h in /sys/class/hwmon/hwmon*; do
    [ -r "$h/name" ] && printf '%s\t%s\n' "$(basename "$h")" "$(cat "$h/name")"
  done
} >"$RAW/hwmon" 2>/dev/null

# ---- pacman -Si checks for the missing-prerequisites table ----
for p in cuda gcc14 gcc15 gcc13 cmake git python uv nodejs npm nodejs-lts-jod github-cli shellcheck curl ninja; do
  if have pacman && pacman -Si "$p" >/dev/null 2>&1; then echo "$p yes"; else echo "$p no"; fi
done >"$RAW/pacman_si"
{ pacman -Q 2>/dev/null || true; } >"$RAW/pacman_all"

export RAW OUT_JSON OUT_MD STAMP_UTC DATE_UTC REPO HOME
export USER_NAME_SCRUB="${USER:-$(id -un 2>/dev/null || true)}"
HOST_NAME_SCRUB="$( (hostname 2>/dev/null || cat /proc/sys/kernel/hostname 2>/dev/null) || true)"
export HOST_NAME_SCRUB

python3 -I - <<'PYEOF'
import json, os, re, sys

RAW = os.environ["RAW"]; HOME = os.environ["HOME"]
REPO = os.environ["REPO"]
USER = os.environ.get("USER_NAME_SCRUB", ""); HOST = os.environ.get("HOST_NAME_SCRUB", "")
U = "unavailable"

def scrub(s):
    if not isinstance(s, str):
        return s
    if HOME and HOME != "/":
        s = s.replace(HOME, "~")
    if USER and len(USER) >= 2:
        s = re.sub(r"(?<![A-Za-z0-9])" + re.escape(USER) + r"(?![A-Za-z0-9])", "<user>", s)
    if HOST and len(HOST) >= 2:
        s = re.sub(r"(?<![A-Za-z0-9])" + re.escape(HOST) + r"(?![A-Za-z0-9])", "<host>", s)
    return s

def raw(k):
    try:
        with open(os.path.join(RAW, k), errors="replace") as f:
            return scrub(f.read().strip())
    except OSError:
        return U

def first(k):
    r = raw(k)
    return r.splitlines()[0] if r else U

# ---- OS ----
osr = {}
for line in raw("os_release").splitlines():
    if "=" in line:
        a, b = line.split("=", 1); osr[a] = b.strip('"')
os_info = {"pretty_name": osr.get("PRETTY_NAME", U), "id": osr.get("ID", U),
           "build_id": osr.get("BUILD_ID", U), "kernel": first("kernel")}

# ---- CPU ----
lscpu = {}
for line in raw("lscpu").splitlines():
    if ":" in line:
        a, b = line.split(":", 1); lscpu[a.strip()] = b.strip()
flags = lscpu.get("Flags", "").split()
avx512 = sorted(f for f in flags if f.startswith("avx512"))
cpu = {
    "model": lscpu.get("Model name", U),
    "sockets": lscpu.get("Socket(s)", U),
    "cores_per_socket": lscpu.get("Core(s) per socket", U),
    "threads_per_core": lscpu.get("Thread(s) per core", U),
    "logical_cpus": lscpu.get("CPU(s)", U),
    "max_mhz": lscpu.get("CPU max MHz", U),
    "avx512_flags": avx512 if avx512 else ("none" if flags else U),
    "avx512_present": bool(avx512) if flags else U,
    "scaling_driver": first("cpu0_scaling_driver"),
    "scaling_governor_cpu0": first("cpu0_scaling_governor"),
    "governors_all_cpus": raw("all_governors") or U,
    "epp_cpu0": first("cpu0_energy_performance_preference"),
    "epp_all_cpus": raw("all_epp") or U,
    "amd_pstate_status": first("amd_pstate_status"),
    "boost": first("cpufreq_boost"),
}

# ---- Memory ----
mi = {}
for line in raw("meminfo").splitlines():
    m = re.match(r"(\w+):\s+(\d+)", line)
    if m: mi[m.group(1)] = int(m.group(2))
def gib(kb): return round(kb / 1048576, 2) if kb is not None else U
thp_e = raw("thp_enabled"); thp_d = raw("thp_defrag")
def active(s):
    m = re.search(r"\[([^\]]+)\]", s); return m.group(1) if m else s
shm = raw("devshm").splitlines()
shm_size = U
if len(shm) >= 2:
    p = shm[1].split()
    if p and p[0].isdigit(): shm_size = round(int(p[0]) / 2**30, 2)
memory = {
    "mem_total_gib": gib(mi.get("MemTotal")), "mem_available_gib": gib(mi.get("MemAvailable")),
    "swap_total_gib": gib(mi.get("SwapTotal")), "swap_free_gib": gib(mi.get("SwapFree")),
    "swapon": raw("swapon"), "zramctl": raw("zramctl"),
    "swappiness": first("swappiness"),
    "thp_enabled": active(thp_e), "thp_defrag": active(thp_d),
    "ulimit_l_kib": first("ulimit_l"), "dev_shm_size_gib": shm_size,
    "ram_speed": "not readable without root; see optional command below",
    "ram_speed_optional_command": "sudo dmidecode -t memory",
}

# ---- Disks ----
def fm_line(k):
    l = raw(k).splitlines()
    return l[1] if len(l) > 1 else U
repo_fm = fm_line("findmnt_repo")
data_fm = fm_line("findmnt_data")
dl = raw("downloads_target")
disks = {
    "lsblk": raw("lsblk"), "findmnt": raw("findmnt"), "df": raw("df"),
    "repo_mount": repo_fm, "mnt_data_mount": data_fm,
    "repo_df": raw("repo_df"),
    "repo_on_mnt_data_nvme1n1p1": ("/dev/nvme1n1p1" in repo_fm and repo_fm.split()[0] == "/mnt/data"),
    "btrfs_options_mnt_data": (data_fm.split()[-1] if data_fm != U else U),
    "btrfs_compress_zstd1": ("compress=zstd:1" in data_fm),
    "downloads_is_symlink": first("downloads_is_link") == "symlink",
    "downloads_target": dl,
    "downloads_points_to_mnt_data_downloads": dl == "/mnt/data/downloads",
}

# ---- GPU ----
qfields = ["name","driver_version","pcie_gen_current","pcie_gen_max","pcie_width_current","pcie_width_max",
           "power_limit","power_default_limit","power_max_limit","clock_graphics","clock_graphics_max",
           "clock_memory","clock_memory_max","temperature_c","persistence_mode","memory_total","memory_used","pstate"]
q = [x.strip() for x in first("nvsmi_query").split(",")]
gpu = dict(zip(qfields, q)) if len(q) == len(qfields) else {"query": first("nvsmi_query")}
head = raw("nvsmi_head")
m = re.search(r"CUDA (?:UMD )?Version:\s*([\d.]+)", head)
gpu["driver_supports_cuda"] = m.group(1) if m else U
qq = raw("nvsmi_q")
def qget(section_re, key_re):
    m = re.search(section_re + r".*?" + key_re + r"\s*:\s*([^\n]+)", qq, re.S)
    return m.group(1).strip() if m else U
gpu["pcie_note"] = ("The PCIe link may downshift at idle (current gen can be below max); "
                    "WP6 measures the link under load.")
gpu["compute_processes"] = raw("nvsmi_compute") or "none"
# graphics clients from the process table in plain nvidia-smi output
procs = []
for line in head.splitlines():
    mm = re.match(r"\|\s+\d+\s+\S+\s+\S+\s+(\d+)\s+([CG]|C\+G)\s+(\S+)\s+(\d+MiB)", line)
    if mm: procs.append({"pid": mm.group(1), "type": mm.group(2), "name": mm.group(3), "mem": mm.group(4)})
gpu["processes_from_nvidia_smi"] = procs
gpu["graphics_processes"] = [p for p in procs if "G" in p["type"]]
gpu["compute_type_processes"] = [p for p in procs if p["type"] == "C"]
gpu["nvidia_smi_q_excerpt"] = "\n".join(
    l for l in qq.splitlines()
    if re.search(r"Persistence Mode|Product Name|Driver Version|CUDA Version|Link Gen|Link Width|Gen$|Width$|Current|Default Power Limit|Max Power Limit|Power Limit|Graphics\s*:|Memory\s*:|GPU Current Temp|Performance State|Display (Mode|Active)|Compute Mode", l)
)[:6000]

# ---- Displays ----
vendors = {"0x1002": "AMD (amdgpu iGPU)", "0x10de": "NVIDIA (RTX dGPU)", "0x8086": "Intel"}
displays = []
for line in raw("drm").splitlines():
    p = line.split("\t")
    if len(p) < 6: continue
    conn, card, status, ven, drv, pci = p
    displays.append({"connector": conn, "card": card, "status": status, "vendor_id": ven,
                     "gpu": vendors.get(ven, ven), "driver": drv, "pci": pci})
conn_displays = [d for d in displays if d["status"] == "connected"]
nv_conn = [d for d in conn_displays if d["vendor_id"] == "0x10de"]
amd_conn = [d for d in conn_displays if d["vendor_id"] == "0x1002"]
if nv_conn:
    finding = ("YES: %d connected display(s) are attached to the NVIDIA GPU (RTX 5060 Ti): %s. "
               "Compositor/Xwayland clients will use dGPU VRAM and the card is not headless. "
               "Move monitors to the iGPU outputs before measurements (G1)." %
               (len(nv_conn), ", ".join(d["connector"] for d in nv_conn)))
elif conn_displays:
    finding = "NO: no connected display is attached to the NVIDIA GPU; all connected displays are on the iGPU."
else:
    finding = "NO connected displays detected in /sys/class/drm."
display = {"connectors": displays, "connected_on_nvidia": [d["connector"] for d in nv_conn],
           "connected_on_amdgpu": [d["connector"] for d in amd_conn],
           "display_attached_to_rtx_5060_ti": bool(nv_conn), "finding": finding}

# ---- CUDA / gcc ----
nv = raw("nvcc_version")
m = re.search(r"release\s+([\d.]+)", nv)
cuda_release = m.group(1) if m else U
gcc_list = []
for line in raw("gcc_versions").splitlines():
    p = line.split("\t")
    if len(p) == 2: gcc_list.append({"path": p[0], "full_version": p[1],
                                     "major": int(p[1].split(".")[0]) if p[1][:1].isdigit() else None})
hc_grep = raw("host_config_grep"); hc_block = raw("host_config_block")
gm = re.findall(r"__GNUC__ > (\d+)", hc_block or hc_grep)
max_gcc = int(gm[0]) if gm else None
# is an #error actually present inside the GNUC guard block?
block_has_error = "#error" in hc_block
arch = raw("nvcc_gpu_arch")
sm120 = ("compute_120" in arch) or ("sm_120" in arch)
usable = sorted({g["major"] for g in gcc_list if g["major"] is not None and max_gcc is not None and g["major"] <= max_gcc})
if cuda_release == U:
    conclusion = "nvcc not found: no CUDA toolkit usable. Install the CUDA toolkit."
else:
    parts = []
    parts.append("CUDA %s (nvcc at %s)." % (cuda_release, first("nvcc_paths")))
    parts.append("sm_120 (compute capability 12.0) is %s by this nvcc (--list-gpu-arch)." % ("SUPPORTED" if sm120 else "NOT listed"))
    if max_gcc is None:
        parts.append("Could not read a gcc host-compiler limit from the CUDA headers.")
    else:
        parts.append("CUDA headers guard host compilers at GCC > %d (newest accepted major = %d)%s." %
                     (max_gcc, max_gcc, "" if block_has_error else
                      "; note the #error line inside that guard is empty/absent in this header, so the limit is not enforced by the header text"))
    if usable:
        best = max((g for g in gcc_list if g["major"] in usable), key=lambda g: (g["major"], g["path"].endswith("/gcc")))
        parts.append("Installed gcc majors acceptable as host compiler: %s -> usable as CMAKE_CUDA_HOST_COMPILER (e.g. %s)." %
                     (", ".join(map(str, usable)), best["path"]))
    else:
        parts.append("No installed gcc is within the supported range; a compatible gcc is needed for CMAKE_CUDA_HOST_COMPILER.")
    conclusion = " ".join(parts)
cuda = {
    "nvcc_paths": raw("nvcc_paths") or U, "nvcc_version": nv, "cuda_release": cuda_release,
    "nvcc_list_gpu_arch": arch, "supports_sm_120": sm120,
    "pacman_cuda_gcc": raw("pacman_cuda_gcc"),
    "gcc_binaries": gcc_list,
    "host_config_h": raw("host_config_path"),
    "host_config_gnuc_lines": hc_grep, "host_config_gnuc_block": hc_block,
    "max_supported_gcc_major": max_gcc, "gcc_guard_has_error_line": block_has_error,
    "usable_gcc_majors": usable, "conclusion": conclusion,
}

# ---- Tools ----
names = ["git","cmake","ninja","make","python3","uv","node","npm","gh","curl","shellcheck","docker","podman"]
tools = {n: {"version": first("tool_" + n), "path": first("toolpath_" + n) or U} for n in names}
tools["gh_auth_status"] = raw("gh_auth")

# ---- llama.cpp / ollama ----
llama = {
    "llama_server_on_path": first("llama_server"), "llama_cli_on_path": first("llama_cli"),
    "ollama_on_path": first("ollama_bin"),
    "pacman_llama": raw("pacman_llama") or "none", "pacman_ollama": raw("pacman_ollama") or "none",
    "directories_depth3": [x for x in raw("llama_dirs").splitlines() if x] or [],
}
llama["found_any"] = bool(
    llama["llama_server_on_path"] != U or llama["llama_cli_on_path"] != U or llama["ollama_on_path"] != U
    or llama["pacman_llama"] != "none" or llama["pacman_ollama"] != "none" or llama["directories_depth3"])

# ---- Background ----
interesting = re.compile(r"ollama|sunshine|libvirt|virtqemud|virtlogd|qemu|llama|docker|containerd|podman|steam|plex|jellyfin|comfy|vllm|nvidia-persistenced|gpu|cosmic-comp", re.I)
sys_svc = [l.split()[0] for l in raw("sys_services").splitlines() if l.strip()]
usr_svc = [l.split()[0] for l in raw("user_services").splitlines() if l.strip()]
background = {
    "system_services_running_count": len(sys_svc), "user_services_running_count": len(usr_svc),
    "system_services_of_interest": [s for s in sys_svc if interesting.search(s)],
    "user_services_of_interest": [s for s in usr_svc if interesting.search(s)],
    "system_services_all": sys_svc, "user_services_all": usr_svc,
    "watched_processes": raw("watch_procs") or "none",
    "top_processes_by_rss": raw("top_rss"),
}

hwmon = [dict(zip(("hwmon", "name"), l.split("\t"))) for l in raw("hwmon").splitlines() if "\t" in l]
hwmon_names = sorted({h["name"] for h in hwmon})

# ---- Missing prerequisites ----
inst = {}
for l in raw("pacman_all").splitlines():
    p = l.split()
    if len(p) == 2: inst[p[0]] = p[1]
si = dict(l.split() for l in raw("pacman_si").splitlines() if len(l.split()) == 2)
rows = []
def add(item, need, status, pkg_cmd, pkgs):
    ok = all(si.get(p) == "yes" for p in pkgs) if pkgs else None
    rows.append({"item": item, "needed": need, "status": status, "command": pkg_cmd,
                 "package_exists_in_repos": ok})
def pm(*pk): return "sudo pacman -S --needed " + " ".join(pk)

if cuda_release == U: add("CUDA toolkit", "supports sm_120", "missing", pm("cuda"), ["cuda"])
elif not sm120: add("CUDA toolkit", "supports sm_120", "installed %s but no sm_120" % cuda_release, pm("cuda"), ["cuda"])
if cuda_release != U and not usable:
    add("gcc host compiler", "gcc major <= %s" % max_gcc, "unsuitable (installed: %s)" % ", ".join(sorted({g['full_version'] for g in gcc_list})) or "none",
        pm("gcc14") if si.get("gcc14") == "yes" else pm("gcc15"), ["gcc14"] if si.get("gcc14") == "yes" else ["gcc15"])
elif cuda_release == U and not gcc_list:
    add("gcc", "any supported by CUDA", "missing", pm("gcc"), ["gcc"])
def vnum(s):
    m = re.search(r"(\d+)\.(\d+)", s); return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
simple = [("cmake","cmake","cmake"),("git","git","git"),("python3","python3","python"),("uv","uv","uv"),
          ("gh","gh","github-cli"),("shellcheck","shellcheck","shellcheck"),("curl","curl","curl")]
for tool, _, pkg in simple:
    if tools[tool]["version"] == U: add(tool, "required", "missing", pm(pkg), [pkg])
if tools["node"]["version"] == U or tools["npm"]["version"] == U or vnum(tools["node"]["version"])[0] < 22:
    st = "missing" if tools["node"]["version"] == U else "unsuitable (%s; need >= 22)" % tools["node"]["version"]
    add("Node.js >= 22 + npm", "required", st, pm("nodejs", "npm"), ["nodejs", "npm"])
if tools["ninja"]["version"] == U: add("ninja", "optional", "missing", pm("ninja"), ["ninja"])
prereq = {"rows": rows, "none_missing": not rows}

bios = {"EXPO": "enabled; configured speed confirmed at 6000 MT/s by `dmidecode -t memory` "
                "(run by Zack, 2026-11-07)",
        "iGPU": "BIOS left at its default; both displays are on the iGPU",
        "PBO/Eco mode": "BIOS default, never changed by Zack; exact mode not recorded"}

data = {"generated_utc": os.environ["STAMP_UTC"], "script": "scripts/inventory.sh",
        "privacy": "username, hostname scrubbed; home path written as ~",
        "os": os_info, "cpu": cpu, "memory": memory, "disks": disks, "gpu": gpu, "display": display,
        "cuda_toolchain": cuda, "tools": tools, "existing_llama_ollama": llama,
        "background_load": background, "hwmon": {"entries": hwmon, "names": hwmon_names},
        "missing_prerequisites": prereq, "manual_bios_fields": bios}

with open(os.environ["OUT_JSON"], "w") as f:
    json.dump(data, f, indent=2, sort_keys=False); f.write("\n")

# ---- Markdown ----
def fence(s): return "```\n" + s.strip() + "\n```\n"
L = []
a = L.append
a("# Environment inventory\n")
a("Generated by `scripts/inventory.sh` (read-only; no sudo). UTC: %s. Username, hostname and home path are scrubbed (home = `~`).\n" % data["generated_utc"])
a("Machine-readable copy: `data/env/inventory-%s.json`.\n" % os.environ["DATE_UTC"])

a("## Missing prerequisites\n")
if rows:
    a("| Item | Needed | Status | Command to run (not executed) | Package in repos (`pacman -Si`) |")
    a("|---|---|---|---|---|")
    for r in rows:
        ex = {True: "yes", False: "NO - check name", None: "n/a"}[r["package_exists_in_repos"]]
        a("| %s | %s | %s | `%s` | %s |" % (r["item"], r["needed"], r["status"], r["command"], ex))
    a("")
else:
    a("none\n")

a("## CUDA / gcc conclusion\n")
a(conclusion + "\n")
a("- nvcc: `%s`; release %s" % (cuda["nvcc_paths"].replace("\n", ", "), cuda_release))
a("- nvcc supported archs: `%s`" % " ".join(arch.split()))
a("- gcc binaries in /usr/bin: " + (", ".join("%s (%s)" % (g["path"], g["full_version"]) for g in gcc_list) or "none"))
a("- Header checked: `%s` (guard lines below)\n" % cuda["host_config_h"])
a(fence(hc_block or hc_grep))
a("Packages (`pacman -Q`):\n"); a(fence(cuda["pacman_cuda_gcc"]))

a("## Displays and GPU attachment\n")
a("**Finding:** " + finding + "\n")
a("| Connector | Card | Status | GPU | Driver | PCI |"); a("|---|---|---|---|---|---|")
for d in displays: a("| %s | %s | %s | %s | %s | %s |" % (d["connector"], d["card"], d["status"], d["gpu"], d["driver"], d["pci"]))
a("")

a("## GPU\n")
for k in ["name","driver_version","driver_supports_cuda","pcie_gen_current","pcie_gen_max","pcie_width_current","pcie_width_max",
          "power_limit","power_default_limit","power_max_limit","clock_graphics","clock_graphics_max","clock_memory","clock_memory_max",
          "temperature_c","persistence_mode","memory_total","memory_used","pstate"]:
    if k in gpu: a("- %s: %s" % (k, gpu[k]))
a("\nNote: %s\n" % gpu["pcie_note"])
a("Compute processes (`--query-compute-apps`): %s\n" % (gpu["compute_processes"] or "none"))
a("Processes on the GPU (nvidia-smi table):\n")
if procs:
    a("| PID | Type | Name | Mem |"); a("|---|---|---|---|")
    for p in procs: a("| %s | %s | %s | %s |" % (p["pid"], p["type"], p["name"], p["mem"]))
    a("")
else: a("none listed\n")

a("## OS and CPU\n")
a("- OS: %s (kernel %s)" % (os_info["pretty_name"], os_info["kernel"]))
a("- CPU: %s; %s core(s)/socket x %s thread(s)/core = %s logical" % (cpu["model"], cpu["cores_per_socket"], cpu["threads_per_core"], cpu["logical_cpus"]))
a("- AVX-512: %s" % (", ".join(cpu["avx512_flags"]) if isinstance(cpu["avx512_flags"], list) else cpu["avx512_flags"]))
a("- scaling driver: %s; governor (cpu0): %s; EPP (cpu0): %s" % (cpu["scaling_driver"], cpu["scaling_governor_cpu0"], cpu["epp_cpu0"]))
a("- governors (all cpus): %s; EPP (all cpus): %s" % (cpu["governors_all_cpus"].replace("\n", "; "), cpu["epp_all_cpus"].replace("\n", "; ")))
a("- amd-pstate status: %s; boost: %s\n" % (cpu["amd_pstate_status"], cpu["boost"]))

a("## Memory\n")
a("- MemTotal %s GiB, MemAvailable %s GiB, SwapTotal %s GiB" % (memory["mem_total_gib"], memory["mem_available_gib"], memory["swap_total_gib"]))
a("- vm.swappiness: %s; THP enabled: %s; THP defrag: %s" % (memory["swappiness"], memory["thp_enabled"], memory["thp_defrag"]))
a("- `ulimit -l`: %s; /dev/shm size: %s GiB" % (memory["ulimit_l_kib"], memory["dev_shm_size_gib"]))
a("- RAM speed: not readable without root. Optional, run yourself to confirm EXPO speed: `sudo dmidecode -t memory`\n")
a("swapon:\n"); a(fence(memory["swapon"])); a("zramctl:\n"); a(fence(memory["zramctl"]))

a("## Disks\n")
a("- Repo: `%s`" % REPO)
a("- Repo mount: `%s`" % repo_fm)
a("- Repo on 256 GB SSD (`/dev/nvme1n1p1` at `/mnt/data`): **%s**" % ("yes" if disks["repo_on_mnt_data_nvme1n1p1"] else "NO"))
a("- /mnt/data btrfs options: `%s`; `compress=zstd:1` present: **%s**" % (disks["btrfs_options_mnt_data"], "yes" if disks["btrfs_compress_zstd1"] else "no"))
a("- `~/Downloads` is a symlink: %s -> `%s` (points to /mnt/data/downloads: %s)\n" % (disks["downloads_is_symlink"], dl, disks["downloads_points_to_mnt_data_downloads"]))
a("lsblk:\n"); a(fence(disks["lsblk"])); a("df -h:\n"); a(fence(disks["df"])); a("findmnt:\n"); a(fence(disks["findmnt"]))

a("## Tools\n")
a("| Tool | Version | Path |"); a("|---|---|---|")
for n in names: a("| %s | %s | %s |" % (n, tools[n]["version"], tools[n]["path"]))
a("\n`gh auth status`:\n"); a(fence(tools["gh_auth_status"]))

a("## Existing llama.cpp / Ollama installs (recorded only, not touched)\n")
a("- llama-server on PATH: %s\n- llama-cli on PATH: %s\n- ollama on PATH: %s" % (llama["llama_server_on_path"], llama["llama_cli_on_path"], llama["ollama_on_path"]))
a("- `pacman -Qs llama`: %s" % (llama["pacman_llama"].replace("\n", " | ") if llama["pacman_llama"] != "none" else "none"))
a("- `pacman -Qs ollama`: %s" % (llama["pacman_ollama"].replace("\n", " | ") if llama["pacman_ollama"] != "none" else "none"))
a("- directories (depth <= 3 of ~ and /mnt/data, excluding this repo): %s\n" % (", ".join("`%s`" % d for d in llama["directories_depth3"]) or "none"))

a("## Background load\n")
a("- Running system services: %d; user services: %d" % (len(sys_svc), len(usr_svc)))
a("- System services of interest: %s" % (", ".join(background["system_services_of_interest"]) or "none"))
a("- User services of interest: %s" % (", ".join(background["user_services_of_interest"]) or "none"))
a("- Watched processes (llama/ollama/sunshine/libvirt/qemu/vllm): %s\n" % background["watched_processes"].replace("\n", " | "))
a("Top processes by RSS:\n"); a(fence(background["top_processes_by_rss"]))

a("## hwmon sensors\n")
a(", ".join("%s=%s" % (h["hwmon"], h["name"]) for h in hwmon) or U); a("")

a("## Manual BIOS fields\n")
a("| Field | Value |"); a("|---|---|")
for k, v in bios.items(): a("| %s | %s |" % (k, v))
a("")

with open(os.environ["OUT_MD"], "w") as f:
    f.write(scrub("\n".join(L)))
PYEOF
echo "wrote $OUT_JSON"
echo "wrote $OUT_MD"
