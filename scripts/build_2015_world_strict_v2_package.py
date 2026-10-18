#!/usr/bin/env python3
"""Project the dated 2015 world candidate into one strict native V2 graph.

PM99's foreign roster writer is proven only as a complete mode-1 transaction.
The dated source graph currently covers a strict subset of those carriers, so
this projector includes every remaining mode-1 carrier as an explicit
byte-preserving baseline row.  Those rows are not presented as 2015 research.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.editor_actions import (
    _native_dd6360_role_start,
    _patch_indexed_player_variable_name_payload,
    _read_native_dd6360_fields,
)
from app.ent_manager_profiles import parse_indexed_ent_manager_profile
from app.eq_team_indexed_metadata import extract_indexed_team_payload_metadata
from app.eq_team_manager_links import parse_indexed_eq_manager_links
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.models import PlayerRecord
from scripts import season_package_v2
from scripts.season_package_compiler_v2 import SeasonCompilerError, _pm99_text


SCHEMA = "pm99-world-2015-strict-v2-projection-receipt-v1"
CANDIDATE_SCHEMA = "pm99-world-2015-editorial-fallback-ratings-v1"
PRESERVE = {"policy": "preserve-existing-mode1"}
SKILL_NAMES = (
    "quality", "speed", "stamina", "aggression", "passing",
    "tackling", "heading", "shooting", "dribbling",
)


class ProjectionError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return season_package_v2.sha256_file(path)


def _proof(grade: str, artifact_id: str) -> dict[str, str]:
    return {"grade": grade, "artifact_id": artifact_id}


def _player_name(payload: bytes, carrier: int) -> str:
    value = " ".join(str(PlayerRecord.from_bytes(payload, 0).name or "").split())
    if not value or value in {"Unknown Player", "Parse Error"}:
        raise ProjectionError(f"baseline JUG carrier {carrier} has no parser-backed name")
    return value


def _base_ratings(payload: bytes, carrier: int) -> dict[str, int]:
    if payload[2:5] != b"\xdd\x63\x60":
        raise ProjectionError(f"preserved baseline carrier {carrier} is not dd6360")
    fields = _read_native_dd6360_fields(payload, int(_native_dd6360_role_start(payload)))
    skills = [int(value) for value in fields["skills"]]
    if len(skills) != 9:
        raise ProjectionError(f"baseline JUG carrier {carrier} lacks nine visible skills")
    result = dict(zip(SKILL_NAMES, skills, strict=True))
    result["handling"] = int(fields["handling"])
    if any(not 0 <= value <= 99 for value in result.values()):
        raise ProjectionError(f"baseline JUG carrier {carrier} has a V2-inexpressible rating")
    return result


def _safe_variable_display_name(payload: bytes, source_name: str, carrier: int) -> str:
    """Choose the least-shortened alias accepted by the proven name writer."""

    full = _pm99_text(source_name, label=f"player carrier {carrier} source name")
    current = _player_name(payload, carrier)
    tokens = full.split()
    candidates = [full]
    if len(tokens) > 1:
        candidates.append(f"{tokens[0][0]}. {tokens[-1]}")
    if tokens:
        candidates.append(tokens[-1])
    if len(tokens) > 1:
        candidates.append(f"{tokens[0]} {tokens[-1][0]}.")
        candidates.append(tokens[0])
        # Some native dd6360 rows have a name window of only four bytes.  Keep
        # a source-derived identity in that window rather than truncating an
        # arbitrary byte string or silently retaining the unrelated carrier.
        candidates.append("".join(f"{token[0]}." for token in tokens))
        candidates.append("".join(token[0] for token in tokens))
        candidates.append(f"{tokens[-1][0]}.")
    elif tokens:
        candidates.append(f"{tokens[0][0]}.")
        candidates.append(tokens[0][0])
    for candidate in dict.fromkeys(candidates):
        if candidate == current:
            return candidate
        try:
            patched, _proof_row = _patch_indexed_player_variable_name_payload(payload, current, candidate)
        except Exception:
            continue
        if _player_name(patched, carrier) != candidate:
            continue
        return candidate
    raise ProjectionError(f"player carrier {carrier} has no safe variable-length source-name alias")


def _fit_source_players_to_native_roster(
    source_players: list[Mapping[str, Any]], native_roster: list[int]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Bind dated players, in source order, to immutable native roster slots."""
    fitted_players: list[dict[str, Any]] = []
    for slot, (source_player, native_player_id) in enumerate(
        zip(source_players, native_roster, strict=False)
    ):
        fitted = dict(source_player)
        fitted["source_candidate_carrier_id"] = int(source_player["player_carrier_id"])
        fitted["player_carrier_id"] = int(native_player_id)
        fitted["slot_index"] = slot
        fitted_players.append(fitted)
    return fitted_players, {
        "native_slot_count": len(native_roster),
        "dated_source_player_count": len(source_players),
        "dated_players_written": len(fitted_players),
        "dated_players_dropped": max(0, len(source_players) - len(native_roster)),
        "native_tail_preserved": max(0, len(native_roster) - len(source_players)),
    }


def _source_ratings(player: Mapping[str, Any]) -> dict[str, int]:
    values = player["rating_disposition"]["values"]
    result = {
        "quality": int(values["rating"]),
        "speed": int(values["sprint_speed"]),
        "stamina": int(values["stamina"]),
        "aggression": int(values["aggression"]),
        "passing": int(values["short_pass"]),
        "tackling": int(values["stand_tackle"]),
        "heading": int(values["heading"]),
        "shooting": int(values["finishing"]),
        "dribbling": int(values["dribbling"]),
        "handling": int(values["gk_handling"]),
    }
    if any(not 0 <= value <= 99 for value in result.values()):
        raise ProjectionError("dated rating is outside the strict PM99 0..99 contract")
    return result


def _source_rating_method(player: Mapping[str, Any]) -> str:
    status = (player.get("rating_disposition") or {}).get("status")
    if status == "fifa16-complete-candidate":
        return "fifa-nearest-edition"
    if status == "editorial-fallback-applied":
        return "deterministic-context"
    raise ProjectionError(f"source player has unresolved rating provenance {status!r}")


def _source_facts(player: Mapping[str, Any]) -> dict[str, Any]:
    source = player["source_player"]
    disposition = player.get("player_facts_disposition") or {}
    physical = disposition.get("physical_fallbacks") or {}

    def source_or_fallback(source_key: str, fallback_key: str) -> Any:
        value = source.get(source_key)
        if value is not None:
            return value
        fallback = physical.get(fallback_key)
        return fallback.get("value") if isinstance(fallback, Mapping) else PRESERVE

    graph = player.get("compiler_graph") or {}
    roles: Any = PRESERVE
    if graph.get("operation") == "mode1-recycle":
        role = graph.get("required_primary_fine_role_code")
        if not isinstance(role, int):
            raise ProjectionError("recycle player lacks its qualified primary fine role")
        roles = [role]
    return {
        "birth_date": source.get("birth_date") or PRESERVE,
        "nationality": source.get("nationality") or PRESERVE,
        "height_cm": source_or_fallback("height_cm", "height_cm"),
        "weight_kg": source_or_fallback("weight_kg", "weight_kg"),
        "primary_position": source.get("position") or PRESERVE,
        "fine_roles": roles,
        "shirt_number": PRESERVE,
    }


def _partial_display_name(value: str) -> str:
    """Turn NTF's `Surname, Given` label into PM99's profile order."""

    parts = [part.strip() for part in str(value).split(",", 1)]
    return f"{parts[1]} {parts[0]}" if len(parts) == 2 and all(parts) else str(value).strip()


def _ownership_displacements(
    candidate: Mapping[str, Any], decisions: Mapping[str, Any] | None,
) -> set[tuple[int, int, int]]:
    groups: dict[tuple[str, str, str], list[tuple[int, int, int]]] = defaultdict(list)
    for club in candidate.get("carrier_drafts") or []:
        for player in club.get("players") or []:
            source = player.get("source_player") or {}
            if not all(isinstance(source.get(key), str) for key in ("name", "birth_date", "nationality")):
                continue
            normal = unicodedata.normalize("NFKD", source["name"])
            identity = (
                "".join(char.casefold() for char in normal if char.isalnum()),
                source["birth_date"], source["nationality"],
            )
            groups[identity].append((int(club["carrier_id"]), int(player["slot_index"]), int(player["player_carrier_id"])))
    overlaps = {identity: sorted(rows) for identity, rows in groups.items() if len(rows) > 1}
    if not overlaps:
        return set()
    if not isinstance(decisions, Mapping) or decisions.get("schema_version") != "pm99-world-2015-person-ownership-decisions-v1":
        raise ProjectionError(f"{len(overlaps)} same-person overlaps require a reviewed ownership-decision receipt")
    by_identity = {}
    for row in decisions.get("decisions") or []:
        identity = row.get("strict_identity") or {}
        key = (identity.get("normalised_name"), identity.get("birth_date"), identity.get("nationality"))
        if key in by_identity:
            raise ProjectionError(f"duplicate ownership decision for {key}")
        by_identity[key] = row
    if set(by_identity) != set(overlaps):
        raise ProjectionError("ownership decisions do not exactly cover the candidate overlap identities")
    displaced: set[tuple[int, int, int]] = set()
    for identity, candidates in overlaps.items():
        decision = by_identity[identity]
        if decision.get("action") != "retain-one-opening-date-owner":
            raise ProjectionError(f"unsupported ownership action for {identity}")
        retained = decision.get("retained") or {}
        retained_key = (retained.get("team_carrier_id"), retained.get("slot_index"), retained.get("player_carrier_id"))
        displaced_rows = decision.get("displaced") or []
        displaced_keys = {
            (row.get("team_carrier_id"), row.get("slot_index"), row.get("player_carrier_id"))
            for row in displaced_rows
            if row.get("disposition") == "preserve-native-carrier-row"
        }
        if retained_key not in candidates or displaced_keys != set(candidates) - {retained_key}:
            raise ProjectionError(f"ownership decision does not partition candidates for {identity}")
        if not decision.get("evidence"):
            raise ProjectionError(f"ownership decision lacks evidence for {identity}")
        displaced.update(displaced_keys)
    return displaced


def build_package(
    *, candidate: Mapping[str, Any], base_tree: Path,
    candidate_path: Path, dispositions: Mapping[str, Any], dispositions_path: Path,
    metadata_dispositions: Mapping[str, Any], metadata_dispositions_path: Path,
    contract_path: Path, calendar_receipt_path: Path,
    ownership_decisions: Mapping[str, Any] | None = None,
    ownership_decisions_path: Path | None = None,
    fit_native_rosters: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if candidate.get("schema_version") != CANDIDATE_SCHEMA:
        raise ProjectionError("candidate schema is unsupported")
    selected_rows = candidate.get("carrier_drafts")
    if not isinstance(selected_rows, list) or len(selected_rows) < 372:
        raise ProjectionError("expected at least the 372-carrier dated source graph")
    if dispositions.get("schema_version") != "pm99-world-2015-unresolved-carrier-dispositions-v1":
        raise ProjectionError("unresolved-carrier dispositions have the wrong schema")
    if metadata_dispositions.get("schema_version") != "pm99-world-2015-club-metadata-dispositions-v1":
        raise ProjectionError("club metadata dispositions have the wrong schema")
    metadata_by_carrier = {
        int(row["carrier_id"]): row
        for row in metadata_dispositions.get("rows") or []
    }
    partial_by_carrier = {
        int(row["carrier_id"]): row
        for row in dispositions.get("dispositions") or []
        if row.get("release_disposition") == "partial-sourced-prefix-preserved-native-tail"
    }
    if not partial_by_carrier:
        raise ProjectionError("reviewed partial-source carrier set is empty")
    displaced_person_rows = _ownership_displacements(candidate, ownership_decisions)
    dbdat = base_tree / "DBDAT"
    eq_data = (dbdat / "EQ98030.FDI").read_bytes()
    jug_data = (dbdat / "JUG98030.FDI").read_bytes()
    ent_data = (dbdat / "ENT98030.FDI").read_bytes()
    eq_entries = {int(e.record_id): e for e in IndexedFDIFile.from_bytes(eq_data).entries}
    jug_entries = {int(e.record_id): e for e in IndexedFDIFile.from_bytes(jug_data).entries}
    ent_entries = {int(e.record_id): e for e in IndexedFDIFile.from_bytes(ent_data).entries}

    mode1: dict[int, dict[str, Any]] = {}
    manager_owners: dict[int, list[int]] = defaultdict(list)
    for carrier, entry in sorted(eq_entries.items()):
        raw = eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        metadata = extract_indexed_team_payload_metadata(raw)
        if int(metadata["record_mode"]) != 1:
            continue
        roster = parse_eq_external_team_roster_payload(raw, {})
        if roster is None or not roster.rows:
            raise ProjectionError(f"mode-1 EQ carrier {carrier} lacks a bounded roster")
        manager_id = parse_indexed_eq_manager_links(raw).active_manager_record_id
        if not isinstance(manager_id, int) or manager_id not in ent_entries:
            raise ProjectionError(f"mode-1 EQ carrier {carrier} lacks a valid active manager")
        manager_owners[manager_id].append(carrier)
        mode1[carrier] = {
            "metadata": metadata,
            "manager_id": manager_id,
            "roster": [int(row.player_record_id) for row in roster.rows],
        }

    selected = {int(row["carrier_id"]): row for row in selected_rows}
    if not set(selected) <= set(mode1):
        raise ProjectionError("dated source graph includes a non-mode-1 carrier")
    recycle_rows = sorted(
        (
            int(club["carrier_id"]), int(player["slot_index"]),
            int(player["player_carrier_id"]),
            int((player.get("compiler_graph") or {}).get("allocation", {}).get("appended_mode0_clone_carrier_id")),
        )
        for club in selected_rows
        for player in club.get("players") or []
        if (player.get("compiler_graph") or {}).get("operation") == "mode1-recycle"
    )
    recycle_donor_by_slot = {
        (team, slot, target): int(
            next(
                player for club in selected_rows if int(club["carrier_id"]) == team
                for player in club.get("players") or []
                if int(player["slot_index"]) == slot and int(player["player_carrier_id"]) == target
            )["compiler_graph"]["allocation"]["old_shared_mode1_carrier_id"]
        )
        for team, slot, target, _old_clone in recycle_rows
    }
    recycle_donor_carriers = set(recycle_donor_by_slot.values())
    # Runtime proof rejected both high and low appended clone IDs: playable
    # clubs do not count those records toward squad eligibility.  V11 leaves
    # the original shared foreign reference graph intact and preserves both
    # occurrences of every affected native carrier.
    rebased_clones: dict[tuple[int, int, int], int] = {}
    clone_rebase_receipt: list[dict[str, int]] = []

    dated_manager_names = {
        carrier: " ".join(str(row["manager"]["value"]).split())
        for carrier, row in metadata_by_carrier.items()
        if row.get("manager", {}).get("status") == "dated-source-fact"
        and str(row.get("manager", {}).get("value") or "").strip()
    }
    safe_manager_names: dict[int, str] = {}
    manager_conflicts: list[dict[str, Any]] = []
    for manager_id, owners in sorted(manager_owners.items()):
        names = {dated_manager_names[owner] for owner in owners if owner in dated_manager_names}
        if names and len(names) == 1 and all(owner in dated_manager_names for owner in owners):
            safe_manager_names[manager_id] = next(iter(names))
        elif names:
            manager_conflicts.append({
                "manager_carrier_id": manager_id,
                "owner_team_carrier_ids": sorted(owners),
                "dated_names": sorted(names),
                "action": "preserve-existing-shared-entity",
            })

    artifact_source = "world-2015-source-candidate"
    artifact_partial = "world-2015-partial-source-dispositions"
    artifact_metadata = "world-2015-club-metadata-dispositions"
    artifact_ownership = "world-2015-person-ownership-decisions"
    artifact_contract = "world-mode1-runtime-contract"
    artifact_calendar = "calendar-2015-receipt"
    source_proof = _proof("source-receipt", artifact_source)
    preserve_proof = _proof("static-contract", artifact_contract)

    managers = []
    for manager_id in sorted(manager_owners):
        entry = ent_entries[manager_id]
        raw = ent_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        profile = parse_indexed_ent_manager_profile(raw, record_id=manager_id)
        current = " ".join(str(profile.surname or "").split()) or f"Manager {manager_id}"
        target = safe_manager_names.get(manager_id)
        row = {
            "id": f"manager-{manager_id}", "carrier_id": manager_id,
            "name": target or current,
            "proof": _proof("source-receipt", artifact_metadata) if target else preserve_proof,
        }
        if target:
            row["person_id"] = f"manager-person-{manager_id}"
            row["policy"] = "write"
        else:
            row["policy"] = "preserve-existing-mode1"
        managers.append(row)

    clubs: list[dict[str, Any]] = []
    players: list[dict[str, Any]] = []
    kits: list[dict[str, Any]] = []
    portraits: list[dict[str, Any]] = []
    selected_player_count = 0
    preserved_player_count = 0
    partial_player_count = 0
    ownership_displaced_player_count = 0
    shared_native_preserve_slot_count = 0
    recycle_fallback_slot_count = 0
    shared_native_preserve_carrier_count = 0
    final_carriers: set[int] = set()
    variable_name_aliases: list[dict[str, Any]] = []
    native_roster_fit_rows: list[dict[str, Any]] = []
    goalkeeper_handling_guards: list[dict[str, Any]] = []

    for carrier, base in sorted(mode1.items()):
        source_club = selected.get(carrier)
        partial_club = partial_by_carrier.get(carrier)
        metadata_disposition = metadata_by_carrier.get(carrier) or {}
        club_id = f"club-{carrier}"
        if source_club:
            name = str(source_club["club"]["source_club_name"])
            source_players = sorted(source_club["players"], key=lambda row: int(row["slot_index"]))
            if fit_native_rosters:
                native_roster = list(base["roster"])
                fitted_players, fit_receipt = _fit_source_players_to_native_roster(
                    source_players, native_roster
                )
                source_players = fitted_players
                roster_ids = native_roster
                native_roster_fit_rows.append({"carrier_id": carrier, **fit_receipt})
            else:
                roster_ids = [int(row["player_carrier_id"]) for row in source_players]
                if len(roster_ids) != len(base["roster"]):
                    raise ProjectionError(f"dated carrier {carrier} changes its fixed roster count")
            player_rows = [
                (row, "ownership-displaced")
                if (
                    carrier,
                    int(row["slot_index"]),
                    int(row.get("source_candidate_carrier_id", row["player_carrier_id"])),
                ) in displaced_person_rows
                else (row, True)
                for row in source_players
            ]
            if fit_native_rosters and len(source_players) < len(roster_ids):
                player_rows.extend(
                    (player_id, False) for player_id in roster_ids[len(source_players):]
                )
        elif partial_club:
            name = str(partial_club["source_selector"]["club_name"])
            roster_ids = list(base["roster"])
            prefix = list(partial_club.get("sourced_prefix") or [])
            if len(prefix) != int(partial_club["sourced_prefix_count"]) or len(prefix) >= len(roster_ids):
                raise ProjectionError(f"partial carrier {carrier} has an invalid reviewed prefix")
            player_rows = [
                ({"player_carrier_id": player_id, "partial_source": prefix[slot]}, "partial")
                if slot < len(prefix) else (player_id, False)
                for slot, player_id in enumerate(roster_ids)
            ]
        else:
            name = str(base["metadata"]["short_name"])
            roster_ids = list(base["roster"])
            player_rows = [(player_id, False) for player_id in roster_ids]
        club_player_ids: list[str] = []
        shared_preserve_player_ids: list[str] = []
        for slot, (source_or_id, sourced) in enumerate(player_rows):
            if fit_native_rosters:
                fitted_carrier = int(
                    source_or_id["player_carrier_id"]
                    if isinstance(source_or_id, dict) else source_or_id
                )
                if fitted_carrier in final_carriers:
                    shared_id = f"player-{fitted_carrier}"
                    club_player_ids.append(shared_id)
                    shared_preserve_player_ids.append(shared_id)
                    shared_native_preserve_slot_count += 1
                    continue
                fitted_entry = jug_entries.get(fitted_carrier)
                if fitted_entry is None:
                    raise ProjectionError(f"fitted native carrier {fitted_carrier} is absent from JUG")
            if sourced is True:
                graph = source_or_id.get("compiler_graph") or {}
                if not fit_native_rosters and graph.get("operation") == "mode1-recycle":
                    target = int(source_or_id["player_carrier_id"])
                    donor = recycle_donor_by_slot[(carrier, slot, target)]
                    shared_id = f"player-{donor}"
                    club_player_ids.append(shared_id)
                    recycle_fallback_slot_count += 1
                    if donor in final_carriers:
                        shared_preserve_player_ids.append(shared_id)
                        shared_native_preserve_slot_count += 1
                    else:
                        donor_entry = jug_entries.get(donor)
                        if donor_entry is None:
                            raise ProjectionError(f"native fallback donor {donor} is absent from JUG")
                        donor_payload = donor_entry.decode_payload(jug_data)
                        if donor_payload[2:5] != b"\xdd\x63\x60":
                            raise ProjectionError(f"native fallback donor {donor} is not dd6360")
                        donor_facts = {field: PRESERVE for field in ("birth_date", "nationality", "height_cm", "weight_kg", "primary_position", "fine_roles", "shirt_number")}
                        players.append({
                            "id": shared_id, "person_id": f"person-{donor}",
                            "carrier_id": donor, "carrier_family": "dd6360",
                            "club_id": club_id, "name": _player_name(donor_payload, donor),
                            "facts": donor_facts,
                            "ratings": {
                                "profile": "pm99-visible-skills-v1",
                                "values": _base_ratings(donor_payload, donor),
                                "provenance": {"method": "native-recycle-fallback-preserve", "proof_grade": "static-contract", "source_ids": ["baseline-runtime-contract"]},
                            },
                            "proof": preserve_proof,
                            "policy": "preserve-existing-mode1",
                        })
                        portraits.append({"player_id": shared_id, "status": "unresolved", "review_reason": "native fallback carrier preserved after runtime rejection of appended clones", "proof": preserve_proof})
                        final_carriers.add(donor)
                        shared_native_preserve_carrier_count += 1
                    continue
                if int(source_or_id["player_carrier_id"]) in recycle_donor_carriers:
                    donor = int(source_or_id["player_carrier_id"])
                    if donor in final_carriers:
                        shared_id = f"player-{donor}"
                        club_player_ids.append(shared_id)
                        shared_preserve_player_ids.append(shared_id)
                        shared_native_preserve_slot_count += 1
                        continue
                    sourced = "shared-native-preserve"
            if sourced is True:
                source_player = source_or_id
                player_carrier = int(source_player["player_carrier_id"])
                if fit_native_rosters:
                    signature = jug_entries[player_carrier].decode_payload(jug_data)[2:5]
                    family = "dd6361" if signature == b"\xdd\x63\x61" else "dd6360" if signature == b"\xdd\x63\x60" else ""
                    if not family:
                        raise ProjectionError(f"fitted native carrier {player_carrier} has unsupported family")
                else:
                    family = str(source_player["player_family"])
                source_name = str(source_player["source_player"]["name"])
                graph = {} if fit_native_rosters else (source_player.get("compiler_graph") or {})
                name_payload_carrier = (
                    int((graph.get("allocation") or {})["old_shared_mode1_carrier_id"])
                    if graph.get("operation") == "mode1-recycle" else player_carrier
                )
                name_entry = jug_entries.get(name_payload_carrier)
                if name_entry is None:
                    raise ProjectionError(f"name source JUG carrier {name_payload_carrier} is absent")
                player_name = _safe_variable_display_name(
                    name_entry.decode_payload(jug_data), source_name, player_carrier,
                )
                if player_name != _pm99_text(source_name, label=f"player carrier {player_carrier} source name"):
                    variable_name_aliases.append({
                        "player_carrier_id": player_carrier,
                        "source_name": source_name,
                        "compiled_display_name": player_name,
                        "policy": "source-derived full/name aliases/initials; each candidate parser-revalidated against the native string window",
                    })
                facts = _source_facts(source_player)
                ratings = _source_ratings(source_player)
                rating_method = _source_rating_method(source_player)
                selected_player_count += 1
                proof = source_proof
                source_id = "dated-world-source"
            elif sourced == "partial":
                player_carrier = int(source_or_id["player_carrier_id"])
                entry = jug_entries.get(player_carrier)
                if entry is None:
                    raise ProjectionError(f"partial roster references absent JUG carrier {player_carrier}")
                payload = entry.decode_payload(jug_data)
                if payload[2:5] != b"\xdd\x63\x60":
                    raise ProjectionError(f"partial player {player_carrier} is not dd6360")
                family = "dd6360"
                partial = source_or_id["partial_source"]
                source_name = _partial_display_name(str(partial["name"]))
                player_name = _safe_variable_display_name(payload, source_name, player_carrier)
                if player_name != _pm99_text(source_name, label=f"player carrier {player_carrier} source name"):
                    variable_name_aliases.append({
                        "player_carrier_id": player_carrier,
                        "source_name": source_name,
                        "compiled_display_name": player_name,
                        "policy": "source-derived full/name aliases/initials; each candidate parser-revalidated against the native string window",
                    })
                nationality = partial.get("nationality")
                facts = {
                    "birth_date": partial.get("birth_date") or PRESERVE,
                    "nationality": nationality if isinstance(nationality, str) and nationality != "UNK" else PRESERVE,
                    "height_cm": PRESERVE, "weight_kg": PRESERVE,
                    "primary_position": partial.get("position") or PRESERVE,
                    "fine_roles": PRESERVE, "shirt_number": PRESERVE,
                }
                ratings = _base_ratings(payload, player_carrier)
                rating_method = "partial-dated-source-with-preserved-baseline-ratings"
                graph = {}
                partial_player_count += 1
                proof = _proof("source-receipt", artifact_partial)
                source_id = "partial-world-source"
            elif sourced in {"ownership-displaced", "shared-native-preserve"}:
                player_carrier = int(source_or_id["player_carrier_id"])
                if (
                    not fit_native_rosters
                    and (source_or_id.get("compiler_graph") or {}).get("operation") == "mode1-recycle"
                ):
                    raise ProjectionError("ownership-displaced row cannot also be a recycle target")
                entry = jug_entries.get(player_carrier)
                if entry is None:
                    raise ProjectionError(f"ownership-displaced row references absent JUG carrier {player_carrier}")
                payload = entry.decode_payload(jug_data)
                if payload[2:5] != b"\xdd\x63\x60":
                    raise ProjectionError(f"ownership-displaced player {player_carrier} is not dd6360")
                family = "dd6360"
                player_name = _player_name(payload, player_carrier)
                facts = {field: PRESERVE for field in ("birth_date", "nationality", "height_cm", "weight_kg", "primary_position", "fine_roles", "shirt_number")}
                ratings = _base_ratings(payload, player_carrier)
                # The ownership decision is reviewed, but the retained rating
                # bytes are not an editorial rating set. Keep rating provenance
                # honest and distinct from the identity/ownership proof.
                rating_method = "preserved-baseline-readback"
                graph = {}
                if sourced == "ownership-displaced":
                    ownership_displaced_player_count += 1
                    proof = _proof("source-receipt", artifact_ownership)
                    source_id = "person-ownership-review"
                else:
                    shared_native_preserve_carrier_count += 1
                    proof = preserve_proof
                    source_id = "baseline-runtime-contract"
            else:
                player_carrier = int(source_or_id)
                entry = jug_entries.get(player_carrier)
                if entry is None:
                    raise ProjectionError(f"preserved roster references absent JUG carrier {player_carrier}")
                payload = entry.decode_payload(jug_data)
                family = "dd6361" if payload[2:5] == b"\xdd\x63\x61" else "dd6360" if payload[2:5] == b"\xdd\x63\x60" else ""
                if family != "dd6360":
                    raise ProjectionError(f"preserved player {player_carrier} uses unsupported family {family!r}")
                player_name = _player_name(payload, player_carrier)
                facts = {field: PRESERVE for field in ("birth_date", "nationality", "height_cm", "weight_kg", "primary_position", "fine_roles", "shirt_number")}
                ratings = _base_ratings(payload, player_carrier)
                rating_method = "preserved-baseline-readback"
                graph = {}
                preserved_player_count += 1
                proof = preserve_proof
                source_id = "baseline-runtime-contract"
            if (
                facts.get("primary_position") == "G"
                and ratings["handling"] < ratings["quality"] - 15
            ):
                before = ratings["handling"]
                ratings = dict(ratings)
                ratings["handling"] = max(before, ratings["quality"] - 3)
                goalkeeper_handling_guards.append({
                    "player_carrier_id": player_carrier,
                    "player_name": str(source_name) if sourced in {True, "partial"} else player_name,
                    "quality": ratings["quality"],
                    "handling_before": before,
                    "handling_after": ratings["handling"],
                    "source_method": rating_method,
                })
                rating_method = "deterministic-goalkeeper-handling-guard"
            if player_carrier in final_carriers:
                raise ProjectionError(f"final foreign graph duplicates JUG carrier {player_carrier}")
            final_carriers.add(player_carrier)
            player_id = f"player-{player_carrier}"
            club_player_ids.append(player_id)
            row = {
                "id": player_id, "person_id": f"person-{player_carrier}",
                "carrier_id": player_carrier, "carrier_family": family,
                "club_id": club_id, "name": player_name, "facts": facts,
                "ratings": {
                    "profile": "pm99-visible-skills-v1", "values": ratings,
                    "provenance": {
                        "method": rating_method,
                        "proof_grade": "source-receipt" if sourced else "static-contract",
                        "source_ids": [source_id],
                    },
                },
                "proof": proof,
            }
            if sourced in {True, "partial"}:
                row["source_name"] = str(source_name)
            if sourced in {False, "ownership-displaced", "shared-native-preserve"}:
                row["policy"] = "preserve-existing-mode1"
            if graph.get("operation") == "mode1-recycle":
                allocation = graph.get("allocation") or {}
                row["recycle_from_mode1_carrier_id"] = int(allocation["old_shared_mode1_carrier_id"])
                row["mode0_clone_carrier_id"] = rebased_clones[(carrier, slot, player_carrier)]
            players.append(row)
            portraits.append({
                "player_id": player_id, "status": "unresolved",
                "review_reason": "portrait is materialised by the separate fail-open asset stage" if sourced is True else "partial source has no identity-safe portrait; preserve existing asset" if sourced == "partial" else "carrier lies outside the dated source graph; preserve existing asset",
                "proof": proof,
            })

        source_identity_name = name if (source_club or partial_club) else None
        stadium = metadata_disposition.get("stadium") or {}
        club_row = {
            "id": club_id, "identity_id": f"club-identity-{carrier}",
            "carrier_id": carrier, "name": name,
            "full_name": source_identity_name or str(base["metadata"]["full_club_name"]),
            "division": "preserve-existing-mode1-membership",
            "capacity_policy": "preserve-existing-mode1",
            "manager_id": f"manager-{base['manager_id']}",
            "roster_player_ids": club_player_ids,
            "opening": {"policy": "preserve-existing-mode1", "proof": preserve_proof},
            "proof": source_proof if source_club else _proof("source-receipt", artifact_partial) if partial_club else preserve_proof,
        }
        if shared_preserve_player_ids:
            club_row["shared_preserve_player_ids"] = shared_preserve_player_ids
        if stadium.get("status") == "dated-season-ground-fact" and str(stadium.get("value") or "").strip():
            club_row["ground_policy"] = "write"
            club_row["ground_name"] = str(stadium["value"])
        else:
            # Opening-fixture stadiums are evidence about one match venue, not
            # a permanent club-ground fact, and therefore stay review-only.
            club_row["ground_policy"] = "preserve-existing-mode1"
        clubs.append(club_row)
        kits.append({
            "club_id": club_id, "artifact_ids": [],
            "policy": "preserve-existing-mode1", "proof": preserve_proof,
        })

    roster_slot_count = sum(len(club["roster_player_ids"]) for club in clubs)
    if (
        len(final_carriers) != len(players)
        or roster_slot_count - len(final_carriers) != shared_native_preserve_slot_count
    ):
        raise ProjectionError("final foreign player graph differs from its declared native shared-reference count")

    nationalities = sorted({
        facts
        for player in players
        for facts in [player["facts"]["nationality"]]
        if isinstance(facts, str)
    }) or ["ENG"]
    artifacts = [
        {"id": artifact_calendar, "kind": "calendar-patch", "sha256": _sha256(calendar_receipt_path), "relative_path": str(calendar_receipt_path.relative_to(ROOT))},
        {"id": artifact_contract, "kind": "runtime-proof", "sha256": _sha256(contract_path), "relative_path": str(contract_path.relative_to(ROOT))},
        {"id": artifact_metadata, "kind": "season-input", "sha256": _sha256(metadata_dispositions_path), "relative_path": str(metadata_dispositions_path.relative_to(ROOT))},
        {"id": artifact_partial, "kind": "season-input", "sha256": _sha256(dispositions_path), "relative_path": str(dispositions_path.relative_to(ROOT))},
        {"id": artifact_source, "kind": "season-input", "sha256": _sha256(candidate_path), "relative_path": str(candidate_path.relative_to(ROOT))},
    ]
    if ownership_decisions_path is not None:
        artifacts.append({"id": artifact_ownership, "kind": "season-input", "sha256": _sha256(ownership_decisions_path), "relative_path": str(ownership_decisions_path.relative_to(ROOT))})
    package = {
        "schema_version": "pm99-season-package-v2",
        "package_id": f"world-2015-16-source-core-{len(selected)}",
        "season": {"start_year": 2015, "end_year": 2016, "label": "2015/16"},
        "scope": {"id": "world-existing-mode1-carriers", "title": "2015/16 sourced foreign core on the complete fixed carrier graph", "countries": nationalities, "competition_policy": "existing-carriers-only"},
        "artifacts": sorted(artifacts, key=lambda row: row["id"]),
        "sources": [
            {"id": "baseline-runtime-contract", "title": "PM99 fixed mode-1 carrier preservation contract", "proof_grade": "static-contract", "evidence_artifact_id": artifact_contract},
            {"id": "dated-world-source", "title": "2015/16 reconciled world source candidate", "proof_grade": "source-receipt", "evidence_artifact_id": artifact_source},
            {"id": "partial-world-source", "title": "2015 reviewed partial-squad source dispositions", "proof_grade": "source-receipt", "evidence_artifact_id": artifact_partial},
            {"id": "club-metadata-source", "title": "2015 reviewed club manager and stadium dispositions", "proof_grade": "source-receipt", "evidence_artifact_id": artifact_metadata},
            *([{"id": "person-ownership-review", "title": "2015 opening-date duplicate-person ownership decisions", "proof_grade": "source-receipt", "evidence_artifact_id": artifact_ownership}] if ownership_decisions_path is not None else []),
        ],
        "clubs": clubs, "players": sorted(players, key=lambda row: row["id"]),
        "managers": sorted(managers, key=lambda row: row["id"]),
        "assets": {
            "kits": sorted(kits, key=lambda row: row["club_id"]),
            "portraits": sorted(portraits, key=lambda row: row["player_id"]),
        },
        "calendar": {"base_year": 1998, "target_year": 2015, "target_rollover_year": 2016, "patch_artifact_id": artifact_calendar, "proof": _proof("runtime-wine", artifact_calendar)},
        "proofs": [
            {"id": "dated-source-proof", "grade": "source-receipt", "artifact_id": artifact_source, "covers": [f"{len(selected)} sourced club carriers", f"{selected_player_count} dated player slots"]},
            {"id": "mode1-contract-proof", "grade": "static-contract", "artifact_id": artifact_contract, "covers": ["complete fixed mode-1 graph", "per-field preservation"]},
            {"id": "club-metadata-proof", "grade": "source-receipt", "artifact_id": artifact_metadata, "covers": ["dated manager identities", "dated season ground facts"]},
            {"id": "partial-source-proof", "grade": "source-receipt", "artifact_id": artifact_partial, "covers": [f"{len(partial_by_carrier)} partial-source carrier prefixes", "native tail preservation"]},
            *([{"id": "person-ownership-proof", "grade": "source-receipt", "artifact_id": artifact_ownership, "covers": ["opening-date same-person ownership", "displaced native row preservation"]}] if ownership_decisions_path is not None else []),
        ],
        "migration": {"status": "native-v2", "source_artifact_ids": sorted([artifact_calendar, artifact_contract, artifact_metadata, artifact_partial, artifact_source, *([artifact_ownership] if ownership_decisions_path is not None else [])]), "known_gaps": []},
    }
    package["clubs"] = sorted(package["clubs"], key=lambda row: row["id"])
    package["sources"] = sorted(package["sources"], key=lambda row: row["id"])
    package["proofs"] = sorted(package["proofs"], key=lambda row: row["id"])
    season_package_v2.validate_package(package, strict=True)
    receipt = {
        "schema_version": SCHEMA,
        "result": "strict-package-emitted",
        "source_candidate_sha256": _sha256(candidate_path),
        "coverage": {
            "mode1_club_count": len(clubs),
            "source_updated_club_count": len(selected),
            "preserved_source_gap_club_count": len(clubs) - len(selected),
            "player_count": len(players),
            "source_updated_player_count": selected_player_count,
            "partial_source_player_count": partial_player_count,
            "ownership_displaced_player_count": ownership_displaced_player_count,
            "shared_native_preserve_slot_count": shared_native_preserve_slot_count,
            "recycle_fallback_slot_count": recycle_fallback_slot_count,
            "shared_native_preserve_carrier_count": shared_native_preserve_carrier_count,
            "preserved_source_gap_player_count": preserved_player_count,
            "manager_entity_count": len(managers),
            "dated_manager_write_count": len(safe_manager_names),
            "dated_ground_write_count": sum(club.get("ground_policy") == "write" for club in clubs),
            "manager_shared_entity_preserve_conflicts": manager_conflicts,
            "recycle_edge_count": sum(1 for player in players if "recycle_from_mode1_carrier_id" in player),
            "recycle_clone_id_rebase": clone_rebase_receipt,
            "variable_name_alias_count": len(variable_name_aliases),
            "variable_name_aliases": sorted(variable_name_aliases, key=lambda row: row["player_carrier_id"]),
            "native_roster_fit": fit_native_rosters,
            "native_roster_fit_rows": native_roster_fit_rows,
            "goalkeeper_handling_guard_count": len(goalkeeper_handling_guards),
            "goalkeeper_handling_guards": goalkeeper_handling_guards,
            "dd6360_count": sum(player["carrier_family"] == "dd6360" for player in players),
            "dd6361_count": sum(player["carrier_family"] == "dd6361" for player in players),
        },
    }
    return package, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--unresolved-dispositions", required=True, type=Path)
    parser.add_argument("--club-metadata-dispositions", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--calendar-receipt", required=True, type=Path)
    parser.add_argument("--person-ownership-decisions", type=Path)
    parser.add_argument(
        "--fit-native-rosters",
        action="store_true",
        help="fit dated squads to the clean base's immutable foreign roster slots",
    )
    parser.add_argument("--output-package", required=True, type=Path)
    parser.add_argument("--output-receipt", required=True, type=Path)
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    dispositions = json.loads(args.unresolved_dispositions.read_text(encoding="utf-8"))
    metadata_dispositions = json.loads(args.club_metadata_dispositions.read_text(encoding="utf-8"))
    ownership_decisions = json.loads(args.person_ownership_decisions.read_text(encoding="utf-8")) if args.person_ownership_decisions else None
    try:
        package, receipt = build_package(
            candidate=candidate, base_tree=args.base_tree, dispositions=dispositions,
            metadata_dispositions=metadata_dispositions,
            candidate_path=args.candidate.resolve(), contract_path=args.contract.resolve(),
            dispositions_path=args.unresolved_dispositions.resolve(),
            metadata_dispositions_path=args.club_metadata_dispositions.resolve(),
            ownership_decisions=ownership_decisions,
            ownership_decisions_path=args.person_ownership_decisions.resolve() if args.person_ownership_decisions else None,
            calendar_receipt_path=args.calendar_receipt.resolve(),
            fit_native_rosters=args.fit_native_rosters,
        )
    except (
        ProjectionError,
        season_package_v2.PackageValidationError,
        SeasonCompilerError,
    ) as exc:
        parser.error(str(exc))
    args.output_package.parent.mkdir(parents=True, exist_ok=True)
    season_package_v2.write_canonical_package(args.output_package, package)
    args.output_receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output_receipt.write_bytes(season_package_v2.canonical_json_bytes(receipt))
    print(json.dumps(receipt["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
