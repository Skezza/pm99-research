import json
from types import SimpleNamespace
import pytest

from scripts import verify_within_club_reserve_runtime_v1 as verify
from scripts import season_within_club_reserve_repair_v1 as source
from scripts import season_release_registry_v1 as registry


@pytest.fixture
def sample(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, 'ROOT', tmp_path)
    monkeypatch.setattr(registry, 'relative_workspace_path', lambda p: str(p.relative_to(tmp_path)))
    plan = tmp_path / 'ownership.json'
    plan.write_text(json.dumps({'schema_version': source.SCHEMA, 'release_id': 'prior',
        'updates': [{'carrier_id': 1}]}))
    package = tmp_path / 'package.json'
    package.write_text(json.dumps({'players': [{'carrier_id': 1, 'source_name': 'Lee Feeney',
        'name': 'Feeney', 'club_id': 'club-1'}], 'clubs': [{'id': 'club-1', 'name': 'Rangers'}]}))
    game = tmp_path / 'game'; (game / 'DBDAT').mkdir(parents=True)
    names = ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF',
        'RIDIESC.PKF', 'MINIESC.PKF', 'NANOESC.PKF')
    for name in names:
        (game / 'DBDAT' / name).write_bytes(name.encode())
    receipt = tmp_path / 'compiler.json'; receipt.write_text('{}')
    evidence = tmp_path / 'evidence'; (evidence / 'screens').mkdir(parents=True)
    (evidence / 'input-provenance.json').write_bytes(receipt.read_bytes())
    (evidence / 'dbdat_override.sha256').write_text('\n'.join(
        registry.sha256_file(game / 'DBDAT' / name) + '  DBDAT/' + name for name in names))
    shot = evidence / 'screens/profile.png'; shot.write_bytes(b'test-original-frame')
    summary = {'success': True, 'player_profile': {'screenshot': '/remote/profile.png',
        'expected_name_token_satisfied': True, 'player_name_ocr_normalized': 'feeney'}}
    (evidence / 'summary.json').write_text(json.dumps(summary))
    review = tmp_path / 'visual.json'
    review.write_text(json.dumps({'method': 'assistant-original-image-visual-review',
        'screenshot_sha256': registry.sha256_file(shot), 'observed_club': 'Rangers'}))
    release = SimpleNamespace(season='2000-01', release_id='new', game_path=game,
        package_path=package, compiler_receipt_path=receipt, locator={'ownership_plan_path': 'ownership.json'})
    monkeypatch.setattr(registry, 'load_registered_release', lambda *args: release)
    monkeypatch.setattr(source, 'verify_plan', lambda *args: None)
    return release, evidence, review, tmp_path / 'proof.json'


def test_exact_native_and_original_named_profile_bind(sample):
    proof = verify.verify(*sample)
    assert proof['club'] == 'Rangers' and proof['native_inputs_hash_verified'] is True


def test_coupled_profile_requires_exact_selected_source_plan_actor(sample,monkeypatch):
    from scripts import season_shtanyuk_2002_coupled_alias_v1 as coupled
    release,evidence,review,output=sample
    plan=registry.ROOT/'ownership.json'
    plan.write_text(json.dumps(dict(schema_version=coupled.SCHEMA,release_id='prior',
        updates=[dict(carrier_id=1),dict(carrier_id=2)])))
    called=[]
    monkeypatch.setattr(coupled,'verify_plan',lambda *args:called.append(True))
    with pytest.raises(ValueError,match='explicitly selected'):
        verify.verify(*sample)
    with pytest.raises(ValueError,match='explicitly selected'):
        verify.verify(*sample,carrier=3)
    proof=verify.verify(*sample,carrier=1)
    assert proof['carrier_id']==1 and called==[True,True,True]


@pytest.mark.parametrize('field,value', [('success', False), ('wine_debugger_detected', True),
                                       ('process_exit_code', 1)])
def test_failed_runner_never_passes(sample, field, value):
    path = sample[1] / 'summary.json'; doc = json.loads(path.read_text())
    doc[field] = value; path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='successfully'):
        verify.verify(*sample)


@pytest.mark.parametrize('change', ['club', 'frame', 'native', 'provenance', 'name'])
def test_wrong_person_club_game_frame_and_provenance_refused(sample, change):
    release, evidence, review, _ = sample
    if change == 'club':
        doc = json.loads(review.read_text()); doc['observed_club'] = 'Celtic'; review.write_text(json.dumps(doc))
    elif change == 'frame':
        (evidence / 'screens/profile.png').write_bytes(b'another-frame')
    elif change == 'native':
        (release.game_path / 'DBDAT/JUG98030.FDI').write_bytes(b'another-game')
    elif change == 'provenance':
        (evidence / 'input-provenance.json').write_text('{"other":true}')
    else:
        path = evidence / 'summary.json'; doc = json.loads(path.read_text())
        doc['player_profile']['player_name_ocr_normalized'] = 'W Feeney'; path.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        verify.verify(*sample)
