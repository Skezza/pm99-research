#!/usr/bin/env python3
"""Capture exact English club kit evidence and emit the mode-0 kit layer."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_kit_catalogue_v1 as catalogue_v1  # noqa: E402
from scripts import season_kit_source_capture_v1 as capture_v1  # noqa: E402


SCHEMA = "pm99-season-kit-layer-v1"
ENGLISH_COMPETITIONS = {
    "faprem", "engprem", "prem", "premier",
    "flcham", "champ", "championship",
    "flone", "d1", "lge1", "league1",
    "fltwo", "d2", "lge2", "league2", "d3",
}


class EnglishKitLayerError(ValueError):
    """English source intake and kit catalogue cannot be joined safely."""


def canonical_json_bytes(value: Any) -> bytes:
    return catalogue_v1.canonical_json_bytes(value)


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char.casefold() for char in text if char.isalnum() and not unicodedata.combining(char))


def english_clubs(source_intake: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    if source_intake.get("schema_version") != "pm99-season-source-intake-v1":
        raise EnglishKitLayerError("source intake must use pm99-season-source-intake-v1")
    season = source_intake.get("season")
    label = str((season or {}).get("label") or "")
    if not re.fullmatch(r"(?:19|20)\d{2}/\d{2}", label):
        raise EnglishKitLayerError("source intake season must be YYYY/YY")
    clubs = []
    for row in source_intake.get("source_clubs") or []:
        selector = row.get("selector") if isinstance(row, Mapping) else None
        if not isinstance(selector, Mapping) or selector.get("country_catalog") != "eng" or selector.get("competition_catalog") not in ENGLISH_COMPETITIONS:
            continue
        name = str(selector.get("club_name") or "").strip()
        if not name:
            raise EnglishKitLayerError("English source club has no name")
        clubs.append(name)
    clubs.sort(key=lambda name: (_normalise(name), name))
    if len({_normalise(name) for name in clubs}) != len(clubs):
        raise EnglishKitLayerError("English source club identities are not unique")
    start = int(label[:4])
    return {"start_year": start, "end_year": start + 1, "label": label}, clubs


def capture_allocation(source_intake: Mapping[str, Any]) -> dict[str, Any]:
    season, clubs = english_clubs(source_intake)
    # Synthetic IDs are local catalogue join keys only; they never claim to be
    # mode-0 EQ carriers. The fixed-carrier authoring tool performs that join.
    return {"schema_version": "pm99-english-kit-capture-allocation-v1", "season": {"catalog": f"{season['start_year']}-{season['end_year']}", "label": season["label"]}, "assignments": [{"carrier_id": index, "club_name": name} for index, name in enumerate(clubs, 1)]}


def build_layer(source_intake: Mapping[str, Any], catalogue: Mapping[str, Any], stoke_matrix: Mapping[str, Any] | None = None) -> dict[str, Any]:
    season, clubs = english_clubs(source_intake)
    if catalogue.get("schema_version") != catalogue_v1.SCHEMA or catalogue.get("season") != season:
        raise EnglishKitLayerError("kit catalogue schema or season does not match source intake")
    by_name = {}
    for row in catalogue.get("rows") or []:
        key = _normalise(row.get("club_name"))
        if not key or key in by_name:
            raise EnglishKitLayerError("kit catalogue club identities are missing or duplicated")
        by_name[key] = row
    stoke_evidence = None
    if stoke_matrix is not None:
        if stoke_matrix.get("schema_version") != "pm99-stoke-home-kit-evidence-matrix-v1":
            raise EnglishKitLayerError("Stoke matrix schema is unsupported")
        matches = [row for row in stoke_matrix.get("rows") or [] if row.get("season") == season["label"] and row.get("club") == "Stoke City" and row.get("status") == "source-ready"]
        if len(matches) != 1:
            raise EnglishKitLayerError(f"Stoke matrix must contain one exact source-ready row for {season['label']}")
        stoke_evidence = matches[0]
    rows = []
    for club in clubs:
        if _normalise(club) == _normalise("Stoke City") and stoke_evidence is not None:
            source = stoke_evidence["source"]
            rows.append({"club": club, "policy": "historical-target-season", "status": "source-ready", "source_url": source["page_url"], "source_cache_sha256": source["page_sha256"], "source_evidence_url": source.get("evidence_url"), "source_evidence_sha256": source.get("evidence_sha256"), "attribution": source.get("attribution"), "facts": stoke_evidence.get("facts"), "home": stoke_evidence["render_contract"]})
            continue
        evidence = by_name.get(_normalise(club))
        if evidence is None:
            rows.append({"club": club, "policy": "blocked-no-target-season-source", "status": "catalogue-row-missing", "source_url": None})
            continue
        if evidence.get("status") == "source-ready":
            source = evidence.get("source") or {}
            rows.append({"club": club, "policy": "historical-target-season", "status": "source-ready", "source_url": source.get("page_url"), "source_revision_id": source.get("revision_id"), "source_revision_timestamp": source.get("revision_timestamp"), "source_cache_sha256": source.get("cache_sha256"), "attribution": source.get("attribution"), "home": evidence.get("render_contract")})
        else:
            rows.append({"club": club, "policy": "blocked-no-target-season-source", "status": evidence.get("status"), "reason": evidence.get("reason"), "source_url": (evidence.get("source") or {}).get("page_url"), "attribution": (evidence.get("source") or {}).get("attribution")})
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    return {"schema_version": SCHEMA, "season": season, "policy": {"continuing_club": "exact-target-season-source-required", "native_fallback": "forbidden", "identity": "source-intake-English-club-normalised-exact-join"}, "coverage": {"english_club_count": len(rows), "status_counts": dict(sorted(status_counts.items()))}, "clubs": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-intake", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--capture-output-dir", type=Path, required=True)
    parser.add_argument("--output-layer", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--stoke-matrix", type=Path)
    args = parser.parse_args()
    intake = json.loads(args.source_intake.read_text(encoding="utf-8"))
    allocation = capture_allocation(intake)
    capture_v1.materialise(allocation, output_dir=args.capture_output_dir, cache_dir=args.cache_dir, allow_network=args.allow_network)
    catalogue = json.loads((args.capture_output_dir / "kit-catalogue-v1.json").read_text(encoding="utf-8"))
    stoke_matrix = json.loads(args.stoke_matrix.read_text(encoding="utf-8")) if args.stoke_matrix else None
    layer = build_layer(intake, catalogue, stoke_matrix)
    args.output_layer.parent.mkdir(parents=True, exist_ok=True)
    args.output_layer.write_bytes(canonical_json_bytes(layer))
    print(json.dumps(layer["coverage"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
