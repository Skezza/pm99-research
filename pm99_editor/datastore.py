"""
Eager in-memory datastore for PM99 DB files (FDI and PKF).
It discovers files under a DB root and reads them into memory.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

DEFAULT_EAGER_MAX_BYTES = int(os.environ.get("PM99_EAGER_MAX_BYTES", "200000000"))  # 200MB


def resolve_db_root(preferred: Optional[str] = None) -> Path:
    """
    Resolve the DB root directory.

    Order:
      1. preferred (if provided and exists)
      2. PM99_DB_ROOT environment variable
      3. ./DBDAT
      4. ./pm99_editor/DBDAT
    """
    candidates: List[Path] = []
    if preferred:
        candidates.append(Path(preferred))
    env = os.environ.get("PM99_DB_ROOT")
    if env:
        candidates.append(Path(env))
    candidates.extend([Path("DBDAT"), Path("pm99_editor/DBDAT")])

    for c in candidates:
        try:
            if c.exists() and c.is_dir():
                return c.resolve()
        except Exception:
            logger.debug("Skipping candidate %s due to error", c, exc_info=True)

    checked = ", ".join(str(c) for c in candidates)
    raise FileNotFoundError(f"DB root not found. Checked: {checked}")


class DataStore:
    """Simple eager in-memory store for FDI and PKF files."""

    def __init__(self, db_root: Optional[str] = None, eager_max_bytes: Optional[int] = None):
        self.db_root = resolve_db_root(db_root)
        self.eager_max_bytes = eager_max_bytes or DEFAULT_EAGER_MAX_BYTES
        self.files: Dict[str, bytes] = {}
        self.index: Dict[str, Dict[str, Any]] = {}
        self.total_bytes: int = 0
        self.loaded: bool = False

    def discover_files(self) -> List[Path]:
        """Find candidate files under the DB root (.FDI / .PKF, case-insensitive)."""
        files: List[Path] = []
        for p in sorted(self.db_root.rglob("*")):
            try:
                if not p.is_file():
                    continue
                if p.suffix.lower() in (".fdi", ".pkf"):
                    files.append(p)
            except Exception:
                logger.debug("Skipping path %s during discovery", p, exc_info=True)
        return files

    def load_all(self) -> Dict[str, bytes]:
        """
        Eagerly load discovered FDI/PKF files into memory.
        Raises MemoryError if eager_max_bytes would be exceeded.
        """
        files = self.discover_files()
        logger.info("Discovered %d DB files under %s", len(files), self.db_root)
        accumulated = 0
        for p in files:
            try:
                data = p.read_bytes()
                size = len(data)
                accumulated += size
                if accumulated > self.eager_max_bytes:
                    raise MemoryError(
                        f"Eager load aborted: accumulated bytes {accumulated} exceed cap {self.eager_max_bytes}"
                    )
                key = str(p.relative_to(self.db_root))
                sample = data[:256]
                mtime = p.stat().st_mtime
                self.files[key] = data
                self.index[key] = {"path": str(p), "size": size, "mtime": mtime, "sample": sample}
            except Exception:
                logger.exception("Failed to read file %s; skipping", p)

        self.total_bytes = sum(item["size"] for item in self.index.values())
        self.loaded = True
        logger.info("Eager load complete: %d files, %d bytes", len(self.files), self.total_bytes)
        return self.files

    def get(self, key: str) -> Optional[bytes]:
        """Return raw bytes for a loaded file (key is path relative to DB root)."""
        return self.files.get(key)

    def keys(self) -> List[str]:
        return list(self.files.keys())

    def summary(self) -> Tuple[int, int]:
        """(num_files, total_bytes)"""
        return len(self.files), self.total_bytes

    def top_n_largest(self, n: int = 5) -> List[Tuple[str, int]]:
        items = sorted(((k, meta["size"]) for k, meta in self.index.items()), key=lambda x: x[1], reverse=True)
        return items[:n]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ds = DataStore()
    ds.load_all()
    print(f"Loaded {len(ds.files)} files ({ds.total_bytes} bytes) from {ds.db_root}")