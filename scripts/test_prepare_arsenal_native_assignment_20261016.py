import pytest

from scripts import prepare_arsenal_native_assignment_20261016 as subject


def player(carrier,name,born,club='english-club-309',pid=None):
    return dict(carrier_id=carrier,name=name,club_id=club,facts=dict(birth_date=born),published_id=pid)


def desired(pid,name,born):
    return dict(source_person=dict(source_player_id=pid,name=name,birth_date=born),
        source_player=dict(name=name,birth_date=born))


@pytest.fixture(autouse=True)
def numeric_identities(monkeypatch):
    monkeypatch.setattr(subject.identities,'unique_person',lambda p,people:
        None if p['published_id'] is None else dict(source_player_id=p['published_id']))


def test_retained_carrier_and_coupled_move_not_reallocated():
    a=desired(1,'Retained Person','1990-01-01');b=desired(2,'Moved Person','1991-01-01')
    paired=[dict(carrier_id=20,moved_source_player_id=2,replacement=desired(3,'New Person','1992-01-01'))]
    kept,moved=subject.represented([
        player(10,'Retained Person','1990-01-01',pid=1),
        player(20,'Moved Person','1991-01-01',club='outside',pid=2)],{},[a,b],paired)
    assert kept=={1:10} and moved=={2:20}


def test_known_original_white_date_conflict_is_explicit_not_generic_matching():
    rows=[player(10,'Ben White','1997-11-08')]
    kept,moved=subject.represented(rows,{},[desired(335721,'Ben White','1997-10-08')],[])
    assert kept=={335721:10} and not moved
    rows[0]['facts']['birth_date']='1997-11-09'
    with pytest.raises(ValueError,match='full-name alias'):
        subject.represented(rows,{},[desired(335721,'Ben White','1997-10-08')],[])


def test_duplicate_original_person_cannot_be_admitted():
    rows=[player(10,'Person','1990-01-01',pid=1),player(11,'Alias','1990-01-01',pid=1)]
    with pytest.raises(ValueError,match='multiple game carriers'):
        subject.represented(rows,{},[desired(1,'Person','1990-01-01')],[])


def test_outside_owner_requires_coupled_source_not_silent_copy():
    with pytest.raises(ValueError,match='unpaired outside'):
        subject.represented([player(10,'Person','1990-01-01',club='outside',pid=1)],{},
            [desired(1,'Person','1990-01-01')],[])


def test_unidentified_same_birthday_cannot_be_assumed_distinct():
    with pytest.raises(ValueError,match='same-birthday'):
        subject.represented([player(10,'Other','1990-01-01')],{},[desired(1,'Person','1990-01-01')],[])


def test_independently_distinct_same_birthday_is_not_duplicate():
    assert subject.represented([player(10,'Other','1990-01-01',pid=2)],{},
        [desired(1,'Person','1990-01-01')],[])==({},{})


def test_retained_identified_person_does_not_need_unrelated_birthday_replacement():
    rows=[player(10,'Person','1990-01-01',pid=1),player(11,'Other','1990-01-01')]
    assert subject.represented(rows,{},[desired(1,'Person','1990-01-01')],[])==({1:10},{})
