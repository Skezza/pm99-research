#!/usr/bin/env python3
"""Focused contract test for generated number-label amendments."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_name_provenance_v1 as provenance
from scripts import stage_number_label_name_amendments_v1 as subject
from tools import season_manifest_amendments as amendments


def main() -> int:
    package = {
        "season": "2021-22",
        "package_id": "world-2021-22",
        "players": [{"id": "p-1", "name": "#8 Sam Morsy", "facts": {}}],
    }
    sidecar = {
        "schema_version": provenance.SCHEMA,
        "season": "2021-22",
        "package": {"sha256": provenance._json_sha256(package)},
        "players": [{
            "player_id": "p-1",
            "canonical_name": "#8 Sam Morsy",
            "status": "source-row-linked",
            "captured_source": {"source_path": "eng/example.txt", "source_row_index": 7},
            "component_candidate": {
                "source_number_label_stripped": True,
                "proposed_display_name": "Sam Morsy",
            },
        }],
    }
    document, stats = subject.stage(
        package=package,
        package_sha256="a" * 64,
        manifest_id="runtime-recipe/r3/season-package.source-writable.json",
        sidecar=sidecar,
        document=amendments.empty_document("2021-22"),
    )
    assert stats == {
        "candidate_count": 1,
        "staged_count": 1,
        "refreshed_evidence_count": 0,
        "already_staged_count": 0,
    }
    assert document["changes"][0]["json_pointer"] == "/players/0/name"
    assert document["changes"][0]["expected"] == "#8 Sam Morsy"
    assert document["changes"][0]["set"] == "Sam Morsy"
    same, repeat = subject.stage(
        package=package,
        package_sha256="a" * 64,
        manifest_id="runtime-recipe/r3/season-package.source-writable.json",
        sidecar=sidecar,
        document=document,
    )
    assert repeat == {
        "candidate_count": 1,
        "staged_count": 0,
        "refreshed_evidence_count": 0,
        "already_staged_count": 1,
    }
    assert same == document
    print("number-label amendment staging contract OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
