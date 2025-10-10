# Ensure repository root is on sys.path so pytest can import app
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

# Session-scoped optional eager preload fixture.
# Enable by setting environment variable PM99_EAGER_CACHE=1 (and optionally PM99_EAGER_MAX_BYTES)
# This fixture is autouse but is a no-op unless the env var is set, so default test behaviour is unchanged.
import os
from app.datastore import DataStore, _EAGER_CACHE

@pytest.fixture(scope="session", autouse=True)
def eager_datastore_cache():
    """Preload DB files once for the test session when PM99_EAGER_CACHE=1.

    This reduces repeated disk reads/parsing for tests that create new DataStore instances
    or load DB files repeatedly. If the DB root or files are missing, the fixture is a no-op.
    """
    if os.environ.get("PM99_EAGER_CACHE", "0") != "1":
        return None

    try:
        ds = DataStore()
        ds.load_all()
    except (FileNotFoundError, MemoryError):
        # Skip caching if data missing or eager cap too small
        return None
    except Exception:
        # Non-fatal; do not break tests
        return None

    try:
        cache_key = (str(ds.db_root), ds.eager_max_bytes)
        _EAGER_CACHE[cache_key] = {"files": ds.files, "index": ds.index, "total_bytes": ds.total_bytes}
    except Exception:
        pass

    return ds
