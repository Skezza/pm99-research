"""Canonical Flynn DOB-only source admission and exact native writer scope."""
import copy
from dataclasses import replace
import importlib.util
import json
import sys
from pathlib import Path
import pytest
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_source_verified_player_changes_v1 as writer
from scripts.season_within_club_reserve_repair_v1 import native_facts

from scripts import season_soccerbase_birthday_disagreement_v1 as proposal

@pytest.fixture(scope='module')
def base():
    if not proposal.INPUT_PATH.is_file() or not registry.locator_path('2000-01',proposal.RELEASE_ID).is_file():
        pytest.skip('optional retained source/native corpus unavailable')
    return registry.load_registered_release('2000-01',proposal.RELEASE_ID)

@pytest.fixture(scope='module')
def plan(base):
    return writer.prepare(base,proposal.INPUT_PATH)

def test_common_writer_reproduces_source_and_applies_dob_only(base,plan):
    stored=json.loads(json.dumps(plan,sort_keys=True))
    writer.verify(base,stored)
    before_package=pipeline.read_json_file(base.package_path)
    before_jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    before_eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    after_package=writer.bind(before_package,stored)
    after_jug,after_eq=writer.apply(before_jug,before_eq,stored)
    assert after_eq==before_eq
    assert native_facts(after_jug,10904)['birth_date']=='1973-09-04'
    diff=[i for i,(a,b) in enumerate(zip(before_jug,after_jug)) if a!=b]
    assert diff==[m['file_offset'] for m in stored['updates'][0]['native_masks'] if m['before']!=m['after']]
    assert len(diff)==3
    old={p['carrier_id']:p for p in before_package['players']}
    new={p['carrier_id']:p for p in after_package['players']}
    assert set(old)==set(new)
    for carrier in old:
        if carrier!=10904: assert new[carrier]==old[carrier]
    assert {k:v for k,v in new[10904].items() if k!='facts'}=={k:v for k,v in old[10904].items() if k!='facts'}
    assert {k:v for k,v in new[10904]['facts'].items() if k!='birth_date'}=={k:v for k,v in old[10904]['facts'].items() if k!='birth_date'}
    assert writer.apply(after_jug,after_eq,stored)==(after_jug,after_eq)

def test_exact_source_parent_and_mask_guards(base,plan):
    request=pipeline.read_json_file(proposal.INPUT_PATH)
    wrong_parent=replace(base,release_id='sourced-original-keeper-roles-20261023-r178a')
    with pytest.raises(ValueError): proposal.prepare(wrong_parent,proposal.INPUT_PATH)
    damaged=copy.deepcopy(plan); damaged['updates'][0]['native_masks'][2]['file_offset']+=1
    with pytest.raises(ValueError): writer.validate_mask(damaged)
    with pytest.raises(ValueError): writer.verify(base,damaged)
