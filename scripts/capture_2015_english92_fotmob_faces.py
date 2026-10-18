#!/usr/bin/env python3
"""Build an identity-checked FotMob portrait fallback ledger.

The normal 2015/16 face stage uses contemporary FIFA artwork.  This helper
only addresses its explicit unresolved tail.  FotMob's search suggestion is
not trusted on its own: a candidate is accepted only when its public player
page has the same normalized player name and exact ISO date of birth as the
compiled season record, and the candidate image itself responds as an image.
The resulting ledger is consumed explicitly by the face stage, so this
network lookup never becomes a silent compiler dependency.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


FOTMOB = "https://www.fotmob.com"
SUGGEST_URL = FOTMOB + "/api/data/search/suggest"
PLAYER_URL = FOTMOB + "/en-GB/players/{player_id}"
IMAGE_URL = "https://images.fotmob.com/image_resources/playerimages/{player_id}.png"
USER_AGENT = "Mozilla/5.0 (PM99 2015/16 historical database research)"

# The names in the dated squad lists are preserved in the game, while a few
# public profile sites use a formal given name.  Each alias remains visible in
# the emitted receipt and must still pass the DOB check.
QUERY_ALIASES = {
    "Aidy White": "Aidan White",
}


def _normal(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char.casefold() for char in decomposed if char.isalnum())


def _request_json(session: requests.Session, name: str) -> list[dict[str, Any]]:
    try:
        response = session.get(SUGGEST_URL, params={"hits": "50", "lang": "en", "term": name}, timeout=30)
        response.raise_for_status()
        raw = response.json()
    except (requests.RequestException, ValueError):
        return []
    results: list[dict[str, Any]] = []
    for group in raw if isinstance(raw, list) else []:
        for candidate in list(group.get("suggestions") or []):
            if candidate.get("type") == "player" and candidate.get("id"):
                results.append(candidate)
    return results


def _profile_date(session: requests.Session, player_id: str) -> tuple[str | None, str | None]:
    try:
        response = session.get(PLAYER_URL.format(player_id=player_id), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        return None, f"profile-request-failed:{type(exc).__name__}"
    match = re.search(r'"birthDate":"(?P<date>\d{4}-\d{2}-\d{2})T', response.text)
    if match is None:
        return None, "profile-has-no-birth-date"
    return str(match.group("date")), None


def _has_image(session: requests.Session, player_id: str) -> bool:
    try:
        response = session.get(IMAGE_URL.format(player_id=player_id), timeout=30)
        return response.status_code == 200 and response.headers.get("content-type", "").startswith("image/")
    except requests.RequestException:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    build = args.build_dir.resolve()
    face_receipt = json.loads((build / "face-stage-receipt.json").read_text(encoding="utf-8"))
    players = {int(row["record_id"]): row for row in json.loads((build / "player-ledger.json").read_text(encoding="utf-8"))}
    unresolved = [row for row in list(face_receipt.get("rows") or []) if row.get("status") != "applied"]
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for face in unresolved:
        record_id = int(face["record_id"])
        player = players.get(record_id)
        if player is None:
            raise RuntimeError(f"face receipt record {record_id} is absent from player-ledger.json")
        name = str(player["name"])
        birth_date = str(player["birth_date"])
        query = QUERY_ALIASES.get(name, name)
        candidates = _request_json(session, query)
        accepted_row: dict[str, Any] | None = None
        reason = "no-player-search-result"
        for candidate in candidates:
            candidate_name = str(candidate.get("name") or "")
            # An alias is a search spelling only; the public player name must
            # still be either the compiled name or that declared alias.
            if _normal(candidate_name) not in {_normal(name), _normal(query)}:
                reason = "candidate-name-mismatch"
                continue
            player_id = str(candidate["id"])
            observed_dob, error = _profile_date(session, player_id)
            if error is not None:
                reason = error
                continue
            if observed_dob != birth_date:
                reason = "profile-date-of-birth-mismatch"
                continue
            if not _has_image(session, player_id):
                reason = "profile-has-no-downloadable-photo"
                continue
            accepted_row = {
                "record_id": record_id,
                "club": str(player["club"]),
                "player": name,
                "source_url": IMAGE_URL.format(player_id=player_id),
                "source_label": "FotMob player-profile headshot",
                "identity_evidence_url": PLAYER_URL.format(player_id=player_id),
                "temporal_note": (
                    "Undated FotMob headshot; player identity is verified by the public profile's "
                    "displayed name and exact date of birth. This is an identity-safe fallback, "
                    "not a claim that the photograph was taken during 2015/16."
                ),
                "fotmob_player_id": player_id,
                "search_query": query,
            }
            break
        if accepted_row is not None:
            accepted.append(accepted_row)
        else:
            rejected.append({"record_id": record_id, "club": player["club"], "player": name, "reason": reason})

    output = {
        "schema_version": "pm99-2015-16-fotmob-face-fallback-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "purpose": "Identity-safe FotMob sources for players unresolved by the dated FIFA headshot stage",
        "rows": accepted,
        "unresolved": rejected,
    }
    args.output.resolve().write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": len(accepted), "unresolved": len(rejected), "output": str(args.output.resolve())}))
    return 0 if not rejected else 2


if __name__ == "__main__":
    raise SystemExit(main())
