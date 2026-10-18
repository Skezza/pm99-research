import pytest
from scripts import season_original_country_policy_v2 as subject
from scripts.build_2015_english92_release import NATIONALITY


def test_republic_of_congo_uses_its_own_native_entry_without_changing_old_mapping():
    assert NATIONALITY['CGO']=='ZAIRE'
    assert subject.native_country('CGO',dict(CONGO=111,ZAIRE=80,XXX=0))==(111,'CONGO')
    assert subject.native_country('COD',dict(CONGO=111,ZAIRE=80,XXX=0))==(80,'ZAIRE')
    assert NATIONALITY['CGO']=='ZAIRE'


@pytest.mark.parametrize('country',['ANT','MSR','KVX','GUY'])
def test_proven_unrepresentable_published_countries_become_xxx_not_england(country):
    assert subject.native_country(country,dict(ENGLAND=30,XXX=0))==(0,'XXX')


def test_unmapped_code_not_invented_or_silently_defaulted():
    with pytest.raises(ValueError,match='do not guess'):
        subject.native_country('ZZZ',dict(ENGLAND=30,XXX=0))


def test_absent_congo_entry_does_not_fall_back_to_zaire():
    with pytest.raises(ValueError,match='absent'):
        subject.native_country('CGO',dict(ZAIRE=80,XXX=0))


@pytest.mark.parametrize('targets',[{}, {'1':['birth_date']},{'1':['nationality'],'01':['nationality']},{'x':['nationality']}])
def test_only_explicit_unique_country_targets_accepted(targets):
    with pytest.raises(ValueError,match='explicit unique nationality-only'):
        subject.prepare(None,None,targets)


def test_new_country_layer_cannot_be_factory_recompiled():
    with pytest.raises(ValueError,match='exact SOURCE'):
        subject.reject_factory_recipe(dict(artifacts=[dict(id=subject.PREFIX+'proof')]))
