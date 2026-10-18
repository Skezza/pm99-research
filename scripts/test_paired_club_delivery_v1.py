import json
import pytest
from scripts import publish_paired_whole_club_delta_v1 as publisher
from scripts import verify_paired_club_identity_v1 as checker


@pytest.mark.parametrize('problem',['native-stale','identity-stale','unselected-changed','introduced','replacement-copy','photo','replay'])
def test_publication_refuses_missing_independent_guards_before_registry_write(tmp_path,problem):
    candidate=tmp_path/'candidate';candidate.mkdir()
    receipt=candidate/'candidate-receipt.json';receipt.write_text('{}')
    digest=publisher.registry.sha256_file(receipt)
    native={'candidate_receipt_sha256':digest,'all_unselected_native_records_identical':True}
    identity={'candidate_receipt_sha256':digest,'introduced_candidate_groups':0,'replacement_cross_club_candidates':0,
        'stale_portraits_cleared':True,'keeper_recipe_replay_idempotent':True}
    if problem=='native-stale':native['candidate_receipt_sha256']='stale'
    if problem=='identity-stale':identity['candidate_receipt_sha256']='stale'
    if problem=='unselected-changed':native['all_unselected_native_records_identical']=False
    if problem=='introduced':identity['introduced_candidate_groups']=1
    if problem=='replacement-copy':identity['replacement_cross_club_candidates']=1
    if problem=='photo':identity['stale_portraits_cleared']=False
    if problem=='replay':identity['keeper_recipe_replay_idempotent']=False
    paths=[tmp_path/'native.json',tmp_path/'identity.json']
    for path,data in zip(paths,(native,identity)):path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='independent'):publisher.publish(candidate,*paths,'not-published')


def test_identity_comparison_keeps_country_independent_cross_club_keys(monkeypatch):
    monkeypatch.setattr(checker.identities,'key',lambda p,people:(p['source_name'],p['birth_date']))
    p=lambda id,club,name='Full Source Name':{'carrier_id':id,'club_id':club,'source_name':name,'birth_date':'1990-01-01'}
    assert not checker.groups({'players':[p(1,'A'),p(2,'A')]},{})
    assert len(checker.groups({'players':[p(1,'A'),p(2,'B')]},{}))==1
    assert not checker.groups({'players':[p(1,'A'),p(2,'B','Different Full Name')]},{})
