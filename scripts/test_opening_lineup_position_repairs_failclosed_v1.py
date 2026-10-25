"""Tactical slots must never manufacture a named player's primary role."""
import copy

import pytest

from scripts import apply_opening_lineup_position_repairs_v1 as repair


@pytest.mark.parametrize("keeper_count", [0, 2])
def test_conflicting_xi_cannot_change_source_positions(tmp_path, monkeypatch, keeper_count):
    players = [
        {"id": str(i), "facts": {"primary_position": "G" if i < keeper_count else "M"}}
        for i in range(11)
    ]
    package = {"players": players, "clubs": [{
        "id": "club", "name": "Source club", "opening": {
            "starting_xi_player_ids": [str(i) for i in range(11)],
            "tactics_positions": [[100, 50, 100, 50]] + [[100, 250, 100, 250]] * 10,
        },
    }]}
    original = copy.deepcopy(package)
    path = tmp_path / "recipe.json"
    path.write_bytes(b"original recipe")
    monkeypatch.setattr(repair.package_v2, "read_canonical_package", lambda _: package)
    with pytest.raises(repair.OpeningLineupPositionRepairError, match="not player-position evidence"):
        repair._plan_package(path)
    assert package == original
    assert path.read_bytes() == b"original recipe"
