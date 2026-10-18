#!/usr/bin/env bash
set -euo pipefail

readonly repo_root="/home/joe/pm99-research"
readonly lock_file="/home/joe/pm99-research/.local/operations/scheduled-continuation.lock"
readonly result_file="/home/joe/pm99-research/.local/operations/scheduled-continuation-last.txt"

mkdir -p "$(dirname "$lock_file")"
exec 9>"$lock_file"
if ! flock -n 9; then
    logger -t pm99-scheduled-continuation "skipped: another continuation run is active"
    exit 0
fi

prompt=$(mktemp)
trap 'rm -f "$prompt"' EXIT
printf '%s\n' \
    'You are the scheduled continuation worker for PM99RE.' \
    'Read docs/SEASON_DELIVERY_STATUS_OPERATIONS.md, docs/HANDOVER_2015_16_WORLD_DATABASE_AND_SEASON_PIPELINE_2026-08-31.md, and .local/operations/season-delivery-status.json first.' \
    'Take exactly one bounded, safe, high-value action toward making one or more of the 25 draft season packages release-eligible.' \
    'Prefer existing hash-bound cache/source evidence and deterministic pipeline repairs. Do not run broad new source acquisition, delete data, move current manifests, or alter the established 2015/16 release.' \
    'Never call a season playable unless it has canonical package, static audit, successful PM99 runtime route, and a bound runtime screenshot.' \
    'Run proportionate validation. Update an operations/status document only when facts changed. In your final response, state exact files changed, validation, eligibility movement, remaining blockers, and the next smallest action.' \
    > "$prompt"

cd "$repo_root"
codex exec --approve-for-me \
    --output-last-message "$result_file" \
    -C "$repo_root" - < "$prompt"
