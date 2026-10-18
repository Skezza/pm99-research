import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts import archive_trashed_codex_states_20261016 as archive
from scripts import capture_arsenal_owned_opening_20261016 as capture


def test_archive_inventory_preserves_symlink_without_reading_target(tmp_path):
    source=tmp_path/'source';source.mkdir()
    external=tmp_path/'external';external.mkdir();(external/'not-a-member').write_text('private outside file')
    (source/'directory-link').symlink_to(external,target_is_directory=True)
    (source/'missing-link').symlink_to(tmp_path/'absent')
    (source/'ordinary').write_bytes(b'original')
    rows=archive.inventory(source)
    assert {r['path'] for r in rows}=={'directory-link','missing-link','ordinary'}
    assert [r for r in rows if r['type']=='file']==[dict(path='ordinary',type='file',size=8,
        sha256=hashlib.sha256(b'original').hexdigest())]


def test_archive_inventory_detects_changed_member_bytes(tmp_path):
    (tmp_path/'member').write_bytes(b'before')
    first=archive.inventory(tmp_path)
    (tmp_path/'member').write_bytes(b'after!')
    assert archive.inventory(tmp_path)!=first


@pytest.mark.parametrize('change',[
    dict(exit_code=1),dict(release_manifest_sha256='other'),dict(evidence='other-run')])
def test_capture_rejects_failed_or_other_game_receipt(tmp_path,monkeypatch,change):
    receipt=tmp_path/'transport.json';evidence=tmp_path/'run'
    saved=dict(exit_code=0,release_manifest_sha256='actual',evidence='run');saved.update(change)
    receipt.write_text(json.dumps(saved))
    monkeypatch.setattr(capture.registry,'relative_workspace_path',lambda p:'run')
    monkeypatch.setattr(capture,'captured',lambda *a:pytest.fail('must not relaunch ambiguous prior transport'))
    with pytest.raises(ValueError,match='failed or binds another'):
        capture.bound_capture([],evidence,receipt,SimpleNamespace(manifest_sha256='actual'),{})


def test_capture_reuses_only_exact_successful_receipt(tmp_path,monkeypatch):
    receipt=tmp_path/'transport.json';receipt.write_text(json.dumps(dict(exit_code=0,
        release_manifest_sha256='actual',evidence='run')))
    monkeypatch.setattr(capture.registry,'relative_workspace_path',lambda p:'run')
    monkeypatch.setattr(capture,'captured',lambda *a:pytest.fail('completed original capture must not repeat'))
    capture.bound_capture([],tmp_path/'run',receipt,SimpleNamespace(manifest_sha256='actual'),{})
