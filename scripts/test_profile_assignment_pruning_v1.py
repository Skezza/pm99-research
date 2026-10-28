import copy
from types import SimpleNamespace

import pytest

from scripts import review_profile_addition_duplicate_assignments_v1 as source
from scripts import season_profile_assignment_pruning_layer_v1 as layer


def pair():
    annual = dict(name='İlhan Mansız', birth_date=None, shirt_number=26)
    added = dict(annual, name='Ilhan Mansiz', birth_date='1975-08-10')
    rows = [dict(facts=annual, source_row_sha256='a'),
        dict(facts=added, source_row_sha256='b', opening_source_player_id='6875',
             opening_xi_origin='profiled-first-fixture-addition')]
    people = [dict(person_id='person-source-a', source_name='İlhan Mansız',
                   facts={'birth_date': {'policy': 'preserve-existing-mode1'}}),
              dict(person_id='person-source-b', source_name='Ilhan Mansiz',
                   facts={'birth_date': '1975-08-10'})]
    profile = dict(published_full_name='İlhan Mansız', source_player_id='6875',
                   published_birth_date='1975-08-10')
    return people, rows, [annual], profile


def test_annual_shirt_and_positive_numeric_profile_prove_exact_input_collision():
    people, rows, annual, profile = pair()
    assert source.prove_projection_pair(people, rows, annual, profile, 26) == (people[1], people[0])


@pytest.mark.parametrize('problem', ['shirt', 'real-namesake', 'duplicate-annual', 'other-id',
    'other-source-hash', 'other-profile-birthday', 'other-recipe-birthday', 'other-name', 'modified-annual'])
def test_name_or_missing_birthday_alone_cannot_authorize_deletion(problem):
    people, rows, annual, profile = copy.deepcopy(pair())
    shirt = 26
    if problem == 'shirt': shirt = 4
    if problem == 'real-namesake': annual[0]['birth_date'] = '1977-12-17'
    if problem == 'duplicate-annual': annual.append(copy.deepcopy(annual[0]))
    if problem == 'other-id': rows[1]['opening_source_player_id'] = 'other'
    if problem == 'other-source-hash': people[0]['person_id'] = 'person-source-unknown'
    if problem == 'other-profile-birthday': profile['published_birth_date'] = '1977-12-17'
    if problem == 'other-recipe-birthday': people[1]['facts']['birth_date'] = '1977-12-17'
    if problem == 'other-name': people[0]['source_name'] = 'Another Mansiz'
    if problem == 'modified-annual': rows[0]['facts'] = dict(annual[0], shirt_number=27)
    with pytest.raises(ValueError): source.prove_projection_pair(people, rows, annual, profile, shirt)


def match(club=114, id=6875, shirt=26):
    return f'''<div class="large-6"><a href="/besiktas/startseite/verein/{club}">Club</a>
    <div class="formation-player-container"><span class="tm-shirt-number">{shirt}</span>
    <a href="/ilhan-mansiz/profil/spieler/{id}">Mansız</a></div></div>'''


def test_match_shirt_requires_exact_original_club_and_numeric_identity():
    assert source.first_match_shirt(match(), 114, '6875') == 26
    for html, club, id in [(match(), 11, '6875'), (match(), 114, '687'),
                          (match()+match(), 114, '6875'), (match(shirt='?'), 114, '6875')]:
        with pytest.raises(ValueError): source.first_match_shirt(html, club, id)


def example():
    bad = dict(id='bad', carrier_id=99, club_id='club')
    keep = dict(id='keep', carrier_id=98, club_id='club')
    package = dict(players=[bad, keep, {'id': 'unrelated'}],
        clubs=[dict(id='club', carrier_id=1001, roster_player_ids=['bad', 'keep']),
               dict(id='other', roster_player_ids=['unrelated'])],
        artifacts=[], portraits=[dict(player_id='bad'), dict(player_id='keep')])
    review = dict(schema=source.SCHEMA, season='2001-02', release_id='baseline',
        package_sha256='package', jug_sha256=layer.digest(b'jug'), eq_sha256=layer.digest(b'eq'),
        club_id='club', club_carrier_id=1001, removed_player=bad, retained_player=keep,
        native_before={'99': {'startup_order': 17}},
        native_roster_before=[[i, 0] for i in range(83, 100)],
        duplicate_input_assignment_proved=True, removed_is_current_native_starter=False)
    plan = dict(schema=layer.SCHEMA, season='2001-02', release_id='baseline',
        package_sha256='package', package_canonical_sha256=layer.digest(layer.packages.canonical_json_bytes(package)),
        jug_sha256=layer.digest(b'jug'), eq_sha256=layer.digest(b'eq'), reviews=[review])
    return package, plan


def test_recipe_delta_removes_exact_assignment_preserving_every_other_person(monkeypatch):
    package, plan = example()
    monkeypatch.setattr(layer.packages, 'validate_package', lambda _: None)
    result = layer.bind(package, plan)
    assert len(package['players']) == 3  # no mutation
    assert result['players'] == package['players'][1:]
    assert result['clubs'][0]['roster_player_ids'] == ['keep']
    assert result['clubs'][1] == package['clubs'][1]
    assert result['portraits'] == [{'player_id': 'keep'}]
    assert result['artifacts'][0]['sha256'] == layer.digest(layer.packages.canonical_json_bytes(plan))


@pytest.mark.parametrize('problem', ['starter', 'order', 'baseline', 'repeat', 'overlap', 'short-squad', 'unproved'])
def test_reserve_policy_rejects_starters_ambiguous_identity_and_forged_baselines(problem):
    _, plan = example()
    r = plan['reviews'][0]
    if problem == 'starter': r['removed_is_current_native_starter'] = True
    if problem == 'order': r['native_before']['99']['startup_order'] = 11
    if problem == 'baseline': r['eq_sha256'] = 'other'
    if problem == 'repeat': plan['reviews'].append(copy.deepcopy(r))
    if problem == 'overlap': r['retained_player']['carrier_id'] = 99
    if problem == 'short-squad': r['native_roster_before'] = r['native_roster_before'][1:]
    if problem == 'unproved': r['duplicate_input_assignment_proved'] = False
    with pytest.raises(ValueError): layer.groups(plan)


def test_recipe_edits_fail_closed_before_pruning(monkeypatch):
    package, plan = example()
    package['players'][1]['name'] = 'edited'
    with pytest.raises(ValueError, match='whole reserve recipe'): layer.bind(package, plan)


def test_apply_never_accepts_a_changed_player_database():
    _, plan = example()
    with pytest.raises(ValueError, match='native player file'): layer.apply(b'changed jug', b'eq', plan)


def test_source_review_is_rederived_not_accepted_by_receipt_label(monkeypatch):
    _, plan = example()
    plan['fixed_cases'] = [{'id': 'case'}]
    monkeypatch.setattr(layer, 'prepare', lambda r, c: dict(plan, reviews=[]))
    with pytest.raises(ValueError, match='no longer reproduces'): layer.verify(SimpleNamespace(), plan)


def test_factory_compile_cannot_silently_drop_pruning():
    with pytest.raises(ValueError, match='must not drop'):
        layer.reject_factory_recipe({'artifacts': [{'id': layer.PREFIX+'2001-02'}]})


def test_original_annual_numeric_id_proves_identity_despite_different_shirt():
    people, rows, annual, profile = pair()
    assert source.prove_projection_pair(people, rows, annual, profile, 52,
        numeric_identity={'source_player_id': '6875'}) == (people[1], people[0])
    with pytest.raises(ValueError, match='numeric identities differ'):
        source.prove_projection_pair(people, rows, annual, profile, 52,
            numeric_identity={'source_player_id': '687'})


def test_annual_numeric_identity_requires_exact_full_id_name_and_single_row():
    raw = '''<table class="items"><tbody><tr><td class="hauptlink">
    <a href="/omer-kilic/profil/spieler/6115">Ömer Kılıç</a>
    </td></tr></tbody></table>'''
    assert source.annual_numeric_identity(raw, 'Ömer Kılıç', '6115')['source_player_id'] == '6115'
    for html, name, id in [(raw, 'Ömer Kılıç', '611'), (raw, 'Another Kılıç', '6115'),
                          (raw + raw, 'Ömer Kılıç', '6115')]:
        with pytest.raises(ValueError): source.annual_numeric_identity(html, name, id)


def test_followup_layer_has_distinct_filename_without_dropping_previous_artifact(monkeypatch):
    package, plan = example()
    package['artifacts'] = [dict(id=layer.PREFIX+'2001-02', relative_path=layer.FILENAME)]
    plan['package_canonical_sha256'] = layer.digest(layer.packages.canonical_json_bytes(package))
    plan['layer_suffix'] = '0123456789ab'
    monkeypatch.setattr(layer.packages, 'validate_package', lambda _: None)
    result = layer.bind(package, plan)
    assert package['artifacts'][0] in result['artifacts']
    assert len({a['relative_path'] for a in result['artifacts']}) == 2
    assert layer.filename(plan) == 'sourced-profile-assignment-pruning-0123456789ab.json'


def test_idempotence_refuses_unrelated_postimage_edits(tmp_path, monkeypatch):
    _, plan = example()
    game = tmp_path / 'game'
    (game / 'DBDAT').mkdir(parents=True)
    (game / 'DBDAT/EQ98030.FDI').write_bytes(b'eq')
    before = layer.groups(plan)[1001]['before']
    after = layer.groups(plan)[1001]['after']
    monkeypatch.setattr(layer.registry, 'load_registered_release', lambda *a: SimpleNamespace(game_path=game))
    monkeypatch.setattr(layer.native, 'roster_rows', lambda raw, id: (None, b'payload', before if raw == b'eq' else after))
    monkeypatch.setattr(layer, 'prune_visible_mode1_roster_payload', lambda *a, **k: b'payload')
    monkeypatch.setattr(layer.compiler, '_rebuild_indexed', lambda *a: b'exact-after')
    monkeypatch.setattr(layer, 'preserve_other_records', lambda *a: None)
    assert layer.apply(b'jug', b'exact-after', plan) == (b'jug', b'exact-after')
    with pytest.raises(ValueError, match='unrelated native changes'):
        layer.apply(b'jug', b'tampered-after', plan)


def source_selection_example():
    ids = list(range(83, 100))
    actors = [dict(id=f'p-{id}', carrier_id=id, club_id='club',
                   policy='preserve-existing-mode1' if id == 99 else 'write') for id in ids]
    package = dict(players=actors, clubs=[dict(id='club', carrier_id=1001,
        roster_player_ids=[a['id'] for a in actors])], artifacts=[],
        assets={'portraits': [dict(player_id=a['id']) for a in actors]})
    review = dict(case_id='source-selection', club_id='club', club_carrier_id=1001,
        native_roster_before=[[id, 0] for id in ids] + [[1000, 1]],
        supported_native_ids=list(range(83, 99)), sourced_xi_native_ids=list(range(83, 94)),
        removed_player_carrier_ids=[99])
    plan = dict(schema=layer.SCHEMA, policy=layer.SOURCE_SELECTION, season='2001-02',
        package_canonical_sha256=layer.digest(layer.packages.canonical_json_bytes(package)),
        reviews=[review])
    return package, plan


def test_source_selection_keeps_people_and_portraits_and_opaque_rows(monkeypatch):
    package, plan = source_selection_example()
    monkeypatch.setattr(layer.packages, 'validate_package', lambda _: None)
    before = copy.deepcopy(package)
    bound = layer.bind(package, plan)
    assert package == before
    assert bound['players'] == before['players']
    assert bound['assets'] == before['assets']
    assert bound['clubs'][0]['roster_player_ids'] == [f'p-{id}' for id in range(83, 99)]
    assert layer.groups(plan)[1001]['after'][-1] == (1000, 1)


@pytest.mark.parametrize('problem', ['missing-xi', 'repeated-xi', 'unsupported-xi',
    'short-supported', 'remove-supported', 'remove-opaque', 'repeated-removal', 'no-removals'])
def test_source_selection_refuses_unsafe_or_unprotected_selection(problem):
    _, plan = source_selection_example()
    review = plan['reviews'][0]
    if problem == 'missing-xi': review['sourced_xi_native_ids'].pop()
    if problem == 'repeated-xi': review['sourced_xi_native_ids'][-1] = 83
    if problem == 'unsupported-xi': review['sourced_xi_native_ids'][-1] = 99
    if problem == 'short-supported': review['supported_native_ids'].pop()
    if problem == 'remove-supported': review['removed_player_carrier_ids'] = [83]
    if problem == 'remove-opaque': review['removed_player_carrier_ids'] = [1000]
    if problem == 'repeated-removal': review['removed_player_carrier_ids'] *= 2
    if problem == 'no-removals': review['removed_player_carrier_ids'] = []
    with pytest.raises(ValueError):
        layer.groups(plan)


@pytest.mark.parametrize('key', ['starting_xi_player_ids', 'substitute_player_ids'])
def test_source_selection_cannot_remove_existing_explicit_editorial_selection(monkeypatch, key):
    package, plan = source_selection_example()
    package['clubs'][0]['opening'] = {key: ['p-99']}
    plan['package_canonical_sha256'] = layer.digest(layer.packages.canonical_json_bytes(package))
    monkeypatch.setattr(layer.packages, 'validate_package', lambda _: None)
    with pytest.raises(ValueError, match='explicitly selected'):
        layer.bind(package, plan)


def test_only_source_selection_opts_into_opaque_flag_preservation(monkeypatch):
    calls = []
    def prune(raw, **kwargs):
        calls.append(kwargs)
        return raw
    monkeypatch.setattr(layer, 'prune_visible_mode1_roster_payload', prune)
    group = dict(before=[(1, 0)], removed=[1])
    layer._prune(b'raw', group, {})
    layer._prune(b'raw', group, {'policy': layer.SOURCE_SELECTION})
    assert 'preserve_unselected_flag_one' not in calls[0]
    assert calls[1]['preserve_unselected_flag_one'] is True


def prepared_selection_fixture(tmp_path, monkeypatch):
    import json
    from app.fdi_indexed import IndexedFDIFile
    from scripts import season_historical_club_label_full_cohort_optin_v2 as full
    package, _ = source_selection_example()
    package['players'].append(dict(id='p-1000', carrier_id=1000, club_id='club', policy='preserve-existing-mode1'))
    package['clubs'][0]['roster_player_ids'].append('p-1000')
    for actor in package['players']:
        actor.update(name=f"Player{actor['carrier_id']}", facts={'birth_date': '1980-01-01'})
    rows = [dict(source_row_index=i, source_row_sha256=str(i),
        facts=dict(name=f'Player{id}', birth_date='1980-01-01'),
        opening_xi_order=i + 1 if i < 11 else None, opening_source_player_id=f's{id}')
        for i, id in enumerate(range(83, 99))]
    selector = dict(country_catalog='spain', competition_catalog='test', club_name='Source Club',
        source_path='source.txt', source_sha256='a' * 64)
    cohort = dict(selector=selector, players=rows, opening_fixture_date='2001-08-01', opening_xi_complete=True)
    pre_path = tmp_path / 'pre.json'
    pre_path.write_text(json.dumps({'source_clubs': [cohort]}))
    package['artifacts'] = [dict(id='opening-squad-preallocation-2001-02', sha256=layer.registry.sha256_file(pre_path))]
    package_path = tmp_path / 'package.json'
    package_path.write_text(json.dumps(package))
    (tmp_path / 'opening-lineups.json').write_text(json.dumps({'clubs': [{'source_selector': selector}]}))
    game = tmp_path / 'game'
    (game / 'DBDAT').mkdir(parents=True)
    (game / 'DBDAT/EQ98030.FDI').write_bytes(b'eq')
    (game / 'DBDAT/JUG98030.FDI').write_bytes(b'jug')
    release = SimpleNamespace(season='2001-02', release_id='base', package_path=package_path, game_path=game)
    monkeypatch.setattr(layer.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(full, 'club_group', lambda club: 'spain')
    monkeypatch.setattr(full, '_assert_unique_source_cohort', lambda *args: None)
    monkeypatch.setattr(full, '_native_owner_index', lambda eq: (None, {}))
    monkeypatch.setattr(full, '_native_jug_identity_index', lambda *args: {})
    monkeypatch.setattr(full, '_bind_cohort', lambda *args, **kwargs: [dict(
        native_player_carrier_id=id, source_row_index=i) for i, id in enumerate(range(83, 99))])
    before = [(id, 0) for id in range(83, 100)] + [(1000, 1)]
    monkeypatch.setattr(layer, '_roster_rows', lambda *args: (None, b'raw', before))
    capture = dict(selector, players=[r['facts'] for r in rows])
    monkeypatch.setattr(source, 'bound_annual_capture', lambda *args: (capture, {'raw': 'verified-fixture'}))
    monkeypatch.setattr(source.opening, 'verify_opening', lambda *args: dict(
        date='2001-08-01', starting_xi=[f's{id}' for id in range(83, 94)]))
    payload = bytearray(16)
    payload[12:16] = bytes(v ^ 0x61 for v in bytes([1, 1]) + (1980).to_bytes(2, 'little'))
    entries = [SimpleNamespace(record_id=id, decode_payload=lambda data: bytes(payload)) for id in range(83, 100)]
    monkeypatch.setattr(IndexedFDIFile, 'from_bytes', lambda data: SimpleNamespace(entries=entries))
    monkeypatch.setattr(source.rosters, 'native_player', lambda *args: {'name_end': 0})
    case = dict(id='selection', policy=layer.SOURCE_SELECTION, club_carrier_id=1001,
        source_selector=selector, preallocation={'path': 'pre.json', 'sha256': layer.registry.sha256_file(pre_path)},
        removed_player_carrier_ids=[99])
    return release, case


def test_source_selection_saved_plan_verifies_after_json_roundtrip(tmp_path, monkeypatch):
    import json
    release, case = prepared_selection_fixture(tmp_path, monkeypatch)
    prepared = layer.prepare(release, [case])
    loaded = json.loads(json.dumps(prepared))
    assert loaded == prepared  # catches tuple/list drift before publication
    layer.verify(release, loaded)


@pytest.mark.parametrize('problem', ['changed-source', 'different-native-dob', 'different-source-xi', 'supported-removal'])
def test_source_selection_prepare_refuses_original_source_and_person_drift(tmp_path, monkeypatch, problem):
    release, case = prepared_selection_fixture(tmp_path, monkeypatch)
    if problem == 'changed-source':
        (tmp_path / 'pre.json').write_text('{}')
    if problem == 'different-native-dob':
        original = source.rosters.native_player
        monkeypatch.setattr(source.rosters, 'native_player', lambda *args: {'name_end': 1})
    if problem == 'different-source-xi':
        monkeypatch.setattr(source.opening, 'verify_opening', lambda *args: dict(
            date='2001-08-01', starting_xi=[f's{id}' for id in range(84, 95)]))
    if problem == 'supported-removal':
        case['removed_player_carrier_ids'] = [83]
    with pytest.raises(ValueError):
        layer.prepare(release, [case])


@pytest.mark.parametrize('country,code', [('brazil', 'BRA1'), ('ireland', 'IR1'), ('norway', 'NO1'), ('sweden', 'SE1')])
def test_source_selection_cannot_accept_known_next_year_calendar_metadata(country, code):
    layer._verify_selection_fixture_year('2024-25', country, code, '2024-02-16')
    with pytest.raises(ValueError, match='next-year calendar'):
        layer._verify_selection_fixture_year('2024-25', country, code, '2025-02-14')


def test_source_selection_retains_existing_russia_transition_quarantine():
    with pytest.raises(ValueError, match='quarantined'):
        layer._verify_selection_fixture_year('2009-10', 'russia', 'RU1', '2009-03-15')
