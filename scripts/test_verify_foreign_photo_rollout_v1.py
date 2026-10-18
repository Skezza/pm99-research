import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import verify_foreign_photo_rollout_v1 as verify
from scripts import season_visual_patch_v1 as art


def test_receipts_follow_current_chain_not_directory_order(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, 'ROOT', tmp_path)
    stages = []
    for release_id in ['z-first', 'a-second']:
        root = tmp_path / '.local/season-art-transactions-v1' / release_id / '2025-26'
        root.mkdir(parents=True)
        receipt = root / 'receipt.json'
        art.save(receipt, {'replacements': [{'carrier_id': 1, 'name': release_id}]})
        app = root / 'visual-patch-application.json'
        art.save(app, {'materialisation_path': str(receipt), 'materialisation_sha256': art.sha(receipt)})
        art.save(root / 'journal.json', {'state': 'committed', 'release_id': release_id})
        stages.append({'id': 'portrait-' + release_id, 'receipt_sha256': art.sha(app)})
    chain = tmp_path / 'chain.json'
    art.save(chain, {'stages': stages})
    release = SimpleNamespace(season='2025-26', build_chain_path=chain)
    assert [lane for lane, _ in verify.committed_photo_receipts(release)] == ['z-first', 'a-second']
    receipt.write_text(json.dumps({'replacements': []}))
    with pytest.raises(ValueError, match='release chain'):
        verify.committed_photo_receipts(release)


def test_foreign_coverage_excludes_english_fixed_carriers():
    package = {'clubs': [
        {'capacity_policy': 'preserve-existing-mode1', 'division': 'Premier League', 'roster_player_ids': ['english']},
        {'capacity_policy': 'preserve-existing-mode1', 'division': 'preserve-existing-mode1-membership',
         'roster_player_ids': ['foreign']} ]}
    assert verify.foreign_roster_ids(package) == {'foreign'}
