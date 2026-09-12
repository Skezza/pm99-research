#!/usr/bin/env python3
"""Bind the complete V2 source package to its checked roster-selection receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import compose_2015_source_tail_package_v1 as v1


SCHEMA = "pm99-world-2015-source-tail-selected-package-v2"
SOURCE_SCHEMA = "pm99-world-2015-source-tail-package-v2"
ORDER_SCHEMA = "pm99-world-2015-source-tail-opening-order-capture-v1"


class SelectedPackageError(ValueError):
    """A selection receipt cannot safely be promoted into V2 build input."""


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _read(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SelectedPackageError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_bytes(value):
        raise SelectedPackageError(f"{label} must be canonical JSON")
    return value, hashlib.sha256(raw).hexdigest()


def compose(*, source_package: Mapping[str, Any], source_sha256: str, order: Mapping[str, Any]) -> dict[str, Any]:
    if source_package.get("schema_version") != SOURCE_SCHEMA:
        raise SelectedPackageError("source package has an unsupported schema")
    if order.get("schema_version") != ORDER_SCHEMA:
        raise SelectedPackageError("opening-order receipt has an unsupported schema")
    order_source = order.get("source")
    if not isinstance(order_source, Mapping) or order_source.get("source_tail_package_sha256") != source_sha256:
        raise SelectedPackageError("opening-order receipt is not bound to this exact V2 source package")
    if order.get("gaps") != []:
        raise SelectedPackageError("opening-order receipt contains unresolved club gaps")
    source_clubs = source_package.get("clubs")
    order_clubs = order.get("clubs")
    if not isinstance(source_clubs, list) or not isinstance(order_clubs, list):
        raise SelectedPackageError("source package or opening-order receipt lacks clubs")
    expected = {club.get("candidate_carrier_id"): club for club in source_clubs if isinstance(club, Mapping)}
    if len(expected) != len(source_clubs) or len(expected) != len(order_clubs):
        raise SelectedPackageError("source package or opening-order receipt has duplicate or mismatched carriers")
    result: list[dict[str, Any]] = []
    selections = Counter()
    for ordered in order_clubs:
        if not isinstance(ordered, Mapping):
            raise SelectedPackageError("opening-order receipt has a malformed club")
        carrier_id = ordered.get("candidate_carrier_id")
        source = expected.get(carrier_id)
        if not isinstance(source, Mapping):
            raise SelectedPackageError(f"opening-order receipt has unexpected carrier {carrier_id!r}")
        for field in ("fixed_roster_slot_count", "country_catalog", "club_name", "target_article_title", "target_article_path"):
            if ordered.get(field) != source.get(field):
                raise SelectedPackageError(f"carrier {carrier_id} changed its source identity at {field}")
        capacity = source.get("fixed_roster_slot_count")
        players = ordered.get("players")
        if not isinstance(capacity, int) or not isinstance(players, list) or len(players) != capacity:
            raise SelectedPackageError(f"carrier {carrier_id} does not have exactly its immutable selected capacity")
        try:
            v1._validate_club(
                club=ordered,
                expected={
                    "capacity": capacity, "country_catalog": source["country_catalog"],
                    "target": {
                        "name": source["club_name"], "article_title": source["target_article_title"],
                        "article_path": source["target_article_path"],
                    },
                },
                capture=v1.CaptureInput("selected", "selected", ordered, "0" * 64),
            )
        except v1.SourceTailPackageError as exc:
            raise SelectedPackageError(str(exc)) from exc
        selection = ordered.get("selection")
        if not isinstance(selection, Mapping):
            raise SelectedPackageError(f"carrier {carrier_id} has no selection policy")
        status = (
            "published-dated-squad-number-order-exception"
            if selection.get("published_dated_squad_number_order_exception_count")
            else "opening-window-ordered-capacity-roster"
        )
        selections[status] += 1
        result.append({
            **dict(ordered),
            "source_package": {
                "source_package_sha256": source_sha256,
                "source_capture_sha256": (source.get("source_package") or {}).get("capture_sha256"),
                "route": "pinned-historic-season-squad",
                "roster_selection_status": status,
            },
        })
    result.sort(key=lambda club: int(club["candidate_carrier_id"]))
    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only selected V2 package; every carrier has exactly its immutable capacity; normal rows use "
            "published domestic opening fixtures, while four named source-schedule absences retain a distinct "
            "published dated-squad-number exception; no PM99 write"
        ),
        "sources": {
            "source_tail_package_sha256": source_sha256,
            "opening_order_schema": order["schema_version"],
        },
        "clubs": result,
        "summary": {
            "selected_carrier_count": len(result),
            "selected_player_count": sum(len(club["players"]) for club in result),
            "roster_selection_status_counts": dict(sorted(selections.items())),
            "opening_lineup_evidence_gap_club_count": sum(
                "opening_lineup_evidence_gap" in club for club in result
            ),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-package", required=True, type=Path)
    parser.add_argument("--opening-order", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"refusing to overwrite selected package: {args.output}")
    try:
        source_package, source_sha = _read(args.source_package, label="source package")
        order, _order_sha = _read(args.opening_order, label="opening-order receipt")
        result = compose(source_package=source_package, source_sha256=source_sha, order=order)
    except (OSError, SelectedPackageError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
