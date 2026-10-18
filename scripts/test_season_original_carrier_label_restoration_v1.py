import copy
import pytest
from scripts import season_original_carrier_label_restoration_v1 as source
from scripts import test_season_historical_club_label_review_v1 as fixtures


def test_full_authored_cohort_identifies_club_without_claiming_missing_opening_starter(monkeypatch):
    club, players, index, sources, expected = fixtures.fixture(monkeypatch)
    expected['opening_xi_complete'] = False
    before = copy.deepcopy((club, players))
    assert source.cohort_source(club, players, 'original-rows', index, sources) == expected
    assert (club, players) == before


@pytest.mark.parametrize('problem', ['known-date', 'name', 'proof', 'mixed-clubs', 'repeated-person', 'small-cohort'])
def test_original_identity_not_a_majority_vote_or_a_new_club_selection(monkeypatch, problem):
    club, players, index, sources, expected = fixtures.fixture(monkeypatch)
    if problem == 'known-date': players[0]['facts']['birth_date'] = '1989-01-02'
    if problem == 'name': players[0]['name'] = 'Another Person'
    if problem == 'proof': players[0]['proof']['artifact_id'] = 'unqualified-seed'
    if problem == 'mixed-clubs':
        key = next(iter(sources)); other = (*key[:2], 'Hamburger SV', *key[3:])
        index[players[-1]['person_id']] = [(other, expected['players'][-1])]
    if problem == 'repeated-person': players[-1]['person_id'] = players[0]['person_id']
    if problem == 'small-cohort': players.pop()
    with pytest.raises(ValueError): source.cohort_source(club, players, 'original-rows', index, sources)


def coach_page(section='Managerial career', years='1994–2005', name='Jim Harvey', club='Morecambe'):
    return f'<h1 id="firstHeading">{name}</h1><table class="infobox"><tr><th>{section}</th></tr><tr><th>{years}</th><td><a>{club}</a></td></tr></table>'.encode()


def test_dated_manager_evidence_retains_current_coach_not_a_new_person_guess():
    assert source.coach(coach_page(), 'Jim Harvey', 'Morecambe', 2000)['from_year'] == 1994


@pytest.mark.parametrize('problem', ['playing-not-managing', 'future', 'boundary', 'name', 'club'])
def test_career_presence_does_not_automatically_certify_a_manager(problem):
    options = {}
    if problem == 'playing-not-managing': options['section'] = 'Senior career'
    if problem == 'future': options['years'] = '2001–2005'
    if problem == 'boundary': options['years'] = '2000–2005'
    if problem == 'name': options['name'] = 'Another Harvey'
    if problem == 'club': options['club'] = 'Barrow'
    with pytest.raises(ValueError): source.coach(coach_page(**options), 'Jim Harvey', 'Morecambe', 2000)


def test_ground_tenancy_is_bound_to_original_club_and_target_year():
    raw = b'<h1 id="firstHeading">Christie Park (Morecambe)</h1><table class="infobox"><tr><td>Morecambe (1921\xe2\x80\x932010)</td></tr></table>'
    assert source.ground(raw, 'Christie Park', 'Morecambe', 2000)['to_year'] == 2010
    with pytest.raises(ValueError): source.ground(raw, 'Christie Park', 'Morecambe', 2011)
    with pytest.raises(ValueError): source.ground(raw, 'Holker Street', 'Morecambe', 2000)
