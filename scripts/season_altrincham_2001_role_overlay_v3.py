"""Private, source-bound fine-role overlay for the rejected r221 V2 proposal.

The V2 adapter/source proof remains unchanged. This wrapper carries its exact
prepared plan and changes only four documented fine-role bytes and the
corresponding four recipe facts. It never writes a release tree.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from app.indexed_jug_roles import read_indexed_native_roles, rewrite_indexed_native_roles
from app.fdi_indexed import IndexedFDIFile
from scripts import season_altrincham_2001_whole_club_v2 as v2
from scripts import season_package_v2 as package_v2
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline

HERE = Path(__file__).resolve().parent
SEASON = "2001-02"
PARENT = "sourced-anelka-traore-lens-chain-20261024-r219a"
BASE_PLAN_PATH = registry.ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/altrincham-2001-delivery-v2/altrincham-2001-whole-club-exchange-v2.json"
BASE_PLAN_SHA256 = "b4c8e4e4346043161c7eb3f4119828b8924eaa61139991b029c4dc7e7b0d248c"
SCHEMA = "pm99-source-bound-altrincham-2001-role-overlay-v3"
MODE = "exact-source-2001-08-11-altrincham-four-fine-role-overlay-v3"
FILENAME = "altrincham-2001-role-overlay-exchange-v3.json"
INNER_FILENAME = "altrincham-2001-role-overlay-source-v3.json"
SOURCE_SCHEMA = "pm99-private-altrincham-2001-role-overlay-source-v3"
ARTIFACT_ID = "altrincham-2001-original-archive-source-v1"
_CACHE: dict[str, dict[str, Any]] = {}

ROLE_UPDATES = {
    27011: {"name": "Steve Hawes", "before": [4], "after": [1], "label": "Right Back",
        "source_basis": "The 11-Aug match report identifies Hawes as a full-back and lists him at shirt/lineup number 2; right-side assignment follows the numbered XI convention and is declared as an editorial side mapping. The exact 2000-01 profile independently records Hawes playing right-back."},
    10959: {"name": "Chris Adams", "before": [4], "after": [2], "label": "Left Back",
        "source_basis": "The 11-Aug match report identifies Adams as a full-back and lists him at shirt/lineup number 3; left-side assignment follows the numbered XI convention and is declared as an editorial side mapping, not a verbatim left-back quote."},
    10955: {"name": "Jason Gallagher", "before": [9], "after": [6], "label": "Right Midfielder",
        "source_basis": "The dated 11-Aug match report places Gallagher on the right; the exact 2000-01 Altrincham squad profile says he generally operated on the right as a midfielder."},
    10962: {"name": "Danny Murphy", "before": [9], "after": [10], "label": "Left Midfielder",
        "source_basis": "The dated 11-Aug match report places Murphy on the left of the midfield."},
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(document: dict) -> bytes:
    return package_v2.canonical_json_bytes(document)


def _load_base_plan() -> dict:
    raw = BASE_PLAN_PATH.read_bytes()
    if _sha(raw) != BASE_PLAN_SHA256:
        raise ValueError("pinned V2 exchange bytes differ")
    doc = json.loads(raw)
    if doc.get("schema") != v2.SCHEMA or doc.get("mode") != v2.MODE:
        raise ValueError("pinned base plan is not the exact canonical V2 exchange")
    if doc.get("parent", {}).get("release_id") != PARENT:
        raise ValueError("V2 base plan no longer binds exact current r219 parent")
    return doc


def _source_rows(base_plan: dict) -> dict[str, dict]:
    return {row["id"]: row for row in base_plan["inner_source_plan"].get("source_bindings", [])}


def _body(base_plan: dict, source_id: str) -> bytes:
    row = _source_rows(base_plan).get(source_id)
    if not row or row.get("kind") != "raw-source-body":
        raise ValueError(f"role evidence source is not a retained original body: {source_id}")
    path = (registry.ROOT / row["path"]).resolve()
    registry.relative_workspace_path(path)
    raw = path.read_bytes()
    if _sha(raw) != row.get("sha256"):
        raise ValueError(f"role evidence source hash mismatch: {source_id}")
    return raw


def _role_evidence(base_plan: dict) -> dict:
    report_raw = _body(base_plan, "aug11-report")
    profile_raw = _body(base_plan, "2000-profile-cross-season")
    report = " ".join(BeautifulSoup(report_raw, "lxml").get_text(" ", strip=True).split())
    profile = " ".join(BeautifulSoup(profile_raw, "lxml").get_text(" ", strip=True).split())
    must = (
        "with Hawes and Adams at full-back",
        "Midfield comprised Gallagher on the right, Murphy on the left and Craney and Hulme in the centre",
        "2. Steve HAWES",
        "3. Chris ADAMS",
        "pacy and hard-working midfielder who generally operates on the right",
        "He also can play very well at right-back",
    )
    combined = report + " " + profile
    if any(phrase.casefold() not in combined.casefold() for phrase in must):
        raise ValueError("dated role evidence no longer supports the narrow four-role overlay")
    bindings = _source_rows(base_plan)
    return {
        "source_bindings": [copy.deepcopy(bindings[key]) for key in ("aug11-report", "2000-profile-cross-season")],
        "claims": [{"carrier_id": cid, **copy.deepcopy(spec)} for cid, spec in ROLE_UPDATES.items()],
        "nonclaims": [
            "The source sheet directly states full-back for Hawes and Adams, but not a left/right word; shirt/lineup numbers 2 and 3 are used only for a declared editorial side assignment.",
            "The overlay makes no claim about current club registration beyond the retained 11-Aug preseason team sheet.",
            "It does not change broad positions, ratings, DOB, nationality, shirt, height, weight, club ownership, opening order, tactics, manager, ground, or photos.",
        ],
    }


def _overlay(base_package: dict, base_jug: bytes, base_plan: dict, inner: dict | None = None):
    evidence = _role_evidence(base_plan)
    package = copy.deepcopy(base_package)
    player_by_id = {row["carrier_id"]: row for row in package["players"]}
    for cid, spec in ROLE_UPDATES.items():
        row = player_by_id.get(cid)
        if (row is None or row.get("source_name") != spec["name"]
                or row.get("facts", {}).get("primary_position") not in ("D", "M")):
            raise ValueError(f"exact Altrincham actor identity/broad position differs at {cid}")
        if row.get("facts", {}).get("fine_roles") != spec["before"]:
            raise ValueError(f"unexpected V2 package fine-role preimage at {cid}")
        row["facts"]["fine_roles"] = list(spec["after"])
    updated, audit = rewrite_indexed_native_roles(base_jug, {cid: spec["after"] for cid, spec in ROLE_UPDATES.items()})
    for row in audit:
        expected = ROLE_UPDATES[row["carrier_id"]]["before"]
        if row["before"][:1] != expected:
            raise ValueError(f"native fine-role preimage mismatch at {row['carrier_id']}")
    if {row["carrier_id"] for row in audit} != set(ROLE_UPDATES):
        raise ValueError("expected exactly four native role edits")
    for cid, spec in ROLE_UPDATES.items():
        entry = next(e for e in IndexedFDIFile.from_bytes(updated).entries if e.record_id == cid)
        payload = entry.decode_payload(updated)
        _, roles = read_indexed_native_roles(payload, cid)
        if roles[0] != spec["after"][0]:
            raise ValueError(f"native role readback mismatch at {cid}")

    inner_doc = inner or {
        "schema": SOURCE_SCHEMA,
        "source_release_id": PARENT,
        "base_v2_exchange_sha256": BASE_PLAN_SHA256,
        "base_v2_inner_source_plan": copy.deepcopy(base_plan["inner_source_plan"]),
        "base_v2_inner_source_plan_sha256": base_plan["inner_source_plan_sha256"],
        "dated_role_evidence": evidence,
        "role_native_byte_audit": audit,
        "role_facts_after": {str(cid): list(spec["after"]) for cid, spec in ROLE_UPDATES.items()},
        "publication_approved": False,
    }
    art = [a for a in package.get("artifacts", []) if a.get("id") == ARTIFACT_ID]
    if len(art) != 1:
        raise ValueError("expected exactly one existing V2 Altrincham source artifact descriptor")
    inner_bytes = _canonical(inner_doc)
    art[0]["relative_path"] = INNER_FILENAME
    art[0]["sha256"] = _sha(inner_bytes)
    return package, updated, inner_doc, inner_bytes, audit


def _compile(base, *, expected_plan: dict | None = None) -> dict:
    if base.season != SEASON or base.release_id != PARENT:
        raise ValueError("Altrincham role overlay is bound to exact unpreferred r219 parent")
    if expected_plan is None:
        v2_plan = _load_base_plan()
    else:
        v2_plan = copy.deepcopy(expected_plan.get("base_v2_exchange"))
        if not isinstance(v2_plan, dict) or _sha(_canonical(v2_plan)) != BASE_PLAN_SHA256:
            raise ValueError("embedded V2 source exchange differs from the exact reviewed base")
    v2.verify(base, v2_plan)
    # Recheck immutable source/parent bindings above before using cached results.
    cache_key = _sha(_canonical({"base": v2_plan,
        "adapter_sha256": registry.sha256_file(Path(__file__).resolve()),
        "role_writer_sha256": registry.sha256_file(registry.ROOT / "upstream/pm99-skezmod-db-editor/app/indexed_jug_roles.py")}))
    if cache_key in _CACHE:
        cached = _CACHE[cache_key]
        if expected_plan is not None and cached["plan"] != expected_plan:
            raise ValueError("cached V3 plan differs from exact source-bound exchange")
        return copy.deepcopy(cached)
    cache2 = v2._compile(base, expected_plan=v2_plan)
    base_package = cache2["result"]["package"]
    base_files = cache2["result"]["native_files"]
    package, jug, inner_doc, inner_bytes, audit = _overlay(
        base_package, base_files["JUG98030.FDI"], v2_plan)
    native = {"JUG98030.FDI": jug,
        "EQ98030.FDI": base_files["EQ98030.FDI"],
        "ENT98030.FDI": base_files["ENT98030.FDI"],
        "MINIFOTO.PKF": base_files["MINIFOTO.PKF"]}
    inner_hash = _sha(inner_bytes)
    sources = copy.deepcopy(v2_plan.get("source_bindings", []))
    implementations = [
        {"path": "scripts/season_altrincham_2001_whole_club_v2.py", "sha256": registry.sha256_file(registry.ROOT / "scripts/season_altrincham_2001_whole_club_v2.py")},
        {"path": "upstream/pm99-skezmod-db-editor/app/indexed_jug_roles.py", "sha256": registry.sha256_file(registry.ROOT / "upstream/pm99-skezmod-db-editor/app/indexed_jug_roles.py")},
        {"path": registry.relative_workspace_path(Path(__file__).resolve()), "sha256": registry.sha256_file(Path(__file__).resolve())},
    ]
    plan = {
        "schema": SCHEMA, "mode": MODE, "season": SEASON,
        "parent": copy.deepcopy(v2_plan["parent"]),
        "base_v2_exchange": copy.deepcopy(v2_plan),
        "base_v2_exchange_sha256": BASE_PLAN_SHA256,
        "source_bindings": sources,
        "implementation_bindings": implementations,
        "inner_source_plan": inner_doc,
        "inner_source_plan_filename": INNER_FILENAME,
        "inner_source_plan_sha256": inner_hash,
        "package_postimage_sha256": _sha(_canonical(package)),
        "native_postimages": {k: _sha(v) for k, v in native.items()},
        "selected_jug_carriers": sorted(v2.selected_carriers(v2_plan)),
        "selected_eq_carriers": [3310], "selected_ent_carriers": [807],
        "role_overlay_carriers": sorted(ROLE_UPDATES),
        "publication_approved": False,
        "scope": "Exact V2 Altrincham source plan plus four source-bound fine-role edits only.",
    }
    plan["transaction_id"] = _sha(_canonical(plan))[:24]
    result = {"plan": plan, "package": package, "native": native,
        "parent_package": json.loads(base.package_path.read_bytes()),
        "parent_native": {name: (base.game_path / "DBDAT" / name).read_bytes()
                          for name in ("JUG98030.FDI", "EQ98030.FDI", "ENT98030.FDI", "MINIFOTO.PKF")},
        "v2_plan": v2_plan, "audit": audit}
    if expected_plan is not None and plan != expected_plan:
        raise ValueError("V3 role overlay does not reproduce exact saved plan")
    _CACHE[cache_key] = copy.deepcopy(result)
    return result


def prepare(base) -> dict:
    if registry.load_preferred_release(SEASON).release_id != PARENT:
        raise ValueError("prepare only accepts current preferred r219 parent; rebase after children")
    return copy.deepcopy(_compile(base)["plan"])


def verify(base, plan: dict) -> None:
    if plan.get("schema") != SCHEMA or plan.get("mode") != MODE or plan.get("season") != SEASON:
        raise ValueError("role overlay requires exact schema/mode/season")
    if plan.get("publication_approved") is not False:
        raise ValueError("source plan cannot self-authorize publication")
    if plan.get("base_v2_exchange_sha256") != BASE_PLAN_SHA256:
        raise ValueError("base V2 exchange hash differs")
    _compile(base, expected_plan=plan)


def bind(package: dict, plan: dict) -> dict:
    base = registry.load_registered_release(SEASON, plan["parent"]["release_id"])
    verify(base, plan)
    result = _compile(base, expected_plan=plan)
    if package not in (result["parent_package"], result["package"]):
        raise ValueError("bind accepts only exact parent or exact V3 postimage package")
    return copy.deepcopy(result["package"])


def apply(jug: bytes, eq: bytes, plan: dict) -> tuple[bytes, bytes]:
    base = registry.load_registered_release(SEASON, plan["parent"]["release_id"])
    verify(base, plan)
    result = _compile(base, expected_plan=plan)
    before = (result["parent_native"]["JUG98030.FDI"], result["parent_native"]["EQ98030.FDI"])
    after = (result["native"]["JUG98030.FDI"], result["native"]["EQ98030.FDI"])
    if (jug, eq) not in (before, after):
        raise ValueError("paired JUG/EQ accepts only exact source or exact V3 postimage")
    return after


def apply_ent(ent: bytes, plan: dict) -> bytes:
    base = registry.load_registered_release(SEASON, plan["parent"]["release_id"])
    verify(base, plan)
    result = _compile(base, expected_plan=plan)
    before, after = result["parent_native"]["ENT98030.FDI"], result["native"]["ENT98030.FDI"]
    if ent not in (before, after): raise ValueError("ENT accepts only exact source or postimage")
    return after


def apply_minifoto(archive: bytes, plan: dict) -> bytes:
    base = registry.load_registered_release(SEASON, plan["parent"]["release_id"])
    verify(base, plan)
    result = _compile(base, expected_plan=plan)
    before, after = result["parent_native"]["MINIFOTO.PKF"], result["native"]["MINIFOTO.PKF"]
    if archive not in (before, after): raise ValueError("MINIFOTO accepts only exact source or postimage")
    return after


def selected_carriers(plan: dict) -> set[int]:
    if plan.get("schema") != SCHEMA or plan.get("mode") != MODE: raise ValueError("wrong V3 route")
    return set(plan["selected_jug_carriers"])


def photo_offsets(plan: dict) -> dict[int, list[int]]:
    base = registry.load_registered_release(SEASON, plan["parent"]["release_id"])
    verify(base, plan)
    return v2.photo_offsets(plan["base_v2_exchange"])


def filename(plan: dict) -> str:
    if plan.get("schema") != SCHEMA or plan.get("mode") != MODE: raise ValueError("wrong V3 route")
    return FILENAME


def source_artifact(plan: dict) -> dict[str, Any]:
    base = registry.load_registered_release(SEASON, plan["parent"]["release_id"])
    verify(base, plan)
    document = copy.deepcopy(plan["inner_source_plan"])
    raw = _canonical(document)
    if _sha(raw) != plan.get("inner_source_plan_sha256"):
        raise ValueError("V3 inner source artifact hash differs")
    return {"filename": INNER_FILENAME, "document": document, "sha256": _sha(raw), "bytes": raw}


def reject_factory_recipe(package: dict) -> None:
    if any(a.get("relative_path") == INNER_FILENAME for a in package.get("artifacts", [])):
        raise ValueError("V3 Altrincham role overlay requires source-bound reconstruction")


def reconstruction(previous, release_id: str):
    receipt = pipeline.read_json_file(previous.compiler_receipt_path)
    if receipt.get("compilation_mode") != MODE: return None
    relative = previous.locator.get("sourced_profile_assignment_plan_path")
    if not relative: raise ValueError("V3 SOURCE lacks exact outer plan locator")
    plan_path = (registry.ROOT / relative).resolve()
    plan = pipeline.read_json_file(plan_path)
    parent = registry.load_registered_release(SEASON, plan["parent"]["release_id"])
    verify(parent, plan)
    if (plan_path != (previous.package_path.parent / filename(plan)).resolve()
            or registry.sha256_file(plan_path) != receipt.get("original_profile_assignment_plan_sha256")):
        raise ValueError("V3 SOURCE outer plan path/hash mismatch")
    artifact = source_artifact(plan)
    artifact_path = previous.package_path.parent / artifact["filename"]
    if registry.sha256_file(artifact_path) != artifact["sha256"]:
        raise ValueError("V3 SOURCE inner artifact hash mismatch")
    expected = bind(json.loads(parent.package_path.read_bytes()), plan)
    previous_package_bytes = previous.package_path.read_bytes()
    if (json.loads(previous_package_bytes) != expected or previous_package_bytes != _canonical(expected)):
        raise ValueError("V3 SOURCE package differs from exact source-bound overlay")
    inventory = pipeline.read_json_file(previous.inventory_path)
    pipeline.assert_tree_matches_inventory(previous.game_path, inventory)
    descriptor = previous.package_path.parent / "role-delta-input.json"
    expected_descriptor = {"season": SEASON, "release_id": parent.release_id,
        "package_sha256": plan["parent"]["package_sha256"],
        "jug_sha256": plan["parent"]["native_sha256"]["JUG98030.FDI"], "updates": [], "unresolved": []}
    if pipeline.read_json_file(descriptor) != expected_descriptor:
        raise ValueError("V3 SOURCE role descriptor is not the exact inert input")
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(SEASON, descriptor, release_id=release_id, source_release_id=parent.release_id,
        profile_assignment_plan_path=plan_path)
    rebuilt = registry.load_registered_release(SEASON, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, inventory)
    if (json.loads(rebuilt.package_path.read_bytes()) != expected
            or rebuilt.package_path.read_bytes() != previous_package_bytes):
        raise ValueError("V3 SOURCE complete game/recipe replay differs")
    return {"season": SEASON, "release_id": release_id,
        "compilation_mode": MODE, "complete_game_inventory_identical": True,
        "complete_recipe_identical": True}
