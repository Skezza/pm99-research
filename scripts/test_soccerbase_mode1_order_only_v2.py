"""Integrated canonical dispatch test against the data-only r196a rebase."""
from __future__ import annotations
import copy,json
from dataclasses import replace
from pathlib import Path
import pytest
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import read_initial_order
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_soccerbase_mode1_order_only_v2 as subject

INPUT=registry.ROOT/'.local/consolidated-audit-20261009/parallel-rc-20261023/horne/hayes-order-only-typed-r196a-input.json'
pytestmark = pytest.mark.skipif(not INPUT.exists(), reason='retained local historical source corpus unavailable')
EXPECTED_OFFSETS=[2744842,2744905,2744961,2745086,2745152,2745218,2745281,2745343,2745412,2745481,2745546,2745608,2745800,2745860]

@pytest.fixture(scope='module')
def base():
    request=pipeline.read_json_file(INPUT)
    return registry.load_registered_release(request['season'],request['release_id'])

@pytest.fixture(scope='module')
def plan(base):
    # Exercise the integrated public exchange dispatch; no provider monkeypatch.
    return exchange.prepare(base,INPUT)

def test_r196a_parent_rebase_sources_and_exact_masks(base,plan):
    req=pipeline.read_json_file(INPUT)
    assert req['release_id']=='sourced-hayes-flynn-birthday-20261023-r196a'
    assert req['expected_package_sha256']==registry.sha256_file(base.package_path)
    assert req['expected_jug_sha256']==registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI')
    assert req['expected_eq_sha256']==registry.sha256_file(base.game_path/'DBDAT/EQ98030.FDI')
    assert plan['source_input']['sha256']==registry.sha256_file(INPUT)
    assert len(plan['native_order_masks'])==18
    changed=[m for m in plan['native_order_masks'] if m['changed']]
    assert len(changed)==14
    assert [m['file_offset'] for m in changed]==EXPECTED_OFFSETS
    assert plan['source_verification']['source_ids']==subject.EXPECTED_XI_IDS
    assert plan['source_verification']['source_full_names']==[
      'Paul Gothard','Jason Tucker','Dean Coppard','Jason Goodliffe','Dominic Sterling',
      'Barry Moore','Ryan Spencer','Steve Barnes','Steve McKimm','Lee Flynn','Dave Stevens']
    assert set(plan['source_verification']['native_roster_flags'])=={0}
    assert {tuple(v) for v in plan['source_verification']['native_owner_sets'].values()}=={(3307,)}
    flynn=next(p for p in pipeline.read_json_file(base.package_path)['players'] if p['carrier_id']==10904)
    assert flynn['facts']['birth_date']=='1973-09-04'

def test_canonical_exchange_bind_apply_and_idempotent_postimage(base,plan):
    stored=json.loads(json.dumps(plan,sort_keys=True))
    exchange.verify(base,stored)
    before_package=pipeline.read_json_file(base.package_path)
    before_jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    before_eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    after_package=exchange.bind(before_package,stored)
    after_jug,after_eq=exchange.apply(before_jug,before_eq,stored)
    assert after_eq==before_eq
    diff=[i for i,(a,b) in enumerate(zip(before_jug,after_jug)) if a!=b]
    assert diff==EXPECTED_OFFSETS
    masks={m['file_offset']:m for m in stored['native_order_masks'] if m['changed']}
    assert set(diff)==set(masks)
    assert all(after_jug[o]==m['after'] for o,m in masks.items())
    index={e.record_id:e for e in IndexedFDIFile.from_bytes(after_jug).entries}
    orders={carrier:read_initial_order(index[carrier].decode_payload(after_jug)).order
      for carrier in stored['complete_mode1_opening']['starting_xi']}
    assert [orders[c] for c in stored['complete_mode1_opening']['starting_xi']]==list(range(1,12))
    old_players={p['carrier_id']:p for p in before_package['players']}
    assert {p['carrier_id']:p for p in after_package['players']}==old_players
    old_clubs={c['carrier_id']:c for c in before_package['clubs']}
    new_clubs={c['carrier_id']:c for c in after_package['clubs']}
    for carrier,old in old_clubs.items():
        if carrier==3307:
            expected=copy.deepcopy(old)
            expected['roster_player_ids']=[old_players[r['carrier_id']]['id'] for r in stored['complete_mode1_opening']['orders']]
            assert new_clubs[carrier]==expected
        else: assert new_clubs[carrier]==old
    assert exchange.apply(after_jug,after_eq,stored)==(after_jug,after_eq)

def test_canonical_dispatch_rejects_wrong_parent_and_mask(base,plan):
    wrong=replace(base,release_id='sourced-original-keeper-roles-20261023-r178a')
    with pytest.raises(ValueError): subject.prepare(wrong,INPUT)
    damaged=copy.deepcopy(plan);damaged['native_order_masks'][0]['file_offset']+=1
    with pytest.raises(ValueError): exchange.verify(base,damaged)
