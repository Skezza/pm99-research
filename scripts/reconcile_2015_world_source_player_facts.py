#!/usr/bin/env python3
"""Join dated world squads to fixed PM99 slots without writing a database.

This is the bridge between a dated squad source and a release ledger.  It
turns only the ``source-squad-ready`` proposals in the fixed-carrier draft into
a deterministic player-fact/rating review queue.  It does not assign a club to
a different country, alter a roster row, select an opening XI, or emit an FDI,
PKF or BMP file.

Each row retains the immutable target EQ/JUG slot, the exact dated source row
and the outcome of matching that player against the local FIFA 16 snapshot.
No FIFA match is silently treated as a zero or average rating: it is an
explicit ``fallback-required`` row for editorial review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA = "pm99-world-2015-source-player-reconciliation-v1"
DRAFT_SCHEMA = "pm99-world-2015-source-carrier-drafts-v1"
SOURCE_SCHEMA = "pm99-footballsquads-season-capture-v1"
MISSING_VALUES = {"", "na", "n/a", "null", "none"}


class ReconciliationError(ValueError):
    """An input violates the fixed-carrier source contract."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def normalise_name(value: object) -> str:
    """Use an accent-insensitive, token-preserving identity key.

    This is intentionally stricter than a fuzzy player search.  A historic
    season compiler must make a human choose between two plausible people.
    """

    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return "".join(character.casefold() for character in text if character.isalnum())


def surname_key(value: object) -> str:
    """Return a conservative last-token key for a dated, known birth date."""

    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    tokens = ["".join(character.casefold() for character in token if character.isalnum()) for token in text.split()]
    return next((token for token in reversed(tokens) if token), "")


def _canonical_object(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReconciliationError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ReconciliationError(f"{label} must be canonical JSON")
    return value, hashlib.sha256(raw).hexdigest()


def _read_fifa_rows(path: Path) -> tuple[list[dict[str, str]], str]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ReconciliationError("FIFA snapshot has no header")
            required = {"player_id", "name", "birthdate", "nationality", "club", "rating", "headshot_url"}
            missing = sorted(required - set(reader.fieldnames))
            if missing:
                raise ReconciliationError("FIFA snapshot misses column(s): " + ", ".join(missing))
            rows = [dict(row) for row in reader]
    except OSError as exc:
        raise ReconciliationError(f"cannot read FIFA snapshot: {path}") from exc
    return rows, digest.hexdigest()


def _selector_key(value: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    fields = ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256")
    result = tuple(str(value.get(field) or "") for field in fields)
    if not all(result):
        raise ReconciliationError("source selector is incomplete")
    return result


def _present(value: object) -> bool:
    return str(value or "").strip().casefold() not in MISSING_VALUES


def _iso_matches_fifa(source_nationality: object, fifa_nationality: object) -> bool:
    """Small, explicit bridge for the common source/FIFA nationality spelling.

    A missing mapping deliberately returns false. It can lower automation
    coverage but cannot choose the wrong duplicated player merely to improve a
    count.
    """

    fifa = normalise_name(fifa_nationality)
    by_iso = {
        "ARG": "argentina", "AUT": "austria", "BEL": "belgium", "BRA": "brazil", "CHI": "chile",
        "COL": "colombia", "CRO": "croatia", "CZE": "czechrepublic", "DEN": "denmark", "ENG": "england",
        "ESP": "spain", "FRA": "france", "GER": "germany", "GRE": "greece", "HUN": "hungary",
        "IRL": "ireland", "ITA": "italy", "NED": "netherlands", "NOR": "norway", "POL": "poland",
        "POR": "portugal", "RUS": "russia", "SCO": "scotland", "SRB": "serbia", "SUI": "switzerland",
        "SWE": "sweden", "TUR": "turkey", "UKR": "ukraine", "URU": "uruguay", "USA": "unitedstates",
        "WAL": "wales",
    }
    return by_iso.get(str(source_nationality or "").upper()) == fifa


def _fifa_projection(row: Mapping[str, str]) -> dict[str, int | str]:
    """Keep source values verbatim; conversion to PM99 remains a later stage."""

    fields = (
        "rating", "sprint_speed", "stamina", "aggression", "short_pass", "stand_tackle",
        "heading", "finishing", "dribbling", "gk_handling", "preferred_positions", "club_kit_number",
    )
    result: dict[str, int | str] = {}
    for field in fields:
        value = str(row.get(field) or "").strip()
        if _present(value):
            result[field] = int(value) if value.isdigit() else value
    return result


def _match_fifa(
    player: Mapping[str, Any],
    *,
    by_name_and_birth: Mapping[tuple[str, str], list[dict[str, str]]],
    by_name: Mapping[str, list[dict[str, str]]],
    by_surname_and_birth: Mapping[tuple[str, str], list[dict[str, str]]],
) -> dict[str, Any]:
    name_key = normalise_name(player.get("name"))
    birth_date = str(player.get("birth_date") or "")
    exact = by_name_and_birth.get((name_key, birth_date), []) if birth_date else []
    if len(exact) == 1:
        chosen = exact[0]
        return {
            "status": "fifa16-exact-name-and-birth-date",
            "fifa16_player_id": int(chosen["player_id"]),
            "fifa16_name": chosen["name"],
            "fifa16_club": chosen["club"],
            "fifa16_headshot_url": chosen["headshot_url"],
            "fifa16_values": _fifa_projection(chosen),
        }
    surname_matches = by_surname_and_birth.get((surname_key(player.get("name")), birth_date), []) if birth_date else []
    if len(surname_matches) == 1:
        chosen = surname_matches[0]
        return {
            "status": "fifa16-unique-surname-and-birth-date",
            "fifa16_player_id": int(chosen["player_id"]),
            "fifa16_name": chosen["name"],
            "fifa16_club": chosen["club"],
            "fifa16_headshot_url": chosen["headshot_url"],
            "fifa16_values": _fifa_projection(chosen),
        }
    candidates = by_name.get(name_key, [])
    if len(candidates) == 1:
        chosen = candidates[0]
        return {
            "status": "fifa16-unique-name",
            "fifa16_player_id": int(chosen["player_id"]),
            "fifa16_name": chosen["name"],
            "fifa16_club": chosen["club"],
            "fifa16_headshot_url": chosen["headshot_url"],
            "fifa16_values": _fifa_projection(chosen),
        }
    nationality_matches = [row for row in candidates if _iso_matches_fifa(player.get("nationality"), row.get("nationality"))]
    if len(nationality_matches) == 1:
        chosen = nationality_matches[0]
        return {
            "status": "fifa16-unique-name-and-nationality",
            "fifa16_player_id": int(chosen["player_id"]),
            "fifa16_name": chosen["name"],
            "fifa16_club": chosen["club"],
            "fifa16_headshot_url": chosen["headshot_url"],
            "fifa16_values": _fifa_projection(chosen),
        }
    if candidates:
        return {"status": "fifa16-ambiguous-name", "candidate_fifa16_player_ids": sorted(int(row["player_id"]) for row in candidates)}
    return {"status": "fallback-required", "reason": "no-fifa16-player-name-match"}


def build_reconciliation(*, registry: Mapping[str, Any], draft: Mapping[str, Any], source_capture: Mapping[str, Any], fifa_rows: Iterable[dict[str, str]], fifa_sha256: str) -> dict[str, Any]:
    if not isinstance(registry.get("carriers"), list):
        raise ReconciliationError("registry has no carrier list")
    if draft.get("schema_version") != DRAFT_SCHEMA or not isinstance(draft.get("proposals"), list):
        raise ReconciliationError("source draft has the wrong schema")
    if source_capture.get("schema_version") != SOURCE_SCHEMA or not isinstance(source_capture.get("clubs"), list):
        raise ReconciliationError("source capture has the wrong schema")
    registry_sha = hashlib.sha256(canonical_json_bytes(dict(registry))).hexdigest()
    capture_sha = hashlib.sha256(canonical_json_bytes(dict(source_capture))).hexdigest()
    if draft.get("registry_sha256") != registry_sha or draft.get("source_capture_sha256") != capture_sha:
        raise ReconciliationError("source draft is not bound to these exact registry and source-capture inputs")

    carriers = {int(row["carrier_id"]): row for row in registry["carriers"] if isinstance(row, dict)}
    if len(carriers) != len(registry["carriers"]):
        raise ReconciliationError("registry has duplicate or malformed carrier ids")
    clubs: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for club in source_capture["clubs"]:
        if not isinstance(club, dict) or not isinstance(club.get("players"), list):
            raise ReconciliationError("source capture has a malformed club")
        key = _selector_key(club)
        if key in clubs:
            raise ReconciliationError("source capture has duplicate club selectors")
        clubs[key] = club

    by_name_and_birth: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    by_name: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_surname_and_birth: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in fifa_rows:
        name = normalise_name(row.get("name"))
        if not name or not str(row.get("player_id") or "").isdigit():
            continue
        by_name[name].append(row)
        if str(row.get("birthdate") or ""):
            by_name_and_birth[(name, str(row["birthdate"]))].append(row)
            surname = surname_key(row.get("name"))
            if surname:
                by_surname_and_birth[(surname, str(row["birthdate"]))].append(row)

    plans: list[dict[str, Any]] = []
    selected_slots = 0
    for proposal in sorted(draft["proposals"], key=lambda row: int(row["carrier_id"])):
        if not isinstance(proposal, dict) or proposal.get("status") != "source-squad-ready":
            continue
        carrier_id = int(proposal["carrier_id"])
        carrier = carriers.get(carrier_id)
        if carrier is None:
            raise ReconciliationError(f"draft refers to unknown carrier {carrier_id}")
        selector = proposal.get("source_selector")
        if not isinstance(selector, dict):
            raise ReconciliationError(f"carrier {carrier_id} lacks a source selector")
        club = clubs.get(_selector_key(selector))
        if club is None:
            raise ReconciliationError(f"carrier {carrier_id} selector is absent from the source capture")
        slots = list(carrier.get("roster_slots") or [])
        source_players = list(club["players"])
        if len(source_players) < len(slots):
            raise ReconciliationError(f"carrier {carrier_id} source squad is smaller than its immutable slot count")
        rows: list[dict[str, Any]] = []
        # The dated source may list more players than PM99 has immutable
        # carriers. The deterministic capacity rule takes its documented
        # source order prefix; ``strict=True`` is still useful once that
        # intentional truncation has occurred.
        selected_source_players = source_players[:len(slots)]
        for source_index, (slot, source_player) in enumerate(zip(slots, selected_source_players, strict=True), start=1):
            if not isinstance(slot, dict) or not isinstance(source_player, dict):
                raise ReconciliationError(f"carrier {carrier_id} contains a malformed slot/source player")
            rows.append({
                "slot_index": int(slot["slot_index"]),
                "player_carrier_id": int(slot["player_carrier_id"]),
                "player_family": str(slot["family"]),
                "immutable_row_flag": int(slot["flag"]),
                "source_squad_index": source_index,
                "source_player": {
                    "name": source_player.get("name"), "birth_date": source_player.get("birth_date"),
                    "nationality": source_player.get("nationality"), "height_cm": source_player.get("height_cm"),
                    "weight_kg": source_player.get("weight_kg"), "position": source_player.get("position"),
                    "shirt_number": source_player.get("shirt_number"), "unresolved_fields": list(source_player.get("unresolved_fields") or []),
                },
                "fifa16": _match_fifa(source_player, by_name_and_birth=by_name_and_birth, by_name=by_name, by_surname_and_birth=by_surname_and_birth),
            })
        selected_slots += len(rows)
        plans.append({
            "carrier_id": carrier_id,
            "fixed_roster_slot_count": len(slots),
            "source_selector": dict(selector),
            "source_club_name": club["club_name"],
            "slot_selection_policy": "source-squad-order-truncated-to-immutable-capacity; not-opening-xi-or-pm99-order",
            "rows": rows,
        })
    status_counts = Counter(row["fifa16"]["status"] for plan in plans for row in plan["rows"])
    unresolved_facts = Counter(
        field for plan in plans for row in plan["rows"] for field in row["source_player"]["unresolved_fields"]
    )
    return {
        "schema_version": SCHEMA,
        "policy": "fixed-existing-carriers-and-slots-only; source-order-is-not-opening-xi; no-fdi-pkf-or-bmp-write",
        "sources": {
            "registry_sha256": registry_sha,
            "source_draft_sha256": hashlib.sha256(canonical_json_bytes(dict(draft))).hexdigest(),
            "source_capture_sha256": capture_sha,
            "fifa16_player_snapshot_sha256": fifa_sha256,
        },
        "coverage": {
            "source_ready_carriers": len(plans),
            "selected_fixed_slots": selected_slots,
            "fifa16_match_status_counts": dict(sorted(status_counts.items())),
            "source_unresolved_field_counts": dict(sorted(unresolved_facts.items())),
        },
        "carrier_plans": plans,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--source-draft", required=True, type=Path)
    parser.add_argument("--source-capture", required=True, type=Path)
    parser.add_argument("--fifa16-player-csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        registry, _ = _canonical_object(args.registry, label="registry")
        draft, _ = _canonical_object(args.source_draft, label="source draft")
        capture, _ = _canonical_object(args.source_capture, label="source capture")
        fifa_rows, fifa_sha = _read_fifa_rows(args.fifa16_player_csv)
        result = build_reconciliation(registry=registry, draft=draft, source_capture=capture, fifa_rows=fifa_rows, fifa_sha256=fifa_sha)
    except ReconciliationError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["coverage"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
