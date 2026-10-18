#!/usr/bin/env bash
set -euo pipefail

readonly repo_root="/home/joe/pm99-research"
readonly remote_host="192.168.1.133"
readonly receipt_dir="/srv/hdd/pm99-archive/receipts/bentley-sd-20260902"
readonly status_file="/srv/hdd/pm99-archive/receipts/overnight-watch-20260902/current-status.txt"

remote_exists() {
    ssh -o BatchMode=yes "$remote_host" "test -f '$1'"
}

start_backup_if_needed() {
    if test -d /home/joe/Bentley/SD \
        && ! remote_exists "$receipt_dir/TRANSFER_COMPLETE" \
        && ! pgrep -f '/home/joe/Bentley/SD/' >/dev/null; then
        systemd-run --user --unit=bentley-sd-resume-20260902 --collect \
            "$repo_root/scripts/bentley_sd_backup_v1.sh"
    fi
}

start_verification_if_needed() {
    if test -d /home/joe/Bentley/SD \
        && remote_exists "$receipt_dir/TRANSFER_COMPLETE" \
        && ! remote_exists "$receipt_dir/VERIFIED" \
        && ! remote_exists "$receipt_dir/VERIFY_FAILED" \
        && ! pgrep -f 'bentley_sd_verify_remove_v1.sh' >/dev/null; then
        systemd-run --user --unit=bentley-sd-verify-20260902 --collect \
            "$repo_root/scripts/bentley_sd_verify_remove_v1.sh"
    fi
}

write_status() {
    local free_bytes bentley_bytes archive_receipts transfer_state verify_state timestamp
    free_bytes=$(df -B1 --output=avail / | tail -1 | tr -d ' ')
    timestamp=$(date -u +%FT%TZ)
    bentley_bytes=$(ssh -o BatchMode=yes "$remote_host" \
        "du -s -B1 /srv/hdd/pm99-archive/backups/bentley-sd-20260902 2>/dev/null | cut -f1" || true)
    archive_receipts=$(ssh -o BatchMode=yes "$remote_host" \
        "find /srv/hdd/pm99-archive/receipts/2015-superseded-20260902 -maxdepth 1 -type f 2>/dev/null | wc -l" || true)
    transfer_state=$(remote_exists "$receipt_dir/TRANSFER_COMPLETE" && printf complete || printf copying)
    verify_state=$(remote_exists "$receipt_dir/VERIFIED" && printf verified || printf pending)
    ssh -o BatchMode=yes "$remote_host" \
        "mkdir -p /srv/hdd/pm99-archive/receipts/overnight-watch-20260902 && printf 'utc=%s\\nlocal_free_bytes=%s\\nbentley_remote_bytes=%s\\nbentley_transfer=%s\\nbentley_verification=%s\\n2015_archive_receipts=%s\\n' '$timestamp' '$free_bytes' '${bentley_bytes:-0}' '$transfer_state' '$verify_state' '${archive_receipts:-0}' > '$status_file'"
    logger -t pm99-overnight-watch "free_bytes=$free_bytes bentley=$transfer_state/$verify_state receipts=${archive_receipts:-0}"
}

while true; do
    start_backup_if_needed
    start_verification_if_needed
    write_status
    sleep 300
done
