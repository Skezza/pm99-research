#!/usr/bin/env python3
"""Extract exact declared managers from a hash-bound allocated opening-lineup receipt.

This is deliberately narrower than a manager-history scrape.  Where the
dated club history overlaps two people, a published first-league match report
can itself declare one manager.  The extractor accepts only rows already
captured from such reports, records that report snapshot hash, and scopes the
result to unresolved selectors of an earlier raw manager supplement.  It
never supplies a fallback name or chooses between candidates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA = "pm99-opening-manager-supplement-v1"
LINEUP_SCHEMA = "pm99-transfermarkt-opening-lineup-source-v1"


class DeclaredManagerSupplementError(ValueError):
    """A declared-manager supplement cannot be proved from its inputs."""


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _read(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeclaredManagerSupplementError(f"cannot read {label}: {path}") from exc
    if not isinstance(document, dict):
        raise DeclaredManagerSupplementError(f"{label} must be a JSON object")
    return document, hashlib.sha256(raw).hexdigest()


def _selector(value: Mapping[str, Any]) -> tuple[str, str, str]:
    source = value.get("source_selector", value)
    if not isinstance(source, Mapping):
        raise DeclaredManagerSupplementError("row has no source selector")
    key = tuple(str(source.get(field) or "").strip() for field in ("country_catalog", "competition_catalog", "club_name"))
    if not all(key):
        raise DeclaredManagerSupplementError("row has an incomplete source selector")
    return key  # type: ignore[return-value]


def _selector_object(selector: tuple[str, str, str]) -> dict[str, str]:
    return dict(zip(("country_catalog", "competition_catalog", "club_name"), selector))


def _scope(
    supplement: Mapping[str, Any], *, source_capture_sha256: str, allocation_sha256: str,
) -> tuple[set[tuple[str, str, str]], dict[tuple[str, str, str], int]]:
    if supplement.get("schema_version") != SCHEMA:
        raise DeclaredManagerSupplementError("gap scope has an unsupported manager supplement schema")
    sources = supplement.get("sources")
    gaps = supplement.get("gaps")
    if not isinstance(sources, Mapping) or not isinstance(gaps, list):
        raise DeclaredManagerSupplementError("gap scope has no sources or gap list")
    if sources.get("full_source_capture_sha256") != source_capture_sha256:
        raise DeclaredManagerSupplementError("gap scope targets a different source capture")
    if sources.get("carrier_allocation_sha256") != allocation_sha256:
        raise DeclaredManagerSupplementError("gap scope targets a different carrier allocation")
    selectors: set[tuple[str, str, str]] = set()
    carrier_ids: dict[tuple[str, str, str], int] = {}
    for row in gaps:
        if not isinstance(row, Mapping):
            raise DeclaredManagerSupplementError("gap scope has a malformed row")
        key = _selector(row)
        carrier_id = row.get("carrier_id")
        if key in selectors or not isinstance(carrier_id, int) or carrier_id <= 0:
            raise DeclaredManagerSupplementError("gap scope has duplicate selectors or an invalid carrier")
        selectors.add(key)
        carrier_ids[key] = carrier_id
    return selectors, carrier_ids


def _report_snapshots(lineups: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    source = lineups.get("source")
    if not isinstance(source, Mapping) or source.get("name") != "Transfermarkt published schedules and match reports":
        raise DeclaredManagerSupplementError("opening lineups have an unsupported source declaration")
    files = source.get("cache_files")
    if not isinstance(files, list):
        raise DeclaredManagerSupplementError("opening lineups have no cache file receipt")
    result: dict[str, tuple[str, str]] = {}
    for item in files:
        if not isinstance(item, Mapping):
            raise DeclaredManagerSupplementError("opening lineups have a malformed cache receipt")
        key, digest, url = item.get("cache_path"), item.get("sha256"), item.get("url")
        if not isinstance(key, str) or not isinstance(digest, str) or not isinstance(url, str):
            raise DeclaredManagerSupplementError("opening lineups have an incomplete cache receipt")
        if key in result:
            raise DeclaredManagerSupplementError("opening lineups duplicate a cache receipt path")
        result[key] = (digest, url)
    return result


def extract(
    *, lineups: Mapping[str, Any], lineups_sha256: str,
    gap_scope: Mapping[str, Any], gap_scope_sha256: str,
) -> dict[str, Any]:
    if lineups.get("schema_version") != LINEUP_SCHEMA:
        raise DeclaredManagerSupplementError("opening lineups have an unsupported schema")
    year = lineups.get("season_start_year")
    source = lineups.get("source")
    if not isinstance(year, int) or not isinstance(source, Mapping):
        raise DeclaredManagerSupplementError("opening lineups have no season or source")
    source_sha = source.get("source_capture_sha256")
    allocation_sha = source.get("carrier_allocation_sha256")
    if not isinstance(source_sha, str) or not isinstance(allocation_sha, str):
        raise DeclaredManagerSupplementError("opening lineups are not bound to source capture and carrier allocation")
    selected, carrier_ids = _scope(gap_scope, source_capture_sha256=source_sha, allocation_sha256=allocation_sha)
    snapshots = _report_snapshots(lineups)
    lineup_by_selector: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for row in lineups.get("clubs") or []:
        if not isinstance(row, Mapping):
            raise DeclaredManagerSupplementError("opening lineups have a malformed club row")
        key = _selector(row)
        if key in lineup_by_selector:
            raise DeclaredManagerSupplementError("opening lineups duplicate a club selector")
        lineup_by_selector[key] = row

    managers: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for key in sorted(selected):
        row = lineup_by_selector.get(key)
        if row is None:
            gaps.append({"source_selector": _selector_object(key), "carrier_id": carrier_ids[key], "reason": "no allocated opening-lineup report for this unresolved manager selector"})
            continue
        manager_name = str(row.get("declared_manager") or "").strip()
        fixture_date = str(row.get("first_league_fixture_date") or "").strip()
        report_url = str(row.get("lineup_source_url") or "").strip()
        match_id = str(row.get("source_match_id") or "").strip()
        blockers = row.get("source_blockers")
        if not manager_name or not fixture_date or not report_url or not match_id or blockers:
            gaps.append({"source_selector": _selector_object(key), "carrier_id": carrier_ids[key], "reason": "allocated opening-lineup report has no unblocked declared manager"})
            continue
        receipt = snapshots.get(f"report/{match_id}.html")
        if receipt is None or receipt[1] != report_url:
            gaps.append({"source_selector": _selector_object(key), "carrier_id": carrier_ids[key], "reason": "allocated opening-lineup report has no matching hash-bound source snapshot"})
            continue
        managers.append({
            "source_selector": _selector_object(key),
            "opening_fixture_date": fixture_date,
            "manager_name": manager_name,
            "source_name": "Transfermarkt published first-league match report",
            "source_url": report_url,
            "source_snapshot_sha256": receipt[0],
            "reason": f"published first-league match report declares the manager for fixed carrier {carrier_ids[key]}",
        })
    return {
        "schema_version": SCHEMA,
        "season_start_year": year,
        "sources": {
            "full_source_capture_sha256": source_sha,
            "carrier_allocation_sha256": allocation_sha,
            "allocated_opening_lineups_sha256": lineups_sha256,
            "gap_scope_supplement_sha256": gap_scope_sha256,
            "gap_scope_policy": "only-unresolved-selectors-from-earlier-hash-bound-raw-manager-supplement-v1",
        },
        "summary": {"supplemented_manager_count": len(managers), "unresolved_manager_count": len(gaps)},
        "managers": managers,
        "gaps": gaps,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allocated-opening-lineups", required=True, type=Path)
    parser.add_argument("--gap-scope-supplement", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise DeclaredManagerSupplementError(f"refusing to overwrite manager supplement: {args.output}")
        lineups, lineups_sha = _read(args.allocated_opening_lineups, "allocated opening lineups")
        scope, scope_sha = _read(args.gap_scope_supplement, "gap scope supplement")
        result = extract(lineups=lineups, lineups_sha256=lineups_sha, gap_scope=scope, gap_scope_sha256=scope_sha)
    except (OSError, DeclaredManagerSupplementError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 1 if args.strict and result["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
