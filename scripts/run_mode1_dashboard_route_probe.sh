#!/usr/bin/env bash
set -euo pipefail

# A small, reusable pre-season-rival runner.  It selects a foreign mode-1 club
# as the first friendly opponent using explicit selector probes, then records
# supplied *managed-club* dashboard steps.  The player still manages the
# English club selected by the base new-game flow.  It is useful for opponent
# and match surfaces, but it must never be passed off as a foreign-club Ground
# or Finance screen.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PM99_RUNNER_NAMESPACE="${PM99_RUNNER_NAMESPACE:-pm99-research-main}"
export PM99_RUNNER_REMOTE_ROOT="${PM99_RUNNER_REMOTE_ROOT:-/home/joe/pm99-runner/namespaces/${PM99_RUNNER_NAMESPACE}}"
export PM99_RUNNER_REMOTE_ASSET_ROOT="${PM99_RUNNER_REMOTE_ASSET_ROOT:-/home/joe/pm99-runner/shared}"
export PM99_RUNNER_REMOTE_REPO_DIR="${PM99_RUNNER_REMOTE_REPO_DIR:-${PM99_RUNNER_REMOTE_ROOT}/workspace/repo}"
export PM99_RUNNER_REMOTE_EDITOR_REPO_DIR="${PM99_RUNNER_REMOTE_EDITOR_REPO_DIR:-${PM99_RUNNER_REMOTE_ROOT}/workspace/editor}"
export PM99_RUNNER_REMOTE_IMAGE="${PM99_RUNNER_REMOTE_IMAGE:-pm99-runner:latest}"
export PM99_RUNNER_HOST_LOCK_NAME="${PM99_RUNNER_HOST_LOCK_NAME:-runner-host}"
export PM99_RUNNER_ARCHIVE_COLD_RUNS="${PM99_RUNNER_ARCHIVE_COLD_RUNS:-0}"

source "${REPO_ROOT}/upstream/pm99-runner/scripts/pm99_runner/common.sh"

RUN_TAG="mode1_dashboard_route_$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_GAME_DIR=""
LOCAL_ARTIFACT_DIR="${REPO_ROOT}/artifacts/mode1_dashboard_route"
TEAM_SLOT="1"
WINDOW_TIMEOUT="120"
DOCKER_TIMEOUT_SECONDS="${PM99_RUNNER_DOCKER_TIMEOUT_SECONDS:-600}"
WORKER_NAME="${PM99_RUNNER_WORKER_NAME:-}"
KEEP_REMOTE_RUN=0
KEEP_REMOTE_ARTIFACTS=0
CLEANUP_ON_FAILURE=0
PROVENANCE_FILE=""
INCLUDE_KIT_ARCHIVES=0
declare -a PRE_RIVAL_STEPS=()
declare -a DASHBOARD_STEPS=()

usage() {
  cat <<'EOF'
Usage: scripts/run_mode1_dashboard_route_probe.sh [options]

Required:
  --local-game-dir <path>      Disposable source game, including the four DBDAT files
  --pre-rival-step <spec>      Selector step after the first rival picker opens; repeat as needed
  --dashboard-step <spec>      Route step after the managed club dashboard appears; repeat as needed

Options:
  --run-tag <id>
  --local-artifact-dir <path>
  --team-slot <n>              Retained for the initial manager-screen flow (default: 1)
  --window-timeout <sec>
  --docker-timeout <sec>
  --worker <name>
  --keep-remote-run
  --keep-remote-artifacts
  --cleanup-on-failure
  --provenance-file <path>    Copy immutable local input provenance into the final artifact directory
  --include-kit-archives      Include all five source kit archives and verify source/runtime DAT.PKF match

Step syntax: LABEL|ACTION|VALUE|DELAY
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-tag) RUN_TAG="$2"; shift 2 ;;
    --local-game-dir) LOCAL_GAME_DIR="$2"; shift 2 ;;
    --local-artifact-dir) LOCAL_ARTIFACT_DIR="$2"; shift 2 ;;
    --team-slot) TEAM_SLOT="$2"; shift 2 ;;
    --window-timeout) WINDOW_TIMEOUT="$2"; shift 2 ;;
    --docker-timeout) DOCKER_TIMEOUT_SECONDS="$2"; shift 2 ;;
    --worker) WORKER_NAME="$2"; shift 2 ;;
    --pre-rival-step) PRE_RIVAL_STEPS+=("$2"); shift 2 ;;
    --dashboard-step) DASHBOARD_STEPS+=("$2"); shift 2 ;;
    --keep-remote-run) KEEP_REMOTE_RUN=1; shift ;;
    --keep-remote-artifacts) KEEP_REMOTE_ARTIFACTS=1; shift ;;
    --cleanup-on-failure) CLEANUP_ON_FAILURE=1; shift ;;
    --provenance-file) PROVENANCE_FILE="$2"; shift 2 ;;
    --include-kit-archives) INCLUDE_KIT_ARCHIVES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "${LOCAL_GAME_DIR}" || ! -d "${LOCAL_GAME_DIR}" ]]; then
  echo "--local-game-dir must name an existing game directory" >&2
  exit 2
fi
if [[ ${#PRE_RIVAL_STEPS[@]} -eq 0 || ${#DASHBOARD_STEPS[@]} -eq 0 ]]; then
  echo "At least one --pre-rival-step and --dashboard-step is required" >&2
  exit 2
fi
if [[ -n "${PROVENANCE_FILE}" && ! -f "${PROVENANCE_FILE}" ]]; then
  echo "--provenance-file must name an existing file" >&2
  exit 2
fi

pm99_runner_select_remote_worker "${WORKER_NAME:-}"
PM99_RUNNER_HOST_LOCK_CONCURRENCY="${PM99_RUNNER_WORKER_LANE_COUNT}"
pm99_runner_require_cmd "${PM99_RUNNER_SSH_BIN}"
pm99_runner_require_cmd "${PM99_RUNNER_RSYNC_BIN}"
pm99_runner_require_editor_root
pm99_runner_ensure_local_artifact_root
pm99_runner_acquire_remote_host_lock "run_mode1_dashboard_route_probe:${RUN_TAG}"
trap 'pm99_runner_release_remote_host_lock' EXIT
pm99_runner_sync_repo

REMOTE_RUN_ROOT="$(pm99_runner_remote_run_root "${RUN_TAG}")"
REMOTE_ARTIFACT_DIR="${PM99_RUNNER_REMOTE_ROOT}/artifacts/${RUN_TAG}"
REMOTE_GAME_DIR="$(pm99_runner_remote_game_dir "${REMOTE_RUN_ROOT}")"
REMOTE_HOME_DIR="$(pm99_runner_remote_home_dir "${REMOTE_RUN_ROOT}")"
REMOTE_WINE_PREFIX_DIR="$(pm99_runner_remote_wine_prefix_dir "${REMOTE_RUN_ROOT}")"
LOCAL_FINAL_ARTIFACT_DIR="${LOCAL_ARTIFACT_DIR}/${RUN_TAG}"

pm99_runner_prepare_remote_run_root "${REMOTE_RUN_ROOT}" "${REMOTE_ARTIFACT_DIR}"

required_dbdat=(JUG98030.FDI EQ98030.FDI ENT98030.FDI MINIFOTO.PKF)
if [[ ${INCLUDE_KIT_ARCHIVES} -eq 1 ]]; then
  required_dbdat+=(BIGCAMP.PKF BIGESC.PKF MINIESC.PKF NANOESC.PKF RIDIESC.PKF)
  [[ -f "${LOCAL_GAME_DIR}/DAT.PKF" ]] || { echo "missing source DAT.PKF" >&2; exit 2; }
  source_palette_hash="$(sha256sum "${LOCAL_GAME_DIR}/DAT.PKF" | awk '{print $1}')"
  visible_palette_hash="$(pm99_runner_ssh "sha256sum $(printf '%q' "${REMOTE_GAME_DIR}/DAT.PKF")" | awk '{print $1}')"
  [[ "${source_palette_hash}" == "${visible_palette_hash}" ]] || {
    echo "Runtime DAT.PKF differs from source; this probe cannot establish kit-colour evidence." >&2
    exit 2
  }
fi
for file_name in "${required_dbdat[@]}"; do
  [[ -f "${LOCAL_GAME_DIR}/DBDAT/${file_name}" ]] || { echo "missing DBDAT/${file_name}" >&2; exit 2; }
done
if [[ -f "${LOCAL_GAME_DIR}/MANAGPRE.EXE" ]]; then
  pm99_runner_apply_disposable_exe_override "${REMOTE_RUN_ROOT}" "${LOCAL_GAME_DIR}/MANAGPRE.EXE"
fi
pm99_runner_apply_disposable_dbdat_overrides "${REMOTE_RUN_ROOT}" "${LOCAL_GAME_DIR}/DBDAT" "${required_dbdat[@]}"

receipt_file="$(mktemp "${TMPDIR:-/tmp}/pm99-mode1-dbdat.XXXXXX")"
{
  printf '# PM99 disposable mode-1 dashboard probe DBDAT receipt\n'
  if [[ ${INCLUDE_KIT_ARCHIVES} -eq 1 ]]; then
    printf '%s  DAT.PKF\n' "${visible_palette_hash}"
  fi
  for file_name in "${required_dbdat[@]}"; do
    local_hash="$(sha256sum "${LOCAL_GAME_DIR}/DBDAT/${file_name}" | awk '{print $1}')"
    visible_hash="$(pm99_runner_ssh "sha256sum $(printf '%q' "${REMOTE_GAME_DIR}/DBDAT/${file_name}")" | awk '{print $1}')"
    [[ "${local_hash}" == "${visible_hash}" ]] || { rm -f -- "${receipt_file}"; echo "visible override mismatch: ${file_name}" >&2; exit 1; }
    printf '%s  DBDAT/%s\n' "${visible_hash}" "${file_name}"
  done
} > "${receipt_file}"
pm99_runner_scp_to_remote "${receipt_file}" "${REMOTE_ARTIFACT_DIR}/dbdat_override.sha256"
rm -f -- "${receipt_file}"

driver_args=(
  python3 /workspace/repo/scripts/pm99_runner/premier_offer_capture_driver.py
  --game-dir /workspace/game --artifacts-dir /workspace/artifacts
  --window-timeout "${WINDOW_TIMEOUT}" --team-slot "${TEAM_SLOT}"
  --skip-team-probe-ocr --skip-default-first-rival-pick --success-mode final_step
)
for step in "${PRE_RIVAL_STEPS[@]}"; do driver_args+=(--pre-rival-step "${step}"); done
for step in "${DASHBOARD_STEPS[@]}"; do driver_args+=(--post-step "${step}"); done

set +e
pm99_runner_remote_one_shot_container_with_timeout \
  "${DOCKER_TIMEOUT_SECONDS}" "${RUN_TAG}" "run_mode1_dashboard_route_probe.sh" \
  "pm99-agent-${RUN_TAG}" "${REMOTE_ARTIFACT_DIR}" \
  --image "${PM99_RUNNER_REMOTE_IMAGE}" --user CURRENT_USER --workdir /workspace/repo --shm-size 2g \
  --env HOME=/workspace/home --env PM99_EDITOR_ROOT=/workspace/editor \
  --env PYTHONPATH=/workspace/repo:/workspace/editor --env WINEPREFIX=/workspace/wine-prefix \
  --volume "${PM99_RUNNER_REMOTE_REPO_DIR}:/workspace/repo" \
  --volume "${PM99_RUNNER_REMOTE_EDITOR_REPO_DIR}:/workspace/editor" \
  --volume "${REMOTE_WINE_PREFIX_DIR}:/workspace/wine-prefix" \
  --volume "${REMOTE_HOME_DIR}:/workspace/home" --volume "${REMOTE_GAME_DIR}:/workspace/game" \
  --volume "${REMOTE_ARTIFACT_DIR}:/workspace/artifacts" -- "${driver_args[@]}"
RUN_STATUS=$?
set -e

set +e
pm99_runner_sync_remote_artifacts "${REMOTE_ARTIFACT_DIR}" "${LOCAL_FINAL_ARTIFACT_DIR}"
SYNC_STATUS=$?
pm99_runner_cleanup_remote_state "${RUN_STATUS}" "${SYNC_STATUS}" "${REMOTE_RUN_ROOT}" "${REMOTE_ARTIFACT_DIR}" \
  "${KEEP_REMOTE_RUN}" "${KEEP_REMOTE_ARTIFACTS}" "${CLEANUP_ON_FAILURE}" 0
CLEANUP_STATUS=$?
set -e

[[ ${SYNC_STATUS} -eq 0 ]] || exit "${SYNC_STATUS}"
[[ ${CLEANUP_STATUS} -eq 0 || ${RUN_STATUS} -ne 0 ]] || exit "${CLEANUP_STATUS}"
if [[ -n "${PROVENANCE_FILE}" ]]; then
  cp -- "${PROVENANCE_FILE}" "${LOCAL_FINAL_ARTIFACT_DIR}/input-provenance.json"
fi
echo "Mode-1 dashboard route artifacts: ${LOCAL_FINAL_ARTIFACT_DIR}"
exit "${RUN_STATUS}"
