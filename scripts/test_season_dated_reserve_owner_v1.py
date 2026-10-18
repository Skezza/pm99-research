import copy
from types import SimpleNamespace
import pytest
from scripts import season_dated_reserve_owner_v1 as policy
from scripts import season_historical_transfer_review_v1 as transfer


def inputs():
    person = {'source_player_id': 10, 'name': 'Actual Reserve', 'birth_date': '1980-01-01'}
    people = {('actualreserve', '1980-01-01'): {10: person}}
    players = [{'id': 'p1', 'club_id': 'owner', 'name': person['name'],
                'facts': {'birth_date': person['birth_date']}},
               {'id': 'p2', 'club_id': 'displaced', 'name': person['name'],
                'facts': {'birth_date': person['birth_date']}}]
    sources = {key: {'source_club_id': n, 'date': d,
        'match_page_date_independently_published': True,
        'starting_xi': {str(i): 'Other Person' for i in range(start, start + 11)},
        'substitutes': {}} for key, n, d, start in
        [('owner', 1, '2005-08-13', 100), ('displaced', 2, '2005-08-14', 200)]}
    events = [{'date': '2004-07-01', 'from_club_id': 3, 'to_club_id': 1,
               'from_club': 'Previous', 'to_club': 'Owner'},
              {'date': '2006-07-01', 'from_club_id': 1, 'to_club_id': 4,
               'from_club': 'Owner', 'to_club': 'Next'}]
    clubs = {k: {'id': k, 'name': k.title(), 'carrier_id': n, 'division': 'premier-league'}
             for k, n in [('owner', 1), ('displaced', 2)]}
    captures = [{'club_name': 'Owner', 'country_catalog': 'eng', 'source_path': 'annual.json',
                 'source_sha256': 'sha', 'players': [dict(name=person['name'], birth_date=person['birth_date'])]}]
    verifier = SimpleNamespace(verify=lambda _: {'status': 'raw-source-reparsed', 'local_path': 'original.html',
        'source_sha256': 'originalsha'})
    return players, sources, person, events, clubs, captures, verifier, people


def test_verified_reserve_owner_does_not_require_a_first_match_appearance():
    args = inputs()
    before = copy.deepcopy(args[:6])
    winner, basis, proof = policy.decide(*args)
    assert winner == args[0][0] and basis == policy.BASIS
    assert proof['source_player']['name'] == 'Actual Reserve'
    assert proof['opening_dates'] == ['2005-08-13', '2005-08-14']
    assert args[:6] == before
    args[0].reverse()
    assert policy.decide(*args)[:2] == (winner, basis)


@pytest.mark.parametrize('problem', ['missing-source', 'same-real-club', 'missing-person',
    'entry-only', 'moves-between-openings', 'other-positive', 'unpublished-date',
    'missing-capture', 'wrong-country', 'wrong-club', 'raw-reparse-refused',
    'wrong-DOB', 'initials-only', 'homonym', 'two-rows', 'native-DOB-conflict',
    'unresolved-substitute'])
def test_source_and_ownership_gaps_never_become_silent_waivers(problem):
    args = list(inputs())
    players, sources, person, events, clubs, captures, verifier, people = args
    if problem == 'missing-source': del sources['displaced']
    if problem == 'same-real-club': sources['displaced']['source_club_id'] = 1
    if problem == 'missing-person': args[2] = None
    if problem == 'entry-only': events.pop()
    if problem == 'moves-between-openings': events[1]['date'] = '2005-08-14'
    if problem == 'other-positive': sources['displaced']['substitutes']['10'] = person['name']
    if problem == 'unpublished-date': sources['displaced']['match_page_date_independently_published'] = False
    if problem == 'missing-capture': captures.clear()
    if problem == 'wrong-country': captures[0]['country_catalog'] = 'ger'
    if problem == 'wrong-club': captures[0]['club_name'] = 'Displaced'
    if problem == 'raw-reparse-refused': args[6] = SimpleNamespace(verify=lambda _: {'status': 'refused'})
    if problem == 'wrong-DOB': captures[0]['players'][0]['birth_date'] = '1981-01-01'
    if problem == 'initials-only': captures[0]['players'][0]['name'] = 'A. Reserve'
    if problem == 'homonym': people[('actualreserve', '1980-01-01')][11] = dict(person, source_player_id=11)
    if problem == 'two-rows': captures[0]['players'].append(copy.deepcopy(captures[0]['players'][0]))
    if problem == 'native-DOB-conflict': players[0]['facts']['birth_date'] = '1981-01-01'
    if problem == 'unresolved-substitute': sources['displaced']['unresolved_substitution_events'] = [
        {'incoming_player_ids': {'10': person['name']}}]
    assert policy.decide(*args)[0] is None


def test_existing_positive_matchday_decisions_stay_unchanged_without_annual_reads():
    args = list(inputs())
    args[1]['owner']['substitutes']['10'] = 'Actual Reserve'
    args[6] = SimpleNamespace(verify=lambda _: pytest.fail('unnecessary new annual source lookup'))
    assert policy.decide(*args) == (args[0][0],
        'positive-opening-membership-and-consistent-dated-transfer-brackets', None)


def plan():
    return {'allow_dated_reserve_owners': True, 'bindings': {
        'dated_reserve_owner_policy': policy.POLICY,
        'opening_person_supplement_policy': 'bound-policy',
        'published_person_supplement': {'path': 'people'},
        'published_transfer_supplement': {'path': 'history'}},
        'updates': [{'ownership_basis': policy.BASIS, 'retained_owner_squad_membership': {}}]}


def test_explicit_original_input_bindings_are_required():
    policy.validate_binding(plan())
    policy.validate_binding({'updates': [{'ownership_basis': 'legacy'}]})


@pytest.mark.parametrize('problem', ['flag', 'policy', 'people', 'history', 'opening', 'witness', 'basis'])
def test_missing_or_forged_authorisation_refuses_the_policy(problem):
    p = plan()
    if problem == 'flag': p['allow_dated_reserve_owners'] = False
    if problem == 'policy': p['bindings']['dated_reserve_owner_policy'] = 'other'
    if problem in ('people', 'history', 'opening'):
        del p['bindings'][{'people': 'published_person_supplement', 'history': 'published_transfer_supplement',
                          'opening': 'opening_person_supplement_policy'}[problem]]
    if problem == 'witness': del p['updates'][0]['retained_owner_squad_membership']
    if problem == 'basis': p['updates'][0]['ownership_basis'] = 'legacy'
    with pytest.raises(ValueError): policy.validate_binding(p)
