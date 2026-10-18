import datetime as dt
from scripts import season_rating_calibration_v3 as c
from scripts.test_season_rating_calibration_v1 import player,source

def test_missing_xi_is_unknown_not_reserve():
    p=player();club=dict(opening=dict(policy='preserve-existing-mode1'))
    assert c.status(p,club)=='unknown'
    assert c.editorial(p,80,'unknown',dt.date(2024,8,1))['quality']>c.editorial(p,80,'opening_squad',dt.date(2024,8,1))['quality']

def test_youth_unknown_not_given_reserve_cut():
    p=player(dob='2007-07-13');date=dt.date(2025,8,1)
    unknown=c.editorial(p,82,'unknown',date);reserve=c.editorial(p,82,'opening_squad',date)
    assert unknown['quality']==reserve['quality']+14

def test_rating_without_dob_never_invents_date():
    p=player(dob={'policy':'preserve-existing-mode1'})
    values=c.editorial(p,70,'unknown',dt.date(2000,8,1))
    assert 1<=values['quality']<=99 and values['handling']<=20
    assert p['facts']['birth_date']=={'policy':'preserve-existing-mode1'}

def test_fullname_subsequence_literal_words_not_fuzzy():
    assert c.subsequence(c.tokens('Lionel Messi'),c.tokens('Lionel Andrés Messi Cuccittini'))
    assert not c.subsequence(c.tokens('James Smith'),c.tokens('John Smith'))
    assert not c.subsequence(c.tokens('Messi'),c.tokens('Lionel Messi'))
    assert not c.subsequence(c.tokens('Lionel Messi'),c.tokens('Messi Lionel'))

def test_variation_not_seeded_by_slot_or_club():
    a=player();a['person_id']='slot-1';b=dict(a,person_id='slot-999',carrier_id=999)
    assert c.editorial(a,70,'unknown',dt.date(2000,8,1))==c.editorial(b,70,'unknown',dt.date(2000,8,1))

def test_source_identity_dob_and_uniqueness():
    p=player(name='Lionel Messi',dob='1987-06-24',position='F')
    row=source()|dict(player_id='158023',dob='1987-06-24',edition=16,long_name='Lionel Andrés Messi Cuccittini',short_name='L. Messi',positions='RW, CF')
    key=(16,'1987-06-24')
    assert c.match(p,2015,{}, {key:[row]})==row
    assert c.match(p,2000,{}, {key:[row]}) is None
    assert c.match(p,2015,{}, {key:[row,row|dict(player_id='other')]}) is None
    assert c.match(player(name='Lionel Messi',dob='1987-06-25'),2015,{}, {key:[row]}) is None

def test_yamal_known_identity_period_specific_editorial_anchor():
    p=player(name='Lamine Yamal',dob='2007-07-13',position='F')
    assert c.yamal_anchor(p,2025)['quality']==86
    assert c.yamal_anchor(p,2024)['quality']==82
    assert c.yamal_anchor(p,2022) is None
    assert c.yamal_anchor(player(name='Lamine Yamal',dob='2007-07-14'),2025) is None
