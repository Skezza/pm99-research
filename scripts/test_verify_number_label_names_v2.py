import copy
from types import SimpleNamespace

import pytest

from scripts import season_pipeline_v2 as pipeline
from scripts import verify_number_label_names_v2 as verifier
from scripts.test_season_number_label_names_v2 import example


def fixture(tmp_path, monkeypatch):
    jug, plan = example()
    plan['release_id'] = 'base'
    plan_path = tmp_path / 'plan.json'
    pipeline.write_canonical_json(plan_path, plan)
    package = dict(players=[copy.deepcopy(plan['updates'][0]['before_player'])], clubs=[], artifacts=[])
    releases = {}
    for rid, raw, recipe in [('base', jug, package),
            ('candidate', verifier.source.apply(jug, plan), verifier.source.bind(package, plan))]:
        root = tmp_path / rid
        game = root / 'game'
        (game / 'DBDAT').mkdir(parents=True)
        (game / 'DBDAT/JUG98030.FDI').write_bytes(raw)
        (game / 'MANAGPRE.EXE').write_bytes(b'same executable')
        (game / 'DBDAT/RIDIESC.PKF').write_bytes(b'same kit')
        (game / 'DBDAT/MINIFOTO/J9600002.BMP').parent.mkdir()
        (game / 'DBDAT/MINIFOTO/J9600002.BMP').write_bytes(b'same actual portrait')
        package_path, inventory_path = root / 'recipe.json', root / 'inventory.json'
        pipeline.write_canonical_json(package_path, recipe)
        pipeline.write_canonical_json(inventory_path, pipeline.build_tree_inventory(game))
        releases[rid] = SimpleNamespace(game_path=game, package_path=package_path,
            release_id=rid, inventory_path=inventory_path, locator=dict(sourced_player_name_only_plan_path='plan.json'))
    monkeypatch.setattr(verifier.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(verifier.registry, 'load_registered_release', lambda season, rid: releases[rid])
    monkeypatch.setattr(verifier.source, 'verify', lambda *args: None)
    return releases, plan_path, tmp_path / 'proof.json'


def test_independent_all_game_native_suffix_recipe_and_birthday_proof(tmp_path, monkeypatch):
    releases, plan, output = fixture(tmp_path, monkeypatch)
    result = verifier.verify('2020-21', 'candidate', plan, output)
    assert result['birth_years_repaired'] == 1
    assert result['after_birthday_disagreements'] == 0
    assert result['original_surname_components_preserved']
    with pytest.raises(ValueError, match='immutable'):
        verifier.verify('2020-21', 'candidate', plan, output)


@pytest.mark.parametrize('fault', ['skill', 'other-player', 'kit', 'portrait', 'exe', 'recipe-fact', 'surname'])
def test_undeclared_changes_fail_independently(tmp_path, monkeypatch, fault):
    releases, plan, output = fixture(tmp_path, monkeypatch)
    candidate = releases['candidate']
    if fault in ('skill', 'other-player', 'surname'):
        path = candidate.game_path / 'DBDAT/JUG98030.FDI'
        raw = bytearray(path.read_bytes())
        entries = {e.record_id: e for e in verifier.IndexedFDIFile.from_bytes(raw).entries}
        entry = entries[4 if fault == 'other-player' else 2]
        offset = (entry.payload_offset + entry.payload_length - 20 if fault != 'surname'
            else entry.payload_offset + 10)
        raw[offset] ^= 1
        path.write_bytes(raw)
        # Rebind the synthetic inventory: verifier must catch the scope drift,
        # not merely an obsolete hash in the fixture's inventory.
        candidate.inventory_path.unlink()
        pipeline.write_canonical_json(candidate.inventory_path, pipeline.build_tree_inventory(candidate.game_path))
    elif fault == 'recipe-fact':
        recipe = pipeline.read_json_file(candidate.package_path)
        recipe['players'][0]['facts']['quality'] = 99
        candidate.package_path.unlink()
        pipeline.write_canonical_json(candidate.package_path, recipe)
    else:
        path = candidate.game_path / {'kit': 'DBDAT/RIDIESC.PKF',
            'portrait': 'DBDAT/MINIFOTO/J9600002.BMP', 'exe': 'MANAGPRE.EXE'}[fault]
        path.write_bytes(b'changed')
        candidate.inventory_path.unlink()
        pipeline.write_canonical_json(candidate.inventory_path, pipeline.build_tree_inventory(candidate.game_path))
    with pytest.raises(ValueError):
        verifier.verify('2020-21', 'candidate', plan, output)
    assert not output.exists()
