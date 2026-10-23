"""Portable parser/guard tests plus optional immutable local native corpus."""
import copy
import hashlib
import os
import json
from pathlib import Path

import pytest

from scripts import season_known_wrong_profile_nationality_v1 as proposal
from scripts import season_release_registry_v1 as registry

ROOT = registry.ROOT
HERE = ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/horne"
ORIGINALS = HERE / "gould-nationality-v1" / "originals"
GOULD_PATH = ORIGINALS / "soccerbase-gould-2982.html"
DFB_PATH = ORIGINALS / "dfb-fiedler-profile.html"
GOULD_URL = "https://www.soccerbase.com/players/player.sd?player_id=2982"
SAMPLE_INPUT = HERE / "known-wrong-sample-input-r178-v1.json"
SB_SYNTHETIC = b"""<html><h1>Jonathan Gould</h1><table>
<tr><td>Born</td><td>18 Jul, 1968</td></tr>
<tr><td>Nationality</td><td>Scotland</td></tr>
</table></html>"""
DFB_SYNTHETIC = b"""<html><head><link rel="canonical" href="https://datencenter.dfb.de/en/data-center/people/christian-fiedler/player"></head><table>
<tr><td>Name</td><td>Christian Fiedler</td></tr>
<tr><td>Date of birth</td><td>1975-03-27</td></tr>
<tr><td>Nation</td><td>Germany</td></tr>
</table></html>"""


def synthetic_wikidata_bridge():
    time_value = {"time": "+1968-08-16T00:00:00Z", "timezone": 0,
        "before": 0, "after": 0, "precision": 11,
        "calendarmodel": "http://www.wikidata.org/entity/Q1985727"}
    document = {"entities": {"Q552710": {"id": "Q552710",
        "labels": {"en": {"language": "en", "value": "Dmitri Kharine"}},
        "aliases": {"en": [{"language": "en", "value": "Dmitri Kharin"}]},
        "claims": {
            "P569": [{"rank": "normal", "mainsnak": {"property": "P569",
                "snaktype": "value", "datavalue": {"type": "time", "value": time_value}}}],
            "P2193": [{"rank": "normal", "mainsnak": {"property": "P2193",
                "snaktype": "value", "datavalue": {"type": "string", "value": "4177"}}}],
        }}}}
    return document


def bridge_bytes(document):
    return json.dumps(document, ensure_ascii=False, sort_keys=True).encode()


def test_wikidata_bridge_accepts_exact_alias_dob_and_soccerbase_id():
    body = bridge_bytes(synthetic_wikidata_bridge())
    digest = hashlib.sha256(body).hexdigest()
    receipt = {"sha256": digest, "url": proposal.WIKIDATA_URL,
        "final_url": proposal.WIKIDATA_URL, "http_status": 200,
        "method": "original-network-JSON"}
    result = proposal.parse_wikidata_alias_bridge(body, receipt,
        expected_sha256=digest, expected_qid="Q552710", expected_url=proposal.WIKIDATA_URL)
    assert result["english_label"] == "Dmitri Kharine"
    assert result["english_alias"] == "Dmitri Kharin"
    assert result["birth_date"] == "1968-08-16"
    assert result["soccerbase_player_id"] == 4177
    assert result["identity_link_only"] is True
    assert result["nationality_claimed"] is False


@pytest.mark.parametrize("fault", ["wrong_qid", "wrong_alias", "wrong_dob", "ambiguous_dob",
    "deprecated_dob", "wrong_id", "missing_dob", "bad_body_hash", "bad_url", "bad_final_url",
    "bad_status", "bad_method", "bad_receipt_hash"])
def test_wikidata_bridge_rejects_incorrect_or_ambiguous_identity(fault):
    doc = synthetic_wikidata_bridge()
    receipt_url = proposal.WIKIDATA_URL
    expected_qid = "Q552710"
    expected_url = proposal.WIKIDATA_URL
    if fault == "wrong_alias":
        doc["entities"]["Q552710"]["aliases"]["en"][0]["value"] = "Dmitri Other"
    elif fault == "wrong_dob":
        doc["entities"]["Q552710"]["claims"]["P569"][0]["mainsnak"]["datavalue"]["value"]["time"] = "+1968-08-17T00:00:00Z"
    elif fault == "ambiguous_dob":
        duplicate = copy.deepcopy(doc["entities"]["Q552710"]["claims"]["P569"][0])
        doc["entities"]["Q552710"]["claims"]["P569"].append(duplicate)
    elif fault == "deprecated_dob":
        doc["entities"]["Q552710"]["claims"]["P569"][0]["rank"] = "deprecated"
    elif fault == "wrong_id":
        doc["entities"]["Q552710"]["claims"]["P2193"][0]["mainsnak"]["datavalue"]["value"] = "9999"
    elif fault == "missing_dob":
        del doc["entities"]["Q552710"]["claims"]["P569"]
    elif fault == "wrong_qid":
        expected_qid = "Q999"
    elif fault == "bad_url":
        expected_url = "https://example.test/entity.json"
    body = bridge_bytes(doc)
    digest = hashlib.sha256(body).hexdigest()
    receipt = {"sha256": digest, "url": receipt_url, "final_url": receipt_url,
        "http_status": 200, "method": "original-network-JSON"}
    if fault == "bad_body_hash":
        digest = "0" * 64
    elif fault == "bad_url":
        receipt["url"] = expected_url
    elif fault == "bad_final_url":
        receipt["final_url"] = "https://example.test/entity.json"
    elif fault == "bad_status":
        receipt["http_status"] = 404
    elif fault == "bad_method":
        receipt["method"] = "cache-guess"
    elif fault == "bad_receipt_hash":
        receipt["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        proposal.parse_wikidata_alias_bridge(body, receipt,
            expected_sha256=digest, expected_qid=expected_qid, expected_url=expected_url)


def test_all_13_country_rows_actual_writer_in_memory(local_registered_sample):
    from scripts import season_pipeline_v2 as pipeline
    from scripts import season_release_registry_v1 as registry
    seasons = ("2000-01", "2001-02", "2002-03", "2003-04", "2004-05", "2005-06", "2006-07")
    inputs = {season: HERE / f"known-wrong-input-{season}-v2.json" for season in seasons}
    if not all(path.is_file() for path in inputs.values()):
        pytest.skip("seven retained preferred-season source inputs unavailable")
    proof = json.loads((HERE / "known-wrong-country-owner-proof-current-20261023-v1.json").read_text())
    from scripts import season_source_verified_player_changes_v1 as writer
    total_rows = 0
    observed_kharine = []
    for season in seasons:
        request_path = inputs[season]
        base = registry.load_registered_release(season,
            json.loads(request_path.read_text())["release_id"])
        plan = writer.prepare(base, request_path)
        expected = [row for row in proof["candidate_rows"] if row["season"] == season]
        assert [row["carrier_id"] for row in plan["updates"]] == [row["carrier"] for row in expected]
        package = pipeline.read_json_file(base.package_path)
        bound = writer.bind(package, plan)
        jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
        eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
        after, after_eq = writer.apply(jug, eq, plan)
        assert after_eq == eq
        allowed = {row["native_mask"]["file_offset"] for row in plan["updates"]}
        assert {i for i, (a, b) in enumerate(zip(jug, after)) if a != b} == allowed
        assert writer.apply(after, eq, plan) == (after, eq)
        for row in plan["updates"]:
            carrier = row["carrier_id"]
            actor = next(p for p in bound["players"] if p["carrier_id"] == carrier)
            assert actor["facts"]["nationality"] == row["nationality"]
            if carrier in (30425, 22055):
                observed_kharine.append(row["source_identity"])
                assert row["nationality"] == "RUS"
                assert row["source_identity"]["nationality_inferred_from_bridge"] is False
                assert row["source_identity"]["identity_bridge"]["qid"] == "Q552710"
        total_rows += len(plan["updates"])
    assert total_rows == 13
    assert len(observed_kharine) == 2


def production_writer(tmp_path, monkeypatch):
    """Exercise the actual guarded writer, never a rewritten test copy."""
    from scripts import season_source_verified_player_changes_v1 as writer
    return writer


@pytest.fixture
def local_registered_sample():
    from scripts import season_release_registry_v1 as registry
    if (os.environ.get("PM99_SKIP_LOCAL_COUNTRY_CORPUS") == "1"
            or not all(p.is_file() for p in (SAMPLE_INPUT, GOULD_PATH, DFB_PATH))
            or not registry.locator_path("2000-01",
                "sourced-original-keeper-roles-20261023-r178a").is_file()):
        pytest.skip("optional retained original captures and registered r178 sample unavailable")


@pytest.fixture
def sb_body():
    return SB_SYNTHETIC


@pytest.fixture
def dfb_body():
    return DFB_SYNTHETIC


def test_soccerbase_exact_name_dob_and_country_parser(sb_body):
    source = dict(provider="soccerbase", provider_player_id=2982, url=GOULD_URL)
    value = proposal.parse_profile_country(sb_body, source,
        actor_name="Jonathan Gould", birth_date="1968-07-18")
    assert value["name"] == "Jonathan Gould"
    assert value["birth_date"] == "1968-07-18"
    assert value["published_country"] == "Scotland"
    assert value["nationality"] == "SCO"


@pytest.mark.parametrize("name,dob", [("Jonathan G. Gould", "1968-07-18"),
                                      ("Jonathan Gould", "1968-07-19")])
def test_soccerbase_rejects_wrong_actor_name_or_dob(sb_body, name, dob):
    with pytest.raises(ValueError):
        proposal.parse_profile_country(sb_body,
            dict(provider="soccerbase", provider_player_id=2982, url=GOULD_URL),
            actor_name=name, birth_date=dob)


def test_soccerbase_rejects_kharin_kharine_spelling_without_alias(sb_body):
    with pytest.raises(ValueError):
        proposal.parse_profile_country(sb_body,
            dict(provider="soccerbase", provider_player_id=4177,
                 url="https://www.soccerbase.com/players/player.sd?player_id=4177"),
            actor_name="Dmitri Kharine", birth_date="1968-08-16")


def test_dfb_exact_canonical_profile_parser(dfb_body):
    value = proposal.parse_dfb_fiedler(dfb_body, url=proposal.DFB_URL,
        name="Christian Fiedler", birth_date="1975-03-27")
    assert value["published_country"] == "Germany"
    assert value["nationality"] == "GER"


@pytest.mark.parametrize("replacement", [
    b"",  # no canonical
    b'<link rel="canonical" href="https://example.test/fiedler">',
    (b'<link rel="canonical" href="' + proposal.DFB_URL.encode() + b'">'
     + b'<link rel="canonical" href="' + proposal.DFB_URL.encode() + b'">'),
])
def test_dfb_body_must_have_one_matching_canonical_link(dfb_body, replacement):
    canonical = b'<link rel="canonical" href="' + proposal.DFB_URL.encode() + b'">'
    body = dfb_body.replace(canonical, replacement)
    with pytest.raises(ValueError, match="canonical Fiedler profile URL"):
        proposal.parse_dfb_fiedler(body, url=proposal.DFB_URL,
            name="Christian Fiedler", birth_date="1975-03-27")


@pytest.mark.parametrize("url", [
    "http://datencenter.dfb.de/en/data-center/people/christian-fiedler/player",
    proposal.DFB_URL + "?source=1", proposal.DFB_URL + "#profile",
    "https://example.test/en/data-center/people/christian-fiedler/player",
])
def test_dfb_noncanonical_profile_url_rejected(dfb_body, url):
    with pytest.raises(ValueError, match="canonical"):
        proposal.parse_dfb_fiedler(dfb_body, url=url,
            name="Christian Fiedler", birth_date="1975-03-27")


@pytest.mark.parametrize("name,dob", [("Christian Fiedler Jr", "1975-03-27"),
                                      ("Christian Fiedler", "1975-03-28")])
def test_dfb_wrong_identity_or_dob_rejected(dfb_body, name, dob):
    with pytest.raises(ValueError):
        proposal.parse_dfb_fiedler(dfb_body, url=proposal.DFB_URL,
                                   name=name, birth_date=dob)


@pytest.mark.parametrize("fault", ["nation", "duplicate", "name", "dob"])
def test_dfb_literal_rows_are_exact_and_unique(dfb_body, fault):
    body = dfb_body
    if fault == "nation":
        body = body.replace(b"<td>Germany</td>", b"<td>Holland</td>", 1)
    elif fault == "duplicate":
        body = body.replace(b"<td>Germany</td>", b"<td>Germany</td><td>Nation:</td><td>Germany</td>", 1)
    elif fault == "name":
        body = body.replace(b"<td>Christian Fiedler</td>", b"<td>Christian Other</td>", 1)
    elif fault == "dob":
        body = body.replace(b"<td>1975-03-27</td>", b"<td>1975-03-28</td>", 1)
    with pytest.raises(ValueError):
        proposal.parse_dfb_fiedler(body, url=proposal.DFB_URL,
            name="Christian Fiedler", birth_date="1975-03-27")


def row_fixture(sb_body, monkeypatch):
    actor = dict(carrier_id=2099, id="player-2099", club_id="club-1",
        name="Jonathan Gould", source_name="Jonathan Gould",
        facts=dict(birth_date="1968-07-18", nationality={"policy":"preserve-existing-mode1"}))
    club = dict(id="club-1", carrier_id=1252, name="Celtic", division="Scottish Premier League")
    source = dict(provider="soccerbase", provider_player_id=2982, url=GOULD_URL,
        path=str(GOULD_PATH.relative_to(ROOT)),
        sha256=hashlib.sha256(sb_body).hexdigest(),
        recipe_before_nationality=copy.deepcopy(actor["facts"]["nationality"]))
    receipt_path = str(GOULD_PATH.with_suffix(GOULD_PATH.suffix + ".source.json").relative_to(ROOT))
    from scripts import season_release_registry_v1 as registry
    receipt_file = ROOT / receipt_path
    receipt = dict(url=GOULD_URL, sha256=source["sha256"])
    result = proposal.prepare_row(season="2000-01", club=club, actor=actor,
        source=source, body=sb_body, receipt=receipt, native_name="Jonathan Gould",
        receipt_path=receipt_path, receipt_sha256="a" * 64,
        native_birth_date="1968-07-18", native_country="NORWAY", owners={1252},
        recipe_before_nationality=copy.deepcopy(actor["facts"]["nationality"]),
        expected_owner=1252, record_offset=32, file_offset=400, native_byte_before=7,
        country_codes={"NORWAY":7, "SCO":12})
    return result, actor, club, source, receipt


def test_one_row_is_explicit_recipe_native_and_exclusive_owner_mask(sb_body, monkeypatch):
    value, _, _, _, _ = row_fixture(sb_body, monkeypatch)
    proposal.validate_row(value)
    assert value["field_mask"] == ["nationality"]
    assert value["native_mask"] == dict(file="DBDAT/JUG98030.FDI", record_offset=32,
        file_offset=400, before=7, after=12)
    assert "membership_witness" not in value
    assert value["source_identity"]["target_season_ownership_claimed"] is False


@pytest.mark.parametrize("fault", ["no_op", "wrong_dob", "duplicate_owner", "bad_receipt",
                                    "bad_source_hash", "recipe_before", "native_before", "extra_mask"])
def test_known_wrong_writer_rejects_unsafe_preimages(sb_body, monkeypatch, fault):
    value, actor, club, source, receipt = row_fixture(sb_body, monkeypatch)
    args = dict(season="2000-01", club=club, actor=actor, source=source, body=sb_body,
        receipt=receipt, native_name="Jonathan Gould", native_birth_date="1968-07-18",
        receipt_path=str(GOULD_PATH.with_suffix(GOULD_PATH.suffix + ".source.json").relative_to(ROOT)),
        receipt_sha256="a" * 64,
        native_country="NORWAY", recipe_before_nationality=copy.deepcopy(actor["facts"]["nationality"]),
        owners={1252}, expected_owner=1252, record_offset=32,
        file_offset=400, native_byte_before=7, country_codes={"NORWAY":7, "SCO":12})
    if fault == "no_op":
        args.update(native_country="SCO", native_byte_before=12,
                    country_codes={"SCO":12})
    elif fault == "wrong_dob":
        args["native_birth_date"] = "1968-07-19"
    elif fault == "duplicate_owner":
        args["owners"] = {1252, 1253}
    elif fault == "bad_receipt":
        args["receipt"] = dict(url="https://wrong.test/profile", sha256=receipt["sha256"])
    elif fault == "bad_source_hash":
        args["source"] = dict(source, sha256="0"*64)
    elif fault == "recipe_before":
        args["recipe_before_nationality"] = "NOR"
    elif fault == "native_before":
        args["native_byte_before"] = 8
    with pytest.raises(ValueError):
        candidate = proposal.prepare_row(**args)
        if fault == "extra_mask":
            candidate["native_mask"]["rating_offset"] = 999
        proposal.validate_row(candidate)


def test_country_result_does_not_claim_historical_membership(sb_body, monkeypatch):
    value, *_ = row_fixture(sb_body, monkeypatch)
    assert "membership_witness" not in value
    assert value["source_identity"]["target_season_ownership_claimed"] is False


def test_existing_changes_bind_apply_authenticates_and_changes_exact_two_bytes(tmp_path, monkeypatch, local_registered_sample):
    if not (SAMPLE_INPUT.is_file() and GOULD_PATH.is_file() and DFB_PATH.is_file()):
        pytest.skip("retained local original captures and registered r178 sample are unavailable")
    from scripts import season_release_registry_v1 as registry
    from scripts import season_pipeline_v2 as pipeline
    writer = production_writer(tmp_path, monkeypatch)
    base = registry.load_registered_release("2000-01", "sourced-original-keeper-roles-20261023-r178a")
    plan = writer.prepare(base, SAMPLE_INPUT)
    assert [row["carrier_id"] for row in plan["updates"]] == [2099, 13196]
    assert [row["nationality"] for row in plan["updates"]] == ["SCO", "GER"]
    jug_path = base.game_path / "DBDAT/JUG98030.FDI"
    eq_path = base.game_path / "DBDAT/EQ98030.FDI"
    before, eq = jug_path.read_bytes(), eq_path.read_bytes()
    package = pipeline.read_json_file(base.package_path)
    bound = writer.bind(package, plan)
    for row in plan["updates"]:
        original = next(p for p in package["players"] if p["carrier_id"] == row["carrier_id"])
        changed = next(p for p in bound["players"] if p["carrier_id"] == row["carrier_id"])
        assert changed["facts"]["nationality"] == row["nationality"]
        original["facts"]["nationality"] = row["nationality"]
        original["fact_fallbacks"] = [f for f in original.get("fact_fallbacks", [])
            if f["field"] != "nationality"]
        assert changed == original
    after, after_eq = writer.apply(before, eq, plan)
    assert after_eq == eq
    expected_offsets = {row["native_mask"]["file_offset"] for row in plan["updates"]}
    assert {i for i, (a, b) in enumerate(zip(before, after)) if a != b} == expected_offsets
    assert all(row["source"]["path"] and row["source_receipt"]["path"]
               for row in plan["updates"])
    # The existing writer's exact whole-postimage path is idempotent.
    assert writer.apply(after, eq, plan) == (after, eq)


@pytest.mark.parametrize("tamper", ["adjacent_offset", "carrier", "source_country"])
def test_existing_apply_rejects_tampered_prepared_plan(tmp_path, monkeypatch, tamper, local_registered_sample):
    from scripts import season_release_registry_v1 as registry
    writer = production_writer(tmp_path, monkeypatch)
    base = registry.load_registered_release("2000-01", "sourced-original-keeper-roles-20261023-r178a")
    plan = writer.prepare(base, SAMPLE_INPUT)
    row = plan["updates"][0]
    jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    if tamper == "adjacent_offset":
        mask = row["native_mask"]
        offset = mask["file_offset"] + 1
        row["native_mask"]["file_offset"] = offset
        row["native_mask"]["before"] = jug[offset]
        row["native_mask"]["after"] = jug[offset] ^ 1
    elif tamper == "carrier":
        row["carrier_id"] = 2098
    else:
        row["nationality"] = "ENG"
        row["source_identity"]["nationality"] = "ENG"
    with pytest.raises(ValueError):
        writer.apply(jug, eq, plan)


def test_existing_apply_rejects_arbitrary_native_preimage(tmp_path, monkeypatch, local_registered_sample):
    from scripts import season_release_registry_v1 as registry
    writer = production_writer(tmp_path, monkeypatch)
    base = registry.load_registered_release("2000-01", "sourced-original-keeper-roles-20261023-r178a")
    plan = writer.prepare(base, SAMPLE_INPUT)
    jug = bytearray((base.game_path / "DBDAT/JUG98030.FDI").read_bytes())
    eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    jug[100] ^= 1
    with pytest.raises(ValueError):
        writer.apply(bytes(jug), eq, plan)


@pytest.mark.parametrize("source_path", [str(GOULD_PATH), "../outside/soccerbase-gould-2982.html"])
def test_prepare_rejects_nonrelative_or_escaping_profile_paths(tmp_path, monkeypatch, source_path, local_registered_sample):
    from scripts import season_release_registry_v1 as registry
    writer = production_writer(tmp_path, monkeypatch)
    base = registry.load_registered_release("2000-01", "sourced-original-keeper-roles-20261023-r178a")
    request = json.loads(SAMPLE_INPUT.read_text())
    request["changes"][0]["source"]["path"] = source_path
    with pytest.raises(ValueError):
        proposal.prepare(base, SAMPLE_INPUT, request=request)


def test_real_plan_has_portable_body_and_receipt_bindings(tmp_path, monkeypatch, local_registered_sample):
    if not (SAMPLE_INPUT.is_file() and GOULD_PATH.is_file() and DFB_PATH.is_file()):
        pytest.skip("retained local original captures and registered r178 sample are unavailable")
    from scripts import season_release_registry_v1 as registry
    writer = production_writer(tmp_path, monkeypatch)
    base = registry.load_registered_release("2000-01", "sourced-original-keeper-roles-20261023-r178a")
    plan = writer.prepare(base, SAMPLE_INPUT)
    for row in plan["updates"]:
        assert registry.sha256_file(ROOT / row["source"]["path"]) == row["source"]["sha256"]
        assert registry.sha256_file(ROOT / row["source_receipt"]["path"]) == row["source_receipt"]["sha256"]
