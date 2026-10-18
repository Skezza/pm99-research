"""Adversarial checks for the original Arsenal side and coordinate rotation."""
from types import SimpleNamespace

import pytest

from scripts import arsenal_2021_opening_transaction_source_v1 as subject


def fixture():
    # Deliberately shuffled DOM order: it is not native tactical slot order.
    coordinates = [(1,80,40),(4,63,28),(2,61,73),(5,61,7.5),
                   (3,63,52.5),(6,43,52),(7,43,28),(9,23,40),
                   (10,18,15),(8,18,65),(11,3,40)]
    nodes = ''.join(
        f'<div class="formation-player-container" style="top:{top}%;left:{left}%">'
        f'<a href="/person/profil/spieler/{pid}">Person</a></div>'
        for pid,top,left in coordinates)
    return ('<div class="aufstellung-box"><div class="large-6">'
        '<a href="/arsenal/startseite/verein/11">Arsenal</a>'
        '<span class="formation-subtitle">Starting Line-up: 4-2-3-1</span>'
        + nodes + '</div><div class="large-6">'
        '<a href="/brentford/startseite/verein/1148">Brentford</a>'
        '</div></div>').encode()


def test_original_numeric_side_and_rotation_not_dom_order():
    rows=subject.grid(fixture(),11,'4-2-3-1',range(1,12))
    assert [r['source_player_id'] for r in rows]==list(range(1,12))


def test_opponent_cannot_be_accepted_as_arsenal():
    with pytest.raises(ValueError,match='published formation'):
        subject.grid(fixture(),1148,'4-2-3-1',range(1,12))


def test_duplicate_numeric_club_sides_are_not_first_match_wins():
    with pytest.raises(ValueError,match='one exact numeric'):
        subject.grid(fixture()+fixture(),11,'4-2-3-1',range(1,12))


@pytest.mark.parametrize('raw',[
    fixture().replace(b'top:3%',b'top:18%'),
    fixture().replace(b'top:80%',b'top:101%'),
    fixture().replace(b'left:73%',b'left:52.5%'),
    fixture().replace(b'/spieler/11',b'/spieler/10'),
    fixture().replace(b'top:3%',b'top:3px'),
])
def test_ambiguous_or_invalid_source_grid_fails_closed(raw):
    with pytest.raises(ValueError):
        subject.grid(raw,11,'4-2-3-1',range(1,12))


def test_philogene_date_correction_requires_original_identity_bridge(monkeypatch):
    biography=b'<table class="infobox">Jaden Richard Philogene-Bidace <span class="bday">2002-02-08</span></table>'
    monkeypatch.setattr(subject,'source_rows',lambda key:('source',biography,{'sha256':'original'}))
    captures=[dict(players=[dict(name='Jaden Philogene-Bidace',birth_date='2002-05-18',
        position='M',shirt_number=47,nationality='ENG')])]
    verifier=SimpleNamespace(verify=lambda capture:dict(status='raw-source-reparsed'))
    row,proof=subject.philogene(dict(birth_date='2002-02-08'),captures,verifier)
    assert row['birth_date']=='2002-02-08' and row['shirt_number'] is None
    assert proof['annual_birth_date']=='2002-05-18'
    assert captures[0]['players'][0]['birth_date']=='2002-05-18'
    with pytest.raises(ValueError,match='bridge'):
        subject.philogene(dict(birth_date='2002-05-18'),captures,verifier)


def test_correct_dob_without_full_identity_does_not_admit_namesake(monkeypatch):
    monkeypatch.setattr(subject,'source_rows',lambda key:('source',
        b'<table class="infobox">Other person <span class="bday">2002-02-08</span></table>',{}))
    with pytest.raises(ValueError,match='bridge'):
        subject.philogene(dict(birth_date='2002-02-08'),[],None)
