#!/usr/bin/env python3
"""Build small, source-bound portrait corrections without rebuilding databases.

Plan reuses the existing roster audit. Materialise stores an archive delta and
only corrected loose bitmaps. Apply creates ONE independent game copy with a
1 GiB free-space reserve and proves that every unrelated file is unchanged.
The old registered release is never modified, nor is successful face detection
misrepresented as human identity certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_portrait_pipeline_v1 as portraits
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.materialise_native_no_photo_v2 import _active_offsets_for_players
from app.minifoto_bitmap_archive import iter_minifoto_records_from_bytes, validate_minifoto_bitmap

SCHEMA = "pm99-season-visual-patch-v1"
DEFAULT_OUTPUT = ROOT / ".local/season-visual-patches-v2"
DEFAULT_AUDITS = ROOT / ".local/visual-qa-20261003"
PATCH_FILE = re.compile(r"^DBDAT/(?:(?:MINIFOTO|MINIESC|NANOESC|RIDIESC)\.PKF|MINIFOTO/J96\d{5}\.BMP)$")


def sha(path):
    return registry.sha256_file(path)


def save(path, value):
    pipeline.write_canonical_json(path, value)


def build_plan(season, audit_root=DEFAULT_AUDITS):
    release = registry.load_preferred_release(season)
    audit_path = audit_root / season / "player-photo-audit.json"
    audit = json.loads(audit_path.read_text())
    if audit["season"] != season or audit["minifoto_sha256"] != sha(release.game_path / "DBDAT/MINIFOTO.PKF"):
        raise ValueError("roster audit is stale or belongs to another season")
    if audit["package_sha256"] != sha(release.package_path):
        raise ValueError("roster audit targets another recipe")
    override_path = ROOT / "data/season-portrait-overrides-v1" / (season + ".json")
    overrides = json.loads(override_path.read_text())["players"] if override_path.exists() else []
    package = json.loads(release.package_path.read_text())
    players = {int(p["carrier_id"]): p for p in package["players"]}
    seen = set()
    replacements = []
    for row in overrides:
        carrier = int(row["carrier_id"])
        if carrier in seen:
            raise ValueError("duplicate reviewed portrait carrier")
        seen.add(carrier)
        player = players.get(carrier)
        if not player or player["name"] != row["name"] or player.get("facts", {}).get("birth_date") != row["birth_date"]:
            raise ValueError("reviewed identity no longer matches recipe")
        replacements.append({**row, "player_id": player["id"], "status": "era-source-candidate",
            "source_image_url": f"https://cdn.sofifa.net/players/{row['sofifa_id'] // 1000}/{row['sofifa_id'] % 1000:03d}/{row['edition']}_120.png",
            "era_grade": "exact-target-edition", "identity_match": "reviewed-official-season-source"})
    # 2015 has a separate legacy materialisation: its package declarations are
    # intentionally unresolved even where identity-bound portraits are present.
    # Do not blanket-remove that working release on the basis of those stubs.
    no_photo = [] if season == "2015-16" else [
        {"carrier_id": row["carrier_id"], "name": row["name"],
         "bitmap_sha256_before": row["bitmap_sha256"],
         "reason": "inherited-stock-face-on-unresolved-or-no-photo-recipe"}
        for row in audit["players"] if row["physical_status"] == "stock-carrier-photo"
        and row["recipe_declaration"] in {"unresolved", "native-no-photo"}
    ]
    review_binding = None
    if season == "2015-16":
        source_path = audit_root / "foreign-source-verification/report.json"
        resolution_path = audit_root / "foreign-biography-review/report.json"
        review = json.loads(source_path.read_text())
        resolution = json.loads(resolution_path.read_text())
        if resolution["input_report_sha256"] != sha(source_path) or resolution["package_sha256"] != sha(release.package_path):
            raise ValueError("portrait source resolutions are stale")
        unresolved = {int(row["carrier_id"]): row for row in resolution["players"] if row["remaining_issues"]}
        no_photo = [{"carrier_id": row["carrier_id"], "name": row["name"],
                     "bitmap_sha256_before": row["installed_bitmap_sha256"],
                     "reason": "unresolved-source-identity-quarantined-not-editorially-fixed",
                     "remaining_issues": unresolved[int(row["carrier_id"])]["remaining_issues"]}
                    for row in review["players"] if int(row["carrier_id"]) in unresolved
                    and int(row["carrier_id"]) not in seen]
        review_binding = {"source_report_sha256": sha(source_path), "resolutions_sha256": sha(resolution_path)}
    return {"schema_version": SCHEMA, "season": season,
        "inputs": {"release_id": release.release_id, "game": str(release.game_path),
                   "package_sha256": sha(release.package_path), "audit_sha256": sha(audit_path),
                   "minifoto_sha256": audit["minifoto_sha256"],
                   "overrides_sha256": sha(override_path) if override_path.exists() else None,
                   "review_binding": review_binding},
        "no_photo": no_photo, "replacements": replacements}


def patched_archive(original, no_photo):
    archive = bytearray(original)
    offsets = _active_offsets_for_players(archive, no_photo)
    for carrier, places in offsets.items():
        if not places:
            raise ValueError(f"expected inherited photo is no longer active: {carrier}")
        for offset in places:
            archive[offset] = 0
    records = {r.player_record_id: r for r in iter_minifoto_records_from_bytes("MINIFOTO.PKF", bytes(archive))}
    if set(no_photo) & records.keys():
        raise ValueError("no-photo entries remain active")
    return bytes(archive), offsets


def build_english_review_plan(report_path, resolutions_path):
    """Quarantine unresolved legacy English portraits, never foreign carriers."""
    release = registry.load_preferred_release('2015-16')
    report = json.loads(report_path.read_text())
    resolutions = json.loads(resolutions_path.read_text())
    if report.get('schema_version') != 'pm99-english-portrait-source-review-v1' or resolutions.get(
            'schema_version') != 'pm99-english-portrait-biography-review-v1':
        raise ValueError('unsupported English source review')
    if resolutions['input_report_sha256'] != sha(report_path):
        raise ValueError('English identity resolutions do not bind the source review')
    for doc in (report, resolutions):
        if (doc['release_id'] != release.release_id or doc['package_sha256'] != sha(release.package_path)
                or doc['minifoto_sha256'] != sha(release.game_path / 'DBDAT/MINIFOTO.PKF')):
            raise ValueError('English portrait review is stale')
    from scripts import audit_registered_visual_assets_v1 as audit
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    entries = {int(e.record_id): e for e in audit.IndexedFDIFile.from_bytes(jug).entries}
    owners, _, modes = audit._source_roster_owners((release.game_path / 'DBDAT/EQ98030.FDI').read_bytes())
    rows = []
    seen = set()
    originals = {int(r['carrier_id']): r for r in report['players']}
    for row in resolutions['players']:
        carrier = int(row['carrier_id'])
        if carrier in seen or carrier not in originals:
            raise ValueError('duplicate or unbound English review row')
        seen.add(carrier)
        original = originals[carrier]
        if row['name'] != original['name'] or row['issues'] != original['issues']:
            raise ValueError('English resolution changed the original audited identity')
        if not row['remaining_issues'] or original['physical_status'] != 'photo':
            continue
        if not any(modes.get(c) == 0 for c in owners.get(carrier, [])):
            raise ValueError('English review carrier no longer belongs to English roster')
        name = audit._player_name(entries[carrier].decode_payload(jug), record_id=carrier)
        if name != row['name']:
            raise ValueError('English review carrier identity changed')
        rows.append({'carrier_id': carrier, 'name': name,
                     'bitmap_sha256_before': original['installed_bitmap_sha256'],
                     'reason': 'unresolved-english-source-identity-or-era-quarantined',
                     'remaining_issues': row['remaining_issues']})
    if seen != originals.keys():
        raise ValueError('English resolutions omit audited players')
    return {'schema_version': SCHEMA, 'season': '2015-16',
            'inputs': {'release_id': release.release_id, 'package_sha256': sha(release.package_path),
                       'minifoto_sha256': report['minifoto_sha256'], 'english_review_sha256': sha(report_path),
                       'english_resolutions_sha256': sha(resolutions_path),
                       'compiled_player_sha256': sha(release.game_path / 'DBDAT/JUG98030.FDI'),
                       'compiled_roster_sha256': sha(release.game_path / 'DBDAT/EQ98030.FDI')},
            'no_photo': rows, 'replacements': []}


def materialise(plan_path, output, *, source_release=None):
    plan = json.loads(plan_path.read_text())
    if plan.get("schema_version") != SCHEMA:
        raise ValueError("unsupported visual patch plan")
    release = source_release if source_release is not None else registry.load_preferred_release(plan["season"])
    if source_release is not None and release.season != plan['season']:
        raise ValueError('visual patch source belongs to another season')
    if release.release_id != plan["inputs"]["release_id"] or sha(release.package_path) != plan["inputs"]["package_sha256"]:
        raise ValueError("visual patch plan is stale")
    archive_path = release.game_path / "DBDAT/MINIFOTO.PKF"
    if sha(archive_path) != plan["inputs"]["minifoto_sha256"]:
        raise ValueError("portrait archive changed since planning")
    if output.exists():
        receipt = json.loads((output / "receipt.json").read_text())
        if receipt["plan_sha256"] != sha(plan_path):
            raise ValueError("output exists for another plan")
        for name, digest in receipt["outputs"].items():
            if sha(output / name) != digest:
                raise ValueError("retained visual patch has changed")
        return receipt
    output.mkdir(parents=True)
    ids = [int(p["carrier_id"]) for p in plan["no_photo"]]
    original = archive_path.read_bytes()
    original_records = {r.player_record_id: r for r in iter_minifoto_records_from_bytes("MINIFOTO.PKF", original)}
    for row in plan["no_photo"]:
        carrier = int(row["carrier_id"])
        loose = release.game_path / "DBDAT/MINIFOTO" / f"J96{carrier:05d}.BMP"
        actual = sha(loose) if loose.is_file() else hashlib.sha256(original_records[carrier].raw_bitmap).hexdigest()
        if actual != row["bitmap_sha256_before"]:
            raise ValueError("audited inherited bitmap no longer matches")
    # Loose-only portraits have no active archive directory entry to disable.
    patched, offsets = patched_archive(original, [carrier for carrier in ids if carrier in original_records])
    dbdat = output / "DBDAT"
    dbdat.mkdir()
    (dbdat / "MINIFOTO.PKF").write_bytes(patched)
    replacements = []
    if plan["replacements"]:
        fifa_plan = {"schema_version": portraits.PLAN_SCHEMA, "season": plan["season"],
                     "inputs": {"package_canonical_sha256": registry.canonical_document_sha256(release.package_path)},
                     "policy": {"identity": "reviewed-official-season-source"}, "players": plan["replacements"]}
        fifa_plan_path = output / "replacement-plan.json"
        save(fifa_plan_path, fifa_plan)
        converted = portraits.materialise(plan_path=fifa_plan_path, minifoto_path=archive_path,
                    cache_root=portraits.DEFAULT_CACHE, output_root=output / "replacements",
                    workers=1, timeout=30, write_previews=True, max_local_bytes=512 * 1024 ** 2)
        save(output / "replacement-materialisation.json", converted)
        for row in converted["players"]:
            carrier = int(row["carrier_id"])
            if row["status"] != "applied":
                raise ValueError(f"replacement could not be materialised: {row['name']}")
            payload = Path(row["converted_path"]).read_bytes()
            validate_minifoto_bitmap(payload)
            loose = dbdat / "MINIFOTO" / f"J96{carrier:05d}.BMP"
            loose.parent.mkdir(exist_ok=True)
            loose.write_bytes(payload)
            replacements.append(row)
    outputs = {str(p.relative_to(output)): sha(p) for p in sorted(dbdat.rglob("*")) if p.is_file()}
    receipt = {"schema_version": "pm99-season-visual-patch-materialisation-v1", "season": plan["season"],
               "plan_sha256": sha(plan_path), "archive_before_sha256": sha(archive_path),
               "no_photo_count": len(ids), "no_photo_offsets": offsets,
               "replacements": replacements, "outputs": outputs,
               "scope": "Assignment corrections; NOT certification of all photographic identities."}
    save(output / "receipt.json", receipt)
    return receipt


def assert_artwork_only_difference(before, after, allowed):
    diff = pipeline.inventory_difference(before, after)
    names = set(diff["only_left"]) | set(diff["only_right"]) | {r["path"] for r in diff["changed"]}
    if not names <= set(allowed):
        raise ValueError("visual patch changed unrelated files: " + repr(sorted(names - set(allowed))))
    return diff


def source_inventory(release):
    expected = pipeline.read_json_file(release.inventory_path)
    actual = pipeline.build_tree_inventory(release.game_path)
    difference = pipeline.inventory_difference(expected, actual)
    # A game launch may alter this user setting. Preserve it verbatim and
    # record the drift; never silently restore a user's fullscreen preference.
    if difference["only_left"] or difference["only_right"] or any(
        row["path"] != "manager.ini" for row in difference["changed"]
    ):
        raise ValueError("registered patch base has unexpected file changes")
    return actual, difference


def apply(plan_path, materialisation_root, output_game, *, source_release=None):
    plan = json.loads(plan_path.read_text())
    receipt = json.loads((materialisation_root / "receipt.json").read_text())
    if receipt["plan_sha256"] != sha(plan_path):
        raise ValueError("materialisation belongs to another plan")
    release = source_release if source_release is not None else registry.load_preferred_release(plan["season"])
    if release.release_id != plan['inputs']['release_id']:
        raise ValueError('visual patch targets another source release')
    if sha(release.package_path) != plan["inputs"]["package_sha256"] or sha(release.game_path / "DBDAT/MINIFOTO.PKF") != receipt["archive_before_sha256"]:
        raise ValueError("patch base changed")
    # Preflight every replacement before copying or writing any game bytes.
    for name, digest in receipt["outputs"].items():
        if not PATCH_FILE.fullmatch(name) or sha(materialisation_root / name) != digest:
            raise ValueError("invalid or changed materialised patch")
    for name, digest in receipt.get('kit_before_sha256s', {}).items():
        if sha(release.game_path / name) != digest:
            raise ValueError('kit patch base changed')
    before, runtime_config = source_inventory(release)
    copy_proof = portraits.copy_game_with_factory_media_links(release.game_path, output_game)
    for name in receipt["outputs"]:
        (output_game / name).parent.mkdir(parents=True, exist_ok=True)
        (output_game / name).write_bytes((materialisation_root / name).read_bytes())
    removals = []
    for row in plan["no_photo"]:
        loose = output_game / "DBDAT/MINIFOTO" / f"J96{int(row['carrier_id']):05d}.BMP"
        if loose.exists():
            removals.append(str(loose.relative_to(output_game)))
            loose.unlink()
    after = pipeline.build_tree_inventory(output_game)
    diff = assert_artwork_only_difference(before, after, [*receipt["outputs"], *removals])
    pipeline.assert_tree_matches_inventory(release.game_path, before)
    result = {"schema_version": "pm99-season-visual-patch-application-v1", "season": plan["season"],
              "plan_path": str(plan_path.resolve()),
              "materialisation_path": str((materialisation_root / 'receipt.json').resolve()),
              "plan_sha256": sha(plan_path), "materialisation_sha256": sha(materialisation_root / "receipt.json"),
              "base_inventory_fingerprint": before["files_fingerprint"], "output_inventory": after,
              "copy_strategy": "shared-immutable-factory-media-independent-mutable-files-v1",
              "copy_proof": copy_proof,
              "registered_base_inventory_fingerprint": release.locator["game_inventory_fingerprint"],
              "existing_runtime_config_difference": runtime_config,
              "included_visual_patch_plan_sha256s": plan.get('included_visual_patch_plan_sha256s', []),
              "kit_probe_receipt_sha256": plan.get('kit_probe_receipt_sha256'),
              "difference": diff, "game": str(output_game), "unrelated_files_unchanged": True}
    save(output_game.parent / "visual-patch-application.json", result)
    return {k: v for k, v in result.items() if k not in {"output_inventory", "difference"}}


def publish(season, output_game, release_id, register=False, application_path=None, *, source_release=None):
    """Bind the new artwork to the unchanged recipe/compiler, never the base.

    Fresh runner attestation and QA are deliberately not inherited from the old
    game. The old release and its complete byte inventory remain recoverable.
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,127}", release_id):
        raise ValueError("invalid release ID")
    release = source_release if source_release is not None else registry.load_preferred_release(season)
    if source_release is not None and (release.season != season or register):
        raise ValueError('explicit visual replay baseline must match season and cannot promote')
    destination = registry.locator_path(season, release_id).parent
    if destination.exists():
        raise ValueError("release ID already exists")
    application_path = application_path or output_game.parent / "visual-patch-application.json"
    application = json.loads(application_path.read_text())
    registered_base = application.get("registered_base_inventory_fingerprint", application["base_inventory_fingerprint"])
    if application["season"] != season or registered_base != release.locator["game_inventory_fingerprint"]:
        raise ValueError("application is not based on the current release")
    inventory = pipeline.assert_tree_matches_inventory(output_game, application["output_inventory"])
    if application.get('compact_rollback_path'):
        from scripts.season_art_transaction_v1 import verified_base_inventory
        base_inventory = verified_base_inventory(application, output_game)
        runtime_config = application['existing_runtime_config_difference']
    else:
        base_inventory, runtime_config = source_inventory(release)
    if base_inventory["files_fingerprint"] != application["base_inventory_fingerprint"]:
        raise ValueError("base changed since patch application")
    difference = pipeline.inventory_difference(base_inventory, inventory)
    allowed = [r["path"] for r in difference["changed"]] + difference["only_left"] + difference["only_right"]
    if not allowed or any(not PATCH_FILE.fullmatch(name) for name in allowed):
        raise ValueError("published changes must be bounded portrait or compact-kit assets")
    outputs = {row["path"]: row["sha256"] for row in inventory["files"] if row["path"] in allowed}
    if runtime_config["changed"]:
        outputs["manager.ini"] = sha(output_game / "manager.ini")
    chain = pipeline.read_json_file(release.build_chain_path)
    stage_id = "portrait-" + release_id
    chain["stages"].append({"id": stage_id, "receipt_sha256": sha(application_path),
                            "outputs": outputs, "removed": difference["only_left"]})
    destination.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f".{release_id}.partial-", dir=destination.parent))
    chain_path = work / "build-chain.json"
    save(chain_path, chain)
    manifest = pipeline.read_json_file(release.release_manifest_path)
    manifest["output"] = {"file_count": inventory["file_count"], "total_bytes": inventory["total_bytes"],
                          "inventory_fingerprint": inventory["files_fingerprint"]}
    chain_artifact = pipeline.external_artifact_descriptor(artifact_id="build-chain", path=chain_path, role="input")
    patch_artifact = pipeline.external_artifact_descriptor(artifact_id=stage_id, path=application_path, role="input")
    manifest["external_artifacts"] = sorted([a for a in manifest["external_artifacts"] if a["id"] != "build-chain"]
                                              + [chain_artifact, patch_artifact], key=lambda a: a["id"])
    manifest["stages"].append(pipeline.make_stage_record(stage_id=stage_id,
        implementation_path=Path(__file__), input_fingerprints={"previous-release": release.manifest_sha256,
           "patch-plan": application["plan_sha256"]}, parameters={"outputs": outputs,
           "removed": difference["only_left"]}, external_artifacts=[patch_artifact]))
    manifest["stages"] = sorted(manifest["stages"], key=lambda s: s["id"])
    pipeline.validate_release_manifest(manifest)
    metadata = work / "metadata"
    metadata.mkdir()
    manifest_path, inventory_path = metadata / "season-manifest.json", metadata / "output.inventory.json"
    save(manifest_path, manifest)
    save(inventory_path, inventory)
    locator = dict(release.locator)
    for key in ("qa_report_path", "qa_report_sha256"):
        locator.pop(key, None)
    locator.update({"release_id": release_id, "game_path": registry.relative_workspace_path(output_game),
        "inventory_path": registry.relative_workspace_path(destination / "metadata/output.inventory.json"),
        "release_manifest_path": registry.relative_workspace_path(destination / "metadata/season-manifest.json"),
        "build_chain_path": registry.relative_workspace_path(destination / "build-chain.json"),
        "game_inventory_fingerprint": inventory["files_fingerprint"],
        "attestation_path": None, "runtime_evidence_path": None, "technical_status": "playable-unverified",
        "qa_status": "not-recorded", "editorial_warning_count": None,
        "portrait_patch_application_path": registry.relative_workspace_path(application_path)})
    if application.get('plan_path'):
        plan_path = Path(application['plan_path'])
        plan_path.resolve().relative_to(ROOT.resolve())
        if sha(plan_path) != application['plan_sha256']:
            raise ValueError('visual patch plan changed before publication')
        locator['visual_patch_plan_path'] = registry.relative_workspace_path(plan_path)
    locator['required_file_hashes'] = {name: sha(output_game / name) for name in registry.REQUIRED_GAME_FILES}
    if any(name in outputs for name in ('DBDAT/MINIESC.PKF', 'DBDAT/NANOESC.PKF', 'DBDAT/RIDIESC.PKF')):
        locator['kit_patch_application_path'] = registry.relative_workspace_path(application_path)
    locator['required_visual_file_hashes'] = {
        **release.locator.get('required_visual_file_hashes', {}),
        **{name: digest for name, digest in outputs.items() if PATCH_FILE.fullmatch(name)}}
    locator['required_visual_absent_paths'] = sorted(set(
        release.locator.get('required_visual_absent_paths', []) + difference['only_left']) - set(outputs))
    for removed in locator['required_visual_absent_paths']:
        locator['required_visual_file_hashes'].pop(removed, None)
    previous_application = release.locator.get("portrait_patch_application_path")
    if previous_application:
        previous = json.loads((ROOT / previous_application).read_text())
        # Older publishers stored kit applications under the portrait key.
        # Keep that kit proof reachable when a later portrait-only stage is
        # appended; do not let the latest face update hide prior kit evidence.
        if not locator.get('kit_patch_application_path') and any(
                r.get('path') in {'DBDAT/MINIESC.PKF', 'DBDAT/NANOESC.PKF', 'DBDAT/RIDIESC.PKF'}
                for r in previous.get('difference', {}).get('changed', [])):
            locator['kit_patch_application_path'] = previous_application
        locator["superseded_visual_patch_plan_sha256s"] = sorted(set(
            release.locator.get("superseded_visual_patch_plan_sha256s", []) + [previous["plan_sha256"]]))
    locator['superseded_visual_patch_plan_sha256s'] = sorted(set(
        locator.get('superseded_visual_patch_plan_sha256s', []) + application.get('included_visual_patch_plan_sha256s', [])))
    save(work / "locator.json", locator)
    work.rename(destination)
    manifest_path = destination / "metadata/season-manifest.json"
    if register:
        from scripts.attest_registered_season_runtime_v1 import _atomic_replace_json
        catalog = registry.load_catalog()
        catalog[season] = {"season": season, "release_id": release_id,
                           "release_manifest_sha256": sha(manifest_path)}
        _atomic_replace_json(registry.CATALOG_PATH, {"schema_version": registry.CATALOG_SCHEMA,
                                "seasons": [catalog[s] for s in sorted(catalog)]})
    return {"season": season, "release_id": release_id, "registered": register,
            "portrait_only": all('MINIFOTO' in name for name in allowed), "game": str(output_game)}


def extend_kit(season, source_root, probe_root, output_root, *, source_release=None):
    """Combine a retained portrait patch with one actually reviewed kit probe."""
    release = source_release if source_release is not None else registry.load_preferred_release(season)
    if source_release is not None and release.season != season:
        raise ValueError('kit patch source belongs to another season')
    plan_path = source_root / season / 'plan.json'
    patch_root = source_root / season / 'patch'
    plan = json.loads(plan_path.read_text())
    receipt = json.loads((patch_root / 'receipt.json').read_text())
    probe = json.loads((probe_root / 'receipt.json').read_text())
    if plan['season'] != season or probe['season'] != season or receipt['plan_sha256'] != sha(plan_path):
        raise ValueError('kit and portrait patches do not share a season')
    if release.release_id != plan['inputs']['release_id']:
        raise ValueError('combined patch targets another release')
    for name in ('MANAGPRE.EXE', 'DAT.PKF', 'DBDAT/JUG98030.FDI', 'DBDAT/EQ98030.FDI', 'DBDAT/ENT98030.FDI', 'DBDAT/MINIFOTO.PKF'):
        if sha(release.game_path / name) != probe['input_hashes'][name]:
            raise ValueError('kit probe database or palette changed')
    for change in probe['changes']:
        name = 'DBDAT/' + change['archive']
        if change['archive'] not in {'MINIESC.PKF', 'NANOESC.PKF', 'RIDIESC.PKF'}:
            raise ValueError('kit probe changes an unsupported archive')
        if sha(release.game_path / name) != change['archive_before_sha256'] or sha(probe_root / 'game' / name) != change['archive_after_sha256']:
            raise ValueError('kit probe archive hashes changed')
    destination = output_root / season
    if destination.exists():
        raise ValueError('refusing to overwrite combined patch')
    destination.mkdir(parents=True)
    for name, digest in receipt['outputs'].items():
        if sha(patch_root / name) != digest:
            raise ValueError('retained portrait patch changed')
    # The old receipt is immutable evidence for the old plan. Retain it at its
    # original path; the combined patch needs a NEW receipt, not an overwrite.
    shutil.copytree(patch_root, destination / 'patch', ignore=shutil.ignore_patterns('receipt.json'))
    plan['included_visual_patch_plan_sha256s'] = [sha(plan_path)]
    plan['kit_probe_receipt_sha256'] = sha(probe_root / 'receipt.json')
    save(destination / 'plan.json', plan)
    receipt['plan_sha256'] = sha(destination / 'plan.json')
    receipt['kit_before_sha256s'] = {}
    for change in probe['changes']:
        name = 'DBDAT/' + change['archive']
        shutil.copyfile(probe_root / 'game' / name, destination / 'patch' / name)
        receipt['outputs'][name] = change['archive_after_sha256']
        receipt['kit_before_sha256s'][name] = change['archive_before_sha256']
    receipt['kit_probe_receipt_sha256'] = plan['kit_probe_receipt_sha256']
    save(destination / 'patch/receipt.json', receipt)
    return {'season': season, 'club': probe['club'], 'compact_kit_archives': 3}


def ensure_playable_patch(season):
    """Lazily apply retained corrections when playing, not for read-only checks.

    Keeps the 26-season rollout small: no game copy is created until that season
    is actually played. A completed matching application is never repeated.
    """
    root = DEFAULT_OUTPUT / season
    plan_path = root / "plan.json"
    materialisation = root / "patch"
    if not plan_path.is_file() or not (materialisation / "receipt.json").is_file():
        return None
    release = registry.load_preferred_release(season)
    applied_path = release.locator.get("portrait_patch_application_path")
    if applied_path:
        applied = json.loads((ROOT / applied_path).read_text())
        if applied.get("plan_sha256") == sha(plan_path):
            return {"season": season, "status": "already-applied"}
        if sha(plan_path) in release.locator.get("superseded_visual_patch_plan_sha256s", []):
            return {"season": season, "status": "already-applied"}
    plan = json.loads(plan_path.read_text())
    if plan["inputs"]["release_id"] != release.release_id:
        raise ValueError("retained visual patch targets another release; refusing to guess")
    game = root / "playable/game"
    if not game.exists():
        apply(plan_path, materialisation, game)
    return publish(season, game, "visual-reviewed-20261003-r2", register=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "plan-english-review", "materialise", "apply", "publish", "extend-kit"))
    parser.add_argument("season")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--game", type=Path)
    parser.add_argument("--release-id")
    parser.add_argument("--register", action="store_true")
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--kit-probe', type=Path)
    parser.add_argument('--english-report', type=Path)
    parser.add_argument('--resolutions', type=Path)
    args = parser.parse_args()
    if args.command == 'extend-kit':
        if args.season == 'all' or args.source_root is None or args.kit_probe is None:
            parser.error('extend-kit requires one season, --source-root and --kit-probe')
        print(json.dumps(extend_kit(args.season, args.source_root, args.kit_probe, args.output_root)))
        return
    seasons = registry.supported_seasons() if args.season == "all" else [args.season]
    if args.command in {"apply", "publish"} and (args.season == "all" or args.game is None):
        parser.error("apply/publish requires one season and --game; no unattended full-copy batch")
    if args.command == "publish" and not args.release_id:
        parser.error("publish requires --release-id")
    results = []
    for season in seasons:
        root = args.output_root / season
        plan_path = root / "plan.json"
        if args.command == "plan":
            result = build_plan(season)
            root.mkdir(parents=True, exist_ok=True)
            if plan_path.exists() and json.loads(plan_path.read_text()) != result:
                raise ValueError("retained plan changed; use a new output root")
            save(plan_path, result)
            results.append({"season": season, "no_photo": len(result["no_photo"]), "replacements": len(result["replacements"])})
        elif args.command == 'plan-english-review':
            if season != '2015-16' or not args.english_report or not args.resolutions:
                parser.error('English review plan requires 2015-16, --english-report and --resolutions')
            result = build_english_review_plan(args.english_report, args.resolutions)
            root.mkdir(parents=True, exist_ok=True)
            save(plan_path, result)
            results.append({'season': season, 'no_photo': len(result['no_photo']), 'replacements': 0})
        elif args.command == "materialise":
            result = materialise(plan_path, root / "patch")
            results.append({"season": season, "no_photo": result["no_photo_count"], "replacements": len(result["replacements"])})
        elif args.command == "apply":
            results.append(apply(plan_path, root / "patch", args.game))
        else:
            results.append(publish(season, args.game, args.release_id, args.register))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
