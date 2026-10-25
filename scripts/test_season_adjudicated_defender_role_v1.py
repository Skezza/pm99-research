"""Editorial defender projection metadata and parent replay-cache negatives."""
import copy
import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import season_dated_parent_facts_editorial_role_v1 as role


def _fischer_identity():
    selector={"club_name":"FC Zürich","country_catalog":"switzerland","competition_catalog":"superl","source_path":"squad/2000/C1/260.html","source_sha256":"a"*64}
    row={"source_row_sha256":"b"*64,"source_row_index":8,"facts":{"name":"Urs Fischer","position":"D","birth_date":None}}
    annual={"source_row_sha256":"b"*64,"source_row_index":8,"season":"2000-01","club_id":"club-1111","selector":selector}
    witness={"identity_policy":"annual-source-row-person-identity-null-dob-v1","full_name":"Urs Fischer","person_id":"person-source-unit-case","values":{"birth_date":"1966-02-20","nationality":"SUI"},"annual_identity":annual,"official_career_contexts":[{"url":"https://www.uefa.com/example/history","sha256":"c"*64,"body":{"path":"retained-career.html","sha256":"c"*64},"receipt":{"path":"career-receipt.json","sha256":"d"*64}}]}
    return witness,{"selector":selector},row

def _valid_plan():
    role_broad, assigned = "D", 4
    masks = [dict(file="DBDAT/JUG98030.FDI", record_offset=i, file_offset=100 + i,
                  before=15 if i == 0 else 98, after=assigned if i == 0 else 98)
             for i in range(6)]
    update = {
        "carrier_id": 14454, "field_mask": ["fine_roles"], "values": {"fine_roles": [assigned]},
        "native_masks": masks, "before_native_roles": [15, 98, 98, 98, 98, 98],
        "after_native_roles": [assigned, 98, 98, 98, 98, 98], "expected_owner": 777,
        "evidence": {"dated_role_evidence": {"published_broad_role": role_broad}},
    }
    return {"schema": role.SCHEMA, "kind": role.KIND, "updates": [update]}


def test_null_dob_official_career_context_accepts_exact_person_and_broad_d():
    witness, club, row = _fischer_identity()
    actor = {"source_name": "Urs Fischer", "person_id": witness["person_id"],
             "club_id": witness["annual_identity"]["club_id"],
             "facts": {"birth_date": witness["values"]["birth_date"]}}
    fact_update = {"values": {"birth_date": "1966-02-20"}}
    evidence = role._official_annual_role_context(witness, row, club, actor, fact_update,
                                                 witness["annual_identity"]["source_row_sha256"], "2000-01")
    assert evidence["source_birth_date"] is None
    assert evidence["corrected_parent_birth_date"] == "1966-02-20"
    assert evidence["published_broad_role"] == "D"
    assert evidence["fine_role_status"] == "editorial-compatible-default-not-published-source-fact"


@pytest.mark.parametrize("mutation", ["wrong_person", "non_official", "annual_dob_present"])
def test_null_dob_role_branch_rejects_wrong_identity_nonofficial_or_non_null_row(mutation):
    witness, club, row = _fischer_identity()
    witness, club, row = copy.deepcopy(witness), copy.deepcopy(club), copy.deepcopy(row)
    actor = {"source_name": "Urs Fischer", "person_id": witness["person_id"],
             "club_id": witness["annual_identity"]["club_id"],
             "facts": {"birth_date": "1966-02-20"}}
    if mutation == "wrong_person":
        actor["person_id"] = "person-source-wrong"
    elif mutation == "non_official":
        witness["official_career_contexts"][0]["url"] = "https://example.org/urs-fischer"
    else:
        row["facts"]["birth_date"] = "1966-02-20"
    with pytest.raises(ValueError):
        role._official_annual_role_context(witness, row, club, actor,
                                           {"values": {"birth_date": "1966-02-20"}},
                                           witness["annual_identity"]["source_row_sha256"], "2000-01")


def test_d_role_owner_must_be_exclusive(monkeypatch):
    monkeypatch.setattr(role, "native_owners", lambda _eq: {14454: {777}})
    assert role._exclusive_owner(b"in-memory-eq", 14454, 777)
    assert not role._exclusive_owner(b"in-memory-eq", 14454, 778)
    monkeypatch.setattr(role, "native_owners", lambda _eq: {14454: {777, 778}})
    assert not role._exclusive_owner(b"in-memory-eq", 14454, 777)


def test_d_role_mask_rejects_compatible_inherited_role_and_extra_native_byte():
    plan = _valid_plan()
    role.validate_mask(plan)
    compatible_inherited = copy.deepcopy(plan)
    compatible_inherited["updates"][0]["before_native_roles"][0] = 4
    with pytest.raises(ValueError, match="compatibility"):
        role.validate_mask(compatible_inherited)

    before = bytes(range(32))
    after = bytearray(before)
    after[100 % len(after)] ^= 1
    with pytest.raises(ValueError, match="outside the exact six-role field mask"):
        role._assert_role_byte_mask(before, bytes(after), plan["updates"][0]["native_masks"])


def test_existing_midfield_default_and_plan_validation_remain_m_to_9():
    assert role.EDITORIAL_ROLE_BY_BROAD["M"] == 9
    old_plan = _valid_plan()
    update = old_plan["updates"][0]
    update["evidence"]["dated_role_evidence"]["published_broad_role"] = "M"
    update["values"] = {"fine_roles": [9]}
    update["after_native_roles"] = [9, 98, 98, 98, 98, 98]
    update["native_masks"][0]["after"] = 9
    role.validate_mask(old_plan)
    assert update["values"] == {"fine_roles": [9]}


def test_fact_parent_warm_replay_rejects_same_content_symlink(monkeypatch, tmp_path):
    monkeypatch.setattr(role.registry, "ROOT", tmp_path)
    from scripts import season_package_v2 as packages

    with tempfile.TemporaryDirectory(dir=tmp_path) as temp_dir:
        root = Path(temp_dir)
        source = root / "nested-source.json"
        source_copy = root / "nested-source-copy.json"
        source_bytes = b'{"retained":"same bytes"}'
        source.write_bytes(source_bytes)
        source_copy.write_bytes(source_bytes)
        source_binding = {"path": source.resolve().relative_to(role.registry.ROOT.resolve()).as_posix(),
                          "sha256": hashlib.sha256(source_bytes).hexdigest()}

        fact_plan_path = root / "fact-plan.json"
        fact_plan = {"season": "2000-01", "release_id": "fact-parent",
                     "nested_evidence": source_binding}
        fact_plan_path.write_text(json.dumps(fact_plan, sort_keys=True))
        fact_plan_binding = {"path": fact_plan_path.resolve().relative_to(role.registry.ROOT.resolve()).as_posix(),
                             "sha256": hashlib.sha256(fact_plan_path.read_bytes()).hexdigest()}
        locator = root / "locator.json"
        locator.write_text(json.dumps({"sourced_profile_assignment_plan_path": fact_plan_binding["path"]}))

        package_data = {"players": [], "clubs": [], "artifacts": [], "proofs": []}
        package = root / "package.json"
        package.write_text(json.dumps(package_data, sort_keys=True))
        manifest = root / "manifest.json"
        manifest.write_text("{}")
        fact_game = root / "fact-game" / "DBDAT"
        base_game = root / "base-game" / "DBDAT"
        fact_game.mkdir(parents=True)
        base_game.mkdir(parents=True)
        (fact_game / "JUG98030.FDI").write_bytes(b"fact-jug")
        (fact_game / "EQ98030.FDI").write_bytes(b"fact-eq")
        post_jug, post_eq = b"corrected-jug", b"corrected-eq"
        (base_game / "JUG98030.FDI").write_bytes(post_jug)
        (base_game / "EQ98030.FDI").write_bytes(post_eq)
        base = SimpleNamespace(season="2000-01", release_id="role-child", package_path=package,
                               release_manifest_path=manifest, game_path=base_game.parent)
        fact_base = SimpleNamespace(season="2000-01", release_id="fact-parent", package_path=package,
                                    release_manifest_path=manifest, game_path=fact_game.parent)
        request = {"adjudicated_facts_plan": fact_plan_binding}
        replay_calls = {"verify": 0, "bind": 0, "apply": 0}
        code_signature = {"value": "code-v1"}

        monkeypatch.setattr(role.registry, "locator_path", lambda *_args: locator)
        monkeypatch.setattr(role.registry, "load_registered_release", lambda *_args: fact_base)
        monkeypatch.setattr(role, "_verification_code_fingerprints",
                            lambda: (("test-verifier", code_signature["value"]),))

        def verify(_base, _plan):
            replay_calls["verify"] += 1

        def bind(_package, _plan):
            replay_calls["bind"] += 1
            return package_data

        def apply(_jug, _eq, _plan):
            replay_calls["apply"] += 1
            return post_jug, post_eq

        monkeypatch.setattr(role.common, "verify", verify)
        monkeypatch.setattr(role.common, "bind", bind)
        monkeypatch.setattr(role.common, "apply", apply)
        role._FACT_REPLAY_CACHE.clear()

        role._verify_fact_parent(base, request)
        assert replay_calls == {"verify": 1, "bind": 1, "apply": 1}
        role._verify_fact_parent(base, request)
        assert replay_calls == {"verify": 1, "bind": 1, "apply": 1}

        code_signature["value"] = "code-v2"
        role._verify_fact_parent(base, request)
        assert replay_calls == {"verify": 2, "bind": 2, "apply": 2}

        source.write_bytes(b'{"retained":"tampered"}')
        with pytest.raises(ValueError, match="source binding changed"):
            role._verify_fact_parent(base, request)
        assert replay_calls == {"verify": 2, "bind": 2, "apply": 2}

        source.write_bytes(source_bytes)
        role._verify_fact_parent(base, request)
        assert replay_calls == {"verify": 2, "bind": 2, "apply": 2}

        source.unlink()
        source.symlink_to(source_copy)
        with pytest.raises(ValueError, match="retained workspace file"):
            role._verify_fact_parent(base, request)
        assert replay_calls == {"verify": 2, "bind": 2, "apply": 2}


@pytest.mark.parametrize("factory_broad,target_broad,roles,null_identity,expected", [
    ("M", "D", [15, 98, 98, 98, 98, 98], True, True),
    ("M", "D", [15, 98, 98, 98, 98, 98], False, False),
    ("D", "M", [15, 98, 98, 98, 98, 98], False, False),
    ("D", "M", [15, 98, 98, 98, 98, 98], True, False),
    ("D", "M", [4, 98, 98, 98, 98, 98], False, True),
    ("D", "D", [15, 98, 98, 98, 98, 98], True, False),
    ("M", "D", [], True, False),
])
def test_factory_seed_exception_is_only_for_verified_null_dob_defender(
        factory_broad, target_broad, roles, null_identity, expected):
    assert role._factory_role_seed_guard_ok(
        "Jerren NIXON", "Urs Fischer", factory_broad, target_broad,
        roles, null_identity) is expected
    assert not role._factory_role_seed_guard_ok(
        "Urs FISCHER", "Urs Fischer", factory_broad, target_broad,
        roles, null_identity)


def test_real_corrected_fischer_parent_has_an_incompatible_factory_seed():
    season = "2000-01"
    release_id = "sourced-fischer-official-facts-20261025-r286a"
    if not role.registry.locator_path(season, release_id).is_file():
        pytest.skip("local registered game corpus unavailable")
    base = role.registry.load_registered_release(season, release_id)
    jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    entry = next(e for e in role.IndexedFDIFile.from_bytes(jug).entries
                 if e.record_id == 14454)
    current = role.native_player(entry.decode_payload(jug), 14454)
    factory = role._factory_roles(14454)
    assert current["position"] == "D"
    assert current["roles"] == factory[4] == [15, 98, 98, 98, 98, 98]
    assert factory[6]["position"] == "M"
    assert not role.compatible("M", 15)
    assert role._exclusive_owner(eq, 14454, 1111)
    assert role.native_facts(jug, 14454)["birth_date"] == "1966-02-20"
    assert role._factory_role_seed_guard_ok(
        factory[5]["name"], "Urs Fischer", "M", "D", factory[4], True)
