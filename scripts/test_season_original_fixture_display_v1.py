import copy
import hashlib
import pytest
from scripts import season_original_fixture_display_v1 as display
from scripts import season_august_source_fallback_v1 as fallback


def actor(tmp_path,monkeypatch):
    monkeypatch.setattr(display.registry,'ROOT',tmp_path)
    bindings=[]
    for index in range(3):
        path=tmp_path/f'original{index}.html';path.write_bytes(f'bound source {index}'.encode())
        bindings.append(dict(path=path.name,sha256=display.registry.sha256_file(path)))
    parsed=dict(club='Hajduk Kula',fixture_date='2002-08-10',
        starting_xi=[dict(published_match_name='Trajkovic' if i==4 else 'Other') for i in range(11)])
    monkeypatch.setattr(display.opening,'parse',lambda *raw:parsed)
    claim=fallback.surname(published_surname='Trajkovic',provider='dekisa',
        club='Hajduk Kula',fixture_date='2002-08-10',source_binding=bindings[0])
    key=hashlib.sha256(display.pipeline.canonical_json_bytes(claim)).hexdigest()[:24]
    return dict(source_player_id='fixture-actor:'+key,name='Trajkovic',given_name=None,
        family_name='Trajkovic',birth_date=None,source_provider='original-fixture',
        identity_policy=fallback.SCHEMA,identity_evidence=claim,original_fixture_bindings=bindings)


def test_unknown_actor_is_not_a_fake_transfermarkt_person(tmp_path,monkeypatch):
    person=actor(tmp_path,monkeypatch)
    assert display.verify_actor(person).startswith('person-original-fixture-')
    assert person['birth_date'] is None


@pytest.mark.parametrize('field,value',[('given_name','Marko'),('name','Marko Trajkovic'),
    ('birth_date','1975-01-01'),('source_provider','transfermarkt'),
    ('source_player_id',123),('identity_policy','guessed')])
def test_actor_cannot_invent_name_birthday_or_provider(tmp_path,monkeypatch,field,value):
    person=actor(tmp_path,monkeypatch);person[field]=value
    with pytest.raises(ValueError):display.verify_actor(person)


def test_changed_original_source_is_refused(tmp_path,monkeypatch):
    person=actor(tmp_path,monkeypatch)
    (tmp_path/'original0.html').write_bytes(b'changed source')
    with pytest.raises(ValueError,match='source changed'):display.verify_actor(person)


def test_missing_fixture_bindings_is_refused(tmp_path,monkeypatch):
    person=actor(tmp_path,monkeypatch);person.pop('original_fixture_bindings')
    with pytest.raises(ValueError,match='lacks original'):display.verify_actor(person)
