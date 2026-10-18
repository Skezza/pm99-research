from bs4 import BeautifulSoup
import pytest
from scripts import prepare_shinnik_khomukha_reserve_20261016 as subject


def page(*,heading='Шинник 2002',person='Дмитрий Хомуха',pid=1285,section='Полузащитники',country='Туркмения',extra=''):
    return BeautifulSoup(f'<h1>{heading}</h1><table><tr><td>{section}</td></tr>'
        f'<tr><td>7</td><td><a href="../../player/h/{pid}.htm">{person}</a></td>'
        f'<td><img alt="{country}"></td><td>23.08.1969</td><td>174</td><td>76</td>'
        f'<td>171</td><td>29</td><td>29</td><td>{extra}</td><td></td><td>2001</td><td>2</td></tr></table>','html.parser')


def test_published_numeric_actor_full_facts_and_role():
    row=subject.registration(page())
    assert (row['birth_date'],row['position'],row['nationality'])==('1969-08-23','M','TKM')
    assert (row['height_cm'],row['weight_kg'],row['shirt_number'])==(174,76,7)


@pytest.mark.parametrize('kwargs',[dict(heading='Шинник 2003'),dict(person='Другой Хомуха'),
    dict(pid=12850),dict(section='Защитники'),dict(country='Россия'),dict(extra='01.09.2002')])
def test_no_wrong_year_namesake_role_flag_or_unreviewed_transfer(kwargs):
    with pytest.raises(ValueError):subject.registration(page(**kwargs))


def test_duplicate_source_identity_not_arbitrarily_selected():
    p=page();p.table.append(page().table.find_all('tr')[1])
    with pytest.raises(ValueError,match='one explicit numeric'):
        subject.registration(p)
