"""Utilities for exporting data tables to clipboard-friendly text."""
from __future__ import annotations

from typing import Iterable, Sequence, Tuple, List, Optional, Mapping, Any, Dict

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


def build_player_detail_rows(
    records: Iterable[Tuple[int, Any]],
    team_lookup: Optional[Mapping[int, str]] = None,
) -> Tuple[Sequence[str], List[Tuple[str, ...]]]:
    """Return headers and rows for the detailed player export table."""

    headers = (
        "Offset",
        "Name",
        "Team ID",
        "Team",
        "Squad #",
        "Position",
        "EN",
        "SP",
        "ST",
        "AG",
        "QU",
        "FI",
        "MO",
        "Attr8",
        "Attr9",
        "Attr10",
        "Attr11",
        "Attr12",
        "Average",
    )
    rows: List[Tuple[str, ...]] = []

    for offset, record in records:
        name = getattr(record, "name", None) or " ".join(
            part for part in [getattr(record, "given_name", ""), getattr(record, "surname", "")]
            if part
        ).strip()

        team_id = getattr(record, "team_id", "")
        team_name = ""
        try:
            if team_lookup and team_id not in (None, ""):
                team_name = team_lookup.get(int(team_id), "") or ""
        except Exception:
            team_name = ""

        squad = getattr(record, "squad_number", "")
        try:
            position = record.get_position_name()
        except Exception:
            position = getattr(record, "position", "")

        attrs = list(getattr(record, "attributes", []) or [])
        if len(attrs) < 12:
            attrs.extend([""] * (12 - len(attrs)))

        en = _stringify(attrs[0]) if len(attrs) > 0 else ""
        sp = _stringify(attrs[1]) if len(attrs) > 1 else ""
        st = _stringify(attrs[2]) if len(attrs) > 2 else ""
        ag = _stringify(attrs[3]) if len(attrs) > 3 else ""
        qu = _stringify(attrs[4]) if len(attrs) > 4 else ""
        fi = _stringify(attrs[5]) if len(attrs) > 5 else ""
        mo = _stringify(attrs[6]) if len(attrs) > 6 else ""
        attr8 = _stringify(attrs[7]) if len(attrs) > 7 else ""
        attr9 = _stringify(attrs[8]) if len(attrs) > 8 else ""
        attr10 = _stringify(attrs[9]) if len(attrs) > 9 else ""
        attr11 = _stringify(attrs[10]) if len(attrs) > 10 else ""
        attr12 = _stringify(attrs[11]) if len(attrs) > 11 else ""

        numeric_attrs: List[int] = []
        for raw_attr in attrs[:10]:
            if raw_attr in (None, ""):
                continue
            if isinstance(raw_attr, (int, float)):
                try:
                    numeric_attrs.append(int(raw_attr))
                except Exception:
                    continue
                continue

            text_value = str(raw_attr).strip()
            if text_value.isdigit():
                try:
                    numeric_attrs.append(int(text_value))
                except Exception:
                    continue

        average = sum(numeric_attrs) // len(numeric_attrs) if numeric_attrs else ""

        rows.append(
            (
                f"0x{offset:08X}",
                name.strip(),
                _stringify(team_id),
                team_name,
                _stringify(squad),
                _stringify(position),
                en,
                sp,
                st,
                ag,
                qu,
                fi,
                mo,
                attr8,
                attr9,
                attr10,
                attr11,
                attr12,
                _stringify(average),
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

    headers = (
        "Offset",
        "Team ID",
        "Name",
        "League",
        "Stadium",
        "Capacity",
        "Car Park",
        "Pitch",
    )
    rows: List[Tuple[str, ...]] = []

    for offset, team in records:
        team_id = getattr(team, "team_id", "")
        name = getattr(team, "name", "Unknown Team") or "Unknown Team"
        league = getattr(team, "league", "")
        stadium = getattr(team, "stadium", "")
        capacity = getattr(team, "stadium_capacity", "")
        car_park = getattr(team, "car_park", "")
        pitch = getattr(team, "pitch", "")

        rows.append(
            (
                f"0x{offset:08X}",
                _stringify(team_id),
                name,
                _stringify(league),
                _stringify(stadium),
                _stringify(capacity),
                _stringify(car_park),
                _stringify(pitch),
            )
        )

    return headers, rows


def build_table_text(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """Helper that combines ``build_*_rows`` with :func:`format_table`."""

    return format_table(headers, rows)


def generate_player_table_text(
    records: Iterable[Tuple[int, Any]],
    team_lookup: Optional[Mapping[int, str]] = None,
    *,
    level: str = "summary",
) -> str:
    if level == "detailed":
        headers, rows = build_player_detail_rows(records, team_lookup=team_lookup)
    else:
        headers, rows = build_player_rows(records, team_lookup=team_lookup)
    return build_table_text(headers, rows)


def generate_coach_table_text(
    records: Iterable[Tuple[int, Any]],
    *,
    level: str = "summary",
) -> str:
    # Currently summary and detailed exports are identical for coaches, but the parameter
    # is accepted for a consistent API surface.
    headers, rows = build_coach_rows(records)
    return build_table_text(headers, rows)


def _group_players_by_team(
    player_records: Iterable[Tuple[int, Any]]
) -> Dict[int, List[Tuple[int, Any]]]:
    grouped: Dict[int, List[Tuple[int, Any]]] = {}
    for offset, record in player_records:
        team_id = getattr(record, "team_id", None)
        if team_id in (None, ""):
            continue
        try:
            key = int(team_id)
        except Exception:
            continue
        grouped.setdefault(key, []).append((offset, record))
    return grouped


def generate_team_table_text(
    records: Iterable[Tuple[int, Any]],
    *,
    level: str = "summary",
    player_records: Optional[Iterable[Tuple[int, Any]]] = None,
    team_lookup: Optional[Mapping[int, str]] = None,
) -> str:
    headers, rows = build_team_rows(records)
    base_table = build_table_text(headers, rows)

    if level != "detailed":
        return base_table

    players_by_team: Dict[int, List[Tuple[int, Any]]] = {}
    if player_records is not None:
        players_by_team = _group_players_by_team(player_records)

    sections: List[str] = [base_table, ""]

    for offset, team in records:
        team_id = getattr(team, "team_id", None)
        team_name = getattr(team, "name", "Unknown Team") or "Unknown Team"
        sections.append(f"Team {team_name} (ID {team_id})")
        team_players = []
        try:
            if team_id is not None and players_by_team:
                team_players = players_by_team.get(int(team_id), [])
        except Exception:
            team_players = []

        if not team_players:
            sections.append("  No players associated with this team.")
            sections.append("")
            continue

        player_headers, player_rows = build_player_detail_rows(
            team_players,
            team_lookup=team_lookup,
        )
        sections.append(format_table(player_headers, player_rows))
        sections.append("")

    return "\n".join(section for section in sections).strip()
