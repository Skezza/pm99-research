#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PM99_RUNNER_NAMESPACE="${PM99_RUNNER_NAMESPACE:-pm99-research-main}"
export PM99_RUNNER_REMOTE_ROOT="${PM99_RUNNER_REMOTE_ROOT:-/home/joe/pm99-runner/namespaces/${PM99_RUNNER_NAMESPACE}}"
export PM99_RUNNER_REMOTE_ASSET_ROOT="${PM99_RUNNER_REMOTE_ASSET_ROOT:-/home/joe/pm99-runner/shared}"
export PM99_RUNNER_REMOTE_REPO_DIR="${PM99_RUNNER_REMOTE_REPO_DIR:-${PM99_RUNNER_REMOTE_ROOT}/workspace/repo}"
export PM99_RUNNER_REMOTE_EDITOR_REPO_DIR="${PM99_RUNNER_REMOTE_EDITOR_REPO_DIR:-${PM99_RUNNER_REMOTE_ROOT}/workspace/editor}"
export PM99_RUNNER_REMOTE_IMAGE="${PM99_RUNNER_REMOTE_IMAGE:-pm99-runner:latest}"
export PM99_RUNNER_HOST_LOCK_NAME="${PM99_RUNNER_HOST_LOCK_NAME:-runner-host}"

source "${REPO_ROOT}/upstream/pm99-runner/scripts/pm99_runner/common.sh"

RUN_TAG="pm99_ddraw_trace_probe_$(date -u +%Y%m%dT%H%M%SZ)"
WORKER_NAME="${PM99_RUNNER_WORKER_NAME:-tiny-m73}"
LOCAL_OVERLAY_DIR="${REPO_ROOT}/.local/runner-overlays/ddraw-trace"
LOCAL_ARTIFACT_DIR="${REPO_ROOT}/artifacts/pm99_ddraw_trace_probe"
SCREEN_GEOMETRY="${PM99_RUNNER_SCREEN_GEOMETRY:-640x480x16}"
DOCKER_TIMEOUT_SECONDS="${PM99_RUNNER_DOCKER_TIMEOUT_SECONDS:-900}"
WINE_DEBUG="${WINEDEBUG:--all}"
NORMALIZE_DISPLAY_MODE=0
CLAMP_HUGE_SURFACES=0
FILTER_ENUM_MODES_640=0
INJECT_ENUM_MODE_640=0
FORCE_SET_DISPLAY_MODE_OK=0
FALLBACK_MANAGED_TEXTURES=0
UPSCALE_PRIMARY=0
DISABLE_CLIPPER_BINDING=0
ROOT_PRESENTATION=0
HIDE_LEGACY_WINDOW=0
CLICK_THROUGH_OVERLAY=0
REDIRECT_CLIPPER=0
X11_COMPOSITOR=0
X11_UPSCALE_FILTER="nearest"
X11_MATCH_ONLY_ADAPTIVE=0
X11_MATCH_COMPARISON=0
X11_MENU_COMPARISON=0
X11_MENU_COMPARISON_FINAL_FRAME=0
X11_OVERLAY_RAISE_DELAY_SECONDS=0
X11_OVERLAY_START_DELAY_SECONDS=0
X11_INTERACTIVE_PRESENTATION=0
MATCH_VIEW_CAPTURE=0
SEASON_OVERVIEW_CAPTURE=0
TITLE_ONLY=0
KEEP_REMOTE=0
VISUAL_GATE_STATUS=0
RUNNER_TRACE_MODE="${PM99_RUNNER_TRACE_MODE:-full}"

STATIC_SQUAD_STEPS=(
  "manager_league|click|460,263|4.0"
  "manager_double|native_double_click|338,63,1|4.0"
  "continue_visible|native_input_click|494,459,1|5.0"
  "focus_name|native_input_click|389,82,1|0.5"
  "J|native_key|J|0.1"
  "O|native_key|O|0.1"
  "E|native_key|E|0.1"
  "space|native_key|Space|0.1"
  "B|native_key|B|0.1"
  "L|native_key|L|0.1"
  "O2|native_key|O|0.1"
  "G1|native_key|G|0.1"
  "G2|native_key|G|0.1"
  "S|native_key|S|0.3"
  "second_division|native_input_click|559,302,1|0.8"
  "pick_stoke|native_input_click|327,356,1|1.0"
  "continue_team|native_input_click|561,440,1|5.0"
  "pick_rival1|native_input_click|173,390,1|0.8"
  "assign_rival1|native_input_click|490,92,1|0.8"
  "pick_rival2|native_input_click|173,390,1|0.8"
  "assign_rival2|native_input_click|490,176,1|0.8"
  "pick_rival3|native_input_click|173,390,1|0.8"
  "assign_rival3|native_input_click|490,258,1|0.8"
  "pick_rival4|native_input_click|173,390,1|0.8"
  "assign_rival4|native_input_click|490,341,1|0.8"
  "continue_after_rivals|native_input_click|561,442,1|6.0"
  "preseason_continue_retry|native_input_click|561,442,1|8.0"
  "preseason_continue_retry|native_input_click|561,442,1|8.0"
  "dashboard_select_squad|native_input_click|214,395,1|1.0"
)

usage() {
  cat <<'USAGE'
Usage: scripts/run_pm99_ddraw_trace_probe.sh [options]

Run the static PM99/Stoke flow with a DirectDraw trace/scaling overlay and
collect artifacts. This wrapper exists so the trace env is passed to the
container without editing protected runner internals.

Options:
  --worker <name>           Remote worker name (default: tiny-m73)
  --run-tag <id>            Override artifact/run tag
  --local-overlay-dir <p>   Overlay containing ddraw.dll (default: .local/runner-overlays/ddraw-trace)
  --local-artifact-dir <p>  Local artifact root (default: artifacts/pm99_ddraw_trace_probe)
  --screen-geometry <geom>  Xvfb geometry (default: PM99_RUNNER_SCREEN_GEOMETRY or 640x480x16)
  --wine-debug <channels>   WINEDEBUG value (default: -all)
  --normalize-display-mode  Make shim report 640x480x16 from GetDisplayMode
  --clamp-huge-surfaces     Clamp impossible CreateSurface sizes to 640x480
  --filter-enum-modes-640   Only pass 640x480x16 EnumDisplayModes results to PM99
  --inject-enum-mode-640    Synthesize a 640x480x16 EnumDisplayModes result if none passed
  --force-set-display-ok    Return DD_OK to PM99 for failed 640x480x16 SetDisplayMode
  --fallback-managed-textures  Retry unsupported managed textures as ordinary textures
  --upscale-primary         Present the final 640x480 frame as one centred 4:3 host-sized image
  --disable-clipper-binding Leave PM99's DirectDraw clipper unattached (diagnostic for legacy viewport clipping)
  --root-presentation      Present the scaled frame on the host desktop while retaining PM99's native input window
  --hide-legacy-window     Move the legacy X child off-screen after startup (presentation-only diagnostic)
  --click-through-overlay  Experimental: use one clean scaled overlay and forward pointer input to PM99
  --redirect-clipper       Experimental: bind DirectDraw's clipper to a 4:3 presentation window
  --x11-compositor         Use the input-transparent X11 compositor presentation explicitly
  --upscale-filter <mode>  Compositor scaler: nearest (default), scale2x, scale2x-fit, or linear
  --match-only-adaptive    Use Lanczos/adaptive sharpening for pitch-like match frames only
  --capture-match-comparison  Write same-source nearest/adaptive match images when a live pitch is seen
  --capture-menu-comparison  Write a same-source nearest/edge-aware menu A/B image
  --capture-final-menu-comparison  Write the final eligible PM99 menu state as the A/B source
  --overlay-raise-delay <s>  Raise the X11 presentation after S seconds (preserves native setup input)
  --overlay-start-delay <s> Start the X11 presentation after S seconds (preserves native setup input)
  --interactive-presentation Make the host-sized menu presentation forward its button clicks to PM99
  --match-view-capture     Continue to the first fixture, select Match View, then capture it
  --season-overview-capture Stop on Stoke C.'s first-season overview before the fixture
  --lean-trace             Reduce runner diagnostics during a long capture route
  --title-only              Stop at the title screen (fast rendering-path diagnostic)
  --docker-timeout <sec>    Hard timeout for the container (default: 900)
  --keep-remote             Do not clean remote run/artifacts after success
  -h, --help                Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --worker) WORKER_NAME="$2"; shift 2 ;;
    --run-tag) RUN_TAG="$2"; shift 2 ;;
    --local-overlay-dir) LOCAL_OVERLAY_DIR="$2"; shift 2 ;;
    --local-artifact-dir) LOCAL_ARTIFACT_DIR="$2"; shift 2 ;;
    --screen-geometry) SCREEN_GEOMETRY="$2"; shift 2 ;;
    --wine-debug) WINE_DEBUG="$2"; shift 2 ;;
    --normalize-display-mode) NORMALIZE_DISPLAY_MODE=1; shift ;;
    --clamp-huge-surfaces) CLAMP_HUGE_SURFACES=1; shift ;;
    --filter-enum-modes-640) FILTER_ENUM_MODES_640=1; shift ;;
    --inject-enum-mode-640) INJECT_ENUM_MODE_640=1; shift ;;
    --force-set-display-ok) FORCE_SET_DISPLAY_MODE_OK=1; shift ;;
    --fallback-managed-textures) FALLBACK_MANAGED_TEXTURES=1; shift ;;
    --upscale-primary) UPSCALE_PRIMARY=1; X11_COMPOSITOR=1; shift ;;
    --disable-clipper-binding) DISABLE_CLIPPER_BINDING=1; shift ;;
    --root-presentation) ROOT_PRESENTATION=1; UPSCALE_PRIMARY=1; shift ;;
    --hide-legacy-window) HIDE_LEGACY_WINDOW=1; shift ;;
    --click-through-overlay) CLICK_THROUGH_OVERLAY=1; ROOT_PRESENTATION=1; UPSCALE_PRIMARY=1; shift ;;
    --redirect-clipper) REDIRECT_CLIPPER=1; UPSCALE_PRIMARY=1; shift ;;
    --x11-compositor) X11_COMPOSITOR=1; UPSCALE_PRIMARY=1; shift ;;
    --upscale-filter) X11_UPSCALE_FILTER="$2"; shift 2 ;;
    --match-only-adaptive) X11_MATCH_ONLY_ADAPTIVE=1; X11_COMPOSITOR=1; UPSCALE_PRIMARY=1; shift ;;
    --capture-match-comparison) X11_MATCH_COMPARISON=1; X11_COMPOSITOR=1; UPSCALE_PRIMARY=1; shift ;;
    --capture-menu-comparison) X11_MENU_COMPARISON=1; X11_COMPOSITOR=1; UPSCALE_PRIMARY=1; shift ;;
    --capture-final-menu-comparison) X11_MENU_COMPARISON=1; X11_MENU_COMPARISON_FINAL_FRAME=1; X11_COMPOSITOR=1; UPSCALE_PRIMARY=1; shift ;;
    --overlay-raise-delay) X11_OVERLAY_RAISE_DELAY_SECONDS="$2"; shift 2 ;;
    --overlay-start-delay) X11_OVERLAY_START_DELAY_SECONDS="$2"; shift 2 ;;
    --interactive-presentation) X11_INTERACTIVE_PRESENTATION=1; X11_COMPOSITOR=1; UPSCALE_PRIMARY=1; shift ;;
    --match-view-capture) MATCH_VIEW_CAPTURE=1; shift ;;
    --season-overview-capture) SEASON_OVERVIEW_CAPTURE=1; shift ;;
    --lean-trace) RUNNER_TRACE_MODE=lean; shift ;;
    --title-only) TITLE_ONLY=1; shift ;;
    --docker-timeout) DOCKER_TIMEOUT_SECONDS="$2"; shift 2 ;;
    --keep-remote) KEEP_REMOTE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "${X11_UPSCALE_FILTER}" in
  scale2x|scale2x-fit|nearest|linear) ;;
  *)
    echo "Invalid upscale filter: ${X11_UPSCALE_FILTER} (expected scale2x, scale2x-fit, nearest, or linear)" >&2
    exit 2
    ;;
esac

if ! [[ "${X11_OVERLAY_RAISE_DELAY_SECONDS}" =~ ^([0-9]+([.][0-9]+)?|\.[0-9]+)$ ]]; then
  echo "Invalid overlay raise delay: ${X11_OVERLAY_RAISE_DELAY_SECONDS}" >&2
  exit 2
fi

if ! [[ "${X11_OVERLAY_START_DELAY_SECONDS}" =~ ^([0-9]+([.][0-9]+)?|\.[0-9]+)$ ]]; then
  echo "Invalid overlay start delay: ${X11_OVERLAY_START_DELAY_SECONDS}" >&2
  exit 2
fi

if [[ "${RUNNER_TRACE_MODE}" != "full" && "${RUNNER_TRACE_MODE}" != "lean" ]]; then
  echo "Invalid runner trace mode: ${RUNNER_TRACE_MODE} (expected full or lean)" >&2
  exit 2
fi

if [[ ${TITLE_ONLY} -eq 1 ]]; then
  # native_runner treats an empty step list as its default title-click flow.
  # An explicit wait preserves the title raster for presentation diagnostics.
  STATIC_SQUAD_STEPS=(
    "title_settle|sleep|ignored|12.0"
  )
fi

MATCH_VIEW_SELECT_TARGET="225,276,1"
MATCH_VIEW_CONTINUE_TARGET="506,452,1"
MATCH_VIEW_INTRO_TARGET="552,452,1"
MATCH_VIEW_INTRO_CENTER_TARGET="320,240,1"
MATCH_VIEW_KICKOFF_TARGET="593,456,1"

if [[ ${MATCH_VIEW_CAPTURE} -eq 1 ]]; then
  # Stop the ordinary capture flow before it opens a dashboard tile, then use
  # the existing first fixture and opt into PM99's own 3D Match View mode.
  # The title screen is sometimes a few seconds behind the runner's ready
  # signal.  Wait here so this fixture route never sends its first Manager
  # League click into a blank frame.
  STATIC_SQUAD_STEPS=("${STATIC_SQUAD_STEPS[@]:0:${#STATIC_SQUAD_STEPS[@]}-1}")
  STATIC_SQUAD_STEPS=(
    "title_settle|sleep|ignored|8.0"
    "${STATIC_SQUAD_STEPS[@]}"
  )
  STATIC_SQUAD_STEPS+=(
    "dashboard_continue|native_input_click|582,459,1|8.0"
    "match_options_inspect|native_inspect|ignored|0.5"
    # This is the native (225,276) centre of the View radio indicator, translated to
    # the current Wine window's input coordinate space above.
    "match_view_select|native_input_click|${MATCH_VIEW_SELECT_TARGET}|1.0"
    "match_view_continue|native_input_click|${MATCH_VIEW_CONTINUE_TARGET}|1.0"
    "match_view_continue_enter|native_input_key|Enter|8.0"
    "match_view_boot|sleep|ignored|12.0"
    "match_view_intro_start|native_input_click|${MATCH_VIEW_INTRO_TARGET}|1.0"
    "match_view_intro_start_center|native_input_click|${MATCH_VIEW_INTRO_CENTER_TARGET}|12.0"
    "match_view_kickoff|native_input_click|${MATCH_VIEW_KICKOFF_TARGET}|12.0"
    "match_view_capture|sleep|ignored|8.0"
  )
fi

if [[ ${SEASON_OVERVIEW_CAPTURE} -eq 1 ]]; then
  # The normal static route opens the Squad screen as its final action.  Stop
  # one screen earlier, on the first-season overview for the selected Stoke C.
  # save, after the two deterministic preseason-advance clicks have completed.
  STATIC_SQUAD_STEPS=("${STATIC_SQUAD_STEPS[@]:0:${#STATIC_SQUAD_STEPS[@]}-1}")
  STATIC_SQUAD_STEPS+=(
    "season_overview_settle|sleep|ignored|40.0"
  )
fi

MATCH_COMPARISON_DIR=""
if [[ ${X11_MATCH_COMPARISON} -eq 1 ]]; then
  MATCH_COMPARISON_DIR="/workspace/artifacts/match-comparison"
fi
MENU_COMPARISON_DIR=""
if [[ ${X11_MENU_COMPARISON} -eq 1 ]]; then
  MENU_COMPARISON_DIR="/workspace/artifacts/menu-comparison"
fi

SCREEN_SIZE="${SCREEN_GEOMETRY%x*}"
SCREEN_WIDTH="${SCREEN_SIZE%x*}"
SCREEN_HEIGHT="${SCREEN_SIZE#*x}"
if [[ ! "${SCREEN_WIDTH}" =~ ^[0-9]+$ || ! "${SCREEN_HEIGHT}" =~ ^[0-9]+$ ]]; then
  echo "Invalid screen geometry: ${SCREEN_GEOMETRY}" >&2
  exit 2
fi
PRESENTATION_WIDTH="${SCREEN_WIDTH}"
PRESENTATION_HEIGHT="${SCREEN_HEIGHT}"
PRESENTATION_X=0
PRESENTATION_Y=0
if [[ ${UPSCALE_PRIMARY} -eq 1 ]]; then
  if (( SCREEN_WIDTH * 3 > SCREEN_HEIGHT * 4 )); then
    PRESENTATION_HEIGHT="${SCREEN_HEIGHT}"
    PRESENTATION_WIDTH=$(( SCREEN_HEIGHT * 4 / 3 ))
  else
    PRESENTATION_WIDTH="${SCREEN_WIDTH}"
    PRESENTATION_HEIGHT=$(( SCREEN_WIDTH * 3 / 4 ))
  fi
  PRESENTATION_X=$(( (SCREEN_WIDTH - PRESENTATION_WIDTH) / 2 ))
  PRESENTATION_Y=$(( (SCREEN_HEIGHT - PRESENTATION_HEIGHT) / 2 ))
fi

if [[ ${TITLE_ONLY} -eq 1 && ${X11_INTERACTIVE_PRESENTATION} -eq 1 ]]; then
  # native_runner normally supplies a logical title click when no steps are
  # passed.  In this diagnostic route, send its equivalent host-space click
  # through the enlarged presentation so the forwarding path is exercised.
  INTERACTIVE_TITLE_X=$(( PRESENTATION_X + (455 * PRESENTATION_WIDTH + 320) / 640 ))
  # After the overlay remaps from its hidden capture state, its fullscreen
  # client starts two root pixels below the Xvfb origin.  Human clicks already
  # use the visible client; this offset is only for the root-coordinate probe.
  INTERACTIVE_TITLE_Y=$(( 2 + PRESENTATION_Y + (300 * PRESENTATION_HEIGHT + 240) / 480 ))
  STATIC_SQUAD_STEPS=(
    "interactive_title_click|click|${INTERACTIVE_TITLE_X},${INTERACTIVE_TITLE_Y},1|4.0"
    "interactive_title_settle|sleep|ignored|2.0"
  )
fi

if [[ ! -d "${LOCAL_OVERLAY_DIR}" ]]; then
  echo "Missing local overlay dir: ${LOCAL_OVERLAY_DIR}" >&2
  exit 2
fi
if [[ ! -f "${LOCAL_OVERLAY_DIR}/ddraw.dll" ]]; then
  echo "Missing ddraw.dll in overlay dir: ${LOCAL_OVERLAY_DIR}" >&2
  exit 2
fi

pm99_runner_require_cmd "${PM99_RUNNER_SSH_BIN}"
pm99_runner_require_cmd "${PM99_RUNNER_RSYNC_BIN}"
pm99_runner_require_editor_root
pm99_runner_select_remote_worker "${WORKER_NAME}"
PM99_RUNNER_HOST_LOCK_CONCURRENCY="${PM99_RUNNER_HOST_LOCK_CONCURRENCY:-${PM99_RUNNER_WORKER_LANE_COUNT}}"

pm99_runner_acquire_remote_host_lock "run_pm99_ddraw_trace_probe:${RUN_TAG}"
trap 'pm99_runner_release_remote_host_lock' EXIT

REMOTE_RUN_ROOT="$(pm99_runner_remote_run_root "${RUN_TAG}")"
REMOTE_GAME_DIR="$(pm99_runner_remote_game_dir "${REMOTE_RUN_ROOT}")"
REMOTE_HOME_DIR="$(pm99_runner_remote_home_dir "${REMOTE_RUN_ROOT}")"
REMOTE_WINE_PREFIX_DIR="$(pm99_runner_remote_wine_prefix_dir "${REMOTE_RUN_ROOT}")"
REMOTE_ARTIFACT_DIR="${PM99_RUNNER_REMOTE_ROOT}/artifacts/${RUN_TAG}"
FINAL_LOCAL_ARTIFACT_DIR="${LOCAL_ARTIFACT_DIR}/${RUN_TAG}"

pm99_runner_prepare_remote_run_root "${REMOTE_RUN_ROOT}" "${REMOTE_ARTIFACT_DIR}"
"${PM99_RUNNER_RSYNC_BIN}" -az \
  "${LOCAL_OVERLAY_DIR}/" "$(pm99_runner_remote_spec):${REMOTE_GAME_DIR}/"
"${PM99_RUNNER_RSYNC_BIN}" -az \
  "${SCRIPT_DIR}/pm99_ddraw_upscale_driver.sh" \
  "${SCRIPT_DIR}/pm99_x11_upscale_overlay.py" \
  "$(pm99_runner_remote_spec):${REMOTE_RUN_ROOT}/"

DRIVER_COMMAND=(
  bash /workspace/run/pm99_ddraw_upscale_driver.sh
  python3 /workspace/repo/scripts/pm99_runner/native_runner.py
  new-game
  --game-dir /workspace/game
  --artifacts-dir /workspace/artifacts
)
for step in "${STATIC_SQUAD_STEPS[@]}"; do
  DRIVER_COMMAND+=(--step "${step}")
done

set +e
pm99_runner_remote_one_shot_container_with_timeout \
  "${DOCKER_TIMEOUT_SECONDS}" \
  "${RUN_TAG}" \
  "run_pm99_ddraw_trace_probe.sh" \
  "pm99-agent-${RUN_TAG}" \
  "${REMOTE_ARTIFACT_DIR}" \
  --image "${PM99_RUNNER_REMOTE_IMAGE}" \
  --user CURRENT_USER \
  --workdir /workspace/repo \
  --shm-size 2g \
  --env HOME=/workspace/home \
  --env PM99_EDITOR_ROOT=/workspace/editor \
  --env PM99_SCREEN_GEOMETRY="${SCREEN_GEOMETRY}" \
  --env PM99_DDRAW_TRACE_LOG=/workspace/artifacts/pm99-ddraw.log \
  --env PM99_DDRAW_NORMALIZE_DISPLAY_MODE="${NORMALIZE_DISPLAY_MODE}" \
  --env PM99_DDRAW_CLAMP_HUGE_SURFACES="${CLAMP_HUGE_SURFACES}" \
  --env PM99_DDRAW_FILTER_ENUM_MODES_640="${FILTER_ENUM_MODES_640}" \
  --env PM99_DDRAW_INJECT_ENUM_MODE_640="${INJECT_ENUM_MODE_640}" \
  --env PM99_DDRAW_FORCE_SET_DISPLAY_MODE_OK="${FORCE_SET_DISPLAY_MODE_OK}" \
  --env PM99_DDRAW_FALLBACK_MANAGED_TEXTURES="${FALLBACK_MANAGED_TEXTURES}" \
  --env PM99_DDRAW_UPSCALE_PRIMARY="${UPSCALE_PRIMARY}" \
  --env PM99_DDRAW_DISABLE_CLIPPER_BINDING="${DISABLE_CLIPPER_BINDING}" \
  --env PM99_DDRAW_ROOT_PRESENTATION="${ROOT_PRESENTATION}" \
  --env PM99_DDRAW_CLICK_THROUGH_OVERLAY="${CLICK_THROUGH_OVERLAY}" \
  --env PM99_DDRAW_REDIRECT_CLIPPER="${REDIRECT_CLIPPER}" \
  --env PM99_DDRAW_X11_UPSCALE_OVERLAY="${X11_COMPOSITOR}" \
  --env PM99_DDRAW_X11_UPSCALE_FILTER="${X11_UPSCALE_FILTER}" \
  --env PM99_DDRAW_X11_MATCH_ONLY_ADAPTIVE="${X11_MATCH_ONLY_ADAPTIVE}" \
  --env PM99_DDRAW_X11_MATCH_COMPARISON_DIR="${MATCH_COMPARISON_DIR}" \
  --env PM99_DDRAW_X11_MENU_COMPARISON_DIR="${MENU_COMPARISON_DIR}" \
  --env PM99_DDRAW_X11_MENU_COMPARISON_FINAL_FRAME="${X11_MENU_COMPARISON_FINAL_FRAME}" \
  --env PM99_DDRAW_X11_OVERLAY_RAISE_DELAY_SECONDS="${X11_OVERLAY_RAISE_DELAY_SECONDS}" \
  --env PM99_DDRAW_X11_OVERLAY_START_DELAY_SECONDS="${X11_OVERLAY_START_DELAY_SECONDS}" \
  --env PM99_DDRAW_X11_INTERACTIVE_INPUT="${X11_INTERACTIVE_PRESENTATION}" \
  --env PM99_DDRAW_X11_CAPTURE_NATIVE_WINDOW=1 \
  --env PM99_DDRAW_KEEP_NATIVE_WINDOW="${X11_COMPOSITOR}" \
  --env PM99_DDRAW_FRAME_PATH=/workspace/artifacts/pm99-upscale-frame.rgb565 \
  --env PM99_DDRAW_HOST_WIDTH="${SCREEN_WIDTH}" \
  --env PM99_DDRAW_HOST_HEIGHT="${SCREEN_HEIGHT}" \
  --env PM99_DDRAW_X11_UPSCALE_OVERLAY_LOG=/workspace/artifacts/pm99-ddraw-x11-overlay.log \
  --env PM99_DDRAW_X11_RESIZE="$(( UPSCALE_PRIMARY && ! ROOT_PRESENTATION && ! REDIRECT_CLIPPER && ! X11_COMPOSITOR ))" \
  --env PM99_DDRAW_X11_HIDE_LEGACY="${HIDE_LEGACY_WINDOW}" \
  --env PM99_DDRAW_PRESENTATION_WIDTH="${PRESENTATION_WIDTH}" \
  --env PM99_DDRAW_PRESENTATION_HEIGHT="${PRESENTATION_HEIGHT}" \
  --env PM99_DDRAW_PRESENTATION_X="${PRESENTATION_X}" \
  --env PM99_DDRAW_PRESENTATION_Y="${PRESENTATION_Y}" \
  --env PM99_DDRAW_X11_RESIZE_LOG=/workspace/artifacts/pm99-ddraw-window-resize.log \
  --env PM99_RUNNER_TRACE_MODE="${RUNNER_TRACE_MODE}" \
  --env WINEDLLOVERRIDES=ddraw=n,b \
  --env WINEDEBUG="${WINE_DEBUG}" \
  --env PYTHONPATH=/workspace/home:/workspace/repo:/workspace/editor \
  --env WINEPREFIX=/workspace/wine-prefix \
  --volume "${PM99_RUNNER_REMOTE_REPO_DIR}:/workspace/repo" \
  --volume "${PM99_RUNNER_REMOTE_EDITOR_REPO_DIR}:/workspace/editor" \
  --volume "${REMOTE_WINE_PREFIX_DIR}:/workspace/wine-prefix" \
  --volume "${REMOTE_HOME_DIR}:/workspace/home" \
  --volume "${REMOTE_RUN_ROOT}:/workspace/run" \
  --volume "${REMOTE_GAME_DIR}:/workspace/game" \
  --volume "${REMOTE_ARTIFACT_DIR}:/workspace/artifacts" \
  -- "${DRIVER_COMMAND[@]}"
RUN_STATUS=$?
set -e

SYNC_STATUS=0
pm99_runner_sync_remote_artifacts "${REMOTE_ARTIFACT_DIR}" "${FINAL_LOCAL_ARTIFACT_DIR}" || SYNC_STATUS=$?

if [[ ${SYNC_STATUS} -eq 0 ]]; then
  python3 "${REPO_ROOT}/scripts/summarize_pm99_ddraw_trace.py" "${FINAL_LOCAL_ARTIFACT_DIR}" \
    --output "${FINAL_LOCAL_ARTIFACT_DIR}/pm99-ddraw-summary.json" || true
fi

if [[ ${RUN_STATUS} -eq 0 && ${SYNC_STATUS} -eq 0 ]]; then
  set +e
  python3 - "${FINAL_LOCAL_ARTIFACT_DIR}/summary.json" \
    "${FINAL_LOCAL_ARTIFACT_DIR}/compatibility_gate.json" \
    "${TITLE_ONLY}" \
    "${MATCH_VIEW_CAPTURE}" \
    "${X11_MATCH_COMPARISON}" \
    "${X11_MENU_COMPARISON}" <<'PY'
import json
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
title_only = sys.argv[3] == "1"
match_view_capture = sys.argv[4] == "1"
match_comparison_requested = sys.argv[5] == "1"
menu_comparison_requested = sys.argv[6] == "1"
summary = json.loads(summary_path.read_text(encoding="utf-8"))
final = dict(summary.get("final_screen_classification") or {})
steps = list(summary.get("steps") or [])
final_screenshot = Path(str((steps[-1] if steps else {}).get("screenshot") or "")).name
local_screenshot = summary_path.parent / "screens" / final_screenshot
allowed_screens = (
    {"title_screen"}
    if title_only
    else {"squad_management_screen", "club_dashboard_screen", "lineup_screen"}
)
comparison_path = summary_path.parent / "match-comparison" / "match_before_after.png"
menu_comparison_path = summary_path.parent / "menu-comparison" / "menu_before_after.png"
menu_manifest_path = summary_path.parent / "menu-comparison" / "menu_ab_manifest.json"
menu_manifest = {}
if menu_manifest_path.is_file():
    try:
        menu_manifest = json.loads(menu_manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        pass
match_comparison_ok = (
    not match_comparison_requested
    or (comparison_path.is_file() and comparison_path.stat().st_size > 0)
)
menu_comparison_ok = (
    not menu_comparison_requested
    or (
        menu_comparison_path.is_file()
        and menu_comparison_path.stat().st_size > 0
        and menu_manifest.get("kind") == "same-source-menu-upscale-ab"
        and bool(menu_manifest.get("source_sha256"))
        and menu_manifest.get("source_kind") in {"native-x11", "directdraw-rgb565"}
        and menu_manifest.get("assets_modified") is False
        and menu_manifest.get("input_coordinates_modified") is False
    )
)
terminal_screen_ok = (
    menu_comparison_requested
    or (
        comparison_path.is_file() and comparison_path.stat().st_size > 0
        if match_view_capture
        else str(final.get("screen") or "") in allowed_screens
    )
)
passed = (
    bool(summary.get("success"))
    and not bool(summary.get("crash_detected"))
    and not bool(summary.get("blocking_error_modal_detected"))
    and local_screenshot.is_file()
    and local_screenshot.stat().st_size > 0
    and (match_comparison_ok and menu_comparison_ok)
    and terminal_screen_ok
)
payload = {
    "passed": passed,
    "allowed_final_screens": sorted(allowed_screens),
    "match_view_capture": match_view_capture,
    "match_comparison_requested": match_comparison_requested,
    "menu_comparison_requested": menu_comparison_requested,
    "terminal_screen_check_bypassed_by_menu_comparison": menu_comparison_requested,
    "runner_success": bool(summary.get("success")),
    "crash_detected": bool(summary.get("crash_detected")),
    "blocking_error_modal_detected": bool(summary.get("blocking_error_modal_detected")),
    "final_screen": final.get("screen"),
    "final_screenshot": final_screenshot,
    "final_screenshot_bytes": local_screenshot.stat().st_size if local_screenshot.is_file() else 0,
    "comparison_screenshot": comparison_path.name if comparison_path.is_file() else "",
    "comparison_screenshot_bytes": comparison_path.stat().st_size if comparison_path.is_file() else 0,
    "menu_comparison_screenshot": menu_comparison_path.name if menu_comparison_path.is_file() else "",
    "menu_comparison_screenshot_bytes": menu_comparison_path.stat().st_size if menu_comparison_path.is_file() else 0,
    "menu_comparison_manifest": menu_manifest_path.name if menu_manifest_path.is_file() else "",
}
output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload, sort_keys=True))
raise SystemExit(0 if passed else 1)
PY
  VISUAL_GATE_STATUS=$?
  set -e
fi

if [[ ${KEEP_REMOTE} -eq 0 ]]; then
  set +e
  pm99_runner_cleanup_remote_state \
    "${RUN_STATUS}" \
    "${SYNC_STATUS}" \
    "${REMOTE_RUN_ROOT}" \
    "${REMOTE_ARTIFACT_DIR}" \
    0 \
    0 \
    1 \
    0
  CLEANUP_STATUS=$?
  set -e
else
  CLEANUP_STATUS=0
fi

echo "remote_run_root=${REMOTE_RUN_ROOT}"
echo "remote_artifacts=${REMOTE_ARTIFACT_DIR}"
echo "local_artifacts=${FINAL_LOCAL_ARTIFACT_DIR}"
echo "run_status=${RUN_STATUS}"
echo "sync_status=${SYNC_STATUS}"
echo "visual_gate_status=${VISUAL_GATE_STATUS}"

if [[ ${SYNC_STATUS} -ne 0 ]]; then
  exit "${SYNC_STATUS}"
fi
if [[ ${CLEANUP_STATUS} -ne 0 && ${RUN_STATUS} -eq 0 ]]; then
  exit "${CLEANUP_STATUS}"
fi
if [[ ${VISUAL_GATE_STATUS} -ne 0 ]]; then
  exit "${VISUAL_GATE_STATUS}"
fi
exit "${RUN_STATUS}"
