from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from scripts import season_complete_mode1_opening_v1 as subject


@pytest.fixture
def opening(monkeypatch):
    e = subject.exchange
    people = [dict(id=f'p{i}', carrier_id=i, club_id='club', person_id=f'person-source-row{i}',
        name=f'Player {i}', source_name=f'Player {i}', facts=dict(birth_date='1990-01-01', primary_position='M'))
        for i in range(1, 14)]
    package = dict(clubs=[dict(id='club', carrier_id=403, name='Werder Bremen',
        opening=dict(policy='preserve-existing-mode1'), roster_player_ids=[p['id'] for p in people])], players=people)
    capture = dict(clubs=[dict(source_selector=dict(transfermarkt_club_id=86,
        club_name='Werder Bremen', transfermarkt_club_name='SV Werder Bremen'),
        source_competition_code='L1', source_match_id=123)])
    pre = dict(source_clubs=[dict(selector=dict(club_name='Werder Bremen'), opening_xi_complete=True,
        opening_fixture_date='2013-08-10', opening_source_match_id=123,
        players=[dict(opening_xi_order=i, opening_source_player_id=i, source_row_sha256=f'row{i}',
            facts=dict(name=f'Player {i}', birth_date='1990-01-01')) for i in range(1, 12)])])
    request = dict(complete_mode1_opening=dict(policy=subject.POLICY, club_carrier_id=403,
        match='match', preallocation='pre'), evidence=dict(match=dict(provider_club_id=86,
            competition='L1', date='2013-08-10', first_league_capture='capture'), pre='pre'),
        new_people=[dict(carrier_id=12, provider_player_id=99, match='match')])
    monkeypatch.setattr(e, 'original', lambda x: x)
    monkeypatch.setattr(e.pipeline, 'read_json_file', lambda x: {'capture':capture, 'pre':pre}[x])
    monkeypatch.setattr(e, 'verify_first_league_fixture', lambda x: None)
    names = []
    monkeypatch.setattr(e, 'verify_match_club', lambda value, name: names.append(name))
    monkeypatch.setattr(e, 'match_people', lambda x: ([dict(source_player_id=str(i)) for i in range(1,12)],
        [dict(source_player_id='99')]))
    monkeypatch.setattr(e.facts, 'native_facts', lambda jug, pid: dict(name=f'Player {pid}',
        birth_date='1990-01-01', position='M', startup_order=14-pid))
    entries = [NS(record_id=i, payload_offset=0, payload_length=1,
        decode_payload=lambda raw: raw) for i in range(1,14)] + [NS(record_id=403, payload_offset=0, payload_length=1)]
    monkeypatch.setattr(subject.IndexedFDIFile, 'from_bytes', lambda x: NS(entries=entries))
    native = NS(mode_byte=1, rows=[NS(flag=0, player_record_id=i) for i in range(1,14)])
    monkeypatch.setattr(e.delta.compiler, 'parse_eq_external_team_roster_payload', lambda *args: native)
    from scripts import season_opening_order_repair_v1 as order
    monkeypatch.setattr(order, 'native_owners', lambda eq: {i:{403} for i in range(1,14)})
    monkeypatch.setattr(subject, 'read_initial_order', lambda raw: NS(family='dd6360'))
    preflights = []
    monkeypatch.setattr(subject, 'apply', lambda jug, eq, plan: preflights.append(deepcopy(plan)))
    return package, request, capture, pre, native, names, preflights


def test_complete_original_xi_and_tail_relative_order_are_preflighted(opening):
    package, request, _, _, _, names, preflights = opening
    plan = subject.prepare(None, request, package, b'jug', b'eq')
    assert plan['starting_xi'] == list(range(1,12))
    assert [r['carrier_id'] for r in plan['orders']] == list(range(1,12)) + [13,12]
    assert len(preflights) == 1
    assert names == ['SV Werder Bremen']
    assert plan['opaque_tactics_unchanged'] is True


def test_explicit_order_only_preserves_complete_source_xi_without_identity_replacements(opening):
    package, request, _, _, _, _, preflights = opening
    request['complete_mode1_opening']['policy'] = subject.ORDER_ONLY_POLICY
    request['new_people'] = []
    plan = subject.prepare(None, request, package, b'jug', b'eq')
    assert plan['policy'] == subject.ORDER_ONLY_POLICY
    assert plan['starting_xi'] == list(range(1,12))
    assert len(preflights) == 1


@pytest.mark.parametrize('field', ['new_people', 'retirements', 'moves', 'orders', 'same_carrier_name_capacity'])
def test_order_only_cannot_smuggle_identity_or_unrelated_transaction(opening, field):
    package, request, _, _, _, _, preflights = opening
    request['complete_mode1_opening']['policy'] = subject.ORDER_ONLY_POLICY
    request['new_people'] = []
    request[field] = [{}]
    with pytest.raises(ValueError):
        subject.prepare(None, request, package, b'jug', b'eq')
    assert not preflights


def test_empty_old_policy_is_not_an_order_only_authorization(opening):
    package, request, *_ = opening
    request['new_people'] = []
    with pytest.raises(ValueError, match='positive bench'):
        subject.prepare(None, request, package, b'jug', b'eq')


@pytest.mark.parametrize('field', ['name', 'birth_date', 'primary_position'])
def test_order_only_checks_non_xi_native_identity_too(opening, field):
    package, request, *_ = opening
    request['complete_mode1_opening']['policy'] = subject.ORDER_ONLY_POLICY
    request['new_people'] = []
    if field == 'name': package['players'][-1]['name'] = 'Someone Else'
    else: package['players'][-1]['facts'][field] = 'wrong'
    with pytest.raises(ValueError, match='all retained native'):
        subject.prepare(None, request, package, b'jug', b'eq')


@pytest.mark.parametrize('policy', ['preserve-existing-mode1', 'invented-default'])
def test_native_preserve_reserve_does_not_become_a_verified_historical_fact(opening, policy):
    package, request, *_ = opening
    request['complete_mode1_opening']['policy'] = subject.ORDER_ONLY_POLICY
    request['new_people'] = []
    package['players'][-1]['facts'].update(birth_date={'policy':policy}, primary_position={'policy':policy})
    if policy == 'preserve-existing-mode1':
        subject.prepare(None, request, package, b'jug', b'eq')
    else:
        with pytest.raises(ValueError, match='all retained native'):
            subject.prepare(None, request, package, b'jug', b'eq')


def test_unused_adjudication_cannot_waive_correct_original_identity(opening):
    package, request, *_ = opening
    request['complete_mode1_opening']['retained_fact_adjudications'] = [dict(carrier_id=1, evidence='unused')]
    with pytest.raises(ValueError, match='unused or duplicate'):
        subject.prepare(None, request, package, b'jug', b'eq')


@pytest.mark.parametrize('bad', [None, 'carrier', 'row', 'provider', 'person', 'old-date', 'official-date'])
def test_prior_birthday_adjudication_is_exact_actor_row_and_official_fact_bound(monkeypatch, bad):
    from scripts import season_adjudicated_player_facts_v1 as adjudicated
    from scripts import season_source_verified_player_changes_v1 as changes
    actor = dict(carrier_id=7, person_id='person-source-row', source_name='Full Person', facts=dict(birth_date='1971-09-20'))
    source = dict(source_row_sha256='row', opening_source_player_id=3514, facts=dict(birth_date='1971-09-10'))
    witness = dict(person_id=actor['person_id'], full_name='Full Person', historical_identity=dict(source_row_sha256='row', provider_player_id=3514))
    row = dict(carrier_id=7, field_mask=['birth_date'], before=dict(person_id=actor['person_id'], facts=dict(birth_date='1971-09-10')), witness=witness)
    document = dict(schema=changes.INPUT_SCHEMA, kind=changes.ADJUDICATED_KIND, season='2000-01', changes=[row])
    request = dict(complete_mode1_opening=dict(retained_fact_adjudications=[dict(carrier_id=7, evidence='prior')]), evidence=dict(prior='file'))
    monkeypatch.setattr(subject.exchange, 'original', lambda x:x)
    monkeypatch.setattr(subject.exchange.pipeline, 'read_json_file', lambda _:document)
    monkeypatch.setattr(adjudicated, 'adjudicate', lambda _:dict(birth_date='1971-09-21' if bad=='official-date' else '1971-09-20'))
    if bad == 'carrier': row['carrier_id'] = 8
    if bad == 'row': witness['historical_identity']['source_row_sha256'] = 'another'
    if bad == 'provider': witness['historical_identity']['provider_player_id'] = 999
    if bad == 'person': witness['person_id'] = 'another'
    if bad == 'old-date': row['before']['facts']['birth_date'] = '1971-01-01'
    if bad is None:
        assert subject.corrected_birthday(NS(season='2000-01'),request,source,actor)==7
    else:
        with pytest.raises(ValueError):
            subject.corrected_birthday(NS(season='2000-01'),request,source,actor)


@pytest.mark.parametrize('bad', ['policy', 'moves', 'native-club', 'competition',
    'fixture', 'xi-id', 'xi-row', 'dob', 'flags', 'ownership', 'starter', 'bench', 'match'])
def test_complete_mode1_refuses_unbound_or_ambiguous_changes(opening, bad):
    package, request, capture, pre, native, _, preflights = opening
    if bad == 'policy': request['complete_mode1_opening']['policy'] = 'guess'
    if bad == 'moves': request['moves'] = [{}]
    if bad == 'native-club': capture['clubs'][0]['source_selector']['club_name'] = 'Another Club'
    if bad == 'competition': capture['clubs'][0]['source_competition_code'] = 'Cup'
    if bad == 'fixture': pre['source_clubs'][0]['opening_fixture_date'] = '2013-08-11'
    if bad == 'xi-id': pre['source_clubs'][0]['players'][0]['opening_source_player_id'] = 200
    if bad == 'xi-row': package['players'][0]['person_id'] = 'unknown'
    if bad == 'dob': package['players'][0]['facts']['birth_date'] = '1980-01-01'
    if bad == 'flags': native.rows[0].flag = 1
    if bad == 'ownership': native.rows[0].player_record_id = 200
    if bad == 'starter': request['new_people'][0]['carrier_id'] = 1
    if bad == 'bench': request['new_people'][0]['provider_player_id'] = 200
    if bad == 'match': request['new_people'][0]['match'] = 'other'
    with pytest.raises(ValueError):
        subject.prepare(None, request, package, b'jug', b'eq')
    assert not preflights
