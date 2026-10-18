#!/usr/bin/env python3
"""Compile a reproducible 2015/16 English PM99 database candidate.

This is deliberately a release compiler, not an editor shortcut.  It starts
from a disposable copy of a known-working PM99 installation and produces a
complete four-division English replacement using only the released JUG, EQ
and ENT write lanes:

* variable-length player and manager names;
* player biography, editorial PM99 skills and broad position, plus six saved
  fine-role slots where the runtime-proven dd6361 carrier family supports
  them;
* carrier club strings, capacity and mode-zero opening finance;
* one source-pinned 24/25-player roster, dated manager and first-match order
  per club;
* either the experimental 92-record source shape or the native, selector-mapped
  80-club Core80 shape (no guessed competition rewrite).

The 2015/16 FootballSquads capture supplies the factual club/player layer.
The checked-in editorial ratings input is the sole authority for all PM99
skills.  Optional FIFA archives remain only for stable portrait-identification
metadata and safe roster-candidate ordering; their numerical attributes are
never read into the rating transform.

Portrait and kit assets are intentionally *not* manufactured here.  They need
their own attribution/asset gate, and the resulting ``portrait-plan.json``
lists every player requiring an approved source image.  This keeps the binary
writer honest: a face must never silently become an unrelated 1999 player.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import struct
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
if str(EDITOR) not in sys.path:
    sys.path.insert(0, str(EDITOR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.editor_actions import (  # noqa: E402
    _apply_player_mutations,
    _patch_indexed_dd6361_variable_name,
    _patch_indexed_player_variable_name_payload,
)
from app.eq_jug_linked import parse_eq_external_team_roster_payload  # noqa: E402
from app.eq_team_indexed_metadata import (  # noqa: E402
    extract_indexed_team_payload_metadata,
    patch_indexed_team_mode0_starting_finance,
    patch_indexed_team_seated_capacity,
)
from app.eq_team_manager_links import patch_indexed_eq_active_manager_id  # noqa: E402
from app.eq_initial_tactics import patch_initial_tactics  # noqa: E402
from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from app.models import PlayerRecord  # noqa: E402
from app.xor import xor_decode, xor_encode  # noqa: E402
from scripts.english92_editorial_ratings import (  # noqa: E402
    EditorialRatingBook,
    audit_editorial_distribution,
    load_editorial_rating_book,
)


SKILLS = (
    "speed", "stamina", "aggression", "quality", "heading", "dribbling",
    "passing", "shooting", "tackling",
)
VISIBLE_SKILLS = (
    "speed", "stamina", "aggression", "quality", "heading", "dribbling",
    "passing", "shooting", "tackling", "handling",
)
POSITION = {"G": 0, "D": 1, "M": 2, "F": 3}
DIVISION_FINANCE = {
    "Premier League": 20_000_000,
    "Championship": 8_000_000,
    "League One": 2_500_000,
    "League Two": 1_000_000,
}
NATIVE_ENGLISH92_HIDDEN_CARRIER_IDS = (321, 328, 332, 365, 335, 350, 355, 366, 324, 359, 371, 3306)
NATIVE_ENGLISH92_CARRIER_IDS = frozenset(
    {
        # The eighty picker carriers are deliberately interleaved in EQ.
        309, 308, 301, 333, 312, 316, 319, 302, 306, 320, 305, 303, 313, 307, 304, 315, 317, 310, 311, 314,
        331, 325, 322, 348, 351, 353, 326, 327, 329, 334, 339, 336, 337, 340, 363, 318, 330, 342, 343, 344,
        345, 346, 349, 352, 375, 379, 354, 384, 3311, 323, 356, 386, 357, 360, 338, 341, 364, 392, 367, 368,
        369, 347, 370, 372, 373, 374, 376, 378, 380, 382, 383, 385, 358, 387, 361, 388, 389, 362, 390, 391,
        *NATIVE_ENGLISH92_HIDDEN_CARRIER_IDS,
    }
)
# FootballSquads and optional portrait metadata use a few different club
# spellings. The normaliser still has to match the player name, so this only
# breaks ties; it has no bearing on editorial skills.
CLUB_ALIASES = {
    "afcwimbledon": "afcwimbledon",
    "miltonkeynesdons": "mkdons",
    "queensparkrangers": "qpr",
    "westbromwichalbion": "westbrom",
    "wolverhamptonwanderers": "wolves",
    "brightonhovealbion": "brighton",
    "nottinghamforest": "nottinghamforest",
    "sheffieldwednesday": "sheffwed",
    "sheffieldunited": "sheffutd",
    "bristolrovers": "bristolrovers",
    "bristolcity": "bristolcity",
}


def _normalise(value: str) -> str:
    text = str(value or "").translate(str.maketrans({"Ł": "L", "ł": "l", "Đ": "D", "đ": "d", "Ø": "O", "ø": "o", "Þ": "Th", "þ": "th", "Æ": "AE", "æ": "ae", "Ð": "D", "ð": "d"}))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "".join(char for char in text.casefold() if char.isalnum())


def _pm99_text(value: str) -> str:
    """Return a readable CP1252 spelling without silently replacing bytes.

    PM99 cannot store several central/eastern-European diacritics.  Keep
    supported CP1252 letters (for example é and ñ), but transliterate the
    unsupported ones at the final storage boundary and retain the source
    spelling separately in the release ledger.
    """
    substitutions = str.maketrans({"Ł": "L", "ł": "l", "Đ": "D", "đ": "d", "Ø": "O", "ø": "o", "Þ": "Th", "þ": "th", "Æ": "AE", "æ": "ae", "Ð": "D", "ð": "d"})
    text = unicodedata.normalize("NFKD", str(value or "").translate(substitutions))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = " ".join(text.split())
    try:
        text.encode("cp1252")
    except UnicodeEncodeError as exc:
        raise ValueError(f"PM99 cannot store {value!r} after transliteration") from exc
    return text


def _club_key(value: str) -> str:
    raw = _normalise(value)
    return CLUB_ALIASES.get(raw, raw.replace("footballclub", "").replace("fc", ""))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_dump(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _read_u16_xor(payload: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(payload):
        raise ValueError("truncated inner string length")
    return (payload[offset] ^ 0x61) | ((payload[offset + 1] ^ 0x61) << 8)


def _write_u16_xor(value: int) -> bytes:
    if not 0 <= value <= 0xFFFF:
        raise ValueError("inner string length outside u16")
    return bytes(((value & 0xFF) ^ 0x61, ((value >> 8) & 0xFF) ^ 0x61))


def _read_inner_string(payload: bytes, offset: int) -> tuple[str, int, int]:
    size = _read_u16_xor(payload, offset)
    start = offset + 2
    end = start + size
    if size < 1 or end > len(payload):
        raise ValueError("invalid inner string")
    return payload[start:end].decode("cp1252"), start, end


def _find_dd6361_name_end(payload: bytes) -> int:
    if payload[2:5] != b"\xdd\x63\x61":
        raise ValueError("opening selection requires dd6361")
    for first in range(5, min(24, len(payload))):
        try:
            surname_len = _read_u16_xor(payload, first)
            surname_end = first + 2 + surname_len
            # Native names are bounded strings. Without this bound, a short
            # name can be skipped and arbitrary biography text thousands of
            # bytes later can accidentally satisfy the metadata checks.
            if not 1 <= surname_len <= 255 or surname_end + 2 > len(payload):
                continue
            full_len = _read_u16_xor(payload, surname_end)
            full_end = surname_end + 2 + full_len
            if not 1 <= full_len <= 255 or full_end + 18 > len(payload):
                continue
            # Same conservative structural check as the browser writer.
            position = payload[full_end + 11] ^ 0x61
            day = payload[full_end + 12] ^ 0x61
            month = payload[full_end + 13] ^ 0x61
            if position <= 7 and 1 <= day <= 31 and 1 <= month <= 12:
                return full_end
        except ValueError:
            pass
    raise ValueError("could not resolve dd6361 variable name anchor")


def _set_dd6361_roles_and_startup(
    payload: bytes,
    *,
    roles: list[int],
    shirt_number: int,
    initial_order: int,
    name_end: int | None = None,
) -> bytes:
    if not roles or len(roles) > 6 or any(role < 0 or role > 17 for role in roles):
        raise ValueError("fine roles must contain one to six PM99 roles")
    if not 1 <= shirt_number <= 99 or not 1 <= initial_order <= 255:
        raise ValueError("invalid shirt number or opening order")
    # Resolve the anchor before any generic fixed-field serializer runs.  A
    # few genuine dd6361 records contain byte patterns which can look like a
    # second valid variable-name prefix after unrelated field mutations; the
    # original suffix anchor is the only safe one for a writer.
    if name_end is None:
        name_end = _find_dd6361_name_end(payload)
    if name_end < 7 or name_end + 8 > len(payload):
        raise ValueError("dd6361 name anchor does not leave a role/startup window")
    result = bytearray(payload)
    # dd6361 stores six individually XOR-obfuscated role codes two bytes after
    # its variable full-name field.  Empty slots are a decoded zero.
    for slot in range(6):
        value = roles[slot] + 1 if slot < len(roles) else 0
        result[name_end + 2 + slot] = value ^ 0x61
    result[7] = shirt_number ^ 0x61
    result[name_end] = initial_order ^ 0x61
    return bytes(result)


def _set_dd6360_primary_role(payload: bytes, *, role: int) -> bytes:
    """Set one compact tactical-role candidate without touching controls.

    This legacy English builder no longer allocates compact foreign carriers,
    but keeping its dormant helper correct matters: the first role byte is
    after the compact control byte, and the other five candidates must become
    native unassigned values rather than repeated data in opaque fields.
    """
    if payload[2:5] != b"\xdd\x63\x60" or not 0 <= role <= 17:
        raise ValueError("dd6360 primary-role write requires a valid native player payload")
    role_start = _native_dd6360_role_start(payload)
    if role_start < 8 or role_start + 8 > len(payload):
        raise ValueError("dd6360 primary role block overruns payload")
    result = bytearray(payload)
    for slot in range(6):
        stored = int(role) + 1 if slot == 0 else 0
        result[role_start + 2 + slot] = stored ^ 0x61
    return bytes(result)


def _set_dd6360_native_player_fields(
    payload: bytes,
    *,
    role: int,
    position: int,
    nationality: int,
    birth_day: int,
    birth_month: int,
    birth_year: int,
    height: int,
    weight: int,
    skills: dict[str, int],
    native_role_start: int,
) -> bytes:
    """Patch the proven native dd6360 semantic block without serialising it.

    dd6360 is *not* the ordinary PlayerRecord layout: decoded bytes 2..4 are
    its ``dd6360`` signature, not the generic model's squad-number byte.  A
    generic ``PlayerRecord.to_bytes()`` therefore damages a live record even
    when every displayed field has parsed correctly.  The native name writer
    gives us the post-rewrite role-block offset; all the fields below are the
    contiguous MANAGPRE native block following that anchor.  Keep the header,
    unknown bytes and the linked-roster ownership untouched.
    """
    if payload[2:5] != b"\xdd\x63\x60":
        raise ValueError("native dd6360 field patch requires a dd6360 payload")
    if not 0 <= role <= 17 or not 0 <= position <= 3:
        raise ValueError("invalid dd6360 role or broad position")
    if not 1 <= birth_day <= 31 or not 1 <= birth_month <= 12 or not 1900 <= birth_year <= 2100:
        raise ValueError("invalid dd6360 date of birth")
    if not 50 <= height <= 250 or not 40 <= weight <= 140:
        raise ValueError("invalid dd6360 height or weight")
    if native_role_start < 8 or native_role_start + 28 > len(payload):
        raise ValueError("dd6360 native semantic block overruns payload")

    result = bytearray(payload)

    def write_xor(offset: int, value: int) -> None:
        if not 0 <= value <= 255:
            raise ValueError(f"dd6360 byte outside range at {offset}: {value}")
        result[offset] = value ^ 0x61

    # Compact roles occupy the six-byte candidate window after the first
    # control byte.  This legacy builder only receives one role, so declare
    # that one candidate and explicitly mark the remaining five unassigned;
    # never overwrite either surrounding control byte.
    for slot in range(6):
        stored = role + 1 if slot == 0 else 0
        result[native_role_start + 2 + slot] = stored ^ 0x61
    write_xor(native_role_start + 8, nationality)
    write_xor(native_role_start + 10, position)
    write_xor(native_role_start + 11, position)
    write_xor(native_role_start + 12, birth_day)
    write_xor(native_role_start + 13, birth_month)
    write_xor(native_role_start + 14, birth_year & 0xFF)
    write_xor(native_role_start + 15, birth_year >> 8)
    write_xor(native_role_start + 16, height)
    write_xor(native_role_start + 17, weight)
    for index, skill in enumerate(SKILLS):
        value = int(skills[skill])
        if not 0 <= value <= 100:
            raise ValueError(f"invalid dd6360 {skill}: {value}")
        write_xor(native_role_start + 18 + index, value)
    if "handling" in skills:
        handling = int(skills["handling"])
        if not 0 <= handling <= 100:
            raise ValueError(f"invalid dd6360 handling: {handling}")
        # Compact dd6360 keeps its tenth displayed stat just after the nine
        # generic attributes.  MANAGPRE's native loader copies it to player+0xd3
        # and the profile labels it HANDLING.
        write_xor(native_role_start + 27, handling)
    return bytes(result)


def _rewrite_eq_strings(payload: bytes, *, short_name: str, stadium_name: str, full_name: str) -> bytes:
    marker = payload.find(b"\xdd\x63\x61", 2, 64)
    if marker < 2:
        raise ValueError("released EQ string marker missing")
    total_offset = marker - 2
    old_total = _read_u16_xor(payload, total_offset)
    cursor = marker + 4
    _short, short_start, short_end = _read_inner_string(payload, cursor)
    _stadium, stadium_start, stadium_end = _read_inner_string(payload, short_end)
    bridge_start = stadium_end
    bridge_end = bridge_start + 2
    if bridge_end > len(payload):
        raise ValueError("EQ string bridge is truncated")
    _full, full_start, full_end = _read_inner_string(payload, bridge_end)
    values = [short_name, stadium_name, full_name]
    encoded = [value.strip().encode("cp1252") for value in values]
    if any(not item or len(item) > 255 for item in encoded):
        raise ValueError("EQ replacement string is blank or exceeds 255 CP1252 bytes")
    old_len = (short_end - short_start) + (stadium_end - stadium_start) + (full_end - full_start)
    new_len = sum(len(item) for item in encoded)
    new_total = old_total + new_len - old_len
    out = bytearray()
    out.extend(payload[:total_offset])
    out.extend(_write_u16_xor(new_total))
    out.extend(payload[marker:marker + 4])
    for value in encoded[:2]:
        out.extend(_write_u16_xor(len(value))); out.extend(value)
    out.extend(payload[bridge_start:bridge_end])
    out.extend(_write_u16_xor(len(encoded[2]))); out.extend(encoded[2])
    out.extend(payload[full_end:])
    # Validate only the fields this function owns.
    check = bytes(out)
    check_marker = check.find(b"\xdd\x63\x61", 2, 64)
    c = check_marker + 4
    observed = []
    for _ in range(2):
        value, _start, c = _read_inner_string(check, c); observed.append(value)
    c += 2
    value, _start, _end = _read_inner_string(check, c); observed.append(value)
    if observed != values:
        raise ValueError("EQ strings failed read-back")
    return check


def _rewrite_roster_tail(raw_payload: bytes, player_ids: list[int]) -> bytes:
    parsed = parse_eq_external_team_roster_payload(raw_payload, {})
    if parsed is None or not parsed.rows:
        raise ValueError("EQ record has no supported external roster")
    first = parsed.rows[0].raw_row_offset
    old_end = parsed.rows[-1].raw_row_offset + 5
    if old_end != len(raw_payload):
        raise ValueError("EQ roster is not a terminal tail")
    if len(player_ids) < 16 or len(player_ids) > 255 or len(set(player_ids)) != len(player_ids):
        raise ValueError("roster must contain 16..255 unique ids")
    result = bytearray(raw_payload[:first - 1])
    result.append(len(player_ids))
    for index, player_id in enumerate(player_ids):
        flag = parsed.rows[index].flag if index < len(parsed.rows) else 0
        result.append(flag)
        result.extend(int(player_id).to_bytes(4, "little"))
    check = parse_eq_external_team_roster_payload(bytes(result), {})
    if check is None or [row.player_record_id for row in check.rows] != player_ids:
        raise ValueError("EQ roster tail failed read-back")
    return bytes(result)


def _rebuild_indexed(original: bytes, indexed: IndexedFDIFile, replacements: dict[int, bytes]) -> bytes:
    """Rebuild indexed FDI with decoded payload replacements."""
    entries = sorted(indexed.entries, key=lambda entry: entry.payload_offset)
    replacement_ids = set(replacements)
    if replacement_ids - {entry.record_id for entry in entries}:
        raise ValueError("replacement record missing from FDI")
    first = entries[0].payload_offset
    out = bytearray(original[:first])
    offsets: dict[int, int] = {}
    lengths: dict[int, int] = {}
    for position, entry in enumerate(entries):
        old_start, old_end = entry.payload_offset, entry.payload_offset + entry.payload_length
        payload = xor_encode(replacements[entry.record_id]) if entry.record_id in replacements else original[old_start:old_end]
        offsets[entry.payload_offset] = len(out)
        lengths[entry.payload_offset] = len(payload)
        out.extend(payload)
        if position + 1 < len(entries):
            out.extend(original[old_end:entries[position + 1].payload_offset])
        else:
            out.extend(original[old_end:])
    for entry in indexed.entries:
        key_len = out[entry.index_offset + 4]
        offset_at = entry.index_offset + 5 + key_len
        struct.pack_into("<I", out, offset_at, offsets[entry.payload_offset])
        struct.pack_into("<I", out, offset_at + 4, lengths[entry.payload_offset])
    checked = IndexedFDIFile.from_bytes(bytes(out))
    if len(checked.entries) != len(indexed.entries):
        raise ValueError("FDI directory changed during rebuild")
    return bytes(out)


def _parse_dob(value: str) -> tuple[int, int, int]:
    day, month, year = value.strip().split("-")
    year_value = int(year)
    return int(day), int(month), 1900 + year_value if year_value >= 20 else 2000 + year_value


def _source_dob_iso(value: str) -> str:
    day, month, year = _parse_dob(value)
    return f"{year:04d}-{month:02d}-{day:02d}"


def _short_name(club: str) -> str:
    aliases = {
        "Manchester United": "Man Utd", "Manchester City": "Man City",
        "West Bromwich Albion": "West Brom", "Queens Park Rangers": "QPR",
        "Brighton & Hove Albion": "Brighton", "Nottingham Forest": "Nottm Forest",
        "Wolverhampton Wanderers": "Wolves", "Sheffield Wednesday": "Sheff Wed",
        "Sheffield United": "Sheff Utd", "Milton Keynes Dons": "MK Dons",
        "AFC Wimbledon": "AFC Wimbledon", "Dagenham & Redbridge": "Dag & Red",
    }
    return aliases.get(club, club)


def _full_name(club: str) -> str:
    return f"{club} Football Club" if not club.endswith("FC") else club


def _select_squad(
    rows: list[dict[str, Any]], division: str, fifa_index: "FifaIndex",
    fifa15_index: "FifaIndex", fifa17_index: "FifaIndex", fifa18_index: "FifaIndex", fifa19_index: "FifaIndex",
    fifa_meta_index: "FifaMetaIndex", editorial_ratings: EditorialRatingBook,
    club: str, opening_contract: dict[str, Any], squad_reference: list[str] | None,
) -> list[dict[str, Any]]:
    """Choose a 25-man squad around a reconciled first-league-match contract."""
    candidates: list[dict[str, Any]] = []
    for source in sorted(rows, key=lambda row: (int(row["shirt_number"]), row["name"])):
        if int(source["shirt_number"]) > 99:
            continue
        # FootballSquads uses zeroes for youth/reserve rows whose published
        # bio has no physical data.  A full historical release must not turn
        # those placeholders into invented height/weight values when at least
        # twenty fully sourced senior rows exist (which the source-ledger
        # gate verifies for every carrier).
        if not (140 <= int(source.get("height_cm") or 0) <= 230 and 40 <= int(source.get("weight_kg") or 0) <= 150):
            continue
        player = dict(source)
        player["source_name"] = str(player["name"])
        player["pm99_name"] = _pm99_text(str(player["name"]))
        player["fifa"] = _match_fifa(
            player["name"], club, str(player["birth_date_ddmmyy"]), fifa_index,
            position=str(player["position"]),
        )
        # FIFA 15 is a close-era fallback, but for a 2015/16 database it is
        # materially better than inventing a tier value or jumping straight
        # to 2017--19.  Keep it separate from the exact FIFA 16 lane so the
        # build receipt never misstates the data's season.
        player["fifa15"] = {} if player["fifa"] else _match_fifa(
            player["name"], club, str(player["birth_date_ddmmyy"]), fifa15_index,
            position=str(player["position"]),
        )
        player["fifa17"] = {} if (player["fifa"] or player["fifa15"]) else _match_fifa(
            player["name"], club, str(player["birth_date_ddmmyy"]), fifa17_index,
            position=str(player["position"]),
        )
        player["fifa18"] = {} if (player["fifa"] or player["fifa15"] or player["fifa17"]) else _match_fifa(
            player["name"], club, str(player["birth_date_ddmmyy"]), fifa18_index,
            position=str(player["position"]),
        )
        player["fifa19"] = {} if (player["fifa"] or player["fifa15"] or player["fifa17"] or player["fifa18"]) else _match_fifa(
            player["name"], club, str(player["birth_date_ddmmyy"]), fifa19_index,
            position=str(player["position"]),
        )
        player["fifa_meta"] = _match_fifa_meta(player["name"], fifa_meta_index)
        candidates.append(player)

    def apply_editorial_rating(player: dict[str, Any], squad_status: str) -> None:
        rating = editorial_ratings.rate(
            club=club,
            division=division,
            player=str(player["source_name"]),
            position=str(player["position"]),
            height_cm=int(player["height_cm"]),
            birth_date_ddmmyy=str(player["birth_date_ddmmyy"]),
            squad_status=squad_status,
        )
        player["skills"] = dict(rating["skills"])
        player["visible_skills"] = dict(rating["visible_skills"])
        player["handling_basis"] = str(rating["handling_basis"])
        player["fine_roles"] = list(rating["fine_roles"])
        player["rating_provenance"] = dict(rating["rating_provenance"])
        player["rating"] = int(player["skills"]["quality"])

    # Give all non-matchday candidates their reserve rating before sorting.
    # FIFA match metadata is intentionally not an argument to this transform.
    for player in candidates:
        apply_editorial_rating(player, "reserve")
    by_source_name = {_normalise(str(row["source_name"])): row for row in candidates}
    if len(by_source_name) != len(candidates):
        raise ValueError(f"{club} has duplicate normalised player identities in its dated source roster")

    def contract_players(label: str) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for row in list(opening_contract.get(label) or []):
            if "source_name" not in row:
                raise ValueError(f"{club} opening contract {label} has no reconciled source name")
            player = by_source_name.get(_normalise(str(row["source_name"])))
            if player is None:
                raise ValueError(f"{club} {label} player is absent from dated roster: {row['source_name']}")
            resolved.append(player)
        return resolved

    eleven = contract_players("starting_xi")
    published_bench = contract_players("substitutes")
    if len(eleven) != 11 or len({_normalise(str(row["source_name"])) for row in eleven}) != 11:
        raise ValueError(f"{club} needs eleven unique reconciled first-league starters")
    if len(published_bench) < 5 or len({_normalise(str(row["source_name"])) for row in published_bench}) != len(published_bench):
        raise ValueError(f"{club} needs a unique reconciled first-league bench")
    starter_keys = {_normalise(str(row["source_name"])) for row in eleven}
    if starter_keys & {_normalise(str(row["source_name"])) for row in published_bench}:
        raise ValueError(f"{club} first-league source puts a player in both XI and bench")

    # PM99 exposes five substitutes. Keep the real match-day order, while
    # ensuring the reported reserve goalkeeper is available on that bench.
    bench_keepers = [row for row in published_bench if row["position"] == "G"]
    if not bench_keepers:
        raise ValueError(f"{club} first-league bench has no identifiable goalkeeper")
    bench = [bench_keepers[0]]
    bench.extend(row for row in published_bench if row is not bench_keepers[0])
    bench = bench[:5]
    bench_keys = {_normalise(str(row["source_name"])) for row in bench}

    if squad_reference is not None:
        reference_keys = [_normalise(name) for name in squad_reference]
        if len(reference_keys) not in {24, 25} or len(set(reference_keys)) != len(reference_keys):
            raise ValueError(f"{club} squad reference must contain 24 or 25 unique players")
        unresolved = [name for name, key in zip(squad_reference, reference_keys, strict=True) if key not in by_source_name]
        if unresolved:
            raise ValueError(f"{club} squad reference includes source-roster absences: {unresolved[:3]}")
        selected = [by_source_name[key] for key in reference_keys]
        expected_matchday = [*eleven, *bench]
        if [player["source_name"] for player in selected[:16]] != [player["source_name"] for player in expected_matchday]:
            raise ValueError(f"{club} squad reference no longer preserves the certified opening XI/bench order")
        for player in selected[:11]:
            apply_editorial_rating(player, "starter")
        for player in selected[11:16]:
            apply_editorial_rating(player, "bench")
        # All remaining source-pinned players retain the default reserve rating.
        return selected

    def source_grade(row: dict[str, Any]) -> int:
        # This is portrait/identity evidence only. It lets a dated senior row
        # outrank an otherwise valid youth page row when PM99 needs a 25-man
        # pool; it has no path to the editorial skills above.
        if row["fifa"]:
            return 4
        if row["fifa15"]:
            return 3
        if row["fifa17"]:
            return 2
        if row["fifa18"]:
            return 1
        if row["fifa19"]:
            return 0
        if row["fifa_meta"]:
            return -1
        return -2

    def squad_rank(row: dict[str, Any]) -> tuple[int, int, int, str]:
        return (-source_grade(row), -int(row["rating"]), int(row["shirt_number"]), str(row["name"]))

    used = starter_keys | bench_keys
    published_reserves = [
        row for row in published_bench
        if _normalise(str(row["source_name"])) not in bench_keys
    ]
    used.update(_normalise(str(row["source_name"])) for row in published_reserves)
    remaining = [row for row in candidates if _normalise(str(row["source_name"])) not in used]
    reserves = published_reserves + sorted(remaining, key=squad_rank)
    # All goalkeepers must be dd6361-backed in this release.  That family has
    # the separately proven Handling trailer; putting any remaining keeper
    # before the first twenty allocation slots prevents it inheriting a 1998
    # visible skill merely because it is the third choice.
    reserves = [row for row in reserves if row["position"] == "G"] + [row for row in reserves if row["position"] != "G"]
    # The source pages include youth keepers with fully populated biographies;
    # keeping every one would produce absurd seven-keeper 25-man squads. Keep
    # the dated XI/bench untouched, then permit at most one extra reserve
    # keeper so every compiled squad has a realistic maximum of three.
    keeper_budget = max(0, 3 - sum(1 for row in eleven + bench if row["position"] == "G"))
    capped_reserves: list[dict[str, Any]] = []
    for row in reserves:
        if row["position"] == "G":
            if keeper_budget <= 0:
                continue
            keeper_budget -= 1
        capped_reserves.append(row)
    selected = eleven + bench + capped_reserves
    if len(selected) < 20:
        raise ValueError(f"{club} only has {len(selected)} balanced source candidates; need at least 20")
    # A few lower-league source pages list fewer than 25 complete senior bios;
    # preserve that factual count rather than invent height/weight for a youth
    # row with zero-valued source data.
    selected = selected[: min(25, len(selected))]
    if sum(1 for row in selected if row["position"] == "G") > 3:
        raise ValueError(f"{club} Core squad has more than three goalkeepers after selection")
    for player in eleven:
        apply_editorial_rating(player, "starter")
    for player in bench:
        apply_editorial_rating(player, "bench")
    # Remaining selected players retain their explicit reserve status.
    return selected


def _tag_fifa_match(row: dict[str, str], method: str) -> dict[str, str]:
    tagged = dict(row)
    tagged["_pm99_match_method"] = method
    return tagged


def _match_fifa(
    name: str,
    club: str,
    birth_date_ddmmyy: str,
    index: "FifaIndex",
    *,
    position: str | None = None,
) -> dict[str, str]:
    """Resolve a source player to a dated FIFA row without crossing positions.

    The historical source roster has a deliberately coarse position family.
    That is not strong enough to distinguish every outfield role, but it is
    decisive for a goalkeeper.  Several English-92 squads contain namesakes
    (for example Adam Smith and Liam Roberts).  Letting a surname fallback
    choose a defender or forward makes their 6--16 goalkeeper fields look
    like an appalling handling rating.  A goalkeeper match is therefore only
    valid when the source row explicitly declares ``GK``; absent that proof,
    the caller records the deterministic goalkeeper fallback instead.
    """
    key = _normalise(name)
    # A small, reviewed alias table bridges published football names that
    # cannot be recovered from token matching alone.  These entries identify
    # a single established player and stay visible in the emitted match
    # method; they are not a general fuzzy-match escape hatch.
    aliases = {
        "chicharito": "javierhernandez",
    }
    alias_key = aliases.get(key)
    exact = index.exact.get(key, [])
    exact_method = "exact-name"
    if not exact and alias_key:
        exact = index.exact.get(alias_key, [])
        exact_method = "reviewed-published-name-alias"
    source_club = _club_key(club)
    source_dob = _source_dob_iso(birth_date_ddmmyy)

    def position_compatible(row: dict[str, str]) -> bool:
        if position != "G":
            return True
        tokens = {
            token.strip().upper()
            for token in re.split(r"[,/\\s]+", str(row.get("preferred_positions", "")))
            if token.strip()
        }
        return "GK" in tokens

    def compatible(rows: list[dict[str, str]]) -> list[dict[str, str]]:
        return [row for row in rows if position_compatible(row)]

    def score(row: dict[str, str]) -> tuple[int, float, str]:
        club_score = 2 if _club_key(row.get("club", "")) == source_club else 0
        return club_score, SequenceMatcher(a=key, b=_normalise(row.get("name", ""))).ratio(), row.get("player_id", "")

    exact = compatible(exact)
    if exact:
        return _tag_fifa_match(max(exact, key=score), exact_method)

    # FIFA Index sometimes stores the short public football name (for example
    # ``Bojan``) while FootballSquads retains a fuller name.  Date of birth
    # plus either club or a strong name containment check is a conservative
    # enough identity bridge; a date alone is never accepted because team
    # mates can share birthdays.
    dob_rows = index.birth_date.get(source_dob, [])
    dob_candidates = []
    for row in compatible(dob_rows):
        candidate_key = _normalise(row.get("name", ""))
        ratio = SequenceMatcher(a=key, b=candidate_key).ratio()
        same_club = _club_key(row.get("club", "")) == source_club
        if (same_club and (ratio >= 0.56 or key in candidate_key or candidate_key in key)) or (
            ratio >= 0.86 or key in candidate_key or candidate_key in key
        ):
            dob_candidates.append(row)
    if dob_candidates:
        return _tag_fifa_match(max(dob_candidates, key=score), "birth-date-and-name")

    # A number of FIFA 16 records use a short football name (``Gabriel``) or
    # a reordered legal name (``John Obi Mikel``) while the dated squad sheet
    # uses ``Gabriel Paulista`` / ``Mikel John Obi``.  Within the *same dated
    # club*, exact token containment is a safer bridge than generic fuzzy
    # matching: it cannot jump to another club's similarly named player.
    def name_tokens(value: str) -> set[str]:
        return {
            _normalise(token)
            for token in unicodedata.normalize("NFKD", str(value)).replace("&#39;", "'").split()
            if _normalise(token)
        }

    source_tokens = name_tokens(name)
    club_aliases: list[dict[str, str]] = []
    for row in compatible(index.club.get(source_club, [])):
        candidate_tokens = name_tokens(str(row.get("name", "")))
        if not candidate_tokens:
            continue
        token_contained = candidate_tokens <= source_tokens or source_tokens <= candidate_tokens
        sufficiently_specific = (
            len(candidate_tokens & source_tokens) >= 2
            or any(len(token) >= 6 and token in source_tokens for token in candidate_tokens)
        )
        if token_contained and sufficiently_specific:
            club_aliases.append(row)
    if club_aliases:
        return _tag_fifa_match(max(club_aliases, key=score), "same-club-token-contained-name")

    # Names such as “Mame Biram Diouf” / “Mame Diouf” need a conservative
    # token-overlap fallback.  A weak match is deliberately rejected.
    best: tuple[tuple[int, float, str], dict[str, str]] | None = None
    # Do not compare every lower-league player against all 10,500 FIFA rows.
    # The last normalized name token is a compact, explainable candidate set:
    # it catches published short forms ("Mame Diouf") while leaving a
    # deterministic skill fallback when no credible FIFA 16 row exists.
    source_tokens = [token for token in _normalise(name).split() if token]
    # _normalise deliberately removes spaces, so derive surname candidates
    # from a separately normalized word sequence.
    raw_tokens = [
        _normalise(token)
        for token in unicodedata.normalize("NFKD", str(name)).split()
        if _normalise(token)
    ]
    candidates = index.surname.get(raw_tokens[-1], []) if raw_tokens else []
    for row in compatible(candidates):
        candidate_key = _normalise(row.get("name", ""))
        ratio = SequenceMatcher(a=key, b=candidate_key).ratio()
        if ratio < 0.72 and not (key in candidate_key or candidate_key in key):
            continue
        item_score = score(row)
        combined = (item_score[0], ratio, item_score[2])
        if best is None or combined > best[0]:
            best = (combined, row)
    return _tag_fifa_match(best[1], "surname-and-name") if best and (best[0][0] >= 2 or best[0][1] >= 0.86) else {}


@dataclass(frozen=True)
class FifaIndex:
    exact: dict[str, list[dict[str, str]]]
    surname: dict[str, list[dict[str, str]]]
    birth_date: dict[str, list[dict[str, str]]]
    club: dict[str, list[dict[str, str]]]


def _load_fifa(path: Path) -> FifaIndex:
    exact: dict[str, list[dict[str, str]]] = defaultdict(list)
    surname: dict[str, list[dict[str, str]]] = defaultdict(list)
    birth_date: dict[str, list[dict[str, str]]] = defaultdict(list)
    club: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            name = str(row.get("name", "")).strip()
            if name:
                item = dict(row)
                exact[_normalise(name)].append(item)
                tokens = [_normalise(token) for token in unicodedata.normalize("NFKD", name).split()]
                if tokens and tokens[-1]:
                    surname[tokens[-1]].append(item)
                if item.get("birthdate"):
                    birth_date[str(item["birthdate"])].append(item)
                if item.get("club"):
                    club[_club_key(str(item["club"]))].append(item)
    return FifaIndex(exact=dict(exact), surname=dict(surname), birth_date=dict(birth_date), club=dict(club))


def _load_fifa17_backfill(path: Path, edition: int) -> FifaIndex:
    """Normalise the documented close-era FIFA 17 source into ``FifaIndex``.

    It intentionally uses the same match rules as FIFA 16 but is loaded in a
    separate lane, so a later close-era attribute record cannot be reported as
    a FIFA 16 fact.  ``short_name`` and ``long_name`` are both indexed as
    aliases for the same id.
    """

    exact: dict[str, list[dict[str, str]]] = defaultdict(list)
    surname: dict[str, list[dict[str, str]]] = defaultdict(list)
    birth_date: dict[str, list[dict[str, str]]] = defaultdict(list)
    club: dict[str, list[dict[str, str]]] = defaultdict(list)
    field_map = {
        "rating": "overall",
        "preferred_positions": "player_positions",
        "acceleration": "movement_acceleration",
        "sprint_speed": "movement_sprint_speed",
        "stamina": "power_stamina",
        "aggression": "mentality_aggression",
        "heading": "attacking_heading_accuracy",
        "dribbling": "skill_dribbling",
        "short_pass": "attacking_short_passing",
        "long_pass": "skill_long_passing",
        "finishing": "attacking_finishing",
        "shot_power": "power_shot_power",
        "stand_tackle": "defending_standing_tackle",
        "slide_tackle": "defending_sliding_tackle",
        "gk_diving": "goalkeeping_diving",
        "gk_handling": "goalkeeping_handling",
        "gk_kicking": "goalkeeping_kicking",
        "gk_reflexes": "goalkeeping_reflexes",
    }
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            player_id = str(raw.get("sofifa_id") or "").strip()
            dob = str(raw.get("dob") or "").strip()
            if not player_id.isdigit() or not dob:
                continue
            item = {
                "player_id": player_id,
                "birthdate": dob,
                "club": str(raw.get("club") or ""),
                "_pm99_edition": str(edition),
                **{target: str(raw.get(source) or "").replace(",", "/") for target, source in field_map.items()},
            }
            aliases = [str(raw.get("short_name") or "").strip(), str(raw.get("long_name") or "").strip()]
            for name in dict.fromkeys(name for name in aliases if name):
                row = {**item, "name": name}
                key = _normalise(name)
                if not key:
                    continue
                exact[key].append(row)
                tokens = [_normalise(token) for token in unicodedata.normalize("NFKD", name).split()]
                if tokens and tokens[-1]:
                    surname[tokens[-1]].append(row)
                birth_date[dob].append(row)
                if item["club"]:
                    club[_club_key(item["club"])].append(row)
    if len(exact) < 15_000:
        raise ValueError("FIFA 17 close-era backfill is unexpectedly incomplete")
    return FifaIndex(exact=dict(exact), surname=dict(surname), birth_date=dict(birth_date), club=dict(club))


@dataclass(frozen=True)
class FifaMetaIndex:
    names: dict[str, list[dict[str, Any]]]
    token_rows: dict[str, list[dict[str, Any]]]


def _name_tokens(value: str) -> list[str]:
    return [
        _normalise(token)
        for token in unicodedata.normalize("NFKD", str(value or "")).replace("&#39;", "'").replace("-", " ").split()
        if _normalise(token)
    ]


def _load_fifa_meta(path: Path) -> FifaMetaIndex:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = list(payload.get("players") or [])
    if len(rows) < 10_000:
        raise ValueError("FIFA 16 player metadata is unexpectedly incomplete")
    names: dict[str, list[dict[str, Any]]] = defaultdict(list)
    token_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        item = dict(row)
        full = " ".join(part for part in (str(item.get("f") or "").strip(), str(item.get("l") or "").strip()) if part)
        candidates = (full, str(item.get("c") or "").strip())
        for candidate in candidates:
            key = _normalise(candidate)
            if key:
                names[key].append(item)
            for token in _name_tokens(candidate):
                if len(token) >= 4:
                    token_rows[token].append(item)
    return FifaMetaIndex(names=dict(names), token_rows=dict(token_rows))


def _match_fifa_meta(name: str, index: FifaMetaIndex) -> dict[str, str]:
    """Resolve a dated FUT player id without guessing a name collision."""
    candidates = index.names.get(_normalise(name), [])
    by_id = {int(row["id"]): row for row in candidates}
    if len(by_id) != 1:
        # A strict alias pass handles reversible editorial differences such as
        # Matt/Matthew, Andy/Andrew and a missing final legal surname. It
        # requires the same last token or full token containment, so names
        # like George Willis/George Williams cannot be confused.
        source_tokens = _name_tokens(name)
        source_set = set(source_tokens)
        candidate_rows: dict[int, dict[str, Any]] = {}
        for token in source_set:
            if len(token) >= 4:
                for candidate in index.token_rows.get(token, []):
                    candidate_rows[int(candidate["id"])] = candidate
        ranked: list[tuple[float, dict[str, Any]]] = []
        for candidate in candidate_rows.values():
            displays = [
                " ".join(part for part in (str(candidate.get("f") or "").strip(), str(candidate.get("l") or "").strip()) if part),
                str(candidate.get("c") or "").strip(),
            ]
            for display in displays:
                candidate_tokens = _name_tokens(display)
                if not candidate_tokens:
                    continue
                candidate_set = set(candidate_tokens)
                same_last = bool(source_tokens and candidate_tokens and source_tokens[-1] == candidate_tokens[-1])
                token_contained = source_set <= candidate_set or candidate_set <= source_set
                first_ratio = SequenceMatcher(a=source_tokens[0], b=candidate_tokens[0]).ratio()
                first_compatible = (
                    source_tokens[0] == candidate_tokens[0]
                    or source_tokens[0] in candidate_tokens[0]
                    or candidate_tokens[0] in source_tokens[0]
                    or first_ratio >= 0.70
                )
                ratio = SequenceMatcher(a=_normalise(name), b=_normalise(display)).ratio()
                if ratio >= 0.80 and first_compatible and (same_last or token_contained):
                    ranked.append((ratio, candidate))
                    break
        ranked.sort(key=lambda item: item[0], reverse=True)
        if not ranked or (len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.04):
            return {}
        row = ranked[0][1]
        method = "FIFA 16 FUT strict name alias"
    else:
        row = next(iter(by_id.values()))
        method = "FIFA 16 FUT exact published name"
    return {
        "player_id": str(int(row["id"])),
        "rating": str(row.get("r") or ""),
        "_pm99_match_method": method,
    }


def _extract_country_codes(game_root: Path) -> dict[str, int]:
    # Reuse the already validated country-table reader, not a hand-maintained
    # nationality integer list.
    sys.path.insert(0, str(ROOT / "scripts"))
    from stoke_2015_apply_metadata import _extract_nationality_codes  # type: ignore
    return _extract_nationality_codes(game_root / "DBDAT" / "TEXTOS.PKF")


NATIONALITY = {
    "ENG": "ENGLAND", "SCO": "SCOTLAND", "WAL": "WALES", "NIR": "NORTHERN IRELAND", "IRL": "IRELAND",
    "FRA": "FRANCE", "ESP": "SPAIN", "GER": "GERMANY", "ITA": "ITALY", "POR": "PORTUGAL", "NED": "HOLLAND",
    "BEL": "BELGIUM", "DEN": "DENMARK", "SWE": "SWEDEN", "NOR": "NORWAY", "FIN": "FINLAND", "ICE": "ICELAND",
    "POL": "POLAND", "CZE": "CZECH REPUBLIC", "SVK": "SLOVAKIA", "HUN": "HUNGARY", "CRO": "CROATIA", "SRB": "YUGOSLAVIA",
    "BOS": "BOSNIA HERZEGOVINA", "ROU": "ROMANIA", "BUL": "BULGARIA", "GRE": "GREECE", "AUT": "AUSTRIA", "SUI": "SWITZERLAND",
    "TUR": "TURKEY", "UKR": "UKRAINE", "RUS": "RUSSIA", "BRA": "BRAZIL", "ARG": "ARGENTINA", "CHI": "CHILE",
    "COL": "COLOMBIA", "URU": "URUGUAY", "PAR": "PARAGUAY", "MEX": "MEXICO", "USA": "UNITED STATES", "CAN": "CANADA",
    "AUS": "AUSTRALIA", "NZL": "NEW ZEALAND", "JPN": "JAPAN", "KOR": "SOUTH KOREA", "NGA": "NIGERIA",
    "GHA": "GHANA", "SEN": "SENEGAL", "CIV": "IVORY COAST", "CMR": "CAMEROON", "MLI": "MALI", "EGY": "EGYPT",
    "MAR": "MOROCCO", "ALG": "ALGIERS", "TUN": "TUNISIA", "RSA": "SOUTH AFRICA", "ZIM": "ZIMBABWE", "JAM": "JAMAICA",
    "TRI": "TRINIDAD AND TOBAGO", "CRC": "COSTA RICA", "VEN": "VENEZUELA", "PER": "PERU", "BOL": "BOLIVIA",
    "ISL": "ICELAND", "MKD": "MACEDONIA", "COD": "ZAIRE", "CGO": "ZAIRE", "BEN": "BENIN", "GAB": "GABON",
    "ANG": "ANGOLA", "KEN": "KENYA", "UGA": "UGANDA", "GAM": "GAMBIA", "SLE": "SIERRA LEONE", "GUI": "GUINEA",
    "CPV": "CAPE VERDE", "BFA": "BURKINA FASO", "TOG": "TOGO", "LBR": "LIBERIA", "GEO": "GEORGIA", "ARM": "ARMENIA",
    "LAT": "LATVIA", "LVA": "LATVIA", "LTU": "LITHUANIA", "EST": "ESTONIA", "MDA": "MOLDOVA", "ALB": "ALBANIA",
    "KSV": "ALBANIA", "MNE": "YUGOSLAVIA", "SVN": "SLOVENIA", "BLR": "BELARUS", "AZE": "AZERBAIJAN", "IRN": "IRAN",
    "IRQ": "IRAQ", "KSA": "SAUDI ARABIA", "QAT": "QATAR", "ISR": "ISRAEL", "JAM": "JAMAICA", "BER": "BERMUDA",

    # The season source packages use modern three-letter country abbreviations
    # while PM99 exposes its own (older) TEXTOS country labels.  These aliases
    # are exact label translations, not editorial substitutions.  Keeping them
    # here makes every compiler caller use the same table and prevents a valid
    # source value from silently becoming the game's ``XXX`` nationality.
    "AFG": "AFGHANISTAN", "ATG": "ANTIGUA Y BARBUDA", "BAN": "BANGLADESH",
    "BDI": "BURUNDI", "BHR": "BAHRAIN", "BIH": "BOSNIA HERZEGOVINA",
    "BLZ": "BELIZE", "BOT": "BOTSWANA", "BRB": "BARBADOS", "CHA": "CHAD",
    "CHN": "CHINA", "COM": "COMORO", "CTA": "CENTRAL AFRICAN REPUBLIC", "DJI": "DJIBOUTI",
    "CUB": "CUBA", "CYP": "CYPRUS", "DEU": "GERMANY", "DMA": "DOMINICA",
    "DOM": "DOMINICAN REPUBLIC", "ECU": "ECUADOR", "END": "ENGLAND",
    "EQG": "EQUATORIAL GUINEA", "ERI": "ERITREA", "FRO": "FAEROE ISLANDS",
    "GNB": "GUINEA BISSAU", "GRN": "GRANADA", "GUA": "GUATEMALA",
    "HAI": "HAITI", "HON": "HONDURAS", "IDN": "INDONESIA", "IND": "INDIA",
    "JOR": "JORDAN", "KAZ": "KAZAKISTAN", "KGZ": "KYRGYZISTAN",
    "LBY": "LIBYA", "LCA": "SAINT LUCIA", "LIB": "LEBANON",
    "LIE": "LIECHTENSTEIN", "LUX": "LUXEMBOURG", "MAD": "MADAGASCAR",
    "MGL": "MONGOLIA", "MLT": "MALTA", "MOZ": "MOZAMBIQUE",
    "MRI": "MAURITIUS ISLANDS", "MTN": "MAURITANIA", "MWI": "MALAWI",
    "NAM": "NAMIBIA", "NCL": "NEW CALEDONIA", "NGR": "NIGERIA",
    "NIG": "NIGER", "OMA": "OMAN", "PAK": "PAKISTAN", "PAN": "PANAMA",
    "PHI": "PHILIPPINES", "PRK": "NORTH KOREA", "RWA": "RWANDA",
    "SEB": "SERBIA", "SEY": "SEYCHELLES", "SIN": "SINGAPORE",
    "SKN": "SAN KITTS Y NEVIS", "SLO": "SLOVENIA", "SLV": "EL SALVADOR",
    "SOM": "SOMALIA", "STP": "SAINT TOME AND PRINCE", "SUD": "SUDAN",
    "SUR": "SURINAM", "SYR": "SYRIA", "TAH": "TAHITI", "TAN": "TANZANIA",
    "THA": "THAILAND", "TKM": "TURKMENISTAN", "UAE": "UNITED ARAB EMIRATES",
    "UZB": "UZBEKISTHAN", "VIE": "VIETNAM", "YEM": "YEMEN", "ZAM": "ZAMBIA",
}


# PM99's fixed 1998 country table has no native label for these declared
# nationalities.  They are deliberately explicit rather than being treated as
# missing map entries: a playable build preserves the game-native XXX display,
# while QA can report them as a real table-capacity limitation instead of
# masking the source fact or substituting a different country.
UNREPRESENTABLE_NATIONALITY = frozenset({
    "ANT",  # Netherlands Antilles
    "ARU",  # Aruba
    "CUW",  # Curaçao
    "GIB",  # Gibraltar
    "GUY",  # Guyana (not French Guiana, which PM99 does contain)
    "HKG",  # Hong Kong
    "KVX",  # Kosovo
    "MSR",  # Montserrat
    "PLE",  # Palestine
    "TCA",  # Turks and Caicos Islands
    "VGB",  # British Virgin Islands
})
UNKNOWN_NATIONALITY = frozenset({"", "UNK", "UNKNOWN", "XXX"})


def _country_code(abbr: str, table: dict[str, int]) -> int:
    code = str(abbr or "").strip().upper()
    if code in UNKNOWN_NATIONALITY or code in UNREPRESENTABLE_NATIONALITY:
        return int(table["XXX"])
    label = NATIONALITY.get(code)
    if label is None:
        raise ValueError(f"unmapped nationality abbreviation {code!r}")
    if label not in table:
        raise ValueError(
            f"PM99 TEXTOS country table lacks mapped nationality label {label!r} for {code!r}"
        )
    return int(table[label])


EQ_TACTICS_PREFIX_BYTES = 0
EQ_TACTICS_PLAYER_BYTES = 160
EQ_TACTICS_PLAYER_COUNT = 11
EQ_TACTICS_GRID_BYTES = EQ_TACTICS_PLAYER_BYTES * EQ_TACTICS_PLAYER_COUNT
EQ_TACTICS_TRAILER_BYTES = 7
EQ_TACTICS_TOTAL_BYTES = EQ_TACTICS_PREFIX_BYTES + EQ_TACTICS_GRID_BYTES + EQ_TACTICS_TRAILER_BYTES


def _formation_bands(formation: object) -> tuple[int, ...]:
    """Parse a conventional outfield formation, failing closed on ambiguity.

    The line-up capture's position dots are useful for left/right ordering, but
    are not a PM99 tactical coordinate system.  A literal translation can put
    every attacking midfielder in the same high PM99 band as a striker.  The
    formation string is the authoritative declaration of how many players
    belong in each line; it must account for exactly the ten outfield players.
    """
    text = str(formation or "").strip()
    if not re.fullmatch(r"[1-9](?:-[1-9])+", text):
        raise ValueError(f"Unsupported first-fixture formation: {formation!r}")
    bands = tuple(int(value) for value in text.split("-"))
    if sum(bands) != 10:
        raise ValueError(
            f"First-fixture formation must account for ten outfield players: {formation!r}"
        )
    if len(bands) not in {2, 3, 4, 5}:
        raise ValueError(f"First-fixture formation has unsupported line count: {formation!r}")
    return bands


def _formation_band_depths(bands: tuple[int, ...]) -> tuple[int, ...]:
    """Return PM99-calibrated depths for a declared formation's lines.

    These are deliberately database-native coordinates, not bytes copied from
    ``TACTICS/predef.*``.  The predefined tactic files are a different format
    and a previous direct-copy probe made PM99 reject a fresh game.  The values
    are calibrated against the real Advanced Tactics pitch: defenders remain
    in their own third, the final declared line occupies the attacking band,
    and intermediate lines remain visibly distinct.
    """
    depth_templates: dict[int, tuple[int, ...]] = {
        2: (135, 400),
        3: (135, 270, 400),
        4: (130, 210, 280, 400),
        5: (125, 195, 270, 330, 405),
    }
    return depth_templates[len(bands)]


def _opening_tactics_from_first_fixture(contract: dict[str, Any]) -> list[list[int]]:
    """Build a PM99-native static grid from a declared first-fixture shape.

    Transfermarkt's pitch is upright: ``top`` grows towards the goalkeeper and
    ``left`` grows towards the right-hand touchline.  PM99's first word is the
    rendered vertical lane (a roughly 228-unit axis), while its second word is
    depth towards the right-hand goal.  The two axes have different legal
    ranges.  Do not scale the vertical lane as if it were the much wider depth
    axis: PM99 clips an over-large first word against the lower edge of the
    pitch, which collapses a formation onto one touchline.

    ``left`` is retained for the lateral placement of each named player.
    ``top`` is used only to order the outfield players into their declared
    formation lines.  It is intentionally not used as a literal depth: source
    diagrams often pack attacking midfielders close to the striker, whereas
    PM99 renders those dots as a five-forward opening shape.

    The words are repeated for defence and attack because a first-fixture
    formation is a static starting state, not a claim about all twenty
    contextual ball-zone decisions.
    """
    starters = list(contract.get("starting_xi") or [])
    if len(starters) != EQ_TACTICS_PLAYER_COUNT:
        raise ValueError("First-fixture tactics need exactly eleven reconciled starters")
    formation_bands = _formation_bands(contract.get("formation"))
    formation_depths = _formation_band_depths(formation_bands)
    prepared: list[tuple[int, float, float, str]] = []
    for index, row in enumerate(starters):
        try:
            left = float(row["pitch_left_percent"])
            top = float(row["pitch_top_percent"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"First-fixture player has no usable pitch coordinate: {row}") from exc
        prepared.append((index, left, top, str(row.get("position") or "").upper()))

    goalkeeper_indexes = [index for index, _, _, position in prepared if position == "G"]
    if len(goalkeeper_indexes) != 1:
        raise ValueError("First-fixture tactics need exactly one named goalkeeper")
    outfield = sorted(
        (entry for entry in prepared if entry[0] not in goalkeeper_indexes),
        key=lambda entry: entry[2],
        reverse=True,
    )
    if len(outfield) != sum(formation_bands):
        raise ValueError("First-fixture tactics do not reconcile to the declared formation")

    depth_by_index: dict[int, int] = {goalkeeper_indexes[0]: 55}
    cursor = 0
    for count, depth in zip(formation_bands, formation_depths, strict=True):
        for index, _, _, _ in outfield[cursor:cursor + count]:
            depth_by_index[index] = depth
        cursor += count

    positions: list[list[int]] = []
    for index, left, _, _ in prepared:
        # PM99 stores (vertical lane, depth) for defence then attack.  Its
        # vertical lane is the short axis, so map Transfermarkt's 0..100 left
        # percentage into the safe 20..208 in-pitch lane.  PM99's visible
        # centre is lane 128, while Transfermarkt uses left=40 for a central
        # player.  The 208 intercept aligns those centres rather than leaving
        # every club's XI slightly low on the rendered pitch. The mirrored lane
        # matches PM99's horizontal presentation: a source right-back sits on
        # the upper side of the rendered pitch and a source left-back on the
        # lower side.  ``top`` maps independently to left-to-right depth.
        vertical = max(20, min(208, round(208 - left * 2.0)))
        positions.append([vertical, depth_by_index[index], vertical, depth_by_index[index]])
    return positions


def _raw_eq_string_end(payload: bytes, cursor: int, label: str) -> int:
    if cursor + 2 > len(payload):
        raise ValueError(f"EQ {label} length lies outside the record")
    end = cursor + 2 + int.from_bytes(payload[cursor:cursor + 2], "little")
    if end > len(payload) or end == cursor + 2:
        raise ValueError(f"EQ {label} is invalid")
    return end


def _mode0_initial_tactics_offset(raw_payload: bytes) -> int:
    """Return the only runtime-proven initial-tactics region (large mode 0)."""
    if len(raw_payload) < 0x2A:
        raise ValueError("EQ payload is too short for initial tactics")
    record_size = int.from_bytes(raw_payload[0x26:0x28], "little")
    if record_size < 600 or raw_payload[0x29] != 0:
        raise ValueError("Initial-tactics writer is proven only for large mode-0 EQ records")
    cursor = 0x2A
    cursor = _raw_eq_string_end(raw_payload, cursor, "short club name")
    cursor = _raw_eq_string_end(raw_payload, cursor, "stadium name")
    cursor += 1 + (1 if record_size > 0x20C else 0)
    cursor = _raw_eq_string_end(raw_payload, cursor, "full club name")
    cursor += 4 + (4 if record_size >= 0x1FE else 0) + 6
    if record_size > 0x207:
        cursor += 2
    cursor += 4
    cursor = _raw_eq_string_end(raw_payload, cursor, "chairman")
    cursor += 8
    cursor = _raw_eq_string_end(raw_payload, cursor, "sponsor")
    cursor = _raw_eq_string_end(raw_payload, cursor, "supplier")
    cursor += 3 + (20 if record_size >= 0x1F9 else 10) + 15 + (46 if record_size >= 0x1F9 else 42)
    if record_size < 700:
        cursor += (7 if record_size < 0x1F9 else 17 if record_size < 0x203 else 21) * 2
    else:
        if cursor >= len(raw_payload):
            raise ValueError("EQ sparse-count byte lies outside the record")
        cursor += 1 + raw_payload[cursor] * 3
    if cursor + EQ_TACTICS_TOTAL_BYTES > len(raw_payload):
        raise ValueError("Initial tactics candidate exceeds the EQ payload")
    return cursor


def _mode1_initial_tactics_offset(raw_payload: bytes) -> int:
    """Return a structurally bounded, but not runtime-proven, mode-1 candidate.

    The indexed EQ-to-ENT reader proves that this is a 0x6e7-byte mode block:
    for mode 1 its manager-link count sits exactly 1,767 bytes after the
    common header/string cursor.  The interior has the same eleven fixed
    twenty-row parameter blocks as the mode-0 tactic grid.  This function
    deliberately parses only the shared prefix and does not reinterpret the
    intervening bytes as mode-0 finance/sponsor metadata.  This only proves
    that a tactics-shaped region is bounded by the shared prefix and link
    tail.  No foreign club can be selected as the managed club in the normal
    new-game flow, so this is deliberately *not* a released write contract.
    """
    if len(raw_payload) < 0x2A:
        raise ValueError("EQ payload is too short for initial tactics")
    record_size = int.from_bytes(raw_payload[0x26:0x28], "little")
    if record_size != 700 or raw_payload[0x29] != 1:
        raise ValueError("Mode-1 initial tactics need a 700-byte mode-1 EQ record")
    cursor = 0x2A
    cursor = _raw_eq_string_end(raw_payload, cursor, "short club name")
    cursor = _raw_eq_string_end(raw_payload, cursor, "stadium name")
    cursor += 1 + (1 if record_size > 0x20C else 0)
    cursor = _raw_eq_string_end(raw_payload, cursor, "full club name")
    cursor += 4 + (4 if record_size >= 0x1FE else 0) + 6
    if cursor + EQ_TACTICS_TOTAL_BYTES > len(raw_payload):
        raise ValueError("Mode-1 initial tactics candidate exceeds the EQ payload")
    return cursor


def _initial_tactics_offset(raw_payload: bytes) -> int:
    """Resolve the only runtime-proven initial-tactics layout (mode 0)."""
    if len(raw_payload) < 0x2A:
        raise ValueError("EQ payload is too short for initial tactics")
    mode = int(raw_payload[0x29])
    if mode == 0:
        return _mode0_initial_tactics_offset(raw_payload)
    raise ValueError(f"No runtime-proven initial-tactics write contract exists for EQ mode {mode}")


def _write_initial_tactics(raw_payload: bytes, positions: list[list[int]]) -> bytes:
    """Legacy static adapter; new recipes should supply twenty contextual states.

    Static recipes keep their documented semantic lane/depth order. Oversized
    legacy pitch coordinates are clipped explicitly to the game's loader range.
    The native boundary/order/biases are handled by the canonical product API.
    """
    if len(positions) != EQ_TACTICS_PLAYER_COUNT or any(len(row) != 4 for row in positions):
        raise ValueError("Need four static coordinates for every opening player slot")
    if any(type(value) is not int or not 0 <= value <= 0x7FF for row in positions for value in row):
        raise ValueError("Initial tactic coordinates must fit PM99's proven raw range")
    states = [[list(min(value, maximum) for value, maximum in zip(position, (228, 398, 228, 398)))
               for _ in range(20)] for position in positions]
    states[0][0][3] = 0  # retain the factory/measured first-goalkeeper-state convention
    return patch_initial_tactics(raw_payload, states)


def _patch_dd6361_visible_handling(
    jug_path: Path,
    player_ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    """Write dd6361's tenth visible stat while proving its native tail map.

    In the decoded indexed payload, the regular writer has already placed the
    nine native visible values at ``[-16:-7]``: speed, stamina, aggression,
    quality, heading, dribbling, passing, shooting and tackling.  The byte at
    ``[-7]`` is the remaining displayed Handling value.  This is the same
    byte the documented dd6361 biography-trailer reader resolves; anchoring it
    to the preceding nine written values makes the compact writer fail closed
    rather than guessing a tail offset.  It also covers the small set of
    biography streams whose length changes make an external cross-entry scan
    unsuitable after a variable-length name rewrite.
    """
    data = jug_path.read_bytes()
    index = IndexedFDIFile.from_bytes(data)
    entries = {entry.record_id: entry for entry in index.entries}
    replacements: dict[int, bytes] = {}
    changes: list[dict[str, Any]] = []
    for row in player_ledger:
        if row["family"] != "dd6361":
            continue
        visible = {field: int(value) for field, value in dict(row["visible_skills"]).items()}
        if tuple(visible) != VISIBLE_SKILLS:
            raise ValueError(f"Player {row['record_id']} has an incomplete visible-skill map")
        player_id = int(row["record_id"])
        entry = entries.get(player_id)
        if entry is None:
            raise ValueError(f"dd6361 visible-skill player {player_id} is missing from JUG")
        payload = bytearray(entry.decode_payload(data))
        if payload[2:5] != b"\xdd\x63\x61" or len(payload) < 19:
            raise ValueError(f"player {player_id} no longer has the proven dd6361 tail layout")
        observed_nine = [payload[-16 + offset] ^ 0x61 for offset in range(len(SKILLS))]
        expected_nine = [visible[field] for field in SKILLS]
        if observed_nine != expected_nine:
            raise ValueError(
                f"player {player_id} visible-tail anchor does not match its nine native skills: "
                f"observed={observed_nine} expected={expected_nine}"
            )
        before = payload[-7] ^ 0x61
        payload[-7] = visible["handling"] ^ 0x61
        replacements[player_id] = bytes(payload)
        changes.append({
            "record_id": player_id,
            "name": row["name"],
            "club": row["club"],
            "position": row["position"],
            "handling_before": before,
            "handling_after": visible["handling"],
            "handling_basis": row["handling_basis"],
        })
    if not replacements:
        raise RuntimeError("No dd6361 players were available for visible Handling synchronisation")
    jug_path.write_bytes(_rebuild_indexed(data, index, replacements))

    verify_data = jug_path.read_bytes()
    verify_index = IndexedFDIFile.from_bytes(verify_data)
    verify_entries = {entry.record_id: entry for entry in verify_index.entries}
    for change in changes:
        payload = verify_entries[int(change["record_id"])].decode_payload(verify_data)
        if payload[-7] ^ 0x61 != int(change["handling_after"]):
            raise RuntimeError(f"Handling read-back failed for player {change['record_id']}")
    return {
        "schema_version": "pm99-dd6361-visible-handling-v1",
        "requested_player_count": len(changes),
        "goalkeeper_count": sum(1 for row in changes if row["position"] == "G"),
        "changes": changes,
    }


def _patch_ent_name(payload: bytes, record_id: int, name: str, *, native_names: dict[str, str] | None = None) -> bytes:
    if native_names is not None:
        from app.ent_manager_profiles import parse_indexed_ent_manager_profile, replace_indexed_ent_manager_names
        from app.xor import xor_decode, xor_encode
        raw = xor_encode(payload)
        profile = parse_indexed_ent_manager_profile(raw, record_id=record_id)
        return xor_decode(replace_indexed_ent_manager_names(raw, record_id=record_id,
            expected_surname=profile.surname, expected_display_name=profile.display_name,
            surname=native_names['surname'], display_name=native_names['display_name']))
    marker = payload.find(b"\xdd\x63\x60")
    full = False
    if marker < 0:
        marker = payload.find(b"\xdd\x63\x61"); full = marker >= 0
    if marker < 2:
        raise ValueError("manager record is not a recognised ENT profile")
    stored_id = _read_u16_xor(payload, marker + 3)
    if stored_id != record_id:
        raise ValueError("manager record id mismatch")
    surname, _start, surname_end = _read_inner_string(payload, marker + 5)
    name_bytes = name.encode("cp1252")
    if not name_bytes or len(name_bytes) > 255:
        raise ValueError("invalid manager display text")
    prefix = payload[:marker - 2]
    header = payload[marker:marker + 5]
    out = bytearray(prefix)
    if full:
        display, _ds, display_end = _read_inner_string(payload, surname_end)
        display_bytes = name_bytes
        out.extend(_write_u16_xor(len(name_bytes) + len(display_bytes) + 2))
        out.extend(header); out.extend(_write_u16_xor(len(name_bytes))); out.extend(name_bytes)
        out.extend(_write_u16_xor(len(display_bytes))); out.extend(display_bytes); out.extend(payload[display_end:])
    else:
        out.extend(_write_u16_xor(len(name_bytes) + 1))
        out.extend(header); out.extend(_write_u16_xor(len(name_bytes))); out.extend(name_bytes); out.extend(payload[surname_end:])
    return bytes(out)


def _read_manager_candidates(ent_file: Path) -> list[tuple[int, bytes]]:
    data = ent_file.read_bytes(); indexed = IndexedFDIFile.from_bytes(data)
    rows = []
    for entry in indexed.entries:
        payload = entry.decode_payload(data)
        try:
            marker = payload.find(b"\xdd\x63\x60")
            if marker < 0: marker = payload.find(b"\xdd\x63\x61")
            if marker < 2 or _read_u16_xor(payload, marker + 3) != entry.record_id:
                continue
            _read_inner_string(payload, marker + 5)
        except ValueError:
            continue
        rows.append((entry.record_id, payload))
    return rows


def _load_squad_reference(path: Path, clubs: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Read a certified roster contract without deriving ability from it.

    It locks membership and allocation order while the editorial model changes
    skills, so a ratings refactor cannot silently invalidate established
    squad, face, roster or opening-order evidence.
    """
    rows = list(json.loads(path.read_text(encoding="utf-8")) or [])
    by_club: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_club[str(row.get("club") or "")].append(dict(row))
    expected_clubs = {str(row["club"]) for row in clubs}
    if set(by_club) != expected_clubs:
        missing = sorted(expected_clubs - set(by_club))
        extra = sorted(set(by_club) - expected_clubs)
        raise ValueError(f"squad reference club mismatch: missing={missing[:3]} extra={extra[:3]}")
    result: dict[str, list[str]] = {}
    for club, club_rows in by_club.items():
        ordered = sorted(club_rows, key=lambda row: int(row.get("initial_order", 0)))
        orders = [int(row.get("initial_order", 0)) for row in ordered]
        if len(ordered) not in {24, 25} or orders != list(range(1, len(ordered) + 1)):
            raise ValueError(f"squad reference has invalid allocation order for {club}")
        names = [str(row.get("source_name") or "") for row in ordered]
        if not all(names) or len({_normalise(name) for name in names}) != len(names):
            raise ValueError(f"squad reference has invalid player identities for {club}")
        result[club] = names
    return result


@dataclass
class BuildPaths:
    source_game: Path
    ledger: Path
    opening_lineup_ledger: Path
    manager_ledger: Path
    fifa: Path
    fifa15: Path
    fifa17: Path
    fifa18: Path
    fifa19: Path
    fifa_meta: Path
    editorial_ratings: Path
    squad_reference: Path
    output: Path


@dataclass(frozen=True)
class AppendedJUGCarrier:
    """A fresh directory ID allocated from a mode-0-only dd6361 template."""

    record_id: int
    payload_offset: int
    key: str


def _args() -> BuildPaths:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-game", required=True, type=Path, help="known-working PM99 installation; never edited")
    parser.add_argument("--source-ledger", default=str(ROOT / "upstream/.local/season-2015-16/2015-16-english-source-ledger.json"), type=Path)
    parser.add_argument("--opening-lineup-ledger", default=str(ROOT / ".local/season-2015-16/2015-16-first-fixture-opening-lineup-reconciliation.json"), type=Path)
    parser.add_argument("--manager-ledger", default=str(ROOT / ".local/season-2015-16/2015-16-opening-manager-ledger.json"), type=Path)
    parser.add_argument("--fifa16", default=str(ROOT / ".local/season-2015-16/fifa16-player-stats.csv"), type=Path)
    parser.add_argument("--fifa15-backfill", default=str(ROOT / ".local/season-2015-16/fifa15-sofifa-backfill.csv"), type=Path)
    parser.add_argument("--fifa17-backfill", default=str(ROOT / ".local/season-2015-16/fifa17-sofifa-backfill.csv"), type=Path)
    parser.add_argument("--fifa18-backfill", default=str(ROOT / ".local/season-2015-16/fifa18-sofifa-backfill.csv"), type=Path)
    parser.add_argument("--fifa19-backfill", default=str(ROOT / ".local/season-2015-16/fifa19-sofifa-backfill.csv"), type=Path)
    parser.add_argument("--fifa16-meta", default=str(ROOT / ".local/season-2015-16/fifa16-ea-player-meta.json"), type=Path)
    parser.add_argument(
        "--editorial-ratings",
        default=str(ROOT / "scripts/data/2015-16-english92-editorial-ratings-v1.json"),
        type=Path,
        help="versioned hand-authored PM99 ratings input; the sole source of player skill values",
    )
    parser.add_argument(
        "--squad-reference",
        default=str(ROOT / ".local/season-2015-16/english92-2015-16-build36-native-no-photo/player-ledger.json"),
        type=Path,
        help="certified 2015/16 24/25-player membership/order reference; rating values are ignored",
    )
    parser.add_argument("--output", required=True, type=Path, help="new release directory")
    values = parser.parse_args()
    return BuildPaths(
        values.source_game.expanduser().resolve(), values.source_ledger.resolve(), values.opening_lineup_ledger.resolve(),
        values.manager_ledger.resolve(), values.fifa16.resolve(), values.fifa15_backfill.resolve(), values.fifa17_backfill.resolve(), values.fifa18_backfill.resolve(), values.fifa19_backfill.resolve(), values.fifa16_meta.resolve(), values.editorial_ratings.resolve(), values.squad_reference.resolve(), values.output.expanduser().resolve(),
    )


def main() -> int:
    paths = _args()
    required = [paths.source_game / "DBDAT" / name for name in ("JUG98030.FDI", "EQ98030.FDI", "ENT98030.FDI", "TEXTOS.PKF")]
    required.extend((paths.ledger, paths.opening_lineup_ledger, paths.manager_ledger, paths.fifa, paths.fifa15, paths.fifa17, paths.fifa18, paths.fifa19, paths.fifa_meta, paths.editorial_ratings, paths.squad_reference))
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("Missing required input(s): " + ", ".join(missing))
    if paths.output.exists():
        raise SystemExit(f"Output already exists: {paths.output}")
    paths.output.mkdir(parents=True)
    game = paths.output / "game"
    shutil.copytree(paths.source_game, game, symlinks=True, ignore=shutil.ignore_patterns("SAVE", "output", "wineprefix", "*.png", "*.log"))

    ledger = json.loads(paths.ledger.read_text(encoding="utf-8"))
    clubs = list(ledger.get("clubs") or [])
    club_count = len(clubs)
    release_profile = "english-80-core" if club_count == 80 else "english-92-native"
    if club_count not in {80, 92}:
        raise SystemExit("The source ledger must contain either 80 native Core80 clubs or 92 experimental clubs")
    club_ids = [int(row["carrier_eq_record_id"]) for row in clubs]
    if len(set(club_ids)) != club_count:
        raise SystemExit("Source ledger carrier IDs must be unique")
    if club_count == 92 and set(club_ids) != NATIVE_ENGLISH92_CARRIER_IDS:
        raise SystemExit("The 92-club ledger must use the runtime-proven native English carrier registry")
    if club_count == 80:
        selectors = [row.get("native_selector") for row in clubs]
        if any(not isinstance(selector, dict) for selector in selectors):
            raise SystemExit("The Core80 ledger must declare every runner-proven native selector slot")
        selector_points = {
            (
                str(selector.get("native_panel")),
                int(selector.get("team_select_x")),
                int(selector.get("team_select_y")),
            )
            for selector in selectors
        }
        if len(selector_points) != 80:
            raise SystemExit("The Core80 ledger has duplicate or incomplete native selector slots")
    carrier_ids = set(club_ids)
    squad_reference = _load_squad_reference(paths.squad_reference, clubs)
    opening_lineups = json.loads(paths.opening_lineup_ledger.read_text(encoding="utf-8"))
    if opening_lineups.get("schema_version") != "pm99-2015-16-opening-lineup-reconciliation-v1":
        raise SystemExit("Opening lineup ledger has an unexpected schema")
    opening_by_club = {str(row.get("club")): row for row in opening_lineups.get("clubs") or []}
    selected_club_names = {str(row["club"]) for row in clubs}
    if not selected_club_names <= set(opening_by_club):
        raise SystemExit("Opening lineup ledger is missing one or more selected source-ledger clubs")
    if opening_lineups.get("failures") or any(not opening_by_club[club].get("reconciled") for club in selected_club_names):
        raise SystemExit("Opening lineup ledger is not certified; resolve every selected dated-match identity before compiling")
    manager_ledger = json.loads(paths.manager_ledger.read_text(encoding="utf-8"))
    manager_rows = list(manager_ledger.get("rows") or [])
    managers_by_club = {str(row.get("club")): row for row in manager_rows}
    if not selected_club_names <= set(managers_by_club):
        raise SystemExit("Dated manager ledger is missing one or more selected source-ledger clubs")
    if any(not str(managers_by_club[club].get("manager_name") or "").strip() for club in selected_club_names):
        raise SystemExit("Dated manager ledger has an empty selected opening manager")
    fifa_index = _load_fifa(paths.fifa)
    fifa15_index = _load_fifa17_backfill(paths.fifa15, 15)
    fifa17_index = _load_fifa17_backfill(paths.fifa17, 17)
    fifa18_index = _load_fifa17_backfill(paths.fifa18, 18)
    fifa19_index = _load_fifa17_backfill(paths.fifa19, 19)
    fifa_meta_index = _load_fifa_meta(paths.fifa_meta)
    editorial_ratings = load_editorial_rating_book(paths.editorial_ratings)
    editorial_ratings.validate_player_anchors({
        (str(club_row["club"]), str(player["name"]))
        for club_row in clubs
        for player in list(club_row.get("players") or [])
    })
    country_codes = _extract_country_codes(game)

    jug_path, eq_path, ent_path = (game / "DBDAT" / name for name in ("JUG98030.FDI", "EQ98030.FDI", "ENT98030.FDI"))
    jug_data = jug_path.read_bytes(); jug_index = IndexedFDIFile.from_bytes(jug_data)
    dd6361 = [entry for entry in jug_index.entries if entry.decode_payload(jug_data)[2:5] == b"\xdd\x63\x61" and entry.payload_length >= 80]
    dd6360 = [entry for entry in jug_index.entries if entry.decode_payload(jug_data)[2:5] == b"\xdd\x63\x60" and entry.payload_length >= 60]
    # A JUG team-id is not enough to prove exclusive ownership: the live EQ
    # roster tables are authoritative.  A carrier may be reused only when
    # every existing owner is a selected mode-0 English carrier that this
    # build rewrites.  This permits the two harmless baseline mode-0
    # duplicates but excludes every foreign/mode-1 relationship.
    source_eq_data = eq_path.read_bytes(); source_eq_index = IndexedFDIFile.from_bytes(source_eq_data)
    owner_ids: dict[int, list[int]] = defaultdict(list)
    source_modes: dict[int, int] = {}
    for team_entry in source_eq_index.entries:
        raw = source_eq_data[team_entry.payload_offset:team_entry.payload_offset + team_entry.payload_length]
        try:
            source_modes[team_entry.record_id] = int(extract_indexed_team_payload_metadata(raw)["record_mode"])
        except Exception as exc:
            raise SystemExit(
                f"EQ carrier {team_entry.record_id} has no parser-backed mode; cannot prove English-only donor allocation"
            ) from exc
        parsed = parse_eq_external_team_roster_payload(raw, {})
        if parsed is not None:
            for row in parsed.rows:
                owner_ids[row.player_record_id].append(team_entry.record_id)
    eligible = [
        entry for entry in dd6361
        if owner_ids.get(entry.record_id)
        and all(source_modes.get(owner) == 0 and owner in carrier_ids for owner in owner_ids[entry.record_id])
    ]
    club_selections: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for club_row in clubs:
        club = str(club_row["club"])
        club_selections.append((club_row, _select_squad(
            list(club_row["players"]), str(club_row["division"]), fifa_index, fifa15_index, fifa17_index, fifa18_index, fifa19_index, fifa_meta_index, editorial_ratings, club,
            opening_by_club[club], squad_reference[club],
        )))
    required_dd6361 = sum(min(20, len(selected)) for _club, selected in club_selections)
    if len(eligible) < required_dd6361:
        raise SystemExit(f"Need {required_dd6361} exclusively English dd6361 player carriers; only found {len(eligible)}")
    dd6361_optional_budget = sum(max(0, len(selected) - 20) for _club, selected in club_selections)
    dd6361_available = list(eligible)
    dd6361_append_template = max(eligible, key=lambda entry: entry.payload_length)
    # A selected player may not be borrowed from a mode-1 roster.  The old
    # experimental builder removed such rows from a foreign donor after
    # selecting its JUG carrier, which silently changed the live foreign
    # roster graph (Barcelona was one observed casualty).  There are no
    # mode-0-only dd6360 candidates in the verified base, so a 25-player
    # English build must use the explicit indexed-JUG append route instead of
    # treating foreign compact carriers as spare reserves.
    jug_entry_by_id = {entry.record_id: entry for entry in jug_index.entries}
    next_appended_jug_id = max(max(jug_entry_by_id), max(owner_ids, default=0)) + 1
    manager_candidates = _read_manager_candidates(ent_path)
    if len(manager_candidates) < club_count:
        raise SystemExit(f"Need {club_count} writable ENT manager records; only found {len(manager_candidates)}")

    player_replacements: dict[int, bytes] = {}
    team_plans: list[dict[str, Any]] = []
    player_ledger: list[dict[str, Any]] = []
    portrait_plan: list[dict[str, Any]] = []
    appended_jug_records: list[tuple[int, str, bytes]] = []
    manager_id_iter = iter(manager_candidates)
    donor_removals: dict[int, set[int]] = defaultdict(set)
    dd6361_optional_used = 0

    def take_dd6361(source: dict[str, Any]) -> tuple[Any, bytes, dict[str, Any]]:
        nonlocal next_appended_jug_id
        target_name = str(source["pm99_name"])
        for index, candidate in enumerate(dd6361_available):
            candidate_payload = candidate.decode_payload(jug_data)
            candidate_record = PlayerRecord.from_bytes(candidate_payload, candidate.payload_offset)
            named, proof = _patch_indexed_dd6361_variable_name(candidate_payload, candidate_record.name, target_name)
            if proof["anchor_status"] == "exact":
                dd6361_available.pop(index)
                return candidate, named, proof
        # The native mode-0 pool is finite.  Append a fresh directory record
        # from a safe dd6361 template instead of borrowing a compact carrier
        # whose live EQ roster belongs to a foreign team.
        candidate_payload = dd6361_append_template.decode_payload(jug_data)
        candidate_record = PlayerRecord.from_bytes(candidate_payload, dd6361_append_template.payload_offset)
        named, proof = _patch_indexed_dd6361_variable_name(candidate_payload, candidate_record.name, target_name)
        if proof["anchor_status"] != "exact":
            raise RuntimeError(f"mode-0 dd6361 append template cannot name {target_name}")
        while next_appended_jug_id in jug_entry_by_id or next_appended_jug_id in owner_ids:
            next_appended_jug_id += 1
        appended = AppendedJUGCarrier(next_appended_jug_id, 0, dd6361_append_template.key)
        next_appended_jug_id += 1
        return appended, named, proof

    for club_row, selected in club_selections:
        club = str(club_row["club"]); division = str(club_row["division"]); eq_id = int(club_row["carrier_eq_record_id"])
        opening_contract = opening_by_club[club]
        manager_source = managers_by_club[club]
        ids: list[int] = []
        manager_id, _manager_payload = next(manager_id_iter)
        for order, source in enumerate(selected, start=1):
            use_dd6361 = order <= 20 or dd6361_optional_used < dd6361_optional_budget
            if use_dd6361:
                entry, named_payload, name_proof = take_dd6361(source)
                family = "dd6361"
                if order > 20:
                    dd6361_optional_used += 1
            else:  # pragma: no cover - 24/25-player sources use the append route
                raise RuntimeError("English reserve allocation must not fall back to dd6360 donors")
            player_id = entry.record_id
            ids.append(player_id)
            day, month, year = _parse_dob(str(source["birth_date_ddmmyy"]))
            if family == "dd6361":
                record = PlayerRecord.from_bytes(named_payload, entry.payload_offset)
                _apply_player_mutations(
                    record,
                    team_id=eq_id, position=POSITION[str(source["position"])],
                    nationality=_country_code(str(source["nationality"]), country_codes), birth_day=day, birth_month=month,
                    birth_year=year, height=int(source["height_cm"]), weight=int(source["weight_kg"]),
                    attribute_updates={slot: int(source["skills"][skill]) for slot, skill in zip(range(3, 12), SKILLS, strict=True)},
                    offset=entry.payload_offset,
                )
                payload = _set_dd6361_roles_and_startup(
                    record.to_bytes(), roles=list(source["fine_roles"]), shirt_number=int(source["shirt_number"]), initial_order=order,
                    name_end=int(name_proof["new_name_end"]),
                )
                shirt_number_status = "written-proven-dd6361"
                fine_role_status = "written-six-slot-dd6361"
            else:
                native_role = int((list(source["fine_roles"]) or [0])[0])
                payload = _set_dd6360_native_player_fields(
                    named_payload,
                    role=native_role,
                    position=POSITION[str(source["position"])],
                    nationality=_country_code(str(source["nationality"]), country_codes),
                    birth_day=day,
                    birth_month=month,
                    birth_year=year,
                    height=int(source["height_cm"]),
                    weight=int(source["weight_kg"]),
                    skills={skill: int(source["skills"][skill]) for skill in SKILLS},
                    native_role_start=int(name_proof["new_role_start"]),
                )
                # Team membership is the rebuilt EQ->JUG roster link. The
                # dd6360 header is not a generic team/squad-number layout, so
                # those two undocumented header bytes remain preserve-only.
                shirt_number_status = "preserved-unproven-dd6360"
                fine_role_status = "primary-written-native-dd6360-secondary-preserved"
            check = PlayerRecord.from_bytes(payload, entry.payload_offset)
            if _normalise(check.name) != _normalise(str(source["pm99_name"])):
                raise RuntimeError(
                    f"Player name read-back failed for {source['pm99_name']}: "
                    f"family={family} record={player_id} observed={check.name!r}"
                )
            if player_id in jug_entry_by_id:
                player_replacements[player_id] = payload
            else:
                appended_jug_records.append((player_id, entry.key, payload))
            fifa_row = dict(source["fifa"])
            fifa15_row = dict(source["fifa15"])
            fifa17_row = dict(source["fifa17"])
            fifa18_row = dict(source["fifa18"])
            fifa19_row = dict(source["fifa19"])
            fifa_meta_row = dict(source["fifa_meta"])
            individual_source = fifa_row or fifa15_row or fifa17_row or fifa18_row or fifa19_row
            fifa_source = individual_source or fifa_meta_row
            portrait_source = (
                "fifa16" if (fifa_row or fifa_meta_row) else
                ("fifa15" if fifa15_row else
                 ("fifa17" if fifa17_row else ("fifa18" if fifa18_row else ("fifa19" if fifa19_row else None))))
            )
            portrait_player_id = fifa_source.get("player_id") if fifa_source else None
            player_ledger.append({
                "record_id": player_id, "team_record_id": eq_id, "club": club, "division": division, "name": source["pm99_name"], "source_name": source["source_name"],
                "shirt_number": int(source["shirt_number"]), "initial_order": order, "position": source["position"],
                "family": family, "shirt_number_status": shirt_number_status, "fine_role_status": fine_role_status,
                "fine_roles": source["fine_roles"], "nationality": source["nationality"], "birth_date": f"{year:04d}-{month:02d}-{day:02d}",
                "height_cm": int(source["height_cm"]), "weight_kg": int(source["weight_kg"]), "skills": source["skills"],
                "visible_skills": source["visible_skills"], "handling_basis": source["handling_basis"],
                "rating_basis": f"editorial PM99 transform {editorial_ratings.version}",
                "rating_provenance": source["rating_provenance"],
                "fifa16_match_method": fifa_row.get("_pm99_match_method") if fifa_row else None,
                "fifa15_match_method": fifa15_row.get("_pm99_match_method") if fifa15_row else None,
                "fifa17_match_method": fifa17_row.get("_pm99_match_method") if fifa17_row else None,
                "fifa18_match_method": fifa18_row.get("_pm99_match_method") if fifa18_row else None,
                "fifa19_match_method": fifa19_row.get("_pm99_match_method") if fifa19_row else None,
                "fifa16_player_id": fifa_source.get("player_id") if portrait_source == "fifa16" and fifa_source else None,
                "fifa16_headshot_url": fifa_row.get("headshot_url"),
                "portrait_source": portrait_source,
                "portrait_player_id": portrait_player_id,
            })
            portrait_plan.append({
                "record_id": player_id, "club": club, "player": source["pm99_name"], "source_player": source["source_name"],
                "status": "needs-approved-era-image", "fifa16_headshot_url": fifa_row.get("headshot_url"),
                "portrait_source": portrait_source, "portrait_player_id": portrait_player_id,
                "required_crop": "close head-and-shoulders; do not use an unrelated 1999 carrier photo",
            })
        opening = ids[:11]; bench = ids[11:16]; reserves = ids[16:]
        goalkeeper_id = next((pid for source, pid in zip(selected, ids, strict=True) if source["position"] == "G" and pid in bench), None)
        if goalkeeper_id is None:
            # The selector is still valid if the only goalkeeper starts; choose
            # the first reserve keeper where available, otherwise fail closed.
            goalkeeper_id = next((pid for source, pid in zip(selected, ids, strict=True) if source["position"] == "G" and pid in reserves), None)
        if goalkeeper_id is None:
            raise RuntimeError(f"{club} has no substitute goalkeeper in its selected PM99 pool")
        team_plans.append({
            "record_id": eq_id, "club": club, "division": division, "short_name": _short_name(club),
            "full_club_name": _full_name(club), "stadium_name": str(club_row["ground_name"]),
            "seated_capacity": int(club_row["capacity"]), "starting_finance": DIVISION_FINANCE[division],
            "manager_record_id": manager_id,
            "manager_name": _pm99_text(str(manager_source["manager_name"])),
            "source_manager_name": str(manager_source["manager_name"]),
            "manager_source_url": str(manager_source["source_url"]),
            "manager_source_method": str(manager_source["method"]),
            "roster_player_record_ids": ids,
            "opening_lineup_player_record_ids": opening, "substitute_player_record_ids": bench,
            "reserve_player_record_ids": reserves, "substitute_goalkeeper_record_id": goalkeeper_id,
            "shirt_numbers": [{"player_record_id": pid, "number": int(source["shirt_number"])} for source, pid in zip(selected, ids, strict=True)],
            "opening_tactics_positions": _opening_tactics_from_first_fixture(opening_contract),
            "opening_tactics_source": {
                "formation": opening_contract["formation"],
                "fixture_date": opening_contract["first_league_fixture_date"],
                "lineup_source_url": opening_contract["lineup_source_url"],
                "placement_method": "pm99-formation-band-v1",
            },
            "snapshot_evidence": {
                "first_league_fixture_date": opening_contract["first_league_fixture_date"],
                "roster_source_url": str(club_row["source_url"]),
                "opening_lineup_status": "certified-reconciled-first-league-XI-and-bench",
            },
        })

    # JUG is rebuilt first because all EQ roster links target these exact IDs.
    built_jug = _rebuild_indexed(jug_data, jug_index, player_replacements)
    if appended_jug_records:
        # Imported lazily to avoid the V2 compiler's deliberate import of this
        # legacy source adapter.  The helper verifies every old decoded JUG
        # payload is unchanged while it appends the fresh directory records.
        from scripts.season_package_compiler_v2 import _append_indexed_fdi_records

        built_jug = _append_indexed_fdi_records(original=built_jug, records=appended_jug_records)
    jug_path.write_bytes(built_jug)
    visible_skills_receipt = _patch_dd6361_visible_handling(jug_path, player_ledger)
    non_dd6361_goalkeepers = [
        row for row in player_ledger
        if row["position"] == "G" and row["family"] != "dd6361"
    ]
    if non_dd6361_goalkeepers:
        raise RuntimeError(
            "Every selected goalkeeper must use the proven dd6361 Handling trailer; "
            f"uncovered records: {[row['record_id'] for row in non_dd6361_goalkeepers]}"
        )

    eq_data = eq_path.read_bytes(); eq_index = IndexedFDIFile.from_bytes(eq_data)
    eq_replacements: dict[int, bytes] = {}
    for plan in team_plans:
        entry = next(item for item in eq_index.entries if item.record_id == plan["record_id"])
        decoded = entry.decode_payload(eq_data)
        decoded = _rewrite_eq_strings(decoded, short_name=plan["short_name"], stadium_name=plan["stadium_name"], full_name=plan["full_club_name"])
        raw = xor_encode(decoded)
        raw = patch_indexed_team_seated_capacity(raw, int(plan["seated_capacity"]))
        # Finance and opening state are runtime-proven only in the playable
        # mode-0 lane.  A mode-1 tactics-shaped region is structurally
        # bounded, but it has no foreign-club fresh-game tactics proof; leave
        # it exact rather than quietly promoting a plausible offset to a
        # world-write contract.
        mode = int(extract_indexed_team_payload_metadata(raw)["record_mode"])
        if mode == 0:
            raw = patch_indexed_team_mode0_starting_finance(raw, int(plan["starting_finance"]))
            plan["starting_finance_status"] = "written-proven-mode0"
            raw = _write_initial_tactics(raw, list(plan["opening_tactics_positions"]))
            plan["opening_tactics_status"] = "written-proven-mode0-first-fixture-grid"
        elif mode == 1:
            plan["starting_finance_status"] = f"preserved-unproven-mode{mode}"
            plan["opening_tactics_status"] = f"preserved-unproven-mode{mode}"
        else:
            plan["starting_finance_status"] = f"preserved-unproven-mode{mode}"
            plan["opening_tactics_status"] = f"preserved-unproven-mode{mode}"
        raw = patch_indexed_eq_active_manager_id(raw, int(plan["manager_record_id"]))
        raw = _rewrite_roster_tail(raw, list(plan["roster_player_record_ids"]))
        eq_replacements[int(plan["record_id"])] = xor_decode(raw)
    for donor_id, removed_ids in sorted(donor_removals.items()):
        if donor_id in eq_replacements:
            raise RuntimeError(f"native reserve donor {donor_id} overlaps an English replacement carrier")
        entry = next(item for item in eq_index.entries if item.record_id == donor_id)
        raw = eq_data[entry.payload_offset:entry.payload_offset + entry.payload_length]
        parsed = parse_eq_external_team_roster_payload(raw, {})
        if parsed is None:
            raise RuntimeError(f"native reserve donor {donor_id} has no readable external roster")
        retained = [row.player_record_id for row in parsed.rows if row.player_record_id not in removed_ids]
        if len(retained) < 20:
            raise RuntimeError(f"native reserve donor {donor_id} would fall below 20 players")
        raw = _rewrite_roster_tail(raw, retained)
        eq_replacements[donor_id] = xor_decode(raw)
    built_eq = _rebuild_indexed(eq_data, eq_index, eq_replacements)
    eq_path.write_bytes(built_eq)

    ent_data = ent_path.read_bytes(); ent_index = IndexedFDIFile.from_bytes(ent_data)
    ent_replacements = {}
    for plan in team_plans:
        entry = next(item for item in ent_index.entries if item.record_id == plan["manager_record_id"])
        ent_replacements[entry.record_id] = _patch_ent_name(entry.decode_payload(ent_data), entry.record_id, plan["manager_name"])
    ent_path.write_bytes(_rebuild_indexed(ent_data, ent_index, ent_replacements))

    # Structural post-build audit: every English carrier must resolve its
    # declared 24/25-player JUG roster and every one must parse as a player.
    built_jug_data = jug_path.read_bytes(); built_jug_index = IndexedFDIFile.from_bytes(built_jug_data)
    built_eq_data = eq_path.read_bytes(); built_eq_index = IndexedFDIFile.from_bytes(built_eq_data)
    jug_entries = {entry.record_id: entry for entry in built_jug_index.entries}
    audit = []
    for plan in team_plans:
        entry = next(item for item in built_eq_index.entries if item.record_id == plan["record_id"])
        roster = parse_eq_external_team_roster_payload(built_eq_data[entry.payload_offset:entry.payload_offset + entry.payload_length], {})
        expected = plan["roster_player_record_ids"]
        actual = [row.player_record_id for row in roster.rows] if roster else []
        parsed_names = []
        for pid in actual:
            player_entry = jug_entries.get(pid)
            if player_entry is None:
                continue
            parsed_names.append(PlayerRecord.from_bytes(player_entry.decode_payload(built_jug_data), player_entry.payload_offset).name)
        audit.append({"record_id": plan["record_id"], "club": plan["club"], "expected_count": len(expected), "actual_count": len(actual), "roster_ok": actual == expected, "player_parse_count": len(parsed_names), "player_names": parsed_names})
    if not all(row["roster_ok"] and row["player_parse_count"] == row["expected_count"] for row in audit):
        raise RuntimeError("post-build linked-roster audit failed")

    registry = {
        "schema_version": "pm99-historical-carrier-registry-v2",
        "release_profile": release_profile,
        "selected_carrier_ids": sorted(carrier_ids),
        "slots": [
            {
                "club": plan["club"],
                "carrier_eq_record_id": plan["record_id"],
                "native_selector": next(
                    (row.get("native_selector") for row in clubs if int(row["carrier_eq_record_id"]) == int(plan["record_id"])),
                    None,
                ),
            }
            for plan in team_plans
        ],
    }
    editorial_rating_audit = audit_editorial_distribution(player_ledger, editorial_ratings)
    if editorial_rating_audit["status"] != "pass":
        raise RuntimeError(
            "editorial ratings distribution audit failed: "
            + "; ".join(str(value) for value in editorial_rating_audit["failures"])
        )
    browser_manifest = {
        "schema_version": "pm99-historical-season-v1", "season": "2015/16",
        "release_profile": release_profile, "carrier_registry": registry,
        "sources": [
            "FootballSquads 2015/16 squad pages",
            f"Editorial PM99 ratings {editorial_ratings.schema_version} ({editorial_ratings.version})",
            "Optional FIFA archives are portrait/identity metadata only; no FIFA numerical field is used for PM99 skills.",
        ],
        # Existing-kit copies are a mechanical browser contract only. The
        # separate release ledger marks them as placeholders until sourced
        # historical art has been imported and verified.
        "kit_art_assignments": [{"source_team_record_id": team["record_id"], "target_team_record_id": team["record_id"]} for team in team_plans],
        "players": [{
            "record_id": row["record_id"], "name": row["name"], "position_code": POSITION[row["position"]],
            "fine_roles": row["fine_roles"], "nationality_code": _country_code(row["nationality"], country_codes),
            "birth_date": row["birth_date"], "height_cm": row["height_cm"], "weight_kg": row["weight_kg"], "skills": row["skills"],
            "visible_skills": row["visible_skills"], "handling_basis": row["handling_basis"],
        } for row in player_ledger],
        "teams": team_plans,
        "managers": [{"record_id": plan["manager_record_id"], "surname": plan["manager_name"]} for plan in team_plans],
    }
    output = paths.output
    manifest_name = "2015-16-english80-core-manifest.json" if club_count == 80 else "2015-16-english92-manifest.json"
    _json_dump(output / manifest_name, browser_manifest)
    _json_dump(output / "player-ledger.json", player_ledger)
    _json_dump(output / "portrait-plan.json", portrait_plan)
    _json_dump(output / "roster-audit.json", audit)
    _json_dump(output / "visible-skill-receipt.json", visible_skills_receipt)
    _json_dump(output / "editorial-rating-audit.json", editorial_rating_audit)
    _json_dump(output / "manager-audit.json", [{
        "club": plan["club"], "manager_record_id": plan["manager_record_id"],
        "manager_name": plan["manager_name"], "source_url": plan["manager_source_url"],
        "source_method": plan["manager_source_method"],
    } for plan in team_plans])
    sources = Counter(row["rating_basis"] for row in player_ledger)
    result = {
        "schema_version": "pm99-2015-16-build-v2", "release_profile": release_profile, "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_game": str(paths.source_game), "source_hashes": {name: _sha256(paths.source_game / "DBDAT" / name) for name in ("JUG98030.FDI", "EQ98030.FDI", "ENT98030.FDI")},
        "output_game": str(game), "output_hashes": {name: _sha256(game / "DBDAT" / name) for name in ("JUG98030.FDI", "EQ98030.FDI", "ENT98030.FDI")},
        "clubs": club_count, "players": len(player_ledger), "managers": len(team_plans), "roster_audit_ok": True,
        "rating_basis_counts": dict(sources),
        "editorial_rating_input": {
            "path": str(paths.editorial_ratings),
            "schema_version": editorial_ratings.schema_version,
            "version": editorial_ratings.version,
            "sha256": editorial_ratings.source_sha256,
            "audit": "editorial-rating-audit.json",
        },
        "squad_membership_reference": {
            "path": str(paths.squad_reference),
            "sha256": _sha256(paths.squad_reference),
            "contract": "membership-and-initial-order-only; ratings ignored",
        },
        "manager_source": str(paths.manager_ledger),
        "portrait_identity_metadata": {
            "fifa16_source": str(paths.fifa),
            "fifa17_backfill_source": str(paths.fifa17),
            "numerical_rating_use": "none",
        },
        "manager_audit_ok": True,
        "visible_skills": {
            "dd6361_players_synchronised": int(visible_skills_receipt["requested_player_count"]),
            "goalkeeper_count": int(visible_skills_receipt["goalkeeper_count"]),
            "goalkeeper_handling_contract": "all selected goalkeepers are dd6361 and receive editorial style-profile handling",
        },
        "portrait_status": "unbuilt: every replacement photo requires approved era-specific source and crop",
        "kit_status": "unbuilt: manifest has identity assignments only; historical kit-art import is an independent gate",
    }
    _json_dump(output / "build-manifest.json", result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
