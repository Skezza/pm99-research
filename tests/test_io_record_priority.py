"""Unit tests for strict-first record candidate selection helpers."""

from app.io import _merge_record_candidate, _record_display_name
from app.models import PlayerRecord


def test_record_display_name_backfills_name_field():
    record = PlayerRecord(given_name="David", surname="Beckham", name="")

    display = _record_display_name(record)

    assert display == "David Beckham"
    assert record.name == "David Beckham"


def test_merge_record_candidate_prefers_higher_priority():
    records = {}
    low_priority = PlayerRecord(given_name="David", surname="Beckham", name="David Beckham")
    high_priority = PlayerRecord(given_name="David", surname="Beckham", name="David Beckham")

    _merge_record_candidate(records, offset=100, record=low_priority, priority=100)
    _merge_record_candidate(records, offset=200, record=high_priority, priority=300)

    priority, offset, record = records["DAVID BECKHAM"]
    assert priority == 300
    assert offset == 200
    assert record is high_priority


def test_merge_record_candidate_ignores_placeholders():
    records = {}
    placeholder = PlayerRecord(given_name="Unknown", surname="", name="Unknown Player")

    _merge_record_candidate(records, offset=100, record=placeholder, priority=300)

    assert records == {}
