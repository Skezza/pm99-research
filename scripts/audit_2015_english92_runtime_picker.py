#!/usr/bin/env python3
"""Verify a compiled English-92 release's *actual* new-game picker surface.

The original PM99 selector has twenty human-manager icon cells for each
English division.  The remaining Football League clubs are still used by the
game, and must be proved through the league-table route.  A complete rewrite
can change which four clubs are omitted from a lower-division picker, so this
audit deliberately consumes the picker capture made from the *built* database;
it does not extrapolate availability from the original 1998 carrier IDs.

This is a release-proof helper, not an OCR engine.  The runner supplies the
OCR labels and this script resolves them only against clubs in the matching
intended division.  Ambiguous or weak matches fail closed.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


PANEL_TO_DIVISION = {
    "division_01": "Premier League",
    "division_02": "Championship",
    "division_03": "League One",
    "division_04": "League Two",
}

# Reviewed runner OCR variants.  Keep these at the capture boundary rather
# than weakening player/club identity matching globally.
OCR_ALIASES = {
    "burniey": "burnley",
    "charitonathletic": "charltonathletic",
    "ipswichtewn": "ipswichtown",
    "nettscounty": "nottscounty",
    "tottenhammotspur": "tottenhamhotspur",
}


def _normalise(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return "".join(character.casefold() for character in text if character.isalnum())


def _candidate_keys(club: str) -> set[str]:
    key = _normalise(club)
    values = {key}
    aliases = {
        "afcwimbledon": "afcwimbledon",
        "brightonhovealbion": "brighton",
        "dagenhamredbridge": "dagred",
        "manchestercity": "mancity",
        "manchesterunited": "manutd",
        "miltonkeynesdons": "mkdons",
        "nottinghamforest": "nottmforest",
        "queensparkrangers": "qpr",
        "sheffieldunited": "sheffutd",
        "sheffieldwednesday": "sheffwed",
        "westbromwichalbion": "westbrom",
        "wolverhamptonwanderers": "wolves",
    }
    if key in aliases:
        values.add(aliases[key])
    return values


def _resolve_label(label: str, candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    raw_key = _normalise(label)
    key = OCR_ALIASES.get(raw_key, raw_key)
    exact = [club for club in candidates if key in _candidate_keys(str(club["club"]))]
    if len(exact) == 1:
        return exact[0], "exact-or-reviewed-ocr-alias"
    if len(exact) > 1:
        return None, "ambiguous-exact"

    ranked = sorted(
        (
            max(SequenceMatcher(a=key, b=value).ratio() for value in _candidate_keys(str(club["club"]))),
            str(club["club"]),
            club,
        )
        for club in candidates
    )
    if not ranked:
        return None, "no-candidates"
    best_ratio, _name, best = ranked[-1]
    runner_up_ratio = ranked[-2][0] if len(ranked) > 1 else 0.0
    if best_ratio < 0.72 or best_ratio - runner_up_ratio < 0.08:
        return None, f"weak-or-ambiguous-fuzzy:{best_ratio:.3f}/{runner_up_ratio:.3f}"
    return best, f"high-confidence-fuzzy:{best_ratio:.3f}"


def audit_runtime_picker(*, season_manifest: dict[str, Any], selector_capture: dict[str, Any]) -> dict[str, Any]:
    teams = list(season_manifest.get("teams") or [])
    if len(teams) != 92:
        raise ValueError(f"Expected a 92-team release manifest, found {len(teams)} teams")
    by_division = {
        division: [team for team in teams if str(team.get("division")) == division]
        for division in PANEL_TO_DIVISION.values()
    }
    expected_sizes = {"Premier League": 20, "Championship": 24, "League One": 24, "League Two": 24}
    if {division: len(rows) for division, rows in by_division.items()} != expected_sizes:
        raise ValueError("Release manifest is not a native 20/24/24/24 English shape")

    capture_by_panel = {
        str(row.get("division_key")): row
        for row in list(selector_capture.get("divisions") or [])
    }
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    for panel, division in PANEL_TO_DIVISION.items():
        capture = capture_by_panel.get(panel)
        observations = list(capture.get("teams") or []) if isinstance(capture, dict) else []
        seen_ids: set[int] = set()
        rows: list[dict[str, Any]] = []
        for observation in observations:
            label = str(observation.get("text") or "").strip()
            resolved, method = _resolve_label(label, by_division[division])
            if resolved is None:
                rows.append({"row_index": observation.get("row_index"), "observed_label": label, "status": method})
                failures.append(f"{division}: unable to resolve picker label {label!r} ({method})")
                continue
            carrier_id = int(resolved["record_id"])
            if carrier_id in seen_ids:
                rows.append({"row_index": observation.get("row_index"), "observed_label": label, "club": resolved["club"], "record_id": carrier_id, "status": "duplicate"})
                failures.append(f"{division}: duplicate picker club {resolved['club']}")
                continue
            seen_ids.add(carrier_id)
            rows.append({
                "row_index": int(observation.get("row_index") or 0),
                "observed_label": label,
                "club": str(resolved["club"]),
                "record_id": carrier_id,
                "status": "resolved",
                "resolution": method,
            })
        if len(observations) != 20:
            failures.append(f"{division}: expected 20 picker observations, found {len(observations)}")
        unavailable = sorted(
            (team for team in by_division[division] if int(team["record_id"]) not in seen_ids),
            key=lambda team: str(team["club"]),
        )
        results.append({
            "panel": panel,
            "division": division,
            "expected_club_count": len(by_division[division]),
            "observed_picker_count": len(observations),
            "resolved_picker_count": len(seen_ids),
            "picker_rows": rows,
            "runtime_non_picker_clubs": [
                {"club": str(team["club"]), "record_id": int(team["record_id"])}
                for team in unavailable
            ],
        })
    return {
        "schema_version": "pm99-english92-runtime-picker-audit-v1",
        "release_profile": season_manifest.get("release_profile"),
        "result": "pass" if not failures else "fail",
        "failures": failures,
        "panels": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season-manifest", required=True, type=Path)
    parser.add_argument("--selector-capture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit_runtime_picker(
        season_manifest=json.loads(args.season_manifest.read_text(encoding="utf-8")),
        selector_capture=json.loads(args.selector_capture.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["result"], "output": str(args.output), "failures": len(result["failures"])}))
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
