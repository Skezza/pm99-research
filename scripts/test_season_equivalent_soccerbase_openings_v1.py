import copy
import pytest
from scripts import season_equivalent_soccerbase_openings_v1 as subject


def captures():
    first = dict(source_path='soccerbase/team/1732/august', country_catalog='eng',
        competition_catalog='conf', competition_name='Conference', club_name='Morecambe',
        source_sha256='a'*64, players=[])
    second = dict(first, source_sha256='b'*64, players=[dict(name='Original Player')])
    return [first, second]


def actual(capture):
    return dict(status='original-first-fixture-reparsed',
        source_capture=dict(source_sha256=capture['source_sha256']),
        fixture=dict(date='2000-08-19', game_id=286454),
        identity_bridges=dict(starting_xi=[dict(id=i) for i in range(11)]),
        raw_sources=[dict(path='original.html', sha256='verified')])


def test_empty_old_catalogue_is_not_a_conflicting_lineup_if_full_original_replays_agree():
    rows = captures(); before = copy.deepcopy(rows)
    chosen, replay, proof = subject.select(rows, actual)
    assert chosen == rows[1]
    assert proof['identity_DOB_gaps_not_waived']
    assert proof['native_writes'] == 0
    assert subject.select(list(reversed(rows)), actual) == (chosen, replay, proof)
    assert rows == before


@pytest.mark.parametrize('problem', ['date', 'person', 'raw-source', 'incomplete-XI'])
def test_cannot_use_larger_catalogue_to_hide_a_real_original_conflict(problem):
    def differing(c):
        row = actual(c)
        if c['source_sha256'] == 'b'*64:
            if problem == 'date': row['fixture']['date'] = '2000-08-26'
            if problem == 'person': row['identity_bridges']['starting_xi'][0]['id'] = 99
            if problem == 'raw-source': row['raw_sources'][0]['sha256'] = 'changed'
            if problem == 'incomplete-XI': row['identity_bridges']['starting_xi'].pop()
        return row
    with pytest.raises(ValueError): subject.select(captures(), differing)


def test_cannot_collapse_different_numerical_teams_or_competitions():
    rows = captures(); rows[1]['source_path'] = 'soccerbase/team/9999/august'
    with pytest.raises(ValueError, match='same exact team'):
        subject.select(rows, actual)


def test_original_parse_error_is_not_silently_discarded_as_an_empty_capture():
    def refused(c): raise ValueError('original biography hash changed')
    with pytest.raises(ValueError, match='biography hash changed'):
        subject.select(captures(), refused)
