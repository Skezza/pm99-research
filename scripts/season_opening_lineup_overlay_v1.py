#!/usr/bin/env python3
"""Attach one raw historic-ID opening-XI receipt as a frozen season overlay."""

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

from scripts import reconcile_transfermarkt_opening_lineups_v1 as reconcile_v1  # noqa: E402
from scripts import season_manager_overlay_v1 as baseline_v1  # noqa: E402


SCHEMA = "pm99-season-opening-lineup-overlay-v1"


class OpeningOverlayError(ValueError):
    pass


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _read(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpeningOverlayError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise OpeningOverlayError(f"{label} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _selector(row: Mapping[str, Any]) -> tuple[str, str, str]:
    value = row.get("source_selector")
    if not isinstance(value, Mapping):
        raise OpeningOverlayError("reconciliation row has no selector")
    key = tuple(str(value.get(field) or "").strip() for field in ("country_catalog", "competition_catalog", "club_name"))
    if not all(key):
        raise OpeningOverlayError("reconciliation row has an incomplete selector")
    return key  # type: ignore[return-value]


def build_overlay(*, baseline: Mapping[str, Any], baseline_sha256: str, season: str,
                  source: Mapping[str, Any], source_sha256: str,
                  base_reconciliation: Mapping[str, Any], base_reconciliation_sha256: str,
                  raw_lineups: Mapping[str, Any], raw_lineups_sha256: str) -> tuple[dict[str, Any], dict[str, Any]]:
    entry = baseline_v1._baseline_entry(baseline=baseline, season=season)
    if (base_reconciliation.get("sources") or {}).get("source_capture_sha256") != source_sha256:
        raise OpeningOverlayError("base reconciliation is not bound to the current source capture")
    try:
        supplementary = reconcile_v1.reconcile(
            source_capture=source, lineup_capture=raw_lineups,
            source_capture_sha256=source_sha256, lineup_capture_sha256=raw_lineups_sha256,
        )
    except reconcile_v1.ReconciliationError as exc:
        raise OpeningOverlayError(str(exc)) from exc
    base_rows = {_selector(row): dict(row) for row in base_reconciliation.get("clubs") or [] if isinstance(row, Mapping)}
    extra_rows = {_selector(row): dict(row) for row in supplementary.get("clubs") or [] if isinstance(row, Mapping)}
    overlap = sorted(set(base_rows) & set(extra_rows))
    if overlap:
        raise OpeningOverlayError(f"supplement overlaps existing reconciliation at {overlap[0]}")
    rows = {**base_rows, **extra_rows}
    reconciled = sum(bool(row.get("starting_xi_reconciled")) for row in rows.values())
    source_clubs = source.get("clubs")
    if not isinstance(source_clubs, list):
        raise OpeningOverlayError("source capture has no club rows")
    result = {
        "schema_version": reconcile_v1.SCHEMA,
        "sources": {
            "source_capture_sha256": source_sha256,
            "base_reconciliation_sha256": base_reconciliation_sha256,
            "historic_id_lineup_supplement_sha256": raw_lineups_sha256,
            "historic_id_supplement_reconciliation_sha256": hashlib.sha256(_bytes(supplementary)).hexdigest(),
        },
        "summary": {
            "source_club_count": len(source_clubs),
            "fixture_captured_club_count": len(rows),
            "reconciled_xi_club_count": reconciled,
            "unreconciled_or_uncaptured_club_count": len(source_clubs) - reconciled,
            "historic_id_supplement_captured_club_count": len(extra_rows),
            "historic_id_supplement_reconciled_xi_club_count": sum(bool(row.get("starting_xi_reconciled")) for row in extra_rows.values()),
        },
        "clubs": [rows[key] for key in sorted(rows)],
        "failures": [*(base_reconciliation.get("failures") or []), *(supplementary.get("failures") or [])],
    }
    audit = {
        "schema_version": SCHEMA, "season": season, "state": "opening-lineup-overlay-provisional-not-release",
        "base": {"baseline_index_sha256": baseline_sha256, "base_draft_sha256": entry["base_draft"]["sha256"]},
        "inputs": {"source_capture_sha256": source_sha256, "base_reconciliation_sha256": base_reconciliation_sha256,
                   "historic_id_lineup_supplement_sha256": raw_lineups_sha256},
        "outputs": {"opening_reconciliation_sha256": hashlib.sha256(_bytes(result)).hexdigest()},
        "coverage": result["summary"],
        "not_performed": ["manager integration", "kit integration", "rating integration", "strict package promotion", "database compilation", "PM99 runtime validation", "screenshot capture"],
    }
    return result, audit


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-index", required=True, type=Path)
    parser.add_argument("--season", required=True)
    parser.add_argument("--source-capture", required=True, type=Path)
    parser.add_argument("--base-reconciliation", required=True, type=Path)
    parser.add_argument("--historic-id-lineups", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output_root.exists():
            raise OpeningOverlayError(f"refusing to overwrite opening-lineup overlay root: {args.output_root}")
        baseline, baseline_sha = _read(args.baseline_index, "baseline index")
        source, source_sha = _read(args.source_capture, "source capture")
        base, base_sha = _read(args.base_reconciliation, "base reconciliation")
        raw, raw_sha = _read(args.historic_id_lineups, "historic-ID lineups")
        reconciliation, audit = build_overlay(baseline=baseline, baseline_sha256=baseline_sha, season=args.season,
            source=source, source_sha256=source_sha, base_reconciliation=base, base_reconciliation_sha256=base_sha,
            raw_lineups=raw, raw_lineups_sha256=raw_sha)
    except (OSError, OpeningOverlayError) as exc:
        parser.error(str(exc))
    args.output_root.mkdir(parents=True, exist_ok=False)
    (args.output_root / "opening-lineup-reconciliation.json").write_bytes(_bytes(reconciliation))
    (args.output_root / "opening-lineup-overlay-audit.json").write_bytes(_bytes(audit))
    print(json.dumps(audit["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
