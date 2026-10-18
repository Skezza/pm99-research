#!/usr/bin/env bash
set -euo pipefail

readonly repo_root="/home/joe/pm99-research"
readonly remote_host="192.168.1.133"
readonly remote_dir="/srv/hdd/pm99-archive/receipts/overnight-watch-20260902/hourly"
readonly matrix="$repo_root/.local/season-historical-squad-backfill-v1/coverage-matrix-current.json"

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
report=$(mktemp)
trap 'rm -f "$report"' EXIT

service_state() {
    if systemctl --user is-active "$1" >/dev/null 2>&1; then
        printf active
    else
        printf inactive
    fi
}

{
    printf 'utc=%s\n' "$timestamp"
    printf 'local_disk='; df -h / | tail -1
    printf 'bentley_backup_service=%s\n' "$(service_state bentley-sd-backup-20260902)"
    printf 'overnight_watch_service=%s\n' "$(service_state pm99-overnight-watch-20260902)"
    printf '2015_archive_service=%s\n' "$(service_state pm99-archive-2015-superseded)"
    if test -f "$matrix"; then
        printf 'coverage_matrix_sha256='; sha256sum "$matrix" | awk '{print $1}'
    fi
    printf 'git_worktree_entries='; git -C "$repo_root" status --short | wc -l
    ssh -o BatchMode=yes "$remote_host" \
        "printf 'remote_disk='; df -h /srv/hdd | tail -1; printf 'bentley_remote='; du -sh /srv/hdd/pm99-archive/backups/bentley-sd-20260902 2>/dev/null || true; printf '2015_archive_receipts='; find /srv/hdd/pm99-archive/receipts/2015-superseded-20260902 -maxdepth 1 -type f 2>/dev/null | wc -l; printf 'bentley_transfer='; test -f /srv/hdd/pm99-archive/receipts/bentley-sd-20260902/TRANSFER_COMPLETE && printf complete || printf copying; printf '\\n'; printf 'bentley_verified='; test -f /srv/hdd/pm99-archive/receipts/bentley-sd-20260902/VERIFIED && printf yes || printf no; printf '\\n'"
} > "$report"

ssh -o BatchMode=yes "$remote_host" "mkdir -p '$remote_dir'"
scp -q -o BatchMode=yes "$report" "$remote_host:$remote_dir/$timestamp.txt"
