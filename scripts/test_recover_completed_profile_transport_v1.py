import pytest
from types import SimpleNamespace
from scripts import recover_completed_profile_transport_v1 as subject


def observation():
    return dict(outer_controller_exit_code=143,tool_terminal_output_observed=True,
        observed_child_statuses=dict(run_status=0,sync_status=0,cleanup_status=0),
        tool_session_id=11682,outer_controller_pid=3489395,child_pid=3500054)


def test_proven_terminal_child_can_be_independently_checked(monkeypatch,tmp_path):
    monkeypatch.setattr(subject,'Path',lambda path:tmp_path)
    subject.validate_observation(observation())


@pytest.mark.parametrize('field',['run_status','sync_status','cleanup_status'])
def test_any_failed_child_stage_refuses_recovery(field):
    value=observation();value['observed_child_statuses'][field]=1
    with pytest.raises(ValueError,match='observed successful child'):
        subject.validate_observation(value)


def test_success_cannot_be_inferred_from_only_a_screenshot():
    value=observation();value['tool_terminal_output_observed']=False
    with pytest.raises(ValueError,match='explicit terminal143'):
        subject.validate_observation(value)


@pytest.mark.parametrize('key',['outer_controller_pid','child_pid'])
def test_active_original_process_refuses_recovery(monkeypatch,tmp_path,key):
    value=observation();monkeypatch.setattr(subject,'Path',lambda path:tmp_path)
    folder=tmp_path/str(value[key]);folder.mkdir();(folder/'cmdline').write_text('active original')
    with pytest.raises(ValueError,match='still exists'):
        subject.validate_observation(value)


def mirrored_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(subject.registry, 'ROOT', tmp_path)
    game = tmp_path / 'game'
    (game / 'DBDAT').mkdir(parents=True)
    evidence = tmp_path / 'evidence'
    (evidence / 'remote_startup').mkdir(parents=True)
    (evidence / 'screens').mkdir()
    (evidence / 'screens/frame.png').write_bytes(b'original-frame')
    (evidence / 'remote_startup/container_exit_code.txt').write_text('0')
    subject.pipeline.write_canonical_json(evidence / 'remote_startup/lease.json', dict(
        status='exited', exit_code=0, launcher='run_stars_player_offer_probe_direct.sh'))
    subject.pipeline.write_canonical_json(evidence / 'summary.json', dict(success=True,
        player_profile=dict(expected_name_token_satisfied=True, screenshot='/workspace/artifacts/screens/frame.png')))
    lines = ['# source_root=' + str(game)]
    for name in ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF',
                 'RIDIESC.PKF', 'MINIESC.PKF', 'NANOESC.PKF', 'BIGCAMP.PKF', 'BIGESC.PKF'):
        path = game / 'DBDAT' / name
        path.write_bytes(name.encode())
        lines.append(subject.registry.sha256_file(path) + '  DBDAT/' + name)
    (evidence / 'dbdat_override.sha256').write_text('\n'.join(lines))
    return SimpleNamespace(game_path=game, manifest_sha256='manifest'), evidence


def test_exited_original_native_child_needs_no_invented_outer_status(tmp_path, monkeypatch):
    release, evidence = mirrored_fixture(tmp_path, monkeypatch)
    result = subject.verify_mirrored_native_child(release, evidence)
    assert result['original_container_exit'] == 0
    assert result['outer_controller_exit_code'] is None
    assert result['original_local_sync_status'] is None
    assert not result['compiler_provenance_file_reconstructed']


@pytest.mark.parametrize('fault', ['active', 'wrong-root', 'native-change', 'missing-frame'])
def test_remote_child_recovery_fails_closed(tmp_path, monkeypatch, fault):
    release, evidence = mirrored_fixture(tmp_path, monkeypatch)
    if fault == 'active':
        (evidence / 'remote_startup/container_exit_code.txt').write_text('143')
    elif fault == 'wrong-root':
        release.game_path = tmp_path / 'different-game'
    elif fault == 'native-change':
        (release.game_path / 'DBDAT/RIDIESC.PKF').write_bytes(b'wrong-kit')
    else:
        (evidence / 'screens/frame.png').unlink()
    with pytest.raises(ValueError):
        subject.verify_mirrored_native_child(release, evidence)
