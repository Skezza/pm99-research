from types import SimpleNamespace
import json
import pytest
from scripts import resume_country_captures_after_disk_20261017 as subject


def fixture(tmp_path,monkeypatch,*,code=3,extra=None,manifest='actual'):
    monkeypatch.setattr(subject.registry,'ROOT',tmp_path)
    root=tmp_path/'proof';root.mkdir()
    evidence=tmp_path/'evidence';evidence.mkdir()
    game=tmp_path/'game'
    command=['launcher','--release-manifest-sha256',manifest,'--dbdat-dir',str(game/'DBDAT')]
    (evidence/'control_launch.json').write_text(json.dumps(dict(child_command=command)))
    if extra:
        (evidence/extra).write_text('{}')
    (root/'startup-transport.json').write_text(json.dumps(dict(exit_code=code,evidence='evidence',release_manifest_sha256='actual')))
    release=SimpleNamespace(manifest_sha256='actual',game_path=game)
    return root,release


def test_only_known_prelaunch_refusal_can_be_retried(tmp_path,monkeypatch):
    root,release=fixture(tmp_path,monkeypatch)
    assert subject.launch_only_disk_refusal(root,release)['exit_code']==3


@pytest.mark.parametrize('code',[0,1,143])
def test_success_or_different_failure_cannot_be_silently_repeated(tmp_path,monkeypatch,code):
    root,release=fixture(tmp_path,monkeypatch,code=code)
    with pytest.raises(ValueError,match='pre-launch-only'):
        subject.launch_only_disk_refusal(root,release)


def test_already_executed_game_evidence_requires_investigation_not_retry(tmp_path,monkeypatch):
    root,release=fixture(tmp_path,monkeypatch,extra='summary.json')
    with pytest.raises(ValueError,match='pre-launch-only'):
        subject.launch_only_disk_refusal(root,release)


def test_another_game_cannot_use_this_disk_recovery(tmp_path,monkeypatch):
    root,release=fixture(tmp_path,monkeypatch,manifest='other-game')
    with pytest.raises(ValueError,match='another actual game'):
        subject.launch_only_disk_refusal(root,release)
