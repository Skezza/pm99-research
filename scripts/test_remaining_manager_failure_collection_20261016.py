"""Find the full repair queue without approving a partial failed admission."""
from types import SimpleNamespace
import pytest
from scripts import season_remaining_manager_tenures_20261016 as subject
from scripts import build_savio_bobb_alias_reserve_20261011 as storage


def test_later_seasons_are_checked_after_first_source_failure(tmp_path, monkeypatch):
    seasons=['2000-01','2001-02','2002-03']
    monkeypatch.setattr(subject,'ROOT',tmp_path/'no-frozen-plans')
    monkeypatch.setattr(subject.sources,'ROOT',tmp_path/'diagnostics')
    subject.sources.ROOT.mkdir()
    def read(path):
        if path.name=='source-admission-summary.json':
            return dict(seasons=[dict(season=s,corrections=1) for s in seasons])
        return dict(state='delivered-native-SOURCE-and-runner-verified',canonical_updates=49,deferred_remaining=36)
    monkeypatch.setattr(subject.pipeline,'read_json_file',read)
    monkeypatch.setattr(subject,'verified_sources',lambda:None)
    monkeypatch.setattr(subject.registry,'supported_seasons',lambda:seasons)
    monkeypatch.setattr(subject.registry,'load_registered_release',lambda s,r:SimpleNamespace(season=s,release_id=r))
    checked=[]
    def prepare(base):
        checked.append(base.season)
        if base.season!='2001-02':
            raise ValueError('unproven original coach '+base.season)
        return dict(season=base.season,summary=dict(corrections=1))
    monkeypatch.setattr(subject,'prepare',prepare)
    monkeypatch.setattr(storage,'retained',lambda *a:pytest.fail('failed batch must not freeze any plan'))
    with pytest.raises(ValueError,match='failed in 2 seasons'):
        subject.main()
    assert checked==seasons and not subject.ROOT.exists()
    files=list((tmp_path/'diagnostics').glob('admission-failures-*.json'))
    assert len(files)==1
    import json
    diagnostic=json.loads(files[0].read_text())
    assert [r['season'] for r in diagnostic['failures']]==['2000-01','2002-03']
    assert diagnostic['independently_admissible_seasons']==['2001-02']
    assert diagnostic['native_writes']==diagnostic['frozen_plans_written']==0
