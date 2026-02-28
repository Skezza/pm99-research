"""
Legacy player data models for Premier Manager 99.

This module was part of early reverse‑engineering efforts and contains only
placeholder implementations for player data structures.  It has been
superseded by :mod:`app.models`, which provides fully featured parsing for
``TeamRecord``, ``CoachRecord`` and ``PlayerRecord``.  The functions
defined here return dummy data and should not be used in new code.

Importing this module will emit a deprecation warning.  Please migrate to
``app.models.PlayerRecord`` and the helpers available in :mod:`app.parsers`.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import List, Optional, Tuple


warnings.warn(
    "app.player_models is deprecated; use app.models.PlayerRecord and helpers from app.parsers instead",
    DeprecationWarning,
    stacklevel=2,
)


@dataclass
class Player:
    """Represents a player record in the database (legacy placeholder)."""
    full_name: str
    section_offset: int
    name_offset: int
    attributes: Optional[List[int]] = None
    metadata: Optional[dict] = None

    def __post_init__(self) -> None:
        if self.attributes is None:
            self.attributes = []
        if self.metadata is None:
            self.metadata = {}

    def __repr__(self) -> str:
        return f"Player(name={self.full_name}, section=0x{self.section_offset:08x}, offset={self.name_offset})"


@dataclass
class PlayerRecord:
    """Complete player record with all fields (legacy placeholder)."""
    team_id: int
    squad_number: int
    name: str
    position: int
    attributes: List[int]
    metadata: dict
    raw_data: bytes
    offset: int

    def __repr__(self) -> str:
        return f"PlayerRecord(name={self.name}, team={self.team_id}, pos={self.position})"



def parse_player(data: bytes, offset: int) -> PlayerRecord:
    """Parse a player record from raw bytes (returns placeholder data)."""
    # This function returns a dummy PlayerRecord.  Real parsing is implemented in app.models.
    return PlayerRecord(
        team_id=0,
        squad_number=0,
        name="Unknown",
        position=0,
        attributes=[50] * 12,
        metadata={},
        raw_data=data,
        offset=offset,
    )



def parse_all_players(file_data: bytes) -> List[PlayerRecord]:
    """Parse all player records from a file (returns placeholder data)."""
    # Return a single dummy player.  Real parsing is implemented in app.models.
    return [
        PlayerRecord(
            team_id=0,
            squad_number=0,
            name="Placeholder",
            position=0,
            attributes=[50] * 12,
            metadata={},
            raw_data=b"",
            offset=0,
        )
    ]
