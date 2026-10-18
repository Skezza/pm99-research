#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
venv_dir="$repo_dir/.local/venvs/season-pipeline"

if [[ ! -x "$venv_dir/bin/python" ]]; then
  python3 -m venv "$venv_dir"
fi

if ! "$venv_dir/bin/python" -c 'import pytest, jsonschema, PIL, requests, numpy, cv2' >/dev/null 2>&1; then
  "$venv_dir/bin/python" -m pip install -r "$repo_dir/requirements-season-dev.txt"
fi

export PYTHONPATH="$repo_dir/upstream/pm99-skezmod-db-editor:$repo_dir${PYTHONPATH:+:$PYTHONPATH}"
exec "$venv_dir/bin/python" -m pytest \
  "$repo_dir/scripts/test_season_pipeline_v2.py" \
  "$repo_dir/scripts/test_season_release_registry_v1.py" \
  "$repo_dir/scripts/test_pm99_season_qa_v1.py" \
  "$repo_dir/scripts/test_season_portrait_pipeline_v1.py" \
  "$repo_dir/scripts/test_season_historical_photo_qa_v1.py" \
  "$@"
