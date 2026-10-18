import pytest
from scripts import season_within_club_reserve_repair_v1 as repair


def page(rows):
    return '<table class="career"><tbody>' + ''.join(
        f'<tr><td><a href="/teams/team.sd?team_id={id}">{name}</a></td>'
        f'<td>{start}</td><td>{end}</td><td>{fee}</td></tr>'
        for id, name, start, end, fee in rows) + '</tbody></table>'


def test_original_dated_interior_owner_and_future_loan():
    raw = page([(2104, 'Rangers', '01 Jan, 99', '01 May, 02', '£100000'),
                (3369, 'Northern S', '29 Jan, 01', '31 May, 01', 'Loan')])
    result = repair.career_owner(raw, '2000-08-01', 'Rangers')
    assert result['owner']['provider_club_id'] == 'soccerbase:2104'
    assert result['exact_matchday_appearance_claimed'] is False


@pytest.mark.parametrize('anchor', ['1999-01-01', '2002-05-01', '2001-03-01'])
def test_boundary_and_overlapping_loan_refused(anchor):
    raw = page([(2104, 'Rangers', '01 Jan, 99', '01 May, 02', ''),
                (3369, 'Northern S', '29 Jan, 01', '31 May, 01', 'Loan')])
    with pytest.raises(ValueError, match='interior'):
        repair.career_owner(raw, anchor, 'Rangers')


@pytest.mark.parametrize('start,end', [('1999', '01 May, 02'),
    ('01 Jan, 99', ''), ('01 May, 02', '01 Jan, 99')])
def test_no_guessed_or_missing_or_reversed_dates(start, end):
    with pytest.raises(ValueError):
        repair.career_owner(page([(2104, 'Rangers', start, end, '')]), '2000-08-01', 'Rangers')


def test_wrong_club_and_provider_and_two_tables_refused():
    raw = page([(2104, 'Rangers', '01 Jan, 99', '01 May, 02', '')])
    for payload, club in [(raw, 'Celtic'), (raw.replace('/teams/team.sd', '/managers/manager.sd'), 'Rangers'),
                          (raw + raw, 'Rangers')]:
        with pytest.raises(ValueError):
            repair.career_owner(payload, '2000-08-01', club)


def test_overlapping_second_club_is_not_absence_based_ownership():
    raw = page([(2104, 'Rangers', '01 Jan, 99', '01 May, 02', ''),
                (737, 'Dundee', '01 Jul, 00', '01 Sep, 00', '')])
    with pytest.raises(ValueError, match='interior'):
        repair.career_owner(raw, '2000-08-01', 'Rangers')


def test_full_biography_and_literal_matching_initial_establish_two_name_components():
    assert repair.name_components('Lee Feeney', 'L Feeney') == {
        'given_name': 'Lee', 'family_name': 'Feeney'}


def test_centre_back_review_is_explicit_and_preserves_annual_disagreement():
    raw = '<table class="infobox"><tr><th>Position</th><td>Centre-back</td></tr></table>'
    proof = repair.centre_back_review(raw, 'M', 'D')
    assert proof['annual_position_before'] == 'M'
    assert proof['broad_position_after'] == 'D'
    assert proof['dated_first_fixture_position_claimed'] is False
    for bad, requested in [(raw.replace('Centre-back', 'Midfielder'), 'D'), (raw+raw, 'D'), (raw, 'M')]:
        with pytest.raises(ValueError): repair.centre_back_review(bad, 'M', requested)


@pytest.mark.parametrize('full,label', [('Lee Feeney', 'W Feeney'),
    ('Giovanni van Bronckhorst', 'G Van Bronckhorst'), ('Lee Feeney', 'Feeney'),
    ('Lee Feeney', 'L F'), ('Lee Feeney', 'L Feney'), ('Lee Feeney', 'L. Feeney')])
def test_never_expand_initials_or_guess_multipart_or_different_surnames(full, label):
    assert repair.name_components(full, label) == {}
