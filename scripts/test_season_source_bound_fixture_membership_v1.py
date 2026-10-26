"""Actual-parent, memory-only integration tests for the private composition."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "upstream/pm99-skezmod-db-editor")]

from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_release_registry_v1 as registry  # noqa: E402
from scripts import season_source_bound_fixture_membership_v1 as subject  # noqa: E402


QA = ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/opening-xi-west-ham-brentford-2003-first-fixture-v1"
SOURCE_DOC = QA / "first-fixture-native-crossmatch-v3.json"


def _inputs():
    if not SOURCE_DOC.is_file():
        pytest.skip("retained historical source corpus is not available")
    parent = registry.load_registered_release("2003-04", "sourced-official-profile-facts-20261024-r275a")
    main_bytes = parent.package_path.read_bytes()
    main = json.loads(main_bytes)
    overlay_path = parent.package_path.parent / "english-season-package.json"
    overlay = json.loads(overlay_path.read_bytes())
    source_doc = json.loads(SOURCE_DOC.read_bytes())
    eq_path = parent.game_path / "DBDAT/EQ98030.FDI"
    jug_path = parent.game_path / "DBDAT/JUG98030.FDI"
    return parent, main, overlay, source_doc, eq_path.read_bytes(), jug_path.read_bytes(), eq_path, jug_path


_replay_cache = None


def _baseline_replay():
    global _replay_cache
    if _replay_cache is None:
        parent, main, overlay, source_doc, eq, jug, *_ = _inputs()
        _replay_cache = subject.compose_in_memory(parent, main, overlay, eq, jug, source_doc)
    return _replay_cache


def test_actual_parent_composes_both_recipe_layers_eq_owners_and_source_xi_orders_in_memory():
    parent, main, overlay, source_doc, eq, jug, eq_path, jug_path = _inputs()
    main_before = copy.deepcopy(main)
    overlay_before = copy.deepcopy(overlay)
    result = _baseline_replay()

    assert result["state"] == "verified-in-memory-only-no-publication"
    assert [(row["player_record_id"], row["from_club_carrier_id"], row["to_club_carrier_id"])
            for row in result["owner_moves"]] == [(9358, 317, 335), (9264, 314, 353), (9462, 320, 353)]
    outputs = result["outputs"]
    main_after, overlay_after = outputs["main_package"], outputs["english_package"]
    for before, after in ((main_before, main_after), (overlay_before, overlay_after)):
        before_players = {int(row["carrier_id"]): row for row in before["players"]}
        after_players = {int(row["carrier_id"]): row for row in after["players"]}
        for carrier in before_players:
            old, new = before_players[carrier], after_players[carrier]
            if carrier in {9358, 9264, 9462}:
                expected = copy.deepcopy(old)
                expected["club_id"] = new["club_id"]
                assert new == expected
            else:
                assert new == old
        target_expected = {
            353: [9264, 12228, 12442, 12446, 12496, 12523, 12534, 12566, 13007, 9462, 13180],
            335: [9358, 9980, 9983, 9984, 9985, 9986, 9987, 9989, 9992, 9994, 9996],
        }
        by_carrier = {int(row["carrier_id"]): row for row in after["players"]}
        by_club = {int(row["carrier_id"]): row for row in after["clubs"]}
        for cid, expected_carriers in target_expected.items():
            club = by_club[cid]
            expected_ids = [by_carrier[c]["id"] for c in expected_carriers]
            assert club["opening"]["starting_xi_player_ids"] == expected_ids
            assert [slot["player_id"] for slot in club["opening"]["tactics_context"]["slots"]] == expected_ids
    assert _sha(eq_path.read_bytes()) == _sha(eq)
    assert _sha(jug_path.read_bytes()) == _sha(jug)
    assert result["roster_payload_receipt"]["jug_or_recipe_written"] is False


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def test_candidate_is_reconstructed_from_registered_parent_and_owned_plan(tmp_path):
    parent, main, overlay, source_doc, eq, jug, *_ = _inputs()
    replay = _baseline_replay()
    plan_path = tmp_path / "opening-fixture-plan.json"
    plan_path.write_bytes(SOURCE_DOC.read_bytes())
    child_main = copy.deepcopy(replay["outputs"]["main_package"])
    child_main["artifacts"].append({"id": subject.PLAN_ARTIFACT_ID,
        "relative_path": plan_path.name, "sha256": _sha(plan_path.read_bytes())})
    loaded, loaded_path, digest = subject.embedded_source_plan(
        child_main, tmp_path / "candidate-season-package.json")
    assert loaded == source_doc and loaded_path == plan_path and digest == _sha(plan_path.read_bytes())
    receipt = subject.verify_source_candidate(
        parent, main, overlay, eq, jug, child_main, replay["outputs"]["english_package"],
        replay["outputs"]["eq"], replay["outputs"]["jug"], loaded)
    assert receipt["state"] == "verified-exact-parent-source-reconstruction"
    assert receipt["identity_disposition_remains_open"] is True
    assert all(row["status"].startswith("unresolved-confirmed-")
               for row in receipt["unresolved_identity_candidates"])


def test_source_candidate_rejects_native_postimage_drift():
    parent, main, overlay, source_doc, eq, jug, *_ = _inputs()
    replay = _baseline_replay()
    child_main = copy.deepcopy(replay["outputs"]["main_package"])
    child_main["artifacts"].append({"id": subject.PLAN_ARTIFACT_ID,
        "relative_path": "opening-fixture-plan.json", "sha256": _sha(SOURCE_DOC.read_bytes())})
    with pytest.raises(subject.OpeningXICompositionError, match="native postimage"):
        subject.verify_source_candidate(
            parent, main, overlay, eq, jug, child_main, replay["outputs"]["english_package"],
            replay["outputs"]["eq"] + b"\0", replay["outputs"]["jug"], source_doc)


def test_rob_lee_same_dob_row_cannot_be_substituted_for_exact_source_full_name():
    parent, main, overlay, source_doc, eq, jug, *_ = _inputs()
    tampered = copy.deepcopy(source_doc)
    west_ham = next(row for row in tampered["club_crossmatches"] if row["club"] == "West Ham United")
    rob = next(row for row in west_ham["xi"] if row["provider_id"] == "14183")
    assert rob["same_dob_parent_carrier_ids"] == [12523, 13213]
    rob["selected_carrier_id"] = 13213
    with pytest.raises(subject.OpeningXICompositionError, match="selected source actor"):
        subject.compose_in_memory(parent, main, overlay, eq, jug, tampered)


def test_english_overlay_owner_drift_fails_before_postimage_creation():
    parent, main, overlay, source_doc, eq, jug, *_ = _inputs()
    tampered = copy.deepcopy(overlay)
    actor = next(row for row in tampered["players"] if row["carrier_id"] == 9264)
    actor["club_id"] = "english-club-353"
    with pytest.raises(subject.OpeningXICompositionError, match="retained canonical file"):
        subject.compose_in_memory(parent, main, tampered, eq, jug, source_doc)


def test_source_hash_drift_fails_closed():
    parent, main, overlay, source_doc, eq, jug, *_ = _inputs()
    tampered = copy.deepcopy(source_doc)
    key = next(iter(tampered["source_files"]))
    tampered["source_files"][key]["sha256"] = "0" * 64
    with pytest.raises(subject.OpeningXICompositionError, match="source hash changed"):
        subject.compose_in_memory(parent, main, overlay, eq, jug, tampered)


def test_raw_reports_reconstruct_exact_target_team_ids_names_groups_and_surface_date_disagreement():
    parent, main, overlay, source_doc, eq, jug, *_ = _inputs()
    _index, _raw, native_rosters, owners = subject._read_rosters(eq)
    receipts = subject._verify_raw_match_reports(source_doc, main, jug, native_rosters, owners)
    by_id = {row["match_id"]: row for row in receipts}
    assert by_id["2247999"]["published_xi_count"] == 11
    assert by_id["2247999"]["selected_club_provider_id"] == 379
    assert by_id["2247999"]["page_metadata_date"] == "2003-08-09"
    assert by_id["2247999"]["body_matchday_date"] == "2003-08-08"
    assert by_id["2247999"]["first_fixture_capture_date"] == "2003-08-08"
    assert by_id["2247999"]["date_claims_differ"] is True
    assert by_id["2302395"]["page_metadata_date"] == "2003-08-09"
    assert by_id["2302395"]["body_matchday_date"] == "2003-08-09"
    assert by_id["2302395"]["first_fixture_capture_date"] == "2003-08-09"
    assert by_id["2302395"]["date_claims_differ"] is False


def test_raw_report_wrong_target_club_identity_fails_closed():
    parent, main, overlay, source_doc, eq, jug, *_ = _inputs()
    _index, _raw, native_rosters, owners = subject._read_rosters(eq)
    west_ham = next(row for row in source_doc["club_crossmatches"] if row["club"] == "West Ham United")
    west_ham["selector"]["transfermarkt_club_id"] = 466
    with pytest.raises(subject.OpeningXICompositionError, match="raw report XI IDs/names/position groups differ"):
        subject._verify_raw_match_reports(source_doc, main, jug, native_rosters, owners)


@pytest.mark.parametrize("url", [
    "http://www.transfermarkt.co.uk/preston-west-ham/index/spielbericht/2247999",
    "https://www.transfermarkt.co.uk.evil.invalid/preston-west-ham/index/spielbericht/2247999",
    "https://evil.invalid/preston-west-ham/index/spielbericht/2247999",
    "https://www.transfermarkt.co.uk@evil.invalid/preston-west-ham/index/spielbericht/2247999",
    "https://joe@www.transfermarkt.co.uk/preston-west-ham/index/spielbericht/2247999",
    "https://www.transfermarkt.co.uk/preston-west-ham/index/spielbericht/2247998",
    "https://www.transfermarkt.co.uk/preston-west-ham/index/spielbericht/2247999?other=1",
    "https://www.transfermarkt.co.uk/arbitrary/spielbericht/2247999",
])
def test_root_rejects_untrusted_or_wrong_fixture_route(url):
    with pytest.raises((subject.OpeningXICompositionError, ValueError)):
        subject._verify_report_url(url, "2247999")


def test_root_accepts_exact_https_report_route():
    subject._verify_report_url("https://www.transfermarkt.co.uk/preston-west-ham/index/spielbericht/2247999", "2247999")


def _minimal_publication_envelope(tmp_path, monkeypatch):
    from scripts import season_pipeline_v2 as pipeline
    monkeypatch.setattr(registry, 'ROOT', tmp_path)
    document = {'schema_version': 'pm99-opening-xi-transfer-crossmatch-v1',
                'parent': {'release_id': 'parent'}, 'source_files': {}}
    source = tmp_path / 'source.json'
    source.write_bytes(pipeline.canonical_json_bytes(document))
    plan = dict(document, schema=subject.PROFILE_SCHEMA, season='2003-04',
                release_id='parent', package_sha256='a' * 64, jug_sha256='b' * 64,
                source_input={'path': 'source.json', 'sha256': _sha(source.read_bytes())},
                scope='test')
    plan['transaction_id'] = _sha(pipeline.canonical_json_bytes(plan))[:24]
    return document, plan


def test_publication_envelope_preserves_original_source_semantics(tmp_path, monkeypatch):
    document, plan = _minimal_publication_envelope(tmp_path, monkeypatch)
    assert subject._verify_envelope(plan) == document


def test_publication_envelope_rejects_resealed_source_changes(tmp_path, monkeypatch):
    from scripts import season_pipeline_v2 as pipeline
    _, plan = _minimal_publication_envelope(tmp_path, monkeypatch)
    plan['parent']['release_id'] = 'another-parent'
    plan.pop('transaction_id')
    plan['transaction_id'] = _sha(pipeline.canonical_json_bytes(plan))[:24]
    with pytest.raises(subject.OpeningXICompositionError, match='altered the original'):
        subject._verify_envelope(plan)


def test_publication_envelope_rejects_stale_content_id(tmp_path, monkeypatch):
    _, plan = _minimal_publication_envelope(tmp_path, monkeypatch)
    plan['release_id'] = 'another-parent'
    with pytest.raises(subject.OpeningXICompositionError, match='content hash'):
        subject._verify_envelope(plan)


def test_publication_envelope_rejects_changed_retained_source(tmp_path, monkeypatch):
    _, plan = _minimal_publication_envelope(tmp_path, monkeypatch)
    (tmp_path / 'source.json').write_text('{}')
    with pytest.raises(subject.OpeningXICompositionError, match='crossmatch changed'):
        subject._verify_envelope(plan)


def _cache_fixture(tmp_path, monkeypatch):
    from scripts import season_pipeline_v2 as pipeline
    from types import SimpleNamespace
    document, plan = _minimal_publication_envelope(tmp_path, monkeypatch)
    evidence = tmp_path / 'report.html'
    evidence.write_bytes(b'original report')
    document['source_files'] = {'report.html': {'sha256': _sha(evidence.read_bytes())}}
    source = tmp_path / 'source.json'
    source.write_bytes(pipeline.canonical_json_bytes(document))
    overlay = tmp_path / 'english-season-package.json'
    overlay.write_bytes(b'{}')
    package = tmp_path / 'package.json'
    package.write_bytes(pipeline.canonical_json_bytes({'artifacts': [{'id': 'english',
        'relative_path': overlay.name, 'sha256': _sha(overlay.read_bytes())}]}))
    game = tmp_path / 'game'
    (game / 'DBDAT').mkdir(parents=True)
    (game / 'DBDAT/EQ98030.FDI').write_bytes(b'parent EQ')
    (game / 'DBDAT/JUG98030.FDI').write_bytes(b'parent JUG')
    release = SimpleNamespace(season='2003-04', release_id='parent', manifest_sha256='c' * 64,
                              package_path=package, game_path=game)
    plan['source_files'] = copy.deepcopy(document['source_files'])
    plan.update(package_sha256=_sha(package.read_bytes()), jug_sha256=_sha(b'parent JUG'),
                source_input={'path': source.name, 'sha256': _sha(source.read_bytes())})
    plan.pop('transaction_id')
    plan['transaction_id'] = _sha(pipeline.canonical_json_bytes(plan))[:24]
    monkeypatch.setattr(subject, '_base', lambda value: release)
    calls = []
    def compose(*args):
        calls.append(args)
        if args[3] != b'parent EQ':
            raise subject.OpeningXICompositionError('changed parent EQ')
        return {'mutable': {'value': 'expected'}}
    monkeypatch.setattr(subject, 'compose_in_memory', compose)
    monkeypatch.setattr(subject, '_RECONSTRUCTION_CACHE', {})
    return plan, release, evidence, calls


def test_checked_process_cache_cannot_be_poisoned_by_a_caller(tmp_path, monkeypatch):
    plan, _, _, calls = _cache_fixture(tmp_path, monkeypatch)
    first = subject._reconstruct(plan)
    first['mutable']['value'] = 'tampered'
    assert subject._reconstruct(plan) == {'mutable': {'value': 'expected'}}
    assert len(calls) == 1


def test_checked_process_cache_rehashes_source_bodies_before_reuse(tmp_path, monkeypatch):
    plan, _, evidence, calls = _cache_fixture(tmp_path, monkeypatch)
    subject._reconstruct(plan)
    evidence.write_bytes(b'changed report')
    with pytest.raises(subject.OpeningXICompositionError, match='source hash changed'):
        subject._reconstruct(plan)
    assert len(calls) == 1


def test_checked_process_cache_never_hides_changed_native_parent(tmp_path, monkeypatch):
    plan, release, _, calls = _cache_fixture(tmp_path, monkeypatch)
    subject._reconstruct(plan)
    (release.game_path / 'DBDAT/EQ98030.FDI').write_bytes(b'changed EQ')
    with pytest.raises(subject.OpeningXICompositionError, match='changed parent EQ'):
        subject._reconstruct(plan)
    assert len(calls) == 2


def test_existing_source_dispatch_routes_only_the_exact_membership_schema(monkeypatch):
    from types import SimpleNamespace
    from scripts import season_profile_assignment_pruning_layer_v1 as dispatcher
    previous = SimpleNamespace(locator={'sourced_profile_assignment_plan_path': 'source.json'}, package_path=Path('package.json'))
    monkeypatch.setattr(dispatcher.pipeline, 'read_json_file', lambda path: {'schema': subject.PROFILE_SCHEMA})
    calls = []
    monkeypatch.setattr(subject, 'reconstruction', lambda *args: calls.append(args) or {'source': 'membership'})
    assert dispatcher.reconstruction(previous, 'child') == {'source': 'membership'}
    assert calls == [(previous, 'child')]


def test_publication_bind_emits_a_schema_valid_source_artifact(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts.test_season_package_compiler_v2 import _native_package
    package = _native_package()
    package['artifacts'].append({'id': 'z-last', 'kind': 'season-input', 'sha256': 'b' * 64})
    package['artifacts'].sort(key=lambda row: row['id'])
    path = tmp_path / 'package.json'
    path.write_bytes(package_v2.canonical_json_bytes(package))
    plan = {'transaction_id': 'a' * 24}
    monkeypatch.setattr(subject, '_base', lambda value: SimpleNamespace(package_path=path))
    monkeypatch.setattr(subject, '_reconstruct', lambda value: {'outputs': {'main_package': copy.deepcopy(package)}})
    bound = subject.bind(package, plan)
    artifact = next(row for row in bound['artifacts'] if row['id'] == subject.PLAN_ARTIFACT_ID)
    assert artifact['kind'] == 'season-input' and artifact['media_type'] == 'application/json'
    assert [row['id'] for row in bound['artifacts']] == sorted(row['id'] for row in bound['artifacts'])
    package_v2.validate_package(bound)
