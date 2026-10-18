#!/usr/bin/env python3
"""Reconcile generic first-league-fixture source XIs to a dated squad capture.

The match-report capture and squad list are independent sources.  This bridge
only records a link when one squad player is identified uniquely; it neither
fills a missing person nor selects a PM99 player carrier.  A line-up player
outside the squad source stays in the explicit additions queue for a separate
dated-person source, exactly as a first-day loan or recent signing should.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import reconcile_2015_english92_opening_lineups as legacy  # noqa: E402


SCHEMA = "pm99-transfermarkt-opening-lineup-reconciliation-v1"
LINEUP_SCHEMA = "pm99-transfermarkt-opening-lineup-source-v1"
LINEUP_SCHEMAS = {LINEUP_SCHEMA, "pm99-composed-opening-lineup-source-v1"}
ALIAS_SCHEMA = "pm99-transfermarkt-opening-lineup-aliases-v1"
PERSON_EVIDENCE_SCHEMA = "pm99-transfermarkt-lineup-person-evidence-v1"


class ReconciliationError(ValueError):
    """Inputs cannot be safely joined."""


def _require_iso_date(value: str) -> str:
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ReconciliationError("lineup person evidence birth date must use ISO YYYY-MM-DD") from exc
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReconciliationError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ReconciliationError(f"{label} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _selector(value: Mapping[str, Any]) -> tuple[str, str, str]:
    club = str(value.get("club_name") or "").strip()
    country = str(value.get("country_catalog") or "").strip()
    competition = str(value.get("competition_catalog") or "").strip()
    if not all((club, country, competition)):
        raise ReconciliationError("club selector lacks club_name, country_catalog or competition_catalog")
    return country, competition, club


def _source_index(capture: Mapping[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    clubs = capture.get("clubs")
    if not isinstance(clubs, list):
        raise ReconciliationError("squad source capture must contain clubs")
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for club in clubs:
        if not isinstance(club, dict) or not isinstance(club.get("players"), list):
            raise ReconciliationError("squad source capture has a malformed club")
        key = _selector(club)
        if key in result:
            raise ReconciliationError(f"squad source capture duplicates selector {key}")
        result[key] = club
    return result


def load_aliases(path: Path | None) -> tuple[dict[tuple[tuple[str, str, str], str], dict[str, str]], str | None]:
    """Load explicit, source-scoped identity aliases; never fuzzy-apply one."""

    if path is None:
        return {}, None
    document, digest = _load_object(path, label="opening-lineup aliases")
    if document.get("schema_version") != ALIAS_SCHEMA or not isinstance(document.get("aliases"), list):
        raise ReconciliationError(f"opening-lineup aliases must have schema {ALIAS_SCHEMA} and an aliases list")
    result: dict[tuple[tuple[str, str, str], str], dict[str, str]] = {}
    for entry in document["aliases"]:
        if not isinstance(entry, dict) or set(entry) != {"reason", "source_name", "source_player_id", "source_selector"}:
            raise ReconciliationError("each lineup alias must have source_selector, source_player_id, source_name and reason")
        if not isinstance(entry["source_selector"], dict):
            raise ReconciliationError("lineup alias source_selector must be an object")
        selector = _selector(entry["source_selector"])
        source_player_id = str(entry["source_player_id"]).strip()
        source_name = str(entry["source_name"]).strip()
        reason = str(entry["reason"]).strip()
        if not all((source_player_id, source_name, reason)):
            raise ReconciliationError("lineup alias has a blank source player id, source name or reason")
        key = (selector, source_player_id)
        if key in result:
            raise ReconciliationError(f"duplicate lineup alias for {selector} / {source_player_id}")
        result[key] = {"source_name": source_name, "reason": reason}
    return result, digest


def load_person_evidence(
    path: Path | None, *, lineup_capture_sha256: str
) -> tuple[dict[tuple[tuple[str, str, str], str], dict[str, str]], str | None]:
    """Load profile facts bound to this exact lineup source receipt."""

    if path is None:
        return {}, None
    document, digest = _load_object(path, label="lineup person evidence")
    if document.get("schema_version") != PERSON_EVIDENCE_SCHEMA or not isinstance(document.get("players"), list):
        raise ReconciliationError(f"lineup person evidence must have schema {PERSON_EVIDENCE_SCHEMA} and a players list")
    if (document.get("source") or {}).get("lineup_capture_sha256") != lineup_capture_sha256:
        raise ReconciliationError("lineup person evidence is not bound to this exact lineup capture")
    result: dict[tuple[tuple[str, str, str], str], dict[str, str]] = {}
    for player in document["players"]:
        if not isinstance(player, dict) or not isinstance(player.get("source_selector"), dict):
            raise ReconciliationError("lineup person evidence has a malformed player")
        selector = _selector(player["source_selector"])
        player_id = str(player.get("source_player_id") or "").strip()
        birth_date = str(player.get("published_birth_date") or "").strip()
        if not player_id:
            raise ReconciliationError("lineup person evidence player lacks source_player_id")
        # A profile without a birth date remains useful to the opening-player
        # addition layer, but cannot corroborate a roster identity here.
        if not birth_date:
            continue
        _require_iso_date(birth_date)
        key = (selector, player_id)
        if key in result:
            raise ReconciliationError(f"lineup person evidence duplicates {selector} / {player_id}")
        result[key] = {"birth_date": birth_date}
    return result, digest


def _reconcile_players(
    *,
    selector: tuple[str, str, str],
    source_players: list[dict[str, Any]],
    roster: list[dict[str, Any]],
    aliases: Mapping[tuple[tuple[str, str, str], str], Mapping[str, str]],
    person_evidence: Mapping[tuple[tuple[str, str, str], str], Mapping[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolved: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    seen: set[str] = set()
    club_key = "/".join(selector)
    for player in source_players:
        if not isinstance(player, dict):
            failures.append({"reason": "malformed-source-player"})
            continue
        alias = aliases.get((selector, str(player.get("source_player_id") or "")))
        evidence = person_evidence.get((selector, str(player.get("source_player_id") or "")))
        try:
            if alias is None:
                row, method, candidates = legacy._match_player(club_key, player, roster, {})
                if row is None and evidence is not None:
                    # A date of birth is corroboration, not identity by itself:
                    # unrelated players at one club can share a birthday.  Keep
                    # at least one substantial published-name token in common
                    # before accepting the unique dated row.
                    published_tokens = legacy._tokens(
                        f"{player.get('display_name') or ''} {str(player.get('source_slug') or '').replace('-', ' ')}"
                    )
                    candidates = [
                        candidate for candidate in roster
                        if str(candidate.get("birth_date") or "") == evidence["birth_date"]
                        and any(
                            len(token) >= 4 and token in legacy._tokens(str(candidate.get("name") or ""))
                            for token in published_tokens
                        )
                    ]
                    if len(candidates) == 1:
                        row = candidates[0]
                        method = "profile-birth-date-unique"
                        candidates = []
            else:
                candidates = [row for row in roster if legacy._normalise(row.get("name")) == legacy._normalise(alias["source_name"])]
                row = candidates[0] if len(candidates) == 1 else None
                method = f"manual-alias:{alias['reason']}" if row is not None else None
                candidates = [] if row is not None else [str(candidate.get("name") or "") for candidate in candidates]
        except (KeyError, TypeError, ValueError) as exc:
            failures.append({"reason": "invalid-source-player", "detail": str(exc)})
            continue
        if row is None:
            failures.append({
                "reason": "ambiguous-or-missing-dated-squad-player",
                "display_name": str(player.get("display_name") or ""),
                "source_player_id": str(player.get("source_player_id") or ""),
                "candidates": candidates,
            })
            continue
        source_name = str(row["name"])
        if source_name in seen:
            failures.append({
                "reason": "duplicate-resolved-player",
                "source_name": source_name,
                "display_name": str(player.get("display_name") or ""),
                "source_player_id": str(player.get("source_player_id") or ""),
            })
            continue
        seen.add(source_name)
        copied = dict(player)
        copied.update({
            "source_name": source_name,
            "source_birth_date": row.get("birth_date"),
            "source_shirt_number": row.get("shirt_number"),
            "source_position": row.get("position"),
            "match_method": method,
        })
        resolved.append(copied)
    return resolved, failures


def reconcile(
    *, source_capture: Mapping[str, Any], lineup_capture: Mapping[str, Any], source_capture_sha256: str,
    lineup_capture_sha256: str, aliases: Mapping[tuple[tuple[str, str, str], str], Mapping[str, str]] | None = None,
    aliases_sha256: str | None = None,
    person_evidence: Mapping[tuple[tuple[str, str, str], str], Mapping[str, str]] | None = None,
    person_evidence_sha256: str | None = None,
    lineup_source_selection_sha256: str | None = None,
) -> dict[str, Any]:
    if lineup_capture.get("schema_version") not in LINEUP_SCHEMAS:
        raise ReconciliationError(f"lineup capture must have one of {sorted(LINEUP_SCHEMAS)}")
    declared_source_sha = (lineup_capture.get("source") or {}).get("source_capture_sha256")
    allowed_bindings = {source_capture_sha256}
    if lineup_source_selection_sha256 is not None:
        allowed_bindings.add(lineup_source_selection_sha256)
    if declared_source_sha not in allowed_bindings:
        raise ReconciliationError("lineup capture is not bound to this exact squad source capture")
    if (
        declared_source_sha == source_capture_sha256
        and lineup_source_selection_sha256 is not None
        and (lineup_capture.get("source") or {}).get("lineup_source_selection_sha256")
        != lineup_source_selection_sha256
    ):
        raise ReconciliationError("composed lineup capture is not bound to this exact source selection")
    roster_by_selector = _source_index(source_capture)
    aliases = aliases or {}
    person_evidence = person_evidence or {}
    captured: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in lineup_capture.get("clubs") or []:
        if not isinstance(row, dict) or not isinstance(row.get("source_selector"), dict):
            raise ReconciliationError("lineup capture has a malformed club")
        key = _selector(row["source_selector"])
        if key in captured:
            raise ReconciliationError(f"lineup capture duplicates selector {key}")
        captured[key] = row

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    methods: Counter[str] = Counter()
    for selector in sorted(roster_by_selector):
        source_club = roster_by_selector[selector]
        captured_club = captured.get(selector)
        if captured_club is None:
            failures.append({"selector": dict(zip(("country_catalog", "competition_catalog", "club_name"), selector)), "reason": "no-first-fixture-source-capture"})
            continue
        source_players = captured_club.get("starting_xi")
        if not isinstance(source_players, list):
            failures.append({"selector": dict(zip(("country_catalog", "competition_catalog", "club_name"), selector)), "reason": "malformed-starting-xi"})
            continue
        xi, club_failures = _reconcile_players(
            selector=selector, source_players=source_players, roster=list(source_club["players"]), aliases=aliases,
            person_evidence=person_evidence,
        )
        if len(xi) != 11:
            club_failures.append({"reason": "expected-eleven-reconciled-players", "actual": len(xi)})
        methods.update(str(row["match_method"]) for row in xi)
        row = {
            "source_selector": dict(captured_club["source_selector"]),
            "first_league_fixture_date": captured_club.get("first_league_fixture_date"),
            "lineup_source_url": captured_club.get("lineup_source_url"),
            "source_match_id": captured_club.get("source_match_id"),
            "formation": captured_club.get("formation"),
            "lineup_source_style": captured_club.get("lineup_source_style"),
            "source_status": captured_club.get("source_status"),
            "source_blockers": list(captured_club.get("source_blockers") or []),
            "starting_xi": xi,
            "starting_xi_reconciled": not club_failures,
            "unresolved_first_fixture_players": club_failures,
        }
        rows.append(row)
        failures.extend({"selector": row["source_selector"], **failure} for failure in club_failures)
    unexpected = sorted(set(captured) - set(roster_by_selector))
    failures.extend({"selector": dict(zip(("country_catalog", "competition_catalog", "club_name"), key)), "reason": "captured-club-not-in-squad-source"} for key in unexpected)
    return {
        "schema_version": SCHEMA,
        "sources": {
            "source_capture_sha256": source_capture_sha256,
            "lineup_source_selection_sha256": lineup_source_selection_sha256,
            "lineup_capture_sha256": lineup_capture_sha256,
            "aliases_sha256": aliases_sha256,
            "person_evidence_sha256": person_evidence_sha256,
        },
        "summary": {
            "source_club_count": len(roster_by_selector),
            "fixture-captured-club-count": len(captured),
            "reconciled-xi-club-count": sum(row["starting_xi_reconciled"] for row in rows),
            "unreconciled-or-uncaptured-club-count": len(roster_by_selector) - sum(row["starting_xi_reconciled"] for row in rows),
            "failure-count": len(failures),
            "match-methods": dict(sorted(methods.items())),
        },
        "clubs": rows,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-capture", required=True, type=Path)
    parser.add_argument("--lineup-capture", required=True, type=Path)
    parser.add_argument("--lineup-source-selection", type=Path, help="hash-bound selector-only projection used by the lineup capture")
    parser.add_argument("--manual-aliases", type=Path, help="canonical reviewed identity aliases; no aliases are inferred")
    parser.add_argument("--person-evidence", type=Path, help="hash-bound profile facts used only for unique date-of-birth links")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--strict", action="store_true", help="return non-zero when a source club is not fully reconciled")
    args = parser.parse_args(argv)
    try:
        source_capture, source_capture_sha256 = _load_object(args.source_capture, label="squad source capture")
        lineup_capture, lineup_capture_sha256 = _load_object(args.lineup_capture, label="lineup source capture")
        selection_sha256 = None
        if args.lineup_source_selection:
            selection, selection_sha256 = _load_object(args.lineup_source_selection, label="lineup source selection")
            full_selectors = set(_source_index(source_capture))
            selected = {_selector(row) for row in selection.get("clubs", []) if isinstance(row, Mapping)}
            if not selected or not selected <= full_selectors:
                raise ReconciliationError("lineup source selection is not an exact selector subset of the squad source capture")
        aliases, aliases_sha256 = load_aliases(args.manual_aliases)
        person_evidence, person_evidence_sha256 = load_person_evidence(
            args.person_evidence, lineup_capture_sha256=lineup_capture_sha256,
        )
        result = reconcile(
            source_capture=source_capture, lineup_capture=lineup_capture,
            source_capture_sha256=source_capture_sha256, lineup_capture_sha256=lineup_capture_sha256,
            aliases=aliases, aliases_sha256=aliases_sha256,
            person_evidence=person_evidence, person_evidence_sha256=person_evidence_sha256,
            lineup_source_selection_sha256=selection_sha256,
        )
    except (OSError, ReconciliationError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], sort_keys=True))
    return 1 if args.strict and result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
