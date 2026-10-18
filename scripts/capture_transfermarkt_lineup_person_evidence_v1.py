#!/usr/bin/env python3
"""Capture immutable person facts for unresolved first-fixture lineup players.

The lineup receipt provides a stable Transfermarkt player ID.  This source
stage snapshots only the player profiles needed by the reconciliation queue
and records their published date of birth.  It does not choose a squad player
or correct a name; the subsequent reconciler may use a *unique* matching date
of birth as an identity bridge.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture_transfermarkt_opening_lineups_v1 import CaptureError, SnapshotCache  # noqa: E402


SCHEMA = "pm99-transfermarkt-lineup-person-evidence-v1"
SUPPLEMENT_SCHEMA = "pm99-opening-person-profile-source-overrides-v1"
LINEUP_SCHEMA = "pm99-transfermarkt-opening-lineup-source-v1"
LINEUP_SCHEMAS = {LINEUP_SCHEMA, "pm99-composed-opening-lineup-source-v1"}
_RENDERED_SQUAD_NUMBER = re.compile(r"^#\s*\d{1,3}\s+")


class PersonEvidenceError(ValueError):
    """Input source receipts cannot be safely connected."""


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PersonEvidenceError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise PersonEvidenceError(f"{label} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _selector(value: Mapping[str, Any]) -> tuple[str, str, str]:
    key = tuple(str(value.get(field) or "").strip() for field in ("country_catalog", "competition_catalog", "club_name"))
    if not all(key):
        raise PersonEvidenceError("club selector lacks country_catalog, competition_catalog or club_name")
    return key  # type: ignore[return-value]


def _candidate_players(lineup_capture: Mapping[str, Any], reconciliation: Mapping[str, Any]) -> list[dict[str, Any]]:
    if lineup_capture.get("schema_version") not in LINEUP_SCHEMAS:
        raise PersonEvidenceError(f"lineup capture must have one of {sorted(LINEUP_SCHEMAS)}")
    if not isinstance(reconciliation.get("sources"), dict):
        raise PersonEvidenceError("reconciliation has no source bindings")
    lineup_by_key: dict[tuple[tuple[str, str, str], str], dict[str, Any]] = {}
    for club in lineup_capture.get("clubs") or []:
        if not isinstance(club, dict) or not isinstance(club.get("source_selector"), dict):
            raise PersonEvidenceError("lineup capture has a malformed club")
        selector = _selector(club["source_selector"])
        for player in club.get("starting_xi") or []:
            if not isinstance(player, dict):
                raise PersonEvidenceError("lineup capture has a malformed starting player")
            player_id = str(player.get("source_player_id") or "").strip()
            if not player_id or not str(player.get("source_url") or "").strip():
                raise PersonEvidenceError("lineup player lacks a stable source id or URL")
            key = (selector, player_id)
            if key in lineup_by_key:
                raise PersonEvidenceError(f"lineup capture duplicates player {key}")
            lineup_by_key[key] = player
    candidates: dict[tuple[tuple[str, str, str], str], dict[str, Any]] = {}
    for club in reconciliation.get("clubs") or []:
        if not isinstance(club, dict) or not isinstance(club.get("source_selector"), dict):
            raise PersonEvidenceError("reconciliation has a malformed club")
        selector = _selector(club["source_selector"])
        for failure in club.get("unresolved_first_fixture_players") or []:
            if not isinstance(failure, dict) or failure.get("reason") not in {
                "ambiguous-or-missing-dated-squad-player",
                "duplicate-resolved-player",
            }:
                continue
            player_id = str(failure.get("source_player_id") or "").strip()
            player = lineup_by_key.get((selector, player_id))
            if player is None:
                raise PersonEvidenceError(f"reconciliation unresolved player is absent from lineup capture: {selector} / {player_id}")
            candidates[(selector, player_id)] = player
    result = []
    for (selector, player_id), player in sorted(candidates.items()):
        row = {
            "source_selector": dict(zip(("country_catalog", "competition_catalog", "club_name"), selector)),
            "source_player_id": player_id,
            "display_name": str(player["display_name"]),
            "source_url": str(player["source_url"]),
        }
        if player.get("source_position_group") is not None:
            row["source_position_group"] = player["source_position_group"]
        result.append(row)
    return result


def _profile_label(page: BeautifulSoup, label: str) -> str:
    for item in page.select(".data-header__label"):
        own = item.find(string=re.compile(r"\S"), recursive=False)
        text = str(own or "").strip().rstrip(":")
        if text != label:
            continue
        content = item.select_one(".data-header__content")
        return content.get_text(" ", strip=True) if content is not None else ""
    return ""


def _height_cm(value: str) -> int | None:
    metric = re.search(r"\b(\d)(?:[.,](\d{1,2}))?\s*m\b", value)
    if metric is not None:
        return round((int(metric.group(1)) + int((metric.group(2) or "0").ljust(2, "0")) / 100) * 100)
    imperial = re.search(r"\b(\d+)\s*ft\s*(\d+)\s*in\b", value, flags=re.IGNORECASE)
    if imperial is not None:
        return round((int(imperial.group(1)) * 12 + int(imperial.group(2))) * 2.54)
    return None


def _published_transfermarkt_name(headline: Any) -> str:
    """Return a profile name without the page's rendered squad-number label."""

    value = headline.get_text(" ", strip=True) if headline is not None else ""
    return _RENDERED_SQUAD_NUMBER.sub("", value).strip()


def _profile_facts(payload: bytes, *, player: Mapping[str, Any]) -> dict[str, Any]:
    page = BeautifulSoup(payload, "html.parser")
    if str(player.get("source_player_id") or "").startswith("soccerbase:"):
        return _soccerbase_profile_facts(page, player=player)
    headline = page.select_one("h1.data-header__headline-wrapper")
    published_full_name = _published_transfermarkt_name(headline)
    if not published_full_name:
        raise PersonEvidenceError(f"profile has no published full name for source player {player['source_player_id']}")
    birth = page.select_one('[itemprop="birthDate"]')
    text = birth.get_text(" ", strip=True) if birth is not None else ""
    match = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", text)
    nationality = page.select_one('[itemprop="nationality"]')
    published_nationality_label = nationality.get_text(" ", strip=True) if nationality is not None else None
    published_nationality_label = published_nationality_label or None
    published_profile_position = _profile_label(page, "Position") or None
    return {
        **player,
        "published_full_name": published_full_name,
        "published_birth_date": f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match is not None else None,
        "published_nationality_label": published_nationality_label,
        "published_profile_position": published_profile_position,
        "published_height_cm": _height_cm(_profile_label(page, "Height")),
        "profile_status": "source-qualified" if match is not None else "source-qualified-with-explicit-gaps",
        "profile_blockers": [] if match is not None else ["no-published-birth-date"],
    }


def _soccerbase_profile_facts(page: BeautifulSoup, *, player: Mapping[str, Any]) -> dict[str, Any]:
    headline = page.select_one("h1")
    published_full_name = headline.get_text(" ", strip=True) if headline is not None else ""
    if not published_full_name:
        raise PersonEvidenceError(f"Soccerbase profile has no published full name for {player['source_player_id']}")
    labelled: dict[str, str] = {}
    for row in page.select("table.clubInfo tr"):
        heading, value = row.select_one("th"), row.select_one("td")
        if heading is not None and value is not None:
            labelled[heading.get_text(" ", strip=True).casefold()] = value.get_text(" ", strip=True)
    birth_match = re.search(r"\bBorn\s+(\d{1,2}\s+[A-Za-z]{3},\s+\d{4})\b", labelled.get("age", ""))
    birth_date = datetime.strptime(birth_match.group(1), "%d %b, %Y").date().isoformat() if birth_match else None
    description = page.select_one('meta[name="description"]')
    description_text = str(description.get("content") or "") if description is not None else ""
    position_match = re.search(r"\b(Goalkeeper|Defender|Midfielder|Forward)\b", description_text, flags=re.IGNORECASE)
    published_position = position_match.group(1).title() if position_match else player.get("source_position_group")
    return {
        **player,
        "published_full_name": published_full_name,
        "published_birth_date": birth_date,
        "published_nationality_label": labelled.get("nationality") or None,
        "published_profile_position": published_position,
        "published_height_cm": _height_cm(labelled.get("height", "")),
        "profile_status": "source-qualified" if birth_date is not None else "source-qualified-with-explicit-gaps",
        "profile_blockers": [] if birth_date is not None else ["no-published-birth-date"],
    }


def _wikipedia_profile_facts(payload: bytes, *, player: Mapping[str, Any]) -> dict[str, Any]:
    """Read independently published facts from one immutable Wikipedia revision."""

    page = BeautifulSoup(payload, "html.parser")
    headline = page.select_one("h1")
    published_name = headline.get_text(" ", strip=True) if headline is not None else ""
    labelled: dict[str, str] = {}
    for row in page.select("table.infobox tr"):
        heading, value = row.select_one("th"), row.select_one("td")
        if heading is not None and value is not None:
            labelled[heading.get_text(" ", strip=True).casefold()] = value.get_text(" ", strip=True)
    birth = page.select_one(".bday")
    birth_date = birth.get_text(" ", strip=True) if birth is not None else None
    position = labelled.get("position") or None
    if not published_name or not position:
        raise PersonEvidenceError(f"Wikipedia revision lacks a published name or position for {player['source_player_id']}")
    return {
        **player,
        "published_full_name": labelled.get("full name") or published_name,
        "published_birth_date": birth_date,
        "published_nationality_label": None,
        "published_profile_position": position,
        "published_height_cm": None,
        "profile_status": "source-qualified" if birth_date else "source-qualified-with-explicit-gaps",
        "profile_blockers": [] if birth_date else ["no-published-birth-date"],
    }


def _supplement_index(value: Mapping[str, Any] | None) -> dict[tuple[tuple[str, str, str], str], dict[str, Any]]:
    if value is None:
        return {}
    if value.get("schema_version") != SUPPLEMENT_SCHEMA:
        raise PersonEvidenceError(f"profile source overrides must have schema {SUPPLEMENT_SCHEMA}")
    result: dict[tuple[tuple[str, str, str], str], dict[str, Any]] = {}
    for row in value.get("rows") or []:
        if not isinstance(row, dict) or not isinstance(row.get("source_selector"), dict):
            raise PersonEvidenceError("profile source overrides contain a malformed row")
        key = (_selector(row["source_selector"]), str(row.get("source_player_id") or "").strip())
        if not key[1] or key in result:
            raise PersonEvidenceError(f"profile source override has a missing or duplicate player id: {key}")
        url = str(row.get("source_url") or "")
        if row.get("parser") != "wikipedia-infobox-v1" or "oldid=" not in url:
            raise PersonEvidenceError("profile source override requires an immutable Wikipedia oldid URL and known parser")
        result[key] = dict(row)
    return result


def capture(
    *, lineup_capture: Mapping[str, Any], lineup_capture_sha256: str, reconciliation: Mapping[str, Any],
    cache: SnapshotCache, profile_source_overrides: Mapping[str, Any] | None = None,
    profile_source_overrides_sha256: str | None = None,
) -> dict[str, Any]:
    if (reconciliation.get("sources") or {}).get("lineup_capture_sha256") != lineup_capture_sha256:
        raise PersonEvidenceError("reconciliation is not bound to this exact lineup capture")
    players = _candidate_players(lineup_capture, reconciliation)
    facts: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    overrides = _supplement_index(profile_source_overrides)
    for player in players:
        player_id = str(player["source_player_id"])
        try:
            key = (_selector(player["source_selector"]), player_id)
            override = overrides.get(key)
            if override is None:
                payload = cache.get(str(player["source_url"]), f"profile/{player_id}.html")
                facts.append(_profile_facts(payload, player=player))
            else:
                override_player = {
                    **player,
                    "lineup_profile_url": player["source_url"],
                    "source_url": str(override["source_url"]),
                    "profile_source_name": str(override.get("source_name") or "Wikipedia"),
                }
                payload = cache.get(str(override["source_url"]), f"profile-supplement/{player_id}.html")
                facts.append(_wikipedia_profile_facts(payload, player=override_player))
        except (CaptureError, OSError, PersonEvidenceError) as exc:
            failures.append({**player, "reason": str(exc)})
    return {
        "schema_version": SCHEMA,
        "source": {
            "name": "Published player profiles referenced by the opening-lineup source (Transfermarkt or Soccerbase)",
            "lineup_capture_sha256": lineup_capture_sha256,
            "profile_source_overrides_sha256": profile_source_overrides_sha256,
            "cache_files": [cache.used[key] for key in sorted(cache.used)],
        },
        "summary": {
            "candidate_player_count": len(players),
            "profiled_player_count": len(facts),
            "failed_player_count": len(failures),
        },
        "players": facts,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lineup-capture", required=True, type=Path)
    parser.add_argument("--reconciliation", required=True, type=Path, help="reconciliation without this person-evidence input")
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--profile-source-overrides", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.delay <= 5:
        parser.error("--delay must be between 0 and 5 seconds")
    try:
        lineup_capture, lineup_capture_sha256 = _load(args.lineup_capture, label="lineup capture")
        reconciliation, _ = _load(args.reconciliation, label="reconciliation")
        overrides, overrides_sha256 = (None, None)
        if args.profile_source_overrides is not None:
            overrides, overrides_sha256 = _load(args.profile_source_overrides, label="profile source overrides")
        cache = SnapshotCache(args.cache_dir, offline=args.offline, delay=args.delay)
        result = capture(
            lineup_capture=lineup_capture, lineup_capture_sha256=lineup_capture_sha256,
            reconciliation=reconciliation, cache=cache,
            profile_source_overrides=overrides, profile_source_overrides_sha256=overrides_sha256,
        )
    except (OSError, PersonEvidenceError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_json_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 1 if args.strict and result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
