from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EditorWorkspaceRoute(str, Enum):
    CLUBS = "clubs"
    PLAYERS = "players"
    COACHES = "coaches"
    LEAGUES = "leagues"
    ADVANCED = "advanced"


@dataclass
class SelectionState:
    selected_club_id: int | None = None
    selected_player_offset: int | None = None
    selected_coach_offset: int | None = None
    current_roster_context: list[int] = field(default_factory=list)


@dataclass
class DirtyRecordState:
    dirty_players: set[int] = field(default_factory=set)
    dirty_teams: set[int] = field(default_factory=set)
    dirty_coaches: set[int] = field(default_factory=set)
    field_dirty_map: dict[str, set[str]] = field(default_factory=dict)

    def set_record_fields(self, category: str, key: int, fields: set[str]) -> None:
        record_key = f"{category}:{int(key)}"
        if fields:
            self.field_dirty_map[record_key] = set(fields)
        else:
            self.field_dirty_map.pop(record_key, None)

        target = self._target_set(category)
        if fields:
            target.add(int(key))
        else:
            target.discard(int(key))

    def clear_record(self, category: str, key: int) -> None:
        self.set_record_fields(category, key, set())

    def any_dirty(self) -> bool:
        return bool(self.dirty_players or self.dirty_teams or self.dirty_coaches)

    def _target_set(self, category: str) -> set[int]:
        normalized = str(category or "").strip().lower()
        if normalized == "players":
            return self.dirty_players
        if normalized == "teams":
            return self.dirty_teams
        if normalized == "coaches":
            return self.dirty_coaches
        raise ValueError(f"Unsupported dirty category: {category!r}")


@dataclass
class SearchResultItem:
    result_type: str
    display_label: str
    backing_record_ref: Any
    route_target: EditorWorkspaceRoute
    subtitle: str = ""


@dataclass
class ClubListItemView:
    offset: int
    team_id: int
    club_name: str
    full_club_name: str
    league: str
    country: str
    coach_name: str
    roster_count: int
    is_dirty: bool = False


@dataclass
class RosterRowView:
    slot_number: int
    player_name: str
    player_offset: int | None
    position_label: str
    nationality_label: str
    skills: dict[str, Any] = field(default_factory=dict)
    status_badges: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlayerProfileView:
    offset: int
    full_name: str
    club_name: str
    squad_number: int
    position_label: str
    dirty: bool
    confidence_label: str
    supports_weight_write: bool
    visible_skills: dict[str, int] = field(default_factory=dict)
    additional_fields: list[tuple[str, str, str]] = field(default_factory=list)
    provenance_lines: list[str] = field(default_factory=list)


@dataclass
class CoachProfileView:
    offset: int
    full_name: str
    club_name: str
    team_id_label: str
    dirty: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class ValidationBannerState:
    status: str = "idle"
    message: str = "Validation idle"
