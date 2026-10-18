#!/usr/bin/env python3
"""Materialise compatibility aliases from one verified immutable revision.

The atomic ``current.json`` manifest is authoritative.  This helper verifies
every referenced revision artifact before copying its exact bytes to the old
well-known season filenames.  ``aliases-current.json`` is written last, so a
consumer can reject an interrupted compatibility refresh.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.season_historical_squad_backfill_batch_v1 import CURRENT_SCHEMA
from scripts.capture_transfermarkt_historical_squads_v1 import canonical_bytes

SCHEMA = "pm99-historical-squad-alias-receipt-v1"


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f".{path.name}-", dir=path.parent, delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def materialise(season_dir: Path) -> dict[str, Any]:
    root = season_dir.resolve()
    manifest_raw = (root / "current.json").read_bytes()
    manifest = json.loads(manifest_raw)
    if not isinstance(manifest, Mapping) or manifest.get("schema_version") != CURRENT_SCHEMA:
        raise ValueError(f"current.json must use {CURRENT_SCHEMA}")
    rows: list[dict[str, str]] = []
    for name, declaration in sorted(manifest.get("artifacts", {}).items()):
        relative = Path(str(declaration.get("path") or ""))
        source = (root / relative).resolve()
        try:
            source.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"revision artifact escapes season directory: {relative}") from exc
        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != declaration.get("sha256"):
            raise ValueError(f"revision artifact hash mismatch: {relative}")
        alias = root / source.name
        _atomic_write(alias, payload)
        rows.append({"artifact": str(name), "alias": alias.name, "sha256": digest})
    receipt = {
        "aliases": rows, "current_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "revision_id": manifest["revision_id"], "schema_version": SCHEMA,
        "season": manifest["season"],
    }
    _atomic_write(root / "aliases-current.json", canonical_bytes(receipt))
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season_dir", type=Path, nargs="+")
    args = parser.parse_args(argv)
    results = [materialise(path) for path in args.season_dir]
    print(json.dumps(results, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
