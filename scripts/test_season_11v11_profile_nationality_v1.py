import copy
from pathlib import Path

import pytest

from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_source_verified_player_changes_v1 as common
from scripts import season_11v11_profile_nationality_v1 as elevenv


HERE = (Path(__file__).resolve().parents[1] / ".local/consolidated-audit-20261009/"
        "parallel-rc-20261023/resume-qa/ostenstad-nationality-v3")


def _base_and_input(season):
    release = {
        "2000-01": "sourced-berkovic-ostenstad-etuhu-20261024-r222a",
        "2002-03": "sourced-keeper-profile-countries-20261023-r183a",
    }[season]
    input_path = HERE / f"egil-norway-input-{season}-v2.json"
    locator = registry.locator_path(season, release)
    if not input_path.is_file() or not locator.is_file():
        pytest.skip("retained local source fixture/release is unavailable")
    return registry.load_registered_release(season, release), input_path


@pytest.mark.parametrize("season", ["2000-01", "2002-03"])
def test_11v11_uses_common_plan_bind_apply_and_native_contract(season):
    base, input_path = _base_and_input(season)
    plan = common.prepare(base, input_path)
    common.verify(base, plan)
    common.validate_mask(plan)
    assert plan["source_policy"].startswith("11v11-exact-numeric-profile")
    assert plan["updates"][0]["source_identity"]["nationality"] == "NOR"

    before = pipeline.read_json_file(base.package_path)
    after = common.bind(before, plan)
    old_players = {row["carrier_id"]: row for row in before["players"]}
    new_players = {row["carrier_id"]: row for row in after["players"]}
    changed = {key for key in old_players if old_players[key] != new_players[key]}
    assert changed == {plan["updates"][0]["carrier_id"]}
    carrier = plan["updates"][0]["carrier_id"]
    assert new_players[carrier]["facts"]["nationality"] == "NOR"
    assert new_players[carrier]["facts"]["birth_date"] == old_players[carrier]["facts"]["birth_date"]
    assert new_players[carrier]["ratings"] == old_players[carrier]["ratings"]
    # The common binder owns the canonical artifact shape; the provider adapter
    # must not add a parallel source/proof representation.
    assert after["sources"] == before["sources"]
    assert after["proofs"] == before["proofs"]
    aid = common.artifact_id(plan)
    artifact = next(row for row in after["artifacts"] if row["id"] == aid)
    assert artifact["sha256"] == common.digest(packages.canonical_json_bytes(plan))

    jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    post, post_eq = common.apply(jug, eq, plan)
    assert post_eq == eq
    assert {i for i, (a, b) in enumerate(zip(jug, post)) if a != b} == {
        plan["updates"][0]["native_mask"]["file_offset"]}
    assert common.apply(post, eq, plan) == (post, eq)


def test_11v11_plan_tampering_is_rejected_by_common_verify():
    base, input_path = _base_and_input("2000-01")
    plan = common.prepare(base, input_path)
    changed = copy.deepcopy(plan)
    changed["updates"][0]["nationality"] = "SWE"
    with pytest.raises(ValueError):
        common.verify(base, changed)


def test_11v11_parser_rejects_wrong_full_name_dob_birthplace_and_profile_id():
    base, input_path = _base_and_input("2000-01")
    request = pipeline.read_json_file(input_path)["changes"][0]
    source = request["source"]
    body_path = registry.ROOT / source["path"]
    raw = body_path.read_bytes()
    with pytest.raises(ValueError, match="exact full name"):
        elevenv.parse_profile(raw, source, full_name="Egil Othername",
            birth_date="1972-01-02", requested_country="NOR")
    with pytest.raises(ValueError, match="exact DOB"):
        elevenv.parse_profile(raw, source, full_name="Egil Ostenstad",
            birth_date="1972-02-01", requested_country="NOR")
    altered = raw.replace(b"<b>Nationality</b>", b"<b>Place of birth</b>", 1)
    with pytest.raises(ValueError, match="explicit Nationality"):
        elevenv.parse_profile(altered, source, full_name="Egil Ostenstad",
            birth_date="1972-01-02", requested_country="NOR")
    bad_source = copy.deepcopy(source)
    bad_source["provider_player_id"] += 1
    with pytest.raises(ValueError, match="canonical player URL/ID"):
        elevenv._capture(bad_source)
