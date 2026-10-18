import json
from types import SimpleNamespace

import pytest

from scripts import qa_photo_revision_closeout_v1 as closeout


def test_report_parent_created_and_revision_binding_frozen(tmp_path):
    release = SimpleNamespace(release_id='photo-r1', manifest_sha256='a'*64,
                              locator={'game_inventory_fingerprint': 'b'*64})
    path = tmp_path / 'season/qa-report.json'
    closeout.save_report(path, {'result': 'pass'}, release)
    report = json.loads(path.read_text())
    assert report['photo_revision_binding'] == closeout.binding(release)
    with pytest.raises(ValueError):
        closeout.save_report(path, {'result': 'pass'}, release)
