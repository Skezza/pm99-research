from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from scripts import season_dated_parent_facts_editorial_role_v1 as dated

import pytest

from scripts import season_release_registry_v1 as registry
from scripts.season_dated_parent_facts_editorial_role_v1 import (
    _one_source_row,
    _read_json_binding,
    _source_dependency_fingerprints,
    _replay_dependency_key,
    _verify_dated_lineup_pair,
)

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/seedorf-visible-identity-correction-v1/dated-parent-facts-editorial-role-v1'


def _request() -> dict:
    source = ROOT / "2012-editorial-role-input-v3.json"
    if not source.is_file():
        pytest.skip("retained dated-role corpus request unavailable")
    return json.loads(source.read_text())


def test_actual_retained_lineup_pair_uses_typed_identity_and_date_fields():
    request = _request()
    _, fact_plan = _read_json_binding(request["adjudicated_facts_plan"])
    update = next(row for row in fact_plan["updates"] if row["carrier_id"] == 16905)
    witness = update["witness"]
    _, allocation = _read_json_binding(witness["historical_identity"]["preallocation"])
    club, row = _one_source_row(allocation, request["changes"][0]["source_row_sha256"])
    parsed = _verify_dated_lineup_pair(request, row, club, 4168, "2012-13")
    assert parsed["date"] == request["dated_lineup_evidence"]["date"]
    assert parsed["provider_player_id"] == 4168
    assert parsed["published_broad_role"] == "M"
    assert parsed["fine_role_status"] == "editorial-compatible-default-not-published-source-fact"


def _synthetic_case(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(registry, "ROOT", tmp_path)
    source_dir = tmp_path / "synthetic-second-person-fixture"
    source_dir.mkdir(exist_ok=True)
    fact_path = source_dir / "fact-plan.json"
    fact = {"updates": [{"carrier_id": 29, "witness": {
        "historical_identity": {"match": {"provider_club_id": 42}}}}]}
    fact_path.write_text(json.dumps(fact))
    folha_path = source_dir / "folha-fixture.html"
    folha_path.write_text("""<!doctype html><html><head><title>Folha - Rovers x Town</title></head><body>
    <p>01/08/1999 Rovers 1 X 0 Town</p>
    <p>Rovers Técnico: Coach One 8. Example Town Técnico: Coach Two</p>
    </body></html>""")
    ge_path = source_dir / "ge-fixture.html"
    ge_path.write_text("""<!doctype html><html><head><title>Rovers x Town - friendly</title></head><body>
    <p>01/08/1999 Rovers and Town met in a friendly.</p>
    <p>Example directed play through the meio-campo for Rovers.</p>
    </body></html>""")
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    request = {
        "changes": [{"carrier_id": 29}],
        "adjudicated_facts_plan": {"path": registry.relative_workspace_path(fact_path), "sha256": sha(fact_path)},
        "dated_lineup_evidence": {
            "date": "1999-08-01", "season": "1999-00", "club_name": "Rovers United",
            "provider_club_id": 42, "selector_source_path": "squad/1999/ENG2/42.html",
            "selector_source_sha256": "a" * 64, "club_source_label": "Rovers",
            "opponent_name": "North Town", "opponent_source_label": "Town",
            "player_full_name": "Alva Example", "provider_player_id": 700,
            "shirt_number": 8, "lineup_label": "Example", "side": "home",
            "home_score": 1, "away_score": 0,
            "folha": {"path": registry.relative_workspace_path(folha_path), "sha256": sha(folha_path),
                      "url": "https://aovivo.folha.uol.com.br/1999/08/01/fixture.shtml"},
            "globo": {"path": registry.relative_workspace_path(ge_path), "sha256": sha(ge_path),
                      "url": "https://ge.globo.com/jogo/cup/01-08-1999/rovers-town.html"},
        },
    }
    annual_club = {"selector": {"club_name": "Rovers United",
        "source_path": "squad/1999/ENG2/42.html", "source_sha256": "a" * 64}}
    annual_row = {"source_row_sha256": "b" * 64, "opening_source_player_id": "700",
        "facts": {"name": "Alva Example", "position": "M", "shirt_number": 8}}
    return request, annual_row, annual_club, source_dir


def test_synthetic_second_person_and_year_pass_generic_policy(tmp_path, monkeypatch):
    request, row, club, source_dir = _synthetic_case(tmp_path, monkeypatch)
    parsed = _verify_dated_lineup_pair(request, row, club, 700, "1999-00")
    assert parsed["date"] == "1999-08-01"
    assert parsed["provider_player_id"] == 700
    assert parsed["club_name"] == "Rovers United"
    assert parsed["published_broad_role"] == "M"
    for path in source_dir.iterdir():
        path.unlink()
    source_dir.rmdir()


def test_synthetic_wrong_date_club_player_and_opponent_scope_reject(tmp_path, monkeypatch):
    request, row, club, source_dir = _synthetic_case(tmp_path, monkeypatch)
    try:
        mutations = []
        for field, value in (("date", "2000-08-01"), ("season", "2000-01"),
                             ("club_name", "Elsewhere"), ("provider_club_id", 43),
                             ("provider_player_id", 701), ("opponent_source_label", "Elsewhere"),
                             ("side", "away")):
            bad = copy.deepcopy(request)
            bad["dated_lineup_evidence"][field] = value
            mutations.append(bad)
        for bad in mutations:
            with pytest.raises(ValueError):
                _verify_dated_lineup_pair(bad, row, club, 700, "1999-00")
        bad_row = copy.deepcopy(row)
        bad_row["opening_source_player_id"] = "701"
        with pytest.raises(ValueError):
            _verify_dated_lineup_pair(request, bad_row, club, 700, "1999-00")
        folha_path = source_dir / "folha-fixture.html"
        original = folha_path.read_bytes()
        sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        for old_text, new_text in ((b"01/08/1999", b"02/08/1999"),
                                   (b"8. Example", b"8. Stranger")):
            folha_path.write_bytes(original.replace(old_text, new_text))
            bad_body = copy.deepcopy(request)
            bad_body["dated_lineup_evidence"]["folha"]["sha256"] = sha(folha_path)
            with pytest.raises(ValueError):
                _verify_dated_lineup_pair(bad_body, row, club, 700, "1999-00")
        folha_path.write_bytes(original)
    finally:
        for path in source_dir.iterdir():
            path.unlink()
        source_dir.rmdir()


def test_warm_cache_source_binding_rehash_rejects_changed_body(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ROOT", tmp_path)
    body = tmp_path / "warm-cache-source-body.bin"
    body.write_bytes(b"captured source v1")
    sha = lambda: hashlib.sha256(body.read_bytes()).hexdigest()
    binding_tree = {"official_source": {"path": registry.relative_workspace_path(body), "sha256": sha()}}
    first = _source_dependency_fingerprints(binding_tree)
    assert first == ((registry.relative_workspace_path(body), sha()),)
    warmed_cache = {_replay_dependency_key(binding_tree)}
    assert len(warmed_cache) == 1
    body.write_bytes(b"tampered source v2")
    with pytest.raises(ValueError, match="nested adjudicated-facts source binding changed"):
        changed_key = _replay_dependency_key(binding_tree)
        assert changed_key in warmed_cache
    body.unlink()


def test_code_fingerprint_change_does_not_change_semantic_plan_or_transaction(monkeypatch):
    from scripts import season_dated_parent_facts_editorial_role_v1 as candidate
    from scripts import season_pipeline_v2 as pipeline
    from scripts import season_source_verified_player_changes_v1 as common
    request_path = ROOT / "2012-editorial-role-input-v3.json"
    if not request_path.is_file():
        pytest.skip("retained r273 source parent is unavailable in this clone")
    request = json.loads(request_path.read_text())
    base = registry.load_registered_release(request["season"], request["release_id"])
    current_package = pipeline.read_json_file(base.package_path)
    jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()

    # This regression does not retest official-source interpretation. The
    # existing v2 proof already covers that expensive full replay. Keep source
    # binding checks, identity parsers, role preimage and native checks real.
    monkeypatch.setattr(common, "verify", lambda _base, _plan: None)
    monkeypatch.setattr(common, "bind", lambda _package, _plan: copy.deepcopy(current_package))
    monkeypatch.setattr(common, "apply", lambda _jug, _eq, _plan: (jug, eq))
    candidate._FACT_REPLAY_CACHE.clear()

    first = candidate.prepare(base, request_path)
    original = candidate._verification_code_fingerprints
    changed = original() + (("test-only-unrelated-runtime-module", "f" * 64),)
    monkeypatch.setattr(candidate, "_verification_code_fingerprints", lambda: changed)
    second = candidate.prepare(base, request_path)

    assert first == second
    assert first["transaction_id"] == second["transaction_id"]
    assert "code_bindings" not in first.get("fact_replay_dependencies", {})
    assert "implementation_sha256" not in first



def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fake_fact_parent(tmp_path: Path, monkeypatch):
    """A disposable parent fixture so _verify_fact_parent cache paths are real."""
    monkeypatch.setattr(registry, "ROOT", tmp_path)
    game = tmp_path / "current-game"
    fact_game = tmp_path / "fact-game"
    for folder in (game, fact_game):
        (folder / "DBDAT").mkdir(parents=True)
        (folder / "DBDAT/JUG98030.FDI").write_bytes(b"jug-exact")
        (folder / "DBDAT/EQ98030.FDI").write_bytes(b"eq-exact")
    parent_package = tmp_path / "current-package.json"
    fact_package = tmp_path / "fact-package.json"
    parent_package.write_bytes(b"package-exact")
    fact_package.write_bytes(b"package-exact")
    parent_manifest = tmp_path / "current-manifest.json"
    fact_manifest = tmp_path / "fact-manifest.json"
    parent_manifest.write_bytes(b"manifest-current")
    fact_manifest.write_bytes(b"manifest-facts")
    fact_plan_path = tmp_path / "fact-plan.json"
    fact_plan_path.write_text("{}\n")
    source_path = tmp_path / "dated-source.html"
    source_path.write_bytes(b"retained source body v1")
    source_rel = registry.relative_workspace_path(source_path)
    fact_plan = {"season": "1999-00", "release_id": "facts-parent", "evidence": {
        "body": {"path": source_rel, "sha256": _sha(source_path)}}}
    parent = SimpleNamespace(season="1999-00", release_id="role-parent", game_path=game,
        package_path=parent_package, release_manifest_path=parent_manifest)
    fact_base = SimpleNamespace(season="1999-00", release_id="facts-parent", game_path=fact_game,
        package_path=fact_package, release_manifest_path=fact_manifest)
    locator = tmp_path / "locator.json"
    locator.write_text(json.dumps({"sourced_profile_assignment_plan_path": registry.relative_workspace_path(fact_plan_path)}))

    real_read = dated.pipeline.read_json_file
    def fake_read(path):
        path = Path(path)
        if path == locator:
            return json.loads(locator.read_text())
        if path in (parent_package, fact_package):
            return {"players": [{"carrier_id": 7}]}
        return real_read(path)

    monkeypatch.setattr(dated.registry, "locator_path", lambda season, release_id: locator)
    monkeypatch.setattr(dated.registry, "load_registered_release", lambda season, release_id: fact_base)
    monkeypatch.setattr(dated.pipeline, "read_json_file", fake_read)
    monkeypatch.setattr(dated, "_read_json_binding", lambda binding: (fact_plan_path, fact_plan))
    return parent, fact_base, fact_plan_path, fact_plan, source_path


def test_verify_fact_parent_warms_hits_and_invalidates_for_code_or_source(tmp_path, monkeypatch):
    parent, fact_base, plan_path, fact_plan, source_path = _fake_fact_parent(tmp_path, monkeypatch)
    dated._FACT_REPLAY_CACHE.clear()
    state = {"code_fingerprint": "candidate-v1", "verify": 0, "bind": 0, "apply": 0}
    monkeypatch.setattr(dated, "_verification_code_fingerprints",
        lambda: (("synthetic-verifier", state["code_fingerprint"]),))
    monkeypatch.setattr(dated.common, "verify", lambda base, plan: state.__setitem__("verify", state["verify"] + 1))
    monkeypatch.setattr(dated.common, "bind", lambda package, plan: state.__setitem__("bind", state["bind"] + 1) or package)
    def fake_apply(jug, eq, plan):
        state["apply"] += 1
        return jug, eq
    monkeypatch.setattr(dated.common, "apply", fake_apply)
    request = {"adjudicated_facts_plan": {"path": registry.relative_workspace_path(plan_path), "sha256": _sha(plan_path)}}
    try:
        dated._verify_fact_parent(parent, request)
        assert state == {"code_fingerprint": "candidate-v1", "verify": 1, "bind": 1, "apply": 1}

        # Same source and code fingerprint must hit the actual module cache.
        dated._verify_fact_parent(parent, request)
        assert state == {"code_fingerprint": "candidate-v1", "verify": 1, "bind": 1, "apply": 1}

        # A changed verifier fingerprint must miss the warm cache and replay.
        state["code_fingerprint"] = "candidate-v2"
        dated._verify_fact_parent(parent, request)
        assert state == {"code_fingerprint": "candidate-v2", "verify": 2, "bind": 2, "apply": 2}

        # Even though a matching key was warmed, changed nested source bytes reject
        # before cache membership and do not count as another successful replay.
        source_path.write_bytes(b"retained source body tampered")
        with pytest.raises(ValueError, match="nested adjudicated-facts source binding changed"):
            dated._verify_fact_parent(parent, request)
        assert state == {"code_fingerprint": "candidate-v2", "verify": 2, "bind": 2, "apply": 2}
    finally:
        dated._FACT_REPLAY_CACHE.clear()


def test_same_start_year_july_fixture_is_outside_august_target_window(tmp_path, monkeypatch):
    request, row, club, source_dir = _synthetic_case(tmp_path, monkeypatch)
    folha_path = source_dir / "folha-fixture.html"
    ge_path = source_dir / "ge-fixture.html"
    folha_path.write_bytes(folha_path.read_bytes().replace(b"01/08/1999", b"31/07/1999"))
    ge_path.write_bytes(ge_path.read_bytes().replace(b"01/08/1999", b"31/07/1999"))
    evidence = request["dated_lineup_evidence"]
    evidence["date"] = "1999-07-31"
    evidence["folha"]["url"] = "https://aovivo.folha.uol.com.br/1999/07/31/fixture.shtml"
    evidence["globo"]["url"] = "https://ge.globo.com/jogo/cup/31-07-1999/rovers-town.html"
    evidence["folha"]["sha256"] = _sha(folha_path)
    evidence["globo"]["sha256"] = _sha(ge_path)
    try:
        # Start-year membership evidence is scoped to August through December.
        with pytest.raises(ValueError, match="target-season date window"):
            dated._verify_dated_lineup_pair(request, row, club, 700, "1999-00")
    finally:
        for path in source_dir.iterdir():
            path.unlink()
        source_dir.rmdir()
