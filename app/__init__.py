"""PM99RE application package.

This package contains the core modules for the Premier Manager 99 database editor.
It is intentionally small at import time to avoid side effects; modules should be
imported explicitly (e.g. ``from app import xor`` or ``from app.models import PlayerRecord``).

The package now exposes a :mod:`app.parsers` submodule which consolidates
commonly used parsing helpers (``decode_entry``, ``load_teams``,
``load_coaches`` and ``find_player_records``).  Consumers can import these
functions directly from ``app.parsers`` for convenience.
"""

__version__ = "0.1.0"
__author__ = "PM99 Reverse Engineering Team"

# Export the unified parsers submodule for convenience.
from . import parsers
