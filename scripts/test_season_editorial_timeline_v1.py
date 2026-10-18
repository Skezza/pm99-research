"""Tests for the shared PM99 historical editorial timeline."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_editorial_timeline_v1 as timeline  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_review_v2 as review_v2  # noqa: E402
from test_season_package_v2 import _valid_package  # noqa: E402


def _package() -> dict:
    package = _valid_package()
    package_v2.validate_package(package, strict=True)
    return package


def test_seed_requires_reconciled_identity_ids() -> None:
    package = _package()
    del package["players"][0]["person_id"]
    with pytest.raises(timeline.TimelineError, match="lacks person_id"):
        timeline.seed_timeline_from_package(package, timeline_id="pm99-editorial-2000-2026")


def test_identity_audit_reports_missing_ids_and_does_not_merge_candidates() -> None:
    package = _package()
    player_1 = next(row for row in package["players"] if row["id"] == "player-1")
    player_2 = next(row for row in package["players"] if row["id"] == "player-2")
    player_2["name"] = player_1["name"]
    player_2["facts"] = copy.deepcopy(player_1["facts"])
    del player_1["person_id"]
    audit = timeline.identity_audit_package(package)
    assert audit["records"]["player"]["missing_identity_ids"] == ["player-1"]
    assert audit["ambiguous_player_candidates"] == [{
        "name": "player 1", "birth_date": "1990-01-01", "nationality": "ENG",
        "package_record_ids": ["player-1", "player-2"],
    }]


def test_timeline_compiles_shared_rating_amendment_to_guarded_overlay() -> None:
    package = _package()
    source = timeline.seed_timeline_from_package(package, timeline_id="pm99-editorial-2000-2026")
    source["amendments"] = [{
        "id": "fixture-player-2-speed",
        "seasons": ["2015-16"],
        "target": {"entity": "player", "identity_id": "person-fixture-player-2"},
        "changes": {"ratings.values.speed": 91},
        "reason": "First-game review confirmed the synthetic speed value was too low.",
        "proof": {"grade": "reviewed-editorial", "artifact_id": "receipt-contract"},
        "rating_provenance": {
            "method": "named gameplay review correction",
            "proof_grade": "reviewed-editorial",
            "source_ids": ["source-ledger"],
        },
    }]
    timeline.validate_timeline_against_package(source, package)
    overlay = timeline.build_review_overlay(
        package=package,
        timeline=source,
        override_id="fixture-2015-16-editorial-r1",
    )
    review_v2.validate_overrides(overlay)
    assert overlay["data_patches"] == [{
        "id": "fixture-player-2-speed",
        "target": {"entity": "player", "id": "player-2"},
        "expected": {"ratings.values.speed": 60},
        "set": {"ratings.values.speed": 91},
        "reason": "First-game review confirmed the synthetic speed value was too low.",
        "proof": {"grade": "reviewed-editorial", "artifact_id": "receipt-contract"},
        "rating_provenance": {
            "method": "named gameplay review correction",
            "proof_grade": "reviewed-editorial",
            "source_ids": ["source-ledger"],
        },
    }]
    derived, receipt = review_v2.apply_overrides(
        package, overlay, derived_package_id="pm99-2015-16-fixture-r1"
    )
    assert next(row for row in derived["players"] if row["id"] == "player-2")["ratings"]["values"]["speed"] == 91
    assert receipt["data_patch_count"] == 1


def test_same_person_can_hold_player_and_manager_roles_across_seasons() -> None:
    package = _package()
    package["players"][0]["person_id"] = "person-fixture-player-manager"
    package["managers"][0]["person_id"] = "person-fixture-player-manager"
    package["managers"][0]["name"] = package["players"][0]["name"]
    package_v2.validate_package(package, strict=True)
    source = timeline.seed_timeline_from_package(package, timeline_id="pm99-editorial-2000-2026")
    person = next(row for row in source["identities"]["people"] if row["id"] == "person-fixture-player-manager")
    assert person["roles"] == ["manager", "player"]


def test_timeline_rejects_conflicting_shared_amendments() -> None:
    package = _package()
    source = timeline.seed_timeline_from_package(package, timeline_id="pm99-editorial-2000-2026")
    amendment = {
        "id": "fixture-player-2-speed-a",
        "seasons": ["2015-16"],
        "target": {"entity": "player", "identity_id": "person-fixture-player-2"},
        "changes": {"ratings.values.speed": 91},
        "reason": "One reviewed decision.",
        "proof": {"grade": "reviewed-editorial", "artifact_id": "receipt-contract"},
        "rating_provenance": {"method": "review", "proof_grade": "reviewed-editorial", "source_ids": ["source-ledger"]},
    }
    competing = copy.deepcopy(amendment)
    competing["id"] = "fixture-player-2-speed-b"
    competing["changes"] = {"ratings.values.speed": 92}
    source["amendments"] = [amendment, competing]
    with pytest.raises(timeline.TimelineError, match="overlaps another amendment"):
        timeline.validate_timeline(source)
