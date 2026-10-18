#!/usr/bin/env bash
set -euo pipefail

readonly source_dir="/home/joe/Bentley/SD"
readonly remote_host="192.168.1.133"
readonly remote_dir="/srv/hdd/pm99-archive/backups/bentley-sd-20260902"
readonly receipt_dir="/srv/hdd/pm99-archive/receipts/bentley-sd-20260902"

test -d "$source_dir"
test "$(ssh -o BatchMode=yes "$remote_host" "test -f '$receipt_dir/TRANSFER_COMPLETE' && printf yes")" = yes

comparison=$(mktemp)
trap 'rm -f "$comparison"' EXIT
rsync -a -c -n --delete --itemize-changes \
    -e 'ssh -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=6' \
    "$source_dir/" "$remote_host:$remote_dir/" > "$comparison"

if test -s "$comparison"; then
    ssh -o BatchMode=yes "$remote_host" \
        "printf 'checksum_verification=failed\\ncompleted_utc=%s\\n' '\$(date -u +%FT%TZ)' > '$receipt_dir/VERIFY_FAILED'"
    cat "$comparison" >&2
    exit 1
fi

source_bytes=$(du -s -B1 "$source_dir" | awk '{print $1}')
file_count=$(find "$source_dir" -type f | wc -l)
verified_utc=$(date -u +%FT%TZ)
ssh -o BatchMode=yes "$remote_host" \
    "printf 'comparison=rsync_checksum_clean\\nsource_bytes=%s\\nfiles=%s\\nverified_utc=%s\\n' '$source_bytes' '$file_count' '$verified_utc' > '$receipt_dir/VERIFIED' && sync"

case "$source_dir" in
    /home/joe/Bentley/SD) find "$source_dir" -depth -delete ;;
    *) echo "refusing unsafe source target" >&2; exit 2 ;;
esac
