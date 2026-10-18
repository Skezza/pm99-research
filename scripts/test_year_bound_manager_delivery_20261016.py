"""Adversarial checks for mixed private coach evidence and fixed dispositions."""
from types import SimpleNamespace
import pytest
from scripts import capture_year_bound_manager_repairs_20261016 as capture
from scripts import checkpoint_year_bound_managers_20261016 as checkpoint
from scripts import advance_year_bound_manager_captures_20261016 as advance


def selected_fixture(tmp_path,monkeypatch,reused=False):
    monkeypatch.setattr(capture.registry,'ROOT',tmp_path)
    monkeypatch.setattr(capture.batch,'ROOT',tmp_path/'new')
    monkeypatch.setattr(capture.prior,'ROOT',tmp_path/'old')
    monkeypatch.setattr(capture.registry,'relative_workspace_path',lambda p:str(p.relative_to(tmp_path)))
    monkeypatch.setattr(capture.registry,'load_registered_release',lambda *a:SimpleNamespace())
    root=(tmp_path/('old' if reused else 'new'))/'2000-01';root.mkdir(parents=True)
    for name in ('native-byte-proof.json','complete-SOURCE-replay.json'):(root/name).touch()
    decision=dict(selected_plan=dict(updates=[1]),reuse_exact_existing_private_plan=reused)
    selected=dict(season='2000-01',release_id=capture.prior.RELEASE if reused else capture.batch.RELEASE,
        evidence_root=str(root.relative_to(tmp_path)),reuse_exact_completed_private_build=reused)
    saved={'source-acceptance-decision.json':decision,'selected-delivery.json':selected,
        'manager-plan.json':decision['selected_plan']}
    monkeypatch.setattr(capture.source,'decision',lambda base:decision)
    monkeypatch.setattr(capture.pipeline,'read_json_file',lambda p:saved[p.name])
    return root,decision,selected,saved


@pytest.mark.parametrize('reused',[False,True])
def test_selection_binds_exact_new_or_reused_plan(tmp_path,monkeypatch,reused):
    root,_,selected,_=selected_fixture(tmp_path,monkeypatch,reused)
    actual=capture.selection('2000-01')
    assert actual[0]==root and actual[1]==selected['release_id']
    assert ('r109a' if reused else 'r110a') in actual[2]


def test_rejected_plan_cannot_reuse_old_game(tmp_path,monkeypatch):
    _,decision,_,_=selected_fixture(tmp_path,monkeypatch,True)
    decision['reuse_exact_existing_private_plan']=False
    with pytest.raises(ValueError,match='approved exact private plan'):capture.selection('2000-01')


def test_wrong_evidence_path_cannot_select_other_season(tmp_path,monkeypatch):
    _,_,selected,_=selected_fixture(tmp_path,monkeypatch)
    selected['evidence_root']='old/2001-02'
    with pytest.raises(ValueError,match='approved exact private plan'):capture.selection('2000-01')


def test_old_game_plan_must_equal_fresh_selected_plan(tmp_path,monkeypatch):
    _,_,_,saved=selected_fixture(tmp_path,monkeypatch,True)
    saved['manager-plan.json']=dict(updates=[2])
    with pytest.raises(ValueError,match='another source plan'):capture.selection('2000-01')


def publication_fixture(tmp_path,monkeypatch):
    root=tmp_path/'batch';root.mkdir()
    monkeypatch.setattr(checkpoint,'ROOT',root)
    seasons=[f'{y}-{str(y+1)[-2:]}' for y in range(2000,2026)]
    monkeypatch.setattr(checkpoint.registry,'supported_seasons',lambda:seasons)
    previous=dict(current_release_bindings=[dict(season=s,release_id='parent',manifest_sha256='h') for s in seasons])
    monkeypatch.setattr(checkpoint.pipeline,'read_json_file',lambda p:previous)
    writes=[]
    monkeypatch.setattr(checkpoint.publisher,'register_completed_delta',lambda *a:writes.append(a))
    return seasons,writes


def test_last_missing_original_prevents_all_publication(tmp_path,monkeypatch):
    seasons,writes=publication_fixture(tmp_path,monkeypatch)
    def verify(s):
        if s==seasons[-1]:raise ValueError('original unreviewed')
        return dict(original_proposals=20,canonical_manager_updates=18,deferred_proposals=2)
    monkeypatch.setattr(checkpoint,'verify',verify)
    with pytest.raises(ValueError,match='unreviewed'):checkpoint.run()
    assert not writes


def test_deferred_proposals_cannot_disappear_from_frozen495(tmp_path,monkeypatch):
    _,writes=publication_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(checkpoint,'verify',lambda s:dict(original_proposals=19,
        canonical_manager_updates=18,deferred_proposals=1))
    with pytest.raises(ValueError,match='495'):checkpoint.run()
    assert not writes


def test_legacy2015_changed_parent_prevents_all_publication(tmp_path,monkeypatch):
    seasons,writes=publication_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(checkpoint,'verify',lambda s:dict(season=s,release_id='new',manifest_sha256='nh',
        original_proposals=15 if s==seasons[-1] else 20,
        canonical_manager_updates=13 if s==seasons[-1] else 18,deferred_proposals=2))
    monkeypatch.setattr(checkpoint.registry,'load_preferred_release',lambda s:SimpleNamespace(
        release_id='unexpected' if s=='2015-16' else 'parent',manifest_sha256='h'))
    with pytest.raises(ValueError,match='unexpected preferred'):checkpoint.run()
    assert not writes


def test_partial_republication_requires_exact_manifest(tmp_path,monkeypatch):
    seasons,writes=publication_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(checkpoint,'verify',lambda s:dict(season=s,release_id='new',manifest_sha256='nh',
        original_proposals=15 if s==seasons[-1] else 20,
        canonical_manager_updates=13 if s==seasons[-1] else 18,deferred_proposals=2))
    monkeypatch.setattr(checkpoint.registry,'load_preferred_release',lambda s:SimpleNamespace(
        release_id='new' if s==seasons[0] else 'parent',manifest_sha256='WRONG' if s==seasons[0] else 'h'))
    with pytest.raises(ValueError,match='unexpected preferred'):checkpoint.run()
    assert not writes


def test_finished_build_needs_no_live_pid_when_selected_proof_exists(tmp_path,monkeypatch):
    monkeypatch.setattr(advance,'ROOT',tmp_path/'batch')
    monkeypatch.setattr(advance.registry,'ROOT',tmp_path)
    root=tmp_path/'batch/2000-01';root.mkdir(parents=True)
    (root/'selected-delivery.json').touch()
    (root/'complete-SOURCE-replay.json').touch()
    monkeypatch.setattr(advance.pipeline,'read_json_file',lambda p:dict(evidence_root='batch/2000-01'))
    advance.await_selected('2000-01',-1)


def test_missing_selection_and_dead_owned_builder_refuses_restart(tmp_path,monkeypatch):
    monkeypatch.setattr(advance,'ROOT',tmp_path/'batch')
    with pytest.raises(ValueError,match='owned year-bound manager builder stopped'):
        advance.await_selected('2000-01',-1)


def test_resume_does_not_repeat_completed_earlier_seasons(monkeypatch):
    monkeypatch.setattr(advance.registry,'supported_seasons',lambda:['2000-01','2008-09','2015-16','2025-26'])
    waited=[];captured=[]
    monkeypatch.setattr(advance,'await_selected',lambda s,pid:waited.append((s,pid)))
    monkeypatch.setattr(advance,'capture',lambda seasons:captured.extend(seasons))
    advance.main(123,'2008-09')
    assert waited==[('2008-09',123),('2025-26',123)]
    assert captured==['2008-09','2025-26']
