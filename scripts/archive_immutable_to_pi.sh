#!/usr/bin/env bash
set -euo pipefail

if (( $# < 1 )); then
    echo "usage: $0 DIRECTORY [...]" >&2
    exit 2
fi

readonly source_root="${ARCHIVE_SOURCE_ROOT:-/home/joe/pm99-research/.local/research-probes}"
readonly remote_host="raspberrypi-2.local"
readonly archive_root="/srv/hdd/pm99-archive"
readonly remote_section="${ARCHIVE_REMOTE_SECTION:-evidence/research-probes}"
readonly batch="${ARCHIVE_BATCH:-research-probes-20260902}"

case "$source_root" in
    /home/joe/pm99-research/.local|/home/joe/pm99-research/.local/research-probes|/home/joe/pm99-research/.local/season-2015-16|/home/joe/pm99-research)
        ;;
    *)
        echo "refusing unapproved source root: $source_root" >&2
        exit 2
        ;;
esac

case "$remote_section" in
    evidence/research-probes|evidence/repo-artifacts|backups/runlogs|packages/upscale-poc|packages/2015-superseded-builds)
        ;;
    *)
        echo "refusing unapproved remote section: $remote_section" >&2
        exit 2
        ;;
esac

for name in "$@"; do
    case "$name" in
        *live*|*current*|*..*|*/*)
            echo "refusing unsafe or live name: $name" >&2
            exit 2
            ;;
    esac

    source_dir="$source_root/$name"
    test -d "$source_dir"
    local_count=$(find "$source_dir" -mindepth 1 | wc -l)

    ssh "$remote_host" "mkdir -p '$archive_root/incoming/$batch' '$archive_root/$remote_section' '$archive_root/receipts/$batch'"
    tar --sort=name --mtime='UTC 2026-09-02' --owner=0 --group=0 --numeric-owner \
        -C "$source_root" -cf - "$name" \
        | zstd -T0 -3 \
        | ssh "$remote_host" "dd of='$archive_root/incoming/$batch/$name.tar.zst.partial' status=none conv=fsync"

    remote_count=$(ssh "$remote_host" \
        "zstd -t '$archive_root/incoming/$batch/$name.tar.zst.partial' >/dev/null && zstd -dc '$archive_root/incoming/$batch/$name.tar.zst.partial' | tar -tf - | tail -n +2 | wc -l")
    test "$local_count" = "$remote_count"
    remote_sha=$(ssh "$remote_host" "sha256sum '$archive_root/incoming/$batch/$name.tar.zst.partial'" | awk '{print $1}')

    ssh "$remote_host" \
        "mv '$archive_root/incoming/$batch/$name.tar.zst.partial' '$archive_root/$remote_section/$name.tar.zst' && printf 'sha256=%s\\nentries=%s\\nsource=%s/%s\\nverified_zstd=yes\\n' '$remote_sha' '$remote_count' '$source_root' '$name' > '$archive_root/receipts/$batch/$name.txt' && sync"

    find "$source_dir" -depth -delete
    echo "archived $name entries=$remote_count sha256=$remote_sha"
done
