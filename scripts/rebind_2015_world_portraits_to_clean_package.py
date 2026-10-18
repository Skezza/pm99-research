#!/usr/bin/env python3
"""Rebind reviewed 2015 portrait results to a clean native-carrier package.

The historical portrait lane was completed before the clean-base compiler was
introduced.  Its carrier numbers are therefore not safe to replay.  This tool
joins those results to the clean package by club and dated player identity,
then emits an application manifest using the clean carrier IDs.  Any identity
that cannot be joined exactly is deliberately left as native no-photo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

MANIFEST_SCHEMA = "pm99-world-2015-asset-candidate-manifest-v1"
MATERIALISATION_SCHEMA = "pm99-world-2015-portrait-materialisation-v1"
OUTPUT_SCHEMA = "pm99-world-2015-clean-portrait-rebind-v1"


class RebindError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normal_name(value: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return "".join(char for char in decomposed if char.isalnum())


def _choose_old_player(
    old_players: list[Mapping[str, Any]], *, source_name: str, slot_index: int,
) -> Mapping[str, Any] | None:
    identity = normal_name(source_name)
    at_slot = [row for row in old_players if int(row.get("slot_index", -1)) == slot_index]
    if len(at_slot) == 1 and normal_name(at_slot[0].get("name")) == identity:
        return at_slot[0]
    matches = [row for row in old_players if normal_name(row.get("name")) == identity]
    return matches[0] if len(matches) == 1 else None


def rebind(
    *, package: Mapping[str, Any], old_manifest: Mapping[str, Any],
    old_materialisation: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if package.get("schema_version") != "pm99-season-package-v2":
        raise RebindError("season package schema is unsupported")
    if old_manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise RebindError("old asset manifest schema is unsupported")
    if old_materialisation.get("schema_version") != MATERIALISATION_SCHEMA:
        raise RebindError("old portrait materialisation schema is unsupported")

    players = {str(row["id"]): row for row in package.get("players", [])}
    clubs = {int(row["carrier_id"]): row for row in package.get("clubs", [])}
    old_clubs = {int(row["carrier_id"]): row for row in old_manifest.get("clubs", [])}
    old_outcomes: dict[tuple[int, int, int], Mapping[str, Any]] = {}
    outcomes_by_identity: dict[tuple[int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in old_materialisation.get("rows", []):
        key = (int(row["carrier_id"]), int(row["slot_index"]), int(row["player_carrier_id"]))
        old_outcomes[key] = row
        outcomes_by_identity[(int(row["carrier_id"]), normal_name(row.get("name")))].append(row)

    new_clubs: list[dict[str, Any]] = []
    new_outcomes: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    used_carriers: set[int] = set()
    matched = failures = no_candidate = unmatched = 0

    for carrier_id, club in sorted(clubs.items()):
        old_club = old_clubs.get(carrier_id, {})
        old_players = list(old_club.get("players", []))
        rebound_players: list[dict[str, Any]] = []
        for slot_index, player_id in enumerate(club.get("roster_player_ids", [])):
            player = players.get(str(player_id))
            if not player or int(player.get("carrier_id", 0)) in used_carriers:
                continue
            # The package's owning club identifies the authoritative occurrence
            # when PM99's native graph shares a carrier between roster tails.
            if str(player.get("club_id")) != str(club.get("id")):
                continue
            source_name = player.get("source_name")
            if not isinstance(source_name, str) or not source_name.strip():
                continue
            clean_player_carrier = int(player["carrier_id"])
            used_carriers.add(clean_player_carrier)
            old_player = _choose_old_player(old_players, source_name=source_name, slot_index=slot_index)
            portrait = {"status": "needs-identity-safe-era-source"}
            fifa_id = None
            outcome = None
            join = "unmatched-native-no-photo"
            if old_player is not None:
                portrait = dict(old_player.get("portrait") or portrait)
                fifa_id = old_player.get("fifa16_player_id")
                old_key = (carrier_id, int(old_player["slot_index"]), int(old_player["player_carrier_id"]))
                outcome = old_outcomes.get(old_key)
                if outcome is None:
                    identity_outcomes = outcomes_by_identity.get((carrier_id, normal_name(source_name)), [])
                    if len(identity_outcomes) == 1:
                        outcome = identity_outcomes[0]
                join = "club-and-player-identity"
                matched += 1
            else:
                unmatched += 1

            # A candidate without its exact reviewed outcome is not replayable.
            # Likewise, an old preserve-native decision was tied to the old
            # carrier and must never survive a clean-carrier reassignment.
            if portrait.get("status") == "fifa16-url-candidate" and outcome is None:
                portrait = {"status": "needs-identity-safe-era-source"}
                join = "candidate-outcome-missing-native-no-photo"
            elif portrait.get("status") != "fifa16-url-candidate":
                portrait = {"status": "needs-identity-safe-era-source"}
                if join == "club-and-player-identity":
                    join = "identity-matched-without-replayable-conversion"
            rebound = {
                "slot_index": slot_index,
                "source_squad_index": slot_index,
                "player_carrier_id": clean_player_carrier,
                "name": source_name,
                "portrait": portrait,
            }
            if fifa_id is not None:
                rebound["fifa16_player_id"] = fifa_id
            rebound_players.append(rebound)

            resulting_state = "native-no-photo"
            if portrait.get("status") == "fifa16-url-candidate" and outcome is not None:
                copied = dict(outcome)
                copied.update({
                    "carrier_id": carrier_id,
                    "slot_index": slot_index,
                    "player_carrier_id": clean_player_carrier,
                    "name": source_name,
                })
                new_outcomes.append(copied)
                if copied.get("status") == "approved-crop-conversion-candidate":
                    resulting_state = "applied"
                else:
                    failures += 1
            else:
                no_candidate += 1
            ledger.append({
                "club_carrier_id": carrier_id,
                "club_name": club.get("name"),
                "player_carrier_id": clean_player_carrier,
                "player_name": source_name,
                "fifa16_player_id": fifa_id,
                "identity_join": join,
                "resulting_state": resulting_state,
                "reason": (outcome or {}).get("failure_reason") if outcome else portrait.get("status"),
            })
        new_clubs.append({
            "carrier_id": carrier_id,
            "source_club_name": club.get("name"),
            "source_status": "source-squad-ready" if rebound_players else "preserve-native",
            "players": rebound_players,
        })

    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "season": "2015-16",
        "result": "clean-native-carrier-portrait-application-manifest",
        "policy": {
            "join": "same fixed club carrier plus exact normalised dated player name; original slot preferred",
            "failure": "native-no-photo; never inherit or substitute an unrelated face",
        },
        "coverage": {
            "selected_player_count": len(ledger),
            "identity_matched_count": matched,
            "identity_unmatched_count": unmatched,
        },
        "clubs": new_clubs,
    }
    manifest_bytes = canonical_bytes(manifest)
    statuses: dict[str, int] = defaultdict(int)
    for row in new_outcomes:
        statuses[str(row.get("status"))] += 1
    materialisation = {
        "schema_version": MATERIALISATION_SCHEMA,
        "season": "2015-16",
        "result": "identity-rebound-reviewed-results",
        "policy": {
            "source": "previously reviewed identity-bound conversion only",
            "failure": "native-no-photo",
        },
        "coverage": {
            "candidate_url_player_count": len(new_outcomes),
            "status_counts": dict(sorted(statuses.items())),
            "success_count": sum(row.get("status") == "approved-crop-conversion-candidate" for row in new_outcomes),
            "native_no_photo_failure_count": failures,
            "pending_count": 0,
        },
        "source": {
            "candidate_manifest_file_sha256": sha256_bytes(manifest_bytes),
        },
        "successes": [row for row in new_outcomes if row.get("status") == "approved-crop-conversion-candidate"],
        "failures": [row for row in new_outcomes if row.get("status") != "approved-crop-conversion-candidate"],
        "pending": [],
        "rows": new_outcomes,
    }
    applied = sum(row["resulting_state"] == "applied" for row in ledger)
    receipt = {
        "schema_version": OUTPUT_SCHEMA,
        "result": "complete-fail-open",
        "coverage": {
            "clean_sourced_player_count": len(ledger),
            "reused_approved_portrait_count": applied,
            "native_no_photo_count": len(ledger) - applied,
            "old_download_failure_count": failures,
            "no_candidate_or_unmatched_count": no_candidate,
            "identity_unmatched_count": unmatched,
        },
        "missing_players": [row for row in ledger if row["resulting_state"] != "applied"],
        "rows": ledger,
    }
    return manifest, materialisation, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season-package", type=Path, required=True)
    parser.add_argument("--old-asset-manifest", type=Path, required=True)
    parser.add_argument("--old-materialisation", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--output-materialisation", type=Path, required=True)
    parser.add_argument("--output-receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = rebind(
            package=json.loads(args.season_package.read_text(encoding="utf-8")),
            old_manifest=json.loads(args.old_asset_manifest.read_text(encoding="utf-8")),
            old_materialisation=json.loads(args.old_materialisation.read_text(encoding="utf-8")),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RebindError) as exc:
        parser.error(str(exc))
    for path, value in zip(
        (args.output_manifest, args.output_materialisation, args.output_receipt), result,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_bytes(value))
    print(json.dumps(result[2]["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
