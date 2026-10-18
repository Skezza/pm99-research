import json
from pathlib import Path
import pytest
from scripts import build_exact_position_batch_20261017 as subject


def setup(monkeypatch,tmp_path,*,partial=False,started=False):
    monkeypatch.setattr(subject,'ROOT',tmp_path/'proofs')
    monkeypatch.setattr(subject.registry,'ROOT',tmp_path)
    monkeypatch.setattr(subject.registry,'locator_path',lambda *a:tmp_path/'absent-locator.json')
    folder=subject.ROOT/'2017-18';folder.mkdir(parents=True)
    plan=folder/'position-plan.json';plan.write_text('{}')
    (folder/'inert.json').write_text('{}')
    (folder/'source-only-reserve-stop.json').write_text(json.dumps(dict(native_build_started=started,
        source_plan_sha256=subject.registry.sha256_file(plan))))
    if partial:(tmp_path/'.local/historical-role-deltas-v1/2017-18'/subject.RELEASE).mkdir(parents=True)
    return folder


def test_existing_source_plan_needs_explicit_resume(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    with pytest.raises(ValueError,match='explicit inspected resume'):
        subject.main('2017-18','base',[10683],Path('unused'))


@pytest.mark.parametrize('changes',[dict(partial=True),dict(started=True)])
def test_partial_native_output_or_a_started_build_cannot_be_replayed_as_source_only(monkeypatch,tmp_path,changes):
    setup(monkeypatch,tmp_path,**changes)
    with pytest.raises(ValueError,match='source-only|partial native'):
        subject.main('2017-18','base',[10683],Path('unused'),resume_source_only=True)


def test_exact_verified_reserve_stop_reaches_source_revalidation_not_automatic_native_write(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    def revalidate(*args):raise RuntimeError('source revalidation reached')
    monkeypatch.setattr(subject.registry,'load_registered_release',revalidate)
    with pytest.raises(RuntimeError,match='source revalidation reached'):
        subject.main('2017-18','base',[10683],Path('unused'),resume_source_only=True)
