#!/usr/bin/env python3
"""Probe PM99 seed PDFs and emit structured reverse-engineering notes data.

This script is intentionally lightweight and safe for iterative local use:
- classifies PDF document types in a folder
- parses known PM99 layouts (player/manager listings, club bio, squad card, player bio)
- cross-checks managers/teams against local DBDAT files (when present)
- cross-correlates squad cards with listing PDFs
- optionally runs a targeted strict player probe to inspect metadata/attributes

It does not write to DBDAT/ and it does not require GUI access.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.editor_sources import _PLAYER_SUBRECORD_SEPARATOR, gather_coach_records, gather_team_records  # type: ignore
from app.models import PlayerRecord  # type: ignore
from app.roster_reconcile import PDF_TEAM_LABEL_TO_QUERY, parse_listing_pdf  # type: ignore
from app.xor import decode_entry  # type: ignore

FOOTER_PREFIXES = (
    "Data Base - Premier Manager 99",
    "(C) Copyright 1998/99 GREMLIN INTERACTIVE",
)


@dataclass
class CoachIndexRow:
    offset: int
    full_name: str
    given_name: str
    surname: str
    norm_surname: str
    norm_last_token: str


@dataclass
class TeamIndexRow:
    offset: int
    team_id: int | None
    name: str
    stadium: str
    stadium_capacity: int | None
    source: str


@dataclass
class StrictPlayerProbeRow:
    source: str
    offset: int
    name: str
    match_kind: str
    team_id: int | None
    squad_number: int | None
    position_primary: int | None
    nationality: int | None
    birth_day: int | None
    birth_month: int | None
    birth_year: int | None
    height: int | None
    attributes: list[int] = field(default_factory=list)
    container_offset: int | None = None
    container_relative_offset: int | None = None


def _run_pdftotext(pdf_path: Path, layout: bool = False) -> str:
    cmd = ["pdftotext"]
    if layout:
        cmd.append("-layout")
    cmd.extend([str(pdf_path), "-"])
    try:
        return subprocess.check_output(cmd).decode("utf-8", "ignore")
    except FileNotFoundError as exc:
        raise RuntimeError("pdftotext is required but not installed") from exc


def _normalize_spaces(value: str) -> str:
    return " ".join((value or "").split())


def _norm_text(value: str) -> str:
    text = _normalize_spaces(value)
    text = (
        text.replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
        .replace("´", "'")
        .replace("–", "-")
        .replace("—", "-")
    )
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    # collapse punctuation to spaces but keep apostrophes for O'Leary style tokens
    text = re.sub(r"[^A-Za-z0-9' ]+", " ", text)
    return _normalize_spaces(text).upper()


def _last_token_norm(value: str) -> str:
    parts = _norm_text(value).split()
    if not parts:
        return ""
    token = parts[-1]
    token = token.strip("'")
    return token


def _canonical_team_label(value: str) -> str:
    clean = _normalize_spaces(value)
    return PDF_TEAM_LABEL_TO_QUERY.get(clean, clean)


def _nonempty_lines(text: str) -> list[str]:
    return [ln.rstrip("\n") for ln in text.splitlines() if ln.strip()]


def parse_two_column_listing(pdf_path: Path, title: str) -> list[dict[str, Any]]:
    text = _run_pdftotext(pdf_path)
    rows: list[dict[str, Any]] = []
    for page_no, page in enumerate(text.split("\f"), start=1):
        lines = [ln.strip() for ln in page.splitlines()]
        if title not in lines:
            continue

        data_lines: list[str] = []
        started = False
        for ln in lines:
            if ln == "TEAM":
                started = True
                continue
            if not started or not ln:
                continue
            if ln.startswith("Pag.") or ln in {"NAME", "TEAM", title}:
                continue
            if any(ln.startswith(prefix) for prefix in FOOTER_PREFIXES):
                break
            data_lines.append(ln)

        if not data_lines:
            continue
        if len(data_lines) % 2 != 0:
            rows.append(
                {
                    "page": page_no,
                    "error": f"odd data line count: {len(data_lines)}",
                    "data_preview": data_lines[:12],
                }
            )
            continue

        half = len(data_lines) // 2
        for name, team in zip(data_lines[:half], data_lines[half:]):
            rows.append({"page": page_no, "name": name, "team": team})
    return rows


def parse_manager_listing_pdf(pdf_path: Path) -> dict[str, Any]:
    rows = parse_two_column_listing(pdf_path, "LISTING OF ALL MANAGERS")
    clean_rows = [row for row in rows if "error" not in row]
    return {
        "rows": clean_rows,
        "row_count": len(clean_rows),
        "team_count": len({row["team"] for row in clean_rows}),
        "parse_errors": [row for row in rows if "error" in row],
    }


def parse_club_bio_pdf(pdf_path: Path) -> dict[str, Any]:
    layout_text = _run_pdftotext(pdf_path, layout=True)
    clean = [ln.strip() for ln in layout_text.splitlines() if ln.strip()]
    out: dict[str, Any] = {
        "pages": len([p for p in layout_text.split("\f") if p.strip()]),
        "team_label": clean[1] if len(clean) > 1 else "",
    }
    for key in ["NAME", "PRESIDENT", "BUDGET", "MEMBERS", "SPONSOR", "PATRON", "GROUND", "CAPACITY", "SIZE"]:
        m = re.search(rf"\b{re.escape(key)}\b\s+(.+)", layout_text)
        if m:
            out[key.lower()] = _normalize_spaces(m.group(1))
    # The layout prints FOUNDATION twice (club + ground), preserve all occurrences.
    foundations = re.findall(r"\bFOUNDATION\s+(\d{4})", layout_text)
    if foundations:
        out["foundation_values"] = [int(v) for v in foundations]
        out["foundation"] = int(foundations[0])
    m = re.search(r"\bCAPACITY\b\s+([\d,]+)\s+spectators", layout_text, flags=re.IGNORECASE)
    if m:
        out["capacity_int"] = int(m.group(1).replace(",", ""))
    return out


def _first_nonspace_index(line: str) -> int:
    for i, ch in enumerate(line):
        if ch != " ":
            return i
    return len(line)


def parse_squad_card_pdf(pdf_path: Path) -> dict[str, Any]:
    layout_text = _run_pdftotext(pdf_path, layout=True)
    raw_lines = [ln.rstrip("\n") for ln in layout_text.splitlines()]
    useful = [
        ln for ln in raw_lines
        if ln.strip()
        and not ln.strip().startswith("Pag.")
        and not any(ln.strip().startswith(prefix) for prefix in FOOTER_PREFIXES)
    ]
    clean = [ln.strip() for ln in useful]

    out: dict[str, Any] = {
        "pages": len([p for p in layout_text.split("\f") if p.strip()]),
        "team_label": clean[0] if clean else "",
    }

    # Parse manager name by column alignment with the MANAGER heading.
    manager = ""
    manager_idx = None
    manager_col = None
    for idx, line in enumerate(useful):
        if line.strip() == "MANAGER":
            manager_idx = idx
            manager_col = _first_nonspace_index(line)
            break
    if manager_idx is not None and manager_col is not None:
        best_line = None
        best_delta = None
        # Search until the outfield headers begin.
        for line in useful[manager_idx + 1:]:
            stripped = line.strip()
            if not stripped:
                continue
            if "MIDFIELDERS" in line and "FORWARDS" in line:
                break
            if stripped in {"GOALKEEPERS", "THE SQUAD"}:
                continue
            col = _first_nonspace_index(line)
            delta = abs(col - manager_col)
            # Prefer centered line close to the MANAGER column; avoid left-column goalkeeper entries.
            if col < max(0, manager_col - 10):
                continue
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_line = stripped
        if best_line:
            manager = best_line
    out["manager"] = manager

    groups: dict[str, list[str]] = {"GOALKEEPERS": [], "DEFENDERS": [], "MIDFIELDERS": [], "FORWARDS": []}

    # Goalkeepers are in the left column and can straddle the MANAGER heading in this layout.
    try:
        gk_idx = next(i for i, line in enumerate(useful) if line.strip() == "GOALKEEPERS")
        end_idx = next(
            i for i, line in enumerate(useful[gk_idx + 1:], start=gk_idx + 1)
            if "MIDFIELDERS" in line and "FORWARDS" in line
        )
        seen_gk: set[str] = set()
        for line in useful[gk_idx + 1:end_idx]:
            stripped = line.strip()
            if not stripped or stripped in {"THE SQUAD", "MANAGER"}:
                continue
            if manager and stripped == manager:
                continue
            # Left-column only to avoid centered manager text.
            if _first_nonspace_index(line) <= 30 and stripped not in seen_gk:
                seen_gk.add(stripped)
                groups["GOALKEEPERS"].append(stripped)
    except StopIteration:
        pass

    # Parse outfield columns after the MIDFIELDERS/FORWARDS heading line.
    header_idx = None
    for idx, line in enumerate(useful):
        if "MIDFIELDERS" in line and "FORWARDS" in line:
            header_idx = idx
            break
    if header_idx is not None:
        for line in useful[header_idx + 1:]:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in {"DEFENDERS", "MIDFIELDERS", "FORWARDS", "MANAGER"}:
                continue
            cols = [c.strip() for c in re.split(r"\s{2,}", line.rstrip()) if c.strip()]
            if not cols:
                continue
            if len(cols) >= 1:
                groups["DEFENDERS"].append(cols[0])
            if len(cols) >= 2:
                groups["MIDFIELDERS"].append(cols[1])
            if len(cols) >= 3:
                groups["FORWARDS"].append(cols[2])

    out["groups"] = groups
    out["group_counts"] = {k: len(v) for k, v in groups.items()}
    out["squad_total"] = sum(out["group_counts"].values())
    return out


def parse_player_bio_pdf(pdf_path: Path) -> dict[str, Any]:
    layout_text = _run_pdftotext(pdf_path, layout=True)
    pages = [page for page in layout_text.split("\f") if page.strip()]
    page1 = pages[0] if pages else layout_text
    clean = [ln.strip() for ln in page1.splitlines() if ln.strip()]
    out: dict[str, Any] = {
        "pages": len(pages),
        "player_name": clean[1] if len(clean) > 1 else "",
    }
    for key in ["BIRTH PLACE", "BIRTH DATE", "AGE", "CITIZENSHIP", "INTERNATIONAL", "PREVIOUS TEAM"]:
        m = re.search(rf"\b{re.escape(key)}\b\s+(.+)", page1)
        if m:
            out[key.lower().replace(" ", "_")] = _normalize_spaces(m.group(1))
    m = re.search(r"\bHEIGHT\s+(\d+\s+\d+)\s+WEIGHT\s+(\d+\s+\d+)", page1)
    if m:
        out["height_imperial"] = m.group(1)
        out["weight_st_lb"] = m.group(2)
    for role in ["GOALKEEPER", "DEFENDER", "MIDFIELDER", "FORWARD"]:
        if role in page1:
            out["position_label"] = role
            break
    headings: list[str] = []
    for page in pages:
        for heading in [
            "PERSONAL DATA",
            "TECHNICAL CHARACTERISTICS",
            "HONOURS",
            "INTERNATIONAL",
            "ANECDOTES",
            "LAST SEASON",
            "CAREER",
            "NOTES",
        ]:
            if heading in page and heading not in headings:
                headings.append(heading)
    out["section_headings"] = headings

    # Career rows are on page 4 in this sample.
    career_rows: list[dict[str, Any]] = []
    for page in pages:
        if "CAREER" not in page or "SEASON" not in page:
            continue
        for line in [ln.strip() for ln in page.splitlines() if ln.strip()]:
            compact = _normalize_spaces(line)
            m = re.match(r"^(\d{2}-\d{2})\s+(.+?)\s+([1P])\s+(\d+)\s+(\d+)$", compact)
            if not m:
                continue
            career_rows.append(
                {
                    "season": m.group(1),
                    "team": m.group(2),
                    "division": m.group(3),
                    "matches": int(m.group(4)),
                    "goals": int(m.group(5)),
                }
            )
    if career_rows:
        out["career_rows"] = career_rows
    return out


def build_coach_index(coach_file: Path) -> list[CoachIndexRow]:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        valid, _ = gather_coach_records(str(coach_file))
    rows: list[CoachIndexRow] = []
    for entry in valid:
        coach = entry.record
        full_name = _normalize_spaces(
            getattr(coach, "full_name", None)
            or f"{getattr(coach, 'given_name', '')} {getattr(coach, 'surname', '')}"
        )
        given_name = _normalize_spaces(getattr(coach, "given_name", ""))
        surname = _normalize_spaces(getattr(coach, "surname", ""))
        rows.append(
            CoachIndexRow(
                offset=entry.offset,
                full_name=full_name,
                given_name=given_name,
                surname=surname,
                norm_surname=_last_token_norm(surname),
                norm_last_token=_last_token_norm(full_name),
            )
        )
    return rows


def build_team_index(team_file: Path) -> tuple[list[TeamIndexRow], int]:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        valid, uncertain = gather_team_records(str(team_file))
    rows: list[TeamIndexRow] = []
    for entry in valid:
        team = entry.record
        rows.append(
            TeamIndexRow(
                offset=entry.offset,
                team_id=getattr(team, "team_id", None),
                name=_normalize_spaces(getattr(team, "name", "")),
                stadium=_normalize_spaces(getattr(team, "stadium", "")),
                stadium_capacity=getattr(team, "stadium_capacity", None),
                source=entry.source,
            )
        )
    return rows, len(uncertain)


def cross_check_manager_listing(rows: list[dict[str, Any]], coaches: list[CoachIndexRow]) -> dict[str, Any]:
    exact_surname_map: dict[str, dict[int, CoachIndexRow]] = defaultdict(dict)
    norm_last_token_map: dict[str, dict[int, CoachIndexRow]] = defaultdict(dict)
    for coach in coaches:
        if coach.surname:
            exact_surname_map[coach.surname.lower()][coach.offset] = coach
        if coach.norm_last_token:
            norm_last_token_map[coach.norm_last_token][coach.offset] = coach
        if coach.norm_surname:
            norm_last_token_map[coach.norm_surname][coach.offset] = coach

    exact_hits = 0
    normalized_hits = 0
    exact_multi = 0
    normalized_multi = 0
    misses_after_normalized: list[dict[str, Any]] = []

    for row in rows:
        label = _normalize_spaces(row.get("name", ""))
        exact_candidates = list(exact_surname_map.get(label.lower(), {}).values()) if label else []
        if exact_candidates:
            exact_hits += 1
            if len(exact_candidates) > 1:
                exact_multi += 1
        norm_key = _last_token_norm(label)
        norm_candidates = list(norm_last_token_map.get(norm_key, {}).values()) if norm_key else []
        if norm_candidates:
            normalized_hits += 1
            if len(norm_candidates) > 1:
                normalized_multi += 1
        else:
            misses_after_normalized.append(row)

    return {
        "exact_surname": {
            "matched": exact_hits,
            "multi_candidate": exact_multi,
            "misses": max(0, len(rows) - exact_hits),
        },
        "normalized_last_token": {
            "matched": normalized_hits,
            "multi_candidate": normalized_multi,
            "misses": max(0, len(rows) - normalized_hits),
            "miss_examples": misses_after_normalized[:10],
        },
    }


def cross_check_club_bio(doc: dict[str, Any], teams: list[TeamIndexRow]) -> dict[str, Any]:
    team_label = doc.get("team_label", "")
    club_name = doc.get("name", "")
    ground = doc.get("ground", "")
    capacity = doc.get("capacity_int")

    canonical_from_label = _canonical_team_label(team_label)
    club_name_norm = _norm_text(club_name)
    canonical_label_norm = _norm_text(canonical_from_label)
    ground_norm = _norm_text(ground)

    name_exact = [t for t in teams if t.name.lower() == club_name.lower()]
    name_norm_contains = [
        t for t in teams
        if club_name_norm and (club_name_norm in _norm_text(t.name) or _norm_text(t.name) in club_name_norm)
    ]
    label_norm_contains = [
        t for t in teams
        if canonical_label_norm and (canonical_label_norm in _norm_text(t.name) or _norm_text(t.name) in canonical_label_norm)
    ]
    ground_contains = [
        t for t in teams
        if ground_norm and ground_norm and ground_norm in _norm_text(t.stadium)
    ]
    capacity_matches = [
        t for t in teams
        if capacity is not None and t.stadium_capacity == capacity
    ]

    def _pack(rows: list[TeamIndexRow]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in rows[:5]:
            out.append(asdict(row))
        return out

    return {
        "canonical_team_from_label": canonical_from_label,
        "team_db_matches": {
            "name_exact": _pack(name_exact),
            "name_norm_contains": _pack(name_norm_contains),
            "label_norm_contains": _pack(label_norm_contains),
            "ground_contains": _pack(ground_contains),
            "capacity_exact": _pack(capacity_matches),
        },
    }


def _flatten_squad_names(groups: dict[str, list[str]]) -> list[str]:
    names: list[str] = []
    for key in ["GOALKEEPERS", "DEFENDERS", "MIDFIELDERS", "FORWARDS"]:
        names.extend(groups.get(key, []))
    return names


def cross_check_squad_card(
    doc: dict[str, Any],
    player_listing_by_team: dict[str, list[str]],
    manager_listing_by_team: dict[str, list[str]],
    coaches: list[CoachIndexRow],
) -> dict[str, Any]:
    team_label = _normalize_spaces(doc.get("team_label", ""))
    canonical = _canonical_team_label(team_label)
    groups = doc.get("groups") or {}
    squad_names = _flatten_squad_names(groups)

    # Compare squad surnames against same-team player listings (surname/label match).
    candidate_listing_names = player_listing_by_team.get(team_label) or player_listing_by_team.get(canonical) or []
    candidate_listing_norms = {_last_token_norm(name): name for name in candidate_listing_names}
    squad_norms = [_last_token_norm(name) for name in squad_names]
    squad_matched = []
    squad_missing = []
    for original, norm in zip(squad_names, squad_norms):
        if norm and norm in candidate_listing_norms:
            squad_matched.append({"squad_name": original, "listing_name": candidate_listing_norms[norm]})
        else:
            squad_missing.append(original)

    listing_names_set = {_last_token_norm(name) for name in candidate_listing_names}
    extra_listing_names = [
        name for name in candidate_listing_names
        if _last_token_norm(name) and _last_token_norm(name) not in set(squad_norms)
    ]

    # Manager cross-check: squad-card manager full name vs listing/coach DB.
    manager_label = _normalize_spaces(doc.get("manager", ""))
    manager_norm_last = _last_token_norm(manager_label)
    coach_matches = [
        asdict(coach)
        for coach in coaches
        if manager_norm_last and coach.norm_last_token == manager_norm_last
    ][:5]
    listing_manager_labels = manager_listing_by_team.get(team_label) or manager_listing_by_team.get(canonical) or []
    listing_manager_matches = [
        label for label in listing_manager_labels if _last_token_norm(label) == manager_norm_last
    ]

    return {
        "canonical_team_from_label": canonical,
        "player_listing_same_team_count": len(candidate_listing_names),
        "squad_vs_listing": {
            "squad_total": len(squad_names),
            "matched_by_surname": len(squad_matched),
            "missing_from_listing": squad_missing,
            "matched_examples": squad_matched[:10],
            "listing_extra_count": len(extra_listing_names),
            "listing_extra_examples": extra_listing_names[:10],
        },
        "manager_checks": {
            "manager_label": manager_label,
            "manager_last_token": manager_norm_last,
            "manager_listing_same_team": listing_manager_labels,
            "manager_listing_match_by_surname": listing_manager_matches,
            "coach_db_matches_by_last_token": coach_matches,
        },
        "listing_last_token_coverage": len(listing_names_set),
    }


def _coach_row_payload(coach: CoachIndexRow) -> dict[str, Any]:
    return asdict(coach)


def _coach_matches_for_manager_label(label: str, coaches: list[CoachIndexRow]) -> dict[str, Any]:
    clean = _normalize_spaces(label)
    if not clean:
        return {
            "manager_label": "",
            "exact_full_name_matches": [],
            "surname_matches": [],
        }

    label_norm = _norm_text(clean)
    label_last = _last_token_norm(clean)
    exact_full = [
        _coach_row_payload(c)
        for c in coaches
        if _norm_text(c.full_name) == label_norm
    ]
    surname_matches = [
        _coach_row_payload(c)
        for c in coaches
        if label_last and c.norm_last_token == label_last
    ]
    return {
        "manager_label": clean,
        "manager_last_token": label_last,
        "exact_full_name_matches": exact_full[:8],
        "surname_matches": surname_matches[:8],
        "surname_match_count": len(surname_matches),
    }


def _guess_canonical_team_from_fragment(fragment: str, team_packets: dict[str, dict[str, Any]]) -> str | None:
    norm = _norm_text(fragment)
    if not norm:
        return None
    # Prefer seed teams first.
    for canonical in sorted(team_packets.keys()):
        canon_norm = _norm_text(canonical)
        if not canon_norm:
            continue
        if norm == canon_norm or norm in canon_norm or canon_norm in norm:
            return canonical
    # Fallback to global PDF alias map values.
    for canonical in sorted(set(PDF_TEAM_LABEL_TO_QUERY.values())):
        canon_norm = _norm_text(canonical)
        if not canon_norm:
            continue
        if norm == canon_norm or norm in canon_norm or canon_norm in norm:
            return canonical
    return None


def build_team_packets(
    docs: list[dict[str, Any]],
    player_listing_rows_by_doc: dict[str, list[dict[str, Any]]],
    manager_listing_rows_by_doc: dict[str, list[dict[str, Any]]],
    coaches: list[CoachIndexRow],
) -> list[dict[str, Any]]:
    packets: dict[str, dict[str, Any]] = {}

    def _ensure(canonical: str) -> dict[str, Any]:
        key = _normalize_spaces(canonical)
        if key not in packets:
            packets[key] = {
                "canonical_team": key,
                "seen_labels": set(),
                "player_listings": {},
                "manager_listings": {},
                "club_bios": [],
                "squad_cards": [],
                "player_bios": [],
            }
        return packets[key]

    # Player listings
    for pdf_name, rows in player_listing_rows_by_doc.items():
        for row in rows:
            team_label = _normalize_spaces(row.get("team", ""))
            canonical = _canonical_team_label(team_label)
            packet = _ensure(canonical)
            if team_label:
                packet["seen_labels"].add(team_label)
            bucket = packet["player_listings"].setdefault(
                pdf_name,
                {
                    "team_label": team_label,
                    "row_count": 0,
                    "player_names": [],
                },
            )
            bucket["row_count"] += 1
            bucket["player_names"].append(_normalize_spaces(row.get("name", "")))

    # Manager listings
    for pdf_name, rows in manager_listing_rows_by_doc.items():
        for row in rows:
            team_label = _normalize_spaces(row.get("team", ""))
            canonical = _canonical_team_label(team_label)
            packet = _ensure(canonical)
            if team_label:
                packet["seen_labels"].add(team_label)
            packet["manager_listings"].setdefault(
                pdf_name,
                {
                    "team_label": team_label,
                    "manager_labels": [],
                },
            )["manager_labels"].append(_normalize_spaces(row.get("name", "")))

    # Club bios, squad cards, player bios (from final parsed docs)
    for doc in docs:
        if doc.get("doc_type") == "club_bio":
            canonical = _normalize_spaces(
                doc.get("canonical_team_from_label") or _canonical_team_label(doc.get("team_label", ""))
            )
            if not canonical:
                continue
            packet = _ensure(canonical)
            if doc.get("team_label"):
                packet["seen_labels"].add(_normalize_spaces(doc.get("team_label", "")))
            packet["club_bios"].append(
                {
                    "pdf": doc.get("pdf"),
                    "team_label": doc.get("team_label"),
                    "name": doc.get("name"),
                    "ground": doc.get("ground"),
                    "capacity_int": doc.get("capacity_int"),
                    "size": doc.get("size"),
                    "foundation_values": doc.get("foundation_values"),
                    "team_db_matches": doc.get("team_db_matches"),
                }
            )
        elif doc.get("doc_type") == "squad_card":
            canonical = _normalize_spaces(
                doc.get("canonical_team_from_label") or _canonical_team_label(doc.get("team_label", ""))
            )
            if not canonical:
                continue
            packet = _ensure(canonical)
            if doc.get("team_label"):
                packet["seen_labels"].add(_normalize_spaces(doc.get("team_label", "")))
            packet["squad_cards"].append(
                {
                    "pdf": doc.get("pdf"),
                    "team_label": doc.get("team_label"),
                    "manager": doc.get("manager"),
                    "group_counts": doc.get("group_counts"),
                    "squad_total": doc.get("squad_total"),
                    "squad_vs_listing": doc.get("squad_vs_listing"),
                    "manager_checks": doc.get("manager_checks"),
                }
            )
        elif doc.get("doc_type") == "player_bio":
            # Try to associate to a seed team using the most recent career row.
            career_rows = doc.get("career_rows") or []
            current_team_fragment = career_rows[-1]["team"] if career_rows else None
            inferred_canonical = _guess_canonical_team_from_fragment(current_team_fragment or "", packets)
            payload = {
                "pdf": doc.get("pdf"),
                "player_name": doc.get("player_name"),
                "position_label": doc.get("position_label"),
                "birth_date": doc.get("birth_date"),
                "citizenship": doc.get("citizenship"),
                "previous_team": doc.get("previous_team"),
                "latest_career_team_fragment": current_team_fragment,
                "inferred_current_team": inferred_canonical,
                "pages": doc.get("pages"),
            }
            if inferred_canonical:
                _ensure(inferred_canonical)["player_bios"].append(payload)

    # Finalize packet stats / consistency flags.
    final_packets: list[dict[str, Any]] = []
    for canonical in sorted(packets.keys()):
        packet = packets[canonical]
        player_listing_total = sum(
            int(bucket.get("row_count", 0))
            for bucket in packet["player_listings"].values()
        )
        manager_labels: list[str] = []
        for bucket in packet["manager_listings"].values():
            manager_labels.extend([_normalize_spaces(v) for v in bucket.get("manager_labels", []) if _normalize_spaces(v)])
        seen_mgr = []
        seen_keys = set()
        for label in manager_labels:
            key = _norm_text(label)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            seen_mgr.append(label)
        manager_matches = [_coach_matches_for_manager_label(label, coaches) for label in seen_mgr]

        squad_totals = [card.get("squad_total") for card in packet["squad_cards"] if isinstance(card.get("squad_total"), int)]
        squad_total = squad_totals[0] if squad_totals else None
        listing_matches_squad = bool(
            squad_total is not None
            and player_listing_total > 0
            and any(card.get("squad_vs_listing", {}).get("matched_by_surname") == squad_total for card in packet["squad_cards"])
        )

        club_bio_count = len(packet["club_bios"])
        squad_card_count = len(packet["squad_cards"])
        manager_listing_count = len(packet["manager_listings"])
        player_listing_count = len(packet["player_listings"])
        player_bio_count = len(packet["player_bios"])
        packet_payload = {
            "canonical_team": canonical,
            "seen_labels": sorted(packet["seen_labels"]),
            "player_listing_total": player_listing_total,
            "player_listings": packet["player_listings"],
            "manager_listings": packet["manager_listings"],
            "manager_coach_db_candidates": manager_matches,
            "club_bios": packet["club_bios"],
            "squad_cards": packet["squad_cards"],
            "player_bios": packet["player_bios"],
            "evidence_counts": {
                "player_listing_docs": player_listing_count,
                "manager_listing_docs": manager_listing_count,
                "club_bio_docs": club_bio_count,
                "squad_card_docs": squad_card_count,
                "player_bio_docs": player_bio_count,
            },
            "completeness_flags": {
                "has_player_listing": player_listing_count > 0,
                "has_manager_listing": manager_listing_count > 0,
                "has_club_bio": club_bio_count > 0,
                "has_squad_card": squad_card_count > 0,
                "has_player_bio": player_bio_count > 0,
                "squad_listing_full_overlap": listing_matches_squad,
            },
            "evidence_score": (
                (2 if player_listing_count > 0 else 0)
                + (2 if manager_listing_count > 0 else 0)
                + (2 if club_bio_count > 0 else 0)
                + (2 if squad_card_count > 0 else 0)
                + (1 if player_bio_count > 0 else 0)
                + (1 if listing_matches_squad else 0)
            ),
        }
        final_packets.append(packet_payload)

    final_packets.sort(key=lambda p: (-int(p.get("evidence_score", 0)), p.get("canonical_team", "")))
    return final_packets


def _record_name(record: PlayerRecord) -> str:
    return _normalize_spaces(getattr(record, "name", "") or f"{getattr(record, 'given_name', '')} {getattr(record, 'surname', '')}")


def _name_match_kind(query: str, candidate_name: str) -> str:
    q_norm = _norm_text(query)
    c_norm = _norm_text(candidate_name)
    if not q_norm or not c_norm:
        return "none"
    if q_norm == c_norm:
        return "exact_norm"
    q_parts = q_norm.split()
    c_parts = c_norm.split()
    if q_parts and c_parts and q_parts[0] == c_parts[0] and q_parts[-1] == c_parts[-1]:
        return "first_last_match"
    if q_parts and c_parts and q_parts[-1] == c_parts[-1]:
        return "surname_match"
    if c_norm in q_norm or q_norm in c_norm:
        return "contains"
    return "none"


def strict_player_probe(player_file: Path, query: str, max_results: int = 8) -> dict[str, Any]:
    data = player_file.read_bytes()
    results: list[StrictPlayerProbeRow] = []
    seen_offsets: set[int] = set()

    def _consider(record: PlayerRecord, offset: int, source: str, container_offset: int | None = None, container_rel: int | None = None) -> None:
        nonlocal results
        if offset in seen_offsets:
            return
        seen_offsets.add(offset)
        name = _record_name(record)
        if name in {"", "Unknown Player", "Parse Error"}:
            return
        match_kind = _name_match_kind(query, name)
        if match_kind == "none":
            return
        results.append(
            StrictPlayerProbeRow(
                source=source,
                offset=offset,
                name=name,
                match_kind=match_kind,
                team_id=getattr(record, "team_id", None),
                squad_number=getattr(record, "squad_number", None),
                position_primary=getattr(record, "position_primary", None),
                nationality=getattr(record, "nationality", None),
                birth_day=getattr(record, "birth_day", None),
                birth_month=getattr(record, "birth_month", None),
                birth_year=getattr(record, "birth_year", None),
                height=getattr(record, "height", None),
                attributes=list(getattr(record, "attributes", [])[:12]),
                container_offset=container_offset,
                container_relative_offset=container_rel,
            )
        )

    offset = 0x400
    data_len = len(data)
    scanned_entries = 0
    while offset + 2 <= data_len:
        length = int.from_bytes(data[offset:offset + 2], "little")
        if length <= 0 or offset + 2 + length > data_len:
            offset += 1
            continue

        try:
            if 40 <= length <= 1024:
                decoded, _ = decode_entry(data, offset)
                record = PlayerRecord.from_bytes(decoded, offset)
                _consider(record, offset, "entry (strict)")
            elif 1024 < length <= 200000:
                decoded, _ = decode_entry(data, offset)
                if _PLAYER_SUBRECORD_SEPARATOR in decoded:
                    starts: list[int] = []
                    pos = decoded.find(_PLAYER_SUBRECORD_SEPARATOR)
                    while pos != -1:
                        starts.append(pos)
                        pos = decoded.find(_PLAYER_SUBRECORD_SEPARATOR, pos + 1)
                    for idx, start in enumerate(starts):
                        end = starts[idx + 1] if idx + 1 < len(starts) else len(decoded)
                        segment = decoded[start:end]
                        if not (50 <= len(segment) <= 256):
                            continue
                        try:
                            subrecord = PlayerRecord.from_bytes(segment, offset + 2 + start)
                        except Exception:
                            continue
                        _consider(
                            subrecord,
                            offset + 2 + start,
                            "entry-subrecord (strict)",
                            container_offset=offset,
                            container_rel=start,
                        )
        except Exception:
            pass

        scanned_entries += 1
        if len(results) >= max_results:
            break
        offset += length + 2

    # Prefer strongest matches first.
    kind_order = {"exact_norm": 0, "first_last_match": 1, "surname_match": 2, "contains": 3}
    results.sort(key=lambda r: (kind_order.get(r.match_kind, 9), r.offset))
    return {
        "query": query,
        "scanned_entries": scanned_entries,
        "matches": [asdict(row) for row in results[:max_results]],
    }


def _club_mention_terms() -> list[str]:
    terms = set(PDF_TEAM_LABEL_TO_QUERY.keys()) | set(PDF_TEAM_LABEL_TO_QUERY.values())
    # Include common expanded forms seen in bios/listings.
    extra = {
        "Manchester United",
        "Manchester Utd",
        "Manchester U",
        "Stoke City",
        "Stoke C.",
        "Stoke",
    }
    terms |= extra
    # Longest-first helps avoid short-token spam dominating snippets.
    return sorted({_normalize_spaces(t) for t in terms if _normalize_spaces(t)}, key=lambda s: (-len(s), s))


def _nearby_club_mentions_simple(text: str, center: int, window: int = 800, limit: int = 12) -> list[dict[str, Any]]:
    if not text:
        return []
    start = max(0, center - max(1, window))
    end = min(len(text), center + max(1, window))
    segment = text[start:end]
    lower_segment = segment.lower()
    seen: set[tuple[int, str]] = set()
    hits: list[dict[str, Any]] = []
    for term in _club_mention_terms():
        lower_term = term.lower()
        pos = lower_segment.find(lower_term)
        while pos != -1:
            abs_idx = start + pos
            key = (abs_idx, lower_term)
            if key not in seen:
                seen.add(key)
                distance = abs((abs_idx + len(term) // 2) - center)
                hits.append(
                    {
                        "text": term,
                        "index": abs_idx,
                        "distance": distance,
                    }
                )
            pos = lower_segment.find(lower_term, pos + 1)
    hits.sort(key=lambda item: (int(item["distance"]), int(item["index"]), item["text"]))
    return hits[:limit]


def decoded_text_probe(
    player_file: Path,
    query: str,
    *,
    max_results: int = 8,
    snippet_chars: int = 160,
    club_window: int = 1000,
) -> dict[str, Any]:
    """Search decoded FDI entries for a raw text query (no parser record required)."""
    file_bytes = player_file.read_bytes()
    query_clean = _normalize_spaces(query)
    query_lower = query_clean.lower()
    if not query_clean:
        return {"query": query, "scanned_entries": 0, "matches": []}

    matches: list[dict[str, Any]] = []
    offset = 0x400
    data_len = len(file_bytes)
    scanned_entries = 0
    while offset + 2 <= data_len:
        length = int.from_bytes(file_bytes[offset:offset + 2], "little")
        if length <= 0 or offset + 2 + length > data_len:
            offset += 1
            continue
        try:
            decoded, enc_len = decode_entry(file_bytes, offset)
        except Exception:
            offset += 1
            continue

        scanned_entries += 1
        try:
            text = decoded.decode("latin-1", errors="ignore")
        except Exception:
            text = ""
        lower = text.lower()
        first_idx = lower.find(query_lower)
        if first_idx != -1:
            count = lower.count(query_lower)
            snippet_start = max(0, first_idx - snippet_chars)
            snippet_end = min(len(text), first_idx + len(query_clean) + snippet_chars)
            snippet = text[snippet_start:snippet_end]
            matches.append(
                {
                    "entry_offset": offset,
                    "entry_length": enc_len,
                    "match_count_in_entry": count,
                    "first_match_index": first_idx,
                    "snippet": _normalize_spaces(snippet),
                    "nearby_club_mentions": _nearby_club_mentions_simple(text, first_idx, window=club_window, limit=16),
                }
            )
            if len(matches) >= max_results:
                break
        offset += length + 2

    return {
        "query": query_clean,
        "scanned_entries": scanned_entries,
        "matches": matches,
    }


_BIO_MARKER = bytes([0xDD, 0x63, 0x61])
_BIO_FULL_NAME_RE = re.compile(
    r"([A-Z][a-z'\-]+(?:\s+\([^)]+\))?(?:\s+[A-Z][a-z'\-]+){0,4}\s+[A-Z][A-Z'\-]{2,}(?:\s+[A-Z][A-Z'\-]{2,}){0,2})"
)


def _extract_bio_marker_name(segment: bytes) -> dict[str, Any] | None:
    text = segment.decode("latin-1", errors="ignore")
    head = text[:240]
    matches = list(_BIO_FULL_NAME_RE.finditer(head))
    if not matches:
        return None
    # Prefer the last titlecase+UPPERCASE name near the marker start (skips prefix glue like UlqdaKeanepa)
    m = matches[-1]
    full_name = _normalize_spaces(m.group(1))
    if not full_name:
        return None
    return {
        "full_name": full_name,
        "match_start": m.start(),
        "match_end": m.end(),
        "head_preview": _normalize_spaces(head[max(0, m.start() - 32):min(len(head), m.end() + 96)]),
    }


def bio_marker_probe(
    player_file: Path,
    query: str,
    *,
    max_results: int = 12,
    club_window: int = 1000,
) -> dict[str, Any]:
    """Probe dd6361-marked biography subrecords and extract full names."""
    file_bytes = player_file.read_bytes()
    query_norm = _norm_text(query)
    query_last = _last_token_norm(query)
    query_has_space = len(query_norm.split()) > 1
    matches: list[dict[str, Any]] = []
    scanned_entries = 0
    marker_count = 0

    offset = 0x400
    data_len = len(file_bytes)
    while offset + 2 <= data_len:
        length = int.from_bytes(file_bytes[offset:offset + 2], "little")
        if length <= 0 or offset + 2 + length > data_len:
            offset += 1
            continue
        try:
            decoded, enc_len = decode_entry(file_bytes, offset)
        except Exception:
            offset += 1
            continue

        scanned_entries += 1
        pos = decoded.find(_BIO_MARKER)
        while pos != -1:
            marker_count += 1
            segment = decoded[pos: min(len(decoded), pos + 512)]
            extracted = _extract_bio_marker_name(segment)
            if extracted:
                full_name = extracted["full_name"]
                name_norm = _norm_text(full_name)
                name_last = _last_token_norm(full_name)
                is_match = False
                match_mode = None
                if query_norm and query_norm in name_norm:
                    is_match = True
                    match_mode = "contains"
                elif (not query_has_space) and query_last and name_last == query_last:
                    is_match = True
                    match_mode = "surname"

                if is_match:
                    # use the full decoded text for nearby club mentions around the extracted match start
                    center = pos + int(extracted["match_start"])
                    text = decoded.decode("latin-1", errors="ignore")
                    matches.append(
                        {
                            "entry_offset": offset,
                            "entry_length": enc_len,
                            "marker_offset_in_entry": pos,
                            "name": full_name,
                            "query_match_mode": match_mode or "contains",
                            "head_preview": extracted["head_preview"],
                            "nearby_club_mentions": _nearby_club_mentions_simple(text, center, window=club_window, limit=16),
                        }
                    )
                    if len(matches) >= max_results:
                        return {
                            "query": query,
                            "scanned_entries": scanned_entries,
                            "bio_marker_count_scanned": marker_count,
                            "matches": matches,
                        }

            pos = decoded.find(_BIO_MARKER, pos + 1)

        offset += length + 2

    return {
        "query": query,
        "scanned_entries": scanned_entries,
        "bio_marker_count_scanned": marker_count,
        "matches": matches,
    }


def probe_seed_player_bios(
    summary: dict[str, Any],
    player_file: Path,
    *,
    strict_max: int = 8,
    text_max: int = 6,
    bio_marker_max: int = 8,
) -> list[dict[str, Any]]:
    docs = summary.get("documents", []) or []
    team_packets = summary.get("team_packets", []) or []
    team_packet_map = {p.get("canonical_team"): p for p in team_packets if p.get("canonical_team")}
    results: list[dict[str, Any]] = []

    for doc in docs:
        if doc.get("doc_type") != "player_bio":
            continue
        full_name = _normalize_spaces(doc.get("player_name", ""))
        if not full_name:
            continue
        parts = full_name.split()
        first_last = ""
        if len(parts) >= 2:
            first_last = f"{parts[0]} {parts[-1]}"
        surname = parts[-1] if parts else ""

        # Infer team from career row fragment and cross-check with team packets.
        inferred_team = None
        career_rows = doc.get("career_rows") or []
        if career_rows:
            inferred_team = _guess_canonical_team_from_fragment(career_rows[-1].get("team", ""), {k: {} for k in team_packet_map.keys()})

        strict_queries = []
        for q in [full_name, first_last]:
            q = _normalize_spaces(q)
            if q and q not in strict_queries:
                strict_queries.append(q)
        strict_results = [strict_player_probe(player_file, q, max_results=strict_max) for q in strict_queries]

        text_queries = []
        for q in [full_name, first_last]:
            q = _normalize_spaces(q)
            if q and q not in text_queries:
                text_queries.append(q)
        text_results = [decoded_text_probe(player_file, q, max_results=text_max) for q in text_queries]

        bio_queries = []
        for q in [full_name, first_last, surname]:
            q = _normalize_spaces(q)
            if q and q not in bio_queries:
                bio_queries.append(q)
        bio_results = [bio_marker_probe(player_file, q, max_results=bio_marker_max) for q in bio_queries]

        strict_exact_like_hit = False
        strict_hits_summary: list[dict[str, Any]] = []
        for probe in strict_results:
            probe_summary = {
                "query": probe.get("query"),
                "match_count": len(probe.get("matches", [])),
                "match_kinds": Counter(m.get("match_kind") for m in probe.get("matches", [])),
                "names": [m.get("name") for m in probe.get("matches", [])],
            }
            if any(m.get("match_kind") in {"exact_norm", "first_last_match"} for m in probe.get("matches", [])):
                strict_exact_like_hit = True
            # Convert Counter for JSON stability.
            probe_summary["match_kinds"] = dict(probe_summary["match_kinds"])
            strict_hits_summary.append(probe_summary)

        bio_marker_exact_full_hit = False
        full_name_norm = _norm_text(full_name)
        first_last_norm = _norm_text(first_last)
        bio_marker_names_seen: list[str] = []
        for probe in bio_results:
            for match in probe.get("matches", []):
                name = _normalize_spaces(match.get("name", ""))
                if not name:
                    continue
                bio_marker_names_seen.append(name)
                name_norm = _norm_text(name)
                if full_name_norm and full_name_norm in name_norm:
                    bio_marker_exact_full_hit = True

        inferred_team_norm = _norm_text(inferred_team or "")
        inferred_team_hit = False
        inferred_team_hit_details: list[str] = []
        for probe in text_results:
            for match in probe.get("matches", []):
                for mention in match.get("nearby_club_mentions", []):
                    m_norm = _norm_text(mention.get("text", ""))
                    if inferred_team_norm and (inferred_team_norm in m_norm or m_norm in inferred_team_norm):
                        inferred_team_hit = True
                        inferred_team_hit_details.append(mention.get("text", ""))
        for probe in bio_results:
            for match in probe.get("matches", []):
                for mention in match.get("nearby_club_mentions", []):
                    m_norm = _norm_text(mention.get("text", ""))
                    if inferred_team_norm and (inferred_team_norm in m_norm or m_norm in inferred_team_norm):
                        inferred_team_hit = True
                        inferred_team_hit_details.append(mention.get("text", ""))

        results.append(
            {
                "pdf": doc.get("pdf"),
                "player_name": full_name,
                "first_last_query": first_last,
                "surname_query": surname,
                "position_label": doc.get("position_label"),
                "birth_date": doc.get("birth_date"),
                "citizenship": doc.get("citizenship"),
                "previous_team": doc.get("previous_team"),
                "latest_career_team_fragment": career_rows[-1].get("team") if career_rows else None,
                "inferred_team": inferred_team,
                "inferred_team_in_seed_packets": inferred_team in team_packet_map if inferred_team else False,
                "strict_player_probes": strict_results,
                "strict_probe_hit_summaries": strict_hits_summary,
                "strict_exact_like_hit": strict_exact_like_hit,
                "decoded_text_probes": text_results,
                "bio_marker_probes": bio_results,
                "bio_marker_names_seen": sorted(set(bio_marker_names_seen)),
                "bio_marker_full_name_hit": bio_marker_exact_full_hit,
                "inferred_team_mention_hit": inferred_team_hit,
                "inferred_team_mention_examples": sorted(set([v for v in inferred_team_hit_details if v]))[:12],
            }
        )
    return results


def build_document_summary(
    pdf_dir: Path,
    coaches: list[CoachIndexRow],
    teams: list[TeamIndexRow],
    team_uncertain_count: int,
) -> dict[str, Any]:
    player_listing_by_team: dict[str, list[str]] = defaultdict(list)
    manager_listing_by_team: dict[str, list[str]] = defaultdict(list)
    player_listing_rows_by_doc: dict[str, list[dict[str, Any]]] = {}
    manager_listing_rows_by_doc: dict[str, list[dict[str, Any]]] = {}
    docs: list[dict[str, Any]] = []

    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        default_text = _run_pdftotext(pdf_path)
        doc: dict[str, Any] = {
            "pdf": pdf_path.name,
            "pages_est": len([p for p in default_text.split("\f") if p.strip()]),
        }

        if "LISTING OF ALL PALYERS" in default_text:
            rows = parse_listing_pdf(str(pdf_path))
            player_listing_rows_by_doc[pdf_path.name] = [
                {"page": row.page, "name": row.name_label, "team": row.team_label}
                for row in rows
            ]
            doc["doc_type"] = "player_listing"
            doc["row_count"] = len(rows)
            doc["team_count"] = len({row.team_label for row in rows})
            doc["sample_rows"] = [
                {"page": row.page, "name": row.name_label, "team": row.team_label}
                for row in rows[:8]
            ]
            team_counts = Counter(row.team_label for row in rows)
            doc["top_team_counts"] = dict(team_counts.most_common(5))
            for row in rows:
                player_listing_by_team[row.team_label].append(row.name_label)
                canonical = _canonical_team_label(row.team_label)
                if canonical != row.team_label:
                    player_listing_by_team[canonical].append(row.name_label)

        elif "LISTING OF ALL MANAGERS" in default_text:
            parsed = parse_manager_listing_pdf(pdf_path)
            rows = parsed["rows"]
            manager_listing_rows_by_doc[pdf_path.name] = [dict(row) for row in rows]
            doc["doc_type"] = "manager_listing"
            doc["row_count"] = parsed["row_count"]
            doc["team_count"] = parsed["team_count"]
            doc["sample_rows"] = rows[:8]
            if parsed["parse_errors"]:
                doc["parse_errors"] = parsed["parse_errors"]
            doc["coach_cross_check"] = cross_check_manager_listing(rows, coaches)
            for row in rows:
                manager_listing_by_team[row["team"]].append(row["name"])
                canonical = _canonical_team_label(row["team"])
                if canonical != row["team"]:
                    manager_listing_by_team[canonical].append(row["name"])

        elif "PERSONAL DATA" in default_text and "TECHNICAL CHARACTERISTICS" in default_text:
            doc["doc_type"] = "player_bio"
            doc.update(parse_player_bio_pdf(pdf_path))

        elif "PRESIDENT" in default_text and "GROUND" in default_text:
            doc["doc_type"] = "club_bio"
            doc.update(parse_club_bio_pdf(pdf_path))
            doc.update(cross_check_club_bio(doc, teams))

        elif "THE SQUAD" in default_text and "MANAGER" in default_text:
            doc["doc_type"] = "squad_card"
            doc.update(parse_squad_card_pdf(pdf_path))
            # Cross-doc checks happen after listings have potentially been loaded; still useful even if this file is encountered first.
            doc["_needs_post_cross_check"] = True

        else:
            doc["doc_type"] = "unknown"
            doc["head_preview"] = _nonempty_lines(default_text)[:12]

        docs.append(doc)

    # Post-pass squad card cross-checks (requires listing indexes built from other docs).
    for doc in docs:
        if doc.get("doc_type") != "squad_card":
            continue
        doc.update(
            cross_check_squad_card(
                doc,
                player_listing_by_team=player_listing_by_team,
                manager_listing_by_team=manager_listing_by_team,
                coaches=coaches,
            )
        )
        doc.pop("_needs_post_cross_check", None)

    team_packets = build_team_packets(
        docs=docs,
        player_listing_rows_by_doc=player_listing_rows_by_doc,
        manager_listing_rows_by_doc=manager_listing_rows_by_doc,
        coaches=coaches,
    )

    return {
        "pdf_dir": str(pdf_dir),
        "db_counts": {
            "coaches": len(coaches),
            "teams_valid": len(teams),
            "teams_uncertain": team_uncertain_count,
        },
        "documents": docs,
        "team_packets": team_packets,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Probe PM99 seed PDFs and emit structured summary JSON")
    p.add_argument("--pdf-dir", default=str(REPO_ROOT / ".local" / "PM99RE-demo-pdfs"), help="Directory containing seed PDFs")
    p.add_argument("--coach-file", default=str(REPO_ROOT / "DBDAT" / "ENT98030.FDI"), help="Coach FDI path (optional if missing)")
    p.add_argument("--team-file", default=str(REPO_ROOT / "DBDAT" / "EQ98030.FDI"), help="Team FDI path (optional if missing)")
    p.add_argument("--player-file", default=str(REPO_ROOT / "DBDAT" / "JUG98030.FDI"), help="Player FDI path (used for --probe-player)")
    p.add_argument("--probe-player", action="append", default=[], help="Targeted strict player probe query (repeatable)")
    p.add_argument("--max-probe-results", type=int, default=8, help="Max rows returned per --probe-player query")
    p.add_argument("--probe-text-query", action="append", default=[], help="Targeted raw decoded-text probe query (repeatable)")
    p.add_argument("--max-text-probe-results", type=int, default=8, help="Max rows returned per --probe-text-query")
    p.add_argument("--probe-bio-marker", action="append", default=[], help="Targeted dd6361 bio-marker subrecord name probe (repeatable)")
    p.add_argument("--max-bio-marker-results", type=int, default=12, help="Max rows returned per --probe-bio-marker")
    p.add_argument("--probe-seed-player-bios", action="store_true", help="Run strict/text/bio-marker linkage probes for parsed player-bio PDFs")
    p.add_argument("--json-output", help="Write JSON summary to this file")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.exists() or not pdf_dir.is_dir():
        print(json.dumps({"error": f"PDF directory not found: {pdf_dir}"}, indent=2))
        return 2

    coaches: list[CoachIndexRow] = []
    teams: list[TeamIndexRow] = []
    team_uncertain_count = 0

    coach_file = Path(args.coach_file)
    if coach_file.exists():
        coaches = build_coach_index(coach_file)

    team_file = Path(args.team_file)
    if team_file.exists():
        teams, team_uncertain_count = build_team_index(team_file)

    summary = build_document_summary(pdf_dir, coaches, teams, team_uncertain_count)

    if args.probe_player:
        player_file = Path(args.player_file)
        probes: list[dict[str, Any]] = []
        if player_file.exists():
            for query in args.probe_player:
                probes.append(strict_player_probe(player_file, query, max_results=args.max_probe_results))
        else:
            probes.append({"error": f"Player file not found: {player_file}"})
        summary["strict_player_probes"] = probes

    if args.probe_text_query:
        player_file = Path(args.player_file)
        probes: list[dict[str, Any]] = []
        if player_file.exists():
            for query in args.probe_text_query:
                probes.append(
                    decoded_text_probe(
                        player_file,
                        query,
                        max_results=args.max_text_probe_results,
                    )
                )
        else:
            probes.append({"error": f"Player file not found: {player_file}"})
        summary["decoded_text_probes"] = probes

    if args.probe_bio_marker:
        player_file = Path(args.player_file)
        probes: list[dict[str, Any]] = []
        if player_file.exists():
            for query in args.probe_bio_marker:
                probes.append(
                    bio_marker_probe(
                        player_file,
                        query,
                        max_results=args.max_bio_marker_results,
                    )
                )
        else:
            probes.append({"error": f"Player file not found: {player_file}"})
        summary["bio_marker_probes"] = probes

    if args.probe_seed_player_bios:
        player_file = Path(args.player_file)
        if player_file.exists():
            summary["seed_player_bio_linkage"] = probe_seed_player_bios(summary, player_file)
        else:
            summary["seed_player_bio_linkage"] = [{"error": f"Player file not found: {player_file}"}]

    payload = json.dumps(summary, indent=2)
    if args.json_output:
        out_path = Path(args.json_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
