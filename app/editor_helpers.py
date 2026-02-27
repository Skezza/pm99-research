"""Utility helpers shared between CLI, GUI, and editor actions."""
import re
from typing import List, Tuple

from app.models import TeamRecord
from app.xor import decode_entry


def _normalize_text(value: str) -> str:
    """Normalize text for comparison (case-fold + collapse whitespace)."""
    if not value:
        return ""
    return " ".join(value.strip().split()).lower()


def _normalize_lookup_key(value: str) -> str:
    """Normalize text for loose lookup by stripping punctuation to spaces."""
    normalized = _normalize_text(value)
    if not normalized:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


_TEAM_QUERY_ALIAS_MAP = {
    "ac milan": ["milan"],
    "inter milan": ["inter"],
    "internazionale milan": ["inter"],
    "internazionale milano": ["inter"],
    "fc barcelona": ["f c barcelona", "barcelona"],
    "barcelona": ["f c barcelona"],
    "real madrid": ["real madrid c f"],
    "real madrid cf": ["real madrid c f"],
    "atletico madrid": ["c at madrid"],
    "atl madrid": ["c at madrid"],
    "manchester united": ["manchester utd"],
    "man utd": ["manchester utd"],
    "manchester city": ["manchester c"],
    "stoke city": ["stoke c"],
}


def _team_query_variants(query: str) -> List[str]:
    """
    Return exact-match variants for user-facing team queries.

    This keeps parser-backed team matching forgiving for common natural names
    without expanding broad substring matching to ambiguous aliases.
    """
    normalized = _normalize_lookup_key(query)
    if not normalized:
        return []
    variants = [normalized]
    for alias in _TEAM_QUERY_ALIAS_MAP.get(normalized, []):
        alias_norm = _normalize_lookup_key(alias)
        if alias_norm and alias_norm not in variants:
            variants.append(alias_norm)
    common_prefixes = {"ac", "as", "fc", "cf"}
    parts = normalized.split()
    if len(parts) >= 2 and parts[0] in common_prefixes:
        stripped = " ".join(parts[1:])
        if stripped and stripped not in variants:
            variants.append(stripped)
    return variants


def team_query_matches(query: str, *, team_name: str, full_club_name: str = "") -> bool:
    """
    Match a user-facing team query against parsed team text with canonical aliases.

    Exact alias variants are checked first against normalized name/full-club-name.
    If none match exactly, the original normalized query is used as a substring
    against the combined normalized team text.
    """
    normalized_query = _normalize_lookup_key(query)
    if not normalized_query:
        return False
    name_norm = _normalize_lookup_key(team_name)
    full_norm = _normalize_lookup_key(full_club_name)
    exact_fields = {v for v in (name_norm, full_norm) if v}
    if any(variant in exact_fields for variant in _team_query_variants(query)):
        return True
    search_text = " ".join(v for v in (name_norm, full_norm) if v)
    return bool(search_text and normalized_query in search_text)


def _player_display_name(record) -> str:
    """Return the best available display name for a player record."""
    name = getattr(record, "name", "") or ""
    if not name:
        given = getattr(record, "given_name", "") or ""
        surname = getattr(record, "surname", "") or ""
        name = " ".join(part for part in (given, surname) if part).strip()
    return " ".join(name.split())


def _team_display_name(team: TeamRecord) -> str:
    """Return the cleaned team name or an empty string."""
    return " ".join((team.name or "").strip().split())


def _coach_display_name(coach) -> str:
    """Return the best available display name for a coach record."""
    name = getattr(coach, "full_name", "") or getattr(coach, "name", "") or ""
    if not name:
        given = getattr(coach, "given_name", "") or ""
        surname = getattr(coach, "surname", "") or ""
        name = " ".join(part for part in (given, surname) if part).strip()
    return " ".join(name.split())


def scan_team_matches(data: bytes, match_team: str | None = None,
                      match_stadium: str | None = None,
                      max_sections: int = 5000) -> Tuple[List[Tuple[int, TeamRecord]], int]:
    """Scan sequential sections of the team file for matching records."""
    matches = []
    offset = 0x400
    scanned = 0
    data_len = len(data)

    while offset + 2 <= data_len and scanned < max_sections:
        try:
            decoded, length = decode_entry(data, offset)
        except Exception:
            offset += 1
            continue

        scanned += 1

        if length <= 0 or length > 0x7000 or offset + 2 + length > data_len:
            offset += 1
            continue

        try:
            team = TeamRecord(decoded, offset)
        except Exception:
            offset += length + 2
            continue

        name_norm = _normalize_text(team.name or "")
        stadium_norm = _normalize_text((team.stadium or "").strip())

        matched = False
        if match_team and match_team in name_norm:
            matched = True
        if match_stadium and match_stadium in stadium_norm:
            matched = True

        if matched:
            matches.append((offset, team))

        offset += length + 2

    return matches, scanned


def find_entries_with_substring(data: bytes, substring: str, max_matches: int = 8) -> List[Tuple[int, bytes]]:
    """Return entry offsets whose decoded payload contains the substring."""
    if not substring:
        return []
    needle = substring.encode("latin-1", errors="ignore").lower()
    matches = []
    offset = 0x400
    data_len = len(data)

    while offset + 2 <= data_len and len(matches) < max_matches:
        try:
            decoded, length = decode_entry(data, offset)
        except Exception:
            offset += 1
            continue

        if length <= 0 or offset + 2 + length > data_len:
            offset += 1
            continue

        if needle in decoded.lower():
            matches.append((offset, decoded))

        offset += length + 2

    return matches


__all__ = [
    "_normalize_text",
    "_normalize_lookup_key",
    "_player_display_name",
    "_team_display_name",
    "_team_query_variants",
    "_coach_display_name",
    "team_query_matches",
    "scan_team_matches",
    "find_entries_with_substring",
]
