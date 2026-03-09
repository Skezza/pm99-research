#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCHER_DIR="${ROOT_DIR}/upstream/pm99-skezmod-patcher"

if [[ ! -d "${PATCHER_DIR}" ]]; then
  echo "Patcher submodule not found at ${PATCHER_DIR}" >&2
  exit 1
fi

cd "${PATCHER_DIR}"

if [[ $# -eq 0 ]]; then
  exec python3 skezmod.py --help
fi

exec "$@"
