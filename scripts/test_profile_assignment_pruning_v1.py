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
