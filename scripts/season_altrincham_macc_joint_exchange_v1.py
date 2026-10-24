"""Source-bound prepare/verify/bind/apply wrapper for the Alty/Macc source transaction.

This follows the publisher's source-bound profile-assignment API. All inputs
and output byte changes remain pinned to r210a; apply_ent is explicit because
the existing publisher treats ENT as a distinct native postimage.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import copy
from pathlib import Path
from typing import Any

from scripts import season_package_v2 as package_v2
from scripts import season_release_registry_v1 as registry

COMPILER_PATH = registry.ROOT / "scripts/season_altrincham_joint_native_v1.py"
SPEC = importlib.util.spec_from_file_location("alty_macc_native_compiler_private", COMPILER_PATH)
assert SPEC is not None and SPEC.loader is not None
compiler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compiler)

SCHEMA = "pm99-source-bound-altrincham-macc-joint-exchange-v1"
MODE = "exact-r210a-18-person-altrincham-plus-macc-bettney-four-file-composition-v1"
SEASON = "2000-01"
RELEASE_ID = compiler.R210_ID
REQUIRED_NATIVE = ("JUG98030.FDI", "EQ98030.FDI", "ENT98030.FDI", "MINIFOTO.PKF")
FILENAME = "altrincham-macc-joint-source-exchange-v1.json"
SOURCE_PLAN_FILENAME = "altrincham-macc-joint-native-plan-v1.json"
_CACHE: dict[str, dict[str, Any]] = {}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    return registry.sha256_file(path)


def _source_bindings(base) -> list[dict[str, str]]:
    data = json.loads(compiler.typed.DATA_INPUT.read_text())
    bindings: dict[str, str] = {}
    def add(path: str, digest: str) -> None:
        if path in bindings and bindings[path] != digest:
            raise ValueError(f"conflicting source digests for {path}")
        bindings[path] = digest
    add(registry.relative_workspace_path(compiler.typed.DATA_INPUT), compiler.typed.DATA_INPUT_SHA256)
    add(registry.relative_workspace_path(compiler.typed.NATIONALITY_INPUT), compiler.typed.NATIONALITY_INPUT_SHA256)
    add(compiler.typed.NATIONALITY_RECEIPT, compiler.typed.NATIONALITY_RECEIPT_SHA256)
    add(compiler.typed.FIXTURE_PATH, compiler.typed.FIXTURE_SHA256)
    add(compiler.typed.FIXTURE_PATH + ".source.json",
        "63421a573889329a8a91fad43b5ad6b3d21adf52994fb935c20f51aefc20c910")
    for row in data["source_bindings"].values():
        if not isinstance(row, dict) or "path" not in row or "sha256" not in row:
            continue
        add(row["path"], row["sha256"])
        if row.get("receipt_path"):
            add(row["receipt_path"], row["receipt_sha256"])
    request_path = registry.relative_workspace_path(compiler.BETTNEY_REQUEST)
    add(request_path, compiler.BETTNEY_REQUEST_SHA256)
    add(compiler.BETTNEY_PROFILE_PATH, compiler.BETTNEY_PROFILE_SHA256)
    add(compiler.BETTNEY_PROFILE_PATH + ".source.json", compiler.BETTNEY_RECEIPT_PROFILE_SHA256)
    add(compiler.BETTNEY_MATCH_PATH, compiler.BETTNEY_MATCH_SHA256)
    add(compiler.BETTNEY_MATCH_PATH + ".source.json", compiler.BETTNEY_RECEIPT_MATCH_SHA256)
    return [dict(path=path, sha256=digest) for path, digest in sorted(bindings.items())]


def _implementation_bindings() -> list[dict[str, str]]:
    paths = {
        "adapter": Path(__file__).resolve(),
        "in_memory_compiler": COMPILER_PATH,
        "typed_alty_reader": compiler.PROTOTYPE,
    }
    # Explicit imports keep implementation identity binding clear without any
    # package-global monkeypatch or path rewriting.
    from app import editor_actions, eq_jug_linked, indexed_jug_roles, player_initial_order
    paths.update({"eq_editor_api": Path(editor_actions.__file__),
        "eq_roster_codec": Path(eq_jug_linked.__file__),
        "native_role_writer": Path(indexed_jug_roles.__file__),
        "order_writer": Path(player_initial_order.__file__)})
    return [dict(name=name, path=registry.relative_workspace_path(path), sha256=_file_sha(path))
            for name, path in sorted(paths.items())]


def _parent_bindings(base) -> dict[str, Any]:
    if base.season != SEASON or base.release_id != RELEASE_ID:
        raise ValueError("Alty/Macc exchange requires the exact preferred r210a parent")
    # The pinned r210 package is already canonical on disk (raw SHA equals
    # its canonical SHA). Require those exact bytes without repeated JSON
    # parsing/serialization on every public API verification.
    package_sha = _file_sha(base.package_path)
    files = {name: base.game_path / "DBDAT" / name for name in REQUIRED_NATIVE}
    observed = {name: _file_sha(path) for name, path in files.items()}
    expected = {"JUG98030.FDI":compiler.R210_JUG_SHA256,
        "EQ98030.FDI":compiler.R210_EQ_SHA256,
        "ENT98030.FDI":compiler.R210_ENT_SHA256,
        "MINIFOTO.PKF":compiler.R210_MINIFOTO_SHA256}
    if package_sha != compiler.R210_PACKAGE_SHA256 or observed != expected:
        raise ValueError("r210a package/native parent pins changed")
    return {"season":base.season,"release_id":base.release_id,
        "package_path":registry.relative_workspace_path(base.package_path),
        "package_sha256":package_sha,"native_files":observed}


def _cache_key(parent: dict, sources: list[dict], implementations: list[dict]) -> str:
    document={"schema":SCHEMA,"mode":MODE,"parent":parent,
        "source_bindings":sources,"implementation_bindings":implementations}
    return hashlib.sha256(package_v2.canonical_json_bytes(document)).hexdigest()


def _compile(base, *, expected_plan: dict | None = None) -> dict:
    parent = _parent_bindings(base)
    sources = _source_bindings(base)
    for row in sources:
        path = registry.ROOT / row["path"]
        if _file_sha(path) != row["sha256"]:
            raise ValueError(f"Alty/Macc original source binding changed: {row['path']}")
    implementations = _implementation_bindings()
    key = _cache_key(parent, sources, implementations)
    cached = _CACHE.get(key)
    if cached is None:
        result = compiler._postimages()
        if result["parent_release"].release_id != parent["release_id"]:
            raise ValueError("native compiler returned a different parent release")
        outputs = result["native_files"]
        if set(outputs) != set(REQUIRED_NATIVE):
            raise ValueError("native compiler returned an incomplete four-file postimage")
        inner = result["plan"]
        # The publisher writes a package's external source artifact using one
        # terminal newline. Normalize the compiled descriptor to those exact
        # bytes; the SOURCE helper will later verify this digest after writing.
        source_artifacts = [a for a in result["package"]["artifacts"]
            if a.get("relative_path") == SOURCE_PLAN_FILENAME]
        if len(source_artifacts) != 1:
            raise ValueError("native compiler package lacks its unique source-plan artifact")
        source_artifacts[0]["sha256"] = _sha(package_v2.canonical_json_bytes(inner))
        plan = {"schema":SCHEMA,"mode":MODE,"season":SEASON,
            "parent":parent,"source_bindings":sources,
            "implementation_bindings":implementations,
            "inner_source_plan":inner,
            "inner_source_plan_sha256":_sha(package_v2.canonical_json_bytes(inner)),
            "inner_source_plan_filename":SOURCE_PLAN_FILENAME,
            "package_postimage_sha256":_sha(package_v2.canonical_json_bytes(result["package"])),
            "native_postimages":{name:_sha(payload) for name,payload in outputs.items()},
            "selected_jug_carriers":sorted({a["carrier_id"] for a in result["allocation"]}|{32951}),
            "selected_eq_carriers":[3310],"selected_ent_carriers":[807],
            "selected_photo_carriers":sorted({a["carrier_id"] for a in result["allocation"]}|{32951}),
            "players_written":19,
            "scope":("Atomic club3310 Altrincham identity/label/ground/18-person roster and sourced manager807 correction; "
                "plus identity correction on existing Macc32951 roster slot. Macc Bettney evidence proves opening-roster "
                "membership and a dated used-sub appearance; this transaction preserves the existing Macc roster order "
                "and does not certify or reorder the complete matchday bench. Preserve all other clubs/players, all "
                "Kidderminster374 counterparts, and opaque mode1 tactics. Altrincham 4-3-3 is an editorial role-shape "
                "projection; native mode1 tactics bytes are preserved, not decoded or certified."),
            "replay_policy":"reparse every original source and reproduce all package/native hashes; no cached output survives a changed source/helper hash",
            "publication_approved":False}
        plan["transaction_id"] = _sha(package_v2.canonical_json_bytes(plan))[:24]
        cached={"plan":plan,"result":result,"parent":parent,
                "native_before":{name:(base.game_path/"DBDAT"/name).read_bytes() for name in REQUIRED_NATIVE}}
        _CACHE[key]=cached
    if cached["parent"] != parent:
        raise ValueError("content-keyed cache parent differs")
    if expected_plan is not None and expected_plan != cached["plan"]:
        raise ValueError("source/native prepare plan does not reproduce exactly")
    # Recheck all source and implementation hashes even on a valid content hit.
    for row in cached["plan"]["source_bindings"]:
        if _file_sha(registry.ROOT/row["path"]) != row["sha256"]:
            raise ValueError("cached source changed after prepare")
    for row in cached["plan"]["implementation_bindings"]:
        if _file_sha(registry.ROOT/row["path"]) != row["sha256"]:
            raise ValueError("cached implementation changed after prepare")
    if _parent_bindings(base) != parent:
        raise ValueError("parent changed after typed prepare")
    return cached


def prepare(base) -> dict:
    """Compile and return a uniquely typed plan; writes no game/release file."""
    return copy.deepcopy(_compile(base)["plan"])


def verify(base, plan: dict) -> None:
    if plan.get("schema") != SCHEMA or plan.get("mode") != MODE:
        raise ValueError("Alty/Macc exchange needs its exact unique schema/mode")
    if plan.get("publication_approved") is not False:
        raise ValueError("private Alty/Macc prepare plan cannot self-authorize publication")
    _compile(base, expected_plan=plan)


def bind(package: dict, plan: dict) -> dict:
    """Bind only against the exact baseline recipe or its exact postimage."""
    base=registry.load_registered_release(SEASON, RELEASE_ID)
    verify(base,plan)
    cache=_compile(base,expected_plan=plan)
    before=json.loads(base.package_path.read_text())
    after=cache["result"]["package"]
    if package not in (before,after):
        raise ValueError("bind accepts only the complete exact r210a package preimage/postimage")
    if _sha(package_v2.canonical_json_bytes(after)) != plan["package_postimage_sha256"]:
        raise ValueError("bound package differs from the prepared Alty/Macc postimage")
    return copy.deepcopy(after)


def _apply_one(current: bytes, preimage: bytes, postimage: bytes, label: str) -> bytes:
    if current not in (preimage, postimage):
        raise ValueError(f"{label} apply accepts only the exact full preimage or postimage")
    return postimage


def apply(jug: bytes, eq: bytes, plan: dict) -> tuple[bytes, bytes]:
    """Apply/idempotently read back the complete selected JUG/EQ postimages."""
    base=registry.load_registered_release(SEASON, RELEASE_ID)
    verify(base,plan)
    cache=_compile(base,expected_plan=plan)
    posts=cache["result"]["native_files"]
    before_jug=cache["native_before"]["JUG98030.FDI"]
    before_eq=cache["native_before"]["EQ98030.FDI"]
    if (jug,eq) not in ((before_jug,before_eq),
            (posts["JUG98030.FDI"],posts["EQ98030.FDI"])):
        raise ValueError("JUG/EQ apply accepts only the complete paired preimage or postimage")
    return (posts["JUG98030.FDI"],posts["EQ98030.FDI"])


def apply_ent(ent: bytes, plan: dict) -> bytes:
    """Explicit manager-file API, matching the existing Woking publisher seam."""
    base=registry.load_registered_release(SEASON, RELEASE_ID)
    verify(base,plan)
    cache=_compile(base,expected_plan=plan)
    before=cache["native_before"]["ENT98030.FDI"]
    after=cache["result"]["native_files"]["ENT98030.FDI"]
    if after == before:
        raise ValueError("prepared Alty/Macc transaction must contain the source-backed ENT807 Ward update")
    return _apply_one(ent,before,after,"ENT")


def apply_minifoto(archive: bytes, plan: dict) -> bytes:
    """Return the exact photo archive postimage (often a guarded no-op)."""
    base=registry.load_registered_release(SEASON, RELEASE_ID)
    verify(base,plan)
    cache=_compile(base,expected_plan=plan)
    return _apply_one(archive,cache["native_before"]["MINIFOTO.PKF"],
                      cache["result"]["native_files"]["MINIFOTO.PKF"],"MINIFOTO")


def selected_carriers(plan: dict) -> set[int]:
    if plan.get("schema") != SCHEMA or plan.get("mode") != MODE:
        raise ValueError("Alty/Macc portrait selection needs its exact schema/mode")
    return set(plan["selected_photo_carriers"])


def filename(plan: dict) -> str:
    if plan.get("schema") != SCHEMA or plan.get("mode") != MODE:
        raise ValueError("Alty/Macc filename needs its exact schema/mode")
    return FILENAME


def source_artifact(plan: dict) -> dict[str, Any]:
    """Expose the exact inner proof document referenced by the bound recipe."""
    base = registry.load_registered_release(SEASON, RELEASE_ID)
    verify(base, plan)
    document = copy.deepcopy(plan["inner_source_plan"])
    digest = _sha(package_v2.canonical_json_bytes(document))
    if digest != plan.get("inner_source_plan_sha256"):
        raise ValueError("Alty/Macc inner source plan changed after prepare")
    if plan.get("inner_source_plan_filename") != SOURCE_PLAN_FILENAME:
        raise ValueError("Alty/Macc source artifact filename differs")
    return {"filename": SOURCE_PLAN_FILENAME, "document": document, "sha256": digest}


def reject_factory_recipe(package: dict) -> None:
    if any(a.get('relative_path') == SOURCE_PLAN_FILENAME for a in package.get('artifacts', [])):
        raise ValueError('Altrincham/Macc composition requires its source-bound reconstruction')


def reconstruction(previous, release_id):
    from scripts import season_pipeline_v2 as pipeline
    receipt = pipeline.read_json_file(previous.compiler_receipt_path)
    if receipt.get('compilation_mode') != MODE:
        return None
    relative = previous.locator.get('sourced_profile_assignment_plan_path')
    if not relative:
        raise ValueError('Altrincham SOURCE lacks its typed assignment plan')
    path = (registry.ROOT / relative).resolve()
    plan = pipeline.read_json_file(path)
    base = registry.load_registered_release(SEASON, RELEASE_ID)
    verify(base, plan)
    if (path != (previous.package_path.parent / filename(plan)).resolve()
            or _file_sha(path) != receipt.get('original_profile_assignment_plan_sha256')):
        raise ValueError('Altrincham SOURCE assignment path/hash differs')
    inner = source_artifact(plan)
    if _file_sha(previous.package_path.parent / inner['filename']) != inner['sha256']:
        raise ValueError('Altrincham retained inner source artifact differs')
    expected_package = bind(pipeline.read_json_file(base.package_path), plan)
    if pipeline.read_json_file(previous.package_path) != expected_package:
        raise ValueError('Altrincham SOURCE recipe differs from its source-bound postimage')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    expected_descriptor = dict(season=SEASON, release_id=RELEASE_ID,
        package_sha256=plan['parent']['package_sha256'],
        jug_sha256=plan['parent']['native_files']['JUG98030.FDI'], updates=[], unresolved=[])
    if pipeline.read_json_file(descriptor) != expected_descriptor:
        raise ValueError('Altrincham SOURCE role descriptor is not the exact inert input')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(SEASON, descriptor, release_id=release_id,
        source_release_id=RELEASE_ID, profile_assignment_plan_path=path)
    rebuilt = registry.load_registered_release(SEASON, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,
        pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != expected_package:
        raise ValueError('Altrincham whole SOURCE recipe replay differs')
    return dict(season=SEASON, release_id=release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True,
        compilation_mode=MODE)
