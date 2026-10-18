#!/usr/bin/env python3
"""Compose a primary opening-lineup receipt with one disjoint raw supplement."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA = "pm99-composed-opening-lineup-source-v1"
RAW_SCHEMA = "pm99-transfermarkt-opening-lineup-source-v1"


class LineupCompositionError(ValueError):
    """Lineup evidence cannot be composed without changing its scope."""


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LineupCompositionError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise LineupCompositionError(f"{label} must be a JSON object")
    return value, hashlib.sha256(payload).hexdigest()


def _selector(row: Mapping[str, Any]) -> tuple[str, str, str]:
    value = row.get("source_selector")
    if not isinstance(value, Mapping):
        raise LineupCompositionError("lineup row has no source selector")
    key = tuple(str(value.get(field) or "").strip() for field in ("country_catalog", "competition_catalog", "club_name"))
    if not all(key):
        raise LineupCompositionError("lineup row has an incomplete selector")
    return key  # type: ignore[return-value]


def compose(
    *, primary: Mapping[str, Any], primary_sha256: str,
    supplement: Mapping[str, Any], supplement_sha256: str,
    source_capture_sha256: str, lineup_source_selection_sha256: str | None,
) -> dict[str, Any]:
    if primary.get("schema_version") not in {RAW_SCHEMA, SCHEMA} or supplement.get("schema_version") != RAW_SCHEMA:
        raise LineupCompositionError("unsupported primary or supplement lineup schema")
    year = primary.get("season_start_year")
    if not isinstance(year, int) or supplement.get("season_start_year") != year:
        raise LineupCompositionError("primary and supplement target different seasons")
    primary_source = (primary.get("source") or {}).get("source_capture_sha256")
    if primary_source not in {source_capture_sha256, lineup_source_selection_sha256}:
        raise LineupCompositionError("primary lineup receipt is not bound to the current source or selector projection")
    if (supplement.get("source") or {}).get("source_capture_sha256") != source_capture_sha256:
        raise LineupCompositionError("supplement lineup receipt is not bound to the current source")
    captured: dict[tuple[str, str, str], dict[str, Any]] = {}
    for label, document in (("primary", primary), ("supplement", supplement)):
        rows = document.get("clubs")
        if not isinstance(rows, list):
            raise LineupCompositionError(f"{label} lineup receipt has no club rows")
        for row in rows:
            if not isinstance(row, Mapping):
                raise LineupCompositionError(f"{label} lineup receipt has a malformed club")
            selector = _selector(row)
            if selector in captured:
                raise LineupCompositionError(f"primary and supplement overlap at {selector}")
            captured[selector] = dict(row)
    primary_failures = primary.get("failures") if isinstance(primary.get("failures"), list) else []
    supplement_failures = supplement.get("failures") if isinstance(supplement.get("failures"), list) else []
    return {
        "schema_version": SCHEMA,
        "season_start_year": year,
        "snapshot_policy": "first domestic-league fixture per club; primary and fixed-carrier historic-ID supplements remain separately hash-bound",
        "source": {
            "name": "Composed published opening-lineup evidence",
            "source_capture_sha256": source_capture_sha256,
            "lineup_source_selection_sha256": lineup_source_selection_sha256,
            "primary_lineup_sha256": primary_sha256,
            "historic_id_supplement_sha256": supplement_sha256,
            "cache_files": list((primary.get("source") or {}).get("cache_files") or []),
            "supplement_cache_files": list((supplement.get("source") or {}).get("cache_files") or []),
            "credits": ["Transfermarkt"],
        },
        "summary": {
            "captured_club_count": len(captured),
            "primary_captured_club_count": len(primary.get("clubs") or []),
            "historic_id_supplemented_club_count": len(supplement.get("clubs") or []),
            "failed_club_count": len(primary_failures) + len(supplement_failures),
        },
        "clubs": [captured[key] for key in sorted(captured)],
        "failures": [*primary_failures, *supplement_failures],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--supplement", type=Path, required=True)
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--lineup-source-selection", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise LineupCompositionError(f"refusing to overwrite composed opening lineups: {args.output}")
        primary, primary_sha = _load(args.primary, "primary opening lineups")
        supplement, supplement_sha = _load(args.supplement, "opening-lineup supplement")
        _source, source_sha = _load(args.source_capture, "source capture")
        selection_sha = _load(args.lineup_source_selection, "lineup source selection")[1] if args.lineup_source_selection else None
        result = compose(primary=primary, primary_sha256=primary_sha, supplement=supplement, supplement_sha256=supplement_sha,
                         source_capture_sha256=source_sha, lineup_source_selection_sha256=selection_sha)
    except (OSError, LineupCompositionError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
