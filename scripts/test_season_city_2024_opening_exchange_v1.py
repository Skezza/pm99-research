import copy
from types import SimpleNamespace
import pytest
from bs4 import BeautifulSoup
from scripts import season_city_2024_opening_exchange_v1 as source


def test_three_atomic_unique_reserve_destination_pairs():
    assert len(source.SWAPS)==3
    assert len({r[k] for r in source.SWAPS for k in (0,1)})==6
    assert {r[2] for r in source.SWAPS}=={1,2802,504}


def test_wrong_season_refuses_before_source_io():
    with pytest.raises(ValueError,match='2024 only'):
        source.prepare(SimpleNamespace(season='2023-24'))


def test_literal_anchor_not_fuzzy():
    page=BeautifulSoup('<p>23 Aug 24 FC Barcelona</p>','lxml')
    source.require_text(page,'23   Aug 24')
    with pytest.raises(ValueError):source.require_text(page,'23 Aug 25')


@pytest.mark.parametrize('fault',['name','birth_date','source_profile_url','identity_policy'])
def test_positive_member_namespace_cannot_be_forged(monkeypatch,fault):
    person=dict(name='Kyle Walker',birth_date='1990-05-28',source_player_id='wikipedia:Kyle_Walker',
        source_provider='wikipedia',source_profile_url=source.SOURCES['city-opening-walker-wikipedia'],
        identity_policy=source.PERSON_POLICY)
    monkeypatch.setattr(source,'sources',lambda:({'Kyle Walker':dict(source_person=person)},[]))
    assert source.verify_person(person).startswith('person-wikipedia-')
    forged=copy.deepcopy(person);forged[fault]='wrong'
    with pytest.raises(ValueError):source.verify_person(forged)


def test_factory_cannot_silently_drop_atomic_owner_layer():
    source.reject_factory_recipe(dict(artifacts=[]))
    with pytest.raises(ValueError,match='source-bound'):
        source.reject_factory_recipe(dict(artifacts=[dict(id=source.PREFIX+'2024-25')]))
