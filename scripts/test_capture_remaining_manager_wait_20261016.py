"""Capture waits cannot treat unrelated or stopped jobs as live builders."""
import os
import pytest
from scripts import capture_remaining_manager_tenures_20261016 as subject


def test_stopped_builder_without_full_source_proof_is_not_restarted(tmp_path,monkeypatch):
    monkeypatch.setattr(subject.batch,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='builders stopped'):
        subject.wait_for_build('2001-02',[999999999])


def test_unrelated_live_process_is_not_counted_as_our_builder(tmp_path,monkeypatch):
    monkeypatch.setattr(subject.batch,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='builders stopped'):
        subject.wait_for_build('2001-02',[os.getpid()])


def test_completed_source_proof_needs_no_live_builder(tmp_path,monkeypatch):
    monkeypatch.setattr(subject.batch,'ROOT',tmp_path)
    root=tmp_path/'2001-02';root.mkdir()
    (root/'complete-SOURCE-replay.json').write_text('{}')
    # This only ends the wait; run() independently validates the complete proof.
    subject.wait_for_build('2001-02',[999999999])
