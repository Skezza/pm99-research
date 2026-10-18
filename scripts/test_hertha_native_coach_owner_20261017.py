"""Do not introduce a second active native manager under an alias."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import deliver_hertha_dated_cohort_coach_20261017 as delivery


def fake(monkeypatch,holders,names):
    monkeypatch.setattr(delivery.build.source.prior.old,'_manager_graph',lambda **kw:(holders,names))
    return SimpleNamespace(game_path=Path('/not-used'),manifest_sha256='immutable-actual-manifest')


def test_only_exact_selected_active_coach(monkeypatch):
    actual=fake(monkeypatch,{1313:[dict(carrier_id=421)]},{1313:'Stevens',999:'H. Stevens'})
    assert delivery.coach_owner_proof(actual)['active_named_coaches']==[
        dict(manager_id=1313,native_name='Stevens',owners=[421])]


@pytest.mark.parametrize('names,holders',[
    ({1313:'Stevens',999:'H. Stevens'},{1313:[dict(carrier_id=421)],999:[dict(carrier_id=999)]}),
    ({1313:'Stevens'},{1313:[dict(carrier_id=421),dict(carrier_id=999)]}),
    ({1313:'Röber'},{1313:[dict(carrier_id=421)]}),
])
def test_active_alias_shared_owner_or_old_coach_refused(monkeypatch,names,holders):
    actual=fake(monkeypatch,holders,names)
    with pytest.raises(ValueError,match='dated reconciliation'):delivery.coach_owner_proof(actual)
