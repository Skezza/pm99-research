from types import SimpleNamespace
from scripts import audit_roster_source_attribution_v1 as audit


def fixture():
    return ({'name': 'Bray Wanderers', 'id': 'club-1855', 'carrier_id': 1855,
             'division': 'preserve-existing-mode1-membership'},
            [{'source_name': f'Full Player {i}', 'name': f'Alias {i}'} for i in range(11)])


def source(club, country='ireland', count=11):
    return {'country_catalog': country, 'club_name': club,
            'players': [{'name': f'Full Player {i}'} for i in range(count)]}


def test_missing_dob_does_not_hide_an_exact_different_club_roster():
    club, players = fixture()
    verifier = SimpleNamespace(verify=lambda _: {'status': 'raw-source-reparsed'})
    result = audit.attribution(club, players, [source('Drogheda United')], verifier)
    assert result['status'] == 'mislabeled-club-candidate-needs-opening-and-manager-proof'
    assert not result['game_change_authorised_by_audit']


def test_ambiguous_full_cohorts_cannot_choose_a_club_by_order():
    club, players = fixture()
    verifier = SimpleNamespace(verify=lambda _: {'status': 'raw-source-reparsed'})
    assert audit.attribution(club, players, [source('Drogheda United'), source('Cork City')], verifier)['status'] == 'ambiguous-best-source-club'


def test_wrong_country_short_cohort_or_unverified_source_is_not_attribution():
    club, players = fixture()
    verifier = SimpleNamespace(verify=lambda _: {'status': 'raw-source-unavailable'})
    assert not audit.attribution(club, players, [source('Drogheda'), source('Foreign', 'italy'), source('Short', count=10)], verifier)['matches']
