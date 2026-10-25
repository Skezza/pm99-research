"""Validate typed opening-cohort edits and checked native order writes.

The adapter binds a source-authored actor/roster/order manifest, validates it
against a pinned package/native parent, and applies only existing mode-1
complete-order writers. Actor facts and ratings live in the ordinary child
recipe and are compiled by season_package_compiler_v2.
"""
from __future__ import annotations

import hashlib
import copy
import csv
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from app.fdi_indexed import IndexedFDIFile
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.player_initial_order import (
    OrderReplacement,
    patch_owned_mode1_complete_orders,
    read_initial_order,
)
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as package_v2
from scripts import season_release_registry_v1 as registry
from scripts.season_exact_fifa_role_delta_v1 import compatible as role_compatible

SCHEMA = "pm99-opening-cohort-delta-v1"
SHA_LEN = 64


class CohortDeltaError(ValueError):
    """The typed cohort delta is stale, ambiguous, or outside its closure."""


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != SHA_LEN or any(c not in "0123456789abcdef" for c in value):
        raise CohortDeltaError(f"{label} must be a lowercase SHA-256")
    return value


def _safe_workspace_path(raw: Any, label: str) -> Path:
    if not isinstance(raw, str):
        raise CohortDeltaError(f"{label} path must be text")
    path = Path(raw)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise CohortDeltaError(f"{label} path escapes the workspace")
    root = registry.ROOT.resolve()
    resolved = (root / path).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CohortDeltaError(f"{label} path escapes the workspace through a symlink") from exc
    return resolved


def _parse_footballsquads_row(raw: str, *, season_start_year: int) -> dict[str, Any]:
    """Keep unavailable secondary facts missing; resolve short years by season."""
    try:
        row = next(csv.reader([raw]))
        if len(row) < 7:
            raise ValueError("expected number, name, nationality, position, height, weight, and DOB")
        def known(value):
            return value.strip().casefold() not in {'', '?', '-', 'n/a', 'unknown'}

        birthday = None
        if known(row[6]):
            parts = row[6].strip().replace('/', '-').split('-')
            if len(parts) != 3:
                raise ValueError('unrecognised published birthday')
            if len(parts[0]) == 4:
                year, month, day = map(int, parts)
            else:
                day, month, year = map(int, parts)
                if len(parts[2]) == 2:
                    year += season_start_year // 100 * 100
                    if year > season_start_year:
                        year -= 100
                elif len(parts[2]) != 4:
                    raise ValueError('published birthday needs a two- or four-digit year')
            birthday = date(year, month, day).isoformat()
        return {
            "name": row[1].strip(),
            "nationality": row[2].strip() if known(row[2]) else None,
            "primary_position": row[3].strip(),
            "height_cm": int(round(float(row[4].strip()) * 100)) if known(row[4]) else None,
            "weight_kg": int(row[5].strip()) if known(row[5]) else None,
            "birth_date": birthday,
        }
    except Exception as exc:
        raise CohortDeltaError(f"FootballSquads source row cannot be parsed: {exc}") from exc


def _owner_rosters(eq: bytes) -> tuple[dict[int, list[int]], dict[int, set[int]]]:
    rosters: dict[int, list[int]] = {}
    owners: dict[int, set[int]] = {}
    for entry in IndexedFDIFile.from_bytes(eq).entries:
        payload = eq[entry.payload_offset:entry.payload_offset + entry.payload_length]
        roster = parse_eq_external_team_roster_payload(payload, {})
        if roster is None:
            continue
        rows = [int(row.player_record_id) for row in roster.rows]
        rosters[int(entry.record_id)] = rows
        for carrier in rows:
            owners.setdefault(carrier, set()).add(int(entry.record_id))
    return rosters, owners


def validate_plan(plan: Mapping[str, Any], *, verify_source_files: bool = True) -> dict[str, Any]:
    """Fail closed on the source, actor, fixed-slot, order, and photo closures."""
    if plan.get("schema") != SCHEMA:
        raise CohortDeltaError("unsupported opening-cohort delta schema")
    parent = plan.get("parent")
    if not isinstance(parent, dict) or not parent.get("season") or not parent.get("release_id"):
        raise CohortDeltaError("opening-cohort delta lacks an exact parent release pin")
    _require_sha(parent.get("package_sha256"), "parent.package_sha256")
    native = parent.get("native_sha256")
    if not isinstance(native, dict) or set(native) != {
        "JUG98030.FDI", "EQ98030.FDI", "ENT98030.FDI", "MINIFOTO.PKF", "TEXTOS.PKF"
    }:
        raise CohortDeltaError("parent native pins must cover the exact five source inputs")
    for name, value in native.items():
        _require_sha(value, f"parent.native_sha256.{name}")

    sources = plan.get("source_bindings")
    if not isinstance(sources, list) or not sources:
        raise CohortDeltaError("source bindings are required")
    source_by_id: dict[str, dict[str, Any]] = {}
    for row in sources:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise CohortDeltaError("each source binding needs a stable id")
        if row["id"] in source_by_id:
            raise CohortDeltaError("source binding ids must be unique")
        expected = _require_sha(row.get("sha256"), f"source {row['id']}.sha256")
        path = _safe_workspace_path(row.get("path"), f"source {row['id']}")
        if verify_source_files:
            if not path.is_file() or _sha_bytes(path.read_bytes()) != expected:
                raise CohortDeltaError(f"source bytes differ for {row['id']}")
        if not isinstance(row.get("claim"), str) or not row["claim"].strip():
            raise CohortDeltaError(f"source {row['id']} needs a bounded claim")
        source_by_id[row["id"]] = row

    clubs = plan.get("clubs")
    if not isinstance(clubs, list) or not clubs:
        raise CohortDeltaError("at least one target club is required")
    clubs_by_carrier: dict[int, dict[str, Any]] = {}
    referenced_sources: set[str] = set()
    for club in clubs:
        if not isinstance(club, dict):
            raise CohortDeltaError("target club rows must be objects")
        cid = club.get("club_carrier_id")
        if not isinstance(cid, int) or isinstance(cid, bool) or cid in clubs_by_carrier:
            raise CohortDeltaError("target club carriers must be unique integers")
        roster_before = club.get("parent_roster_carriers")
        roster_after = club.get("post_roster_carriers")
        if not isinstance(roster_before, list) or not isinstance(roster_after, list):
            raise CohortDeltaError("target club needs complete parent and postimage carrier rosters")
        if (not roster_before or len(roster_before) != len(set(roster_before))
                or roster_before != roster_after):
            raise CohortDeltaError("cohort delta must preserve exact fixed roster slots and their order")
        if club.get("source_fixture_binding_id") not in source_by_id:
            raise CohortDeltaError("club opening order lacks an exact fixture/source-body binding")
        referenced_sources.add(club["source_fixture_binding_id"])
        xi = club.get("starting_xi_carriers")
        compatible_xi = club.get("compatible_native_xi_carriers")
        complete = club.get("complete_order_carriers")
        slot_rows = club.get("source_slot_rows")
        if (not isinstance(xi, list) or len(xi) != 11 or len(set(xi)) != 11
                or not isinstance(compatible_xi, list) or len(compatible_xi) != 11
                or len(set(compatible_xi)) != 11 or set(xi) != set(compatible_xi)
                or not isinstance(complete, list)
                or complete != compatible_xi + [x for x in roster_after if x not in set(xi)]
                or len(complete) != len(roster_after) or len(set(complete)) != len(complete)
                or set(complete) != set(roster_after)):
            raise CohortDeltaError("source XI, compatible native XI, and complete order must be unique, complete, and roster-owned")
        if (not isinstance(slot_rows, list) or len(slot_rows) != 11
                or {row.get("carrier_id") for row in slot_rows if isinstance(row, dict)} != set(xi)):
            raise CohortDeltaError("every source XI carrier needs one typed position binding")
        for row in slot_rows:
            if (not isinstance(row.get("evidence_ids"), list) or not row["evidence_ids"]
                    or any(source_id not in source_by_id for source_id in row["evidence_ids"])):
                raise CohortDeltaError("each source slot needs exact source evidence bindings")
            referenced_sources.update(row["evidence_ids"])
            options = row.get("published_position_options")
            if options is not None:
                if not isinstance(options, list) or not options:
                    raise CohortDeltaError("published position options must be a nonempty list")
                for option in options:
                    if (not isinstance(option, dict) or option.get("source_id") not in source_by_id
                            or option.get("position") not in {"G", "D", "M", "F"}):
                        raise CohortDeltaError("slot position option lacks a bound period source or valid broad role")
                    referenced_sources.add(option["source_id"])
                if row.get("slot_position") not in {option["position"] for option in options}:
                    raise CohortDeltaError("editorial slot position is not supported by a bound published option")
                if len({option["position"] for option in options}) > 1 and not row.get("position_selection_decision"):
                    raise CohortDeltaError("conflicting published positions need an explicit editorial selection")
        expected_compatible = [int(row["carrier_id"]) for role in ("G", "D", "M", "F")
                               for row in slot_rows if row.get("slot_position") == role]
        if (expected_compatible != compatible_xi
                or sum(row.get("slot_position") == "G" for row in slot_rows) != 1
                or any(row.get("slot_position") not in {"G", "D", "M", "F"} for row in slot_rows)):
            raise CohortDeltaError("native XI slot order is not compatible with bound G/D/M/F positions")
        if not isinstance(club.get("native_formation"), str) or not club["native_formation"]:
            raise CohortDeltaError("role-compatible source order needs its formation disposition")
        clubs_by_carrier[cid] = club

    actors = plan.get("actors")
    if not isinstance(actors, list) or not actors:
        raise CohortDeltaError("selected source actors are required")
    seen_actor_ids: set[str] = set()
    seen_destinations: set[int] = set()
    seen_recipe_ids: set[str] = set()
    for actor in actors:
        if not isinstance(actor, dict):
            raise CohortDeltaError("actor bindings must be objects")
        aid = actor.get("player_id")
        destination = actor.get("post_carrier_id")
        club_id = actor.get("club_carrier_id")
        if not isinstance(aid, str) or not aid or aid in seen_actor_ids:
            raise CohortDeltaError("selected source actor IDs must be unique")
        recipe_id = actor.get("recipe_player_id")
        if not isinstance(recipe_id, str) or not recipe_id or recipe_id in seen_recipe_ids:
            raise CohortDeltaError("child recipe actor IDs must be unique and explicit")
        if not isinstance(destination, int) or isinstance(destination, bool) or destination in seen_destinations:
            raise CohortDeltaError("postimage carrier assignments must be unique integers")
        if club_id not in clubs_by_carrier or destination not in clubs_by_carrier[club_id]["post_roster_carriers"]:
            raise CohortDeltaError("actor destination escapes its closed target club roster")
        if actor.get("identity_policy") not in {"same-person-preserve", "new-source-person"}:
            raise CohortDeltaError("actor identity policy is not explicit")
        for field in ("source_name", "published_name", "published_surname", "native_display_name"):
            if not isinstance(actor.get(field), str) or not actor[field].strip():
                raise CohortDeltaError(f"actor {aid} lacks {field}")
        display = actor["native_display_name"]
        published_name = actor["published_name"]
        surname = actor["published_surname"]
        if not (display == published_name or display == surname or display.endswith(" " + surname)):
            raise CohortDeltaError(f"actor {aid} native display is not a whole published name/surname")
        evidence = actor.get("source_binding_ids")
        if (not isinstance(evidence, list) or not evidence
                or any(source_id not in source_by_id for source_id in evidence)):
            raise CohortDeltaError(f"actor {aid} lacks exact source bindings")
        referenced_sources.update(evidence)
        crosswalk = actor.get("identity_crosswalk")
        if actor["identity_policy"] == "new-source-person" and actor["source_name"].casefold() != actor["published_name"].casefold():
            if not isinstance(crosswalk, dict):
                raise CohortDeltaError(f"actor {aid} source/published name alias needs an explicit identity crosswalk")
        if crosswalk is not None:
            if (not isinstance(crosswalk, dict)
                    or crosswalk.get("policy") != "official-profile-and-period-roster-exact-facts-v1"
                    or crosswalk.get("official_profile_source_id") not in source_by_id
                    or crosswalk.get("period_roster_source_id") not in source_by_id
                    or crosswalk.get("official_profile_full_name") != actor["source_name"]
                    or crosswalk.get("period_published_name") != actor["published_name"]
                    or not isinstance(crosswalk.get("same_identity_fields"), dict)
                    or not {"birth_date", "nationality", "height_cm", "broad_position"} <= set(crosswalk["same_identity_fields"])
                    or not isinstance(crosswalk.get("identity_evidence_ids"), list)
                    or not crosswalk["identity_evidence_ids"]
                    or any(source_id not in source_by_id or source_id not in evidence
                           for source_id in crosswalk["identity_evidence_ids"])):
                raise CohortDeltaError(f"actor {aid} alias crosswalk must bind exact official and period source evidence")
            referenced_sources.update(crosswalk["identity_evidence_ids"])
        conflicts = actor.get("source_fact_conflicts", [])
        if not isinstance(conflicts, list):
            raise CohortDeltaError(f"actor {aid} source fact conflicts must be a list")
        for conflict in conflicts:
            if (not isinstance(conflict, dict) or not conflict.get("field")
                    or conflict.get("source_binding_id") not in source_by_id
                    or not conflict.get("native_source_preimage")
                    or not conflict.get("published_source_value")
                    or not conflict.get("disposition")):
                raise CohortDeltaError(f"actor {aid} source fact conflict needs exact source values and disposition")
            referenced_sources.add(conflict["source_binding_id"])
        corrections = actor.get("source_fact_corrections", [])
        if not isinstance(corrections, list):
            raise CohortDeltaError(f"actor {aid} source fact corrections must be a list")
        corrected_fields: set[str] = set()
        for correction in corrections:
            if (not isinstance(correction, dict)
                    or correction.get("field") not in {"birth_date", "nationality", "height_cm", "weight_kg"}
                    or correction["field"] in corrected_fields
                    or correction.get("disposition") not in {"reviewed-source-correction", "verified-no-change"}
                    or correction.get("source_binding_id") not in source_by_id
                    or correction.get("source_row_type") != "footballsquads-mens-squad-row-v1"
                    or not isinstance(correction.get("source_row_text"), str)
                    or _sha_bytes(correction["source_row_text"].encode("utf-8")) != correction.get("source_row_sha256")
                    or not isinstance(correction.get("identity_evidence_ids"), list)
                    or not correction["identity_evidence_ids"]
                    or any(source_id not in source_by_id or source_id not in evidence
                           for source_id in correction["identity_evidence_ids"])):
                raise CohortDeltaError(f"actor {aid} source correction lacks a hash-bound row or identity crosswalk")
            if verify_source_files:
                source_path = _safe_workspace_path(source_by_id[correction["source_binding_id"]]["path"],
                                                   f"source {correction['source_binding_id']}")
                if correction["source_row_text"].encode("utf-8") not in source_path.read_bytes():
                    raise CohortDeltaError(f"actor {aid} exact correction row is absent from its bound source")
            parsed = _parse_footballsquads_row(correction["source_row_text"],
                season_start_year=int(parent['season'][:4]))
            field = correction["field"]
            if parsed[field] is None:
                raise CohortDeltaError(f"actor {aid} correction claims an unavailable published fact: {field}")
            if parsed["name"].casefold() != actor["source_name"].casefold():
                raise CohortDeltaError(f"actor {aid} correction row belongs to another published person")
            if parsed[field] != correction.get("published_value"):
                raise CohortDeltaError(f"actor {aid} correction value differs from its published source row: {field}")
            transfer = actor.get("native_transfer_binding")
            source_semantics = transfer.get("source_native_semantics", {}) if isinstance(transfer, dict) else {}
            native_key = {"birth_date": "birth_date", "nationality": "nationality_iso",
                          "height_cm": "height_cm", "weight_kg": "weight_kg"}[field]
            native_value = source_semantics.get(native_key)
            if correction.get("native_source_preimage") != native_value:
                raise CohortDeltaError(f"actor {aid} correction preimage differs from its bound native source: {field}")
            corrected_fields.add(field)
            referenced_sources.add(correction["source_binding_id"])
            referenced_sources.update(correction["identity_evidence_ids"])
        if actor["identity_policy"] == "same-person-preserve":
            preserve = actor.get("preserve_fields")
            if (not isinstance(preserve, list) or not {"person_id", "ratings"} <= set(preserve)
                    or not ({"facts", "facts_except_explicit_corrections"} & set(preserve))):
                raise CohortDeltaError(f"same-person move {aid} must preserve person, ratings, and unmasked facts")
            transfer = actor.get("native_transfer_binding")
            if not isinstance(transfer, dict):
                raise CohortDeltaError(f"same-person move {aid} lacks bound native source/destination preimages")
            for key in ("source_payload_sha256", "destination_preimage_payload_sha256"):
                _require_sha(transfer.get(key), f"actor {aid}.{key}")
            if (transfer.get("source_carrier_id") != actor.get("pre_carrier_id")
                    or transfer.get("destination_carrier_id") != destination
                    or transfer.get("source_person_id") != actor.get("person_id")
                    or transfer.get("source_recipe_player_id") != actor.get("recipe_player_id")
                    or not isinstance(transfer.get("destination_preimage_recipe_player_id"), str)
                    or not isinstance(transfer.get("source_owner_club_carrier_id"), int)
                    or transfer.get("destination_owner_club_carrier_id") != actor.get("club_carrier_id")):
                raise CohortDeltaError(f"same-person move {aid} native transfer binding identity differs")
        role_projection = actor.get("role_projection")
        if role_projection is not None:
            if (not isinstance(role_projection, dict)
                    or role_projection.get("policy") != "reviewed-editorial-compatible-broad-default"
                    or role_projection.get("primary_position") not in {"G", "D", "M", "F"}
                    or not isinstance(role_projection.get("fine_roles"), list)
                    or not role_projection["fine_roles"]
                    or not role_compatible(role_projection["primary_position"], role_projection["fine_roles"][0])
                    or not role_projection.get("decision")
                    or not isinstance(role_projection.get("evidence_ids"), list)
                    or not role_projection["evidence_ids"]
                    or any(source_id not in source_by_id for source_id in role_projection["evidence_ids"])):
                raise CohortDeltaError(f"actor {aid} role projection is not a sourced compatible editorial choice")
            transfer = actor.get("native_transfer_binding")
            if transfer and transfer.get("source_native_semantics", {}).get("broad_position") != role_projection["primary_position"]:
                raise CohortDeltaError(f"actor {aid} role projection broad position differs from the bound person source")
            referenced_sources.update(role_projection["evidence_ids"])
        if actor.get("facts_binding") is not None and not isinstance(actor["facts_binding"], dict):
            raise CohortDeltaError(f"actor {aid} facts binding must be typed")
        if actor.get("rating_binding") is not None and not isinstance(actor["rating_binding"], dict):
            raise CohortDeltaError(f"actor {aid} rating binding must be typed")
        club = clubs_by_carrier[club_id]
        if actor.get("native_order_after") != club["complete_order_carriers"].index(destination) + 1:
            raise CohortDeltaError(f"actor {aid} native order differs from its exact carrier slot")
        source_slot = next((row for row in club["source_slot_rows"]
                            if row["carrier_id"] == destination), None)
        if source_slot is None:
            if actor.get("opening_membership") == "starting-xi":
                raise CohortDeltaError(f"actor {aid} is marked starter outside the source XI")
        elif (actor.get("opening_membership") != "starting-xi"
              or actor.get("slot_position") != source_slot.get("slot_position")):
            raise CohortDeltaError(f"actor {aid} source XI position binding differs from its native slot")
        seen_actor_ids.add(aid)
        seen_destinations.add(destination)
        seen_recipe_ids.add(recipe_id)

    dispositions = plan.get("source_bound_dispositions", [])
    if not isinstance(dispositions, list):
        raise CohortDeltaError("source-bound dispositions must be a list")
    for disposition in dispositions:
        if not isinstance(disposition, dict) or not disposition.get("evidence_ids"):
            raise CohortDeltaError("each source-bound disposition needs evidence IDs")
        if any(source_id not in source_by_id for source_id in disposition["evidence_ids"]):
            raise CohortDeltaError("source-bound disposition references an unknown source")
        referenced_sources.update(disposition["evidence_ids"])
    if referenced_sources != set(source_by_id):
        raise CohortDeltaError("source bindings must be referenced by an actor or source fixture")
    photos = plan.get("portrait_decisions")
    if (not isinstance(photos, list) or len(photos) != len(seen_actor_ids)
            or {r.get("player_id") for r in photos if isinstance(r, dict)} != seen_actor_ids):
        raise CohortDeltaError("every selected actor needs exactly one explicit portrait decision")
    if any(r.get("status") != "native-no-photo" for r in photos):
        raise CohortDeltaError("this bounded proposal supports only explicit native-no-photo outcomes")
    return {"actor_count": len(actors), "club_carrier_ids": sorted(clubs_by_carrier),
            "source_binding_count": len(source_by_id), "portrait_decision_count": len(photos)}


def validate_parent(plan: Mapping[str, Any], release: Any) -> None:
    """Verify the plan is still based on the exact registered parent bytes."""
    parent = plan["parent"]
    if (parent["season"], parent["release_id"]) != (release.season, release.release_id):
        raise CohortDeltaError("registered parent identity changed")
    if registry.sha256_file(release.package_path) != parent["package_sha256"]:
        raise CohortDeltaError("parent recipe SHA changed")
    for name, expected in parent["native_sha256"].items():
        if registry.sha256_file(release.game_path / "DBDAT" / name) != expected:
            raise CohortDeltaError(f"parent native input SHA changed: {name}")


def apply_order_layer(jug: bytes, eq: bytes, plan: Mapping[str, Any]) -> bytes:
    """Replay the existing owned-mode1 full-order writer from typed source rows."""
    validate_plan(plan)
    rosters, owners = _owner_rosters(eq)
    entries = {int(e.record_id): e for e in IndexedFDIFile.from_bytes(jug).entries}
    output = jug
    for club in plan["clubs"]:
        cid = int(club["club_carrier_id"])
        if rosters.get(cid) != club["parent_roster_carriers"]:
            raise CohortDeltaError(f"club {cid} fixed parent roster changed")
        carriers = club["complete_order_carriers"]
        if any(owners.get(int(carrier)) != {cid} for carrier in carriers):
            raise CohortDeltaError(f"club {cid} order includes a nonexclusive native owner")
        current = {int(e.record_id): e for e in IndexedFDIFile.from_bytes(output).entries}
        replacements = []
        for target_order, carrier in enumerate(carriers, 1):
            payload = current[int(carrier)].decode_payload(output)
            state = read_initial_order(payload)
            replacements.append(OrderReplacement(int(carrier), state.name, state.order, target_order))
        output = patch_owned_mode1_complete_orders(
            output, eq, club_record_id=cid, replacements=replacements
        )
    before = {int(e.record_id): e.decode_payload(jug) for e in IndexedFDIFile.from_bytes(jug).entries}
    after = {int(e.record_id): e.decode_payload(output) for e in IndexedFDIFile.from_bytes(output).entries}
    changed = {carrier for carrier in before if before[carrier] != after[carrier]}
    allowed = {carrier for club in plan["clubs"] for carrier in club["complete_order_carriers"]}
    if not changed <= allowed:
        raise CohortDeltaError("native order replay changed records outside target rosters")
    for club in plan["clubs"]:
        for order, carrier in enumerate(club["complete_order_carriers"], 1):
            if read_initial_order(after[int(carrier)]).order != order:
                raise CohortDeltaError(f"club {club['club_carrier_id']} order readback differs")
    return output


def canonical_apply_after_standard_actor_compile(parent_jug: bytes, compiled_jug: bytes,
                                                  eq: bytes, plan: Mapping[str, Any],
                                                  country_codes: Mapping[str, int]
                                                  ) -> tuple[bytes, dict[str, Any]]:
    """Private prototype for the shared compiler/SOURCE callback.

    Call only after the ordinary package actor compiler has emitted player
    rows. The same callback must be called from build and SOURCE replay; this
    helper verifies bound same-person transfers first, then applies the
    existing complete mode-1 order writer. Photo-off continues through the
    existing no-photo materializer.
    """
    summary = validate_plan(plan)
    unresolved = [actor["player_id"] for actor in plan["actors"]
                  if any(str(conflict.get("disposition", "")).startswith("unresolved-")
                         for conflict in actor.get("source_fact_conflicts", []))]
    if unresolved:
        raise CohortDeltaError(f"source fact conflicts require review before compiler replay: {unresolved}")
    transfer_receipts = verify_same_person_native_transfers(parent_jug, compiled_jug, plan, country_codes)
    output = apply_order_layer(compiled_jug, eq, plan)
    return output, {"plan_summary": summary, "same_person_transfers": transfer_receipts,
                    "order_postimage_sha256": _sha_bytes(output)}


def native_name_roundtrip(payload: bytes, carrier_id: int, current_name: str, desired_name: str) -> bytes:
    """Use the existing checked variable-name encoder; never clip native text."""
    try:
        return compiler._patch_indexed_player_variable_name_payload(
            payload, current_name, desired_name
        )[0]
    except Exception as exc:
        raise CohortDeltaError(f"native published name does not fit carrier {carrier_id}: {exc}") from exc


def native_semantic_snapshot(jug: bytes, carrier_id: int) -> dict[str, Any]:
    """Decode semantic fields from one pinned native player carrier."""
    entries = {int(row.record_id): row for row in IndexedFDIFile.from_bytes(jug).entries}
    entry = entries.get(carrier_id)
    if entry is None:
        raise CohortDeltaError(f"native player carrier {carrier_id} is absent")
    payload = entry.decode_payload(jug)
    try:
        role_start = compiler._native_dd6360_role_start(payload)
        fields = compiler._read_native_dd6360_fields(payload, role_start)
        order = read_initial_order(payload)
    except Exception as exc:
        raise CohortDeltaError(f"carrier {carrier_id} has no checked semantic profile readback: {exc}") from exc
    roles = [int(value) for value in fields["fine_role_codes"] if int(value) != 98]
    position = {0: "G", 1: "D", 2: "M", 3: "F"}.get(int(fields["visible_position_code"]))
    if position is None:
        raise CohortDeltaError(f"carrier {carrier_id} has an unsupported broad position byte")
    return {
        "carrier_id": carrier_id,
        "payload_sha256": _sha_bytes(payload),
        "name": order.name,
        "order": order.order,
        "broad_position": position,
        "fine_roles": roles,
        "nationality_code": int(fields["visible_nationality_code"]),
        "birth_date": f"{int(fields['birth_year']):04d}-{int(fields['birth_month']):02d}-{int(fields['birth_day']):02d}",
        "height_cm": int(fields["height_cm"]),
        "weight_kg": int(fields["weight_kg"]),
        "skills": [int(value) for value in fields["skills"]] + [int(fields["handling"])],
    }


def verify_same_person_native_transfers(parent_jug: bytes, compiled_jug: bytes,
                                         plan: Mapping[str, Any],
                                         country_codes: Mapping[str, int]) -> list[dict[str, Any]]:
    """Require moved same-person semantic fields to follow source carriers.

    Names and startup order are intentionally excluded; all decoded identity,
    broad/fine role, physical, citizenship, and skill fields must match the
    frozen source carrier before any order layer is applied.
    """
    fields = ("broad_position", "fine_roles", "nationality_code", "birth_date",
              "height_cm", "weight_kg", "skills")
    result = []
    for actor in plan["actors"]:
        if actor["identity_policy"] != "same-person-preserve":
            continue
        source = native_semantic_snapshot(parent_jug, int(actor["pre_carrier_id"]))
        target = native_semantic_snapshot(compiled_jug, int(actor["post_carrier_id"]))
        projection = actor.get("role_projection")
        corrections = {row["field"]: row["published_value"] for row in actor.get("source_fact_corrections", [])}
        field_map = {"birth_date": "birth_date", "nationality": "nationality_code",
                     "height_cm": "height_cm", "weight_kg": "weight_kg"}
        corrected_native_fields = {field_map[key] for key in corrections}
        compare_fields = tuple(field for field in fields
                               if field not in corrected_native_fields
                               and not (projection and field == "fine_roles"))
        mismatches = {field: {"source": source[field], "target": target[field]}
                      for field in compare_fields if source[field] != target[field]}
        if projection:
            expected_roles = [int(value) for value in projection["fine_roles"]]
            expected_position = projection["primary_position"]
            if target["fine_roles"] != expected_roles or target["broad_position"] != expected_position:
                mismatches["reviewed_role_projection"] = {
                    "expected_position": expected_position, "actual_position": target["broad_position"],
                    "expected_fine_roles": expected_roles, "actual_fine_roles": target["fine_roles"],
                }
        for field, value in corrections.items():
            native_field = field_map[field]
            expected_value = (country_codes.get(compiler.NATIONALITY.get(value))
                              if field == "nationality" else value)
            if target[native_field] != expected_value:
                mismatches[f"source_fact_correction:{field}"] = {
                    "expected": expected_value, "actual": target[native_field]}
        if mismatches:
            raise CohortDeltaError(
                f"same-person actor {actor['player_id']} native semantic transfer differs: {mismatches}"
            )
        result.append({"actor_id": actor["player_id"], "source_carrier_id": source["carrier_id"],
                       "target_carrier_id": target["carrier_id"], "compared_fields": list(fields),
                       "role_projection": projection,
                       "source_fact_corrections": [dict(row) for row in actor.get("source_fact_corrections", [])],
                       "source_payload_sha256": source["payload_sha256"],
                       "target_payload_sha256": target["payload_sha256"]})
    return result


def bind_same_person_preimages(parent_package: Mapping[str, Any], parent_jug: bytes,
                               parent_eq: bytes, plan: Mapping[str, Any],
                               country_codes: Mapping[str, int]
                               ) -> dict[str, Any]:
    """Attach exact frozen source/destination owner and payload bindings.

    This must run against the pinned parent before child actor rows are made.
    It intentionally binds decoded source identity plus both raw payload hashes;
    the compiler still rewrites semantic values through its standard actor path.
    """
    bound = copy.deepcopy(dict(plan))
    _rosters, owners = _owner_rosters(parent_eq)
    parent_players = {int(row["carrier_id"]): row for row in parent_package["players"]}
    parent_clubs = {row["id"]: int(row["carrier_id"]) for row in parent_package["clubs"]}
    rows_by_carrier = {int(row["carrier_id"]): row for row in parent_package["players"]}
    for actor in bound["actors"]:
        if actor["identity_policy"] != "same-person-preserve":
            continue
        source_carrier, destination = int(actor["pre_carrier_id"]), int(actor["post_carrier_id"])
        source_owners = owners.get(source_carrier, set())
        destination_owners = owners.get(destination, set())
        if len(source_owners) != 1 or len(destination_owners) != 1:
            raise CohortDeltaError(f"same-person actor {actor['player_id']} source/destination owner is not exclusive")
        source_row, destination_row = rows_by_carrier.get(source_carrier), rows_by_carrier.get(destination)
        if source_row is None or destination_row is None:
            raise CohortDeltaError(f"same-person actor {actor['player_id']} source/destination recipe row is absent")
        source_owner = next(iter(source_owners))
        destination_owner = next(iter(destination_owners))
        source_owner_id = parent_clubs.get(source_row.get("club_id"))
        destination_owner_id = parent_clubs.get(destination_row.get("club_id"))
        if source_owner_id != source_owner or destination_owner_id != destination_owner:
            raise CohortDeltaError(f"same-person actor {actor['player_id']} recipe/native owner mismatch")
        if (source_row["id"] != actor["recipe_player_id"]
                or source_row.get("person_id") != actor.get("person_id")
                or destination_owner != actor["club_carrier_id"]):
            raise CohortDeltaError(f"same-person actor {actor['player_id']} source person or destination owner mismatch")
        if source_carrier == destination:
            raise CohortDeltaError("same-person move must use distinct source and destination carriers")
        source = native_semantic_snapshot(parent_jug, source_carrier)
        destination_preimage = native_semantic_snapshot(parent_jug, destination)
        iso_by_code = {int(country_codes[full]): iso for iso, full in compiler.NATIONALITY.items()
                       if full in country_codes}
        source_iso = iso_by_code.get(source["nationality_code"])
        if source_iso is None:
            raise CohortDeltaError("source native nationality code has no checked country mapping")
        source_semantics = {key: source[key] for key in (
            "broad_position", "fine_roles", "nationality_code", "birth_date",
            "height_cm", "weight_kg", "skills")}
        source_semantics["nationality_iso"] = source_iso
        actor["native_transfer_binding"] = {
            "source_carrier_id": source_carrier,
            "destination_carrier_id": destination,
            "source_owner_club_carrier_id": source_owner,
            "destination_owner_club_carrier_id": destination_owner,
            "source_recipe_player_id": source_row["id"],
            "destination_preimage_recipe_player_id": destination_row["id"],
            "source_person_id": source_row["person_id"],
            "source_payload_sha256": source["payload_sha256"],
            "destination_preimage_payload_sha256": destination_preimage["payload_sha256"],
            "source_native_semantics": source_semantics,
        }
    return bound


def same_person_recipe_postimages(parent_package: Mapping[str, Any], parent_jug: bytes,
                                  plan: Mapping[str, Any], country_codes: Mapping[str, int]
                                  ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build standard compiler actor rows from the frozen same-person source.

    The child row keeps person identity and ratings from the pinned source actor.
    Its preserved-mode1 factual markers are expanded only to decoded values in
    that same actor's exact parent native preimage. The package compiler then
    writes those semantic fields through its normal typed path.
    """
    parent_players = {row["id"]: row for row in parent_package["players"]}
    parent_by_carrier = {int(row["carrier_id"]): row for row in parent_package["players"]}
    iso_by_code = {int(country_codes[full]): iso for iso, full in compiler.NATIONALITY.items()
                   if full in country_codes}
    actor_rows, receipts = [], []
    for actor in plan["actors"]:
        if actor["identity_policy"] != "same-person-preserve":
            continue
        if not isinstance(actor.get("native_transfer_binding"), dict):
            raise CohortDeltaError("same-person recipe construction requires bound native preimages")
        source_row = parent_by_carrier.get(int(actor["pre_carrier_id"]))
        if source_row is None or source_row["id"] != actor["recipe_player_id"]:
            raise CohortDeltaError(f"same-person actor {actor['player_id']} source recipe row changed")
        if source_row.get("person_id") != actor.get("person_id"):
            raise CohortDeltaError(f"same-person actor {actor['player_id']} person ID differs from source row")
        source_payload = native_semantic_snapshot(parent_jug, int(actor["pre_carrier_id"]))
        destination_payload = native_semantic_snapshot(parent_jug, int(actor["post_carrier_id"]))
        transfer_binding = actor["native_transfer_binding"]
        if (source_payload["payload_sha256"] != transfer_binding["source_payload_sha256"]
                or destination_payload["payload_sha256"] != transfer_binding["destination_preimage_payload_sha256"]):
            raise CohortDeltaError(f"same-person actor {actor['player_id']} native preimage payload changed after binding")
        nationality = iso_by_code.get(source_payload["nationality_code"])
        if nationality is None:
            raise CohortDeltaError("source native nationality byte has no checked recipe identity mapping")
        current_semantics = {key: source_payload[key] for key in (
            "broad_position", "fine_roles", "nationality_code", "birth_date",
            "height_cm", "weight_kg", "skills")}
        current_semantics["nationality_iso"] = nationality
        if transfer_binding["source_native_semantics"] != current_semantics:
            raise CohortDeltaError(f"same-person actor {actor['player_id']} decoded source semantics changed after binding")
        if (int(actor["pre_carrier_id"]) == int(actor["post_carrier_id"])
                or source_row.get("carrier_family") != parent_by_carrier[int(actor["post_carrier_id"])].get("carrier_family")):
            raise CohortDeltaError("same-person exchange needs distinct same-family source and destination carriers")
        row = copy.deepcopy(source_row)
        row.update({"carrier_id": int(actor["post_carrier_id"]),
                    "club_id": next(c["id"] for c in parent_package["clubs"]
                                    if int(c["carrier_id"]) == int(actor["club_carrier_id"])),
                    "name": actor["native_display_name"]})
        projected_roles = actor.get("role_projection", {}).get("fine_roles", source_payload["fine_roles"])
        projected_position = actor.get("role_projection", {}).get("primary_position", source_payload["broad_position"])
        row["facts"] = {
            "birth_date": source_payload["birth_date"],
            "fine_roles": [int(value) for value in projected_roles],
            "height_cm": source_payload["height_cm"],
            "nationality": nationality,
            "primary_position": projected_position,
            "shirt_number": {"policy": "preserve-existing-mode1"},
            "weight_kg": source_payload["weight_kg"],
        }
        for correction in actor.get("source_fact_corrections", []):
            field = correction["field"]
            if field in {"birth_date", "nationality", "height_cm", "weight_kg"}:
                row["facts"][field] = correction["published_value"]
        row["fact_fallbacks"] = [fallback for fallback in row.get("fact_fallbacks", [])
                                  if fallback.get("field") == "shirt_number"]
        actor_rows.append(row)
        receipts.append({"actor_id": actor["player_id"], "recipe_player_id": row["id"],
                         "person_id": row["person_id"],
                         "source_carrier_id": int(actor["pre_carrier_id"]),
                         "target_carrier_id": int(actor["post_carrier_id"]),
                         "source_payload_sha256": source_payload["payload_sha256"],
                         "target_preimage_payload_sha256": destination_payload["payload_sha256"],
                         "transferred_semantic_fields": ["broad_position", "nationality_code",
                                                           "birth_date", "height_cm", "weight_kg", "skills"],
                         "role_projection": actor.get("role_projection"),
                         "source_fact_corrections": [dict(row) for row in actor.get("source_fact_corrections", [])],
                         "ratings_preserved_from_source_recipe_row": True,
                         "historical_claim_from_native_fallbacks": False})
    return actor_rows, receipts


def canonical_document_sha256(document: Mapping[str, Any]) -> str:
    return _sha_bytes(package_v2.canonical_json_bytes(dict(document)))
