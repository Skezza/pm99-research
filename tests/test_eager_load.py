"""Test for the eager loader that ensures DB FDI/PKF files are loaded into memory."""
import pytest
from pm99_editor.datastore import DataStore, resolve_db_root


def test_eager_load_db_files():
    # Resolve DB root; skip if not present in this environment
    try:
        db_root = resolve_db_root()
    except FileNotFoundError:
        pytest.skip("DB root not found; skipping eager-load test")

    ds = DataStore(db_root=str(db_root))
    files = ds.load_all()

    # Expect at least one DB file in the repo's DBDAT; otherwise the test is not meaningful.
    assert len(files) > 0, "No DB files were loaded by DataStore.load_all()"

    # Validate each loaded entry is non-empty bytes
    for key, data in files.items():
        assert isinstance(data, (bytes, bytearray)), f"Loaded file {key} is not bytes"
        assert len(data) > 0, f"Loaded file {key} is empty"

    # Basic index consistency checks
    num_files, total_bytes = ds.summary()
    assert num_files == len(files)
    assert total_bytes == sum(len(v) for v in files.values())