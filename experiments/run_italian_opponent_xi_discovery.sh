#!/usr/bin/env bash
# Reusable read-only, exact-release opponent-statistics discovery.
set -euo pipefail
task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
season="${1:?Usage: bash experiments/run_italian_opponent_xi_discovery.sh SEASON UNIQUE_RUN_TAG}"
run_tag="${2:?A unique run tag is required}"
case "${season}" in
  2000-01) release=sourced-italian-opening-xi-20261008-r54a; search=SHEVCHENKO; shirt=26,374,1 ;;
  2005-06) release=sourced-italian-opening-primary-roles-20261008-r55a; search=CARACCIOLO; shirt=166,410,1 ;;
  2006-07) release=sourced-italian-opening-primary-roles-20261008-r55a; search=CALDERONI; shirt=166,410,1 ;;
  *) echo "Unsupported bounded Italian delivery season: ${season}" >&2; exit 2 ;;
esac
export PM99_ITALIAN_OPPONENT_XI_PROBE=1
export PM99_RUNNER_ARCHIVE_COLD_RUNS=0
export PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE=0
exec bash "${task_root}/experiments/run_italian_opponent_xi_private_probe_v3.sh" \
  --worker tiny-m73 --run-tag "${run_tag}" \
  --local-game-dir "${task_root}/.local/historical-role-deltas-v1/${season}/${release}/game" \
  --local-artifact-dir "${task_root}/.local/italian-delivery/runtime" \
  --team-slot 1 --player-search "${search}" --player-label "${season}_opponent_xi" \
  --profile-only --skip-default-first-rival-pick \
  --pre-rival-step 'country_italy|native_input_click|145,259,1|2.0' \
  --pre-rival-step "select_target_shirt_body|native_input_click|${shirt}|1.0" \
  --pre-rival-step 'inspect_selected_actual_rival|native_inspect|ignored|0.5' \
  --auto-continue-cycles 2 --keep-remote-run --keep-remote-artifacts
