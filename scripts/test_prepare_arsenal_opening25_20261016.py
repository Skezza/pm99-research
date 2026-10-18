import pytest
from types import SimpleNamespace
from scripts import prepare_arsenal_opening25_20261016 as subject


def test_known_wrong_annual_date_is_not_forced_into_current_recipe():
    row,conflict=subject.person_facts(335721,dict(birth_date='1997-10-08'),{'benwhite'},[
        dict(name='Ben White',birth_date='1997-11-08',position='D')])
    assert row['birth_date']=='1997-10-08'
    assert conflict['annual']=='1997-11-08'


def test_unreviewed_dob_conflict_cannot_be_silently_overridden():
    with pytest.raises(ValueError,match='unreviewed'):
        subject.person_facts(123,dict(birth_date='1997-10-08'),{'benwhite'},[
            dict(name='Ben White',birth_date='1997-11-08',position='D')])


def test_ambiguous_source_alias_does_not_choose_first_row():
    with pytest.raises(ValueError,match='one original annual identity'):
        subject.person_facts(123,dict(birth_date='1997-10-08'),{'benwhite'},[
            dict(name='Ben White',birth_date='1997-10-08',position='D')]*2)


def test_departed_player_period_facts_do_not_imply_opening_owner_or_shirt_number():
    captures=[dict(club_name='Udinese',source_path='udinese.txt',source_sha256='bound',players=[
        dict(name='Pablo Marí',birth_date='1993-08-31',position='D',nationality='ESP',shirt_number=22)])]
    verifier=SimpleNamespace(verify=lambda c:dict(status='raw-source-reparsed'))
    row,proof=subject.other_period_facts(dict(name='Pablo Marí',birth_date='1993-08-31'),{'pablomari'},captures,verifier)
    assert row['position']=='D' and row['nationality']=='ESP' and row['shirt_number'] is None
    assert 'not-owner-or-shirt-number' in proof['policy']


def test_secondary_disagreement_is_logged_not_majority_voted():
    captures=[dict(club_name='Other',source_path=str(i),source_sha256='bound',players=[
        dict(name='Pablo Marí',birth_date='1993-08-31',position='D',nationality=n)])
        for i,n in enumerate(('ESP','ESP','ENG'))]
    row,proof=subject.other_period_facts(dict(name='Pablo Marí',birth_date='1993-08-31'),{'pablomari'},
        captures,SimpleNamespace(verify=lambda c:dict(status='raw-source-reparsed')))
    assert row['nationality'] is None
    assert proof['secondary_disagreements']['nationality']==['ENG','ESP']
