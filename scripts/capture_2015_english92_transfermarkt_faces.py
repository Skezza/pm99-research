#!/usr/bin/env python3
"""Find identity-checked fallback portrait URLs for a built 2015/16 season.

This is deliberately a *receipt generator*, not an image scraper hidden inside
the release compiler.  It reads the unresolved rows emitted by the normal
FIFA-era face stage, searches Transfermarkt only when the dated squad source
does not already carry a player-profile URL, and accepts a photo only when the
profile's displayed date of birth exactly agrees with the compiled player.

The generated JSON is accepted by ``prepare_2015_english92_fifa16_faces.py``
as its manual-source ledger.  It leaves rows without an actual profile photo
explicitly unresolved: a default silhouette is never treated as a player's
portrait.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


PROFILE_PATTERN = re.compile(r'href="([^\"]+/profil/spieler/\d+)"')
PORTRAIT_PATTERN = re.compile(
    r'https://img\\.a\\.transfermarkt\\.technology/portrait/big/[^"? ]+'
)
DATE_PATTERN = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_profile_date(iso_date: str) -> str:
    year, month, day = str(iso_date).split("-", 2)
    return f"{day}/{month}/{year}"


def _profile_photo(session: requests.Session, profile_url: str, birth_date: str) -> tuple[str | None, str]:
    try:
        response = session.get(profile_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        return None, f"profile-request-failed:{type(exc).__name__}"
    expected_date = _expected_profile_date(birth_date)
    if expected_date not in set(DATE_PATTERN.findall(response.text)):
        return None, "profile-date-of-birth-mismatch"
    portraits = list(dict.fromkeys(PORTRAIT_PATTERN.findall(response.text)))
    image_url = next((url for url in portraits if not url.endswith("/default.jpg")), None)
    if image_url is None:
        return None, "profile-has-no-player-photo"
    try:
        image = session.get(image_url, timeout=30)
        if image.status_code != 200 or not image.headers.get("content-type", "").startswith("image/"):
            return None, f"portrait-request-failed:http-{image.status_code}"
    except requests.RequestException as exc:
        return None, f"portrait-request-failed:{type(exc).__name__}"
    return image_url, "accepted"


def _source_profile_urls(season_ledger: dict[str, Any]) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for club in list(season_ledger.get("clubs") or []):
        club_name = str(club.get("club") or "")
        for player in list(club.get("players") or []):
            profile_url = str((player.get("first_fixture_source") or {}).get("profile_url") or "")
            if profile_url.startswith("https://"):
                result[(club_name, str(player.get("name") or ""))] = profile_url
    return result


def _search_profile_urls(session: requests.Session, name: str) -> list[str]:
    url = "https://www.transfermarkt.co.uk/schnellsuche/ergebnis/schnellsuche?query=" + quote(name)
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return []
    return list(dict.fromkeys("https://www.transfermarkt.co.uk" + value for value in PROFILE_PATTERN.findall(response.text)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--season-ledger", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--delay-seconds", type=float, default=0.15)
    args = parser.parse_args()

    build_dir = args.build_dir.resolve()
    faces = _read(build_dir / "face-stage-receipt.json")
    players = {int(row["record_id"]): row for row in _read(build_dir / "player-ledger.json")}
    source_profiles = _source_profile_urls(_read(args.season_ledger.resolve()))
    unresolved = [row for row in list(faces.get("rows") or []) if row.get("status") != "applied"]
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (PM99 historical database research)"

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, face in enumerate(unresolved, start=1):
        record_id = int(face["record_id"])
        player = players.get(record_id)
        if player is None:
            raise RuntimeError(f"face receipt record {record_id} is absent from the player ledger")
        club = str(player["club"])
        name = str(player["name"])
        candidates = [source_profiles[(club, name)]] if (club, name) in source_profiles else _search_profile_urls(session, name)
        outcome = "no-profile-search-result"
        for profile_url in candidates[:12]:
            photo_url, status = _profile_photo(session, profile_url, str(player["birth_date"]))
            outcome = status
            if photo_url is None:
                continue
            accepted.append(
                {
                    "record_id": record_id,
                    "club": club,
                    "player": name,
                    "source_url": photo_url,
                    "source_label": "Transfermarkt player-profile headshot",
                    "identity_evidence_url": profile_url,
                    "temporal_note": (
                        "Undated Transfermarkt headshot; player identity is verified by the profile's "
                        "displayed date of birth. This is an identity-safe fallback, not a claim that "
                        "the photograph was taken during 2015/16."
                    ),
                }
            )
            outcome = "accepted"
            break
        if outcome != "accepted":
            rejected.append({"record_id": record_id, "club": club, "player": name, "reason": outcome})
        if index < len(unresolved) and args.delay_seconds > 0:
            time.sleep(args.delay_seconds)

    output = {
        "schema_version": "pm99-2015-16-transfermarkt-face-fallback-v1",
        "purpose": "Identity-safe fallback portrait sources for players unresolved by FIFA-era CDN artwork",
        "rows": accepted,
        "unresolved": rejected,
    }
    args.output.resolve().write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": len(accepted), "unresolved": len(rejected), "output": str(args.output.resolve())}))
    return 0 if not rejected else 2


if __name__ == "__main__":
    raise SystemExit(main())
