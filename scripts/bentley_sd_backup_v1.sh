#!/usr/bin/env bash
set -euo pipefail

readonly source_dir="/home/joe/Bentley/SD"
readonly remote_host="192.168.1.133"
readonly remote_dir="/srv/hdd/pm99-archive/backups/bentley-sd-20260902"
readonly receipt_dir="/srv/hdd/pm99-archive/receipts/bentley-sd-20260902"

test -d "$source_dir"
ssh -o BatchMode=yes "$remote_host" "mkdir -p '$remote_dir' '$receipt_dir'"
rsync -a --partial --append-verify --human-readable --info=progress2,stats2 \
    -e 'ssh -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=6' \
    "$source_dir/" "$remote_host:$remote_dir/"

file_count=$(find "$source_dir" -type f | wc -l)
completed_utc=$(date -u +%FT%TZ)
ssh -o BatchMode=yes "$remote_host" \
    "printf 'source=%s\\nfiles=%s\\ncompleted_utc=%s\\n' '$source_dir' '$file_count' '$completed_utc' > '$receipt_dir/TRANSFER_COMPLETE' && sync"
