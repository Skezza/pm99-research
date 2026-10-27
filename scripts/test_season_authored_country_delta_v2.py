"""Selected-player capacity recovery must retain the same native safety checks."""
import copy
import hashlib
import pytest
from scripts import season_authored_country_delta_v1 as legacy
from scripts import season_authored_country_delta_v2 as current
from scripts import season_same_carrier_name_capacity_v1 as capacity
from scripts.test_season_same_carrier_name_capacity_v1 import fixture
from app.fdi_indexed import IndexedFDIFile
from app.player_name_capacity import recover_compact_name_window


def request(tmp_path,monkeypatch):
    bundle,data=fixture(tmp_path,monkeypatch)
    factory=capacity.verify_bundle(bundle).read_bytes()
    original=IndexedFDIFile.from_bytes(factory).entries[0].decode_payload(factory)
    entry=next(e for e in IndexedFDIFile.from_bytes(data).entries if e.record_id==2)
    raw=entry.decode_payload(data)
    restored,proof=recover_compact_name_window(original,raw)
    claim=dict(carrier_id=2,current_sha256=hashlib.sha256(raw).hexdigest(),
        recovered_sha256=hashlib.sha256(restored).hexdigest(),proof=proof)
    return data,dict(name_capacity=dict(bundle=bundle,claims=[claim]))


def test_old_and_new_transaction_formats_remain_distinct():
    assert legacy.SCHEMA != current.SCHEMA
    assert legacy.MODE != current.MODE


def test_absent_capacity_keeps_original_bytes():
    assert current.prepare_name_capacity(b'unchanged',{},[])==b'unchanged'


def test_selected_slot_recovery_preserves_other_native_records(tmp_path,monkeypatch):
    raw,plan=request(tmp_path,monkeypatch)
    result=current.prepare_name_capacity(raw,plan,[2])
    assert result!=raw
    before={e.record_id:e.decode_payload(raw) for e in IndexedFDIFile.from_bytes(raw).entries}
    after={e.record_id:e.decode_payload(result) for e in IndexedFDIFile.from_bytes(result).entries}
    assert before[3]==after[3]
    assert current.prepare_name_capacity(raw,plan,[2])==result


@pytest.mark.parametrize('fault',['outside-selection','duplicate','preimage','postimage','proof','factory'])
def test_rejects_invalid_capacity_authority(tmp_path,monkeypatch,fault):
    raw,plan=request(tmp_path,monkeypatch);selected=[2];claim=plan['name_capacity']['claims'][0]
    if fault=='outside-selection':selected=[3]
    elif fault=='duplicate':plan['name_capacity']['claims'].append(copy.deepcopy(claim))
    elif fault=='preimage':claim['current_sha256']='forged'
    elif fault=='postimage':claim['recovered_sha256']='forged'
    elif fault=='proof':claim['proof']={}
    elif fault=='factory':plan['name_capacity']['bundle']['factory']['sha256']='forged'
    with pytest.raises(ValueError):current.prepare_name_capacity(raw,plan,selected)


@pytest.mark.parametrize('adapter',[legacy,current],ids=['existing-v1','explicit-v2'])
def test_source_dispatch_keeps_each_transaction_on_its_version(tmp_path,monkeypatch,adapter):
    from types import SimpleNamespace
    import json
    from scripts import season_profile_assignment_pruning_layer_v1 as dispatch
    recipe=tmp_path/'package.json';recipe.write_text('{}')
    plan=tmp_path/'plan.json';plan.write_text(json.dumps(dict(schema=adapter.SCHEMA)))
    previous=SimpleNamespace(package_path=recipe,locator={'sourced_profile_assignment_plan_path':str(plan)})
    calls=[]
    def replay(parent,release_id):
        calls.append((parent,release_id))
        return {'selected_version':adapter.SCHEMA}
    monkeypatch.setattr(adapter,'reconstruction',replay)
    result=dispatch.reconstruction(previous,'source-replay')
    assert result=={'selected_version':adapter.SCHEMA}
    assert calls==[(previous,'source-replay')]
