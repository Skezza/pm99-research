#!/usr/bin/env python3
"""Create a season-neutral, hash-bound opening-manager ledger.

The preferred evidence is the manager published in each club's first league
match report by ``capture_transfermarkt_opening_lineups_v1.py``. Missing
reports and missing manager labels stay explicit. A canonical supplement may
add a manager only with its own dated source URL and snapshot hash. There is
deliberately no native/current-manager fallback.

This stage is offline and resumable: source pages are cached by the upstream
capture, supplements can be extended independently, and identical inputs
produce byte-identical output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Mapping


LINEUP_SCHEMA = "pm99-transfermarkt-opening-lineup-source-v1"
LINEUP_SCHEMAS = {LINEUP_SCHEMA, "pm99-composed-opening-lineup-source-v1"}
SUPPLEMENT_SCHEMA = "pm99-opening-manager-supplement-v1"
OUTPUT_SCHEMA = "pm99-opening-manager-ledger-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ManagerLedgerError(ValueError):
    """An input is malformed or cannot be joined without ambiguity."""


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load(path: Path, *, label: str, canonical: bool = False) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManagerLedgerError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ManagerLedgerError(f"{label} must be a JSON object")
    if canonical and raw != _canonical_json_bytes(value):
        raise ManagerLedgerError(f"{label} must be canonical JSON")
    return value, hashlib.sha256(raw).hexdigest()


def _selector(value: Mapping[str, Any]) -> tuple[str, str, str]:
    result = tuple(str(value.get(field) or "").strip() for field in ("country_catalog", "competition_catalog", "club_name"))
    if not all(result):
        raise ManagerLedgerError("club selector lacks country_catalog, competition_catalog or club_name")
    return result  # type: ignore[return-value]


def _selector_object(value: tuple[str, str, str]) -> dict[str, str]:
    return dict(zip(("country_catalog", "competition_catalog", "club_name"), value))


def _source_clubs(source_capture: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    rows = source_capture.get("clubs")
    if not isinstance(rows, list) or not rows:
        raise ManagerLedgerError("squad source capture must have a non-empty clubs list")
    result: set[tuple[str, str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ManagerLedgerError("squad source capture has a malformed club")
        selector = _selector(row)
        if selector in result:
            raise ManagerLedgerError(f"squad source capture duplicates club {selector}")
        result.add(selector)
    return sorted(result)


def _lineup_rows(lineup: Mapping[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    if lineup.get("schema_version") not in LINEUP_SCHEMAS:
        raise ManagerLedgerError(f"lineup receipt must have one of {sorted(LINEUP_SCHEMAS)}")
    rows = lineup.get("clubs")
    if not isinstance(rows, list):
        raise ManagerLedgerError("lineup receipt must have a clubs list")
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("source_selector"), dict):
            raise ManagerLedgerError("lineup receipt has a malformed club")
        selector = _selector(row["source_selector"])
        if selector in result:
            raise ManagerLedgerError(f"lineup receipt duplicates club {selector}")
        result[selector] = row
    return result


def _report_snapshots(lineup: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    source = lineup.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("cache_files"), list):
        raise ManagerLedgerError("lineup receipt has no source cache-file ledger")
    result: dict[str, dict[str, str]] = {}
    for row in source["cache_files"]:
        if not isinstance(row, dict):
            raise ManagerLedgerError("lineup cache ledger contains a malformed row")
        url = str(row.get("url") or "").strip()
        sha256 = str(row.get("sha256") or "").strip()
        cache_path = str(row.get("cache_path") or "").strip()
        if not url or not cache_path or not SHA256_RE.fullmatch(sha256):
            raise ManagerLedgerError("lineup cache ledger row lacks URL, cache path or SHA-256")
        value = {"cache_path": cache_path, "sha256": sha256}
        if url in result and result[url] != value:
            raise ManagerLedgerError(f"lineup cache ledger conflicts for {url}")
        result[url] = value
    return result


def _supplements(document: Mapping[str, Any] | None, *, season_start_year: int) -> dict[tuple[str, str, str], dict[str, Any]]:
    if document is None:
        return {}
    if document.get("schema_version") != SUPPLEMENT_SCHEMA:
        raise ManagerLedgerError(f"manager supplement must have schema {SUPPLEMENT_SCHEMA}")
    if document.get("season_start_year") != season_start_year:
        raise ManagerLedgerError("manager supplement season does not match lineup receipt")
    rows = document.get("managers")
    if not isinstance(rows, list):
        raise ManagerLedgerError("manager supplement must have a managers list")
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    exact_fields = {
        "source_selector", "opening_fixture_date", "manager_name", "source_name",
        "source_url", "source_snapshot_sha256", "reason",
    }
    for row in rows:
        if not isinstance(row, dict) or set(row) != exact_fields or not isinstance(row.get("source_selector"), dict):
            raise ManagerLedgerError("manager supplement row has unexpected or missing fields")
        selector = _selector(row["source_selector"])
        strings = {field: str(row.get(field) or "").strip() for field in exact_fields - {"source_selector"}}
        if any(not value for value in strings.values()):
            raise ManagerLedgerError(f"manager supplement has a blank fact for {selector}")
        try:
            date.fromisoformat(strings["opening_fixture_date"])
        except ValueError:
            raise ManagerLedgerError(f"manager supplement has an invalid date for {selector}")
        if not re.fullmatch(r"https?://\S+", strings["source_url"]):
            raise ManagerLedgerError(f"manager supplement has an invalid source URL for {selector}")
        if not SHA256_RE.fullmatch(strings["source_snapshot_sha256"]):
            raise ManagerLedgerError(f"manager supplement has an invalid source snapshot hash for {selector}")
        if selector in result:
            raise ManagerLedgerError(f"manager supplement duplicates club {selector}")
        result[selector] = {**row, **strings}
    return result


def materialise(
    *, source_capture: Mapping[str, Any], source_capture_sha256: str,
    lineup: Mapping[str, Any], lineup_sha256: str,
    supplement: Mapping[str, Any] | None = None, supplement_sha256: str | None = None,
) -> dict[str, Any]:
    season_start_year = lineup.get("season_start_year")
    if not isinstance(season_start_year, int):
        raise ManagerLedgerError("lineup receipt has no integer season_start_year")
    selectors = _source_clubs(source_capture)
    selector_set = set(selectors)
    lineup_by_club = _lineup_rows(lineup)
    unknown_lineups = sorted(set(lineup_by_club) - selector_set)
    if unknown_lineups:
        raise ManagerLedgerError(f"lineup receipt contains club absent from squad source: {unknown_lineups[0]}")
    snapshots = _report_snapshots(lineup)
    supplement_by_club = _supplements(supplement, season_start_year=season_start_year)
    unknown_supplements = sorted(set(supplement_by_club) - selector_set)
    if unknown_supplements:
        raise ManagerLedgerError(f"manager supplement contains club absent from squad source: {unknown_supplements[0]}")

    managers: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for selector in selectors:
        row = lineup_by_club.get(selector)
        supplemental = supplement_by_club.get(selector)
        manager = str((row or {}).get("declared_manager") or "").strip()
        if manager and supplemental is not None:
            raise ManagerLedgerError(f"manager supplement duplicates published match-report evidence for {selector}")
        if manager:
            report_url = str(row.get("lineup_source_url") or "").strip()
            snapshot = snapshots.get(report_url)
            if snapshot is None:
                raise ManagerLedgerError(f"manager report URL has no cache receipt for {selector}")
            managers.append({
                "source_selector": _selector_object(selector),
                "opening_fixture_date": str(row.get("first_league_fixture_date") or ""),
                "manager_name": manager,
                "resolution_method": "first-league-match-report-declared-manager",
                "evidence": {
                    "source_name": "Transfermarkt published match report",
                    "source_url": report_url,
                    "source_match_id": str(row.get("source_match_id") or ""),
                    "source_snapshot_cache_path": snapshot["cache_path"],
                    "source_snapshot_sha256": snapshot["sha256"],
                },
            })
        elif supplemental is not None:
            managers.append({
                "source_selector": _selector_object(selector),
                "opening_fixture_date": supplemental["opening_fixture_date"],
                "manager_name": supplemental["manager_name"],
                "resolution_method": "dated-source-supplement",
                "evidence": {
                    "source_name": supplemental["source_name"],
                    "source_url": supplemental["source_url"],
                    "source_snapshot_sha256": supplemental["source_snapshot_sha256"],
                    "reason": supplemental["reason"],
                },
            })
        else:
            gaps.append({
                "source_selector": _selector_object(selector),
                "reason": "first-league-match-report-has-no-published-manager" if row is not None else "no-first-league-match-report-capture",
                "required_resolution": "add a dated, hash-bound manager supplement; native manager fallback is forbidden",
            })
    methods: dict[str, int] = {}
    for row in managers:
        method = row["resolution_method"]
        methods[method] = methods.get(method, 0) + 1
    return {
        "schema_version": OUTPUT_SCHEMA,
        "season_start_year": season_start_year,
        "policy": "correct manager at each club's first league fixture; no native/current-manager fallback",
        "sources": {
            "squad_source_capture_sha256": source_capture_sha256,
            "opening_lineup_receipt_sha256": lineup_sha256,
            "manager_supplement_sha256": supplement_sha256,
        },
        "summary": {
            "source_club_count": len(selectors),
            "resolved_manager_count": len(managers),
            "unresolved_manager_count": len(gaps),
            "resolution_method_counts": dict(sorted(methods.items())),
        },
        "managers": managers,
        "gaps": gaps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-capture", required=True, type=Path)
    parser.add_argument("--opening-lineups", required=True, type=Path)
    parser.add_argument("--supplement", type=Path, help="canonical dated source supplements for manager gaps")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--strict", action="store_true", help="return non-zero while any manager remains unresolved")
    args = parser.parse_args(argv)
    try:
        source, source_sha256 = _load(args.source_capture, label="squad source capture")
        lineup, lineup_sha256 = _load(args.opening_lineups, label="opening lineup receipt")
        supplement, supplement_sha256 = (None, None)
        if args.supplement is not None:
            supplement, supplement_sha256 = _load(args.supplement, label="manager supplement", canonical=True)
        result = materialise(
            source_capture=source, source_capture_sha256=source_sha256,
            lineup=lineup, lineup_sha256=lineup_sha256,
            supplement=supplement, supplement_sha256=supplement_sha256,
        )
    except ManagerLedgerError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_json_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 1 if args.strict and result["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
