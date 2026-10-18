#!/usr/bin/env python3
"""Merge approved historical photo QA rows into a FIFA portrait materialisation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.season_pipeline_v2 import write_canonical_json
from scripts.season_pipeline_v2 import canonical_json_bytes


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rebind_unchanged_club_qa(original_path, revised_path, qa_path, discovery_path, output_path):
    """Reuse a completed face review ONLY if every club input row is unchanged."""
    original, revised, qa, discovery = [json.loads(p.read_text()) for p in (
        original_path, revised_path, qa_path, discovery_path)]
    if qa['input_hashes']['fifa_manifest'] != sha(original_path) or qa['input_hashes']['discovery_receipt'] != sha(discovery_path):
        raise ValueError('original QA inputs are stale')
    club = qa['club']
    before = sorted([p for p in original['players'] if p.get('target_club') == club], key=lambda p: p['carrier_id'])
    after = sorted([p for p in revised['players'] if p.get('target_club') == club], key=lambda p: p['carrier_id'])
    if not before or canonical_json_bytes(before) != canonical_json_bytes(after) or original['season'] != revised['season']:
        raise ValueError('club inputs changed; a fresh face review is required')
    for row in qa['players']:
        selected = row.get('selected')
        if not selected:
            continue
        matches = [c for p in discovery['players'] if p['name'] == row['name'] for c in p.get('candidates', [])
                   if c['title'] == selected['title'] and c['description_url'] == selected['source_page']]
        if len(matches) != 1:
            raise ValueError('selected photograph has no unique original discovery record')
        for key in ('image_url', 'original_url', 'licence_url', 'artist', 'date_basis'):
            selected[key] = matches[0].get(key)
        selected['date_basis'] = selected['date_basis'] or 'legacy-Commons-date-field-not-recorded'
    qa['input_hashes']['fifa_manifest'] = sha(revised_path)
    qa['unchanged_club_rebinding'] = {'original_qa_sha256': sha(qa_path),
                                    'original_fifa_sha256': sha(original_path),
                                    'club_rows_sha256': hashlib.sha256(canonical_json_bytes(before)).hexdigest()}
    write_canonical_json(output_path, qa)


def compose(fifa_path: Path, qa_path: Path) -> dict:
    fifa = json.loads(fifa_path.read_text())
    qa = json.loads(qa_path.read_text())
    if fifa["season"] != qa["season"] or qa["schema_version"] != "pm99-historical-photo-qa-v1":
        raise ValueError("QA receipt and FIFA materialisation disagree")
    if qa.get("input_hashes", {}).get("fifa_manifest") != sha(fifa_path):
        raise ValueError("QA receipt was produced for a different FIFA materialisation")
    qa_carriers = [int(row["carrier_id"]) for row in qa["players"]]
    if len(qa_carriers) != len(set(qa_carriers)):
        raise ValueError("QA contains duplicate player carriers")
    selected = {int(row["carrier_id"]): row for row in qa["players"] if row["status"] == "photo-candidate"}
    original = {int(row["carrier_id"]): row for row in fifa["players"]}
    if len(original) != len(fifa["players"]):
        raise ValueError("FIFA materialisation contains duplicate player carriers")
    expected_club_carriers = {int(row["carrier_id"]) for row in fifa["players"]
                             if row.get("target_club") == qa.get("club")}
    if set(qa_carriers) != expected_club_carriers:
        raise ValueError("QA does not exactly cover the declared club squad")
    if not selected.keys() <= original.keys():
        raise ValueError("QA contains unknown player carriers")
    if not expected_club_carriers or len(selected) != qa["counts"].get("photo-candidate", 0):
        raise ValueError("club QA coverage is incomplete")
    rows = []
    for row in fifa["players"]:
        replacement = selected.get(int(row["carrier_id"]))
        if replacement is None:
            rows.append(row)
            continue
        photo = replacement["selected"]
        bitmap = Path(photo["bitmap"])
        if not bitmap.is_file() or sha(bitmap) != photo["bitmap_sha256"]:
            raise ValueError("historical bitmap changed: " + replacement["name"])
        if row["name"] != replacement["name"]:
            raise ValueError("player name mismatch: " + replacement["name"])
        # Do not leave FIFA previews or identity metadata on a photographic
        # replacement. Keep that provenance in an explicitly named fallback.
        fallback = {key: row[key] for key in ("sofifa_id", "source_name", "source_image_url",
                    "source_sha256", "preview_path", "preview_sha256", "era_grade") if key in row}
        updated = {key: value for key, value in row.items() if key not in (
            "sofifa_id", "source_name", "source_birth_date", "source_club", "source_profile_url",
            "source_edition", "era_distance_seasons", "preview_path", "preview_sha256")}
        preview = Path(photo["preview"])
        rows.append({**updated, "status": "applied", "converted_path": str(bitmap.resolve()),
                     "converted_sha256": photo["bitmap_sha256"],
                     "source_image_url": photo.get("image_url"),
                     "source_profile_url": photo["source_page"], "source_name": replacement["name"],
                     "source_sha256": photo["source_sha256"],
                     "preview_path": str(preview.resolve()), "preview_sha256": sha(preview),
                     "photograph_provenance": {key: photo.get(key) for key in (
                         "source_page", "image_url", "original_url", "photo_date", "date_basis",
                         "licence", "licence_url", "artist")}, "fifa_fallback": fallback,
                     "era_grade": "dated-historical-photograph",
                     "portrait_qa_receipt": str(qa_path.resolve())})
    coverage = dict(fifa["coverage"])
    coverage["applied_count"] = sum(row["status"] == "applied" for row in rows)
    coverage["native_no_photo_count"] = sum(row["status"] == "native-no-photo" for row in rows)
    coverage["status_counts"] = {"applied": coverage["applied_count"],
                                 "native-no-photo": coverage["native_no_photo_count"]}
    coverage["historical_photo_count"] = len(selected)
    coverage["era_grade_counts"] = dict(sorted(Counter(row.get("era_grade", "unresolved")
                                                       for row in rows).items()))
    return {**fifa, "players": rows, "coverage": coverage,
            "historical_photo_overlay": {"qa_receipt": str(qa_path.resolve()), "qa_sha256": sha(qa_path),
                                         "fifa_materialisation_sha256": sha(fifa_path),
                                         "photo_carriers": sorted(selected)}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fifa-materialisation", type=Path, required=True)
    parser.add_argument("--qa-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compose(args.fifa_materialisation, args.qa_receipt)
    write_canonical_json(args.output, result)
    print(json.dumps({"historical_photo_count": result["coverage"]["historical_photo_count"],
                      "applied_count": result["coverage"]["applied_count"]}))


if __name__ == "__main__":
    main()
