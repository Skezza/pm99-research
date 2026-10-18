#!/usr/bin/env python3
"""Prefill review-only 2015/16 foreign fixed-carrier ledger rows from FIFA 16.

The local FIFA 16 player snapshot is useful historical input, but it is not a
club, manager, kit, portrait, opening-lineup or competition-membership source.
This command turns only *unambiguous exact present-name matches* into
``blocked`` ledger rows.  Each row preserves the approved PM99 carrier and
roster slot IDs, records the FIFA facts/ratings candidates, and names every
missing decision as a blocker.

It never writes a PM99 file.  It deliberately does not turn a string match
into a claim about a foreign division or draw pool, and it refuses to choose
between two PM99 carriers which normalise to the same current club name.

The output is therefore a useful, deterministic review starting point for a
season package, not a release candidate.  A future source-ledger amendment
must replace every ``Unresolved 2015 ...`` placeholder and clear every
blocker before a carrier can become ``complete``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from scripts import world_fixed_carrier_ledger_v2 as ledger  # noqa: E402
from scripts.audit_world_2015_source_coverage import strict_club_key  # noqa: E402


REPORT_SCHEMA = "pm99-world-fifa16-draft-prefill-report-v1"
FIFA_SOURCE_ID = "fifa16-player-snapshot"
REGISTRY_SOURCE_ID = "fixed-carrier-registry"
REQUIRED_COLUMNS = {
    "player_id",
    "name",
    "club",
    "nationality",
    "height",
    "weight",
    "birthdate",
    "rating",
    "sprint_speed",
    "stamina",
    "aggression",
    "short_pass",
    "stand_tackle",
    "heading",
    "finishing",
    "dribbling",
    "gk_handling",
    "preferred_positions",
    "club_kit_number",
}
MISSING_VALUES = {"", "na", "n/a", "null", "none"}

# PM99 uses its own 1998 country table, so this is deliberately a translation
# table, rather than asserting that FIFA's strings are PM99 country codes.
# ``XXX`` remains an explicit compiler/review blocker and the report retains
# the original FIFA nationality string for every such row.
FIFA_NATIONALITY_TO_PM99 = {
    "albania": "ALB", "algeria": "ALG", "angola": "ANG", "argentina": "ARG",
    "armenia": "ARM", "australia": "AUS", "austria": "AUT", "azerbaijan": "AZE",
    "belarus": "BLR", "belgium": "BEL", "benin": "BEN", "bolivia": "BOL",
    "bosnia & herzegovina": "BOS", "bosnia and herzegovina": "BOS", "bosnia herzegovina": "BOS", "brazil": "BRA",
    "bulgaria": "BUL", "burkina faso": "BFA", "cameroon": "CMR", "canada": "CAN",
    "cape verde": "CPV", "chile": "CHI", "colombia": "COL", "congo": "CGO",
    "costa rica": "CRC", "croatia": "CRO", "czech republic": "CZE", "denmark": "DEN",
    "dr congo": "COD", "ecuador": "ECU", "egypt": "EGY", "england": "ENG",
    "estonia": "EST", "finland": "FIN", "france": "FRA", "gabon": "GAB",
    "gambia": "GAM", "georgia": "GEO", "germany": "GER", "ghana": "GHA",
    "greece": "GRE", "guinea": "GUI", "hungary": "HUN", "iceland": "ISL",
    "iran": "IRN", "iraq": "IRQ", "israel": "ISR", "italy": "ITA", "ivory coast": "CIV",
    "jamaica": "JAM", "japan": "JPN", "kenya": "KEN", "korea republic": "KOR",
    "latvia": "LVA", "liberia": "LBR", "lithuania": "LTU", "mali": "MLI",
    "mexico": "MEX", "moldova": "MDA", "montenegro": "MNE", "morocco": "MAR",
    "netherlands": "NED", "new zealand": "NZL", "nigeria": "NGA",
    "northern ireland": "NIR", "north macedonia": "MKD", "norway": "NOR",
    "paraguay": "PAR", "peru": "PER", "poland": "POL", "portugal": "POR",
    "republic of ireland": "IRL", "romania": "ROU", "russia": "RUS", "scotland": "SCO",
    "senegal": "SEN", "serbia": "SRB", "sierra leone": "SLE", "slovakia": "SVK",
    "slovenia": "SVN", "south africa": "RSA", "spain": "ESP", "sweden": "SWE",
    "switzerland": "SUI", "togo": "TOG", "trinidad and tobago": "TRI", "tunisia": "TUN",
    "turkey": "TUR", "uganda": "UGA", "ukraine": "UKR", "united states": "USA",
    "uruguay": "URU", "venezuela": "VEN", "wales": "WAL", "zimbabwe": "ZIM",
}


class FIFA16DraftError(ValueError):
    """The snapshot or ledger is not a safe prefill input."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_canonical_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(dict(value)))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return "".join(character for character in text.casefold() if character.isalnum())


def _normalise_label(value: object) -> str:
    """Normalise a country label while retaining its word boundaries."""

    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(text.casefold().split())


def _present(value: object) -> bool:
    return str(value or "").strip().casefold() not in MISSING_VALUES


def _integer(value: object, *, field: str, minimum: int, maximum: int) -> int:
    if not _present(value):
        raise FIFA16DraftError(f"FIFA row has no {field}")
    try:
        parsed = int(float(str(value)))
    except ValueError as exc:
        raise FIFA16DraftError(f"FIFA row has invalid {field}: {value!r}") from exc
    if not minimum <= parsed <= maximum:
        raise FIFA16DraftError(f"FIFA row {field} is outside {minimum}..{maximum}: {parsed}")
    return parsed


def _player_position(row: Mapping[str, str]) -> tuple[str, list[int]]:
    """Map FIFA's public position token into an explicitly provisional PM99 role.

    The source only supports the broad family with confidence.  Mode-1
    secondary-role writes are not runtime-proven, so the one-role value below
    exists solely to make the blocked ledger structurally complete.  It must
    be replaced with a reviewed PM99 role decision before compilation.
    """

    tokens = {
        token.upper()
        for token in re.split(r"[,/\\s]+", str(row.get("preferred_positions") or ""))
        if token.strip()
    }
    if "GK" in tokens:
        return "G", [0]
    if tokens & {"CB", "LB", "RB", "LWB", "RWB", "LCB", "RCB", "SW"}:
        return "D", [4]
    if tokens & {"ST", "CF", "LF", "RF", "LS", "RS"}:
        return "F", [12]
    return "M", [9]


def _fifa_player_facts(row: Mapping[str, str]) -> tuple[dict[str, Any], dict[str, int], str | None]:
    position, roles = _player_position(row)
    nationality_label = str(row.get("nationality") or "").strip()
    nationality = FIFA_NATIONALITY_TO_PM99.get(_normalise_label(nationality_label), "XXX")
    shirt_number = _integer(row.get("club_kit_number"), field="club_kit_number", minimum=0, maximum=99)
    facts = {
        "birth_date": str(row.get("birthdate") or "").strip(),
        "nationality": nationality,
        "height_cm": _integer(row.get("height"), field="height", minimum=100, maximum=250),
        "weight_kg": _integer(row.get("weight"), field="weight", minimum=30, maximum=200),
        "primary_position": position,
        "fine_roles": roles,
        "shirt_number": shirt_number,
    }
    if not re.fullmatch(r"19\d{2}-\d{2}-\d{2}", facts["birth_date"]):
        raise FIFA16DraftError(f"FIFA row has invalid birthdate: {facts['birth_date']!r}")
    ratings = {
        "quality": _integer(row.get("rating"), field="rating", minimum=0, maximum=99),
        "speed": _integer(row.get("sprint_speed"), field="sprint_speed", minimum=0, maximum=99),
        "stamina": _integer(row.get("stamina"), field="stamina", minimum=0, maximum=99),
        "aggression": _integer(row.get("aggression"), field="aggression", minimum=0, maximum=99),
        "passing": _integer(row.get("short_pass"), field="short_pass", minimum=0, maximum=99),
        "tackling": _integer(row.get("stand_tackle"), field="stand_tackle", minimum=0, maximum=99),
        "heading": _integer(row.get("heading"), field="heading", minimum=0, maximum=99),
        "shooting": _integer(row.get("finishing"), field="finishing", minimum=0, maximum=99),
        "dribbling": _integer(row.get("dribbling"), field="dribbling", minimum=0, maximum=99),
        "handling": _integer(row.get("gk_handling"), field="gk_handling", minimum=0, maximum=99),
    }
    return facts, ratings, nationality_label if nationality == "XXX" else None


def read_fifa16_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise FIFA16DraftError("FIFA CSV has no header")
        missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames))
        if missing:
            raise FIFA16DraftError("FIFA CSV misses required columns: " + ", ".join(missing))
        rows = [dict(row) for row in reader]
    ids = [str(row.get("player_id") or "").strip() for row in rows]
    if not rows or any(not value.isdigit() for value in ids) or len(ids) != len(set(ids)):
        raise FIFA16DraftError("FIFA CSV must have non-empty unique numeric player_id values")
    return rows


def _rows_by_strict_club(rows: Iterable[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = strict_club_key(row.get("club"))
        if key:
            result[key].append(row)
    return dict(result)


def _carrier_keys(registry: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for carrier in registry["carriers"]:
        key = strict_club_key(carrier["baseline_club"].get("name"))
        if key:
            result[key].append(dict(carrier))
    return dict(result)


def _slot_sort_key(row: Mapping[str, str]) -> tuple[int, int]:
    # This is deliberately not a claim about PM99's opening squad order.  It
    # only makes the prefill repeatable until an opening-XI/tactics source
    # supplies the actual order.
    number = _integer(row.get("club_kit_number"), field="club_kit_number", minimum=0, maximum=99)
    return number, _integer(row.get("player_id"), field="player_id", minimum=1, maximum=99_999_999)


def _provisional_player_row(slot: Mapping[str, Any], source: Mapping[str, str]) -> tuple[dict[str, Any], str | None]:
    facts, ratings, unsupported_nationality = _fifa_player_facts(source)
    return {
        "slot_index": int(slot["slot_index"]),
        "player_carrier_id": int(slot["player_carrier_id"]),
        "person_id": f"fifa16-player-{int(str(source['player_id']))}",
        "name": str(source["name"]).strip(),
        "facts": facts,
        "ratings": ratings,
        "source_ids": [FIFA_SOURCE_ID],
        "portrait": {"status": "unresolved"},
    }, unsupported_nationality


def _blocked_update(carrier: Mapping[str, Any], source_rows: list[dict[str, str]]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    carrier_id = int(carrier["carrier_id"])
    usable: list[dict[str, str]] = []
    for row in source_rows:
        try:
            _fifa_player_facts(row)
        except FIFA16DraftError:
            continue
        usable.append(row)
    usable.sort(key=_slot_sort_key)
    slots = list(carrier["roster_slots"])
    if len(usable) < len(slots):
        raise FIFA16DraftError("candidate club has fewer complete FIFA player rows than fixed PM99 slots")
    chosen = usable[: len(slots)]
    if len({str(row["player_id"]) for row in chosen}) != len(chosen):
        raise FIFA16DraftError("candidate club has duplicate FIFA player IDs")

    players: list[dict[str, Any]] = []
    unsupported: list[dict[str, str]] = []
    for slot, source in zip(slots, chosen, strict=True):
        player, nationality = _provisional_player_row(slot, source)
        players.append(player)
        if nationality is not None:
            unsupported.append({
                "carrier_id": str(carrier_id),
                "player_id": str(source["player_id"]),
                "player_name": str(source["name"]),
                "fifa_nationality": nationality,
            })
    club_name = str(chosen[0]["club"]).strip()
    blockers = {
        "2015-club-ground-and-capacity-source-required",
        "2015-era-kit-source-required",
        "2015-manager-source-required",
        "2015-portrait-or-no-photo-decision-required",
        "fifa16-slot-allocation-proposal-requires-review",
        "foreign-competition-membership-preserve-only",
        "foreign-mode1-opening-lineup-and-tactics-source-required",
        "foreign-mode1-role-position-and-shirt-number-write-not-proven",
    }
    if unsupported:
        blockers.add("player-nationality-not-representable-in-current-pm99-country-table")
    update = {
        "carrier_id": carrier_id,
        "status": "blocked",
        "club": {
            "identity_key": f"draft-carrier-{carrier_id}",
            "name": club_name,
            "full_name": club_name,
            # Do not silently retain a 1998 ground/capacity: placeholders make
            # an omitted historical source visible in review and fail closed.
            "ground_name": "Unresolved 2015 ground",
            "seated_capacity": 0,
            "source_ids": [FIFA_SOURCE_ID, REGISTRY_SOURCE_ID],
        },
        "manager": {
            "carrier_id": int(carrier["baseline_club"]["active_manager_carrier_id"]),
            "person_id": f"unresolved-manager-carrier-{int(carrier['baseline_club']['active_manager_carrier_id'])}",
            "name": "Unresolved 2015 manager",
            "source_ids": [REGISTRY_SOURCE_ID],
        },
        "kit": {
            "status": "unresolved",
            "reason": "No approved 2015/16 era-specific kit source is attached; inherited PM99 art must not be retained.",
        },
        "players": players,
        "blockers": sorted(blockers),
    }
    return update, unsupported


def build_prefilled_ledger(
    *,
    registry: Mapping[str, Any],
    base_ledger: Mapping[str, Any],
    fifa_rows: list[dict[str, str]],
    fifa_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a canonical blocked ledger and an auditable eligibility report."""

    ledger.validate_registry(registry)
    ledger.validate_ledger(registry=registry, ledger=base_ledger)
    if base_ledger["sources"] or base_ledger["carrier_updates"]:
        raise FIFA16DraftError("prefill accepts an empty, hash-locked world ledger only; merge reviewed amendments explicitly")
    if not re.fullmatch(r"[0-9a-f]{64}", fifa_sha256):
        raise FIFA16DraftError("FIFA snapshot hash must be a lower-case SHA-256")

    source_by_club = _rows_by_strict_club(fifa_rows)
    carriers_by_key = _carrier_keys(registry)
    shared_player_ids = {
        int(row["player_carrier_id"])
        for row in registry["known_baseline_duplicate_player_carriers"]
    }
    accepted_player_ids: set[int] = set()
    updates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    unsupported_nationalities: list[dict[str, str]] = []

    for carrier in registry["carriers"]:
        carrier_id = int(carrier["carrier_id"])
        key = strict_club_key(carrier["baseline_club"].get("name"))
        candidates = source_by_club.get(key, [])
        if not candidates:
            skipped.append({"carrier_id": carrier_id, "reason": "no-strict-current-club-match"})
            continue
        if len(carriers_by_key.get(key, [])) != 1:
            skipped.append({"carrier_id": carrier_id, "reason": "ambiguous-baseline-club-key"})
            continue
        source_club_names = {str(row.get("club") or "").strip() for row in candidates}
        if len(source_club_names) != 1:
            skipped.append({"carrier_id": carrier_id, "reason": "ambiguous-fifa-source-club-name"})
            continue
        slot_ids = {int(row["player_carrier_id"]) for row in carrier["roster_slots"]}
        if slot_ids & accepted_player_ids:
            skipped.append({"carrier_id": carrier_id, "reason": "shared-jug-carrier-conflicts-with-earlier-draft"})
            continue
        if any(str(row.get("family")) != "dd6360" for row in carrier["roster_slots"]):
            skipped.append({"carrier_id": carrier_id, "reason": "non-dd6360-player-family"})
            continue
        try:
            update, unsupported = _blocked_update(carrier, candidates)
        except FIFA16DraftError as exc:
            skipped.append({"carrier_id": carrier_id, "reason": str(exc)})
            continue
        # Shared baseline JUG IDs are allowed only where this prefill never
        # assigns that same JUG carrier in a second draft update.  The ledger
        # validator then enforces the same rule for later amendments.
        if (slot_ids & shared_player_ids) and (slot_ids & accepted_player_ids):
            skipped.append({"carrier_id": carrier_id, "reason": "baseline-shared-jug-carrier-conflict"})
            continue
        updates.append(update)
        accepted_player_ids.update(slot_ids)
        unsupported_nationalities.extend(unsupported)

    output = dict(base_ledger)
    output["sources"] = [
        {
            "id": FIFA_SOURCE_ID,
            "title": "Local FIFA 16 player snapshot: candidate facts, ratings and current-club strings only",
            "kind": "ratings",
            "content_sha256": fifa_sha256,
        },
        {
            "id": REGISTRY_SOURCE_ID,
            "title": "Approved PM99 fixed-carrier registry: structural IDs only, not 2015 historical evidence",
            "kind": "other",
            "content_sha256": hashlib.sha256(canonical_json_bytes(registry)).hexdigest(),
        },
    ]
    output["carrier_updates"] = updates
    ledger.validate_ledger(registry=registry, ledger=output)

    reason_counts = Counter(str(row["reason"]) for row in skipped)
    report = {
        "schema_version": REPORT_SCHEMA,
        "result": "blocked-review-prefill-created",
        "registry_sha256": hashlib.sha256(canonical_json_bytes(registry)).hexdigest(),
        "base_ledger_sha256": hashlib.sha256(canonical_json_bytes(base_ledger)).hexdigest(),
        "fifa16_player_snapshot_sha256": fifa_sha256,
        "selection_contract": {
            "club_match": "exact strict_club_key match, one PM99 carrier and one FIFA club spelling only",
            "player_selection": "ascending FIFA club kit number then FIFA player id; not an opening XI, tactical or PM99 roster-order claim",
            "slot_contract": "existing mode-1 carrier IDs, JUG IDs, slot indexes and flags are preserved",
            "write_policy": "blocked ledger only; no PM99 binary is read or written",
        },
        "coverage": {
            "foreign_carrier_count": len(registry["carriers"]),
            "strict_current_club_candidate_carrier_count": sum(
                1 for carrier in registry["carriers"]
                if strict_club_key(carrier["baseline_club"].get("name")) in source_by_club
            ),
            "blocked_prefilled_carrier_count": len(updates),
            "blocked_prefilled_player_slot_count": sum(len(row["players"]) for row in updates),
            "skipped_carrier_count": len(skipped),
            "unsupported_pm99_nationality_row_count": len(unsupported_nationalities),
        },
        "blocked_carrier_ids": [int(row["carrier_id"]) for row in updates],
        "skipped_carriers_by_reason": dict(sorted(reason_counts.items())),
        "skipped_carriers": skipped,
        "unsupported_pm99_nationality_rows": unsupported_nationalities,
        "remaining_required_before_any-complete-carrier": [
            "Capture dated club ground/capacity and manager sources.",
            "Capture an approved era-correct kit source; do not inherit 1998 art.",
            "Capture or explicitly reject a portrait for every player.",
            "Review all provisional fixed-slot player allocations against a dated squad source.",
            "Keep foreign competition membership unchanged until its writer is proven.",
            "Prove the mode-1 role, position, shirt-number, opening-lineup and tactics write contracts.",
        ],
    }
    return output, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--base-ledger", type=Path, required=True)
    parser.add_argument("--fifa16-player-csv", type=Path, required=True)
    parser.add_argument("--output-ledger", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    args = parser.parse_args(argv)
    registry, _ = ledger.read_canonical_json(args.registry, label="fixed-carrier registry")
    base_ledger, _ = ledger.read_canonical_json(args.base_ledger, label="empty world season ledger")
    fifa_path = args.fifa16_player_csv.resolve()
    output, report = build_prefilled_ledger(
        registry=registry,
        base_ledger=base_ledger,
        fifa_rows=read_fifa16_rows(fifa_path),
        fifa_sha256=sha256_file(fifa_path),
    )
    write_canonical_json(args.output_ledger, output)
    write_canonical_json(args.output_report, report)
    print(json.dumps({"ledger": str(args.output_ledger), "report": str(args.output_report), **report["coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
