"""Finite adversarial checks for the canonical Evers/Adams exchange dispatch."""
from __future__ import annotations

import copy
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'upstream/pm99-skezmod-db-editor')]
from scripts import season_soccerbase_mode0_partial_order_v1 as subject
from scripts import season_pipeline_v2 as pipeline
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_release_registry_v1 as registry

REQUEST = ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/plymouth-evers-adams-source-request-v1.json'
RELEASE = 'sourced-hayes-opening-order-20261023-r197a'
REQUIRED_LOCAL = [
    REQUEST,
    ROOT / '.local/historical-role-deltas-v1/2000-01' / RELEASE / 'season-package.json',
    ROOT / '.local/historical-role-deltas-v1/2000-01' / RELEASE / 'game/DBDAT/JUG98030.FDI',
    ROOT / '.local/historical-role-deltas-v1/2000-01' / RELEASE / 'game/DBDAT/EQ98030.FDI',
    *(ROOT / binding['path'] for binding in subject.SOURCE_BINDINGS.values()),
    *(ROOT / binding['receipt_path'] for binding in subject.SOURCE_BINDINGS.values()),
]
pytestmark = pytest.mark.skipif(
    not all(path.exists() for path in REQUIRED_LOCAL),
    reason='requires local SoccerBase originals/receipts and the pinned 2000-01 r197 parent')


def _base():
    return registry.load_registered_release('2000-01', RELEASE)


def test_original_dated_xi_five_bench_and_exact_actor_delta():
    plan = exchange.prepare(_base(), REQUEST)
    proof = plan['typed_partial_order']
    assert proof['fixture']['date'] == '2000-08-12'
    assert len(proof['starting_xi_source_ids']) == 11
    assert len(proof['published_bench_source_ids']) == 5
    assert 'soccerbase:15645' in proof['published_bench_source_ids']
    assert 'soccerbase:8915' not in proof['starting_xi_source_ids'] + proof['published_bench_source_ids']
    assert proof['selection_before'] == subject.BEFORE
    assert proof['selection_after'] == subject.AFTER
    assert len(proof['changed_jug_offsets']) == 5
    assert [(r['carrier_id'], r['before'], r['after']) for r in proof['changed_order_rows']] == [
        (33129, 22, 15), (33121, 15, 19), (33126, 19, 20),
        (33127, 20, 21), (33128, 21, 22)]
    assert proof['scope_limit'].startswith('The exact dated source lists five substitutes')


def test_source_and_parent_bindings_reject_mutation():
    base = _base()
    request = pipeline.read_json_file(REQUEST)
    bad_source = copy.deepcopy(request)
    bad_source['source_bindings']['adams_profile']['sha256'] = '0' * 64
    try:
        subject._validate_request(base, bad_source)
    except ValueError as exc:
        assert 'source body/receipt' in str(exc)
    else:
        raise AssertionError('modified SoccerBase body hash was accepted')
    bad_parent = copy.deepcopy(request)
    bad_parent['expected_eq_sha256'] = '0' * 64
    try:
        subject._validate_request(base, bad_parent)
    except ValueError as exc:
        assert 'EQ parent pin' in str(exc)
    else:
        raise AssertionError('modified native parent pin was accepted')
    bad_actor = copy.deepcopy(request)
    bad_actor['actors']['add']['provider_player_id'] = 15646
    try:
        subject._validate_request(base, bad_actor)
    except ValueError as exc:
        assert 'actor identities' in str(exc)
    else:
        raise AssertionError('modified exact actor/provider metadata was accepted')


def test_existing_mode0_writer_changes_only_its_five_masks():
    base = _base()
    plan = exchange.prepare(base, REQUEST)
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    layer = plan['typed_partial_order']['order_layer']
    output = subject.order_writer.apply_layer(eq, jug, layer, allow_compact=False)
    assert subject.order_writer.apply_layer(eq, output, layer, allow_compact=False) == output
    assert eq == (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    changed = {i for i, (before, after) in enumerate(zip(jug, output)) if before != after}
    assert changed == set(plan['typed_partial_order']['changed_jug_offsets'])
    assert len(changed) == 5


def test_exchange_shaped_bind_and_apply_preserve_every_other_input():
    base = _base()
    plan = exchange.prepare(base, REQUEST)
    package = pipeline.read_json_file(base.package_path)
    result = exchange.bind(package, plan)
    assert result['players'] == package['players']
    assert result['assets'] == package['assets']
    before_club = next(c for c in package['clubs'] if c['carrier_id'] == 385)
    after_club = next(c for c in result['clubs'] if c['carrier_id'] == 385)
    assert after_club['opening']['starting_xi_player_ids'] == before_club['opening']['starting_xi_player_ids']
    assert after_club['opening']['substitute_player_ids'] == subject.AFTER
    assert len(after_club['roster_player_ids']) == 25
    assert {p['id'] for p in result['players'] if p['club_id'] == after_club['id']} == set(
        next(c for c in result['clubs'] if c['carrier_id'] == 385)['roster_player_ids'])
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    output_jug, output_eq = exchange.apply(jug, eq, plan)
    assert output_eq == eq
    assert {i for i, (a, b) in enumerate(zip(jug, output_jug)) if a != b} == set(
        plan['typed_partial_order']['changed_jug_offsets'])
    post_jug, post_eq = exchange.apply(output_jug, output_eq, plan)
    assert post_jug == output_jug and post_eq == eq


def test_canonical_exchange_dispatch_rejects_invalid_mask():
    base = _base()
    plan = exchange.prepare(base, REQUEST)
    assert plan['schema'] == exchange.SCHEMA
    damaged = copy.deepcopy(plan)
    damaged['typed_partial_order']['changed_jug_offsets'].append(0)
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    try:
        exchange.apply(jug, eq, damaged)
    except ValueError as exc:
        assert 'does not independently reproduce' in str(exc)
    else:
        raise AssertionError('tampered five-byte mask was accepted')
