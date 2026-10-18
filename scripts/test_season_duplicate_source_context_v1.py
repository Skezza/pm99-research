import datetime as dt
import json
import pytest

from scripts import season_duplicate_source_context_v1 as context
from scripts import season_historical_transfer_review_v1 as legacy
from scripts import season_release_registry_v1 as registry


def original_snapshot(tmp_path, monkeypatch, with_appearances=False):
    import duckdb
    monkeypatch.setattr(registry,'ROOT',tmp_path)
    database=tmp_path/'original.duckdb'
    c=duckdb.connect(str(database))
    c.execute('CREATE TABLE version (version VARCHAR)');c.execute("INSERT INTO version VALUES ('pinned-v1')")
    c.execute('CREATE TABLE players (player_id INTEGER, name VARCHAR, first_name VARCHAR, last_name VARCHAR, date_of_birth DATE, url VARCHAR)')
    c.execute('INSERT INTO players VALUES (?,?, ?, ?, ?, ?)',[99,'Full Name','Full','Name',dt.date(1990,1,2),'https://original.example/99'])
    c.execute('CREATE TABLE transfers (player_id INTEGER, transfer_date DATE, from_club_id INTEGER, to_club_id INTEGER, from_club_name VARCHAR, to_club_name VARCHAR)')
    c.execute("INSERT INTO transfers VALUES (99, '2021-07-01', 1, 44, 'Prior', 'Opening'), (99, '2022-01-01', 44, 2, 'Opening', 'Later'), (99, NULL, 2, 3, 'Later', 'Unknown')")
    if with_appearances:
        c.execute('CREATE TABLE games (game_id INTEGER, season INTEGER, competition_type VARCHAR)')
        c.execute('CREATE TABLE appearances (game_id INTEGER, player_club_id INTEGER, player_id INTEGER)')
        c.execute("INSERT INTO games VALUES (1,2021,'domestic_league')")
        c.execute('INSERT INTO appearances VALUES (1,44,99)')
    c.close()
    receipt=tmp_path/'pin.json';receipt.write_text(json.dumps({'source':{
        'database_sha256':registry.sha256_file(database),'database_version':'pinned-v1',
        'dataset_project_url':'https://original.example/dataset'}}))
    return database,receipt


def test_no_appearance_tables_required_for_identical_people_and_dated_transfer_proof(tmp_path,monkeypatch):
    database,receipt=original_snapshot(tmp_path,monkeypatch)
    people,events,binding=context.load_snapshot(database,receipt)
    person=legacy.unique_person({'name':'Full Name','facts':{'birth_date':'1990-01-02'}},people)
    assert person['source_player_id']==99
    interval=legacy.transfer_interval(events[99],'2021-08-07')
    assert interval['status']=='recorded-entry-and-exit-bracket-fixture'
    assert interval['source_owner_club_id']==44
    assert len(events[99])==2
    assert binding['sha256']==registry.sha256_file(database)


def test_explicit_fast_scope_has_exact_legacy_people_transfers_and_pin(tmp_path,monkeypatch):
    database,receipt=original_snapshot(tmp_path,monkeypatch,True)
    people,events,binding=context.load_snapshot(database,receipt)
    old_people,old_events,appearances,old_binding=legacy.load_snapshot(database,receipt)
    assert (people,events,binding)==(old_people,old_events,old_binding)
    assert appearances[('2021',44)]=={99}


@pytest.mark.parametrize('problem',['sha','version'])
def test_changed_source_snapshot_or_pin_version_refused(tmp_path,monkeypatch,problem):
    database,receipt=original_snapshot(tmp_path,monkeypatch)
    doc=json.loads(receipt.read_text())
    doc['source']['database_sha256' if problem=='sha' else 'database_version']='changed'
    receipt.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='immutable'): context.load_snapshot(database,receipt)


def test_source_context_refuses_different_snapshot_before_reading_any_game():
    with pytest.raises(ValueError,match='snapshot differs'):
        context.context({'bindings':{'snapshot':{'sha256':'bound'}}},{},{},{'sha256':'other'})
