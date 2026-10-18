#!/usr/bin/env python3
"""Focused contract tests for the non-mutating name-provenance sidecar."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_name_provenance_v1 as subject


def _capture_player(name: str, *, number: int, birth_date: str) -> dict[str, object]:
    return {
        "shirt_number": number,
        "name": name,
        "nationality": "ENG",
        "position": "M",
        "height_cm": 180,
        "weight_kg": 75,
        "birth_date": birth_date,
        "unresolved_fields": [],
    }


def _package_player(player_id: str, name: str | None, *, number: int = 8, birth_date: str = "1989-09-10") -> dict[str, object]:
    player: dict[str, object] = {
        "id": player_id,
        "name": name or "Native Carrier",
        "facts": {
            "birth_date": birth_date,
            "primary_position": "M",
            "shirt_number": number,
            "height_cm": 180,
            "weight_kg": 75,
        },
    }
    if name is not None:
        player["source_name"] = name
    return player


def main() -> int:
    capture = {
        "schema_version": subject.CAPTURE_SCHEMA,
        "season": {"label": "2000/01"},
        "clubs": [{
            "club_name": "Example Town",
            "source_path": "eng/2000-2001/d1/example.txt",
            "source_sha256": "a" * 64,
            "players": [
                _capture_player("#8 Sam Morsy", number=8, birth_date="1989-09-10"),
                _capture_player("Baranov, Nikita", number=9, birth_date="1988-01-01"),
            ],
        }],
    }
    package = {
        "season": "2000-01",
        "package_id": "world-2000-01",
        "players": [
            _package_player("p-prefix", "#8 Sam Morsy"),
            _package_player("p-comma", "Baranov, Nikita", number=9, birth_date="1988-01-01"),
            _package_player("p-native", None),
            _package_player("p-missing", "Missing Player"),
        ],
    }
    result = subject.build_provenance(package=package, sources={"test-capture": capture})
    rows = {row["player_id"]: row for row in result["players"]}
    assert rows["p-prefix"]["status"] == "source-row-linked"
    assert rows["p-prefix"]["source_match"] == "exact-source-name"
    assert rows["p-prefix"]["captured_source"]["raw_name"] == "#8 Sam Morsy"
    assert rows["p-prefix"]["captured_source"]["source_artifact_id"] == "test-capture"
    assert rows["p-prefix"]["component_candidate"] == {
        "proposed_display_name": "Sam Morsy",
        "source_number_label_stripped": True,
        "status": "ready-given-first",
        "method": "captured-first-token-given-remainder-surname",
        "given_name": "Sam",
        "surname": "Morsy",
        "requires_authoritative_identity_check": False,
        "reasons": ["stripped a rendered squad-number label from captured name text"],
    }
    assert rows["p-comma"]["component_candidate"]["given_name"] == "Nikita"
    assert rows["p-comma"]["component_candidate"]["surname"] == "Baranov"
    assert rows["p-comma"]["component_candidate"]["requires_authoritative_identity_check"] is True
    assert rows["p-native"]["status"] == "native-retained-no-historical-source"
    assert rows["p-missing"]["status"] == "needs-source-rescrape"
    assert result["summary"] == {
        "player_count": 4,
        "status_counts": {
            "native-retained-no-historical-source": 1,
            "needs-source-rescrape": 1,
            "source-row-linked": 2,
        },
        "component_status_counts": {
            "ready-comma-order": 1,
            "ready-given-first": 1,
        },
        "authoritative_identity_queue_count": 1,
        "source_number_label_repair_count": 1,
        "historical_source_rescrape_queue_count": 1,
        "native_retained_no_historical_source_count": 1,
    }
    print("season name provenance contract OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
