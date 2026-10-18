#!/usr/bin/env python3
"""Bind English mode-0 authoring input to clean-base carriers and merge V2.

The authoring document intentionally contains no JUG or ENT allocations.  This
adapter performs that binary-dependent allocation without modifying the base
tree, emits a strict Season Package V2 document, and records the exact clean
FDI hashes which made the allocation valid.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.eq_team_manager_links import parse_indexed_eq_manager_links
from app.fdi_indexed import IndexedFDIFile
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as package_v2
from scripts.season_authoring_layer_integrator_v1 import _tactics_positions
from scripts.season_english_fixed_carrier_authoring_v1 import COMPILER_SCHEMA


SCHEMA = "pm99-english-mode0-package-adapter-receipt-v1"
POSITION_ROLE = {"G": [0], "D": [4], "M": [9], "F": [12]}
POSITION_HEIGHT = {"G": 188, "D": 183, "M": 178, "F": 182}
POSITION_WEIGHT = {"G": 82, "D": 78, "M": 73, "F": 77}


class EnglishMode0AdapterError(ValueError):
    """The authoring input cannot be safely allocated on this clean base."""


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(package_v2.canonical_json_bytes(dict(value))).hexdigest()


def _read_json(path: Path, *, canonical: bool = False) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EnglishMode0AdapterError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise EnglishMode0AdapterError(f"JSON root must be an object: {path}")
    if canonical and raw != package_v2.canonical_json_bytes(value):
        raise EnglishMode0AdapterError(f"input must use canonical JSON bytes: {path}")
    return value


def _stable_id(prefix: str, value: object) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", str(value).casefold()).strip("-")
    if not token or len(token) > 60:
        token = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{token}"


def _manager_candidates(ent_data: bytes) -> list[int]:
    indexed = IndexedFDIFile.from_bytes(ent_data)
    result: list[int] = []
    for entry in indexed.entries:
        payload = entry.decode_payload(ent_data)
        marker = payload.find(b"\xdd\x63\x60")
        if marker < 0:
            marker = payload.find(b"\xdd\x63\x61")
        if marker < 2:
            continue
        try:
            compiler._patch_ent_name(payload, int(entry.record_id), "Adapter Check")
        except Exception:
            continue
        result.append(int(entry.record_id))
    return sorted(result)


def _manager_owners(eq_data: bytes) -> dict[int, set[int]]:
    result: dict[int, set[int]] = defaultdict(set)
    indexed = IndexedFDIFile.from_bytes(eq_data)
    for entry in indexed.entries:
        raw = eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        try:
            manager = parse_indexed_eq_manager_links(raw).active_manager_record_id
        except ValueError:
            continue
        if manager is not None:
            result[int(manager)].add(int(entry.record_id))
    return result


def _position(facts: Mapping[str, Any]) -> str:
    value = str(facts.get("primary_position") or facts.get("position") or "").upper()[:1]
    if value not in POSITION_ROLE:
        raise EnglishMode0AdapterError(f"unsupported player position {value!r}")
    return value


def _facts(source: Mapping[str, Any], *, start_year: int, order: int,
           proof: Mapping[str, str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    position_fallback = False
    try:
        position = _position(source)
    except EnglishMode0AdapterError:
        # Missing secondary profile facts must not prevent a sourced player
        # from being compiled.  Midfield is the neutral deterministic PM99
        # role; the fallback stays explicit in the player audit.
        position = "M"
        position_fallback = True
    values: dict[str, Any] = {
        "birth_date": source.get("birth_date"),
        "nationality": source.get("nationality"),
        "height_cm": source.get("height_cm"),
        "weight_kg": source.get("weight_kg"),
        "primary_position": position,
        "fine_roles": source.get("fine_roles") or POSITION_ROLE[position],
        "shirt_number": source.get("shirt_number"),
    }
    defaults = {
        "birth_date": f"{start_year - 25:04d}-07-01",
        # Playing in England is not evidence of English nationality. Unknown
        # remains explicit until an independent player source supplies it.
        "nationality": "UNK",
        "height_cm": POSITION_HEIGHT[position],
        "weight_kg": POSITION_WEIGHT[position],
        "shirt_number": min(order, 99),
    }
    fallbacks: list[dict[str, Any]] = []
    for field in sorted(defaults):
        if values[field] is not None:
            continue
        values[field] = defaults[field]
        fallbacks.append({
            "field": field,
            "method": "deterministic-default",
            "value": defaults[field],
            "reason": "The target-season source did not publish this secondary fact.",
            "proof": dict(proof),
        })
    return values, fallbacks


def _merge_unique(base: Sequence[Mapping[str, Any]], additions: Sequence[Mapping[str, Any]],
                  *, label: str) -> list[dict[str, Any]]:
    result = {str(row["id"]): copy.deepcopy(dict(row)) for row in base}
    for row in additions:
        identity = str(row["id"])
        if identity in result and result[identity] != row:
            raise EnglishMode0AdapterError(f"{label} ID collision: {identity}")
        result[identity] = copy.deepcopy(dict(row))
    return sorted(result.values(), key=lambda row: str(row["id"]))


def build_package(*, compiler_input: Mapping[str, Any], foreign_package: Mapping[str, Any],
                  jug_data: bytes, eq_data: bytes, ent_data: bytes,
                  package_id: str,
                  allow_provisional_duplicates: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    if compiler_input.get("schema_version") != COMPILER_SCHEMA:
        raise EnglishMode0AdapterError(f"authoring input must use {COMPILER_SCHEMA}")
    season_label = str(compiler_input.get("season") or "")
    season = foreign_package.get("season")
    if not isinstance(season, Mapping) or season.get("label") != season_label:
        raise EnglishMode0AdapterError("foreign package and English input seasons differ")
    package_v2.validate_package(dict(foreign_package), strict=True)
    start_year = int(season["start_year"])
    clubs_in = compiler_input.get("clubs")
    if not isinstance(clubs_in, list) or not clubs_in:
        raise EnglishMode0AdapterError("English compiler input has no clubs")
    selected = {int(row["carrier_id"]) for row in clubs_in}
    if len(selected) != len(clubs_in):
        raise EnglishMode0AdapterError("English team carrier IDs are not unique")

    owners, _rosters, modes = compiler._source_roster_owners(eq_data)
    if any(modes.get(carrier) != 0 for carrier in selected):
        raise EnglishMode0AdapterError("every selected English team carrier must reparse as mode 0")
    jug_index = IndexedFDIFile.from_bytes(jug_data)
    jug_entries = {int(entry.record_id): entry for entry in jug_index.entries}
    reusable = sorted(
        carrier for carrier, entry in jug_entries.items()
        if entry.decode_payload(jug_data)[2:5] == b"\xdd\x63\x61"
        and owners.get(carrier)
        and all(owner in selected and modes.get(owner) == 0 for owner in owners[carrier])
    )
    if not reusable:
        raise EnglishMode0AdapterError("clean base has no exclusively selected mode-0 dd6361 carriers")
    template = max(reusable, key=lambda carrier: (jug_entries[carrier].payload_length, -carrier))
    existing_foreign_player_carriers = {int(row["carrier_id"]) for row in foreign_package["players"]}
    reusable = [carrier for carrier in reusable if carrier not in existing_foreign_player_carriers]
    next_carrier = max([*jug_entries, *owners], default=0) + 1

    manager_owners = _manager_owners(eq_data)
    foreign_manager_carriers = {int(row["carrier_id"]) for row in foreign_package["managers"]}
    managers_available = [
        carrier for carrier in _manager_candidates(ent_data)
        if carrier not in foreign_manager_carriers
        and all(owner in selected for owner in manager_owners.get(carrier, set()))
    ]
    if len(managers_available) < len(clubs_in):
        raise EnglishMode0AdapterError("clean base lacks one safe writable ENT manager per English club")

    artifact_id = "english-mode0-authoring-input"
    proof = {"grade": "source-receipt", "artifact_id": artifact_id}
    source_id = "english-mode0-authoring"
    english_clubs: list[dict[str, Any]] = []
    english_players: list[dict[str, Any]] = []
    english_managers: list[dict[str, Any]] = []
    kits: list[dict[str, Any]] = []
    portraits: list[dict[str, Any]] = []
    appended: list[dict[str, int]] = []
    allocations: list[dict[str, Any]] = []
    primary_position_fallbacks: list[dict[str, Any]] = []
    reusable_cursor = 0
    for club_row, manager_carrier in zip(
        sorted(clubs_in, key=lambda row: int(row["carrier_id"])),
        managers_available[:len(clubs_in)],
        strict=True,
    ):
        team_carrier = int(club_row["carrier_id"])
        club_name = str(club_row.get("club") or "").strip()
        club_id = _stable_id("english-club", team_carrier)
        manager_name = str((club_row.get("manager") or {}).get("manager_name") or "").strip()
        if not club_name or not manager_name:
            raise EnglishMode0AdapterError(f"team carrier {team_carrier} has no club or manager name")
        manager_id = _stable_id("english-manager", team_carrier)
        english_managers.append({
            "id": manager_id, "person_id": _stable_id("manager-person", manager_name),
            "carrier_id": manager_carrier, "name": manager_name, "policy": "write", "proof": proof,
        })
        input_players = club_row.get("players")
        if not isinstance(input_players, list) or not 16 <= len(input_players) <= 255:
            raise EnglishMode0AdapterError(
                f"{club_name} has {len(input_players) if isinstance(input_players, list) else 0} players; "
                "the proven mode-0 roster writer requires 16..255"
            )
        roster: list[str] = []
        xi: list[str] = []
        for order, player_row in enumerate(input_players, start=1):
            source_facts = player_row.get("facts")
            ratings = player_row.get("ratings")
            if not isinstance(source_facts, Mapping) or not isinstance(ratings, Mapping):
                raise EnglishMode0AdapterError(f"{club_name} player {order} is malformed")
            if reusable_cursor < len(reusable):
                player_carrier = reusable[reusable_cursor]
                append_from = None
                reusable_cursor += 1
            else:
                while next_carrier in jug_entries or next_carrier in owners or next_carrier in existing_foreign_player_carriers:
                    next_carrier += 1
                player_carrier = next_carrier
                next_carrier += 1
                append_from = template
                appended.append({"carrier_id": player_carrier, "append_from_carrier_id": template})
            player_id = _stable_id("english-player", player_carrier)
            name = str(source_facts.get("name") or "").strip()
            if not name:
                raise EnglishMode0AdapterError(f"{club_name} player {order} has no name")
            raw_position = str(
                source_facts.get("primary_position") or source_facts.get("position") or ""
            ).upper()[:1]
            if raw_position not in POSITION_ROLE:
                primary_position_fallbacks.append({
                    "club": club_name,
                    "player": name,
                    "source_order": order,
                    "fallback_position": "M",
                    "reason": "target-season source did not publish a supported primary position",
                })
            facts, fallback_rows = _facts(source_facts, start_year=start_year, order=order, proof=proof)
            rating_values = {str(key): min(99, int(value)) for key, value in ratings.items()}
            player = {
                "id": player_id, "person_id": _stable_id("player-person", f"{team_carrier}-{order}"),
                "carrier_id": player_carrier, "carrier_family": "dd6361", "club_id": club_id,
                "name": name, "source_name": name, "facts": facts,
                "ratings": {"profile": "pm99-visible-skills-v1", "values": rating_values,
                            "provenance": {"method": "English target-season rating layer", "proof_grade": "source-receipt", "source_ids": [source_id]}},
                "proof": proof,
            }
            if fallback_rows:
                player["fact_fallbacks"] = fallback_rows
            if append_from is not None:
                player["append_from_carrier_id"] = append_from
            english_players.append(player)
            roster.append(player_id)
            if bool(player_row.get("opening_xi")):
                xi.append(player_id)
            portraits.append({"player_id": player_id, "status": "native-no-photo", "proof": proof})
        if len(xi) != 11:
            raise EnglishMode0AdapterError(f"{club_name} does not declare exactly eleven opening players")
        opening = club_row.get("opening") or {}
        xi_rows = [
            {"source_position": english_players[-len(input_players) + roster.index(player_id)]["facts"]["primary_position"]}
            for player_id in xi
        ]
        english_clubs.append({
            "id": club_id, "identity_id": _stable_id("club-identity", club_name), "carrier_id": team_carrier,
            "name": club_name, "full_name": club_name, "division": str(club_row.get("division") or "English league"),
            "ground_policy": "preserve-existing-mode1", "capacity_policy": "preserve-existing-mode1",
            # Finance is not part of the authoring contract.  Use the same
            # deterministic neutral value for every mode-0 carrier; unlike a
            # zero value this round-trips through the traced MANAGPRE lane.
            "starting_finance": 20_000_000, "manager_id": manager_id, "roster_player_ids": roster,
            "opening": {"fixture_date": str(opening.get("fixture_date")), "starting_xi_player_ids": xi,
                        "substitute_player_ids": [player_id for player_id in roster if player_id not in xi][:7],
                        "formation": str(opening.get("formation")),
                        "tactics_positions": _tactics_positions(str(opening.get("formation")), xi_rows), "proof": proof},
            "proof": proof,
        })
        kits.append({"club_id": club_id, "artifact_ids": [artifact_id], "policy": "write", "proof": proof})
        allocations.append({"team_carrier_id": team_carrier, "manager_carrier_id": manager_carrier,
                            "player_carrier_ids": [int(player["carrier_id"]) for player in english_players[-len(input_players):]]})

    package = copy.deepcopy(dict(foreign_package))
    if any(int(row["carrier_id"]) in selected for row in package["clubs"]):
        raise EnglishMode0AdapterError("foreign package overlaps an English team carrier")
    package["package_id"] = package_id
    package["scope"] = {**package["scope"], "countries": sorted(set(package["scope"]["countries"]) | {"ENG"})}
    package["artifacts"] = _merge_unique(package["artifacts"], [{"id": artifact_id, "kind": "season-input", "sha256": _digest(compiler_input)}], label="artifact")
    package["sources"] = _merge_unique(package["sources"], [{"id": source_id, "title": "English fixed-carrier authoring input", "proof_grade": "source-receipt", "evidence_artifact_id": artifact_id}], label="source")
    package["proofs"] = _merge_unique(package["proofs"], [{"id": "english-mode0-carrier-proof", "grade": "source-receipt", "artifact_id": artifact_id, "covers": ["English mode-0 teams", "exclusive dd6361 player allocation", "writable ENT manager allocation"]}], label="proof")
    package["clubs"] = sorted([*package["clubs"], *english_clubs], key=lambda row: str(row["id"]))
    package["players"] = sorted([*package["players"], *english_players], key=lambda row: str(row["id"]))
    package["managers"] = sorted([*package["managers"], *english_managers], key=lambda row: str(row["id"]))
    package["assets"]["kits"] = sorted([*package["assets"]["kits"], *kits], key=lambda row: str(row["club_id"]))
    package["assets"]["portraits"] = sorted([*package["assets"]["portraits"], *portraits], key=lambda row: str(row["player_id"]))
    package["migration"] = {"status": "native-v2", "source_artifact_ids": sorted(set(package["migration"]["source_artifact_ids"]) | {artifact_id}), "known_gaps": []}
    try:
        package_v2.validate_package(package, strict=not allow_provisional_duplicates)
    except package_v2.PackageValidationError as exc:
        raise EnglishMode0AdapterError(str(exc)) from exc
    receipt = {
        "schema_version": SCHEMA, "season": season_label,
        "input_sha256": {"english_compiler_input": _digest(compiler_input), "foreign_package": _digest(foreign_package),
                         "JUG98030.FDI": hashlib.sha256(jug_data).hexdigest(), "EQ98030.FDI": hashlib.sha256(eq_data).hexdigest(),
                         "ENT98030.FDI": hashlib.sha256(ent_data).hexdigest()},
        "output_package_sha256": _digest(package), "clubs": len(english_clubs), "players": len(english_players),
        "managers": len(english_managers), "reused_player_carriers": reusable_cursor,
        "appended_player_carriers": appended, "allocations": allocations,
        "primary_position_fallbacks": primary_position_fallbacks,
        "policy": "read-only-preflight-exclusive-selected-mode0-dd6361-and-safe-ent-v1",
        "provisional_duplicate_normalisation_required": allow_provisional_duplicates,
    }
    return package, receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--english-input", required=True, type=Path)
    parser.add_argument("--foreign-package", required=True, type=Path)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--package-id", required=True)
    parser.add_argument("--output-package", required=True, type=Path)
    parser.add_argument("--output-receipt", required=True, type=Path)
    parser.add_argument("--allow-provisional-duplicates", action="store_true")
    args = parser.parse_args(argv)
    english = _read_json(args.english_input, canonical=True)
    foreign = _read_json(args.foreign_package, canonical=True)
    dbdat = args.base_tree / "DBDAT"
    package, receipt = build_package(
        compiler_input=english, foreign_package=foreign,
        jug_data=(dbdat / "JUG98030.FDI").read_bytes(), eq_data=(dbdat / "EQ98030.FDI").read_bytes(),
        ent_data=(dbdat / "ENT98030.FDI").read_bytes(), package_id=args.package_id,
        allow_provisional_duplicates=args.allow_provisional_duplicates,
    )
    package_v2.write_canonical_package(args.output_package, package)
    args.output_receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output_receipt.write_bytes(package_v2.canonical_json_bytes(receipt))
    print(json.dumps({"clubs": receipt["clubs"], "players": receipt["players"], "appended": len(receipt["appended_player_carriers"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
