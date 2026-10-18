import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import season_same_carrier_name_capacity_v1 as capacity
from scripts.test_season_package_compiler_v2 import _indexed_fdi,_dd6360_player_payload
from app.player_name_capacity import stored_case_display
from app.editor_actions import _patch_indexed_dd6360_variable_name,_native_dd6360_role_start,_read_native_dd6360_fields


def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(capacity.registry,'ROOT',tmp_path)
    factory=_dd6360_player_payload(2)
    current,_=_patch_indexed_dd6360_variable_name(factory,stored_case_display(factory),'Q')
    data=_indexed_fdi([(2,'',current),(3,'',_dd6360_player_payload(3))])
    factory_path=tmp_path/'factory.fdi';factory_path.write_bytes(_indexed_fdi([(2,'',factory)]))
    monkeypatch.setattr(capacity,'FACTORY_SHA',capacity.registry.sha256_file(factory_path))
    fields=_read_native_dd6360_fields(current,_native_dd6360_role_start(current))
    pilot={'schema_version':'pm99-private-factory-name-capacity-runtime-pilot-v1','historical_release':False,
        'publication_authorised':False,'native_records_changed':1,'unrelated_native_bytes_unchanged':True,
        'native_proof':{'semantic_readback_unchanged':True,'opaque_suffix_preserved':True,
            'native_fields_before':fields,'native_fields_after':fields,
            'recovery':{'exact_shrink_roundtrip':True},'current_suffix_cursor':10,
            'pilot_suffix_cursor':20,'factory_suffix_cursor':30},
        'pilot_display_name':'Bugnet','pilot_jug_sha256':'actual-pilot-digest'}
    summary={'success':True,'wine_debugger_detected':False,'process_exit_code':None,
        'player_profile':{'expected_name_token_satisfied':True,'player_name_ocr_normalized':'bugnet',
                          'screenshot':'/workspace/artifacts/screens/profile.png'}}
    bundle={'policy':capacity.POLICY,'factory':capacity.bound(factory_path)}
    for key,value,name in [('runtime_pilot',pilot,'pilot.json'),('runtime_summary',summary,'summary.json')]:
        path=tmp_path/name;path.write_text(json.dumps(value));bundle[key]=capacity.bound(path)
    shot=tmp_path/'profile.png';shot.write_bytes(b'screenshot-bound-by-hash')
    hashes=tmp_path/'hashes.txt';hashes.write_text('actual-pilot-digest  DBDAT/JUG98030.FDI\n')
    bundle.update(runtime_screenshot=capacity.bound(shot),visible_dbdat_hashes=capacity.bound(hashes))
    return bundle,data


def test_default_has_no_extra_native_policy_or_changes():
    original=b'not-even-a-game-file'
    assert capacity.prepare_source(original,{'updates':[],'bindings':{}})==original


def test_capacity_preparation_changes_only_explicit_selected_slot_and_reproduces_claim(tmp_path,monkeypatch):
    bundle,data=fixture(tmp_path,monkeypatch)
    restored,claim=capacity.recover_slot(data,2,bundle)
    plan={'allow_same_carrier_name_capacity':True,'bindings':{'same_carrier_name_capacity':bundle},
        'updates':[{'layer':'main','carrier_id':2,'same_carrier_name_capacity':claim}]}
    assert capacity.prepare_source(data,plan)==restored
    entries=capacity.IndexedFDIFile.from_bytes(data).entries
    unchanged=next(e for e in entries if e.record_id==3)
    assert unchanged.decode_payload(data)==unchanged.decode_payload(restored)
    plan['updates'][0]['same_carrier_name_capacity']['current_record_sha256']='forged'
    with pytest.raises(ValueError,match='independently reproduced'):capacity.prepare_source(data,plan)


@pytest.mark.parametrize('problem',['optin','binding','layer','carrier','empty-claims'])
def test_explicit_capacity_policy_and_matching_slot_are_required(tmp_path,monkeypatch,problem):
    bundle,data=fixture(tmp_path,monkeypatch);_,claim=capacity.recover_slot(data,2,bundle)
    plan={'allow_same_carrier_name_capacity':True,'bindings':{'same_carrier_name_capacity':bundle},
        'updates':[{'layer':'main','carrier_id':2,'same_carrier_name_capacity':claim}]}
    if problem=='optin':plan['allow_same_carrier_name_capacity']=False
    if problem=='binding':plan['bindings']={}
    if problem=='layer':plan['updates'][0]['layer']='english'
    if problem=='carrier':plan['updates'][0]['carrier_id']=3
    if problem=='empty-claims':plan['updates']=[]
    with pytest.raises(ValueError):capacity.prepare_source(data,plan)


@pytest.mark.parametrize('problem',['source-bytes','game-failed','wrong-name','not-observed','crash','wrong-visible-DB','changed-native-facts','no-readback'])
def test_runtime_pilot_cannot_be_swapped_forged_or_relabelled_as_a_live_pass(tmp_path,monkeypatch,problem):
    bundle,data=fixture(tmp_path,monkeypatch)
    if problem=='source-bytes':(tmp_path/'profile.png').write_bytes(b'changed')
    elif problem=='wrong-visible-DB':
        path=tmp_path/'hashes.txt';path.write_text('wrong  DBDAT/JUG98030.FDI\n')
        bundle['visible_dbdat_hashes']=capacity.bound(path)
    elif problem in ('changed-native-facts','no-readback'):
        path=tmp_path/'pilot.json';doc=json.loads(path.read_text())
        if problem=='changed-native-facts':doc['native_proof']['native_fields_after']['height_cm']=100
        else:doc['native_proof']['native_fields_before']=doc['native_proof']['native_fields_after']=None
        path.write_text(json.dumps(doc));bundle['runtime_pilot']=capacity.bound(path)
    else:
        path=tmp_path/'summary.json';doc=json.loads(path.read_text())
        if problem=='game-failed':doc['success']=False
        if problem=='wrong-name':doc['player_profile']['player_name_ocr_normalized']='Tony'
        if problem=='not-observed':doc['player_profile']['expected_name_token_satisfied']=False
        if problem=='crash':doc['wine_debugger_detected']=True
        path.write_text(json.dumps(doc));bundle['runtime_summary']=capacity.bound(path)
    with pytest.raises(ValueError):capacity.verify_bundle(bundle)
