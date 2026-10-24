"""Project compatible editorial fine roles only for proven stale factory actors.

Retained exact-season source evidence proves identity, DOB and broad position;
the compatible fine position is explicitly editorial. Reuse the common masked
writer, never claim this default was published as a historical fine role.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_adjudicated_player_facts_v1 as adjudicated
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_package_v2 as packages
from scripts import season_source_verified_player_changes_v1 as common_changes
from scripts.season_historical_roster_audit_v1 import native_player
from scripts.season_historical_roster_audit_v1 import normalise as normalize_name
from scripts.season_source_package_builder_v1 import _source_person_id
from scripts.season_exact_fifa_role_delta_v1 import compatible
from scripts.season_within_club_reserve_repair_v1 import native_facts

SCHEMA = common_changes.SCHEMA
INPUT_SCHEMA = common_changes.INPUT_SCHEMA
KIND = "reviewed-editorial-compatible-fine-role-projection"
POLICY = "deterministic-compatible-editorial-fine-role-by-source-broad-not-historical-claim"
EDITORIAL_ROLE_BY_BROAD = {"D": 4, "M": 9, "F": 12}
FACTORY_JUG = registry.ROOT / ".local/season-pipeline-v2/pm99-base-clean/DBDAT/JUG98030.FDI"
PREFIX = "source-backed-player-changes-"


def distinct_factory_identity(factory_name, source_name):
    """Conservatively hold aliases/common tokens rather than infer a new actor."""
    def tokens(name):
        return {normalize_name(token) for token in re.findall(r"[^\W\d_]+", str(name)) if len(normalize_name(token)) > 1}
    factory_tokens, source_tokens = tokens(factory_name), tokens(source_name)
    return bool(factory_tokens and source_tokens
                and all(a not in b and b not in a for a in factory_tokens for b in source_tokens))


def _sha(path: Path) -> str:
    return registry.sha256_file(path)


def _parent(base):
    package = pipeline.read_json_file(base.package_path)
    jug_path = base.game_path / "DBDAT/JUG98030.FDI"
    eq_path = base.game_path / "DBDAT/EQ98030.FDI"
    return package, jug_path.read_bytes(), eq_path.read_bytes()


def prepare_request(base, request, input_path):
    if (request.get("schema") != INPUT_SCHEMA or request.get("kind") != KIND
            or request.get("season") != base.season or request.get("release_id") != base.release_id
            or type(request.get("carrier_id")) is not int or request.get("policy") != POLICY):
        raise ValueError("exact registered parent and reviewed editorial policy required")
    target = request["carrier_id"]
    package, jug, eq = _parent(base)
    if (_sha(base.package_path) != request.get("parent_package_sha256")
            or _sha(base.release_manifest_path) != request.get("parent_manifest_sha256")
            or _sha(base.game_path / "DBDAT/JUG98030.FDI") != request.get("parent_jug_sha256")
            or _sha(base.game_path / "DBDAT/EQ98030.FDI") != request.get("parent_eq_sha256")):
        raise ValueError("registered parent package/native bindings changed")
    witness = request.get("historical_identity_witness")
    if not isinstance(witness, dict):
        raise ValueError("exact historical identity witness required")
    provider_id = witness.get("historical_identity", {}).get("provider_player_id")
    if (type(provider_id) not in (int, str) or not str(provider_id).isdigit() or int(provider_id) < 1
            or adjudicated.verify_historical_identity(witness) != int(provider_id)):
        raise ValueError("existing original fixture/preallocation identity proof failed")
    preallocation = registry.ROOT / witness["historical_identity"]["preallocation"]["path"]
    match_path = registry.ROOT / witness["historical_identity"]["match"]["path"]
    allocation = pipeline.read_json_file(preallocation)
    row_sha = witness["historical_identity"]["source_row_sha256"]
    source_rows = [(club, row) for club in allocation["source_clubs"] for row in club["players"]
                   if row.get("source_row_sha256") == row_sha]
    if len(source_rows) != 1:
        raise ValueError("one exact historical source-row hash required")
    source_club, source_row = source_rows[0]
    source_facts = source_row.get("facts", {})
    if (source_row.get("opening_source_player_id") != str(witness["historical_identity"]["provider_player_id"])
            or _source_person_id(source_row) != witness.get("person_id")
            or source_facts.get("name") != witness.get("full_name")
            or not source_facts.get("birth_date")
            or source_facts.get("position") not in ("D", "M", "F")
            or source_club.get("opening_source_match_id") != str(witness["historical_identity"]["match_id"])
            or source_club.get("opening_fixture_date") != witness["historical_identity"]["match"]["date"]
            or source_club["opening_fixture_date"][:4] != base.season[:4]):
        raise ValueError("source row must rebind provider ID, identity, DOB, broad role and target-year fixture")
    source_broad = source_facts["position"]
    editorial_fine = EDITORIAL_ROLE_BY_BROAD[source_broad]
    if not compatible(source_broad, editorial_fine):
        raise ValueError("fixed editorial fallback is incompatible with source broad role")
    source_bindings = {
        "preallocation": {"path": registry.relative_workspace_path(preallocation), "sha256": _sha(preallocation)},
        "fixture": {"path": registry.relative_workspace_path(match_path), "sha256": _sha(match_path)},
    }
    expected_bindings = request.get("source_bindings")
    if expected_bindings != source_bindings:
        raise ValueError("source input paths/hashes are not the reviewed retained originals")
    players = {p["carrier_id"]: p for p in package["players"]}
    target = request["carrier_id"]
    artifact_id = "opening-squad-preallocation-" + base.season
    artifact_rows = [a for a in package.get("artifacts", []) if a.get("id") == artifact_id]
    if len(artifact_rows) != 1 or artifact_rows[0].get("sha256") != request["historical_identity_witness"]["historical_identity"]["preallocation"]["sha256"]:
        raise ValueError("parent recipe does not bind exact historical preallocation source")
    actor = players[target]
    if (actor.get("source_name") != witness["full_name"] or actor["facts"].get("primary_position") != source_broad
            or actor["facts"].get("birth_date") != source_facts["birth_date"]
            or actor["facts"].get("fine_roles") != {"policy": "preserve-existing-mode1"}
            or actor.get("proof", {}).get("artifact_id") != artifact_id
            or actor.get("proof", {}).get("grade") != "source-captured"
            or actor.get("person_id") != witness.get("person_id")
            or any(f.get("field") == "birth_date" for f in actor.get("fact_fallbacks", []))):
        raise ValueError("recipe identity, broad role, or preserve-existing fine-role preimage differs")
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    entry = entries[target]
    payload = entry.decode_payload(jug)
    current_roles_end, current_roles = read_indexed_native_roles(payload, target)
    observed = native_player(payload, target)
    facts = native_facts(jug, target)
    club = next(c for c in package["clubs"] if c["id"] == actor["club_id"])
    owners = ownership.native_owners(eq)
    if (normalize_name(observed["name"]) != normalize_name(actor["name"])
            or observed["position"] != source_broad or facts["birth_date"] != source_facts["birth_date"]
            or owners.get(target) != {club["carrier_id"]}):
        raise ValueError("source/recipe/native identity, broad role, DOB or exclusive owner differs")
    factory = FACTORY_JUG.read_bytes()
    factory_entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(factory).entries}
    factory_entry = factory_entries[target]
    factory_payload = factory_entry.decode_payload(factory)
    factory_roles_end, factory_roles = read_indexed_native_roles(factory_payload, target)
    factory_native = native_player(factory_payload, target)
    factory_facts = native_facts(factory, target)
    if (factory_roles != current_roles or current_roles[0] == 98
            or factory_native["position"] not in ("D", "M", "F")
            or factory_facts["birth_date"] == facts["birth_date"]
            or source_broad == factory_native["position"] or compatible(source_broad, current_roles[0])
            or not compatible(factory_native["position"], factory_roles[0])
            or not distinct_factory_identity(factory_native["name"], witness["full_name"])):
        raise ValueError("factory record must prove inherited roles on a different-DOB, name-distinct, compatible broad-role actor")
    preserved_country_native = payload[observed["name_end"] + 8] ^ 0x61
    after_roles = [editorial_fine, 98, 98, 98, 98, 98]
    masks = []
    for i, role in enumerate(after_roles):
        offset = entry.payload_offset + current_roles_end + 2 + i
        old = 0 if current_roles[i] == 98 else current_roles[i] + 1
        new = 0 if role == 98 else role + 1
        if jug[offset] != old:
            raise ValueError("fine-role byte boundary/preimage differs")
        masks.append(dict(file="DBDAT/JUG98030.FDI", record_offset=current_roles_end + 2 + i,
                          file_offset=offset, before=old, after=new))
    candidate = bytearray(jug)
    for mask in masks:
        candidate[mask["file_offset"]] = mask["after"]
    reread_roles_end, reread_roles = read_indexed_native_roles(entry.decode_payload(bytes(candidate)), target)
    if reread_roles_end != current_roles_end or reread_roles != after_roles:
        raise ValueError("six-byte postimage did not reread as the compatible editorial set")
    if native_facts(bytes(candidate), target) != facts:
        raise ValueError("fine-role postimage changed identity/country/DOB/broad facts")
    update = dict(carrier_id=target, before=copy.deepcopy(actor), values={"fine_roles": [editorial_fine]},
        field_mask=["fine_roles"], native_masks=masks,
        evidence=dict(historical_identity_witness=copy.deepcopy(witness), source_bindings=source_bindings,
            historical_source_row=dict(source_row_sha256=row_sha, provider_player_id=str(witness["historical_identity"]["provider_player_id"]),
                full_name=witness["full_name"], birth_date=source_facts["birth_date"], broad_position=source_broad,
                fixture_match_id=str(witness["historical_identity"]["match_id"]), fixture_date=source_club["opening_fixture_date"]),
            before_native_roles=current_roles, after_native_roles=after_roles,
            factory_preimage=dict(path=registry.relative_workspace_path(FACTORY_JUG), sha256=_sha(FACTORY_JUG),
                name=factory_native["name"], broad=factory_native["position"],
                birth_date=factory_facts["birth_date"], roles=factory_roles),
            editorial_provenance=dict(policy=POLICY, editorial_choice=source_broad, fine_role_code=editorial_fine,
                source_claim="No historical fine-role source claim; original source proves broad " + source_broad + " only.",
                rationale="The configured role is an explicitly reviewed compatible representative for retained broad position; inherited incompatible secondary roles are stale from a different-DOB factory actor.")),
        expected_owner=club["carrier_id"])
    result = dict(
        schema=SCHEMA, kind=KIND, policy=POLICY, season=base.season, release_id=base.release_id,
        parent=dict(package_sha256=_sha(base.package_path), manifest_sha256=_sha(base.release_manifest_path),
                    jug_sha256=_sha(base.game_path / "DBDAT/JUG98030.FDI"), eq_sha256=_sha(base.game_path / "DBDAT/EQ98030.FDI")),
        package_sha256=_sha(base.package_path), jug_sha256=_sha(base.game_path / "DBDAT/JUG98030.FDI"),
        eq_sha256=_sha(base.game_path / "DBDAT/EQ98030.FDI"),
        source_input=dict(path=registry.relative_workspace_path(input_path), sha256=_sha(input_path)),
        updates=[update], expected_country_native=preserved_country_native,
        scope="Only target recipe fine_roles and six exact target JUG fine-role bytes. Preserve current nationality/country, DOB, names, identity, broad role, all ratings, club/EQ ownership/order/tactics, managers, kits, photos and every other byte.")
    result["transaction_id"] = common_changes.digest(packages.canonical_json_bytes(result))[:24]
    return result


def prepare(base, input_path):
    path = Path(input_path)
    resolved = registry.ROOT / registry.relative_workspace_path(path)
    request = pipeline.read_json_file(resolved)
    return prepare_request(base, request, resolved)


def request_from_plan(plan):
    p = plan["parent"]
    witness=plan["updates"][0]["evidence"]["historical_identity_witness"]
    return dict(schema=INPUT_SCHEMA, kind=KIND, policy=POLICY, season=plan["season"], release_id=plan["release_id"],
                carrier_id=plan["updates"][0]["carrier_id"], parent_package_sha256=p["package_sha256"],
                parent_manifest_sha256=p["manifest_sha256"], parent_jug_sha256=p["jug_sha256"],
                parent_eq_sha256=p["eq_sha256"], historical_identity_witness=witness,
                source_bindings=plan["updates"][0]["evidence"]["source_bindings"])


def verify(base, request, plan):
    input_path = registry.ROOT / plan["source_input"]["path"]
    if (not input_path.resolve().is_relative_to(registry.ROOT.resolve())
            or _sha(input_path) != plan["source_input"]["sha256"]
            or pipeline.read_json_file(input_path) != request
            or prepare_request(base, request, input_path) != plan):
        raise ValueError("fresh exact source/native proof does not reproduce the proposed plan")



def validate_mask(plan):
    if plan.get("schema") != SCHEMA or plan.get("kind") != KIND or plan.get("policy") != POLICY:
        raise ValueError("explicit reviewed editorial projection policy required")
    base = registry.load_registered_release(plan["season"], plan["release_id"])
    verify(base, request_from_plan(plan), plan)
