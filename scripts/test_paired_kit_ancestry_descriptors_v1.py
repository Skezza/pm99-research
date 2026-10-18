import json
from types import SimpleNamespace
import pytest
from scripts import pm99_season_qa_v1 as qa


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    old, game = tmp_path/'old', tmp_path/'new'
    (old/'DBDAT').mkdir(parents=True);(game/'DBDAT').mkdir(parents=True)
    changes, native_hashes = [], {}
    for name in ('MINIESC.PKF','NANOESC.PKF','RIDIESC.PKF'):
        (old/'DBDAT'/name).write_bytes(b'old '+name.encode())
        (game/'DBDAT'/name).write_bytes(b'new '+name.encode())
        before, after = qa._sha256(old/'DBDAT'/name), qa._sha256(game/'DBDAT'/name)
        changes.append({'path':'DBDAT/'+name,'left':{'sha256':before},'right':{'sha256':after}})
        native_hashes[name]=after
    chain=tmp_path/'chain.json';chain.write_text('{}')
    candidate=tmp_path/'candidate.json';candidate.write_text(json.dumps({'native_hashes':native_hashes}))
    native=tmp_path/'native.json';native.write_text(json.dumps({
        'candidate_receipt_sha256':qa._sha256(candidate),'all_unselected_native_records_identical':True}))
    identity=tmp_path/'identity.json';identity.write_text(json.dumps({
        'candidate_receipt_sha256':qa._sha256(candidate),'introduced_candidate_groups':0,'replacement_cross_club_candidates':0}))
    application={'season':'2022-23','source_release_id':'old','source_build_chain_sha256':qa._sha256(chain),
        'difference':{'changed':changes}}
    for label,path in [('candidate_receipt',candidate),('native_proof',native),('identity_proof',identity)]:
        application[label]={'path':path.name,'sha256':qa._sha256(path)}
    receipt=tmp_path/'application.json';receipt.write_text(json.dumps(application))
    descriptors=[{'sha256':qa._sha256(path),'size':path.stat().st_size} for path in (chain,candidate,native,identity,receipt)]
    manifest={'external_artifacts':[],'stages':[{'external_artifacts':descriptors}]}
    monkeypatch.setattr(qa.release_registry,'load_registered_release',lambda season,release:
        SimpleNamespace(game_path=old,build_chain_path=chain))
    monkeypatch.setattr(qa,'_registered_kit_patch_hashes',lambda *args,**kwargs:{})
    return game,receipt,application,manifest


def test_inherited_original_stage_descriptors_are_valid_hash_authority(tmp_path,monkeypatch):
    game,receipt,application,manifest=setup(tmp_path,monkeypatch)
    result=qa._paired_kit_patch_hashes('2022-23',game,None,receipt,application,manifest)
    assert len(result)==3


@pytest.mark.parametrize('problem',['unbound','tampered'])
def test_stage_ancestry_does_not_relax_hash_protection(tmp_path,monkeypatch,problem):
    game,receipt,application,manifest=setup(tmp_path,monkeypatch)
    if problem=='unbound':manifest['stages']=[]
    else:(tmp_path/'chain.json').write_text('{"wrong":true}')
    with pytest.raises(qa.QaError,match='hash-bound'):
        qa._paired_kit_patch_hashes('2022-23',game,None,receipt,application,manifest)
