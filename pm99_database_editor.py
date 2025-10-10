# Compatibility shim for legacy pm99_database_editor imports
# Exports a PlayerRecord constructor that delegates to app.models.PlayerRecord.from_bytes
from typing import Any, List

try:
    from app.models import PlayerRecord as _PRClass
except Exception:
    _PRClass = None

try:
    from app.xor import decode_entry as xor_decode, encode_entry as xor_encode, read_string, write_string
except Exception:
    def xor_decode(*args, **kwargs):
        raise RuntimeError("app.xor.decode_entry not available")
    def xor_encode(*args, **kwargs):
        raise RuntimeError("app.xor.encode_entry not available")
    def read_string(*args, **kwargs):
        raise RuntimeError("app.xor.read_string not available")
    def write_string(*args, **kwargs):
        raise RuntimeError("app.xor.write_string not available")

def find_player_records(path, **kwargs):
    """
    Convenience wrapper to return parsed player records from a given FDI file path.
    Returns whatever app.io.FDIFile exposes (list or records).
    """
    try:
        from app.io import FDIFile
        f = FDIFile(path)
        f.load()
        # Prefer a list_players helper if present
        if hasattr(f, "list_players"):
            return f.list_players()
        if hasattr(f, "records"):
            return f.records
        return []
    except Exception as e:
        raise RuntimeError(f"find_player_records failed: {e}")

def PlayerRecord(data: bytes, offset: int = 0, version: int = 700):
    """Compatibility constructor: returns instance of app.models.PlayerRecord."""
    if _PRClass is None:
        raise ImportError("app.models.PlayerRecord is not available")
    return _PRClass.from_bytes(data, offset, version)

__all__ = [
    "PlayerRecord",
    "find_player_records",
    "xor_decode",
    "xor_encode",
    "read_string",
    "write_string",
]
