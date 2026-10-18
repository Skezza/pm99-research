from types import SimpleNamespace
import pytest
from scripts import build_registered_quality_release_v1 as build
from scripts import season_source_bound_shirt_numbers_v1 as shirts
from scripts import season_arsenal_2021_owned_opening_v1 as actors
from scripts import season_visual_patch_reconstruction_v1 as artwork
from scripts import season_source_bound_birthday_disagreements_v1 as birthdays


@pytest.fixture(autouse=True)
def isolate_unrelated_newer_alias_layers(monkeypatch):
    # These deliberate receipt-less stubs exercise shirt/coach/artwork order,
    # not the separately tested original-alias native reconstruction readers.
    from scripts import season_original_alias_countries_v1,season_stoke_commons_number_v1
    for module in (season_original_alias_countries_v1,season_stoke_commons_number_v1):
        monkeypatch.setattr(module,'reconstruction',lambda *args:None)


def test_current_shirt_layer_precedes_inherited_actor_layer(monkeypatch):
    monkeypatch.setattr(build.registry,'load_preferred_release',lambda s:SimpleNamespace())
    monkeypatch.setattr(build,'_build_manager_reconstruction',lambda *a,**k:None)
    monkeypatch.setattr(shirts,'reconstruction',lambda *a:dict(exact_shirt_layer_replayed=True))
    monkeypatch.setattr(actors,'reconstruction',lambda *a:pytest.fail('older actor plan cannot hide shirt byte delta'))
    assert build.build('2021-22',release_id='proof')==dict(exact_shirt_layer_replayed=True)


def test_later_coach_layer_not_dropped_by_inherited_shirt_locator(monkeypatch):
    monkeypatch.setattr(build.registry,'load_preferred_release',lambda s:SimpleNamespace())
    monkeypatch.setattr(build,'_build_manager_reconstruction',lambda *a,**k:dict(latest_coach_replayed=True))
    monkeypatch.setattr(shirts,'reconstruction',lambda *a:pytest.fail('older shirt plan cannot hide coach update'))
    assert build.build('2021-22',release_id='proof')==dict(latest_coach_replayed=True)


def test_latest_artwork_stage_precedes_inherited_shirt_receipt(monkeypatch):
    monkeypatch.setattr(build.registry,'load_preferred_release',lambda s:SimpleNamespace())
    monkeypatch.setattr(artwork,'reconstruction',lambda *a:dict(latest_artwork_replayed=True))
    monkeypatch.setattr(build,'_build_manager_reconstruction',lambda *a,**k:pytest.fail('inherited compiler receipt cannot hide later artwork'))
    monkeypatch.setattr(shirts,'reconstruction',lambda *a:pytest.fail('inherited shirt cannot hide later artwork'))
    assert build.build('2021-22',release_id='proof')==dict(latest_artwork_replayed=True)


def test_latest_birthday_layer_precedes_inherited_player_layer(monkeypatch):
    monkeypatch.setattr(build.registry,'load_preferred_release',lambda s:SimpleNamespace())
    monkeypatch.setattr(build,'_build_manager_reconstruction',lambda *a,**k:None)
    monkeypatch.setattr(birthdays,'reconstruction',lambda *a:dict(latest_birthday_replayed=True))
    monkeypatch.setattr(shirts,'reconstruction',lambda *a:pytest.fail('older player layer cannot hide birthday correction'))
    assert build.build('2011-12',release_id='proof')==dict(latest_birthday_replayed=True)


def test_later_manager_layer_precedes_inherited_birthday(monkeypatch):
    monkeypatch.setattr(build.registry,'load_preferred_release',lambda s:SimpleNamespace())
    monkeypatch.setattr(build,'_build_manager_reconstruction',lambda *a,**k:dict(latest_manager_replayed=True))
    monkeypatch.setattr(birthdays,'reconstruction',lambda *a:pytest.fail('older birthday cannot hide manager correction'))
    assert build.build('2011-12',release_id='proof')==dict(latest_manager_replayed=True)
