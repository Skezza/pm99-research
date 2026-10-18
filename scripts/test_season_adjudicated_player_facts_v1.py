"""Focused source-admission tests for known-wrong player fact adjudication."""

import copy
import json
from pathlib import Path

import pytest

from app.fdi_indexed import IndexedFDIFile
from scripts import season_adjudicated_player_facts_v1 as subject
from scripts import season_package_compiler_v2 as compiler
from scripts import season_release_registry_v1 as registry
from scripts import season_source_verified_player_changes_v1 as changes
from scripts.season_within_club_reserve_repair_v1 import native_facts


ROOT = Path(__file__).resolve().parents[1]
WITNESS_PATH = ROOT / ".local/consolidated-audit-20261009/Scotland2000-label-manager-v1/larsson-facts/adjudicated-witness-v1.json"


@pytest.fixture
def witness():
    if not WITNESS_PATH.is_file():
        pytest.skip('retained original-source witness unavailable')
    return json.loads(WITNESS_PATH.read_text(encoding="utf-8"))


def test_retained_witness_reproduces_adjudicated_facts(witness):
    assert subject.adjudicate(witness) == {
        "birth_date": "1971-09-20",
        "nationality": "SWE",
    }


def test_country_code_must_match_published_country_literal(witness):
    """A source's literal 'Sweden' must not be relabelable as another valid code."""
    forged = copy.deepcopy(witness)
    forged["values"]["nationality"] = "ENG"
    forged["official_sources"][0]["nationality"]["code"] = "ENG"

    with pytest.raises(ValueError):
        subject.adjudicate(forged)


def test_historical_provider_id_is_not_replaceable_by_matching_name_or_old_dob(witness):
    forged = copy.deepcopy(witness)
    forged["historical_identity"]["provider_player_id"] = 3515

    with pytest.raises(ValueError):
        subject.adjudicate(forged)


@pytest.mark.parametrize("field", ["source_row_sha256", "preallocation_sha256", "match_sha256"])
def test_historical_identity_requires_exact_source_hashes(witness, field):
    """Hashes bind the historical row and original source bodies; a name/DOB is not enough."""
    forged = copy.deepcopy(witness)
    if field == "source_row_sha256":
        forged["historical_identity"][field] = "0" * 64
    elif field == "preallocation_sha256":
        forged["historical_identity"]["preallocation"]["sha256"] = "0" * 64
    else:
        forged["historical_identity"]["match"]["sha256"] = "0" * 64

    with pytest.raises((ValueError, OSError)):
        subject.adjudicate(forged)


def test_historical_person_id_must_be_derived_from_bound_source_row(witness):
    forged = copy.deepcopy(witness)
    forged["person_id"] = "person-source-" + "0" * 64

    with pytest.raises(ValueError):
        subject.adjudicate(forged)


def test_published_birthdays_must_agree_with_adjudicated_date(witness):
    forged = copy.deepcopy(witness)
    forged["values"]["birth_date"] = "1971-09-10"

    with pytest.raises(ValueError):
        subject.adjudicate(forged)


def test_claimed_source_date_must_be_present_in_that_original_body(witness):
    forged = copy.deepcopy(witness)
    forged["official_sources"][1]["birth_date"]["literal"] = "10/09/1971"

    with pytest.raises(ValueError):
        subject.adjudicate(forged)


def _prepared_2000_case():
    path = ROOT / ".local/consolidated-audit-20261009/Scotland2000-label-manager-v1/larsson-facts/2000-01-adjudicated-input-v1.json"
    if not path.is_file():
        pytest.skip("retained 2000-01 adjudication input is unavailable")
    request = json.loads(path.read_text(encoding="utf-8"))
    base = registry.load_registered_release(request["season"], request["release_id"])
    return base, path, request, changes.prepare(base, path)


def test_native_postreadback_matches_adjudicated_recipe_and_country():
    base, _path, _request, plan = _prepared_2000_case()
    original_jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    original_eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()

    updated_jug, updated_eq = changes.apply(original_jug, original_eq, plan)

    assert updated_eq == original_eq
    codes = compiler._extract_country_codes_from_textos(base.game_path / "DBDAT/TEXTOS.PKF")
    country_code = compiler._country_code("SWE", codes)
    entries = {entry.record_id: entry for entry in IndexedFDIFile.from_bytes(updated_jug).entries}
    for row in plan["updates"]:
        carrier = row["carrier_id"]
        assert native_facts(updated_jug, carrier)["birth_date"] == row["values"]["birth_date"]
        raw = entries[carrier].decode_payload(updated_jug)
        end = row["native_masks"][0]["record_offset"]
        assert raw[end] ^ 0x61 == country_code

    allowed = {
        mask["file_offset"]
        for row in plan["updates"]
        for mask in row["native_masks"]
        if mask["before"] != mask["after"]
    }
    changed = {
        index for index, (before, after) in enumerate(zip(original_jug, updated_jug))
        if before != after
    }
    assert changed == allowed


def test_native_writer_rejects_a_mixed_preimage():
    base, _path, _request, plan = _prepared_2000_case()
    original_jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    original_eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    updated_jug, _ = changes.apply(original_jug, original_eq, plan)
    changed_mask = next(
        mask for row in plan["updates"] for mask in row["native_masks"]
        if mask["before"] != mask["after"]
    )
    mixed = bytearray(original_jug)
    mixed[changed_mask["file_offset"]] = updated_jug[changed_mask["file_offset"]]

    with pytest.raises(ValueError, match="exact complete pre/postimages"):
        changes.apply(bytes(mixed), original_eq, plan)
