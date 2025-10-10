"""Utilities for exporting data tables to clipboard-friendly text."""
from __future__ import annotations

from typing import Iterable, Sequence, Tuple, List, Optional, Mapping, Any

Table = Sequence[Sequence[Any]]


def _stringify(value: Any) -> str:
    """Convert arbitrary values to strings suitable for table output."""

    if value is None:
        return ""
    return str(value)


def format_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """Format ``rows`` into a human-readable table string."""

    normalized_rows: List[Tuple[str, ...]] = []
    widths = [len(h) for h in headers]

    for row in rows:
        normalized = tuple(_stringify(cell) for cell in row)
        normalized_rows.append(normalized)
        for idx, cell in enumerate(normalized):
            if idx < len(widths):
                widths[idx] = max(widths[idx], len(cell))
            else:
                widths.append(len(cell))

    header_line = " | ".join(f"{headers[idx]:<{widths[idx]}}" for idx in range(len(headers)))
    separator = "-+-".join("-" * widths[idx] for idx in range(len(headers)))

    lines = [header_line, separator]

    for row in normalized_rows:
        padded = [
            f"{row[idx]:<{widths[idx]}}" if idx < len(row) else "".ljust(widths[idx])
            for idx in range(len(headers))
        ]
        lines.append(" | ".join(padded))

    return "\n".join(lines)


def build_player_rows(
    records: Iterable[Tuple[int, Any]],
    team_lookup: Optional[Mapping[int, str]] = None,
) -> Tuple[Sequence[str], List[Tuple[str, ...]]]:
    """Return headers and rows for the player export table."""

    headers = ("Offset", "Name", "Team", "Squad #", "Position")
    rows: List[Tuple[str, ...]] = []

    for offset, record in records:
        name = getattr(record, "name", None) or " ".join(
            part for part in [getattr(record, "given_name", ""), getattr(record, "surname", "")]
            if part
        ).strip()

        try:
            team_id = getattr(record, "team_id", None)
        except Exception:
            team_id = None

        team_bits = []
        if team_id not in (None, ""):
            team_bits.append(str(team_id))
            if team_lookup:
                team_name = team_lookup.get(int(team_id), "")
                if team_name:
                    team_bits.append(team_name)
        team_display = " - ".join(team_bits)

        squad = getattr(record, "squad_number", "")
        try:
            position = record.get_position_name()
        except Exception:
            position = getattr(record, "position", "")

        rows.append(
            (
                f"0x{offset:08X}",
                name.strip(),
                team_display,
                _stringify(squad),
                _stringify(position),
            )
        )

    return headers, rows


def build_coach_rows(records: Iterable[Tuple[int, Any]]) -> Tuple[Sequence[str], List[Tuple[str, ...]]]:
    """Return headers and rows for the coach export table."""

    headers = ("Offset", "Name")
    rows: List[Tuple[str, ...]] = []

    for offset, coach in records:
        name = getattr(coach, "full_name", None) or str(coach)
        if not name:
            name = "Unknown Coach"
        rows.append((f"0x{offset:08X}", name))

    return headers, rows


def build_team_rows(records: Iterable[Tuple[int, Any]]) -> Tuple[Sequence[str], List[Tuple[str, ...]]]:
    """Return headers and rows for the team export table."""

    headers = ("Offset", "Team ID", "Name", "League")
    rows: List[Tuple[str, ...]] = []

    for offset, team in records:
        team_id = getattr(team, "team_id", "")
        name = getattr(team, "name", "Unknown Team") or "Unknown Team"
        league = getattr(team, "league", "")
        rows.append((f"0x{offset:08X}", _stringify(team_id), name, _stringify(league)))

    return headers, rows


def build_table_text(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """Helper that combines ``build_*_rows`` with :func:`format_table`."""

    return format_table(headers, rows)


def generate_player_table_text(
    records: Iterable[Tuple[int, Any]],
    team_lookup: Optional[Mapping[int, str]] = None,
) -> str:
    headers, rows = build_player_rows(records, team_lookup=team_lookup)
    return build_table_text(headers, rows)


def generate_coach_table_text(records: Iterable[Tuple[int, Any]]) -> str:
    headers, rows = build_coach_rows(records)
    return build_table_text(headers, rows)


def generate_team_table_text(records: Iterable[Tuple[int, Any]]) -> str:
    headers, rows = build_team_rows(records)
    return build_table_text(headers, rows)
