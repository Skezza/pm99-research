"""Deterministic editorial PM99 ratings for the 2015/16 English 92 build.

This module deliberately has no dependency on FIFA/EA/SoFIFA data.  It turns
the checked-in, reviewable editorial input into the nine native PM99 skills
and the separately proven displayed Handling value.  The input combines
club-level contemporary strength judgements, the certified opening-match
selection, position/body archetypes, and a finite set of hand-authored player
anchors.  A stable name-key variation only separates otherwise identical
editorial cases; it is never presented as a historical fact.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SKILLS = (
    "speed", "stamina", "aggression", "quality", "heading", "dribbling",
    "passing", "shooting", "tackling",
)
VISIBLE_SKILLS = (*SKILLS, "handling")
SCHEMA_VERSION = "pm99-2015-16-english92-editorial-ratings-v1"
_DIVISIONS = ("Premier League", "Championship", "League One", "League Two")
_SQUAD_STATUS_BONUS = {"starter": 5, "bench": 1, "reserve": -5}
_STYLE_ROLE_DEFAULTS = {
    "goalkeeper": [0],
    "shot_stopper": [0],
    "sweeper_keeper": [0],
    "centre_back": [4, 5],
    "ball_playing_centre_back": [4, 5],
    "full_back": [1, 5],
    "attacking_full_back": [2, 4],
    "anchor_midfielder": [14, 9],
    "box_to_box_midfielder": [9, 14],
    "playmaker": [9, 7, 17],
    "wide_midfielder": [6, 11, 15],
    "winger": [10, 13, 16],
    "target_forward": [12, 8],
    "poacher": [12, 8],
    "mobile_forward": [8, 12],
    "complete_forward": [8, 12],
    "inside_forward": [13, 16, 17],
}
_POSITION_STYLE_DEFAULTS = {
    "G": "goalkeeper",
    "D": "centre_back",
    "M": "box_to_box_midfielder",
    "F": "mobile_forward",
}
# Relative to the editorial Quality score.  Height is applied separately to
# aerial players; the profiles avoid making every player at a position alike.
_STYLE_DELTAS = {
    "goalkeeper": {"speed": -22, "stamina": -15, "aggression": -12, "heading": -30, "dribbling": -32, "passing": -9, "shooting": -37, "tackling": -25, "handling": 0},
    "shot_stopper": {"speed": -20, "stamina": -16, "aggression": -10, "heading": -30, "dribbling": -34, "passing": -13, "shooting": -38, "tackling": -26, "handling": 3},
    "sweeper_keeper": {"speed": -14, "stamina": -12, "aggression": -11, "heading": -29, "dribbling": -25, "passing": 1, "shooting": -35, "tackling": -22, "handling": 0},
    "centre_back": {"speed": -8, "stamina": 0, "aggression": 4, "heading": 5, "dribbling": -13, "passing": -5, "shooting": -20, "tackling": 5, "handling": -9},
    "ball_playing_centre_back": {"speed": -6, "stamina": 1, "aggression": 1, "heading": 4, "dribbling": -4, "passing": 6, "shooting": -17, "tackling": 4, "handling": 1},
    "full_back": {"speed": 3, "stamina": 6, "aggression": 1, "heading": -5, "dribbling": -2, "passing": 0, "shooting": -14, "tackling": 4, "handling": -1},
    "attacking_full_back": {"speed": 6, "stamina": 7, "aggression": -1, "heading": -7, "dribbling": 4, "passing": 4, "shooting": -7, "tackling": 1, "handling": 3},
    "anchor_midfielder": {"speed": -3, "stamina": 5, "aggression": 4, "heading": -2, "dribbling": -3, "passing": 3, "shooting": -12, "tackling": 5, "handling": 0},
    "box_to_box_midfielder": {"speed": 2, "stamina": 7, "aggression": 2, "heading": -1, "dribbling": 1, "passing": 3, "shooting": -2, "tackling": 2, "handling": 2},
    "playmaker": {"speed": -1, "stamina": 2, "aggression": -6, "heading": -8, "dribbling": 7, "passing": 10, "shooting": 1, "tackling": -9, "handling": 7},
    "wide_midfielder": {"speed": 5, "stamina": 5, "aggression": -1, "heading": -7, "dribbling": 4, "passing": 3, "shooting": -2, "tackling": -3, "handling": 4},
    "winger": {"speed": 8, "stamina": 3, "aggression": -3, "heading": -10, "dribbling": 8, "passing": 2, "shooting": 2, "tackling": -13, "handling": 8},
    "target_forward": {"speed": -5, "stamina": 1, "aggression": 3, "heading": 10, "dribbling": -6, "passing": -4, "shooting": 7, "tackling": -20, "handling": -3},
    "poacher": {"speed": 4, "stamina": 0, "aggression": 0, "heading": 2, "dribbling": 1, "passing": -7, "shooting": 11, "tackling": -23, "handling": 1},
    "mobile_forward": {"speed": 6, "stamina": 3, "aggression": 1, "heading": 0, "dribbling": 4, "passing": -1, "shooting": 8, "tackling": -20, "handling": 4},
    "complete_forward": {"speed": 4, "stamina": 4, "aggression": 1, "heading": 4, "dribbling": 4, "passing": 3, "shooting": 8, "tackling": -16, "handling": 4},
    "inside_forward": {"speed": 7, "stamina": 2, "aggression": -2, "heading": -5, "dribbling": 8, "passing": 2, "shooting": 6, "tackling": -17, "handling": 8},
}


def _normalise(value: str) -> str:
    value = str(value or "").translate(str.maketrans({"Ł": "L", "ł": "l", "Đ": "D", "đ": "d", "Ø": "O", "ø": "o", "Þ": "Th", "þ": "th", "Æ": "AE", "æ": "ae", "Ð": "D", "ð": "d"}))
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return "".join(char for char in value.casefold() if char.isalnum())


def _clamp(value: int, low: int = 1, high: int = 99) -> int:
    return max(low, min(high, int(value)))


def _identity_key(club: str, player: str) -> str:
    return f"{_normalise(club)}::{_normalise(player)}"


def _stable_variation(club: str, player: str, field: str) -> int:
    """Return a small deterministic separator, not a historical evaluation."""
    digest = hashlib.sha256(f"2015-16-editorial-v1|{_identity_key(club, player)}|{field}".encode("utf-8")).digest()
    return int(digest[0] % 5) - 2


def _age_on_opening_day(birth_date_ddmmyy: str) -> int:
    day, month, year = (int(part) for part in str(birth_date_ddmmyy).split("-"))
    year += 1900 if year >= 20 else 2000
    return 2015 - year - int((month, day) > (8, 8))


class EditorialRatingBook:
    """Validated rating input plus its deterministic transformation."""

    def __init__(self, payload: dict[str, Any], source_path: Path) -> None:
        self.payload = payload
        self.source_path = source_path
        self.schema_version = str(payload.get("schema_version") or "")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unexpected editorial ratings schema: {self.schema_version!r}")
        if str(payload.get("season") or "") != "2015/16":
            raise ValueError("editorial ratings must be pinned to 2015/16")
        if not str(payload.get("provenance") or "").strip():
            raise ValueError("editorial ratings need a provenance statement")
        clubs = dict(payload.get("club_strengths") or {})
        if len(clubs) != 92:
            raise ValueError("editorial ratings need exactly 92 club-strength entries")
        self.club_strengths: dict[str, int] = {}
        for club, value in clubs.items():
            score = int(value)
            if not 42 <= score <= 88:
                raise ValueError(f"editorial club strength is outside 42..88: {club!r}")
            self.club_strengths[_normalise(club)] = score
        if len(self.club_strengths) != len(clubs):
            raise ValueError("editorial club-strength names collide after normalisation")
        self.players: dict[str, dict[str, Any]] = {}
        for row in list(payload.get("player_overrides") or []):
            club = str(row.get("club") or "")
            player = str(row.get("player") or "")
            key = _identity_key(club, player)
            if not club or not player or key in self.players:
                raise ValueError("editorial player overrides need unique club/player identities")
            if _normalise(club) not in self.club_strengths:
                raise ValueError(f"editorial player override has unknown club: {club!r}")
            quality = int(row.get("quality", 0))
            style = str(row.get("style") or "")
            if not 30 <= quality <= 95 or style not in _STYLE_DELTAS:
                raise ValueError(f"invalid editorial player override: {club} / {player}")
            fine_roles = row.get("fine_roles")
            if fine_roles is not None and (
                not isinstance(fine_roles, list)
                or not 1 <= len(fine_roles) <= 6
                or any(not isinstance(role, int) or not 0 <= role <= 17 for role in fine_roles)
            ):
                raise ValueError(f"invalid editorial fine roles: {club} / {player}")
            self.players[key] = {"quality": quality, "style": style, **({"fine_roles": fine_roles} if fine_roles is not None else {})}
        self.source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()

    @property
    def version(self) -> str:
        return str(self.payload.get("version") or "v1")

    def _default_style(self, position: str, height_cm: int) -> str:
        if position == "D":
            return "centre_back" if height_cm >= 184 else "full_back"
        if position == "M":
            return "wide_midfielder" if height_cm <= 173 else "box_to_box_midfielder"
        if position == "F":
            return "target_forward" if height_cm >= 188 else "mobile_forward"
        return _POSITION_STYLE_DEFAULTS[position]

    def validate_player_anchors(self, roster_identities: set[tuple[str, str]]) -> None:
        """Fail if a hand-authored anchor no longer resolves in the source roster."""
        available = {_identity_key(club, player) for club, player in roster_identities}
        missing = sorted(key for key in self.players if key not in available)
        if missing:
            raise ValueError(
                "editorial player anchors do not resolve in the source roster: "
                + ", ".join(missing[:8])
                + (" ..." if len(missing) > 8 else "")
            )

    def rate(
        self,
        *,
        club: str,
        division: str,
        player: str,
        position: str,
        height_cm: int,
        birth_date_ddmmyy: str,
        squad_status: str,
    ) -> dict[str, Any]:
        if division not in _DIVISIONS or position not in _POSITION_STYLE_DEFAULTS:
            raise ValueError(f"unsupported editorial player context: {club} / {player}")
        if squad_status not in _SQUAD_STATUS_BONUS:
            raise ValueError(f"unknown editorial squad status: {squad_status}")
        club_strength = self.club_strengths.get(_normalise(club))
        if club_strength is None:
            raise ValueError(f"editorial ratings have no club strength for {club!r}")
        override = self.players.get(_identity_key(club, player))
        age = _age_on_opening_day(birth_date_ddmmyy)
        age_adjustment = -4 if age <= 19 else (-2 if age <= 21 else (1 if 25 <= age <= 31 else (-2 if age >= 35 else 0)))
        style = str(override["style"]) if override else self._default_style(position, height_cm)
        # Non-anchor players receive a transparent, source-era contextual
        # baseline.  The one-point stable separator avoids a grid of identical
        # generic values without pretending it is an observation.
        quality = int(override["quality"]) if override else _clamp(
            club_strength + _SQUAD_STATUS_BONUS[squad_status] + age_adjustment + _stable_variation(club, player, "quality"),
            32,
            88,
        )
        deltas = _STYLE_DELTAS[style]
        aerial_adjustment = max(-4, min(7, (int(height_cm) - 180) // 3))
        skills: dict[str, int] = {"quality": quality}
        for field in SKILLS:
            if field == "quality":
                continue
            value = quality + int(deltas[field]) + _stable_variation(club, player, field)
            if field == "heading":
                value += aerial_adjustment
            skills[field] = _clamp(value)
        handling = _clamp(quality + int(deltas["handling"]) + _stable_variation(club, player, "handling"))
        if position == "G":
            handling = max(handling, max(35, quality - 12))
        return {
            "skills": {field: int(skills[field]) for field in SKILLS},
            "visible_skills": {**{field: int(skills[field]) for field in SKILLS}, "handling": int(handling)},
            "handling_basis": f"editorial-{self.version}-style-profile",
            "fine_roles": list((override or {}).get("fine_roles") or _STYLE_ROLE_DEFAULTS[style]),
            "rating_provenance": {
                "model_schema": self.schema_version,
                "model_version": self.version,
                "input_sha256": self.source_sha256,
                "club_strength": club_strength,
                "squad_status": squad_status,
                "age_on_2015_08_08": age,
                "age_adjustment": age_adjustment,
                "style": style,
                "source": "hand-authored-player-anchor" if override else "editorial-contextual-transform",
                "stable_separator": _stable_variation(club, player, "quality") if not override else 0,
            },
        }


def load_editorial_rating_book(path: Path) -> EditorialRatingBook:
    return EditorialRatingBook(json.loads(path.read_text(encoding="utf-8")), path)


def audit_editorial_distribution(rows: list[dict[str, Any]], book: EditorialRatingBook) -> dict[str, Any]:
    """Audit differentiation and tier separation without claiming historic truth."""
    if not rows:
        raise ValueError("cannot audit an empty editorial player list")
    divisions: dict[str, list[int]] = defaultdict(list)
    styles: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    quality_values: list[int] = []
    for row in rows:
        quality = int(dict(row["skills"])["quality"])
        quality_values.append(quality)
        divisions[str(row["division"])].append(quality)
        provenance = dict(row.get("rating_provenance") or {})
        styles[str(provenance.get("style") or "unknown")] += 1
        statuses[str(provenance.get("squad_status") or "unknown")] += 1
    quality_values.sort()
    division_summary = {
        division: {
            "players": len(values),
            "minimum": min(values),
            "maximum": max(values),
            "mean": round(sum(values) / len(values), 2),
        }
        for division, values in sorted(divisions.items())
    }
    failures: list[str] = []
    if len(rows) < 2_000:
        failures.append("expected a complete English-92 player population")
    if quality_values[0] > 45 or quality_values[-1] < 86 or quality_values[-1] - quality_values[0] < 42:
        failures.append("editorial quality range does not distinguish poor and elite players")
    if len(set(quality_values)) < 35:
        failures.append("editorial quality distribution is too compressed")
    if set(division_summary) != set(_DIVISIONS):
        failures.append("editorial audit is missing an English division")
    elif not (
        division_summary["Premier League"]["mean"] > division_summary["Championship"]["mean"] > division_summary["League One"]["mean"] > division_summary["League Two"]["mean"]
    ):
        failures.append("editorial division means do not preserve the intended strength order")
    return {
        "schema_version": "pm99-2015-16-editorial-rating-audit-v1",
        "status": "pass" if not failures else "fail",
        "input": {"schema_version": book.schema_version, "version": book.version, "sha256": book.source_sha256, "path": str(book.source_path)},
        "players": len(rows),
        "quality": {
            "minimum": quality_values[0],
            "maximum": quality_values[-1],
            "mean": round(sum(quality_values) / len(quality_values), 2),
            "distinct_values": len(set(quality_values)),
            "elite_85_plus": sum(value >= 85 for value in quality_values),
            "poor_52_or_less": sum(value <= 52 for value in quality_values),
        },
        "divisions": division_summary,
        "styles": dict(sorted(styles.items())),
        "squad_statuses": dict(sorted(statuses.items())),
        "failures": failures,
    }
