#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EDITOR_DIR="${ROOT_DIR}/upstream/pm99-skezmod-db-editor"

if [[ ! -d "${EDITOR_DIR}" ]]; then
  echo "Editor submodule not found at ${EDITOR_DIR}" >&2
  exit 1
fi

cd "${EDITOR_DIR}"

if [[ $# -eq 0 ]]; then
  exec python3 -m app.cli --help
fi

exec "$@"
