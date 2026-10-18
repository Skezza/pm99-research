import pytest
from scripts import season_cgo_disambiguation_v1 as subject


def html(country='Congo_national_football_team',years='2004–2013',name='Christopher Samba',born='1984-03-28'):
    return f'<h1 id="firstHeading">{name}</h1><table class="infobox"><tr><td class="bday">{born}</td></tr><tr><td>{years}</td><td><a href="./{country}">Congo</a></td></tr></table>'.encode()


def test_exact_dated_republic_country_is_distinct_from_democratic_country():
    assert subject.parse(html(),'Christopher Samba','1984-03-28','2009-10')['country']=='CGO'
    assert subject.parse(html(country='DR_Congo_national_football_team'),'Christopher Samba','1984-03-28','2009-10')['country']=='COD'


@pytest.mark.parametrize('changes',[dict(name='Other Samba'),dict(born='1984-03-29')])
def test_full_original_identity_and_birthday_cannot_be_guessed(changes):
    with pytest.raises(ValueError,match='full-name/DOB'):
        subject.parse(html(**changes),'Christopher Samba','1984-03-28','2009-10')


def test_future_international_country_does_not_prove_earlier_season():
    with pytest.raises(ValueError,match='does not cover target season'):
        subject.parse(html(years='2019–2022'),'Christopher Samba','1984-03-28','2016-17')


def test_ambiguous_or_undated_country_does_not_prove_either_congo():
    with pytest.raises(ValueError,match='closed date interval'):
        subject.parse(html(years=''),'Christopher Samba','1984-03-28','2009-10')
    raw=html()+'<table class="infobox"><tr><td>2005–2011</td><td><a href="./DR_Congo_national_football_team">Congo</a></td></tr></table>'.encode()
    with pytest.raises(ValueError,match='affiliation is ambiguous'):
        subject.parse(raw,'Christopher Samba','1984-03-28','2009-10')


def test_unsupported_country_and_other_nationalities_are_not_part_of_cgo_disambiguation():
    assert subject.verify(dict(nationality='ANT'),'2009-10') is None


def test_single_dated_year_is_not_extrapolated_backward():
    assert subject.parse(html(years='2019'),'Christopher Samba','1984-03-28','2019-20')['country']=='CGO'
    with pytest.raises(ValueError,match='does not cover target season'):
        subject.parse(html(years='2019'),'Christopher Samba','1984-03-28','2016-17')


def test_missing_independent_catalogue_refuses_before_any_publication(tmp_path):
    with pytest.raises(ValueError,match='requires independent dated'):
        subject.verify(dict(nationality='CGO'),'2009-10',catalog=tmp_path/'absent.json')


def test_retained_original_samba_biography_really_corroborates_target_country():
    root=subject.registry.ROOT/'.local/consolidated-audit-20261009/country-policy-v2-cohort-20261017/2010-11'
    if not subject.CATALOG.exists() or not (root/'country-plan.json').exists():pytest.skip('local original corpus unavailable')
    row=subject.pipeline.read_json_file(root/'country-plan.json')['updates'][0]
    proof=subject.verify(row,'2010-11')
    assert proof['country']=='CGO' and proof['source_player_id']==29016


def test_original_imbula_biography_is_not_a_republic_of_congo_witness():
    root=subject.registry.ROOT/'.local/consolidated-audit-20261009/country-policy-v2-cohort-20261017/2016-17'
    if not subject.CATALOG.exists() or not (root/'country-plan.json').exists():pytest.skip('local original corpus unavailable')
    row=next(r for r in subject.pipeline.read_json_file(root/'country-plan.json')['updates'] if r['carrier_id']==9161)
    with pytest.raises(ValueError,match='does not cover target season'):subject.verify(row,'2016-17')
    with pytest.raises(ValueError,match='dated country: COD'):subject.verify(row,'2019-20')
