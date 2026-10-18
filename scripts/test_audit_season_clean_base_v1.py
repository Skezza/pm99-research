"""Unit tests for clean-base carrier-diff accounting."""

import pytest

from scripts.audit_season_clean_base_v1 import CleanBaseAuditError, _changed


def test_changed_reports_only_payload_differences() -> None:
    assert _changed({1: b"a", 2: b"b"}, {1: b"a", 2: b"c"}, label="fixture") == [2]


def test_changed_rejects_record_set_drift() -> None:
    with pytest.raises(CleanBaseAuditError, match="record ID set changed"):
        _changed({1: b"a"}, {1: b"a", 2: b"b"}, label="fixture")
