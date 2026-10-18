import json
import pytest
from pathlib import Path
from scripts import publish_paired_whole_club_delta_v1 as publisher
from scripts import verify_paired_club_identity_v1 as checker


def replay_proof():
    from scripts import prepare_paired_whole_club_native_v1 as replay
    implementation = Path(replay.__file__).resolve()
    return dict(schema='pm99-original-source-proposal-replay-evidence-v1', season='2018-19',
                source_proposal={'sha256': 'proposal'}, original_source_proposal_replayed_exactly=True,
                implementation=dict(path=publisher.registry.relative_workspace_path(implementation),
                                    sha256=publisher.registry.sha256_file(implementation)),
                controller_exit_code=0)


def test_original_source_replay_accepts_bound_success():
    proof = replay_proof()
    publisher.validate_original_source_replay(proof, proof['source_proposal'], '2018-19')


@pytest.mark.parametrize('damage', [None, 'order', 'failure', 'session', 'claim'])
def test_original_source_replay_narrow_post_call_receipt_recovery(damage):
    proof = replay_proof()
    proof.update(controller_exit_code=1, controller_session=29366,
        failed_controller_claimed_success=False,
        call_order=['replay.independently_replay_sources([proposal])',
                    'p.write_canonical_json(... implementation.path=registry.relative_workspace_path(replay.__file__) ...)'],
        post_replay_receipt_failure='AttributeError: str object has no attribute resolve in registry.relative_workspace_path(replay.__file__). Corrected receipt-generation argument to Path(replay.__file__).',
        recovery_method='Source replay call returned before the following receipt-argument evaluation failed. Python sequential execution and the terminal traceback establish completion; no source replay repeated.')
    if damage == 'order': proof['call_order'].reverse()
    if damage == 'failure': proof['post_replay_receipt_failure'] = 'Source replay failed'
    if damage == 'session': proof['controller_session'] = 0
    if damage == 'claim': proof['failed_controller_claimed_success'] = True
    if damage is None:
        publisher.validate_original_source_replay(proof, proof['source_proposal'], '2018-19')
    else:
        with pytest.raises(ValueError, match='completion evidence'):
            publisher.validate_original_source_replay(proof, proof['source_proposal'], '2018-19')


@pytest.mark.parametrize('field,value', [('schema', 'wrong'), ('season', '2017-18'),
    ('implementation', {'sha256': 'stale'}), ('source_proposal', {}),
    ('original_source_proposal_replayed_exactly', False), ('controller_exit_code', None),
    ('controller_exit_code', 1), ('controller_exit_code', False), ('controller_exit_code', 2)])
def test_original_source_replay_rejects_unbound_or_unexplained_completion(field, value):
    proof = replay_proof()
    proposal = proof['source_proposal'].copy()
    proof[field] = value
    with pytest.raises(ValueError, match='original source replay'):
        publisher.validate_original_source_replay(proof, proposal, '2018-19')


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


def test_retained_publisher_requires_original_source_replay_before_metadata(tmp_path):
    from scripts import season_owned_club_composition_v1 as retained
    candidate = tmp_path / 'candidate'
    candidate.mkdir()
    receipt = candidate / 'candidate-receipt.json'
    receipt.write_text(json.dumps(dict(schema_version=retained.PRIVATE_SCHEMA)))
    digest = publisher.registry.sha256_file(receipt)
    native = dict(schema_version=retained.PRIVATE_SCHEMA + '-native-and-artwork-replay',
                  candidate_receipt=dict(sha256=digest), complete_candidate_game_inventory_identical=True,
                  complete_candidate_recipe_identical=True, offline_kit_rerender=True,
                  exact_ground_row_replayed=True)
    identity = dict(candidate_receipt_sha256=digest, introduced_candidate_groups=0,
                    replacement_cross_club_candidates=0, stale_portraits_cleared=True,
                    keeper_recipe_replay_idempotent=True)
    paths = [tmp_path / 'native.json', tmp_path / 'identity.json']
    for path, payload in zip(paths, (native, identity)):
        path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match='original source replay'):
        publisher.publish(candidate, *paths, 'not-published')
