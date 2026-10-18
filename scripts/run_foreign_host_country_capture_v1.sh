#!/usr/bin/env bash
set -euo pipefail

# Capture one foreign preseason-picker country at a repaint-safe cadence. The
# result is evidence for fixed-carrier host-country mapping, not a topology
# write. `foreign_host_mapping_v1.py` verifies screenshots afterwards.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAPTURE_JSON=""
LOCAL_GAME_DIR=""
ARTIFACT_ROOT="${ROOT_DIR}/.local/runlogs/foreign-host-mapping"
WORKER="default"
RUN_TAG=""
SETTLE_SECONDS="2.5"
TILE_Y_OFFSET="0"
HITPOINTS_JSON=""
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: scripts/run_foreign_host_country_capture_v1.sh --capture <json> --local-game-dir <game> [options]

Runs exactly one country flag and club-tile selector from a reviewed host
capture JSON at a safe default 2.5-second post-click cadence. It never changes
PM99 files. The rival picker is stateful (four friendly slots), so a multi-tile
capture is not valid carrier evidence. Follow it with
foreign_host_mapping_v1.py to reject stale or altered frames.

Options:
  --artifact-root <dir>       Local runner artifact root
  --worker <name>             PM99 runner worker (default: default)
  --run-tag <tag>             Override runner tag
  --settle-seconds <seconds>  Per-country/per-tile frame settle time (default: 2.5)
  --tile-y-offset <pixels>   Offset each reviewed tile click vertically (default: 0)
  --hitpoints <json>         Exact x/y hitpoint per tile, overriding reviewed selectors
  --dry-run                   Print the delegated runner command only
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --capture) CAPTURE_JSON="$2"; shift 2 ;;
    --local-game-dir) LOCAL_GAME_DIR="$2"; shift 2 ;;
    --artifact-root) ARTIFACT_ROOT="$2"; shift 2 ;;
    --worker) WORKER="$2"; shift 2 ;;
    --run-tag) RUN_TAG="$2"; shift 2 ;;
    --settle-seconds) SETTLE_SECONDS="$2"; shift 2 ;;
    --tile-y-offset) TILE_Y_OFFSET="$2"; shift 2 ;;
    --hitpoints) HITPOINTS_JSON="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "${CAPTURE_JSON}" && -f "${CAPTURE_JSON}" ]] || { echo "--capture must name an existing JSON file" >&2; exit 2; }
[[ -n "${LOCAL_GAME_DIR}" && -d "${LOCAL_GAME_DIR}" ]] || { echo "--local-game-dir must name an existing game directory" >&2; exit 2; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }
[[ "${SETTLE_SECONDS}" =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo "--settle-seconds must be numeric" >&2; exit 2; }
awk -v value="${SETTLE_SECONDS}" 'BEGIN { exit !(value >= 1.5 && value <= 10.0) }' || {
  echo "--settle-seconds must be from 1.5 through 10.0" >&2
  exit 2
}
[[ "${TILE_Y_OFFSET}" =~ ^-?[0-9]+$ ]] || { echo "--tile-y-offset must be an integer" >&2; exit 2; }
(( TILE_Y_OFFSET >= -30 && TILE_Y_OFFSET <= 30 )) || { echo "--tile-y-offset must be from -30 through 30" >&2; exit 2; }

capture_schema="$(jq -r '.schema // empty' "${CAPTURE_JSON}")"
[[ "${capture_schema}" == "pm99-foreign-host-capture-v1" ]] || { echo "Unsupported capture schema: ${capture_schema:-missing}" >&2; exit 2; }
country="$(jq -r '.country.canonical_name // empty' "${CAPTURE_JSON}")"
flag_x="$(jq -r '.country.flag_selector.x // empty' "${CAPTURE_JSON}")"
flag_y="$(jq -r '.country.flag_selector.y // empty' "${CAPTURE_JSON}")"
[[ -n "${country}" && "${flag_x}" =~ ^[0-9]+$ && "${flag_y}" =~ ^[0-9]+$ ]] || {
  echo "Capture country requires canonical_name and integer flag_selector.x/y" >&2
  exit 2
}
tile_count="$(jq '.tiles | length' "${CAPTURE_JSON}")"
[[ "${tile_count}" -eq 1 ]] || {
  echo "Capture must contain exactly one tile; use foreign_host_capture_tile_v1.py --prepare first" >&2
  exit 2
}
[[ "$(jq '.route_selection_limit // 1' "${CAPTURE_JSON}")" -eq 1 ]] || {
  echo "Capture route_selection_limit must be 1" >&2
  exit 2
}

if [[ -n "${HITPOINTS_JSON}" ]]; then
  [[ -f "${HITPOINTS_JSON}" ]] || { echo "--hitpoints must name an existing JSON file" >&2; exit 2; }
  hitpoint_schema="$(jq -r '.schema // empty' "${HITPOINTS_JSON}")"
  [[ "${hitpoint_schema}" == "pm99-foreign-host-hitpoints-v1" ]] || {
    echo "Unsupported hitpoint schema: ${hitpoint_schema:-missing}" >&2
    exit 2
  }
  [[ "$(jq -r '.capture_id // empty' "${HITPOINTS_JSON}")" == "$(jq -r '.capture_id' "${CAPTURE_JSON}")" ]] || {
    echo "Hitpoints capture_id must match --capture" >&2
    exit 2
  }
  [[ "$(jq '.hitpoints | length' "${HITPOINTS_JSON}")" -eq "${tile_count}" ]] || {
    echo "Hitpoints must cover the selected capture tile exactly once" >&2
    exit 2
  }
fi

if [[ -z "${RUN_TAG}" ]]; then
  slug="$(printf '%s' "${country}" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-')"
  RUN_TAG="foreign_host_${slug}_slow_$(date -u +%Y%m%dT%H%M%SZ)"
fi

declare -a args=(
  --run-tag "${RUN_TAG}"
  --local-game-dir "${LOCAL_GAME_DIR}"
  --local-artifact-dir "${ARTIFACT_ROOT}"
  --worker "${WORKER}"
  --pre-rival-step "select_${country}|native_input_click|${flag_x},${flag_y},1|${SETTLE_SECONDS}"
)

while IFS= read -r tile; do
  index="$(jq -r '.tile_index' <<<"${tile}")"
  x="$(jq -r '.selector.x' <<<"${tile}")"
  y="$(jq -r '.selector.y' <<<"${tile}")"
  screenshot="$(jq -r '.screenshot' <<<"${tile}")"
  label="$(basename "${screenshot}" .png | sed -E 's/^[0-9]+_//')"
  [[ "${index}" =~ ^[0-9]+$ && "${x}" =~ ^[0-9]+$ && "${y}" =~ ^[0-9]+$ && -n "${label}" ]] || {
    echo "Invalid tile row ${index}" >&2
    exit 2
  }
  if [[ -n "${HITPOINTS_JSON}" ]]; then
    hitpoint_count="$(jq --argjson index "${index}" '[.hitpoints[] | select(.tile_index == $index)] | length' "${HITPOINTS_JSON}")"
    [[ "${hitpoint_count}" -eq 1 ]] || { echo "Need exactly one hitpoint for tile ${index}" >&2; exit 2; }
    hitpoint="$(jq -cer --argjson index "${index}" '.hitpoints[] | select(.tile_index == $index)' "${HITPOINTS_JSON}")" || {
      echo "No exact hitpoint for tile ${index}" >&2
      exit 2
    }
    x="$(jq -r '.x' <<<"${hitpoint}")"
    y="$(jq -r '.y' <<<"${hitpoint}")"
    [[ "${x}" =~ ^[0-9]+$ && "${y}" =~ ^[0-9]+$ ]] || { echo "Invalid hitpoint for tile ${index}" >&2; exit 2; }
  fi
  y=$((y + TILE_Y_OFFSET))
  args+=(--pre-rival-step "${label}|native_input_click|${x},${y},1|${SETTLE_SECONDS}")
done < <(jq -c '.tiles | sort_by(.tile_index)[]' "${CAPTURE_JSON}")
args+=(--dashboard-step 'post_probe_done|native_inspect|ignored|0.5')

printf 'Country capture plan: %s, tiles=%s, settle=%ss, tile-y-offset=%s, tag=%s\n' "${country}" "${tile_count}" "${SETTLE_SECONDS}" "${TILE_Y_OFFSET}" "${RUN_TAG}"
printf 'Delegated command:'
printf ' %q' "${ROOT_DIR}/scripts/run_mode1_dashboard_route_probe.sh" "${args[@]}"
printf '\n'
if [[ "${DRY_RUN}" -eq 1 ]]; then
  exit 0
fi
"${ROOT_DIR}/scripts/run_mode1_dashboard_route_probe.sh" "${args[@]}"
