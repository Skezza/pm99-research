# Ensure repository root is on sys.path so pytest can import pm99_editor
import os
import sys
from pathlib import Path

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _require_data_file(path: str) -> Path:
    file_path = Path(path)
    if not file_path.exists():
        pytest.skip(f"Required data file not found: {path}")
    return file_path


@pytest.fixture(scope="module")
def players_fdi_path():
    """Return the players database path or skip if the fixture is unavailable."""

    return _require_data_file("DBDAT/JUG98030.FDI")


@pytest.fixture(scope="module")
def teams_fdi_path():
    """Return the teams database path or skip if the fixture is unavailable."""

    return _require_data_file("DBDAT/EQ98030.FDI")


@pytest.fixture(scope="module")
def coaches_fdi_path():
    """Return the coaches database path or skip if the fixture is unavailable."""

    return _require_data_file("DBDAT/ENT98030.FDI")