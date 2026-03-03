from __future__ import annotations

import csv
import json
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any

from .editor_helpers import _player_display_name
from .editor_sources import gather_player_records_heuristic, gather_player_records_strict
from .xor import decode_entry


PDF_HEADER_MARKERS = {"LISTING OF ALL PALYERS", "NAME", "TEAM"}
PDF_FOOTER_PREFIXES = (
    "Data Base - Premier Manager 99",
    "(C) Copyright 1998/99 GREMLIN INTERACTIVE",
)

# PM99 UI abbreviations as seen in the roster listing PDFs / in-game screens.
PDF_TEAM_LABEL_TO_QUERY = {
    "Arsenal": "Arsenal",
    "Aston Villa": "Aston Villa",
    "Blackburn R.": "Blackburn Rovers",
    "Blackpool": "Blackpool",
    "Barnet": "Barnet",
    "Barnsley": "Barnsley",
    "Birmingham C.": "Birmingham City",
    "Bolton W.": "Bolton Wanderers",
    "Bournemouth": "Bournemouth",
    "Brighton & HA": "Brighton and Hove Albion",
    "Bradford City": "Bradford City",
    "Bristol City": "Bristol City",
    "Bristol Rovers": "Bristol Rovers",
    "Bury": "Bury",
    "Burnley": "Burnley",
    "Cambridge U.": "Cambridge United",
    "Cardiff C.": "Cardiff City",
    "Carlisle U.": "Carlisle United",
    "Charlton Ath.": "Charlton Athletic",
    "Chester C.": "Chester City",
    "Chesterfield": "Chesterfield",
    "Chelsea": "Chelsea",
    "Colchester U.": "Colchester United",
    "Coventry": "Coventry City",
    "Crewe Alex.": "Crewe Alexandra",
    "Crystal Pal.": "Crystal Palace",
    "Darlington": "Darlington",
    "Derby County": "Derby County",
    "Everton": "Everton",
    "Exeter C.": "Exeter City",
    "Fulham": "Fulham",
    "Gillingham": "Gillingham",
    "Grimsby T.": "Grimsby Town",
    "Halifax T.": "Halifax Town",
    "Hartlepool U.": "Hartlepool United",
    "Huddersfield T.": "Huddersfield Town",
    "Hull C.": "Hull City",
    "Ipswich": "Ipswich Town",
    "Leeds Utd.": "Leeds United",
    "Leicester": "Leicester City",
    "Leyton O.": "Leyton Orient",
    "Lincoln C.": "Lincoln City",
    "Liverpool": "Liverpool",
    "Luton T.": "Luton Town",
    "Macclesfield T.": "Macclesfield Town",
    "Manchester C.": "Manchester City",
    "Manchester Utd.": "Manchester United",
    "Middlesbrough": "Middlesbrough",
    "Millwall": "Millwall",
    "Mansfield T.": "Mansfield Town",
    "Northampton T.": "Northampton Town",
    "Newcastle Utd.": "Newcastle United",
    "Nottingham F.": "Nottingham Forest",
    "Notts C.": "Notts County",
    "Oldham Ath.": "Oldham Athletic",
    "Oxford Utd": "Oxford United",
    "Peterborough": "Peterborough United",
    "Plymouth Arg.": "Plymouth Argyle",
    "Port Vale": "Port Vale",
    "Portsmouth": "Portsmouth",
    "Preston NE": "Preston North End",
    "Q.P.R.": "Queens Park Rangers",
    "Reading": "Reading",
    "Rochdale": "Rochdale",
    "Rotherham U.": "Rotherham United",
    "Scarborough": "Scarborough",
    "Scunthorpe U.": "Scunthorpe United",
    "Sheffield W.": "Sheffield Wednesday",
    "Sheffield Utd.": "Sheffield United",
    "Shrewsbury T.": "Shrewsbury Town",
    "Southampton": "Southampton",
    "Southend Utd.": "Southend United",
    "Stockport C.": "Stockport County",
    "Stoke C.": "Stoke City",
    "Sunderland": "Sunderland",
    "Swindon": "Swindon Town",
    "Tottenham H.": "Tottenham Hotspur",
    "Torquay U.": "Torquay United",
    "Tranmere Rov.": "Tranmere Rovers",
    "WBA": "West Bromwich Albion",
    "Walsall": "Walsall",
    "Watford": "Watford",
    "West Ham": "West Ham United",
    "Wigan Ath.": "Wigan Athletic",
    "Wimbledon": "Wimbledon",
    "Wolverhampton": "Wolverhampton Wanderers",
    "Wrexham": "Wrexham",
    "Wycombe W.": "Wycombe Wanderers",
    "York City": "York City",
}


@dataclass(frozen=True)
class PdfRosterRow:
    page: int
    name_label: str
    team_label: str


@dataclass(frozen=True)
class NameHint:
    team_label: str = ""
    team_query: str = ""
    surname: str = ""
    first_name: str = ""
    initial: str = ""
    position: str = ""


@dataclass
class CandidateScore:
    candidate_name: str
    candidate_offset: int
    candidate_source: str
    team_id: int | None = None
    squad_number: int | None = None
    default_score: float = 0.0
    default_band: str = "none"
    default_mentions: list[str] = field(default_factory=list)
    wide_score: float = 0.0
    wide_band: str = "none"
    wide_mentions: list[str] = field(default_factory=list)
    entry_offset: int | None = None
    strict_subrecord_group_byte: int | None = None
    name_hint_match: str = "none"
    name_hint_bonus: float = 0.0
    name_hint_first_name: str = ""
    name_hint_initial: str = ""


@dataclass
class ReconcileRowResult:
    page: int
    team_label: str
    team_query: str
    pdf_name_label: str
    pdf_base_name: str
    pdf_initial_hint: str
    candidate_count: int
    default_hit_count: int
    wide_hit_count: int
    name_hint_count: int
    name_hint_preview: str
    status: str
    status_detail: str
    best_candidate_name: str
    best_candidate_offset_hex: str
    best_candidate_source: str
    best_default_score: float
    best_default_band: str
    best_default_mentions: str
    best_wide_score: float
    best_wide_band: str
    best_wide_mentions: str
    best_strict_group_byte_hex: str
    best_name_hint_match: str
    best_name_hint_bonus: float
    candidate_preview: str
    review_decision: str = ""
    review_notes: str = ""
    expected_full_name: str = ""
    accepted_candidate_name: str = ""


@dataclass
class TeamReconcileSummary:
    team_label: str
    team_query: str
    roster_rows: int
    isolated_default: int
    any_default_match: int
    any_wide_match: int
    status_counts: dict[str, int]
    status_detail_counts: dict[str, int]
    strict_group_bytes: dict[str, int]


@dataclass
class ReconcileRunSummary:
    schema_version: str
    pdf_path: str
    player_file: str
    name_hints_path: str | None
    name_hints_loaded: int
    pdf_rows: int
    teams: int
    team_counts: dict[str, int]
    player_scan_counts: dict[str, int]
    summary_counts: dict[str, int]
    summary_counts_detail: dict[str, int]
    team_summaries: list[TeamReconcileSummary]
    group_byte_team_hints: dict[str, dict[str, int]]
    rows: list[ReconcileRowResult]


def _cli_module():
    # Lazy import avoids circular import when app.cli uses this module.
    from . import cli as cli_module

    return cli_module


def parse_listing_pdf(pdf_path: str) -> list[PdfRosterRow]:
    """Parse the PM99 roster listing PDF into page-scoped rows."""
    try:
        text = subprocess.check_output(["pdftotext", pdf_path, "-"]).decode("utf-8", "ignore")
    except FileNotFoundError as exc:
        raise RuntimeError("pdftotext is required but not installed") from exc

    pages = text.split("\f")
    rows: list[PdfRosterRow] = []
    for page_no, page in enumerate(pages, start=1):
        lines = [ln.strip() for ln in page.splitlines()]
        if "LISTING OF ALL PALYERS" not in lines:
            continue

        data_lines: list[str] = []
        started = False
        for ln in lines:
            if ln == "TEAM":
                started = True
                continue
            if not started or not ln:
                continue
            if any(ln.startswith(prefix) for prefix in PDF_FOOTER_PREFIXES):
                break
            if ln.startswith("Pag.") or ln in PDF_HEADER_MARKERS:
                continue
            data_lines.append(ln)

        if not data_lines:
            continue
        if len(data_lines) % 2 != 0:
            raise RuntimeError(f"Unexpected odd data line count on page {page_no}: {len(data_lines)}")

        half = len(data_lines) // 2
        names = data_lines[:half]
        teams = data_lines[half:]
        for name_label, team_label in zip(names, teams):
            rows.append(PdfRosterRow(page=page_no, name_label=name_label, team_label=team_label))
    return rows


def _normalize_spaces(value: str) -> str:
    return " ".join((value or "").strip().split())


def _normalize_name_match_text(value: str) -> str:
    text = _normalize_spaces(value)
    if not text:
        return ""
    text = (
        text.replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
        .replace("´", "'")
        .replace("–", "-")
        .replace("—", "-")
    )
    decomposed = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _normalize_spaces(text).upper()


def _canonical_team_query(team_label: str) -> str:
    clean = _normalize_spaces(team_label)
    return PDF_TEAM_LABEL_TO_QUERY.get(clean, clean)


def _normalize_hint_team_key(value: str) -> str:
    return _normalize_spaces(value).lower()


def _normalize_hint_surname_key(value: str) -> str:
    return _normalize_name_match_text(value)


def _normalize_hint_given_name_key(value: str) -> str:
    parts = _normalize_name_match_text(value).split()
    return parts[0] if parts else ""


def _iter_name_hint_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        hints = payload.get("hints")
        if isinstance(hints, list):
            return [row for row in hints if isinstance(row, dict)]
    raise RuntimeError("Name hints JSON must be a list[object] or {'hints': [...]} payload")


def _row_value(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in row and row[key] is not None:
            return _normalize_spaces(str(row[key]))
    return ""


def _coerce_name_hint(row: dict[str, Any]) -> NameHint | None:
    team_label = _row_value(row, "team_label", "team", "team_name")
    team_query = _row_value(row, "team_query", "club_query", "club")
    surname = _row_value(row, "surname", "pdf_base_name", "pdf_name_label", "name_label", "name")
    first_name = _row_value(row, "first_name", "forename", "given_name")
    initial = _row_value(row, "initial", "first_initial")
    position = _row_value(row, "position", "pos")

    if not team_label and not team_query:
        return None
    if not surname:
        return None
    if not initial and first_name:
        initial = first_name[0].upper()
    if initial:
        initial = initial[0].upper()

    return NameHint(
        team_label=team_label,
        team_query=team_query,
        surname=surname,
        first_name=first_name,
        initial=initial,
        position=position,
    )


def load_name_hints(path: str) -> list[NameHint]:
    hint_path = Path(path)
    if not hint_path.exists():
        raise RuntimeError(f"Name hints file not found: {hint_path}")

    if hint_path.suffix.lower() == ".json":
        payload = json.loads(hint_path.read_text(encoding="utf-8"))
        raw_rows = _iter_name_hint_rows(payload)
    else:
        with hint_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            raw_rows = [dict(row) for row in reader]

    hints: list[NameHint] = []
    for row in raw_rows:
        hint = _coerce_name_hint(row)
        if hint is not None:
            hints.append(hint)
    return hints


def _build_name_hint_index(hints: list[NameHint]) -> dict[tuple[str, str], list[NameHint]]:
    index: dict[tuple[str, str], list[NameHint]] = defaultdict(list)
    for hint in hints:
        surname_key = _normalize_hint_surname_key(hint.surname)
        if not surname_key:
            continue
        team_values = {hint.team_label, hint.team_query}
        for team_value in list(team_values):
            if not team_value:
                continue
            team_values.add(_canonical_team_query(team_value))
        for team_value in team_values:
            team_key = _normalize_hint_team_key(team_value)
            if not team_key:
                continue
            index[(team_key, surname_key)].append(hint)
    return index


def _name_hints_for_row(
    row: PdfRosterRow,
    club_query: str,
    parsed_label: dict[str, Any],
    name_hint_index: dict[tuple[str, str], list[NameHint]],
) -> list[NameHint]:
    if not name_hint_index:
        return []
    team_keys = {
        _normalize_hint_team_key(row.team_label),
        _normalize_hint_team_key(club_query),
    }
    surname_keys = {
        parsed_label.get("base_match_upper", ""),
        parsed_label.get("last_token_match", ""),
    }

    results: list[NameHint] = []
    seen = set()
    for team_key in team_keys:
        if not team_key:
            continue
        for surname_key in surname_keys:
            if not surname_key:
                continue
            for hint in name_hint_index.get((team_key, surname_key), []):
                hint_key = (
                    hint.team_label,
                    hint.team_query,
                    hint.surname,
                    hint.first_name,
                    hint.initial,
                    hint.position,
                )
                if hint_key in seen:
                    continue
                seen.add(hint_key)
                results.append(hint)
    return results


def _parse_pdf_name_label(label: str) -> dict[str, Any]:
    """
    Parse PDF name labels such as:
      - 'Thorne'
      - 'Davis K.'
      - 'Gregory N.'
      - 'Van der Kwaak'
    """
    clean = _normalize_spaces(label)
    if not clean:
        return {
            "raw": "",
            "base": "",
            "base_upper": "",
            "base_match_upper": "",
            "last_token": "",
            "last_token_match": "",
            "initial_hint": None,
        }

    initial_hint = None
    base = clean

    # Surname with trailing initial (dot optional): "Davis K." / "Johnson M"
    trailing_match = re.match(r"^(?P<base>.+?)\s+(?P<initial>[A-Z])(?:\.)?$", clean)
    # Initial-first forms seen in some PDFs: "D. Wright"
    leading_match = re.match(r"^(?P<initial>[A-Z])(?:\.)?\s+(?P<base>.+)$", clean)

    if trailing_match:
        base = _normalize_spaces(trailing_match.group("base"))
        initial_hint = trailing_match.group("initial").upper()
    elif leading_match:
        base = _normalize_spaces(leading_match.group("base"))
        initial_hint = leading_match.group("initial").upper()
    else:
        base = clean

    base_upper = base.upper()
    base_match_upper = _normalize_name_match_text(base)
    last_token = base_upper.split()[-1] if base_upper.split() else ""
    last_token_match = _normalize_name_match_text(last_token)
    return {
        "raw": clean,
        "base": base,
        "base_upper": base_upper,
        "base_match_upper": base_match_upper,
        "last_token": last_token,
        "last_token_match": last_token_match,
        "initial_hint": initial_hint,
    }


def _entry_ranges(file_bytes: bytes) -> tuple[list[tuple[int, int, int, int]], list[int]]:
    cli = _cli_module()
    ranges = cli._scan_entry_ranges(file_bytes)
    starts = [start for _, start, _, _ in ranges]
    return ranges, starts


def _decode_entry_cached(
    file_bytes: bytes,
    cache: dict[int, tuple[bytes, int]],
    entry_offset: int,
) -> tuple[bytes, int] | None:
    if entry_offset in cache:
        return cache[entry_offset]
    try:
        decoded, enc_len = decode_entry(file_bytes, entry_offset)
    except Exception:
        return None
    cache[entry_offset] = (decoded, enc_len)
    return cache[entry_offset]


def _candidate_display_meta(entry) -> dict[str, Any]:
    record = entry.record
    name = _normalize_spaces(_player_display_name(record))
    upper = name.upper()
    match_upper = _normalize_name_match_text(name)
    parts = upper.split()
    given_name = parts[0] if parts else ""
    last_token = parts[-1] if parts else ""
    given_initial = parts[0][0] if parts and parts[0] else None
    return {
        "name": name,
        "name_upper": upper,
        "name_match_upper": match_upper,
        "given_name": given_name,
        "given_name_match": _normalize_hint_given_name_key(given_name),
        "last_token": last_token,
        "last_token_match": _normalize_name_match_text(last_token),
        "given_initial": given_initial,
    }


def _match_pdf_label_to_candidate(pdf_name_info: dict[str, Any], candidate_meta: dict[str, Any]) -> bool:
    base_upper = pdf_name_info["base_upper"]
    base_match_upper = pdf_name_info.get("base_match_upper") or base_upper
    if not base_upper:
        return False
    pdf_last_token_match = pdf_name_info.get("last_token_match") or pdf_name_info["last_token"]
    candidate_last_token_match = candidate_meta.get("last_token_match") or candidate_meta["last_token"]
    if pdf_name_info["last_token"] and candidate_last_token_match != pdf_last_token_match:
        return False
    if " " in base_upper or "-" in base_upper:
        if base_match_upper not in (candidate_meta.get("name_match_upper") or candidate_meta["name_upper"]):
            return False
    if pdf_name_info["initial_hint"]:
        if candidate_meta.get("given_initial") != pdf_name_info["initial_hint"]:
            return False
    return True


def _team_query_aliases(team_label: str, club_query: str) -> list[str]:
    cli = _cli_module()
    aliases = list(cli._club_query_aliases(club_query))

    raw_label = _normalize_spaces(team_label)
    if raw_label:
        aliases.append(raw_label)
        if "." in raw_label:
            aliases.append(raw_label.replace(".", ""))

    # Abbreviation labels often omit punctuation in decoded blobs (e.g. Q.P.R. -> QPR).
    for alias in list(aliases):
        compact = alias.replace(".", "")
        if compact != alias:
            aliases.append(compact)

    dedup: list[str] = []
    seen = set()
    for alias in aliases:
        cleaned = _normalize_spaces(alias)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(cleaned)
    return dedup


def _score_name_hint_delta(candidate_meta: dict[str, Any], hint: NameHint) -> tuple[float, str]:
    delta = 0.0
    tags: list[str] = []

    hint_first = _normalize_hint_given_name_key(hint.first_name)
    cand_first = candidate_meta.get("given_name_match") or ""
    if hint_first:
        if cand_first and cand_first == hint_first:
            delta += 0.20
            tags.append("first_name_exact")
        elif cand_first and min(len(cand_first), len(hint_first)) >= 4 and (
            cand_first.startswith(hint_first) or hint_first.startswith(cand_first)
        ):
            delta += 0.12
            tags.append("first_name_prefix")
        elif cand_first:
            delta -= 0.35
            tags.append("first_name_mismatch")

    if hint.initial:
        cand_initial = (candidate_meta.get("given_initial") or "").upper()
        if cand_initial and cand_initial == hint.initial.upper():
            delta += 0.08
            tags.append("initial_exact")
        elif cand_initial:
            delta -= 0.08
            tags.append("initial_mismatch")

    if not tags:
        return 0.0, "none"
    return delta, "+".join(tags)


def _apply_name_hints_to_candidate_score(
    score: CandidateScore,
    candidate_meta: dict[str, Any],
    row_hints: list[NameHint],
) -> None:
    if not row_hints:
        return

    best_hint: NameHint | None = None
    best_delta = 0.0
    best_match = "none"
    best_rank = -999.0

    for hint in row_hints:
        delta, match = _score_name_hint_delta(candidate_meta, hint)
        if match == "none":
            continue

        rank = delta
        if "first_name_exact" in match:
            rank += 1.0
        if "initial_exact" in match:
            rank += 0.25
        if "mismatch" in match:
            rank -= 0.5

        if rank > best_rank:
            best_rank = rank
            best_hint = hint
            best_delta = delta
            best_match = match

    if best_hint is None:
        return

    score.name_hint_match = best_match
    score.name_hint_bonus = best_delta
    score.name_hint_first_name = best_hint.first_name or ""
    score.name_hint_initial = best_hint.initial or ""

    cli = _cli_module()
    for scope in ("default", "wide"):
        current = float(getattr(score, f"{scope}_score", 0.0))
        # Do not create club evidence from name hints alone; only modulate existing evidence.
        if current <= 0.0:
            continue
        adjusted = max(0.0, min(1.0, current + best_delta))
        setattr(score, f"{scope}_score", adjusted)
        setattr(score, f"{scope}_band", cli._association_band(adjusted) if adjusted > 0.0 else "none")


def _locate_candidate_entry_offset(entry, file_bytes: bytes, ranges, starts) -> tuple[int, int] | None:
    """Return (entry_offset, payload_start) for the enclosing decoded FDI entry."""
    cli = _cli_module()
    record = entry.record
    container_offset = getattr(record, "container_offset", None)
    if isinstance(container_offset, int):
        return container_offset, container_offset + 2
    enclosing = cli._entry_for_payload_offset(ranges, starts, entry.offset)
    if not enclosing:
        return None
    entry_offset, payload_start, _payload_end, _length = enclosing
    return entry_offset, payload_start


def _score_candidate_for_club(
    entry,
    file_bytes: bytes,
    ranges,
    starts,
    decode_cache: dict[int, tuple[bytes, int]],
    team_label: str,
    club_query: str,
    default_window: int,
    wide_window: int,
) -> CandidateScore:
    cli = _cli_module()
    aliases = _team_query_aliases(team_label, club_query)
    meta = _candidate_display_meta(entry)
    located = _locate_candidate_entry_offset(entry, file_bytes, ranges, starts)
    result = CandidateScore(
        candidate_name=meta["name"],
        candidate_offset=entry.offset,
        candidate_source=entry.source,
        team_id=getattr(entry.record, "team_id", None),
        squad_number=getattr(entry.record, "squad_number", None),
    )
    probe = cli._probe_player_subrecord_header(entry.record)
    group_byte = probe.get("subrecord_group_byte")
    if isinstance(group_byte, int):
        result.strict_subrecord_group_byte = group_byte

    if not located:
        return result
    entry_offset, payload_start = located
    result.entry_offset = entry_offset

    decoded_pair = _decode_entry_cached(file_bytes, decode_cache, entry_offset)
    if not decoded_pair:
        return result
    decoded, _enc_len = decoded_pair
    text = decoded.decode("latin-1", errors="ignore")

    preferred_index = None
    rel = getattr(entry.record, "container_relative_offset", None)
    if isinstance(rel, int) and isinstance(getattr(entry.record, "container_offset", None), int):
        preferred_index = rel
        original_sub = bytes(getattr(entry.record, "original_raw_data", b"") or b"")
        name_bytes = meta["name"].encode("latin-1", errors="ignore")
        if original_sub and name_bytes:
            idx_sub = original_sub.upper().find(name_bytes.upper())
            if idx_sub != -1:
                preferred_index = preferred_index + idx_sub
    if preferred_index is None:
        preferred_index = entry.offset - payload_start

    center = cli._find_name_center_in_text(text, meta["name"], preferred_index=preferred_index)

    def _mentions_for_window(window: int):
        alias_mentions = cli._extract_query_mentions(text, center, aliases, window=window, limit=12)
        club_like_mentions = cli._extract_nearby_club_mentions(text, center, window=window, limit=12)
        club_query_norm = club_query.lower()
        target_mentions = [m for m in club_like_mentions if club_query_norm in m["text"].lower()]
        seen = {(m["index"], m["text"].lower()) for m in target_mentions}
        for m in alias_mentions:
            key = (m["index"], m["text"].lower())
            if key in seen:
                continue
            seen.add(key)
            target_mentions.append(m)
        target_mentions.sort(key=lambda item: (item["distance"], item["index"]))
        return target_mentions

    for key, window in (("default", default_window), ("wide", wide_window)):
        mentions = _mentions_for_window(window)
        if not mentions:
            continue
        nearest = mentions[0]
        score = cli._association_score(
            nearest["distance"],
            window,
            "strict_subrecord_context" if "strict" in entry.source else "heuristic_blob_context",
        )
        score = cli._adjust_confidence_for_mention_kind(score, nearest.get("alias_kind"))
        setattr(result, f"{key}_score", score)
        setattr(result, f"{key}_band", cli._association_band(score))
        setattr(result, f"{key}_mentions", [m["text"] for m in mentions[:5]])

    return result


def _row_result_from(
    row: PdfRosterRow,
    parsed_label: dict[str, Any],
    club_query: str,
    row_hints: list[NameHint],
    status: str,
    status_detail: str,
    scored: list[CandidateScore],
    best: CandidateScore | None,
    default_hits: list[CandidateScore],
    wide_hits: list[CandidateScore],
) -> ReconcileRowResult:
    return ReconcileRowResult(
        page=row.page,
        team_label=row.team_label,
        team_query=club_query,
        pdf_name_label=row.name_label,
        pdf_base_name=parsed_label["base"],
        pdf_initial_hint=parsed_label["initial_hint"] or "",
        candidate_count=len(scored),
        default_hit_count=len(default_hits),
        wide_hit_count=len(wide_hits),
        name_hint_count=len(row_hints),
        name_hint_preview=" | ".join(
            " ".join(part for part in [hint.first_name, hint.surname] if part) or hint.surname
            for hint in row_hints[:5]
        ),
        status=status,
        status_detail=status_detail,
        best_candidate_name=best.candidate_name if best else "",
        best_candidate_offset_hex=(
            f"0x{best.candidate_offset:08X}" if best and isinstance(best.candidate_offset, int) else ""
        ),
        best_candidate_source=best.candidate_source if best else "",
        best_default_score=float(best.default_score) if best else 0.0,
        best_default_band=best.default_band if best else "none",
        best_default_mentions=("; ".join(best.default_mentions) if best else ""),
        best_wide_score=float(best.wide_score) if best else 0.0,
        best_wide_band=best.wide_band if best else "none",
        best_wide_mentions=("; ".join(best.wide_mentions) if best else ""),
        best_strict_group_byte_hex=(
            f"0x{int(best.strict_subrecord_group_byte):02X}"
            if best and isinstance(best.strict_subrecord_group_byte, int)
            else ""
        ),
        best_name_hint_match=(best.name_hint_match if best else "none"),
        best_name_hint_bonus=(float(best.name_hint_bonus) if best else 0.0),
        candidate_preview=" | ".join(
            (
                f"{c.candidate_name}[{c.default_band} {c.default_score:.3f}/"
                f"{c.wide_band} {c.wide_score:.3f}]"
            )
            for c in scored[:5]
        ),
    )


def _detail_status(status: str, best: CandidateScore | None) -> str:
    if status == "isolated_default":
        if best and best.default_band in {"high", "medium"}:
            return "isolated_default_high_conf"
        return "isolated_default_low_conf"
    if status == "isolated_wide_only":
        return "isolated_wide_provisional"
    if status in {"ambiguous_default", "ambiguous_wide_only"}:
        return "ambiguous_review"
    if status == "db_candidate_no_club_evidence":
        return "candidate_no_club_evidence"
    if status == "no_db_candidate":
        return "no_db_candidate"
    return status


def _matches_team_filter(row: PdfRosterRow, team_filter: str | None) -> bool:
    if not team_filter:
        return True
    wanted = _normalize_spaces(team_filter).lower()
    if not wanted:
        return True
    row_label = _normalize_spaces(row.team_label).lower()
    row_query = _canonical_team_query(row.team_label).lower()
    return wanted in {row_label, row_query}


def reconcile_pdf_rosters(
    pdf_path: str,
    player_file: str,
    default_window: int = 800,
    wide_window: int = 10000,
    team_filter: str | None = None,
    name_hints_path: str | None = None,
) -> ReconcileRunSummary:
    pdf_rows_all = parse_listing_pdf(pdf_path)
    pdf_rows = [row for row in pdf_rows_all if _matches_team_filter(row, team_filter)]
    rows_by_team: dict[str, list[PdfRosterRow]] = defaultdict(list)
    for row in pdf_rows:
        rows_by_team[row.team_label].append(row)

    loaded_name_hints = load_name_hints(name_hints_path) if name_hints_path else []
    name_hint_index = _build_name_hint_index(loaded_name_hints) if loaded_name_hints else {}

    heuristic_valid, heuristic_uncertain = gather_player_records_heuristic(player_file)
    strict_valid, strict_uncertain = gather_player_records_strict(player_file)
    heuristic_entries = heuristic_valid + heuristic_uncertain
    strict_entries = strict_valid + strict_uncertain
    strict_offsets = {e.offset for e in strict_entries}

    file_bytes = Path(player_file).read_bytes()
    ranges, starts = _entry_ranges(file_bytes)
    decode_cache: dict[int, tuple[bytes, int]] = {}

    candidates_by_last_token: dict[str, list[Any]] = defaultdict(list)
    candidates_by_last_token_match: dict[str, list[Any]] = defaultdict(list)
    meta_by_offset: dict[int, dict[str, Any]] = {}
    dedup_entries_by_offset: dict[int, Any] = {}
    for entry in heuristic_entries + strict_entries:
        existing = dedup_entries_by_offset.get(entry.offset)
        if existing is not None:
            if ("strict" in entry.source) and ("strict" not in existing.source):
                dedup_entries_by_offset[entry.offset] = entry
            continue
        dedup_entries_by_offset[entry.offset] = entry
    for offset, entry in dedup_entries_by_offset.items():
        meta = _candidate_display_meta(entry)
        meta_by_offset[offset] = meta
        if meta["last_token"]:
            candidates_by_last_token[meta["last_token"]].append(entry)
        if meta.get("last_token_match"):
            candidates_by_last_token_match[meta["last_token_match"]].append(entry)

    detailed_rows: list[ReconcileRowResult] = []
    team_summaries: list[TeamReconcileSummary] = []

    for team_label in sorted(rows_by_team.keys()):
        roster_rows = rows_by_team[team_label]
        club_query = _canonical_team_query(team_label)
        group_counter: Counter[int] = Counter()
        status_counter: Counter[str] = Counter()
        status_detail_counter: Counter[str] = Counter()
        exact_isolated = 0
        any_default_match = 0
        any_wide_match = 0

        for row in roster_rows:
            parsed_label = _parse_pdf_name_label(row.name_label)
            row_hints = _name_hints_for_row(row, club_query, parsed_label, name_hint_index)
            candidate_entries_by_offset: dict[int, Any] = {}
            for entry in candidates_by_last_token.get(parsed_label["last_token"], []):
                candidate_entries_by_offset[entry.offset] = entry
            norm_last = parsed_label.get("last_token_match")
            if norm_last:
                for entry in candidates_by_last_token_match.get(norm_last, []):
                    candidate_entries_by_offset[entry.offset] = entry
            candidate_entries = list(candidate_entries_by_offset.values())
            matched_candidates = [
                entry
                for entry in candidate_entries
                if _match_pdf_label_to_candidate(parsed_label, meta_by_offset[entry.offset])
            ]

            scored: list[CandidateScore] = []
            for entry in matched_candidates:
                score = _score_candidate_for_club(
                    entry=entry,
                    file_bytes=file_bytes,
                    ranges=ranges,
                    starts=starts,
                    decode_cache=decode_cache,
                    team_label=row.team_label,
                    club_query=club_query,
                    default_window=default_window,
                    wide_window=wide_window,
                )
                _apply_name_hints_to_candidate_score(score, meta_by_offset[entry.offset], row_hints)
                scored.append(score)
            scored.sort(
                key=lambda item: (
                    -float(item.default_score),
                    -float(item.wide_score),
                    item.candidate_name,
                )
            )

            best = scored[0] if scored else None
            default_hits = [c for c in scored if float(c.default_score) > 0.0]
            wide_hits = [c for c in scored if float(c.wide_score) > 0.0]

            if default_hits:
                any_default_match += 1
            if wide_hits:
                any_wide_match += 1

            if not matched_candidates:
                status = "no_db_candidate"
            elif not default_hits and not wide_hits:
                status = "db_candidate_no_club_evidence"
            elif len(default_hits) == 1:
                status = "isolated_default"
                exact_isolated += 1
            elif len(default_hits) > 1:
                status = "ambiguous_default"
            elif len(wide_hits) == 1:
                status = "isolated_wide_only"
            else:
                status = "ambiguous_wide_only"
            status_counter[status] += 1
            status_detail = _detail_status(status, best)
            status_detail_counter[status_detail] += 1

            if best and isinstance(best.strict_subrecord_group_byte, int) and float(best.default_score) > 0.0:
                group_counter[int(best.strict_subrecord_group_byte)] += 1

            detailed_rows.append(
                _row_result_from(
                    row=row,
                    parsed_label=parsed_label,
                    club_query=club_query,
                    row_hints=row_hints,
                    status=status,
                    status_detail=status_detail,
                    scored=scored,
                    best=best,
                    default_hits=default_hits,
                    wide_hits=wide_hits,
                )
            )

        team_summaries.append(
            TeamReconcileSummary(
                team_label=team_label,
                team_query=club_query,
                roster_rows=len(roster_rows),
                isolated_default=exact_isolated,
                any_default_match=any_default_match,
                any_wide_match=any_wide_match,
                status_counts=dict(status_counter),
                status_detail_counts=dict(status_detail_counter),
                strict_group_bytes={f"0x{k:02X}": v for k, v in group_counter.most_common()},
            )
        )

    group_to_teams: dict[int, Counter[str]] = defaultdict(Counter)
    for row in detailed_rows:
        if row.status != "isolated_default":
            continue
        value = row.best_strict_group_byte_hex
        if not value:
            continue
        try:
            byte_val = int(value, 16)
        except Exception:
            continue
        group_to_teams[byte_val][row.team_label] += 1

    return ReconcileRunSummary(
        schema_version="v1",
        pdf_path=str(pdf_path),
        player_file=str(player_file),
        name_hints_path=str(name_hints_path) if name_hints_path else None,
        name_hints_loaded=len(loaded_name_hints),
        pdf_rows=len(pdf_rows),
        teams=len(rows_by_team),
        team_counts=dict(Counter(row.team_label for row in pdf_rows)),
        player_scan_counts={
            "heuristic_valid": len(heuristic_valid),
            "heuristic_uncertain": len(heuristic_uncertain),
            "strict_valid": len(strict_valid),
            "strict_uncertain": len(strict_uncertain),
            "strict_offsets": len(strict_offsets),
        },
        summary_counts=dict(Counter(row.status for row in detailed_rows)),
        summary_counts_detail=dict(Counter(row.status_detail for row in detailed_rows)),
        team_summaries=team_summaries,
        group_byte_team_hints={
            f"0x{g:02X}": dict(counter.most_common())
            for g, counter in sorted(group_to_teams.items())
        },
        rows=detailed_rows,
    )


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def result_to_dict(result: ReconcileRunSummary) -> dict[str, Any]:
    return _jsonable(result)


def _write_json(path: str, payload: Any) -> None:
    Path(path).write_text(json.dumps(_jsonable(payload), indent=2), encoding="utf-8")


def _write_csv(path: str, rows: list[Any]) -> None:
    row_dicts = [_jsonable(row) for row in rows]
    if not row_dicts:
        Path(path).write_text("", encoding="utf-8")
        return
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row_dicts[0].keys()))
        writer.writeheader()
        writer.writerows(row_dicts)


def write_reconcile_outputs(
    result: ReconcileRunSummary,
    *,
    json_output: str,
    csv_output: str,
    team_summary_csv: str | None = None,
) -> None:
    _write_json(json_output, result)
    _write_csv(csv_output, result.rows)
    if team_summary_csv:
        _write_csv(team_summary_csv, result.team_summaries)


def print_reconcile_run_summary(result: ReconcileRunSummary, top_n: int = 10) -> None:
    if getattr(result, "schema_version", None):
        print(f"Schema: {result.schema_version}")
    if getattr(result, "name_hints_loaded", 0):
        hint_path = getattr(result, "name_hints_path", None) or "n/a"
        print(f"Name hints: {result.name_hints_loaded} loaded ({hint_path})")
    print(f"Rows: {result.pdf_rows} across {result.teams} teams")
    print(f"Status counts: {result.summary_counts}")
    top_teams = sorted(
        result.team_summaries,
        key=lambda item: (-int(item.isolated_default), item.team_label),
    )[:top_n]
    print("Top teams by isolated_default:")
    for item in top_teams:
        print(
            f"  {item.team_label}: isolated_default={item.isolated_default}, "
            f"any_default={item.any_default_match}, any_wide={item.any_wide_match}, rows={item.roster_rows}"
        )
