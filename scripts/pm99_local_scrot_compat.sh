#!/usr/bin/env bash
# Local runner compatibility wrapper for workstations without scrot.
# The PM99 runner invokes `scrot <output.png>` first.  Returning a controlled
# failure makes it select its next, window-specific ImageMagick `import`
# fallback; root-window capture is black under this local X setup.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: scrot <output.png>" >&2
  exit 2
fi

echo "scrot is unavailable; use native_runner's window-specific import fallback" >&2
exit 127
