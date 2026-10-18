import copy
import pytest

from scripts import season_monagas_2003_missing_birthday_v1 as missing


def original():
    return dict(people=[dict(source_player_id=847961, independent_published_name='Enermis Rodríguez',
        confirmed_birth_date=None, source_gap='original-DOB-unpublished-or-unconfirmed',
        published_match_name='Enermis Rodríguez', membership='starting_xi')],
        original_bindings=[dict(path='original.html', sha256='original-digest')])


def test_known_provider_id_with_missing_date_is_not_a_fake_person(monkeypatch):
    report = original()
    monkeypatch.setattr(missing.source, 'prepare', lambda path: copy.deepcopy(report))
    person = missing.from_row(report['people'][0], report['original_bindings'])
    assert missing.verify(person) == 'person-transfermarkt-847961'
    assert person['birth_date'] is None


@pytest.mark.parametrize('field,value', [('birth_date', '1970-01-01'),
    ('given_name', 'Enermis'), ('family_name', 'Rodríguez'),
    ('source_player_id', 847941), ('name', 'Other Rodríguez'),
    ('source_provider', 'soccerbase'), ('identity_policy', 'guess')])
def test_unknown_secondary_date_does_not_allow_invented_identity(monkeypatch, field, value):
    report = original()
    monkeypatch.setattr(missing.source, 'prepare', lambda path: copy.deepcopy(report))
    person = missing.from_row(report['people'][0], report['original_bindings'])
    person[field] = value
    with pytest.raises(ValueError):
        missing.verify(person)


def test_source_change_is_not_accepted_from_saved_parsed_claim(monkeypatch):
    report = original()
    person = missing.from_row(copy.deepcopy(report['people'][0]), copy.deepcopy(report['original_bindings']))
    report['original_bindings'][0]['sha256'] = 'changed'
    monkeypatch.setattr(missing.source, 'prepare', lambda path: copy.deepcopy(report))
    with pytest.raises(ValueError, match='source'):
        missing.verify(person)


def test_known_birthday_cannot_be_erased(monkeypatch):
    report = original()
    report['people'][0]['confirmed_birth_date'] = '1972-01-01'
    with pytest.raises(ValueError, match='known'):
        missing.from_row(report['people'][0], report['original_bindings'])


def alias_source(tmp_path, monkeypatch):
    report = original()
    monkeypatch.setattr(missing.source, 'prepare', lambda path: copy.deepcopy(report))
    monkeypatch.setattr(missing.source, 'ROOT', tmp_path)
    monkeypatch.setattr(missing.registry, 'ROOT', tmp_path)
    raw = tmp_path / 'raw.json'
    missing.pipeline.write_canonical_json(raw, dict(data=[dict(id='847961',
        name='Enermis Rodríguez', shortName='E. Rodríguez', artistName='', displayName='')]))
    missing.pipeline.write_canonical_json(tmp_path / 'monagas-2003-original-person-candidates-v1.json',
        dict(batches=[dict(raw_path='raw.json', raw_sha256=missing.registry.sha256_file(raw))]))
    return missing.from_row(report['people'][0], report['original_bindings']), raw


def test_short_alias_is_published_not_a_guessed_surname(tmp_path, monkeypatch):
    person, _ = alias_source(tmp_path, monkeypatch)
    assert missing.display_candidates(person) == [dict(name='E. Rodríguez',
        method='original-explicit-unknown-DOB-shortName')]
    assert person['given_name'] is None and person['family_name'] is None


def test_changed_original_alias_response_refused(tmp_path, monkeypatch):
    person, raw = alias_source(tmp_path, monkeypatch)
    raw.write_bytes(b'{"data":[]}')
    with pytest.raises(ValueError, match='source changed'):
        missing.display_candidates(person)
