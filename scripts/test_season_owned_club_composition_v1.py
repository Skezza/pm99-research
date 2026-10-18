import copy
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import season_owned_club_composition_v1 as subject


def test_standalone_import_bootstraps_upstream_without_test_environment():
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    completed = subprocess.run([sys.executable, '-c',
        'from scripts import season_owned_club_composition_v1'],
        cwd=subject.registry.ROOT, env=env, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_retained_order_matches_sourced_native_order_without_other_changes():
    package = dict(clubs=[dict(id='kept', roster_player_ids=['p1', 'p2']),
                          dict(id='other', roster_player_ids=['p3'])],
                   players=[dict(id='p1', carrier_id=1, club_id='kept'),
                            dict(id='p2', carrier_id=2, club_id='kept'),
                            dict(id='p3', carrier_id=3, club_id='other')])
    expected = copy.deepcopy(package)
    expected['clubs'][0]['roster_player_ids'] = ['p2', 'p1']
    subject.bind_owned_order(package, 'kept', [2, 1])
    assert package == expected


@pytest.mark.parametrize('order', [[1], [1, 1], [1, 3], [1, 2, 3]])
def test_retained_order_cannot_change_fixed_ownership(order):
    package = dict(clubs=[dict(id='kept', roster_player_ids=['p1', 'p2'])],
                   players=[dict(id='p1', carrier_id=1, club_id='kept'),
                            dict(id='p2', carrier_id=2, club_id='kept')])
    original = copy.deepcopy(package)
    with pytest.raises(ValueError, match='exact owned roster'):
        subject.bind_owned_order(package, 'kept', order)
    assert package == original


@pytest.fixture
def private_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(subject.registry, 'ROOT', tmp_path)
    root = tmp_path / '.local'
    root.mkdir()
    game = root / 'parent/game'
    (game / 'DBDAT/MINIFOTO').mkdir(parents=True)
    for name in ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF'):
        (game / 'DBDAT' / name).write_bytes(b'unchanged ' + name.encode())
    (game / 'unrelated.txt').write_bytes(b'keep')
    (game / 'DBDAT/MINIFOTO/J9600007.BMP').write_bytes(b'old identity')
    package_path = root / 'parent/season-package.json'
    package_path.write_text('{}')
    for name in ('proposal.json', 'retained.json'):
        (root / name).write_text('{}')
    base = SimpleNamespace(season='2018-19', release_id='parent', manifest_sha256='f' * 64,
                           package_path=package_path, game_path=game,
                           inventory_path=root / 'parent/inventory.json')
    subject.pipeline.write_canonical_json(base.inventory_path, subject.pipeline.build_tree_inventory(game))
    files = {name: b'new ' + name.encode() for name in
             ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF')}
    package = dict(artifacts=[])
    proof = dict(compositions=[], changed_identity_carriers=[7], moves=[dict(source_carrier=8, destination_carrier=7)])
    monkeypatch.setattr(subject, 'compile_preflight', lambda *args: (copy.deepcopy(package), files, proof))
    monkeypatch.setattr(subject.whole.package_v2, 'validate_package', lambda *args: None)
    monkeypatch.setattr(subject.shutil, 'disk_usage', lambda _: SimpleNamespace(free=10 * 1024**3))
    return base, root, package, files


def test_private_materialisation_preserves_parent_and_serializes_operations(private_candidate):
    base, root, package, files = private_candidate
    before = {p.relative_to(base.game_path): p.read_bytes() for p in base.game_path.rglob('*') if p.is_file()}
    receipt = subject.materialise_private(base, root / 'proposal.json', root / 'retained.json', {}, root / 'candidate')
    assert receipt['native_files_written'] and not receipt['registered']
    assert not receipt['publication_authorised'] and not receipt['complete_SOURCE_replay_verified']
    assert before == {p.relative_to(base.game_path): p.read_bytes() for p in base.game_path.rglob('*') if p.is_file()}
    for name, payload in files.items():
        actual = root / 'candidate/game/DBDAT' / name
        assert actual.read_bytes() == payload
        assert actual.stat().st_ino != (base.game_path / 'DBDAT' / name).stat().st_ino
    assert not (root / 'candidate/game/DBDAT/MINIFOTO/J9600007.BMP').exists()
    transaction = subject.pipeline.read_json_file(root / 'candidate' / receipt['transaction_artifact'])
    assert transaction['compilation']['moves'] == [dict(source_carrier=8, destination_carrier=7)]
    assert not transaction['source_clearance']
    assert (root / 'candidate/game/unrelated.txt').stat().st_ino == (base.game_path / 'unrelated.txt').stat().st_ino


def test_materialisation_requires_verified_inputs_before_writing(private_candidate):
    base, root, package, _ = private_candidate
    package['artifacts'].append(dict(id='missing', relative_path='missing.json', sha256='0' * 64))
    with pytest.raises((ValueError, FileNotFoundError)):
        subject.materialise_private(base, root / 'proposal.json', root / 'retained.json', {}, root / 'candidate')
    assert not (root / 'candidate').exists()


def test_disk_guard_does_not_create_partial_candidate(private_candidate, monkeypatch):
    base, root, _, _ = private_candidate
    monkeypatch.setattr(subject.shutil, 'disk_usage', lambda _: SimpleNamespace(free=8 * 1024**3))
    with pytest.raises(ValueError, match='8-GiB reserve'):
        subject.materialise_private(base, root / 'proposal.json', root / 'retained.json', {}, root / 'candidate')
    assert not (root / 'candidate').exists()


def test_dirty_parent_inventory_refused_before_candidate_write(private_candidate):
    base, root, _, _ = private_candidate
    (base.game_path / 'unrelated.txt').write_bytes(b'unregistered change')
    with pytest.raises(subject.pipeline.PipelineError):
        subject.materialise_private(base, root / 'proposal.json', root / 'retained.json', {}, root / 'candidate')
    assert not (root / 'candidate').exists()


def test_candidate_cannot_overwrite_existing_output(private_candidate):
    base, root, _, _ = private_candidate
    output = root / 'candidate'
    output.mkdir()
    with pytest.raises(ValueError, match='new and immutable'):
        subject.materialise_private(base, root / 'proposal.json', root / 'retained.json', {}, output)


def test_candidate_cannot_escape_local_workspace(private_candidate):
    base, root, _, _ = private_candidate
    with pytest.raises(ValueError, match='local workspace'):
        subject.materialise_private(base, root / 'proposal.json', root / 'retained.json', {}, root.parent / 'outside')


def test_candidate_cannot_be_created_inside_protected_parent(private_candidate):
    base, root, _, _ = private_candidate
    with pytest.raises(ValueError, match='protected parent'):
        subject.materialise_private(base, root / 'proposal.json', root / 'retained.json', {}, base.game_path / 'nested')


@pytest.mark.parametrize('name', ['game/DBDAT/JUG98030.FDI', 'season-package.json', 'candidate-receipt.json', '../outside', '/outside'])
def test_artifacts_cannot_shadow_candidate_outputs(private_candidate, name):
    base, root, package, _ = private_candidate
    package['artifacts'].append(dict(id='shadow', relative_path=name, sha256='0' * 64))
    with pytest.raises(ValueError, match='artifact'):
        subject.materialise_private(base, root / 'proposal.json', root / 'retained.json', {}, root / 'candidate')
    assert not (root / 'candidate').exists()


def test_generated_artifact_must_match_recipe_hash(private_candidate, monkeypatch):
    base, root, package, files = private_candidate
    composition = dict(season=base.season)
    name = subject.whole.delta.plan_filename(composition)
    package['artifacts'].append(dict(id='generated', relative_path=name, sha256='0' * 64))
    monkeypatch.setattr(subject, 'compile_preflight', lambda *args: (
        package, files, dict(compositions=[composition], changed_identity_carriers=[])))
    with pytest.raises(ValueError, match='generated recipe artifact'):
        subject.materialise_private(base, root / 'proposal.json', root / 'retained.json', {}, root / 'candidate')
    assert not (root / 'candidate').exists()


def test_unsourced_keeper_role_is_refused_before_native_parse():
    with pytest.raises(ValueError, match='sourced goalkeeper'):
        subject.sourced_keeper_role(b'', 1, 'M')


def test_factory_compile_cannot_silently_ignore_retained_transaction():
    with pytest.raises(ValueError, match='source reconstruction'):
        subject.reject_factory_recipe(dict(artifacts=[dict(id=subject.PREFIX + 'example')]))
    subject.reject_factory_recipe(dict(artifacts=[]))


def test_saved_transaction_replay_uses_canonical_json_not_python_key_types(private_candidate, monkeypatch):
    base, root, package, files = private_candidate
    proof = dict(compositions=[], changed_identity_carriers=[], photo_offsets={7: []})
    monkeypatch.setattr(subject, 'compile_preflight', lambda *args: (copy.deepcopy(package), files, proof))
    target = root / 'candidate'
    subject.materialise_private(base, root / 'proposal.json', root / 'retained.json', {}, target)
    monkeypatch.setattr(subject, 'verify_materialised', lambda *args: dict(observations=[]))
    result = subject.replay_materialised(base, target)
    assert result['saved_transaction_recipe_identical']
    assert result['saved_transaction_native_files_identical']
    assert not result['complete_SOURCE_replay_verified']
    changed_files = dict(files, **{'JUG98030.FDI': b'not the same output'})
    monkeypatch.setattr(subject, 'compile_preflight', lambda *args: (copy.deepcopy(package), changed_files, proof))
    with pytest.raises(ValueError, match='native files do not exactly replay'):
        subject.replay_materialised(base, target)


def test_registered_reconstruction_does_not_claim_other_transaction_types(tmp_path):
    assert subject.reconstruction(SimpleNamespace(compiler_receipt_path=None), 'unused') is None
    path = tmp_path / 'compiler.json'
    path.write_text('{"schema": "other", "compilation_mode": "other"}')
    assert subject.reconstruction(SimpleNamespace(compiler_receipt_path=path), 'unused') is None


def test_registered_reconstruction_never_discards_edited_recipe(tmp_path):
    compiler = tmp_path / 'compiler.json'
    recipe = tmp_path / 'season-package.json'
    recipe.write_text('{}')
    compiler.write_text(subject.pipeline.canonical_json_bytes(dict(
        schema=subject.REGISTERED_SCHEMA, compilation_mode=subject.MODE,
        season_package_sha256='0' * 64)).decode())
    with pytest.raises(ValueError, match='edited retained recipe'):
        subject.reconstruction(SimpleNamespace(compiler_receipt_path=compiler, package_path=recipe), 'unused')


def test_original_mannion_keeper_role_is_corrected_without_other_field_drift():
    from app.fdi_indexed import IndexedFDIFile
    try:
        base = subject.registry.load_registered_release('2018-19', 'sourced-barnet-original-opening-20261017-r143a')
    except (ValueError, OSError):
        pytest.skip('local registered original 2018 native fixture unavailable')
    original = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(original).entries}
    payload = entries[11315].decode_payload(original)
    person, before = subject.transfer.read(payload, 11315)
    changed, proof = subject.sourced_keeper_role(payload, 11315, 'G')
    assert proof['before_codes'] == [6, 98, 98, 98, 98, 98]
    assert proof['after_codes'] == [0, 98, 98, 98, 98, 98]
    assert changed[:person['name_end'] + 2] == payload[:person['name_end'] + 2]
    assert changed[person['name_end'] + 8:] == payload[person['name_end'] + 8:]
    assert subject.sourced_keeper_role(changed, 11315, 'G') == (changed, None)
    with pytest.raises(ValueError, match='native broad position'):
        subject.sourced_keeper_role(entries[11043].decode_payload(original), 11043, 'G')
