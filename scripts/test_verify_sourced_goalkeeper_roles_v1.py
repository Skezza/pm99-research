"""Adversarial synthetic readback tests; no proprietary game inputs."""
import copy
import json
from types import SimpleNamespace

import pytest
from app.fdi_indexed import IndexedFDIFile
from scripts import verify_sourced_goalkeeper_roles_v1 as module
from scripts.test_season_package_compiler_v2 import _indexed_fdi, _dd6361_player_payload


def setup(tmp_path, monkeypatch):
    payload = bytearray(_dd6361_player_payload(2, role=3))
    end = module.audit.native_player(bytes(payload), 2)['name_end']
    payload[end + 11] = 0 ^ 0x61  # Literal native G, with copied outfield role.
    before = _indexed_fdi([(2, '', bytes(payload))])
    entry = IndexedFDIFile.from_bytes(before).entries[0]
    offset = entry.payload_offset + end + 2
    after = bytearray(before)
    after[offset:offset+6] = bytes([1, 0, 0, 0, 0, 0])
    package = {'players': [{'id': 'keeper', 'facts': {'fine_roles': [3], 'quality': 50}}],
               'clubs': [{'id': 'club'}], 'artifacts': [], 'proofs': []}
    modified = copy.deepcopy(package)
    modified['players'][0]['facts']['fine_roles'] = [0]
    plan = {'release_id': 'baseline', 'updates': [{'player_id': 'keeper', 'carrier_id': 2}]}
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps(plan))
    releases = {}
    for name, jug, document in [('baseline', before, package), ('repair', bytes(after), modified)]:
        game = tmp_path / name / 'game'
        (game / 'DBDAT').mkdir(parents=True)
        for filename in ('EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF', 'RIDIESC.PKF', 'MINIESC.PKF', 'NANOESC.PKF'):
            (game / 'DBDAT' / filename).write_bytes(b'identical synthetic archive')
        (game / 'MANAGPRE.EXE').write_bytes(b'identical synthetic executable')
        (game / 'DBDAT/JUG98030.FDI').write_bytes(jug)
        package_path = tmp_path / name / 'package.json'
        package_path.write_text(json.dumps(document))
        releases[name] = SimpleNamespace(game_path=game, package_path=package_path, release_id=name,
            locator={'historical_role_plan_path': 'plan.json'})
    monkeypatch.setattr(module.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(module.registry, 'load_registered_release', lambda season, release: releases[release])
    monkeypatch.setattr(module.source, 'verify', lambda release, plan: None)
    return releases, plan_path, tmp_path / 'proof.json', offset


def test_exact_native_and_recipe_delta_passes(tmp_path, monkeypatch):
    releases, plan, output, offset = setup(tmp_path, monkeypatch)
    result = module.verify('2000-01', 'repair', plan, output)
    assert result['corrected_goalkeeper_labels'] == 1
    assert result['all_other_native_bytes_identical']
    with pytest.raises(ValueError, match='immutable'):
        module.verify('2000-01', 'repair', plan, output)


@pytest.mark.parametrize('drift', ['role', 'other-native-byte', 'file-length', 'archive', 'executable',
                                  'rating', 'club', 'evidence', 'saved-plan'])
def test_unrelated_or_incorrect_delta_refuses(tmp_path, monkeypatch, drift):
    releases, plan, output, offset = setup(tmp_path, monkeypatch)
    release = releases['repair']
    if drift in ('role', 'other-native-byte', 'file-length'):
        target = release.game_path / 'DBDAT/JUG98030.FDI'
        data = bytearray(target.read_bytes())
        if drift == 'role': data[offset] = 4
        elif drift == 'other-native-byte': data[-1] ^= 1
        else: data.append(0)
        target.write_bytes(data)
    elif drift == 'archive':
        (release.game_path / 'DBDAT/MINIFOTO.PKF').write_bytes(b'wrong archive')
    elif drift == 'executable':
        (release.game_path / 'MANAGPRE.EXE').write_bytes(b'wrong executable')
    elif drift == 'saved-plan':
        saved = tmp_path / 'different-plan.json'; saved.write_text('{}')
        release.locator['historical_role_plan_path'] = saved.name
    else:
        document = json.loads(release.package_path.read_text())
        if drift == 'rating': document['players'][0]['facts']['quality'] = 99
        elif drift == 'club': document['clubs'][0]['id'] = 'another-club'
        else: document['proofs'].append({'id': 'unrelated-proof'})
        release.package_path.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        module.verify('2000-01', 'repair', plan, output)
    assert not output.exists()
