import copy

import pytest

from scripts import reconcile_2015_recipe_manager_graph_v1 as repair


def fixture_graph():
    package = {'season': {'start_year': 2015, 'end_year': 2016}, 'players': [{'id': 'player-27'}],
               'clubs': [{'id': 'club-1', 'carrier_id': 1, 'name': 'Barcelona', 'manager_id': 'manager-1069'},
                         {'id': 'club-8800', 'carrier_id': 8800, 'name': 'Special', 'manager_id': 'manager-548'},
                         {'id': 'club-8801', 'carrier_id': 8801, 'name': 'Other', 'manager_id': 'manager-548'}],
               'managers': [{'id': 'manager-1069', 'carrier_id': 1069, 'name': 'Luis Enrique'}],
               'assets': {'portraits': []}}
    holders = {3: [{'carrier_id': 1}], 4: [{'carrier_id': 335}],
               548: [{'carrier_id': 8800}, {'carrier_id': 8801}]}
    names = {3: 'Luis Enrique', 4: 'Mark Hughes', 548: 'Preserved'}
    plan = {'season': '2015-16', 'targets': [
        {'team_carrier_id': 1, 'manager_carrier_id': 3, 'manager_name': 'Luis Enrique', 'scope': 'foreign', 'source_status': 'synthetic-dated-source'},
        {'team_carrier_id': 335, 'manager_carrier_id': 4, 'manager_name': 'Mark Hughes', 'scope': 'english', 'source_status': 'synthetic-dated-source'}],
        'preserved_non_club_links': [{'team_carrier_id': c, 'manager_carrier_id': 548} for c in (8800, 8801)]}
    return package, holders, names, plan


def test_aligns_record_identity_not_just_visible_manager_name():
    package, holders, names, plan = fixture_graph()
    original = copy.deepcopy(package)
    result, changes = repair.align_package(package, holders, names, plan)
    assert package == original
    assert changes == [{'club_id': 'club-1', 'club_carrier_id': 1, 'before': 'manager-1069',
                        'after': 'manager-3', 'native_manager_name': 'Luis Enrique'}]
    assert result['clubs'][0]['manager_id'] == 'manager-3'
    assert {m['carrier_id'] for m in result['managers']} == {3, 548}
    assert result['players'] == original['players']
    assert result['assets'] == original['assets']
    assert result['managers'][0]['policy'] == 'write'
    assert result['managers'][1]['policy'] == 'preserve-existing-mode1'
    assert result['managers'][1]['proof']['grade'] == 'static-contract'
    # No invented historical person IDs to silence identity validation.
    assert all('person_id' not in manager for manager in result['managers'])
    assert repair.align_package(result, holders, names, plan) == (result, [])


@pytest.mark.parametrize('defect', ['wrong_name', 'wrong_owner', 'shared_sourced_owner',
                                  'wrong_english_name', 'missing_special', 'extra_foreign',
                                  'duplicate_source_target'])
def test_refuses_unbound_or_changed_graph(defect):
    package, holders, names, plan = fixture_graph()
    if defect == 'wrong_name': names[3] = 'Wrong'
    if defect == 'wrong_owner': holders[99] = holders.pop(3)
    if defect == 'shared_sourced_owner': holders[3].append({'carrier_id': 1001})
    if defect == 'wrong_english_name': names[4] = 'Wrong English Coach'
    if defect == 'missing_special': holders.pop(548)
    if defect == 'extra_foreign': package['clubs'].append({'carrier_id': 999})
    if defect == 'duplicate_source_target': plan['targets'].append(plan['targets'][0])
    with pytest.raises(ValueError):
        repair.align_package(package, holders, names, plan)


def test_qa_reuses_dated_graph_only_when_recipe_native_and_evidence_match(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import pm99_season_qa_v1 as qa
    package, holders, names, plan = fixture_graph()
    package, _ = repair.align_package(package, holders, names, plan)
    document = {'schema_version': repair.SCHEMA, 'season': '2015-16', 'source_bindings': [],
                'dated_foreign_managers': [plan['targets'][0]]}
    path = tmp_path / 'manager-graph-reconciliation.json'
    qa.pipeline_v2.write_canonical_json(path, document)
    package['artifacts'] = [{'id': repair.ARTIFACT, 'relative_path': path.name,
        'sha256': repair.hashlib.sha256(qa.pipeline_v2.canonical_json_bytes(document)).hexdigest()}]
    release = SimpleNamespace(package_path=tmp_path / 'package.json', game_path=tmp_path)
    monkeypatch.setattr(qa.release_registry, 'load_preferred_release', lambda season: release)
    monkeypatch.setattr(repair, 'checked_inputs', lambda release: (plan, []))
    monkeypatch.setattr(qa, '_manager_graph', lambda **kwargs: (holders, names))
    rows, _ = qa.verified_manager_plan_rows('2015-16', package)
    assert rows['club-1']['carrier_id'] == 3
    assert rows['club-8800']['out_of_scope_non_club'] is True
    assert 'after' not in rows['club-8800']  # No dated coach is claimed.
    package['clubs'][0]['manager_id'] = 'manager-1069'
    with pytest.raises(qa.QaError, match='declarations differ'):
        qa.verified_manager_plan_rows('2015-16', package)
    path.write_text('{}')
    with pytest.raises(qa.QaError, match='hash/schema'):
        qa.verified_manager_plan_rows('2015-16', package)


def test_native_aliases_do_not_replace_canonical_dated_identity():
    package, holders, names, plan = fixture_graph()
    package, _ = repair.align_package(package, holders, names, plan)
    declaration = next(m for m in package['managers'] if m['carrier_id'] == 3)
    declaration['native_names'] = {'surname': 'Enrique', 'display_name': 'Enrique'}
    names[3] = 'Enrique'
    result, changes = repair.align_package(package, holders, names, plan, native_aliases={3: declaration})
    assert not changes
    assert result == package
    declaration['name'] = 'Wrong Enrique'
    with pytest.raises(ValueError, match='different dated canonical'):
        repair.align_package(package, holders, names, plan, native_aliases={3: declaration})


def test_alias_cannot_hide_a_wrong_native_manager():
    package, holders, names, plan = fixture_graph()
    package, _ = repair.align_package(package, holders, names, plan)
    declaration = next(m for m in package['managers'] if m['carrier_id'] == 3)
    declaration['native_names'] = {'surname': 'Enrique', 'display_name': 'Enrique'}
    names[3] = 'Not Enrique'
    with pytest.raises(ValueError, match='exclusive ownership'):
        repair.align_package(package, holders, names, plan, native_aliases={3: declaration})
