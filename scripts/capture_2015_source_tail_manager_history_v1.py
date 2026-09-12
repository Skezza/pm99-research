#!/usr/bin/env python3
"""Capture early-season managers for the strict 2015 source-tail clubs.

The source-tail squad receipt already pins one historical Transfermarkt club
identity for every replacement carrier.  Reusing that identity is safer than
trying a second, fuzzy club-name search.  This command reads the published
manager history at the same early-season snapshot used by the global 2015
manager plan (2015-09-01).  It is source-only: an ambiguous manager, a name
PM99 cannot represent, or a malformed identity remains an explicit gap.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_2015_world_manager_transfermarkt_snapshot_v5 as manager_snapshot  # noqa: E402
from scripts import capture_opening_manager_history_supplements_v1 as manager_history  # noqa: E402
from scripts import capture_transfermarkt_opening_lineups_v1 as opening  # noqa: E402


SCHEMA = "pm99-world-2015-source-tail-manager-history-v1"
SOURCE_SCHEMA = "pm99-world-2015-source-tail-selected-package-v2"
AS_OF = date(2015, 9, 1)

# PM99 manager strings are CP1252.  These published 2015 manager names use
# Latin letters outside that code page.  The right-hand spelling is an
# explicit, reviewable ASCII transliteration; the published spelling remains
# in the source receipt.  This is never an automatic character-stripping
# fallback.
DOCUMENTED_PM99_LATIN_MANAGER_SPELLINGS = {
    (1403, "Marius Șumudică"): "Marius Sumudica",
    (2253, "Gediminas Jarmalavičius"): "Gediminas Jarmalavicius",
}


class SourceTailManagerError(ValueError):
    """A source-tail identity cannot prove one early-season manager."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _load(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceTailManagerError(f"cannot read selected source-tail package: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise SourceTailManagerError("selected source-tail package must be canonical JSON")
    if value.get("schema_version") != SOURCE_SCHEMA:
        raise SourceTailManagerError(f"selected source-tail package must use {SOURCE_SCHEMA}")
    return value, hashlib.sha256(raw).hexdigest()


def _targets(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    clubs = value.get("clubs")
    if not isinstance(clubs, list) or not clubs:
        raise SourceTailManagerError("selected source-tail package has no clubs")
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for club in clubs:
        if not isinstance(club, Mapping):
            raise SourceTailManagerError("selected source-tail package contains a malformed club")
        carrier = club.get("candidate_carrier_id")
        name = club.get("club_name")
        country = club.get("country_catalog")
        identity = club.get("source_identity")
        if (
            not isinstance(carrier, int)
            or carrier <= 0
            or carrier in seen
            or not isinstance(name, str)
            or not name.strip()
            or not isinstance(country, str)
            or not country.strip()
            or not isinstance(identity, Mapping)
        ):
            raise SourceTailManagerError("selected source-tail club lacks a unique carrier or source identity")
        club_id = identity.get("transfermarkt_club_id")
        slug = identity.get("transfermarkt_slug")
        if not isinstance(club_id, int) or club_id <= 0 or not isinstance(slug, str) or not slug.strip():
            raise SourceTailManagerError(f"source-tail club {carrier} has an invalid Transfermarkt identity")
        seen.add(carrier)
        result.append({
            "carrier_id": carrier,
            "source_club_name": " ".join(name.split()),
            "source_selector": {
                "country_catalog": " ".join(country.split()),
                "competition_catalog": "transfermarkt-2015-source-tail-domestic-opening-window",
                "club_name": " ".join(name.split()),
            },
            "transfermarkt_club_id": club_id,
            "transfermarkt_slug": slug.strip(),
            "pinned_squad_url": str(club.get("source_url") or "").strip(),
            "pinned_squad_sha256": str(club.get("source_sha256") or "").strip(),
            "opening_fixture_date": min(
                (
                    str(row.get("date") or "")
                    for row in club.get("opening_fixtures") or []
                    if isinstance(row, Mapping) and str(row.get("date") or "")
                ),
                default=None,
            ),
        })
    return sorted(result, key=lambda row: int(row["carrier_id"]))


def capture(
    *, source_tail: Mapping[str, Any], source_tail_sha256: str,
    cache: opening.SnapshotCache,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for target in _targets(source_tail):
        carrier = int(target["carrier_id"])
        club_id = int(target["transfermarkt_club_id"])
        slug = str(target["transfermarkt_slug"])
        url = f"{opening.BASE_URL}/{slug}/mitarbeiterhistorie/verein/{club_id}"
        key = f"manager-history/2015-source-tail/{carrier}-{club_id}.html"
        fixture_date = target["opening_fixture_date"]
        try:
            observed_on = date.fromisoformat(fixture_date) if fixture_date else AS_OF
        except ValueError as exc:
            raise SourceTailManagerError(
                f"source-tail club {carrier} has an invalid opening fixture date"
            ) from exc
        try:
            payload = cache.get(url, key)
            published_name, manager_id = manager_history.manager_at_date(payload, observed_on)
            manager_name = published_name
            spelling_method = "published-transfermarkt-display-name"
            if not manager_snapshot._safe_manager_name(manager_name):
                manager_name = DOCUMENTED_PM99_LATIN_MANAGER_SPELLINGS.get(
                    (carrier, published_name), ""
                )
                if not manager_snapshot._safe_manager_name(manager_name):
                    raise SourceTailManagerError(
                        "published manager display name requires a reviewed PM99 Latin spelling"
                    )
                spelling_method = (
                    "documented-pm99-latin-spelling-for-published-transfermarkt-name"
                )
            snapshot = cache.used[key]
            rows.append({
                **target,
                "snapshot_as_of": observed_on.isoformat(),
                "manager_snapshot_policy": (
                    "first-published-domestic-fixture-date"
                    if fixture_date else "fixed-early-season-snapshot-for-schedule-gap"
                ),
                "manager_name": manager_name,
                "published_manager_name": published_name,
                "pm99_spelling_method": spelling_method,
                "source_name": "Transfermarkt published club manager history",
                "source_url": url,
                "source_snapshot_sha256": snapshot["sha256"],
                "reason": (
                    f"manager id {manager_id} uniquely covers the "
                    f"{observed_on.isoformat()} opening-season snapshot for the exact "
                    "source-tail historical club identity"
                ),
            })
        except (OSError, ValueError, opening.CaptureError, manager_history.ManagerHistoryError, SourceTailManagerError) as exc:
            gaps.append({
                "carrier_id": carrier,
                "source_club_name": target["source_club_name"],
                "reason": str(exc),
            })
    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only; each carrier uses its pinned historical source-tail club identity; "
            "one published Transfermarkt manager must uniquely cover the first domestic fixture, "
            "or the fixed 2015-09-01 snapshot only where a documented schedule gap exists; "
            "no native/current-manager fallback and no automatic transliteration"
        ),
        "sources": {
            "source_tail_selected_package_sha256": source_tail_sha256,
            "manager_history_cache_files": [cache.used[key] for key in sorted(cache.used)],
        },
        "coverage": {
            "fallback_early_season_snapshot": AS_OF.isoformat(),
            "first_domestic_fixture_snapshot_count": sum(
                row["manager_snapshot_policy"] == "first-published-domestic-fixture-date"
                for row in rows
            ),
            "schedule_gap_snapshot_count": sum(
                row["manager_snapshot_policy"] == "fixed-early-season-snapshot-for-schedule-gap"
                for row in rows
            ),
            "source_tail_club_count": len(rows) + len(gaps),
            "dated_transfermarkt_manager_match_count": len(rows),
            "unresolved_manager_count": len(gaps),
            "unresolved_reason_counts": dict(sorted(Counter(row["reason"] for row in gaps).items())),
        },
        "rows": rows,
        "gaps": gaps,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-tail-selected-package", required=True, type=Path)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise SourceTailManagerError(f"refusing to overwrite source receipt: {args.output}")
        source_tail, source_tail_sha256 = _load(args.source_tail_selected_package)
        result = capture(
            source_tail=source_tail,
            source_tail_sha256=source_tail_sha256,
            cache=opening.SnapshotCache(args.cache_root, offline=args.offline, delay=args.delay),
        )
    except (OSError, SourceTailManagerError, opening.CaptureError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 1 if args.strict and result["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
