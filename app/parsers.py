"""
Unified parsing utilities for Premier Manager 99 data.

This module consolidates various loaders and scanners into a single interface.

It re-exports the key functions from :mod:`app.loaders` and :mod:`app.scanner`
so that callers can import common parsing helpers from one place.  For now this
module is a light wrapper around the existing functions; future work may merge
the underlying implementations to reduce duplication.

Functions exported:

* :func:`decode_entry` – decode length‑prefixed XOR‑encoded records.
* :func:`load_teams` – load team records from the teams FDI file.
* :func:`load_coaches` – load coach records from the coaches FDI file with strict
  validation heuristics.
* :func:`find_player_records` – heuristically scan raw data for embedded
  player records, returning candidate offsets and confidence scores.

"""

from __future__ import annotations

# Re-export lower-level parsing helpers.
from app.loaders import decode_entry, load_teams, load_coaches  # type: ignore[F401]
from app.scanner import find_player_records  # type: ignore[F401]


__all__ = [
    "decode_entry",
    "load_teams",
    "load_coaches",
    "find_player_records",
]
