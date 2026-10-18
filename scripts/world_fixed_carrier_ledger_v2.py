#!/usr/bin/env python3
"""Create and audit reproducible foreign fixed-carrier season ledgers.

This is deliberately an *authoring* boundary, not a PM99 writer.  It captures
the 451 mode-1 carrier slots PM99 already owns, lets a season ledger attach
historical club/player/manager sources to those immutable slots, and reports
whether the content is sufficiently complete for the narrow V2 compiler.

It has no field or command for country, division, draw pool, competition or
membership.  The database format has no proven foreign topology writer, so a
world source ledger must not grow one by implication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.eq_jug_linked import parse_eq_external_team_roster_payload  # noqa: E402
from app.eq_team_indexed_metadata import extract_indexed_team_payload_metadata  # noqa: E402
from app.eq_team_manager_links import parse_indexed_eq_manager_links  # noqa: E402
from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from app.models import PlayerRecord  # noqa: E402


REGISTRY_SCHEMA = "pm99-world-fixed-carrier-registry-v2"
LEDGER_SCHEMA = "pm99-world-fixed-carrier-ledger-v2"
AUDIT_SCHEMA = "pm99-world-fixed-carrier-ledger-audit-v2"
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ISO_DATE_RE = re.compile(r"^(?:19|20)\d{2}-\d{2}-\d{2}$")
PLAYER_FACT_KEYS = {
    "birth_date",
    "nationality",
    "height_cm",
    "weight_kg",
    "primary_position",
    "fine_roles",
    "shirt_number",
}
RATING_KEYS = {
    "quality",
    "speed",
    "stamina",
    "aggression",
    "passing",
    "tackling",
    "heading",
    "shooting",
    "dribbling",
    "handling",
}
COMPLETE_PORTRAIT_STATUSES = {"applied", "native-no-photo"}
ALL_PORTRAIT_STATUSES = {*COMPLETE_PORTRAIT_STATUSES, "unresolved"}
ALL_KIT_STATUSES = {"applied", "unresolved"}


class WorldLedgerError(ValueError):
    """The registry or source ledger is incomplete, stale, or unsafe."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_canonical_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(dict(value)))


def read_canonical_json(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorldLedgerError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise WorldLedgerError(f"{label} must use canonical JSON bytes")
    return value, hashlib.sha256(raw).hexdigest()


def _require_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise WorldLedgerError(f"{label} must be a stable lower-case id")
    return value


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise WorldLedgerError(f"{label} must be a lowercase SHA-256")
    return value


def _require_nonblank(value: Any, label: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise WorldLedgerError(f"{label} must be a non-blank string of at most {maximum} characters")
    return value.strip()


def _require_sorted_unique_ids(value: Any, label: str, valid: set[str]) -> list[str]:
    if not isinstance(value, list) or not value or value != sorted(value) or len(value) != len(set(value)):
        raise WorldLedgerError(f"{label} must be a non-empty sorted unique id list")
    result = []
    for item in value:
        identity = _require_id(item, label)
        if identity not in valid:
            raise WorldLedgerError(f"{label} references unknown source {identity!r}")
        result.append(identity)
    return result


def _display_name(payload: bytes) -> str | None:
    try:
        record = PlayerRecord.from_bytes(payload, 0)
    except Exception:
        return None
    name = " ".join(str(record.name or "").split())
    return name or None


def build_registry_from_dbdat(*, dbdat: Path, registry_id: str) -> dict[str, Any]:
    """Return a portable inventory of the existing mode-1 carrier slots.

    The result intentionally records *only* structural carrier information.
    It does not infer country, league, division, selection order, or draw-pool
    membership from record order, names, or the mode byte.
    """

    _require_id(registry_id, "registry_id")
    dbdat = dbdat.expanduser().resolve()
    required = {name: dbdat / name for name in ("EQ98030.FDI", "JUG98030.FDI", "ENT98030.FDI")}
    missing = [str(path) for path in required.values() if not path.is_file() or path.is_symlink()]
    if missing:
        raise WorldLedgerError("missing safe source database file(s): " + ", ".join(missing))

    eq_data = required["EQ98030.FDI"].read_bytes()
    jug_data = required["JUG98030.FDI"].read_bytes()
    eq_index = IndexedFDIFile.from_bytes(eq_data)
    jug_index = IndexedFDIFile.from_bytes(jug_data)
    jug_entries = {entry.record_id: entry for entry in jug_index.entries}
    carriers: list[dict[str, Any]] = []
    player_occurrences: dict[int, list[dict[str, int]]] = defaultdict(list)

    for entry in sorted(eq_index.entries, key=lambda item: int(item.record_id)):
        raw = eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        try:
            metadata = extract_indexed_team_payload_metadata(raw)
        except Exception:
            continue
        if int(metadata.get("record_size") or 0) != 700 or int(metadata.get("record_mode") or -1) != 1:
            continue
        roster = parse_eq_external_team_roster_payload(raw, {})
        if roster is None:
            raise WorldLedgerError(f"mode-1 carrier {entry.record_id} has no parser-backed terminal roster")
        try:
            manager = parse_indexed_eq_manager_links(raw)
        except Exception as exc:
            raise WorldLedgerError(f"mode-1 carrier {entry.record_id} has no parser-backed manager link") from exc
        if manager.active_manager_record_id is None:
            raise WorldLedgerError(f"mode-1 carrier {entry.record_id} has no existing active manager link")

        slots: list[dict[str, Any]] = []
        for row in roster.rows:
            player_entry = jug_entries.get(int(row.player_record_id))
            if player_entry is None:
                raise WorldLedgerError(
                    f"mode-1 carrier {entry.record_id} links absent JUG carrier {row.player_record_id}"
                )
            payload = player_entry.decode_payload(jug_data)
            signature = payload[2:5].hex() if len(payload) >= 5 else ""
            family = {"dd6360": "dd6360", "dd6361": "dd6361"}.get(signature, "opaque")
            slot = {
                "slot_index": int(row.slot_index),
                "player_carrier_id": int(row.player_record_id),
                "flag": int(row.flag),
                "family": family,
                "baseline_name": _display_name(payload),
            }
            slots.append(slot)
            player_occurrences[int(row.player_record_id)].append(
                {"carrier_id": int(entry.record_id), "slot_index": int(row.slot_index)}
            )

        carriers.append(
            {
                "carrier_id": int(entry.record_id),
                "record_mode": 1,
                "baseline_club": {
                    "name": metadata.get("short_name"),
                    "full_name": metadata.get("full_club_name"),
                    "ground_name": metadata.get("stadium_name"),
                    "seated_capacity": int(metadata.get("seated_capacity") or 0),
                    "active_manager_carrier_id": int(manager.active_manager_record_id),
                },
                "roster_slots": slots,
                "topology_policy": "preserve-existing-carrier-and-roster-slots",
            }
        )

    duplicates = [
        {
            "player_carrier_id": player_id,
            "occurrences": occurrences,
        }
        for player_id, occurrences in sorted(player_occurrences.items())
        if len(occurrences) > 1
    ]
    files = {
        name: {"relative_path": f"DBDAT/{name}", "sha256": sha256_file(path), "size": path.stat().st_size}
        for name, path in sorted(required.items())
    }
    return {
        "schema_version": REGISTRY_SCHEMA,
        "registry_id": registry_id,
        "baseline": {"database_files": files},
        "topology_policy": "preserve-existing-carriers-no-country-division-or-membership-claims",
        "carriers": carriers,
        "known_baseline_duplicate_player_carriers": duplicates,
    }


def validate_registry(registry: Mapping[str, Any]) -> None:
    if set(registry) != {
        "schema_version",
        "registry_id",
        "baseline",
        "topology_policy",
        "carriers",
        "known_baseline_duplicate_player_carriers",
    }:
        raise WorldLedgerError("registry has unsupported fields")
    if registry.get("schema_version") != REGISTRY_SCHEMA:
        raise WorldLedgerError("registry schema_version is unsupported")
    _require_id(registry.get("registry_id"), "registry_id")
    if registry.get("topology_policy") != "preserve-existing-carriers-no-country-division-or-membership-claims":
        raise WorldLedgerError("registry topology policy is unsupported")
    baseline = registry.get("baseline")
    if not isinstance(baseline, dict) or set(baseline) != {"database_files"}:
        raise WorldLedgerError("registry baseline must contain only database_files")
    files = baseline.get("database_files")
    if not isinstance(files, dict) or set(files) != {"EQ98030.FDI", "JUG98030.FDI", "ENT98030.FDI"}:
        raise WorldLedgerError("registry baseline must fingerprint EQ/JUG/ENT only")
    for name, item in files.items():
        if not isinstance(item, dict) or set(item) != {"relative_path", "sha256", "size"}:
            raise WorldLedgerError(f"registry baseline {name} has unsupported fields")
        if item.get("relative_path") != f"DBDAT/{name}" or not isinstance(item.get("size"), int) or item["size"] < 1:
            raise WorldLedgerError(f"registry baseline {name} is invalid")
        _require_sha256(item.get("sha256"), f"registry baseline {name}.sha256")

    carriers = registry.get("carriers")
    if not isinstance(carriers, list) or not carriers:
        raise WorldLedgerError("registry carriers must be a non-empty list")
    carrier_ids: set[int] = set()
    player_occurrences: dict[int, list[dict[str, int]]] = defaultdict(list)
    previous = 0
    for index, carrier in enumerate(carriers):
        if not isinstance(carrier, dict) or set(carrier) != {
            "carrier_id", "record_mode", "baseline_club", "roster_slots", "topology_policy"
        }:
            raise WorldLedgerError(f"registry carriers[{index}] has unsupported fields")
        carrier_id = carrier.get("carrier_id")
        if not isinstance(carrier_id, int) or carrier_id <= previous or carrier_id in carrier_ids:
            raise WorldLedgerError("registry carriers must be carrier-id sorted and unique")
        previous = carrier_id
        carrier_ids.add(carrier_id)
        if carrier.get("record_mode") != 1 or carrier.get("topology_policy") != "preserve-existing-carrier-and-roster-slots":
            raise WorldLedgerError(f"registry carrier {carrier_id} is not a fixed mode-1 carrier")
        club = carrier.get("baseline_club")
        if not isinstance(club, dict) or set(club) != {
            "name", "full_name", "ground_name", "seated_capacity", "active_manager_carrier_id"
        }:
            raise WorldLedgerError(f"registry carrier {carrier_id} baseline club is invalid")
        if not isinstance(club.get("active_manager_carrier_id"), int) or club["active_manager_carrier_id"] < 1:
            raise WorldLedgerError(f"registry carrier {carrier_id} has no existing manager carrier")
        slots = carrier.get("roster_slots")
        if not isinstance(slots, list) or not slots:
            raise WorldLedgerError(f"registry carrier {carrier_id} has no valid roster slot list")
        for slot_index, slot in enumerate(slots):
            if not isinstance(slot, dict) or set(slot) != {
                "slot_index", "player_carrier_id", "flag", "family", "baseline_name"
            }:
                raise WorldLedgerError(f"registry carrier {carrier_id} slot {slot_index} is invalid")
            if slot.get("slot_index") != slot_index or not isinstance(slot.get("player_carrier_id"), int):
                raise WorldLedgerError(f"registry carrier {carrier_id} slots must be contiguous")
            if not isinstance(slot.get("flag"), int) or not 0 <= slot["flag"] <= 255:
                raise WorldLedgerError(f"registry carrier {carrier_id} slot {slot_index} has invalid flag")
            if slot.get("family") not in {"dd6360", "dd6361", "opaque"}:
                raise WorldLedgerError(f"registry carrier {carrier_id} slot {slot_index} has unknown player family")
            player_occurrences[int(slot["player_carrier_id"])].append(
                {"carrier_id": carrier_id, "slot_index": slot_index}
            )
    expected_duplicates = [
        {"player_carrier_id": player_id, "occurrences": occurrences}
        for player_id, occurrences in sorted(player_occurrences.items())
        if len(occurrences) > 1
    ]
    if registry.get("known_baseline_duplicate_player_carriers") != expected_duplicates:
        raise WorldLedgerError("registry baseline duplicate-player report does not match its slot table")


def initialise_ledger(*, registry: Mapping[str, Any], ledger_id: str, start_year: int) -> dict[str, Any]:
    validate_registry(registry)
    _require_id(ledger_id, "ledger_id")
    if not isinstance(start_year, int) or not 1999 <= start_year <= 2025:
        raise WorldLedgerError("start_year must be 1999..2025")
    registry_sha = hashlib.sha256(canonical_json_bytes(dict(registry))).hexdigest()
    return {
        "schema_version": LEDGER_SCHEMA,
        "ledger_id": ledger_id,
        "season": {
            "start_year": start_year,
            "end_year": start_year + 1,
            "label": f"{start_year}/{str(start_year + 1)[-2:]}",
        },
        "registry_sha256": registry_sha,
        "topology_policy": "preserve-existing-carriers-no-membership-write",
        "sources": [],
        "carrier_updates": [],
    }


def _validate_sources(ledger: Mapping[str, Any]) -> set[str]:
    sources = ledger.get("sources")
    if not isinstance(sources, list):
        raise WorldLedgerError("ledger sources must be a list")
    result: set[str] = set()
    previous = ""
    for index, source in enumerate(sources):
        if not isinstance(source, dict) or set(source) != {"id", "title", "kind", "content_sha256"}:
            raise WorldLedgerError(f"ledger sources[{index}] has unsupported fields")
        identity = _require_id(source.get("id"), f"ledger sources[{index}].id")
        if identity <= previous or identity in result:
            raise WorldLedgerError("ledger sources must be id-sorted and unique")
        previous = identity
        result.add(identity)
        _require_nonblank(source.get("title"), f"ledger sources[{index}].title")
        if source.get("kind") not in {"club", "manager", "squad", "player", "portrait", "kit", "ratings", "other"}:
            raise WorldLedgerError(f"ledger sources[{index}].kind is unsupported")
        _require_sha256(source.get("content_sha256"), f"ledger sources[{index}].content_sha256")
    return result


def _validate_player(
    *,
    row: Mapping[str, Any],
    registry_slot: Mapping[str, Any],
    source_ids: set[str],
    carrier_id: int,
    status: str,
) -> dict[str, Any]:
    expected_fields = {
        "slot_index", "player_carrier_id", "person_id", "name", "facts", "ratings", "source_ids", "portrait"
    }
    if set(row) != expected_fields:
        raise WorldLedgerError(f"carrier {carrier_id} player slot has unsupported fields")
    if row.get("slot_index") != registry_slot["slot_index"] or row.get("player_carrier_id") != registry_slot["player_carrier_id"]:
        raise WorldLedgerError(
            f"carrier {carrier_id} player slot {registry_slot['slot_index']} changes a fixed player carrier or order"
        )
    _require_id(row.get("person_id"), f"carrier {carrier_id} player person_id")
    _require_nonblank(row.get("name"), f"carrier {carrier_id} player name", maximum=255)
    facts = row.get("facts")
    if not isinstance(facts, dict) or set(facts) != PLAYER_FACT_KEYS:
        raise WorldLedgerError(f"carrier {carrier_id} player facts are incomplete")
    if not isinstance(facts.get("birth_date"), str) or not ISO_DATE_RE.fullmatch(facts["birth_date"]):
        raise WorldLedgerError(f"carrier {carrier_id} player birth_date is invalid")
    if not isinstance(facts.get("nationality"), str) or not re.fullmatch(r"[A-Z]{3}", facts["nationality"]):
        raise WorldLedgerError(f"carrier {carrier_id} player nationality is invalid")
    if not isinstance(facts.get("height_cm"), int) or not 100 <= facts["height_cm"] <= 250:
        raise WorldLedgerError(f"carrier {carrier_id} player height is invalid")
    if not isinstance(facts.get("weight_kg"), int) or not 30 <= facts["weight_kg"] <= 200:
        raise WorldLedgerError(f"carrier {carrier_id} player weight is invalid")
    if facts.get("primary_position") not in {"G", "D", "M", "F"}:
        raise WorldLedgerError(f"carrier {carrier_id} player primary position is invalid")
    if not isinstance(facts.get("fine_roles"), list) or not facts["fine_roles"] or any(
        not isinstance(role, int) or not 0 <= role <= 17 for role in facts["fine_roles"]
    ):
        raise WorldLedgerError(f"carrier {carrier_id} player fine roles are invalid")
    if not isinstance(facts.get("shirt_number"), int) or not 0 <= facts["shirt_number"] <= 99:
        raise WorldLedgerError(f"carrier {carrier_id} player shirt number is invalid")
    ratings = row.get("ratings")
    if not isinstance(ratings, dict) or set(ratings) != RATING_KEYS or any(
        not isinstance(value, int) or not 0 <= value <= 99 for value in ratings.values()
    ):
        raise WorldLedgerError(f"carrier {carrier_id} player ratings are incomplete")
    _require_sorted_unique_ids(row.get("source_ids"), f"carrier {carrier_id} player source_ids", source_ids)
    portrait = row.get("portrait")
    if not isinstance(portrait, dict) or not set(portrait) <= {"status", "source_ids", "reason"} or "status" not in portrait:
        raise WorldLedgerError(f"carrier {carrier_id} player portrait is invalid")
    portrait_status = portrait.get("status")
    if portrait_status not in ALL_PORTRAIT_STATUSES:
        raise WorldLedgerError(f"carrier {carrier_id} player portrait status is invalid")
    if portrait_status == "applied":
        _require_sorted_unique_ids(portrait.get("source_ids"), f"carrier {carrier_id} portrait source_ids", source_ids)
        if "reason" in portrait:
            raise WorldLedgerError(f"carrier {carrier_id} applied portrait must not include a no-photo reason")
    elif portrait_status == "native-no-photo":
        _require_nonblank(portrait.get("reason"), f"carrier {carrier_id} native no-photo reason")
        if portrait.get("source_ids", []) not in ([], None):
            _require_sorted_unique_ids(portrait.get("source_ids"), f"carrier {carrier_id} no-photo source_ids", source_ids)
    elif status == "complete":
        raise WorldLedgerError(f"complete carrier {carrier_id} cannot leave a portrait unresolved")
    return dict(row)


def _validate_kit(*, kit: Any, source_ids: set[str], carrier_id: int, status: str) -> None:
    """Require a deliberate kit disposition for every completed club carrier.

    A portrait has a safe native fallback; a historically wrong inherited kit
    does not. Therefore a complete carrier must name approved era-specific kit
    source material. Draft/blocked rows can show the gap explicitly. Bitmap
    conversion and archive writing remain a separate asset stage.
    """
    if not isinstance(kit, dict) or not set(kit) <= {"status", "source_ids", "reason"} or "status" not in kit:
        raise WorldLedgerError(f"carrier {carrier_id} kit is invalid")
    kit_status = kit.get("status")
    if kit_status not in ALL_KIT_STATUSES:
        raise WorldLedgerError(f"carrier {carrier_id} kit status is invalid")
    if kit_status == "applied":
        _require_sorted_unique_ids(kit.get("source_ids"), f"carrier {carrier_id} kit source_ids", source_ids)
        if "reason" in kit:
            raise WorldLedgerError(f"carrier {carrier_id} applied kit must not include an unresolved reason")
    else:
        _require_nonblank(kit.get("reason"), f"carrier {carrier_id} unresolved kit reason")
        if kit.get("source_ids", []) not in ([], None):
            _require_sorted_unique_ids(kit.get("source_ids"), f"carrier {carrier_id} unresolved kit source_ids", source_ids)
        if status == "complete":
            raise WorldLedgerError(f"complete carrier {carrier_id} cannot leave a kit unresolved")


def validate_ledger(*, registry: Mapping[str, Any], ledger: Mapping[str, Any]) -> None:
    validate_registry(registry)
    expected_fields = {
        "schema_version", "ledger_id", "season", "registry_sha256", "topology_policy", "sources", "carrier_updates"
    }
    if set(ledger) != expected_fields:
        raise WorldLedgerError("ledger has unsupported fields; topology fields are deliberately absent")
    if ledger.get("schema_version") != LEDGER_SCHEMA:
        raise WorldLedgerError("ledger schema_version is unsupported")
    _require_id(ledger.get("ledger_id"), "ledger_id")
    season = ledger.get("season")
    if not isinstance(season, dict) or set(season) != {"start_year", "end_year", "label"}:
        raise WorldLedgerError("ledger season is invalid")
    start_year = season.get("start_year")
    if not isinstance(start_year, int) or not 1999 <= start_year <= 2025 or season.get("end_year") != start_year + 1:
        raise WorldLedgerError("ledger season year range is invalid")
    if season.get("label") != f"{start_year}/{str(start_year + 1)[-2:]}":
        raise WorldLedgerError("ledger season label is invalid")
    expected_registry_sha = hashlib.sha256(canonical_json_bytes(dict(registry))).hexdigest()
    if ledger.get("registry_sha256") != expected_registry_sha:
        raise WorldLedgerError("ledger is locked to a different fixed-carrier registry")
    if ledger.get("topology_policy") != "preserve-existing-carriers-no-membership-write":
        raise WorldLedgerError("ledger topology policy is invalid")
    source_ids = _validate_sources(ledger)

    registry_by_carrier = {int(row["carrier_id"]): row for row in registry["carriers"]}
    updates = ledger.get("carrier_updates")
    if not isinstance(updates, list):
        raise WorldLedgerError("ledger carrier_updates must be a list")
    seen_carriers: set[int] = set()
    club_identities: dict[str, int] = {}
    manager_people: dict[str, int] = {}
    player_people: dict[str, int] = {}
    player_payloads: dict[int, bytes] = {}
    previous = 0
    for index, update in enumerate(updates):
        if not isinstance(update, dict) or set(update) != {"carrier_id", "status", "club", "manager", "players", "kit", "blockers"}:
            raise WorldLedgerError(f"carrier update {index} has unsupported fields")
        carrier_id = update.get("carrier_id")
        if not isinstance(carrier_id, int) or carrier_id <= previous or carrier_id in seen_carriers:
            raise WorldLedgerError("carrier updates must be carrier-id sorted and unique")
        previous = carrier_id
        seen_carriers.add(carrier_id)
        registry_carrier = registry_by_carrier.get(carrier_id)
        if registry_carrier is None:
            raise WorldLedgerError(f"carrier update {carrier_id} does not exist in the fixed registry")
        status = update.get("status")
        if status not in {"draft", "blocked", "complete"}:
            raise WorldLedgerError(f"carrier update {carrier_id} has invalid status")
        blockers = update.get("blockers")
        if not isinstance(blockers, list) or blockers != sorted(blockers) or any(
            not isinstance(blocker, str) or not blocker.strip() for blocker in blockers
        ):
            raise WorldLedgerError(f"carrier update {carrier_id} blockers must be a sorted string list")
        if status == "blocked" and not blockers:
            raise WorldLedgerError(f"blocked carrier {carrier_id} needs an explicit blocker")
        if status == "complete" and blockers:
            raise WorldLedgerError(f"complete carrier {carrier_id} cannot retain blockers")

        club = update.get("club")
        if not isinstance(club, dict) or set(club) != {
            "identity_key", "name", "full_name", "ground_name", "seated_capacity", "source_ids"
        }:
            raise WorldLedgerError(f"carrier update {carrier_id} club has unsupported or missing fields")
        club_identity = _require_id(club.get("identity_key"), f"carrier {carrier_id} club identity_key")
        if club_identity in club_identities:
            raise WorldLedgerError(
                f"club identity {club_identity} is assigned to both carriers {club_identities[club_identity]} and {carrier_id}"
            )
        club_identities[club_identity] = carrier_id
        for key in ("name", "full_name", "ground_name"):
            _require_nonblank(club.get(key), f"carrier {carrier_id} club {key}", maximum=255)
        if not isinstance(club.get("seated_capacity"), int) or not 0 <= club["seated_capacity"] <= 2_000_000:
            raise WorldLedgerError(f"carrier {carrier_id} club seated_capacity is invalid")
        _require_sorted_unique_ids(club.get("source_ids"), f"carrier {carrier_id} club source_ids", source_ids)

        manager = update.get("manager")
        if not isinstance(manager, dict) or set(manager) != {"carrier_id", "person_id", "name", "source_ids"}:
            raise WorldLedgerError(f"carrier {carrier_id} manager is invalid")
        if manager.get("carrier_id") != registry_carrier["baseline_club"]["active_manager_carrier_id"]:
            raise WorldLedgerError(
                f"carrier {carrier_id} changes manager carrier; the fixed-carrier ledger does not relink managers"
            )
        manager_person = _require_id(manager.get("person_id"), f"carrier {carrier_id} manager person_id")
        prior_manager_carrier = manager_people.get(manager_person)
        if prior_manager_carrier is not None and prior_manager_carrier != int(manager["carrier_id"]):
            raise WorldLedgerError(
                f"manager {manager_person} is assigned to different ENT carriers {prior_manager_carrier} and {manager['carrier_id']}"
            )
        manager_people[manager_person] = int(manager["carrier_id"])
        _require_nonblank(manager.get("name"), f"carrier {carrier_id} manager name", maximum=255)
        _require_sorted_unique_ids(manager.get("source_ids"), f"carrier {carrier_id} manager source_ids", source_ids)

        _validate_kit(kit=update.get("kit"), source_ids=source_ids, carrier_id=carrier_id, status=status)

        players = update.get("players")
        if not isinstance(players, list):
            raise WorldLedgerError(f"carrier update {carrier_id} players must be a list")
        slots = registry_carrier["roster_slots"]
        if status == "complete" and len(players) != len(slots):
            raise WorldLedgerError(f"complete carrier {carrier_id} must account for every existing roster slot")
        if len(players) > len(slots):
            raise WorldLedgerError(f"carrier update {carrier_id} has too many player rows")
        previous_slot = -1
        for player in players:
            if not isinstance(player, dict) or not isinstance(player.get("slot_index"), int):
                raise WorldLedgerError(f"carrier update {carrier_id} player rows need integer slot_index values")
            slot_index = int(player["slot_index"])
            if not 0 <= slot_index < len(slots) or slot_index <= previous_slot:
                raise WorldLedgerError(
                    f"carrier update {carrier_id} player rows must use unique ascending existing slot indexes"
                )
            previous_slot = slot_index
            normalised = _validate_player(
                row=player,
                registry_slot=slots[slot_index],
                source_ids=source_ids,
                carrier_id=carrier_id,
                status=status,
            )
            person_id = str(normalised["person_id"])
            player_carrier_id = int(normalised["player_carrier_id"])
            earlier_person = player_people.get(person_id)
            if earlier_person is not None and earlier_person != player_carrier_id:
                raise WorldLedgerError(
                    f"player person {person_id} is assigned to different JUG carriers {earlier_person} and {player_carrier_id}"
                )
            player_people[person_id] = player_carrier_id
            canonical_payload = canonical_json_bytes(normalised)
            earlier_payload = player_payloads.get(player_carrier_id)
            if earlier_payload is not None and earlier_payload != canonical_payload:
                raise WorldLedgerError(
                    f"shared baseline JUG carrier {player_carrier_id} has conflicting historical identities/content"
                )
            player_payloads[player_carrier_id] = canonical_payload


def audit_ledger(*, registry: Mapping[str, Any], ledger: Mapping[str, Any]) -> dict[str, Any]:
    """Return a machine-readable coverage and blocker report without writing PM99."""

    validate_ledger(registry=registry, ledger=ledger)
    updates = {int(row["carrier_id"]): row for row in ledger["carrier_updates"]}
    all_carriers = [int(row["carrier_id"]) for row in registry["carriers"]]
    status_counts: Counter[str] = Counter()
    portrait_counts: Counter[str] = Counter()
    kit_counts: Counter[str] = Counter()
    complete_slots = 0
    incomplete_carriers: list[int] = []
    for carrier in registry["carriers"]:
        carrier_id = int(carrier["carrier_id"])
        update = updates.get(carrier_id)
        status = str(update["status"]) if update is not None else "unassigned"
        status_counts[status] += 1
        if status != "complete":
            incomplete_carriers.append(carrier_id)
        if update is not None:
            kit_counts[str(update["kit"]["status"])] += 1
            for player in update["players"]:
                portrait_counts[str(player["portrait"]["status"])] += 1
            if status == "complete":
                complete_slots += len(update["players"])
    blockers: list[dict[str, Any]] = []
    if incomplete_carriers:
        blockers.append(
            {
                "code": "world-content-incomplete",
                "carrier_count": len(incomplete_carriers),
                "carrier_ids": incomplete_carriers,
                "message": "Every foreign fixed carrier needs a complete sourced update before a world release.",
            }
        )
    duplicates = registry["known_baseline_duplicate_player_carriers"]
    if duplicates:
        blockers.append(
            {
                "code": "baseline-shared-player-carriers",
                "player_carrier_count": len(duplicates),
                "players": duplicates,
                "message": "Shared baseline JUG carriers must receive one consistent historical identity or remain explicitly blocked.",
            }
        )
    return {
        "schema_version": AUDIT_SCHEMA,
        "ledger_id": ledger["ledger_id"],
        "season": ledger["season"],
        "registry_sha256": ledger["registry_sha256"],
        "coverage": {
            "foreign_carrier_total": len(all_carriers),
            "carrier_status_counts": dict(sorted(status_counts.items())),
            "complete_player_slot_count": complete_slots,
            "kit_status_counts": dict(sorted(kit_counts.items())),
            "portrait_status_counts": dict(sorted(portrait_counts.items())),
        },
        "blockers": blockers,
        "scope_exclusions": [
            {
                "code": "foreign-topology-preserved",
                "message": "Country, division, draw-pool and competition membership are deliberately preserved. They are not requirements for an in-place world-content release.",
            }
        ],
    }


def _command_init_registry(args: argparse.Namespace) -> int:
    registry = build_registry_from_dbdat(dbdat=args.dbdat, registry_id=args.registry_id)
    validate_registry(registry)
    write_canonical_json(args.output, registry)
    print(json.dumps({"output": str(args.output), "carrier_count": len(registry["carriers"])}, sort_keys=True))
    return 0


def _command_init_ledger(args: argparse.Namespace) -> int:
    registry, _ = read_canonical_json(args.registry, label="fixed-carrier registry")
    ledger = initialise_ledger(registry=registry, ledger_id=args.ledger_id, start_year=args.start_year)
    write_canonical_json(args.output, ledger)
    print(json.dumps({"output": str(args.output), "registry_sha256": ledger["registry_sha256"]}, sort_keys=True))
    return 0


def _command_validate(args: argparse.Namespace) -> int:
    registry, _ = read_canonical_json(args.registry, label="fixed-carrier registry")
    ledger, _ = read_canonical_json(args.ledger, label="world content ledger")
    validate_ledger(registry=registry, ledger=ledger)
    print("world fixed-carrier ledger validation passed")
    return 0


def _command_audit(args: argparse.Namespace) -> int:
    registry, _ = read_canonical_json(args.registry, label="fixed-carrier registry")
    ledger, _ = read_canonical_json(args.ledger, label="world content ledger")
    report = audit_ledger(registry=registry, ledger=ledger)
    write_canonical_json(args.output, report)
    print(json.dumps(report["coverage"], sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init_registry = sub.add_parser("init-registry", help="read a baseline and emit its mode-1 fixed slots")
    init_registry.add_argument("--dbdat", type=Path, required=True)
    init_registry.add_argument("--registry-id", required=True)
    init_registry.add_argument("--output", type=Path, required=True)
    init_registry.set_defaults(handler=_command_init_registry)
    init_ledger = sub.add_parser("init-ledger", help="create an empty season ledger locked to a registry")
    init_ledger.add_argument("--registry", type=Path, required=True)
    init_ledger.add_argument("--ledger-id", required=True)
    init_ledger.add_argument("--start-year", type=int, required=True)
    init_ledger.add_argument("--output", type=Path, required=True)
    init_ledger.set_defaults(handler=_command_init_ledger)
    validate = sub.add_parser("validate", help="validate source data against its fixed carrier registry")
    validate.add_argument("--registry", type=Path, required=True)
    validate.add_argument("--ledger", type=Path, required=True)
    validate.set_defaults(handler=_command_validate)
    audit = sub.add_parser("audit", help="emit deterministic coverage and blocker report")
    audit.add_argument("--registry", type=Path, required=True)
    audit.add_argument("--ledger", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    audit.set_defaults(handler=_command_audit)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except WorldLedgerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
