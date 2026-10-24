"""Corpus-backed API/guard tests for the Gimmelli/Serena source adapter."""
from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_inter_gimmelli_serena_exchange_v1 as adapter

REQUEST_PATH = ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/dalmat-2000-gimmelli-adapter-v1/request-r223a-canonical-bound-v3.json'
TEMPLATE_PATH = ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/dalmat-2000-gimmelli-adapter-v1/request-r220-canonical-bound-v1.json'


@pytest.fixture(scope='module')
def context():
    if not REQUEST_PATH.is_file() or not TEMPLATE_PATH.is_file():
        pytest.skip('retained local source request/corpus is unavailable')
    locator = adapter.registry.locator_path('2000-01', 'sourced-shuker-city-opening-owner-20261024-r223a')
    if not locator.is_file():
        pytest.skip('registered r223A corpus is unavailable')
    base = adapter.registry.load_registered_release(
        '2000-01', 'sourced-shuker-city-opening-owner-20261024-r223a')
    plan = adapter.prepare(base, REQUEST_PATH)
    package = adapter.pipeline.read_json_file(base.package_path)
    post = adapter.bind(package, plan)
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    foto = (base.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
    return base, plan, package, post, jug, eq, foto


def test_publisher_api_roundtrip_and_native_invariants(context):
    base, plan, parent, post, jug, eq, foto = context
    plan_json = json.loads(adapter.canonical(plan))
    assert plan_json == plan
    assert adapter.prepare(base, REQUEST_PATH) == plan_json
    assert adapter.verify(base, plan) is None
    assert adapter.bind(post, plan) == post
    assert adapter.bind(post, plan) is not post

    patched, patched_eq = adapter.apply(jug, eq, plan)
    assert patched_eq == eq
    assert adapter.apply(patched, patched_eq, plan) == (patched, patched_eq)
    post_foto = adapter.apply_minifoto(foto, plan)
    assert adapter.apply_minifoto(post_foto, plan) == post_foto
    assert adapter.selected_carriers(plan) == {4211, 14660}
    assert adapter.remove_loose_bitmap(None, 4211, plan) is None
    assert adapter.remove_loose_bitmap(None, 14660, plan) is None
    assert adapter.filename(plan).startswith(adapter.PREFIX)
    assert adapter.source_artifact(plan)['sha256'] == adapter.sha(adapter.canonical(plan))
    with pytest.raises(ValueError, match='source-bound replay'):
        adapter.reject_factory_recipe(post)

    for row in parent['players']:
        if row['carrier_id'] not in (4211, 14660, 7275):
            assert next(p for p in post['players'] if p['id'] == row['id']) == row
    assert next(p for p in post['players'] if p['carrier_id'] == 7275) == next(
        p for p in parent['players'] if p['carrier_id'] == 7275)
    serena_after = next(p for p in post['players'] if p['carrier_id'] == 14660)
    serena_source = next(p for p in parent['players'] if p['carrier_id'] == 4211)
    dalmat_before = next(p for p in parent['players'] if p['carrier_id'] == 14660)
    assert serena_after['person_id'] == serena_source['person_id']
    assert serena_after['ratings'] == serena_source['ratings']
    assert serena_after['facts']['height_cm'] == serena_source['facts']['height_cm']
    assert serena_after['facts']['weight_kg'] == serena_source['facts']['weight_kg']
    assert serena_after['ratings'] != dalmat_before['ratings']
    assert serena_after['facts']['height_cm'] != dalmat_before['facts']['height_cm']
    assert serena_after['facts']['weight_kg'] == dalmat_before['facts']['weight_kg']
    assert next(p for p in post['players'] if p['carrier_id'] == 4211)['person_id'] not in {
        serena_source['person_id'], dalmat_before['person_id']}
    assert post['clubs'] == parent['clubs']
    assert post['managers'] == parent['managers']


def test_source_and_package_tampering_refuse(context, tmp_path):
    base, plan, parent, *_ = context
    tampered = copy.deepcopy(json.loads(REQUEST_PATH.read_text()))
    tampered['sources']['storia']['sha256'] = '0' * 64
    candidate = Path(__file__).with_name('tampered-request-test-only.json')
    candidate.write_text(json.dumps(tampered, ensure_ascii=False))
    try:
        with pytest.raises(ValueError, match='source SHA differs'):
            adapter.prepare(base, candidate)
    finally:
        candidate.unlink(missing_ok=True)

    mutated = copy.deepcopy(parent)
    mutated['package_id'] = 'mutated-test-only'
    with pytest.raises(ValueError, match='exact complete parent or exact complete postimage'):
        adapter.bind(mutated, plan)


def test_plan_artifact_matches_actual_single_lf_writer(context, tmp_path):
    _base, plan, *_ = context
    written_path = tmp_path / adapter.filename(plan)
    written_sha = adapter.pipeline.write_canonical_json(written_path, plan)
    artifact = adapter.source_artifact(plan)
    assert written_path.read_bytes() == artifact['bytes'] == adapter.packages.canonical_json_bytes(plan)
    assert written_sha == adapter.sha(written_path.read_bytes()) == artifact['sha256']
    assert written_path.read_bytes().endswith(b'\n')
    assert not written_path.read_bytes().endswith(b'\n\n')


def test_bind_accepts_only_exact_parent_and_postimage(context):
    _base, plan, parent, post, *_ = context
    assert adapter.bind(parent, plan) == post
    assert adapter.bind(post, plan) == post
    changed = copy.deepcopy(parent)
    changed['package_id'] = 'tampered-bind-test'
    with pytest.raises(ValueError, match='exact complete parent or exact complete postimage'):
        adapter.bind(changed, plan)


def test_reconstruction_checks_matching_mode_before_locator(tmp_path):
    receipt = tmp_path / 'foreign-receipt.json'
    receipt.write_text(json.dumps({'compilation_mode': 'another-mode'}))

    class NoLocator(SimpleNamespace):
        @property
        def locator(self):
            raise AssertionError('foreign SOURCE mode must return before inherited locator access')

    previous = NoLocator(compiler_receipt_path=receipt)
    assert adapter.reconstruction(previous, 'unused-child') is None


def test_rebase_request_creates_new_exact_parent_binding(context):
    base = context[0]
    output = Path(__file__).with_name('rebase-request-test-only.json')
    try:
        result = adapter.rebase_request(base, output, REQUEST_PATH)
        request = json.loads(output.read_text())
        assert result['release_id'] == base.release_id
        assert request['parent'] == adapter.exact_parent(base)
        assert request['schema'] == adapter.INPUT_SCHEMA
        assert output.read_bytes() == adapter.canonical(request)
        assert not output.read_bytes().endswith(b'\n\n')
    finally:
        output.unlink(missing_ok=True)


def test_source_replay_preflight_accepts_only_exact_layer(context):
    base, plan, _parent, post, *_ = context
    scratch = Path(__file__).with_name('source-preflight-test-only')
    scratch.mkdir(exist_ok=False)
    try:
        plan_path = scratch / adapter.filename(plan)
        adapter.pipeline.write_canonical_json(plan_path, plan)
        artifact = adapter.source_artifact(plan)
        assert plan_path.read_bytes() == artifact['bytes']
        assert adapter.registry.sha256_file(plan_path) == artifact['sha256']
        package_path = scratch / 'season-package.json'
        package_path.write_bytes(adapter.canonical(post))
        descriptor_path = scratch / 'role-delta-input.json'
        descriptor_path.write_bytes(adapter.canonical({
            'season': base.season, 'release_id': base.release_id,
            'package_sha256': adapter.registry.sha256_file(base.package_path),
            'jug_sha256': adapter.registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'),
            'updates': [], 'unresolved': []}))
        receipt_path = scratch / 'compiler-receipt.json'
        receipt_path.write_bytes(adapter.canonical({
            'compilation_mode': adapter.MODE,
            'original_profile_assignment_plan_sha256': adapter.sha(plan_path.read_bytes())}))
        previous = SimpleNamespace(season=base.season, release_id='private-unregistered-preflight',
            package_path=package_path, compiler_receipt_path=receipt_path,
            game_path=base.game_path, inventory_path=base.inventory_path,
            locator={'sourced_profile_assignment_plan_path': str(plan_path.relative_to(adapter.ROOT))})
        checked = adapter._source_preflight(previous)
        assert checked['plan']['transaction_id'] == plan['transaction_id']
        assert checked['package'] == post

        changed = copy.deepcopy(post)
        changed['players'][0]['name'] = 'tampered test value'
        package_path.write_bytes(adapter.canonical(changed))
        with pytest.raises(ValueError, match='complete recipe change'):
            adapter._source_preflight(previous)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
