#!/usr/bin/env python3
"""Resolve the palette PM99 actually uses for compact kit indices at runtime."""

from __future__ import annotations

from pathlib import Path
import struct

from app.minifoto_bitmap_archive import parse_riff_palette

# The two earlier DAT palettes differ at slot 111: they contain (10,15,0),
# while the active lineup palette contains (0,0,100). A 256-index runner chart
# on 2026-10-04 identifies this third RIFF resource as the displayed palette.
PALETTE_OFFSET = 0x7F974


def runtime_kit_palette(dbdat: Path) -> tuple[list[tuple[int, int, int]], dict[str, object]]:
    """Return ``DAT.PKF``'s kit palette, never an adjacent simulator palette.

    Compact-kit BMPs use palette indices.  ``SIMULDAT/*.PAL`` is readable but
    not the palette used by the game when it displays those records; using it
    produces candidates whose external preview differs from runtime colours.
    """
    game_root = dbdat.parent
    path = game_root / "DAT.PKF"
    if not path.is_file():
        raise ValueError(f"PM99 runtime DAT.PKF is missing beside DBDAT: {path}")
    data = path.read_bytes()
    if len(data) < PALETTE_OFFSET + 8 or data[PALETTE_OFFSET:PALETTE_OFFSET + 4] != b'RIFF':
        raise ValueError(f'PM99 runtime kit RIFF palette is missing at {PALETTE_OFFSET:#x}: {path}')
    size = struct.unpack_from('<I', data, PALETTE_OFFSET + 4)[0] + 8
    if PALETTE_OFFSET + size > len(data):
        raise ValueError(f'PM99 runtime kit RIFF palette is truncated: {path}')
    palette = parse_riff_palette(data[PALETTE_OFFSET:PALETTE_OFFSET + size])
    if len(palette) != 256:
        raise ValueError(f"PM99 runtime kit palette is incomplete: {path}")
    return palette, {"path": str(path.resolve()), "resource": "DAT.PKF", "offset": PALETTE_OFFSET}
