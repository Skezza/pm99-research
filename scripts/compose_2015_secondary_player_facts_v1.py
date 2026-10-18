#!/usr/bin/env python3
"""Compose compatible source-only 2015 player-fact receipts.

Several exact-identity sources can each cover a different missing biography
field.  This adapter makes their agreement explicit before the review-overlay
writer sees a single patch.  Conflicting source values are reported as a gap,
never selected by source priority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_2015_fifa16_secondary_player_facts_v1 as fifa16  # noqa: E402
from scripts import capture_2015_declared_historical_player_facts_v1 as declared  # noqa: E402
from scripts import capture_2015_sofifa_secondary_player_facts_v1 as sofifa  # noqa: E402
from scripts import capture_2015_wikipedia_player_facts_v1 as wikipedia  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-world-2015-composed-secondary-player-facts-v1"
ACCEPTED = {fifa16.SCHEMA, sofifa.SCHEMA, wikipedia.SCHEMA, declared.SCHEMA}


class FactCompositionError(ValueError):
    """A secondary-fact receipt cannot be combined safely."""


def _read(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FactCompositionError(f"invalid receipt: {path}") from exc
    if not isinstance(value, dict) or raw != package_v2.canonical_json_bytes(value):
        raise FactCompositionError(f"receipt must be canonical JSON: {path}")
    if value.get("schema_version") not in ACCEPTED:
        raise FactCompositionError(f"unsupported player-fact receipt schema: {path}")
    return value, raw


def compose(receipts: Sequence[tuple[Path, Mapping[str, Any], bytes]]) -> dict[str, Any]:
    if not receipts:
        raise FactCompositionError("at least one receipt is required")
    base_hashes = {
        str((receipt.get("sources") or {}).get("base_package_sha256") or "")
        for _path, receipt, _raw in receipts
    }
    if len(base_hashes) != 1 or not next(iter(base_hashes)):
        raise FactCompositionError("all player-fact receipts must bind to one base package")
    values: dict[str, dict[str, set[Any]]] = defaultdict(lambda: defaultdict(set))
    source_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path, receipt, _raw in receipts:
        for row in receipt.get("rows") or []:
            if not isinstance(row, Mapping):
                raise FactCompositionError("receipt has a malformed fact row")
            player_id, facts = row.get("player_id"), row.get("facts")
            if not isinstance(player_id, str) or not isinstance(facts, Mapping):
                raise FactCompositionError("receipt fact row lacks player ID or facts")
            source_rows[player_id].append({"path": path, "row": row})
            for field, value in facts.items():
                values[player_id][str(field)].add(value)
    rows: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for player_id in sorted(values):
        disputed = {field: sorted(items, key=repr) for field, items in values[player_id].items() if len(items) != 1}
        if disputed:
            conflicts.append({"player_id": player_id, "conflicting_fields": disputed})
            continue
        first = source_rows[player_id][0]["row"]
        rows.append({
            "player_id": player_id,
            "carrier_id": first.get("carrier_id"),
            "player_name": first.get("player_name"),
            "source_name": first.get("source_name"),
            "missing_fields": first.get("missing_fields"),
            "facts": {field: next(iter(items)) for field, items in sorted(values[player_id].items())},
            "source_receipts": [
                {"path": entry["path"].resolve().relative_to(ROOT).as_posix(),
                 "source_name": entry["row"].get("source_name")}
                for entry in source_rows[player_id]
            ],
            "reason": "all exact-identity secondary-fact sources agree on each emitted field",
        })
    sourced = Counter(field for row in rows for field in row["facts"])
    return {
        "schema_version": SCHEMA,
        "policy": "compose only exact-identity source receipts bound to one package; require exact agreement per player field; conflicts stay explicit",
        "sources": {
            "base_package_sha256": next(iter(base_hashes)),
            "receipts": [
                {"path": path.resolve().relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(raw).hexdigest(), "schema_version": receipt["schema_version"]}
                for path, receipt, raw in receipts
            ],
        },
        "coverage": {
            "input_receipt_count": len(receipts), "player_rows_with_at_least_one_sourced_fact": len(rows),
            "sourced_field_counts": dict(sorted(sourced.items())), "conflicting_player_count": len(conflicts),
        },
        "rows": rows, "conflicts": conflicts,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise FactCompositionError(f"refusing to overwrite output: {args.output}")
        paths = [path.resolve() for path in args.receipt]
        if len(paths) != len(set(paths)):
            raise FactCompositionError("each receipt may be supplied once")
        result = compose([(path, *_read(path)) for path in paths])
    except (OSError, FactCompositionError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(package_v2.canonical_json_bytes(result))
    print(json.dumps(result["coverage"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
