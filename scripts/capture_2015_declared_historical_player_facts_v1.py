#!/usr/bin/env python3
"""Record a small, fully cited set of target-season player facts.

This is intentionally a source receipt rather than a hand edit.  It covers
facts that are both visible in the 2015/16 recipe and awkward for the generic
English-Wikipedia title lane: players in the Luxembourg and Romanian source
tails, plus their contemporaneous club evidence.  Every row is pinned to an
existing ``player_id`` *and* its declared source identity.  A changed carrier
or source name makes the capture fail rather than silently applying a fact to
somebody else.

The receipt may contain an unrepresentable PM99 country (currently Curaçao).
That is useful source truth: the compiler's explicit XXX policy, not an
invented substitute, decides what can be written to the original game table.
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


SCHEMA = "pm99-world-2015-declared-historical-player-facts-v1"

# Each source is either a contemporaneous 2015 squad document or a player
# biography used solely for the player's sporting nationality.  These are
# deliberate exact-identity records, not search-result guesses.
DECLARED_FACTS: tuple[dict[str, Any], ...] = (
    {
        "player_id": "player-14179", "carrier_id": 14179,
        "source_name": "Sanaa Altama", "facts": {"nationality": "CHA"},
        "source_title": "Petrolul 2015/16 opening squad and shirt numbers",
        "source_url": "https://www.observatorulph.ro/sport/55148-esti-fan-petrolul-lotul-si-numerele-jucatorilor-de-pe-tricou-pentru-sezonul-2015-2016",
        "source_scope": "published 11 July 2015 opening-squad nationality: France/Chad; sport nationality Chad",
    },
    {
        "player_id": "player-2315", "carrier_id": 2315,
        "source_name": "Tim Heinz", "facts": {"nationality": "LUX"},
        "source_title": "Tim Heinz biography",
        "source_url": "https://en.wikipedia.org/wiki/Tim_Heinz",
        "source_scope": "Luxembourg international player biography",
    },
    {
        "player_id": "player-2316", "carrier_id": 2316,
        "source_name": "Joël Kitenge", "facts": {"nationality": "LUX"},
        "source_title": "Joël Kitenge biography",
        "source_url": "https://en.wikipedia.org/wiki/Jo%C3%ABl_Kitenge",
        "source_scope": "Luxembourg international player biography",
    },
    {
        "player_id": "player-2317", "carrier_id": 2317,
        "source_name": "René Peters", "facts": {"nationality": "LUX"},
        "source_title": "René Peters biography",
        "source_url": "https://en.wikipedia.org/wiki/Ren%C3%A9_Peters_(footballer)",
        "source_scope": "Luxembourg international player biography",
    },
    {
        "player_id": "player-32104", "carrier_id": 32104,
        "source_name": "Kadar Hassan", "facts": {"nationality": "DJI"},
        "source_title": "Petrolul 2015/16 opening squad and shirt numbers",
        "source_url": "https://www.observatorulph.ro/sport/55148-esti-fan-petrolul-lotul-si-numerele-jucatorilor-de-pe-tricou-pentru-sezonul-2015-2016",
        "source_scope": "published 11 July 2015 opening squad calls Ismail Ahmed Kadar Hassan France/Djibouti; sporting nationality Djibouti",
    },
    {
        "player_id": "player-32106", "carrier_id": 32106,
        "source_name": "Gevaro Nepomuceno", "facts": {"nationality": "CUW"},
        "source_title": "Petrolul 2015/16 opening squad and shirt numbers",
        "source_url": "https://www.observatorulph.ro/sport/55148-esti-fan-petrolul-lotul-si-numerele-jucatorilor-de-pe-tricou-pentru-sezonul-2015-2016",
        "source_scope": "published 11 July 2015 opening squad calls Gevaro Nepomuceno Netherlands/Curaçao; sporting nationality Curaçao",
    },
    {
        "player_id": "player-32109", "carrier_id": 32109,
        "source_name": "Karim Ziani", "facts": {"nationality": "ALG"},
        "source_title": "Karim Ziani biography",
        "source_url": "https://en.wikipedia.org/wiki/Karim_Ziani",
        "source_scope": "Algeria international player biography",
    },
)


class DeclaredFactCaptureError(ValueError):
    """A bound historical-fact record cannot safely target this recipe."""


def capture(*, package: Mapping[str, Any], package_sha256: str) -> dict[str, Any]:
    players = {
        str(row.get("id") or ""): row
        for row in package.get("players") or []
        if isinstance(row, Mapping)
    }
    rows: list[dict[str, Any]] = []
    for declared in DECLARED_FACTS:
        player_id = str(declared["player_id"])
        player = players.get(player_id)
        if player is None:
            raise DeclaredFactCaptureError(f"missing declared player {player_id}")
        if int(player.get("carrier_id") or 0) != int(declared["carrier_id"]):
            raise DeclaredFactCaptureError(f"carrier mismatch for {player_id}")
        if str(player.get("source_name") or "") != str(declared["source_name"]):
            raise DeclaredFactCaptureError(f"source identity mismatch for {player_id}")
        facts = player.get("facts")
        if not isinstance(facts, Mapping):
            raise DeclaredFactCaptureError(f"missing facts for {player_id}")
        absent = {
            field: value for field, value in dict(declared["facts"]).items()
            if facts.get(field) is None or isinstance(facts.get(field), Mapping)
        }
        if not absent:
            raise DeclaredFactCaptureError(f"declared facts are already present for {player_id}")
        rows.append({
            "player_id": player_id, "carrier_id": int(declared["carrier_id"]),
            "player_name": str(player.get("name") or ""),
            "source_name": str(declared["source_name"]),
            "missing_fields": sorted(absent), "facts": dict(sorted(absent.items())),
            "source_title": str(declared["source_title"]),
            "source_url": str(declared["source_url"]),
            "source_scope": str(declared["source_scope"]),
            "reason": "target-season carrier and declared source identity both match a cited historical fact",
        })
    return {
        "schema_version": SCHEMA,
        "policy": "source-only declared historical facts; exact player ID, carrier and source-name binding; fill only absent recipe fields; no binary write",
        "sources": {"base_package_sha256": package_sha256},
        "coverage": {"declared_fact_row_count": len(rows), "sourced_field_counts": {"nationality": len(rows)}},
        "rows": sorted(rows, key=lambda row: row["player_id"]),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise DeclaredFactCaptureError(f"refusing to overwrite receipt: {args.output}")
        package = package_v2.read_canonical_package(args.package)
        package_v2.validate_package(package)
        raw = args.package.read_bytes()
        result = capture(package=package, package_sha256=hashlib.sha256(raw).hexdigest())
    except (OSError, package_v2.PackageValidationError, DeclaredFactCaptureError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(package_v2.canonical_json_bytes(result))
    print(json.dumps(result["coverage"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
