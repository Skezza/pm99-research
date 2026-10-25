import pytest

from scripts import build_registered_quality_release_v1 as build
from scripts import season_disk_budget_v1 as disk_budget
from scripts import test_build_registered_manager_reconstruction_v1 as fixtures


@pytest.mark.parametrize("reserve", [
    disk_budget.DEFAULT_RESERVE,
    6 * 1024**3,
])
def test_manager_source_reconstruction_forwards_selected_reserve(tmp_path, monkeypatch, reserve):
    _, candidate, _, calls, _ = fixtures.setup(tmp_path, monkeypatch)

    result = build._build_manager_reconstruction(
        candidate, release_id="rebuilt", minimum_free_bytes=reserve)

    assert result["minimum_free_bytes"] == reserve
    assert calls[0][1]["minimum_free_bytes"] == reserve
    assert result["complete_game_inventory_identical"]
    assert result["complete_recipe_identical"]


def test_manager_source_reconstruction_defaults_to_eight_gib(tmp_path, monkeypatch):
    _, candidate, _, calls, _ = fixtures.setup(tmp_path, monkeypatch)

    result = build._build_manager_reconstruction(candidate, release_id="rebuilt")

    assert result["minimum_free_bytes"] == disk_budget.DEFAULT_RESERVE
    assert calls[0][1]["minimum_free_bytes"] == disk_budget.DEFAULT_RESERVE


def test_manager_source_reconstruction_rejects_less_than_six_gib_before_publishing(tmp_path, monkeypatch):
    _, candidate, _, calls, _ = fixtures.setup(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="at least 6 GiB"):
        build._build_manager_reconstruction(
            candidate, release_id="rebuilt", minimum_free_bytes=5 * 1024**3)

    assert calls == []
