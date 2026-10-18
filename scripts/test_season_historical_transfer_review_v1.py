import datetime as dt
import json
from types import SimpleNamespace

import pytest

from scripts import season_historical_transfer_review_v1 as review


def player(name='Cristiano Ronaldo', date='1985-02-05'):
    return {'name': name, 'facts': {'birth_date': date}}


def event(date, source, destination):
    return {'date': date, 'from_club_id': source, 'to_club_id': destination,
            'from_club': str(source), 'to_club': str(destination)}


def test_exact_source_names_and_dob_without_initial_guess():
    index = review.person_index([(8198, 'Cristiano Ronaldo', 'Cristiano', 'Ronaldo dos Santos', dt.date(1985, 2, 5), 'https://source/profile/8198')])
    assert review.unique_person(player(), index)['source_player_id'] == 8198
    assert review.unique_person(player('Cristiano Ronaldo dos Santos'), index)['source_player_id'] == 8198
    assert review.unique_person(player('C. Ronaldo'), index) is None
    assert review.unique_person(player(date='1985-02-06'), index) is None


def test_explicit_shirt_heading_keeps_full_name_dob_and_ambiguity_guards():
    row = (42, 'Kevin Long', 'Kevin', 'Long', dt.date(1990, 8, 18), 'https://source/42')
    index = review.person_index([row])
    labelled = player('#13 Kevin Long', '1990-08-18')
    assert review.unique_person(labelled, index)['source_player_id'] == 42
    assert labelled['name'] == '#13 Kevin Long'
    for name in ('#13 K. Long', '13 Kevin Long', '#123 Kevin Long', 'Kevin Long 13'):
        assert review.unique_person(player(name, '1990-08-18'), index) is None
    assert review.unique_person(player('#13 Kevin Long', '1990-08-19'), index) is None
    ambiguous = review.person_index([row, (43, *row[1:])])
    assert review.unique_person(labelled, ambiguous) is None


def test_future_transfer_cannot_change_opening_owner():
    events = [event('2003-08-12', 336, 985), event('2009-07-06', 985, 418)]
    found = review.transfer_interval(events, '2005-08-13')
    assert found['source_owner_club_id'] == 985
    assert found['status'] == 'recorded-entry-and-exit-bracket-fixture'


def test_entry_only_and_missing_transfer_chain_are_not_certified():
    assert review.transfer_interval([event('2003-08-12', 336, 985)], '2005-08-13')['status'] == 'entry-only-unverified-continuity'
    events = [event('2003-08-12', 336, 985), event('2009-07-06', 7, 418)]
    assert review.transfer_interval(events, '2005-08-13')['status'] == 'recorded-transfer-chain-disagrees'


def test_same_day_moves_need_chronology_not_arbitrary_sorting():
    events = [event('2005-07-01', 1, 2), event('2005-07-01', 2, 3), event('2007-07-01', 3, 4)]
    assert review.transfer_interval(events, '2005-08-13')['status'] == 'same-day-transfer-order-unresolved'


def test_repeated_original_blob_is_rehashed_once_but_conflicting_pin_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(review, 'ROOT', tmp_path)
    path = tmp_path / 'report.html'; path.write_bytes(b'original')
    calls = []
    digest = review.registry.sha256_file(path)
    monkeypatch.setattr(review.registry, 'sha256_file', lambda p: calls.append(p) or digest)
    source = {'path': 'report.html', 'sha256': digest}
    row = {'status': 'original-first-fixture-reparsed', 'evidence': {'raw_sources': [source, source]}}
    review.verify_opening_sources({'clubs': [row, row]})
    assert calls == [path]
    row['evidence']['raw_sources'] = [source, {**source, 'sha256': 'wrong'}]
    with pytest.raises(ValueError, match='source bytes changed'):
        review.verify_opening_sources({'clubs': [row]})


def test_resume_never_relabels_a_changed_recipe(tmp_path, monkeypatch):
    package = tmp_path / 'package.json'; package.write_text('{}')
    source = tmp_path / 'opening.json'; source.write_text('{"clubs": []}')
    release = SimpleNamespace(release_id='original', package_path=package)
    monkeypatch.setattr(review.registry, 'load_preferred_release', lambda s: release)
    binding = {'sha256': 'snapshot'}
    saved = tmp_path / 'review.json'
    saved.write_text(json.dumps({'schema_version': review.SCHEMA, 'season': '2000-01', 'summary': {'players': 1},
        'bindings': {'release_id': 'original', 'package_sha256': review.registry.sha256_file(package),
                     'snapshot': binding, 'opening_review_sha256': review.registry.sha256_file(source)}}))
    assert review.reuse_completed('2000-01', binding, source, saved) == {'players': 1}
    release.release_id = 'different'
    with pytest.raises(ValueError, match='inputs changed'):
        review.reuse_completed('2000-01', binding, source, saved)
