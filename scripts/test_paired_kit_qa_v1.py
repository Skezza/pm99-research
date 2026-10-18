"""Coupled roster/kit updates must extend exact independent release evidence."""
import json
from types import SimpleNamespace

import pytest

from scripts import pm99_season_qa_v1 as qa


@pytest.mark.parametrize('problem', [None, 'unbound', 'native-proof', 'identity-proof',
    'introduced', 'outside-copy', 'unselected', 'current-bytes', 'prior-bytes',
    'receipt-bytes', 'missing-size', 'another-season'])
def test_coupled_artwork_requires_complete_exact_transaction(tmp_path, monkeypatch, problem):
    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    previous = SimpleNamespace(game_path=tmp_path / 'previous', build_chain_path=tmp_path / 'old-chain.json')
    previous.build_chain_path.write_text('{}')
    game = tmp_path / 'current'
    names = ('MINIESC.PKF', 'NANOESC.PKF', 'RIDIESC.PKF')
    changes = []
    hashes = {}
    for name in names:
        old, new = previous.game_path / 'DBDAT' / name, game / 'DBDAT' / name
        old.parent.mkdir(parents=True, exist_ok=True)
        new.parent.mkdir(parents=True, exist_ok=True)
        old.write_bytes(('before-' + name).encode())
        new.write_bytes(('after-' + name).encode())
        hashes[name] = qa._sha256(new)
        changes.append({'path': 'DBDAT/' + name, 'left': {'sha256': qa._sha256(old)},
            'right': {'sha256': hashes[name]}})
    receipt = tmp_path / 'candidate.json'
    if problem == 'receipt-bytes':
        hashes[names[0]] = 'wrong'
    receipt.write_text(json.dumps({'native_hashes': hashes}))
    digest = qa._sha256(receipt)
    native = {'candidate_receipt_sha256': digest, 'all_unselected_native_records_identical': True}
    identity = {'candidate_receipt_sha256': digest,
        'introduced_candidate_groups': 0, 'replacement_cross_club_candidates': 0}
    if problem == 'native-proof':
        native['candidate_receipt_sha256'] = 'stale'
    if problem == 'identity-proof':
        identity['candidate_receipt_sha256'] = 'stale'
    if problem == 'introduced':
        identity['introduced_candidate_groups'] = 1
    if problem == 'outside-copy':
        identity['replacement_cross_club_candidates'] = 1
    if problem == 'unselected':
        native['all_unselected_native_records_identical'] = False
    proof_paths = [tmp_path / 'native.json', tmp_path / 'identity.json']
    for path, doc in zip(proof_paths, (native, identity)):
        path.write_text(json.dumps(doc))
    app = {'season': '2021-22', 'source_release_id': 'prior',
        'source_build_chain_sha256': qa._sha256(previous.build_chain_path),
        'difference': {'changed': changes}}
    for label, path in zip(('candidate_receipt', 'native_proof', 'identity_proof'), [receipt, *proof_paths]):
        app[label] = {'path': path.name, 'sha256': qa._sha256(path)}
    if problem == 'missing-size':
        app['difference']['changed'] = changes[:2]
    if problem == 'another-season':
        app['season'] = '2020-21'
    application = tmp_path / 'application.json'
    application.write_text(json.dumps(app))
    manifest = {'external_artifacts': [{'sha256': qa._sha256(p), 'size': p.stat().st_size}
        for p in [application, previous.build_chain_path, receipt, *proof_paths]]}
    if problem == 'unbound':
        manifest['external_artifacts'] = []
    if problem == 'current-bytes':
        (game / 'DBDAT' / names[0]).write_bytes(b'changed')
    if problem == 'prior-bytes':
        (previous.game_path / 'DBDAT' / names[0]).write_bytes(b'changed')
    monkeypatch.setattr(qa.release_registry, 'load_registered_release', lambda *args: previous)
    monkeypatch.setattr(qa, '_registered_kit_patch_hashes', lambda *args, **kwargs: {})
    if problem:
        with pytest.raises(qa.QaError):
            qa._paired_kit_patch_hashes('2021-22', game, None, application, app, manifest)
    else:
        result = qa._paired_kit_patch_hashes('2021-22', game, None, application, app, manifest)
        assert set(result) == set(names)
        assert all(result[n]['after'] == hashes[n] for n in names)
