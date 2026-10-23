"""Canonical source/native admission, including persisted plans and old-parent safety."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import sys

import pytest
import hashlib
import json

from scripts import season_period_cohort_coach_v4 as subject
from scripts import season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher

ROOT = registry.ROOT
PARENTS = {"2004-05": "sourced-keeper-profile-countries-20261023-r185a",
           "2006-07": "sourced-keeper-profile-countries-20261023-r187a",
           "2003-04": "sourced-keeper-profile-countries-20261023-r184a"}


def base_for(season):
    return registry.load_registered_release(season, PARENTS[season])


@pytest.fixture(autouse=True)
def optional_private_corpus(request):
    if request.node.name == "test_raw_html_title_and_canonical_identity_are_checked_not_just_receipt_fields":
        return
    marker = subject.EVIDENCE_ROOT / "raw/dfb-hertha-squad-2004-05.html"
    if not marker.is_file() or not all(registry.locator_path(s, p).is_file() for s, p in PARENTS.items()):
        pytest.skip("optional retained source/native corpus unavailable")


@lru_cache(maxsize=2)
def prepared(season: str) -> dict:
    base = base_for(season)
    return subject.prepare(base, expected_release_id=base.release_id)


@pytest.mark.parametrize("season", ["2004-05", "2006-07"])
def test_actual_period_cohort_and_dated_gotz_are_admitted(season):
    plan = prepared(season)
    admission = plan["admission"]
    assert plan["schema_version"] == subject.SCHEMA
    assert plan["updates"][0]["carrier_id"] == 421
    assert (plan["updates"][0]["before"], plan["updates"][0]["after"]) == (
        "1. FC Koln", "Hertha Berlin")
    assert admission["annual_capture"]["represented_members"] == 25
    assert admission["annual_capture"]["selector"]["club_name"] == "Hertha Berlin"
    assert admission["coach_history"]["decision"] == {
        "name": "Falko Götz",
        "from_date": "2004-07-01",
        "to_date": "2007-04-10",
        "target_date": season[:4] + "-08-01",
        "ignored_invalid_historical_rows": [
            ["23", "Günter Sebert", "21 August 1992", "20 October 1990"]
        ],
    }
    assert admission["fiedler_identity"] == {
        "carrier_id": 13196,
        "source_name": "Christian Fiedler",
        "recipe_birth_date": "1975-03-27",
        "dfb_literal_birth_date": "27.03.1975",
        "native_birth_date": "1975-03-27",
    }
    crosswalk = admission["native_birth_date_crosswalk"]
    assert crosswalk["status"] == "all-25-exact"
    assert crosswalk["count"] == 25
    assert crosswalk["mismatches"] == []
    assert crosswalk["birthday_changes_proposed"] == 0
    assert all(row["annual_birth_date"] == row["recipe_birth_date"] == row["native_birth_date"]
               for row in crosswalk["entries"])
    assert plan["manager_plan"]["source_method"] == subject.MANAGER_SOURCE_METHOD
    manager = plan["manager_plan"]["updates"][0]
    assert (manager["carrier_id"], manager["before"], manager["native_before"]) == (
        1313, "Röber", "Röber")
    assert (manager["after"], manager["native_after"]) == ("Falko Götz", "Götz")
    assert manager["effective_opening_date"] == season[:4] + "-08-01"
    assert manager["native_manager_owner_count"] == 1
    assert plan["native_writer_preflight"]["manager_native_after"] == "Götz"
    assert plan["native_writer_preflight"]["ent_decoded_records_changed"] == [1313]
    assert plan["native_writer_preflight"]["eq_delta"][0]["carrier_id"] == 421
    assert "Current native and recipe manager link is Röber" in plan["scope"]
    assert "sourced manager identity required" in plan["scope"]
    subject.verify_manager_pair(plan, plan["manager_plan"])
    subject.verify(base_for(season), plan)


@pytest.mark.parametrize("season", ["2004-05", "2006-07"])
def test_json_stored_v2_plan_freshly_reverifies(season, tmp_path):
    base = base_for(season)
    plan = subject.prepare(base, expected_release_id=base.release_id)
    path = tmp_path / f"{season}-hertha-plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    restored = json.loads(path.read_text(encoding="utf-8"))
    assert restored == plan
    subject.verify(base, restored)


@pytest.mark.parametrize("season", ["2004-05", "2006-07"])
def test_existing_publisher_materializes_gotz_native_name_and_dated_coverage(season):
    plan = prepared(season)
    base = base_for(season)
    package = publisher.pipeline.read_json_file(base.package_path)
    updated = publisher.updated_package(
        package,
        {"season": season, "updates": []},
        manager_plan=plan["manager_plan"],
        club_plan=plan,
    )
    manager = next(row for row in updated["managers"] if row["carrier_id"] == 1313)
    manager_sha = hashlib.sha256(publisher.pipeline.canonical_json_bytes(
        plan["manager_plan"])).hexdigest()
    proof_id = "proof-historical-managers-" + season + "-" + manager_sha[:16]
    proof = next(row for row in updated["proofs"] if row["id"] == proof_id)
    assert manager["name"] == "Falko Götz"
    assert manager["native_names"] == {"surname": "Götz", "display_name": "Götz"}
    assert proof["covers"] == ["raw-reparsed-dated-closed-manager-tenure"]


@pytest.mark.parametrize("season", ["2004-05", "2006-07"])
def test_explicit_expected_release_pins_exact_parent_and_allows_named_rebase(season):
    base = base_for(season)
    plan = subject.prepare(base, expected_release_id=base.release_id)
    assert plan["expected_release_id"] == base.release_id
    with pytest.raises(ValueError, match="explicit expected parent release"):
        subject.prepare(base, expected_release_id="unrelated-child")


@pytest.mark.parametrize("season", ["2004-05", "2006-07"])
def test_native_dob_mismatch_is_named_and_not_silently_repaired(season, monkeypatch):
    base = base_for(season)
    original = subject._cached_native_facts
    wrong_date = "1975-03-28"

    def injected(jug_bytes, carrier_id):
        row = original(jug_bytes, carrier_id)
        if carrier_id == 13196:
            return {**row, "birth_date": wrong_date}
        return row

    monkeypatch.setattr(subject, "_cached_native_facts", injected)
    plan = subject.prepare(base, expected_release_id=base.release_id)
    crosswalk = plan["admission"]["native_birth_date_crosswalk"]
    assert crosswalk["status"] == "mismatch"
    assert [row["carrier_id"] for row in crosswalk["mismatches"]] == [13196]
    assert crosswalk["mismatches"][0]["native_birth_date"] == wrong_date
    assert crosswalk["mismatches"][0]["recipe_birth_date"] == "1975-03-27"
    assert crosswalk["birthday_changes_proposed"] == 0
    assert plan["updates"][0]["after"] == "Hertha Berlin"


@pytest.mark.parametrize("season", ["2004-05", "2006-07"])
def test_primary_receipts_and_original_bindings_are_present(season):
    plan = prepared(season)
    manager_sources = plan["manager_plan"]["updates"][0]["evidence"]["raw_sources"]
    assert len(manager_sources) == 3
    for source in manager_sources:
        raw_path = ROOT / source["path"]
        assert registry.sha256_file(raw_path) == source["sha256"]
        receipt_path = source.get("source_receipt_path") or source.get("receipt_path")
        assert receipt_path
        receipt_sha = source.get("source_receipt_sha256") or source["receipt_sha256"]
        assert registry.sha256_file(ROOT / receipt_path) == receipt_sha
    evidence = plan["admission"]["primary_dfb_sources"]
    assert {row["id"] for row in evidence} >= {
        subject.DFB[season]["team"], subject.DFB[season]["fixture"],
        subject.DFB[season]["home_fixture"], "hertha-official-olympiastadion-history",
    }


def test_2003_04_is_not_admitted_by_v4():
    base = base_for("2003-04")
    with pytest.raises(ValueError, match="only 2004-05 and 2006-07"):
        subject.prepare(base)


def test_wrong_official_url_or_claim_does_not_bind_capture():
    with pytest.raises(ValueError, match="original source/receipt does not bind"):
        subject._captured_page(
            "dfb-hertha-squad-2004-05",
            expected_url="https://wrong.example/hertha",
            title="Hertha BSC, Bundesliga 2004/05 - DFB Datencenter",
            phrases=("Falko Götz",),
        )


def test_raw_html_title_and_canonical_identity_are_checked_not_just_receipt_fields():
    raw = (b'<html><head><title>Approved</title>'
           b'<link rel="canonical" href="https://example.test/page"></head>'
           b'<body>Original body</body></html>')
    assert subject._validate_html_identity(raw, expected_url="https://example.test/page",
                                           title="Approved") == "Original body"
    with pytest.raises(ValueError, match="raw source title"):
        subject._validate_html_identity(raw.replace(b"Approved", b"Forged"),
            expected_url="https://example.test/page", title="Approved")
    with pytest.raises(ValueError, match="canonical URL"):
        subject._validate_html_identity(raw.replace(b"https://example.test/page",
                                                     b"https://wrong.test/page"),
            expected_url="https://example.test/page", title="Approved")
    with pytest.raises(ValueError, match="canonical URL"):
        subject._validate_html_identity(raw.replace(
            b"</head>", b'<link rel="canonical" href="https://example.test/page"></head>'),
            expected_url="https://example.test/page", title="Approved")


def test_raw_page_body_claim_not_receipt_title_is_required():
    with pytest.raises(ValueError, match="literal target-season primary claim missing"):
        subject._captured_page(
            "dfb-hertha-squad-2004-05",
            expected_url="https://datencenter.dfb.de/competitions/bundesliga/seasons/2004-2005/teams/hertha-bsc",
            title="Hertha BSC, Bundesliga 2004/05 - DFB Datencenter",
            phrases=("Not present in the raw page body",),
        )
    with pytest.raises(ValueError, match="literal target-season primary claim missing"):
        subject._captured_page(
            "dfb-hertha-squad-2004-05",
            expected_url="https://datencenter.dfb.de/competitions/bundesliga/seasons/2004-2005/teams/hertha-bsc",
            title="Hertha BSC, Bundesliga 2004/05 - DFB Datencenter",
            phrases=("Falko Götz", "Not the actual coach"),
        )


def test_dated_coach_parser_rejects_nonmatching_gotz_period():
    with pytest.raises(ValueError, match="does not identify Götz"):
        subject._dated_gotz("2003-04")
