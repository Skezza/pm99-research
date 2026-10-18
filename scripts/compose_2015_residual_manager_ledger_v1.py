#!/usr/bin/env python3
"""Adapt the closed 2015 residual-manager receipt into a write ledger.

The receipt remains the historical authority.  This adapter contains no club
or manager names of its own: it preserves each reviewed fixed carrier and the
source evidence needed by the existing manager-only compiler repair.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-opening-manager-ledger-v1"
RESIDUAL_SCHEMA = "pm99-world-2015-residual-manager-history-v1"


class ResidualLedgerError(ValueError):
    """The residual receipt cannot be promoted without an exact carrier."""


def build(receipt: Mapping[str, Any], *, receipt_sha256: str) -> dict[str, Any]:
    if receipt.get("schema_version") != RESIDUAL_SCHEMA:
        raise ResidualLedgerError(f"residual receipt must use {RESIDUAL_SCHEMA}")
    rows = receipt.get("rows")
    if not isinstance(rows, list):
        raise ResidualLedgerError("residual receipt has no rows")
    managers: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ResidualLedgerError("residual receipt has a malformed row")
        carrier_id = row.get("carrier_id")
        name = " ".join(str(row.get("manager_name") or "").split())
        club = " ".join(str(row.get("source_club_name") or "").split())
        if not isinstance(carrier_id, int) or carrier_id <= 0 or carrier_id in seen or not name or not club:
            raise ResidualLedgerError("residual receipt row lacks a unique carrier, source club or manager")
        seen.add(carrier_id)
        managers.append({
            "carrier_id": carrier_id,
            "source_selector": {"club_name": club},
            "manager_name": name,
            "opening_fixture_date": row.get("snapshot_as_of"),
            "resolution_method": f"residual-target-{row.get('source_method')}-history",
            "evidence": {
                "source_name": row.get("source_name"),
                "source_url": row.get("source_url"),
                "source_snapshot_sha256": row.get("source_snapshot_sha256"),
            },
        })
    if len(managers) != 26:
        raise ResidualLedgerError("residual receipt must close exactly 26 manager targets")
    return {
        "schema_version": SCHEMA,
        "season_start_year": 2015,
        "policy": "derived only from the closed 2015 residual-manager source receipt; explicit reviewed fixed-carrier join",
        "source": {"residual_manager_receipt_sha256": receipt_sha256},
        "managers": sorted(managers, key=lambda row: int(row["carrier_id"])),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--residual-receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ResidualLedgerError(f"refusing to overwrite output: {args.output}")
        raw = args.residual_receipt.read_bytes()
        receipt = json.loads(raw.decode("utf-8"))
        if not isinstance(receipt, dict) or raw != package_v2.canonical_json_bytes(receipt):
            raise ResidualLedgerError("residual receipt must be canonical JSON")
        result = build(receipt, receipt_sha256=hashlib.sha256(raw).hexdigest())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ResidualLedgerError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(package_v2.canonical_json_bytes(result))
    print(json.dumps({"manager_count": len(result["managers"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
