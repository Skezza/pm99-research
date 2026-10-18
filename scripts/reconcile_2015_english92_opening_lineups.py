#!/usr/bin/env python3
"""Reconcile dated 2015/16 first-league XIs to the factual squad ledger.

The Transfermarkt capture contains the contemporaneous match-report formation
grid.  The FootballSquads ledger is the audited source used by the season
compiler for names, birth dates, shirts and player metadata.  This bridge
allows the compiler to use a real first-day XI without silently guessing a
name match.  Ambiguous or missing identities are retained in the review
output and make the result non-certifiable.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _normalise(value: str) -> str:
    text = str(value or "").translate(str.maketrans({"Ł": "L", "ł": "l", "Đ": "D", "đ": "d", "Ø": "O", "ø": "o", "Þ": "Th", "þ": "th", "Æ": "AE", "æ": "ae", "Ð": "D", "ð": "d"}))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "".join(char for char in text.casefold() if char.isalnum())


def _tokens(value: str) -> set[str]:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return {
        _normalise(token)
        for token in re.findall(r"[A-Za-z0-9]+", text.replace("-", " "))
        if _normalise(token)
    }


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _alias_map(path: Path | None) -> dict[tuple[str, str], dict[str, str]]:
    if path is None:
        return {}
    document = _load_json(path)
    rows = document.get("aliases") if isinstance(document, dict) else document
    if not isinstance(rows, list):
        raise ValueError("Manual aliases must be a list or an object with an aliases list")
    resolved: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Manual alias entries must be objects")
        club = str(row.get("club") or "").strip()
        source_slug = str(row.get("source_slug") or "").strip()
        source_name = str(row.get("source_name") or "").strip()
        reason = str(row.get("reason") or "").strip()
        if not all((club, source_slug, source_name, reason)):
            raise ValueError("Manual aliases need club, source_slug, source_name and reason")
        key = (club, source_slug)
        if key in resolved:
            raise ValueError(f"Duplicate manual alias for {club} / {source_slug}")
        resolved[key] = {"source_name": source_name, "reason": reason}
    return resolved


def _match_player(
    club: str,
    source_player: dict[str, Any],
    roster: list[dict[str, Any]],
    aliases: dict[tuple[str, str], dict[str, str]],
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """Return one roster row only when the evidence identifies it uniquely."""
    slug = str(source_player["source_slug"])
    display = str(source_player["display_name"])
    alias = aliases.get((club, slug))
    if alias is not None:
        exact = [row for row in roster if _normalise(str(row["name"])) == _normalise(alias["source_name"])]
        if len(exact) != 1:
            return None, None, [str(row["name"]) for row in exact]
        return exact[0], f"manual-alias:{alias['reason']}", []

    slug_key = _normalise(slug.replace("-", " "))
    display_key = _normalise(display)
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for row in roster:
        name = str(row["name"])
        key = _normalise(name)
        name_tokens = _tokens(name)
        slug_tokens = _tokens(slug)
        display_tokens = _tokens(display)
        score = 0
        method = ""
        if key == slug_key:
            score, method = 100, "full-source-slug"
        elif key == display_key:
            score, method = 95, "published-display-name"
        elif min(len(key), len(slug_key)) >= 6 and (key in slug_key or slug_key in key):
            score, method = 85, "full-name-containment"
        elif len(name_tokens) >= 2 and (name_tokens <= slug_tokens or slug_tokens <= name_tokens):
            score, method = 80, "full-name-token-containment"
        else:
            surname = next(reversed(re.findall(r"[A-Za-z0-9]+", unicodedata.normalize("NFKD", name.replace("-", " ")))), "")
            surname_key = _normalise(surname)
            # ``slug_tokens`` is a set.  Selecting its first member makes the
            # reconciliation vary with Python's hash randomisation, which is
            # unacceptable for a hash-bound season receipt.  Use lexical order
            # for this last-resort surname comparison instead.
            sorted_slug_tokens = sorted(slug_tokens)
            given = sorted_slug_tokens[0] if len(sorted_slug_tokens) == 1 else next((token for token in sorted_slug_tokens if token != surname_key), "")
            has_conflicting_given_name = bool(given and len(slug_tokens) >= 2 and given not in name_tokens)
            if len(surname_key) >= 5 and surname_key in (slug_tokens | display_tokens) and not has_conflicting_given_name:
                score, method = 40, "unique-surname-only"
        if score:
            candidates.append((score, method, row))
    if not candidates:
        return None, None, []
    best = max(score for score, _method, _row in candidates)
    winners = [(method, row) for score, method, row in candidates if score == best]
    if len(winners) != 1:
        return None, None, [str(row["name"]) for _method, row in winners]
    method, row = winners[0]
    return row, method, []


def _reconcile_player_list(
    club: str,
    source_rows: list[dict[str, Any]],
    roster: list[dict[str, Any]],
    aliases: dict[tuple[str, str], dict[str, str]],
    label: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    reconciled: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source_player in source_rows:
        row, method, candidates = _match_player(club, source_player, roster, aliases)
        if row is None:
            failures.append({
                "club": club, "list": label, "source_slug": source_player["source_slug"],
                "display_name": source_player["display_name"],
                "reason": "ambiguous-or-missing-source-player", "candidates": candidates,
            })
            continue
        name = str(row["name"])
        if name in seen:
            failures.append({
                "club": club, "list": label, "source_slug": source_player["source_slug"],
                "display_name": source_player["display_name"], "reason": "duplicate-resolved-player", "source_name": name,
            })
            continue
        seen.add(name)
        resolved = dict(source_player)
        resolved.update({
            "source_name": name, "shirt_number": int(row["shirt_number"]),
            "position": str(row["position"]), "match_method": method,
        })
        reconciled.append(resolved)
    return reconciled, failures


def reconcile(
    source_ledger: dict[str, Any],
    lineup_capture: dict[str, Any],
    aliases: dict[tuple[str, str], dict[str, str]],
) -> dict[str, Any]:
    if lineup_capture.get("schema_version") != "pm99-2015-16-opening-lineup-source-v1":
        raise ValueError("Unexpected opening-lineup source schema")
    source_clubs = {str(row["club"]): row for row in source_ledger.get("clubs") or []}
    captured_clubs = {str(row["club"]): row for row in lineup_capture.get("clubs") or []}
    missing_capture = sorted(set(source_clubs) - set(captured_clubs))
    unexpected_capture = sorted(set(captured_clubs) - set(source_clubs))
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for club in sorted(set(source_clubs) & set(captured_clubs)):
        captured = captured_clubs[club]
        source = source_clubs[club]
        xi, xi_failures = _reconcile_player_list(club, list(captured.get("starting_xi") or []), list(source["players"]), aliases, "starting_xi")
        subs, sub_failures = _reconcile_player_list(club, list(captured.get("substitutes") or []), list(source["players"]), aliases, "substitutes")
        club_failures = xi_failures + sub_failures
        if len(xi) != 11:
            club_failures.append({"club": club, "list": "starting_xi", "reason": "expected-eleven", "actual": len(xi)})
        if len(subs) < 5:
            club_failures.append({"club": club, "list": "substitutes", "reason": "need-five-pm99-bench-candidates", "actual": len(subs)})
        if len({row["source_name"] for row in xi} & {row["source_name"] for row in subs}):
            club_failures.append({"club": club, "reason": "player-in-xi-and-bench"})
        rows.append({
            "club": club, "division": source["division"], "first_league_fixture_date": captured["first_league_fixture_date"],
            "formation": captured["formation"], "schedule_url": captured["schedule_url"],
            "lineup_source_url": captured["lineup_source_url"], "source_match_id": captured["source_match_id"],
            "starting_xi": xi, "substitutes": subs, "reconciled": not club_failures,
        })
        failures.extend(club_failures)
    failures.extend({"reason": "missing-captured-club", "club": club} for club in missing_capture)
    failures.extend({"reason": "unexpected-captured-club", "club": club} for club in unexpected_capture)
    methods = Counter(
        row["match_method"]
        for club in rows
        for row in club["starting_xi"] + club["substitutes"]
    )
    return {
        "schema_version": "pm99-2015-16-opening-lineup-reconciliation-v1",
        "season": "2015/16",
        "snapshot_policy": lineup_capture["snapshot_policy"],
        "source_capture": lineup_capture["source"],
        "clubs": rows,
        "summary": {
            "club_count": len(rows), "certified_club_count": sum(1 for row in rows if row["reconciled"]),
            "failures": len(failures), "match_methods": dict(sorted(methods.items())),
        },
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ledger", type=Path, default=ROOT / "upstream/.local/season-2015-16/2015-16-english-source-ledger.json")
    parser.add_argument("--lineup-source", required=True, type=Path)
    parser.add_argument("--manual-aliases", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = reconcile(
        _load_json(args.source_ledger), _load_json(args.lineup_source),
        _alias_map(args.manual_aliases),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], sort_keys=True))
    return 0 if not result["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
