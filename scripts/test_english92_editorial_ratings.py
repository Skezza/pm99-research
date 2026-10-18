from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.english92_editorial_ratings import audit_editorial_distribution, load_editorial_rating_book  # noqa: E402


INPUT = ROOT / "scripts/data/2015-16-english92-editorial-ratings-v1.json"


def _synthetic_english92_rows():
    """Exercise every club transform without any third-party ratings fixture."""
    book = load_editorial_rating_book(INPUT)
    division_by_index = (
        ("Premier League", 20),
        ("Championship", 24),
        ("League One", 24),
        ("League Two", 24),
    )
    clubs = list(book.payload["club_strengths"])
    offset = 0
    rows = []
    for division, count in division_by_index:
        for club in clubs[offset:offset + count]:
            for number in range(25):
                position = ("G", "D", "M", "F")[number % 4]
                status = "starter" if number < 11 else ("bench" if number < 16 else "reserve")
                rating = book.rate(
                    club=club,
                    division=division,
                    player=f"Synthetic {number}",
                    position=position,
                    height_cm=190 if position in {"G", "D"} else 176,
                    birth_date_ddmmyy="01-01-90",
                    squad_status=status,
                )
                rows.append({"division": division, **rating})
        offset += count
    return book, rows


def test_editorial_input_is_complete_and_anchor_values_override_context() -> None:
    book = load_editorial_rating_book(INPUT)

    assert len(book.club_strengths) == 92
    assert len(book.players) >= 100
    assert book.rate(
        club="Manchester City", division="Premier League", player="Sergio Agüero",
        position="F", height_cm=173, birth_date_ddmmyy="02-06-88", squad_status="reserve",
    )["skills"]["quality"] == 92
    assert book.rate(
        club="Dagenham & Redbridge", division="League Two", player="Reserve Example",
        position="D", height_cm=182, birth_date_ddmmyy="01-01-95", squad_status="reserve",
    )["skills"]["quality"] < 50


def test_editorial_transform_is_deterministic_and_produces_varied_pm99_profiles() -> None:
    book, rows = _synthetic_english92_rows()
    first = book.rate(
        club="Arsenal", division="Premier League", player="Deterministic Example",
        position="M", height_cm=178, birth_date_ddmmyy="01-01-90", squad_status="starter",
    )
    second = book.rate(
        club="Arsenal", division="Premier League", player="Deterministic Example",
        position="M", height_cm=178, birth_date_ddmmyy="01-01-90", squad_status="starter",
    )

    assert first == second
    assert first["rating_provenance"]["source"] == "editorial-contextual-transform"
    assert len({tuple(row["visible_skills"].values()) for row in rows}) > 500
    audit = audit_editorial_distribution(rows, book)
    assert audit["status"] == "pass", audit["failures"]
    assert audit["quality"]["elite_85_plus"] > 0
    assert audit["quality"]["poor_52_or_less"] > 0
