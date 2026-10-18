"""Tests for the portable PM99 historical season-package V2 contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import season_package_v2 as package_v2  # noqa: E402
from season_package_v2 import (  # noqa: E402
    PackageValidationError,
    migrate_2015_english92,
    read_canonical_package,
    validate_package,
    write_canonical_package,
)


HASH = "a" * 64


def test_schema_validation_cache_is_content_addressed() -> None:
    package_v2._SCHEMA_ERROR_CACHE.clear()
    package = _valid_package()

    assert package_v2._schema_errors(package) == []
    assert len(package_v2._SCHEMA_ERROR_CACHE) == 1
    assert package_v2._schema_errors(package) == []
    assert len(package_v2._SCHEMA_ERROR_CACHE) == 1

    package["package_id"] = "pm99-2016-17-fixture"
    assert package_v2._schema_errors(package) == []
    assert len(package_v2._SCHEMA_ERROR_CACHE) == 2


def _proof() -> dict[str, str]:
    return {"grade": "static-contract", "artifact_id": "receipt-contract"}


def test_compiled_schema_agrees_with_original_validator_and_does_not_modify_data():
    import copy
    import jsonschema
    pytest.importorskip('jsonschema_rs')
    raw = package_v2.SCHEMA_PATH.read_bytes()
    original = jsonschema.Draft202012Validator(json.loads(raw))
    examples = [_valid_package()]
    for field, value in [('nationality', 30), ('fine_roles', [99]), ('height_cm', True)]:
        bad = copy.deepcopy(examples[0]); bad['players'][0]['facts'][field] = value; examples.append(bad)
    bad = copy.deepcopy(examples[0]); bad['players'][0]['extra_unknown_key'] = 1; examples.append(bad)
    for document in examples:
        before = copy.deepcopy(document)
        assert package_v2._fast_schema_valid(raw, document) == original.is_valid(document)
        assert document == before


def test_schema_cache_is_bound_to_contract_bytes(tmp_path, monkeypatch):
    package_v2._SCHEMA_ERROR_CACHE.clear()
    raw = json.loads(package_v2.SCHEMA_PATH.read_text())
    path = tmp_path / 'schema.json'; path.write_text(json.dumps(raw))
    monkeypatch.setattr(package_v2, 'SCHEMA_PATH', path)
    package = _valid_package()
    assert package_v2._schema_errors(package) == []
    raw['properties']['schema_version']['const'] = 'not-this-package'
    path.write_text(json.dumps(raw))
    assert package_v2._schema_errors(package)


def test_schema_accelerator_missing_retains_python_fallback(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'jsonschema_rs', None)
    assert package_v2._fast_schema_valid(b'{"type":"object"}', {}) is None


def test_schema_accelerator_does_not_fetch_remote_references():
    pytest.importorskip('jsonschema_rs')
    assert package_v2._fast_schema_valid(b'{"$ref":"https://example.invalid/schema"}', {}) is None


def _valid_package() -> dict:
    players = []
    portraits = []
    for carrier_id in range(1, 12):
        player_id = f"player-{carrier_id}"
        players.append({
            "id": player_id,
            "person_id": f"person-fixture-player-{carrier_id}",
            "carrier_id": carrier_id,
            "carrier_family": "dd6361",
            "club_id": "club-100",
            "name": f"Player {carrier_id}",
            "facts": {
                "birth_date": "1990-01-01",
                "nationality": "ENG",
                "height_cm": 180,
                "weight_kg": 75,
                "primary_position": "G" if carrier_id == 1 else "M",
                "fine_roles": [0],
                "shirt_number": carrier_id,
            },
            "ratings": {
                "profile": "pm99-visible-skills-v1",
                "values": {key: 60 for key in (
                    "quality", "speed", "stamina", "aggression", "passing", "tackling", "heading", "shooting", "dribbling", "handling",
                )},
                "provenance": {
                    "method": "reviewed editorial",
                    "proof_grade": "reviewed-editorial",
                    "source_ids": ["source-ledger"],
                },
            },
            "proof": _proof(),
        })
        portraits.append({
            "player_id": player_id,
            "status": "native-no-photo",
            "proof": _proof(),
        })
    return {
        "schema_version": "pm99-season-package-v2",
        "package_id": "pm99-2015-16-fixture",
        "season": {"start_year": 2015, "end_year": 2016, "label": "2015/16"},
        "scope": {
            "id": "english-four-divisions",
            "title": "Fixture scope",
            "countries": ["ENG"],
            "competition_policy": "proven-membership-only",
        },
        "artifacts": [
            {"id": "calendar-output", "kind": "calendar-patch", "sha256": HASH},
            {"id": "kit-home", "kind": "kit-render", "sha256": HASH},
            {"id": "receipt-contract", "kind": "season-input", "sha256": HASH},
        ],
        "sources": [{
            "id": "source-ledger",
            "title": "Captured player ledger",
            "proof_grade": "source-captured",
            "evidence_artifact_id": "receipt-contract",
        }],
        "clubs": [{
            "id": "club-100", "identity_id": "club-fixture-town",
            "carrier_id": 100,
            "name": "Fixture Town",
            "division": "Premier League",
            "manager_id": "manager-1",
            "roster_player_ids": [f"player-{number}" for number in range(1, 12)],
            "opening": {
                "fixture_date": "2015-08-08",
                "starting_xi_player_ids": [f"player-{number}" for number in range(1, 12)],
                "substitute_player_ids": [],
                "formation": "4-4-2",
                "tactics_positions": [[128, 55, 128, 55] for _ in range(11)],
                "proof": _proof(),
            },
            "proof": _proof(),
        }],
        "players": sorted(players, key=lambda item: item["id"]),
        "managers": [{"id": "manager-1", "person_id": "person-fixture-manager", "carrier_id": 1, "name": "Fixture Manager", "proof": _proof()}],
        "assets": {
            "kits": [{"club_id": "club-100", "artifact_ids": ["kit-home"], "proof": _proof()}],
            "portraits": portraits,
        },
        "calendar": {
            "base_year": 1998,
            "target_year": 2015,
            "target_rollover_year": 2016,
            "patch_artifact_id": "calendar-output",
            "proof": _proof(),
        },
        "proofs": [{"id": "proof-static", "grade": "static-contract", "artifact_id": "receipt-contract", "covers": ["fixture"]}],
        "migration": {"status": "native-v2", "source_artifact_ids": ["receipt-contract"], "known_gaps": []},
    }


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_legacy_build(build: Path) -> None:
    build.mkdir()
    team = {
        "club": "Fixture Town",
        "short_name": "Fixture Town",
        "full_club_name": "Fixture Town FC",
        "division": "Premier League",
        "record_id": 307,
        "manager_record_id": 49,
        "stadium_name": "Fixture Ground",
        "seated_capacity": 20000,
        "starting_finance": 1000000,
        "roster_player_record_ids": list(range(1, 12)),
        "opening_lineup_player_record_ids": list(range(1, 12)),
        "substitute_player_record_ids": [],
        "opening_tactics_positions": [[128, 55, 128, 55] for _ in range(11)],
        "opening_tactics_source": {"fixture_date": "08/08/2015", "formation": "4-4-2"},
    }
    manifest_players = []
    ledger = []
    face_rows = []
    for record_id in range(1, 12):
        source = build / f"source-{record_id}.png"
        crop = build / f"crop-{record_id}.png"
        source.write_bytes(f"source-{record_id}".encode())
        crop.write_bytes(f"crop-{record_id}".encode())
        manifest_players.append({"record_id": record_id, "fine_roles": [0]})
        ledger.append({
            "record_id": record_id,
            "team_record_id": 307,
            "family": "dd6361",
            "name": f"Player {record_id}",
            "birth_date": "1990-01-01",
            "nationality": "ENG",
            "height_cm": 180,
            "weight_kg": 75,
            "position": "G" if record_id == 1 else "M",
            "fine_roles": [0],
            "shirt_number": record_id,
            "rating_basis": "fixture rating source",
            "visible_skills": {key: 60 for key in (
                "quality", "speed", "stamina", "aggression", "passing", "tackling", "heading", "shooting", "dribbling", "handling",
            )},
        })
        face_rows.append({
            "record_id": record_id,
            "status": "applied",
            "source_image_path": str(source),
            "preview_path": str(crop),
            "source_url": f"https://example.test/{record_id}.png",
        })
    _write(build / "2015-16-english92-manifest.json", {"teams": [team], "players": manifest_players})
    _write(build / "player-ledger.json", ledger)
    _write(build / "manager-audit.json", [{"manager_record_id": 49, "manager_name": "Fixture Manager"}])
    _write(build / "face-stage-receipt.json", {"minifoto_sha256_after": HASH, "rows": face_rows})
    kit_dir = build / "kit-stage"
    kit_dir.mkdir()
    _write(kit_dir / "fixture-kit-receipt.json", {"patched": [{"team_id": 307, "archive_name": "MINIESC.PKF", "slot": 3, "bitmap_sha256_after": HASH}]})
    _write(build / "calendar-patch-receipt.json", {"base_year": 1998, "target_year": 2015, "target_rollover_year": 2016, "after_sha256": HASH})
    _write(build / "build-manifest.json", {"source_hashes": {"EQ98030.FDI": HASH}, "output_hashes": {"EQ98030.FDI": HASH}})


def test_valid_native_package_is_strictly_accepted(tmp_path: Path) -> None:
    package_path = tmp_path / "season.json"
    write_canonical_package(package_path, _valid_package())
    package = read_canonical_package(package_path)
    validate_package(package, strict=True)


def test_valid_native_package_accepts_1999_00_boundary() -> None:
    package = _valid_package()
    package["package_id"] = "pm99-1999-00-fixture"
    package["season"] = {"start_year": 1999, "end_year": 2000, "label": "1999/00"}
    package["calendar"]["target_year"] = 1999
    package["calendar"]["target_rollover_year"] = 2000

    validate_package(package, strict=True)


def test_native_package_accepts_explicit_mode1_opening_preservation(tmp_path: Path) -> None:
    package = _valid_package()
    package["clubs"][0]["division"] = "preserve-existing-mode1-membership"
    package["clubs"][0]["opening"] = {
        "policy": "preserve-existing-mode1",
        "proof": _proof(),
    }
    package_path = tmp_path / "mode1-preserve-opening.json"
    write_canonical_package(package_path, package)
    validate_package(read_canonical_package(package_path), strict=True)


def test_native_package_accepts_explicit_mode1_metadata_and_kit_preservation() -> None:
    package = _valid_package()
    package["clubs"][0].pop("ground_name", None)
    package["clubs"][0].pop("seated_capacity", None)
    package["clubs"][0]["ground_policy"] = "preserve-existing-mode1"
    package["clubs"][0]["capacity_policy"] = "preserve-existing-mode1"
    package["managers"][0].pop("person_id")
    package["managers"][0]["policy"] = "preserve-existing-mode1"
    package["assets"]["kits"][0]["artifact_ids"] = []
    package["assets"]["kits"][0]["policy"] = "preserve-existing-mode1"
    validate_package(package, strict=True)


def test_player_fact_accepts_explicit_mode1_preserve_object() -> None:
    package = _valid_package()
    package["players"][0]["facts"]["shirt_number"] = {"policy": "preserve-existing-mode1"}
    validate_package(package, strict=True)


def test_noncanonical_bytes_and_absolute_paths_are_rejected(tmp_path: Path) -> None:
    package = _valid_package()
    package["artifacts"][0]["relative_path"] = "/home/unsafe/receipt.json"
    with pytest.raises(PackageValidationError, match="absolute filesystem paths"):
        validate_package(package)

    package_path = tmp_path / "season.json"
    package_path.write_text(json.dumps(_valid_package(), indent=2), encoding="utf-8")
    with pytest.raises(PackageValidationError, match="not canonically encoded"):
        read_canonical_package(package_path)


def test_strict_native_package_requires_reconciled_editorial_ids() -> None:
    package = _valid_package()
    del package["clubs"][0]["identity_id"]
    del package["managers"][0]["person_id"]
    del package["players"][0]["person_id"]
    with pytest.raises(PackageValidationError, match="reconciled .* ID"):
        validate_package(package, strict=True)


def test_explicit_manager_names_preserve_full_identity():
    package = _valid_package()
    package['managers'][0]['name'] = 'Louis van Gaal'
    package['managers'][0]['native_names'] = {'surname': 'van Gaal', 'display_name': 'Louis van Gaal'}
    original_name = package['managers'][0]['name']
    validate_package(package, strict=True)
    assert package['managers'][0]['name'] == original_name


@pytest.mark.parametrize('native_names', [
    {'surname': 'Wenger'}, {'surname': ' W', 'display_name': 'Arsène Wenger'},
    {'surname': '🚫', 'display_name': 'Wenger'}, {'surname': 'x' * 256, 'display_name': 'Wenger'},
])
def test_manager_native_names_reject_invalid_or_incomplete_segments(native_names):
    package = _valid_package()
    package['managers'][0]['native_names'] = native_names
    with pytest.raises(PackageValidationError, match='native_names'):
        validate_package(package)


def test_manager_alias_cannot_override_whole_record_preservation():
    package = _valid_package()
    package['managers'][0].update(policy='preserve-existing-mode1',
        native_names={'surname': 'Wenger', 'display_name': 'Wenger'})
    with pytest.raises(PackageValidationError, match='whole-record fallback'):
        validate_package(package)


def test_manager_name_edit_cannot_silently_keep_an_old_person_alias():
    package = _valid_package()
    package['managers'][0].update(name='New Coach',
        native_names={'surname': 'Wenger', 'display_name': 'Arsène Wenger'})
    with pytest.raises(PackageValidationError, match='refresh it after a name edit'):
        validate_package(package)


def test_strict_native_package_rejects_unreconciled_same_person_candidates() -> None:
    package = _valid_package()
    first = next(row for row in package["players"] if row["id"] == "player-1")
    second = next(row for row in package["players"] if row["id"] == "player-2")
    second["name"] = first["name"]
    second["facts"] = dict(first["facts"])
    with pytest.raises(PackageValidationError, match="ambiguous same-person"):
        validate_package(package, strict=True)


def test_recycle_clone_carrier_must_fit_gameplay_positive_15_bit_range() -> None:
    package = _valid_package()
    player = package["players"][0]
    player["recycle_from_mode1_carrier_id"] = 12
    player["mode0_clone_carrier_id"] = 32768

    with pytest.raises(PackageValidationError, match="mode0_clone_carrier_id"):
        validate_package(package)


def test_each_player_rating_provenance_must_reference_a_known_source() -> None:
    package = _valid_package()
    package["players"][0]["ratings"]["provenance"]["source_ids"] = ["source-missing"]
    with pytest.raises(PackageValidationError, match="unknown source"):
        validate_package(package, strict=True)


def test_cross_references_and_formation_shape_fail_closed() -> None:
    package = _valid_package()
    package["clubs"][0]["opening"]["starting_xi_player_ids"][10] = "player-missing"
    package["clubs"][0]["opening"]["formation"] = "4-1-4-2"
    with pytest.raises(PackageValidationError) as exc_info:
        validate_package(package)
    text = str(exc_info.value)
    assert "not in its roster" in text
    assert "outfield shape must total ten" in text


def test_legacy_2015_adapter_outputs_portable_canonical_metadata(tmp_path: Path) -> None:
    build = tmp_path / "legacy-build"
    _write_legacy_build(build)
    package = migrate_2015_english92(build)
    assert package["migration"]["status"] == "legacy-migrated"
    assert len(package["clubs"]) == 1
    assert len(package["players"]) == 11
    assert len(package["assets"]["portraits"]) == 11
    assert package["assets"]["portraits"][0]["status"] == "applied"
    assert any("crop recipe" in gap for gap in package["migration"]["known_gaps"])
    rendered = tmp_path / "migrated.json"
    write_canonical_package(rendered, package)
    validate_package(read_canonical_package(rendered))
    with pytest.raises(PackageValidationError, match="strict validation rejects legacy-migrated"):
        validate_package(package, strict=True)
    assert "/tmp/" not in rendered.read_text(encoding="utf-8")


def test_legacy_2015_adapter_preserves_explicit_native_no_photo_reason(tmp_path: Path) -> None:
    build = tmp_path / "legacy-build"
    _write_legacy_build(build)
    face_path = build / "face-stage-receipt.json"
    face = json.loads(face_path.read_text(encoding="utf-8"))
    face["rows"][0] = {
        "record_id": 1,
        "status": "intentionally-no-photo",
        "no_verified_portrait_reason": "no identity-safe era photograph was found",
    }
    _write(face_path, face)
    package = migrate_2015_english92(build)
    portrait = next(row for row in package["assets"]["portraits"] if row["player_id"] == "player-1")
    assert portrait == {
        "player_id": "player-1",
        "status": "native-no-photo",
        "review_reason": "no identity-safe era photograph was found",
        "proof": {"grade": "legacy-migrated", "artifact_id": "legacy-face-stage-receipt"},
    }
