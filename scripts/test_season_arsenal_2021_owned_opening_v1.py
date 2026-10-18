import json
import re
from types import SimpleNamespace

import pytest

from scripts import season_arsenal_2021_owned_opening_v1 as subject
from scripts import build_registered_quality_release_v1 as build


def test_wrong_season_refuses_before_any_source_or_native_io():
    with pytest.raises(ValueError,match='Arsenal2021 only'):
        subject.prepare(SimpleNamespace(season='2020-21'))


def test_only_identity_changed_slots_clear_photos():
    plan=dict(assignment=dict(replacements=[dict(carrier_id=1),dict(carrier_id=2)],
        retained_Arsenal=[[100,3]],moved_into_Arsenal=[[200,4]]))
    assert subject.selected_carriers(plan)=={1,2}


def test_absent_receipt_is_not_an_arsenal_transaction():
    assert subject.reconstruction(SimpleNamespace(),'new') is None


def test_later_manager_receipt_cannot_be_discarded(tmp_path):
    receipt=tmp_path/'compiler.json';receipt.write_text(json.dumps(dict(compilation_mode='known-good-baseline-manager-name-delta')))
    assert subject.reconstruction(SimpleNamespace(compiler_receipt_path=receipt),'new') is None


def test_latest_opening_receipt_precedes_inherited_donor_role_layer(monkeypatch):
    from scripts import season_donor_keeper_role_delta_v1 as donor
    previous=SimpleNamespace()
    monkeypatch.setattr(build.registry,'load_preferred_release',lambda _:previous)
    monkeypatch.setattr(build,'_build_manager_reconstruction',lambda *a,**k:None)
    monkeypatch.setattr(subject,'reconstruction',lambda *a:dict(Arsenal_opening_replayed=True))
    monkeypatch.setattr(donor,'reconstruction',lambda *a:pytest.fail('older inherited role layer must not hide opening transaction'))
    assert build.build('2021-22',release_id='new')==dict(Arsenal_opening_replayed=True)
def test_recipe_artifact_id_uses_canonical_lowercase_identifier():
    assert re.fullmatch(r'[a-z][a-z0-9-]{1,79}',subject.PREFIX+'2021-22')


@pytest.mark.parametrize('desired,expected',[
    ('John Carrierb','John CARRIERB'),('Calum Chambers','Calum CHAMBERS')])
def test_exact_native_surname_casing_comes_from_real_writer(tmp_path,desired,expected):
    from scripts.test_season_package_compiler_v2 import _indexed_fdi,_dd6361_player_payload
    dbdat=tmp_path/'DBDAT';dbdat.mkdir()
    (dbdat/'JUG98030.FDI').write_bytes(_indexed_fdi([(1,'NAME',_dd6361_player_payload(1))]))
    before=(dbdat/'JUG98030.FDI').read_bytes()
    result=subject.native_display_names(SimpleNamespace(game_path=tmp_path),{1:dict(name=desired)},[1])
    assert result=={1:expected}
    assert (dbdat/'JUG98030.FDI').read_bytes()==before

