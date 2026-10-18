#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
runner_common="${repo_root}/upstream/pm99-runner/scripts/pm99_runner/common.sh"

output_dir="${repo_root}/.local/pm99-upscale-poc"
source_dir=""
overlay_dll="${repo_root}/.local/runner-overlays/ddraw-trace/ddraw.dll"
remote_source=1

usage() {
  cat <<'EOF'
Usage: scripts/build_pm99_local_upscale_poc.sh [options]

Materialize a self-contained, local-only PM99 visual-upscale POC.  The package
contains the complete game data, the DirectDraw shim, two isolated Wine
prefixes, and launchers for enhanced versus original presentation.

Options:
  --output-dir <path>   New package directory (default: .local/pm99-upscale-poc)
  --source-dir <path>   Existing complete PM99 game directory; skips remote copy
  --overlay-dll <path>  Built DirectDraw shim (default: .local/runner-overlays/ddraw-trace/ddraw.dll)
  --no-remote           Refuse remote source fallback; require --source-dir
  -h, --help            Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir) output_dir="$2"; shift 2 ;;
    --source-dir) source_dir="$2"; remote_source=0; shift 2 ;;
    --overlay-dll) overlay_dll="$2"; shift 2 ;;
    --no-remote) remote_source=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

abs_path() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).expanduser().resolve())
PY
}

output_dir="$(abs_path "${output_dir}")"
overlay_dll="$(abs_path "${overlay_dll}")"
if [[ -n "${source_dir}" ]]; then
  source_dir="$(abs_path "${source_dir}")"
fi

if [[ -e "${output_dir}" ]]; then
  echo "Refusing to overwrite existing POC package: ${output_dir}" >&2
  exit 2
fi
if [[ ! -f "${overlay_dll}" ]]; then
  echo "Missing built DirectDraw shim: ${overlay_dll}" >&2
  echo "Build it first with: ./scripts/build_pm99_ddraw_trace_overlay.sh" >&2
  exit 2
fi

parent_dir="$(dirname "${output_dir}")"
mkdir -p "${parent_dir}"
staging_dir="$(mktemp -d "${parent_dir}/.pm99-upscale-poc.XXXXXX")"
trap 'rm -rf "${staging_dir}"' EXIT

game_dir="${staging_dir}/game"
mkdir -p "${game_dir}" "${staging_dir}/support" "${staging_dir}/runtime"
source_kind=""
source_location=""
source_fingerprint=""

if [[ -n "${source_dir}" ]]; then
  if [[ ! -f "${source_dir}/MANAGPRE.EXE" || ! -f "${source_dir}/MFC42.DLL" ]]; then
    echo "Source is not a complete PM99 game directory: ${source_dir}" >&2
    exit 2
  fi
  cp -a "${source_dir}/." "${game_dir}/"
  source_kind="local-copy"
  source_location="${source_dir}"
elif [[ ${remote_source} -eq 1 ]]; then
  if [[ ! -f "${runner_common}" ]]; then
    echo "Missing runner common helpers: ${runner_common}" >&2
    exit 2
  fi
  # shellcheck source=/dev/null
  source "${runner_common}"
  pm99_runner_require_cmd "${PM99_RUNNER_SSH_BIN}"
  pm99_runner_require_cmd "${PM99_RUNNER_RSYNC_BIN}"
  remote_game_dir="$(pm99_runner_remote_source_install_dir)"
  pm99_runner_ssh "test -f $(printf '%q' "${remote_game_dir}/MANAGPRE.EXE") && test -f $(printf '%q' "${remote_game_dir}/MFC42.DLL")"
  "${PM99_RUNNER_RSYNC_BIN}" -a \
    "$(pm99_runner_remote_spec):${remote_game_dir}/" "${game_dir}/"
  source_kind="runner-source-copy"
  source_location="$(pm99_runner_remote_spec):${remote_game_dir}"
  source_fingerprint="$(pm99_runner_ssh "cat $(printf '%q' "$(pm99_runner_remote_source_fingerprint_path)")" 2>/dev/null || true)"
else
  echo "A PM99 source is required: pass --source-dir or omit --no-remote." >&2
  exit 2
fi

if [[ ! -f "${game_dir}/MANAGPRE.EXE" || ! -f "${game_dir}/MFC42.DLL" || ! -d "${game_dir}/DBDAT" ]]; then
  echo "Copied game directory failed PM99 completeness checks." >&2
  exit 1
fi

cp -p "${overlay_dll}" "${game_dir}/ddraw.dll"
cp -p "${script_dir}/pm99_ddraw_upscale_driver.sh" "${staging_dir}/support/"
cp -p "${script_dir}/pm99_x11_upscale_overlay.py" "${staging_dir}/support/"
cp -p "${script_dir}/pm99_local_poc_run_enhanced.sh" "${staging_dir}/run-enhanced.sh"
cp -p "${script_dir}/pm99_local_poc_run_original.sh" "${staging_dir}/run-original.sh"
cp -p "${script_dir}/pm99_local_poc_README.md" "${staging_dir}/README.md"
chmod 0755 "${staging_dir}/run-enhanced.sh" "${staging_dir}/run-original.sh" "${staging_dir}/support/pm99_ddraw_upscale_driver.sh"

python3 - "${staging_dir}" "${source_kind}" "${source_location}" "${source_fingerprint}" <<'PY'
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
game = root / "game"

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

game_files = [path for path in game.rglob("*") if path.is_file()]
payload = {
    "kind": "pm99-local-upscale-poc",
    "created_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "game_source": {
        "kind": sys.argv[2],
        "location": sys.argv[3],
        "runner_fingerprint": sys.argv[4].strip(),
        "file_count": len(game_files),
        "bytes": sum(path.stat().st_size for path in game_files),
    },
    "core_files": {
        name: {"sha256": sha256(game / name), "bytes": (game / name).stat().st_size}
        for name in ("MANAGPRE.EXE", "MFC42.DLL", "ddraw.dll")
    },
    "enhanced_mode": {
        "presentation_profile": "stable-native-x11",
        "frame_source": "completed native 640x480 X11 window snapshots only",
        "directdraw_primary_surface": "native 640x480",
        "native_window_mutations": False,
        "input_forwarding": False,
        "menu_scaler": "Scale2x plus restrained bilinear final fit",
        "live_match_scaler": "adaptive Lanczos plus edge-limited sharpening",
        "assets_modified": False,
        "original_launch_forces": "Wine builtin DirectDraw",
    },
}
(root / "build-manifest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

mv "${staging_dir}" "${output_dir}"
trap - EXIT
echo "POC package created: ${output_dir}"
echo "Enhanced: ${output_dir}/run-enhanced.sh"
echo "Original: ${output_dir}/run-original.sh"
