#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
game_dir="${root_dir}/game"

if ! command -v wine >/dev/null 2>&1; then
  echo "Wine is not installed. See ${root_dir}/README.md." >&2
  exit 2
fi
if [[ -z "${DISPLAY:-}" ]]; then
  echo "DISPLAY is not set; launch this from your desktop terminal session." >&2
  exit 2
fi

cd "${game_dir}"
exec env \
  WINEPREFIX="${PM99_POC_WINEPREFIX:-${root_dir}/wineprefix-original}" \
  WINEDEBUG="${WINEDEBUG:--all}" \
  WINEDLLOVERRIDES="ddraw=b" \
  wine "${game_dir}/MANAGPRE.EXE"
