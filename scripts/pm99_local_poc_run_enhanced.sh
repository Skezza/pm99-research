#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
game_dir="${root_dir}/game"
support_dir="${root_dir}/support"

for command in wine python3 xdotool wmctrl import xdpyinfo; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Missing required command: ${command}" >&2
    echo "See ${root_dir}/README.md for the one-line Ubuntu dependency install." >&2
    exit 2
  fi
done
if [[ -z "${DISPLAY:-}" ]]; then
  echo "DISPLAY is not set; launch this from your desktop terminal session." >&2
  exit 2
fi
python3 - <<'PY'
try:
    import cv2  # noqa: F401
    import numpy  # noqa: F401
except ModuleNotFoundError as exc:
    raise SystemExit(f"Missing enhanced-presenter Python module: {exc.name}")
PY

screen_geometry="${PM99_POC_SCREEN_GEOMETRY:-}"
if [[ -z "${screen_geometry}" ]]; then
  desktop_dimensions="$(xdpyinfo 2>/dev/null | awk '/dimensions:/{print $2; exit}')"
  if [[ "${desktop_dimensions}" =~ ^[0-9]+x[0-9]+$ ]]; then
    screen_geometry="${desktop_dimensions}x16"
  else
    echo "Could not detect desktop dimensions. Set PM99_POC_SCREEN_GEOMETRY, for example 1920x1080x16." >&2
    exit 2
  fi
fi

screen_size="${screen_geometry%x*}"
screen_width="${screen_size%x*}"
screen_height="${screen_size#*x}"
if [[ ! "${screen_width}" =~ ^[0-9]+$ || ! "${screen_height}" =~ ^[0-9]+$ ]]; then
  echo "Invalid PM99_POC_SCREEN_GEOMETRY: ${screen_geometry}" >&2
  exit 2
fi

if (( screen_width * 3 > screen_height * 4 )); then
  presentation_height="${screen_height}"
  presentation_width=$(( screen_height * 4 / 3 ))
else
  presentation_width="${screen_width}"
  presentation_height=$(( screen_width * 3 / 4 ))
fi
presentation_x=$(( (screen_width - presentation_width) / 2 ))
presentation_y=$(( (screen_height - presentation_height) / 2 ))
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
runtime_dir="${root_dir}/runtime/enhanced-${run_id}"
mkdir -p "${runtime_dir}"

cd "${game_dir}"
exec env \
  WINEPREFIX="${PM99_POC_WINEPREFIX:-${root_dir}/wineprefix-enhanced}" \
  WINEDEBUG="${WINEDEBUG:--all}" \
  WINEDLLOVERRIDES="ddraw=n,b" \
  PM99_DDRAW_NORMALIZE_DISPLAY_MODE=1 \
  PM99_DDRAW_FILTER_ENUM_MODES_640=1 \
  PM99_DDRAW_INJECT_ENUM_MODE_640=1 \
  PM99_DDRAW_FORCE_SET_DISPLAY_MODE_OK=1 \
  PM99_DDRAW_FALLBACK_MANAGED_TEXTURES=1 \
  PM99_DDRAW_UPSCALE_PRIMARY=0 \
  PM99_DDRAW_X11_UPSCALE_OVERLAY=1 \
  PM99_DDRAW_X11_UPSCALE_FILTER=scale2x-fit \
  PM99_DDRAW_X11_MATCH_ONLY_ADAPTIVE=1 \
  PM99_DDRAW_X11_CAPTURE_NATIVE_WINDOW=1 \
  PM99_DDRAW_X11_SOURCE_MODE=native-x11 \
  PM99_DDRAW_X11_NATIVE_CAPTURE_HZ=12 \
  PM99_DDRAW_X11_PRESENTATION_HZ=30 \
  PM99_DDRAW_X11_OVERLAY_START_DELAY_SECONDS=3 \
  PM99_DDRAW_X11_KEEP_ABOVE=0 \
  PM99_DDRAW_FRAME_PATH="${runtime_dir}/pm99-frame.rgb565" \
  PM99_DDRAW_TRACE_LOG="${runtime_dir}/pm99-ddraw.log" \
  PM99_DDRAW_X11_UPSCALE_OVERLAY_LOG="${runtime_dir}/pm99-presenter.log" \
  PM99_DDRAW_HOST_WIDTH="${screen_width}" \
  PM99_DDRAW_HOST_HEIGHT="${screen_height}" \
  PM99_DDRAW_PRESENTATION_WIDTH="${presentation_width}" \
  PM99_DDRAW_PRESENTATION_HEIGHT="${presentation_height}" \
  PM99_DDRAW_PRESENTATION_X="${presentation_x}" \
  PM99_DDRAW_PRESENTATION_Y="${presentation_y}" \
  PM99_DDRAW_DRIVER_DIR="${support_dir}" \
  PM99_DDRAW_X11_OVERLAY_SCRIPT="${support_dir}/pm99_x11_upscale_overlay.py" \
  "${support_dir}/pm99_ddraw_upscale_driver.sh" \
  wine "${game_dir}/MANAGPRE.EXE"
