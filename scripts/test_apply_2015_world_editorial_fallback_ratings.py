from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import apply_2015_world_editorial_fallback_ratings as ratings  # noqa: E402


def _player(*, position: str, role: str, player_id: int = 101) -> dict[str, object]:
    opening: dict[str, object] = {"lineup_role": role} if role in {"starting_lineup", "substitutes"} else {"status": "not-in-strictly-reconciled-opening-xi-or-bench"}
    return {
        "player_carrier_id": player_id,
        "source_squad_index": 20 if role == "source-squad-depth" else 4,
        "source_player": {"position": position, "birth_date": "1990-01-02", "height_cm": 190},
        "opening_fixture_presence": opening,
    }


def test_editorial_fallback_is_deterministic_and_position_shaped() -> None:
    forward = _player(position="F", role="starting_lineup")
    defender = _player(position="D", role="starting_lineup", player_id=102)
    one = ratings._editorial_values(carrier_id=1, player=forward, base=68, ceiling=82, hierarchy_source="carrier-retained-fifa16")
    two = ratings._editorial_values(carrier_id=1, player=forward, base=68, ceiling=82, hierarchy_source="carrier-retained-fifa16")
    defensive = ratings._editorial_values(carrier_id=1, player=defender, base=68, ceiling=82, hierarchy_source="carrier-retained-fifa16")

    assert one == two
    assert one["status"] == "editorial-fallback-applied"
    assert one["basis"]["source_squad_role"] == "starting_lineup"
    assert one["values"]["finishing"] > one["values"]["stand_tackle"]
    assert defensive["values"]["stand_tackle"] > defensive["values"]["finishing"]


def test_editorial_fallback_respects_the_carrier_star_protection_ceiling() -> None:
    player = _player(position="M", role="starting_lineup")
    result = ratings._editorial_values(carrier_id=7, player=player, base=80, ceiling=81, hierarchy_source="carrier-retained-fifa16")

    assert result["values"]["rating"] <= 81
    assert result["basis"]["carrier_star_protection_ceiling"] == 81
