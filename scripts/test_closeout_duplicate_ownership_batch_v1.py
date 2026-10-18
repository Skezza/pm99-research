import json
from types import SimpleNamespace

import pytest

from scripts import closeout_duplicate_ownership_batch_v1 as batch
from scripts import pm99_season_qa_v1 as qa


def test_completed_English_layer_slots_are_reused_not_rebuilt(tmp_path,monkeypatch):
    season='2015-16';source=tmp_path/'source'/season;source.mkdir(parents=True)
    for name in ('old','current'):
        directory=tmp_path/name/'DBDAT';directory.mkdir(parents=True)
        for file in ('EQ98030.FDI','ENT98030.FDI'): (directory/file).write_bytes(b'unchanged')
        (directory/'JUG98030.FDI').write_bytes(name.encode())
        (tmp_path/name/'package.json').write_text('{}')
    before={'id':'english-player-1','source_name':'Old Person','facts':{'birth_date':'1990-01-01'}}
    update={'layer':'english','player_id':before['id'],'before':before,
        'replacement':{'source_player':{'name':'New Person','birth_date':'1995-01-01'}},
        'retained_owner_player_id':'correct-copy','owner_evidence':{},'replacement_opening_evidence':{}}
    saved=tmp_path/'saved-plan.json';saved.write_text(json.dumps({'updates':[update]}))
    old=SimpleNamespace(package_path=tmp_path/'old/package.json',game_path=tmp_path/'old')
    current=SimpleNamespace(package_path=tmp_path/'current/package.json',game_path=tmp_path/'current',
        release_id='completed-English',locator={'ownership_plan_path':'saved-plan.json'})
    doc={'season':season,'release_id':'old','package_sha256':batch.registry.sha256_file(old.package_path),
        'jug_sha256':batch.registry.sha256_file(old.game_path/'DBDAT/JUG98030.FDI'),
        'updates':[update],'summary':{'replacement_slots':1}}
    (source/'ownership-plan.json').write_text(json.dumps(doc))
    monkeypatch.setattr(batch,'ROOT',tmp_path)
    monkeypatch.setattr(batch.registry,'ROOT',tmp_path)
    monkeypatch.setattr(batch.registry,'supported_seasons',lambda:[season])
    monkeypatch.setattr(batch.registry,'load_registered_release',lambda *a:old)
    monkeypatch.setattr(batch.registry,'load_preferred_release',lambda *a:current)
    after={'id':before['id'],'source_name':'New Person','facts':{'birth_date':'1995-01-01'}}
    monkeypatch.setattr(batch.planner,'package_layers',lambda r:[('main',{'players':[]},current.package_path),
        ('english',{'players':[after]},tmp_path/'English.json')])
    output=tmp_path/'continued';batch.rebase_completed_plans(tmp_path/'source',output,seasons=[season])
    result=json.loads((output/season/'ownership-plan.json').read_text())
    assert result['updates']==[] and result['release_id']=='completed-English'
    assert len(result['continued_from']['completed_slots_not_rebuilt'])==1


def test_native_proof_freezes_checked_code_without_overwriting(tmp_path):
    source = tmp_path / 'source.py'
    source.write_text('original checked implementation\n')
    implementations = {'compiler_path': source}
    hashes = {'compiler_path': batch.registry.sha256_file(source)}
    frozen = batch.freeze_implementations(implementations, hashes, tmp_path / 'frozen')
    assert frozen['compiler_path'].read_bytes() == source.read_bytes()
    assert batch.freeze_implementations(implementations, hashes, tmp_path / 'frozen') == frozen
    source.write_text('later implementation\n')
    assert batch.registry.sha256_file(frozen['compiler_path']) == hashes['compiler_path']
    with pytest.raises(ValueError, match='before freezing'):
        batch.freeze_implementations(implementations, hashes, tmp_path / 'frozen')
    hashes['compiler_path'] = batch.registry.sha256_file(source)
    with pytest.raises(ValueError, match='never overwrite'):
        batch.freeze_implementations(implementations, hashes, tmp_path / 'frozen')


@pytest.mark.parametrize('layer_changed', [False, True])
def test_identity_resume_uses_only_exact_unchanged_recipe_layers(tmp_path, monkeypatch, layer_changed):
    package = tmp_path / 'pkg.json'
    package.write_text('{}')
    row = {'season': '2000-01', 'release_id': 'current',
        'package_sha256': batch.registry.sha256_file(package),
        'layers': [{'path': 'pkg.json', 'sha256': 'changed' if layer_changed else batch.registry.sha256_file(package)}],
        'duplicate_candidate_groups': 1, 'candidates': []}
    previous = tmp_path / 'previous.json'
    previous.write_text(json.dumps({'schema_version': 'pm99-country-independent-player-identity-candidate-audit-v1',
                                   'seasons': [row]}))
    monkeypatch.setattr(batch, 'ROOT', tmp_path)
    monkeypatch.setattr(batch.registry, 'supported_seasons', lambda: ['2000-01'])
    monkeypatch.setattr(batch.registry, 'load_preferred_release',
                        lambda _: SimpleNamespace(release_id='current', package_path=package))
    monkeypatch.setattr(batch.registry, 'relative_workspace_path', lambda p: str(p.relative_to(tmp_path)))
    def must_reaudit(release):
        raise AssertionError('identity re-audit required')
    monkeypatch.setattr(batch.planner, 'package_layers', must_reaudit)
    if layer_changed:
        with pytest.raises(AssertionError, match='re-audit required'):
            batch.audit_current_identities(tmp_path / 'output.json', previous)
    else:
        result = batch.audit_current_identities(tmp_path / 'output.json', previous)
        assert result['seasons'] == [row]
        assert result['reuse']['unchanged_seasons'] == ['2000-01']


def test_closeout_never_overwrites_completed_evidence(tmp_path):
    output = tmp_path / 'complete'
    output.mkdir()
    with pytest.raises(ValueError, match='immutable'):
        batch.closeout(tmp_path, output, tmp_path)


def test_closeout_rejects_failed_full_release_validation(tmp_path, monkeypatch):
    root = tmp_path / 'plans'
    (root / '2000-01').mkdir(parents=True)
    (root / '2000-01' / 'ownership-plan.json').write_text(json.dumps({'updates': [], 'unresolved': []}))
    monkeypatch.setattr(batch.registry, 'supported_seasons', lambda: ['2000-01'])
    monkeypatch.setattr(batch.registry, 'validate_preferred_release', lambda *a, **k: {'season': '2000-01', 'valid': False})
    with pytest.raises(ValueError, match='release validation failed'):
        batch.closeout(root, tmp_path / 'output', tmp_path)
    assert not (tmp_path / 'output').exists()


def test_closeout_rejects_qa_from_previous_recipe(tmp_path, monkeypatch):
    season = '2000-01'
    (tmp_path / season).mkdir()
    (tmp_path / season / 'ownership-plan.json').write_text(json.dumps({'updates': [], 'unresolved': []}))
    (tmp_path / season / 'qa-report.json').write_text(json.dumps({'inputs': {'package_sha256': 'old'}}))
    monkeypatch.setattr(batch.registry, 'supported_seasons', lambda: [season])
    monkeypatch.setattr(batch.registry, 'validate_preferred_release', lambda *a, **k: {'season': season, 'valid': True})
    monkeypatch.setattr(batch.registry, 'load_preferred_release', lambda s: SimpleNamespace(package_path=tmp_path))
    monkeypatch.setattr(batch.registry, 'sha256_file', lambda p: 'current')
    with pytest.raises(ValueError, match='QA is not bound'):
        batch.closeout(tmp_path, tmp_path / 'output', tmp_path)
    assert not (tmp_path / 'output').exists()


def test_closeout_retains_historical_failure_without_claiming_pass(tmp_path, monkeypatch):
    season = '2000-01'
    (tmp_path / season).mkdir()
    (tmp_path / season / 'ownership-plan.json').write_text(json.dumps({
        'updates': [], 'unresolved': [{'reason': 'identity-ambiguous'}]}))
    (tmp_path / season / 'qa-report.json').write_text(json.dumps({
        'inputs': {'package_sha256': 'current'}, 'result': 'fail',
        'blockers': [{'code': 'package-validation-failed'}]}))
    attestation = tmp_path / 'attestation.json'
    attestation.write_text(json.dumps({'runtime_receipts': [{
        'lineup_screenshot': 'lineup.png', 'lineup_screenshot_sha256': 'screenshot'}]}))
    readback = tmp_path / 'readback.json'
    readback.write_text(json.dumps({'seasons': [], 'players': 0}))
    reproduction = tmp_path / 'reproduction.json'
    reproduction.write_text(json.dumps({'seasons': [], 'players': 0,
        'compiler_path': 'scripts/compiler.py', 'compiler_sha256': 'current'}))
    release = SimpleNamespace(package_path=tmp_path / 'package.json', inventory_path=tmp_path / 'inventory.json',
        attestation_path=attestation, runtime_evidence_path=tmp_path / 'runtime',
        release_id='unchanged', manifest_sha256='manifest')
    monkeypatch.setattr(batch.registry, 'supported_seasons', lambda: [season])
    monkeypatch.setattr(batch.registry, 'validate_preferred_release', lambda *a, **k: {'season': season, 'valid': True})
    monkeypatch.setattr(batch.registry, 'load_preferred_release', lambda s: release)
    monkeypatch.setattr(batch.registry, 'sha256_file', lambda p: 'current')
    monkeypatch.setattr(batch.registry, 'relative_workspace_path', lambda p: str(p))
    result = batch.closeout(tmp_path, tmp_path / 'output', tmp_path,
                            native_readback=readback, native_reproduction=reproduction)
    assert result['full_release_validation_passed'] == 1
    assert result['historical_qa_passed'] == 0
    assert result['historical_qa_blockers'] == {'package-validation-failed': 1}
    assert result['unresolved_entries'] == 1
    assert result['releases'][0]['runtime_scope'] == 'unchanged-game-exact-existing-proof'


def test_quality_resume_retains_complete_failed_historical_audit(tmp_path, monkeypatch):
    def must_not_repeat_audit(*args, **kwargs):
        raise AssertionError('completed audit must not run again')
    monkeypatch.setattr(qa, 'audit_season', must_not_repeat_audit)
    monkeypatch.setattr(qa, 'audit_runtime', lambda season: {})
    season = '2000-01'
    (tmp_path / season).mkdir()
    report = {'inputs': {'package_sha256': 'current'}, 'result': 'fail',
              'checks': {key: {} for key in ('runtime', 'kits', 'compiled_managers', 'compiled_handling')},
              'blockers': [{'code': 'package-validation-failed'}]}
    (tmp_path / season / 'qa-report.json').write_text(json.dumps(report))
    monkeypatch.setattr(batch.registry, 'supported_seasons', lambda: [season])
    monkeypatch.setattr(batch.registry, 'load_preferred_release', lambda s: SimpleNamespace(package_path=tmp_path))
    monkeypatch.setattr(batch.registry, 'sha256_file', lambda p: 'current')
    monkeypatch.setattr(batch.registry, 'relative_workspace_path', lambda p: str(p))
    output = tmp_path / 'new'
    batch.resume_quality(tmp_path, output, 1)
    assert json.loads((output / season / 'qa-report.json').read_text()) == report
    assert json.loads((output / 'reuse-ledger.json').read_text())['retried_checker_executions'] == []


@pytest.mark.parametrize('completed', [False, True])
def test_rebase_reuses_exact_completed_slots_without_replanning(tmp_path, monkeypatch, completed):
    season = '2017-18'
    source_root = tmp_path / 'source'
    (source_root / season).mkdir(parents=True)
    before = {'id': 'slot', 'name': 'Old Player'}
    proposal = {'player_id': 'slot', 'before': before,
                'replacement': {'source_player': {'name': 'New Player', 'birth_date': '1990-01-01'}},
                'retained_owner_player_id': 'owner', 'owner_evidence': {'date': '2017-08-01'},
                'replacement_opening_evidence': {'date': '2017-08-12'}}
    source = {'release_id': 'old', 'package_sha256': 'hash', 'jug_sha256': 'hash',
              'updates': [proposal], 'summary': {'replacement_slots': 1}}
    (source_root / season / 'ownership-plan.json').write_text(json.dumps(source))
    current_row = ({'id': 'slot', 'source_name': 'New Player',
                    'facts': {'birth_date': '1990-01-01'}} if completed else before)
    package = tmp_path / 'package.json'
    package.write_text(json.dumps({'players': [current_row], 'artifacts': []}))
    proof = tmp_path / 'proof.json'
    proof.write_text(json.dumps({'updates': [proposal]}))
    old = SimpleNamespace(package_path=package, game_path=tmp_path / 'old')
    current = SimpleNamespace(package_path=package, game_path=tmp_path / 'current',
                              release_id='new', locator={'ownership_plan_path': 'proof.json'})
    monkeypatch.setattr(batch, 'ROOT', tmp_path)
    monkeypatch.setattr(batch.registry, 'supported_seasons', lambda: [season])
    monkeypatch.setattr(batch.registry, 'load_registered_release', lambda *a: old)
    monkeypatch.setattr(batch.registry, 'load_preferred_release', lambda *a: current)
    monkeypatch.setattr(batch.registry, 'sha256_file', lambda *a: 'hash')
    monkeypatch.setattr(batch.registry, 'relative_workspace_path', lambda p: str(p))
    output = tmp_path / 'output'
    batch.rebase_completed_plans(source_root, output)
    result = json.loads((output / season / 'ownership-plan.json').read_text())
    assert result['release_id'] == 'new'
    assert result['updates'] == ([] if completed else [proposal])
    assert len(result['continued_from']['completed_slots_not_rebuilt']) == int(completed)
    if completed:
        proof.write_text(json.dumps({'updates': []}))
        with pytest.raises(ValueError, match='exact completed correction proof'):
            batch.rebase_completed_plans(source_root, tmp_path / 'unproven')


def test_rebase_refuses_changed_club_context(tmp_path, monkeypatch):
    season = '2017-18'
    (tmp_path / season).mkdir()
    (tmp_path / season / 'ownership-plan.json').write_text(json.dumps({
        'release_id': 'old', 'package_sha256': 'hash', 'jug_sha256': 'hash'}))
    old = SimpleNamespace(package_path=tmp_path / 'old-package', game_path=tmp_path / 'old-game')
    current = SimpleNamespace(game_path=tmp_path / 'new-game')
    monkeypatch.setattr(batch.registry, 'supported_seasons', lambda: [season])
    monkeypatch.setattr(batch.registry, 'load_registered_release', lambda *a: old)
    monkeypatch.setattr(batch.registry, 'load_preferred_release', lambda *a: current)
    monkeypatch.setattr(batch.registry, 'sha256_file',
                        lambda p: 'changed' if p == current.game_path / 'DBDAT/EQ98030.FDI' else 'hash')
    with pytest.raises(ValueError, match='club/order/manager context changed'):
        batch.rebase_completed_plans(tmp_path, tmp_path / 'output')


def test_native_verification_never_overwrites_receipt(tmp_path):
    output = tmp_path / 'receipt.json'
    output.write_text('{}')
    with pytest.raises(ValueError, match='immutable'):
        batch.verify_native_batch(tmp_path, 'release', output)


def test_identity_audit_uses_original_names_dob_and_current_english_layer(tmp_path, monkeypatch):
    def player(carrier, source, display, country):
        return {'id': f'player-{carrier}', 'carrier_id': carrier, 'club_id': f'club-{carrier}',
                'source_name': source, 'name': display,
                'facts': {'birth_date': '1980-01-01', 'nationality': country}}
    stale = player(1, 'Someone Else', 'S. Else', 'ENG')
    main = {'players': [stale, player(2, 'Original Full Name', 'F. Name', 'XXX')]}
    english = {'players': [player(1, 'Original Full Name', 'Original Name', 'FRA')]}
    release = SimpleNamespace(package_path=tmp_path, release_id='current')
    monkeypatch.setattr(batch.registry, 'supported_seasons', lambda: ['2015-16'])
    monkeypatch.setattr(batch.registry, 'load_preferred_release', lambda s: release)
    monkeypatch.setattr(batch.registry, 'sha256_file', lambda p: 'hash')
    monkeypatch.setattr(batch.registry, 'relative_workspace_path', lambda p: str(p))
    monkeypatch.setattr(batch.planner, 'package_layers',
                        lambda r: [('main', main, tmp_path), ('english', english, tmp_path)])
    output = tmp_path / 'audit.json'
    result = batch.audit_current_identities(output)
    assert result['seasons'][0]['duplicate_candidate_groups'] == 1
    candidate = result['seasons'][0]['candidates'][0]
    assert candidate['source_name_key'] == 'originalfullname'
    assert {p['carrier_id'] for p in candidate['players']} == {1, 2}
    assert len(candidate['players']) == 2
    with pytest.raises(ValueError, match='immutable'):
        batch.audit_current_identities(output)
def test_quality_reuse_requires_current_runner_binding():
    from scripts.closeout_duplicate_ownership_batch_v1 import reusable_quality
    runtime = {'passed': True, 'artifact_root': 'new-proof', 'release_manifest_bound': True}
    report = {'inputs': {'package_sha256': 'same-recipe'},
        'checks': {'runtime': runtime, 'kits': {}, 'compiled_managers': {}, 'compiled_handling': {}},
        'blockers': [{'code': 'package-validation-failed'}]}
    assert reusable_quality(report, 'same-recipe', runtime)
    assert not reusable_quality(report, 'another-recipe', runtime)
    assert not reusable_quality(report, 'same-recipe', {**runtime, 'artifact_root': 'later-proof'})
    assert not reusable_quality(report, 'same-recipe', {**runtime, 'passed': False})
    report['blockers'].append({'code': 'qa-execution-error'})
    assert not reusable_quality(report, 'same-recipe', runtime)
