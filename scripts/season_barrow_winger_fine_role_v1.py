"""Canonical-ready, source-bound Barrow fine-role layer.

The only native mutation delegates to the existing primary/fine role writer;
the broad position is required to remain M. FIFA17's DOB is excluded.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from pathlib import Path

from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_exact_primary_position_delta_v2 as native_writer
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.season_within_club_reserve_repair_v1 import native_facts


ROOT = registry.ROOT
INPUT = ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/barrow-2016-canonical-v2/barrow-fine-role-request-v2.json"
REQUEST_SCHEMA = "pm99-barrow-editorial-fine-role-request-v1"
SCHEMA = "pm99-source-bound-barrow-winger-fine-role-v1"
POLICY = "swansea-winger-fifa17-compatible-editorial-role-v1"
MODE = "known-good-baseline-source-bound-barrow-fine-role-v1"
PREFIX = "source-bound-barrow-winger-role-"
_FIFA_MATCHES_BY_BODY = {}


def _sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_bound(path, expected_sha):
    path = (ROOT / path).resolve(strict=True) if not Path(path).is_absolute() else Path(path).resolve(strict=True)
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError("Barrow retained source path escapes workspace")
    body = path.read_bytes()
    if _sha_bytes(body) != expected_sha:
        raise ValueError("Barrow source body/hash binding changed")
    return path, body


def _find_fifa_rows(stream, edition, player_id):
    selected = []
    for row in csv.DictReader(stream):
        if row.get("fifa_version") == edition and row.get("player_id") == player_id:
            selected.append({k: row.get(k) for k in
                ("fifa_version", "fifa_update_date", "player_id", "long_name", "dob", "player_positions")})
            if len(selected) > 1:
                raise ValueError("Barrow FIFA source has ambiguous edition/ID rows")
    return selected


def _fifa_row(req):
    source = req["fifa_source"]
    path = (ROOT / source["path"]).resolve(strict=True)
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError("Barrow FIFA source path escapes workspace")
    first_sha = _sha_file(path)
    if first_sha != source["sha256"]:
        raise ValueError("Barrow FIFA body hash changed")
    key = (first_sha, "17", "207645")
    rows = _FIFA_MATCHES_BY_BODY.get(key)
    if rows is None:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = _find_fifa_rows(stream, "17", "207645")
        # Rehash after the streaming parse to reject a concurrent source change.
        if _sha_file(path) != first_sha:
            raise ValueError("Barrow FIFA source changed while being parsed")
        _FIFA_MATCHES_BY_BODY[key] = tuple(rows)  # cache only the tiny matching row
    wanted = source["row"]
    if len(rows) != 1 or rows[0] != {k: wanted[k] for k in rows[0]}:
        raise ValueError("Barrow FIFA17 ID/name/role row differs")
    if (source.get("dob_use") != "excluded-conflicts-with-target-year-annual-and-native-1992-10-13"
            or rows[0]["dob"] != "1992-10-01" or rows[0]["player_positions"] != "RW, LW, RM"):
        raise ValueError("Barrow FIFA17 DOB conflict or role labels are not explicitly disclosed")
    return dict(row=rows[0], sha256=first_sha, dob_used_for_identity=False)


def _annual_row(req):
    source = req["annual_source"]
    ds_path, ds_bytes = _read_bound(source["dataset"], source["dataset_sha256"])
    raw_path, raw_bytes = _read_bound(source["source_file"], source["source_file_sha256"])
    ds = json.loads(ds_bytes.decode("utf-8"))
    if (ds.get("schema_version") != "pm99-footballsquads-season-capture-v1"
            or ds.get("season", {}).get("label") != "2016/17"):
        raise ValueError("Barrow target-year annual dataset identity differs")
    rel = raw_path.relative_to(ROOT / ".local/external-sources/cache.footballsquads").as_posix()
    clubs = [c for c in ds["clubs"] if c.get("source_path") == rel
             and c.get("source_sha256") == source["source_file_sha256"]]
    row = source["source_row"]
    captured = [p for c in clubs for p in c["players"] if p.get("name") == req["name"]
                and p.get("birth_date") == req["birth_date"]]
    if len(clubs) != 1 or clubs[0].get("club_name") != "Leeds United" or len(captured) != 1:
        raise ValueError("Barrow annual exact source row is absent or ambiguous")
    if (captured[0].get("position") != "F" or row != dict(name="Modou Barrow", birth_date="1992-10-13",
            position="F", source_club="Leeds United", printed_club_field="Swansea C")):
        raise ValueError("Barrow annual source full-name/DOB/position evidence differs")
    csv_rows = []
    for fields in csv.reader(io.StringIO(raw_bytes.decode("utf-8-sig"))):
        if len(fields) >= 8 and fields[1].strip() == req["name"] and fields[6].strip() == "13-10-92":
            csv_rows.append(fields)
            if len(csv_rows) > 1:
                raise ValueError("Barrow annual raw row is ambiguous")
    if (len(csv_rows) != 1 or csv_rows[0][3].strip() != "F" or csv_rows[0][-1].strip() != "Swansea C"):
        raise ValueError("Barrow original annual row failed raw-source reparse")
    return {"dataset": ds_path.relative_to(ROOT).as_posix(), "dataset_sha256": source["dataset_sha256"],
            "source_file": raw_path.relative_to(ROOT).as_posix(), "source_file_sha256": source["source_file_sha256"],
            "full_name": req["name"], "birth_date": req["birth_date"], "source_position": "F",
            "source_club": "Leeds United", "opening_membership_claim": False}


def _club_source(req):
    source = req["club_source"]
    body_path, body = _read_bound(source["path"], source["sha256"])
    receipt_path, receipt_bytes = _read_bound(source["receipt_path"], source["receipt_sha256"])
    receipt = json.loads(receipt_bytes.decode("utf-8"))
    if (receipt.get("url") != source["url"] or receipt.get("path") != source["path"]
            or receipt.get("sha256") != source["sha256"]
            or receipt.get("published_date_evidence", {}).get("date") != "2016-09-02"):
        raise ValueError("Barrow official Swansea body/receipt/date binding differs")
    page = BeautifulSoup(body, "lxml")
    title = page.title.get_text(" ", strip=True) if page.title else ""
    text = " ".join(page.get_text(" ", strip=True).split())
    if (title != "Swans confirm squad numbers | Swansea City"
            or not all(s in text for s in ("2016-17 season", "Winger Modou Barrow", "17. Modou Barrow"))):
        raise ValueError("Barrow original official club page lacks the claimed winger/squad context")
    return {"url": source["url"], "path": body_path.relative_to(ROOT).as_posix(),
            "sha256": source["sha256"], "receipt_path": receipt_path.relative_to(ROOT).as_posix(),
            "receipt_sha256": source["receipt_sha256"], "published_date": "2016-09-02",
            "claim": "official club calls him a winger in 2016-17 squad announcement"}


def filename(plan):
    if plan.get("schema") != SCHEMA or plan.get("policy") != POLICY or plan.get("mode") != MODE:
        raise ValueError("unsupported Barrow source plan")
    return "barrow-winger-fine-role-" + plan["transaction_id"] + ".json"


def artifact_id(plan):
    return PREFIX + plan["transaction_id"]


def prepare(base, input_path=INPUT):
    request_path = Path(input_path)
    if not request_path.is_absolute():
        request_path = ROOT / request_path
    request_path = request_path.resolve(strict=True)
    if not request_path.is_relative_to(ROOT.resolve()):
        raise ValueError("Barrow source request escapes workspace")
    request_bytes = request_path.read_bytes()
    request = json.loads(request_bytes.decode("utf-8"))
    expected_request_keys = {"schema", "season", "release_id", "carrier_id", "name", "birth_date", "before", "after",
        "annual_source", "fifa_source", "club_source", "conflict_disposition"}
    if set(request) != expected_request_keys:
        raise ValueError("Barrow typed request has unknown or missing top-level fields")
    if (request.get("schema") != REQUEST_SCHEMA or base.season != "2016-17"
            or base.release_id != "sourced-alias-primary-positions-20261017-r133a"
            or request.get("season") != base.season or request.get("release_id") != base.release_id
            or request.get("carrier_id") != 9290 or request.get("name") != "Modou Barrow"
            or request.get("birth_date") != "1992-10-13"
            or request.get("before") != {"primary_position": "M", "fine_roles": [9]}
            or request.get("after") != {"primary_position": "M", "fine_roles": [13], "label": "LW",
                                         "policy": "editorial-compatible-wing-role-not-match-deployment-v1"}):
        raise ValueError("Barrow request schema, exact parent, identity, or M-preserving role scope differs")
    annual = _annual_row(request)
    fifa = _fifa_row(request)
    club_source = _club_source(request)
    package_path = base.package_path
    package = pipeline.read_json_file(package_path)
    player = next((p for p in package["players"] if p["carrier_id"] == 9290), None)
    if (player is None or player["facts"].get("birth_date") != request["birth_date"]
            or player["facts"].get("primary_position") != "M" or player["facts"].get("fine_roles") != [9]
            or roster.normalise((player.get("source_name") or player["name"]).removeprefix("#77 ")) != roster.normalise(request["name"])):
        raise ValueError("Barrow exact package name/DOB/broad/fine preimage differs")
    jug_path, eq_path = base.game_path / "DBDAT/JUG98030.FDI", base.game_path / "DBDAT/EQ98030.FDI"
    jug, eq = jug_path.read_bytes(), eq_path.read_bytes()
    jug_sha, eq_sha = _sha_bytes(jug), _sha_bytes(eq)
    if jug_sha != registry.sha256_file(jug_path) or eq_sha != registry.sha256_file(eq_path):
        raise ValueError("Barrow release native source changed during read")
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    if 9290 not in entries:
        raise ValueError("Barrow native carrier absent")
    payload = entries[9290].decode_payload(jug)
    native = roster.native_player(payload, 9290)
    dob = native_facts(jug, 9290)["birth_date"]
    owners = ownership.native_owners(eq)
    club = next(c for c in package["clubs"] if c["id"] == player["club_id"])
    if (roster.normalise(native["name"].removeprefix("#77 ")) != roster.normalise(request["name"])
            or dob != request["birth_date"] or native["position"] != "M"
            or native["roles"] != [9, 98, 98, 98, 98, 98] or club["carrier_id"] != 315
            or player["club_id"] != "english-club-315" or owners.get(9290) != {315}):
        raise ValueError("Barrow native identity/position/role/Swansea exclusive owner preimage differs")
    if 13 not in {6, 7, 9, 10, 11, 13, 14} or "LW" not in fifa["row"]["player_positions"].split(", "):
        raise ValueError("Barrow LW role is not a sourced M-compatible fine role")
    update = {"carrier_id": 9290, "player_id": player["id"], "name": "Modou Barrow",
        "birth_date": "1992-10-13", "before_player": copy.deepcopy(player), "before_native": native,
        "primary_position": "M", "fine_roles_before": [9], "fine_roles": [13],
        "owner_carrier_id": 315, "annual_source": annual, "fifa_source": fifa, "club_source": club_source}
    source_bindings = [{"path": request_path.relative_to(ROOT).as_posix(), "sha256": _sha_bytes(request_bytes)},
        {"path": annual["dataset"], "sha256": annual["dataset_sha256"]},
        {"path": annual["source_file"], "sha256": annual["source_file_sha256"]},
        {"path": request["fifa_source"]["path"], "sha256": fifa["sha256"]},
        {"path": club_source["path"], "sha256": club_source["sha256"]},
        {"path": club_source["receipt_path"], "sha256": club_source["receipt_sha256"]}]
    canonical_adapter_path = ROOT / "scripts/season_barrow_winger_fine_role_v1.py"
    adapter_sha = _sha_file(Path(__file__).resolve())
    if canonical_adapter_path.exists() and _sha_file(canonical_adapter_path) != adapter_sha:
        raise ValueError("Barrow canonical adapter source differs from tested private copy")
    code_paths = (ROOT / "scripts/season_exact_primary_position_delta_v2.py",
        ROOT / "scripts/season_historical_roster_audit_v1.py", ROOT / "scripts/season_opening_order_repair_v1.py",
        ROOT / "scripts/season_package_v2.py", ROOT / "upstream/pm99-skezmod-db-editor/app/indexed_jug_roles.py")
    implementation_bindings = [{"path": "scripts/season_barrow_winger_fine_role_v1.py", "sha256": adapter_sha}]
    implementation_bindings.extend({"path": p.relative_to(ROOT).as_posix(), "sha256": _sha_file(p)} for p in code_paths)
    plan = {"schema": SCHEMA, "policy": POLICY, "mode": MODE, "season": base.season,
        "release_id": base.release_id, "package_sha256": registry.sha256_file(package_path),
        "jug_sha256": jug_sha, "eq_sha256": eq_sha, "updates": [update],
        "source_input": {"path": request_path.relative_to(ROOT).as_posix(), "sha256": _sha_bytes(request_bytes)},
        "source_bindings": source_bindings,
        "implementation_bindings": implementation_bindings,
        "scope": "Only carrier9290 fine role CM9 to editorial-compatible LW13. Preserve broad M, DOB, nationality, ratings, exclusive owner315, all unrelated package facts and all other native bytes.",
        "interpretation": "Official dated club page calls him a winger; FIFA17 lists LW among RW/LW/RM. LW is an editorial compatible role choice, not a match deployment claim.",
        "dob_disposition": "FIFA17 row DOB 1992-10-01 is conflicting and not used; annual/native 1992-10-13 remain authoritative for this scoped correction."}
    plan["transaction_id"] = hashlib.sha256(packages.canonical_json_bytes(plan)).hexdigest()[:24]
    return plan


def verify(base, plan, input_path=None):
    path = input_path or (ROOT / plan["source_input"]["path"])
    if plan.get("schema") != SCHEMA or plan.get("policy") != POLICY or plan.get("mode") != MODE:
        raise ValueError("Barrow plan schema/policy/mode differs")
    if prepare(base, path) != plan:
        raise ValueError("Barrow source/preimage plan did not reproduce")


def bind(package, plan):
    if plan.get("schema") != SCHEMA or plan.get("policy") != POLICY or plan.get("mode") != MODE:
        raise ValueError("Barrow package bind requires its unique source policy")
    base = registry.load_registered_release(plan["season"], plan["release_id"])
    if registry.sha256_file(base.package_path) != plan["package_sha256"] or package != pipeline.read_json_file(base.package_path):
        raise ValueError("Barrow package bind requires exact registered parent")
    verify(base, plan)
    result = copy.deepcopy(package)
    player = next(p for p in result["players"] if p["carrier_id"] == 9290)
    if player != plan["updates"][0]["before_player"]:
        raise ValueError("Barrow player recipe preimage changed")
    player["facts"]["fine_roles"] = [13]
    aid = artifact_id(plan)
    result["artifacts"].append({"id": aid, "kind": "season-input", "relative_path": filename(plan),
        "sha256": hashlib.sha256(packages.canonical_json_bytes(plan)).hexdigest(), "media_type": "application/json"})
    result["artifacts"].sort(key=lambda x: x["id"])
    result["proofs"].append({"id": "proof-" + aid, "grade": "source-receipt", "artifact_id": aid,
        "covers": ["official-swansea-2016-17-winger-source", "FIFA17-listed-compatible-LW-role",
                   "broad-M-and-DOB-preserved", "Swansea-owner315-preserved",
                   "FIFA17-DOB-conflict-explicitly-excluded"]})
    result["proofs"].sort(key=lambda x: x["id"])
    packages.validate_package(result)
    return result


def _writer_bridge(plan):
    update = plan["updates"][0]
    return {"schema": native_writer.SCHEMA, "season": plan["season"], "release_id": plan["release_id"],
        "jug_sha256": plan["jug_sha256"], "eq_sha256": plan["eq_sha256"],
        "updates": [{"carrier_id": update["carrier_id"], "before_native": update["before_native"],
                     "primary_position": "M", "fine_roles": [13]}]}


def apply(jug, eq, plan):
    base = registry.load_registered_release(plan["season"], plan["release_id"])
    verify(base, plan)
    before_jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    before_eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    if (_sha_bytes(before_jug) != plan["jug_sha256"] or _sha_bytes(before_eq) != plan["eq_sha256"]
            or _sha_bytes(eq) != plan["eq_sha256"]):
        raise ValueError("Barrow source plan exact JUG/EQ preimage changed")
    patched, patched_eq = native_writer.apply(jug, eq, _writer_bridge(plan))
    repeat, repeat_eq = native_writer.apply(patched, patched_eq, _writer_bridge(plan))
    if (repeat, repeat_eq) != (patched, patched_eq) or patched_eq != eq:
        raise ValueError("Barrow fine-role native write not idempotent or EQ-preserving")
    if ownership.native_owners(patched_eq) != ownership.native_owners(before_eq):
        raise ValueError("Barrow fine-role change altered exact native owner map")
    return patched, patched_eq


def reject_factory_recipe(package):
    if any(a.get("id", "").startswith(PREFIX) for a in package.get("artifacts", [])):
        raise ValueError("Barrow source role requires its exact SOURCE plan; factory replay refused")


def reconstruction(previous, release_id):
    # Guard wrong modes before touching inherited SOURCE plan locator state.
    receipt_path = getattr(previous, "compiler_receipt_path", None)
    if receipt_path is None:
        return None
    receipt = pipeline.read_json_file(receipt_path)
    if receipt.get("compilation_mode") != MODE:
        return None
    locator = previous.locator or {}
    relative = locator.get("sourced_profile_assignment_plan_path")
    if not relative or Path(relative).is_absolute():
        raise ValueError("Barrow SOURCE plan locator missing or absolute")
    path = (ROOT / relative).resolve(strict=True)
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError("Barrow SOURCE plan locator escapes workspace")
    plan = pipeline.read_json_file(path)
    if plan.get("schema") != SCHEMA:
        return None
    if (plan.get("mode") != MODE or plan.get("policy") != POLICY
            or receipt.get("original_profile_assignment_plan_sha256") != registry.sha256_file(path)):
        raise ValueError("Barrow SOURCE receipt/plan mode or hash differs")
    base = registry.load_registered_release(previous.season, plan["release_id"])
    verify(base, plan, ROOT / plan["source_input"]["path"])
    package = pipeline.read_json_file(previous.package_path)
    if bind(pipeline.read_json_file(base.package_path), plan) != package:
        raise ValueError("Barrow SOURCE would discard recipe changes")
    art = next((a for a in package["artifacts"] if a.get("id") == artifact_id(plan)), None)
    if (art is None or path != (previous.package_path.parent / filename(plan)).resolve()
            or art.get("sha256") != hashlib.sha256(packages.canonical_json_bytes(plan)).hexdigest()):
        raise ValueError("Barrow source artifact path/hash differs")
    for release in (base, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    descriptor_path = previous.package_path.parent / "role-delta-input.json"
    descriptor = pipeline.read_json_file(descriptor_path)
    expected = {"season": base.season, "release_id": base.release_id,
        "package_sha256": registry.sha256_file(base.package_path),
        "jug_sha256": registry.sha256_file(base.game_path / "DBDAT/JUG98030.FDI"), "updates": [], "unresolved": []}
    if descriptor != expected:
        raise ValueError("Barrow SOURCE requires the exact inert player descriptor")
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season, descriptor_path, release_id=release_id,
        source_release_id=base.release_id, profile_assignment_plan_path=path)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != package:
        raise ValueError("Barrow SOURCE replay changed the complete package")
    return {"season": previous.season, "release_id": release_id,
        "complete_game_inventory_identical": True, "complete_recipe_identical": True}
