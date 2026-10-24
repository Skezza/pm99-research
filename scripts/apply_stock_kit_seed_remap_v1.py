#!/usr/bin/env python3
"""Prepare one season's approved stock-kit seed-carrier remap patch.

The command is dry-run by default. It consumes a bound combined-26 checklist,
copies only the three compact kit archives to a new detached scratch directory,
reuses ``copy_art`` for each explicitly approved row, and hands the resulting
probe to the existing visual-patch materialise/extend APIs. It never edits a
registered game, recipe, database, photo archive, or preferred-release catalog.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records_from_bytes  # noqa: E402
from scripts import patch_carrier_kit_art as carrier_kit  # noqa: E402
from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts import season_release_registry_v1 as registry  # noqa: E402
from scripts import season_visual_patch_v1 as visual_patch  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402


SCHEMA = "combined26-stock-kit-remap-candidate-checklist-v1"
APPROVAL_SCHEMA = "pm99-stock-kit-seed-remap-approval-v1"
PLAN_SCHEMA = "pm99-season-stock-kit-seed-remap-v1"
ARCHIVES = ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
CASE_RE = re.compile(r"^kit-stock-seed-remap-[0-9a-f]{20}$")
BMP_RE = re.compile(r"^EQ96\d{4}\.BMP$")


class StockKitRemapError(ValueError):
    """A bound input or scope guard rejected a remap."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return registry.sha256_file(path)


def _canonical_bytes(value: Any) -> bytes:
    return pipeline.canonical_json_bytes(value)


def case_id_for(row: Mapping[str, Any]) -> str:
    payload = {
        "season": row["season"],
        "club_id": row["club_id"],
        "target_carrier_id": int(row["target_carrier_id"]),
        "source_baseline_carrier_id": int(row["source_baseline_carrier_id"]),
    }
    return "kit-stock-seed-remap-" + sha256_bytes(_canonical_bytes(payload))[:20]


def _archive_hashes(value: Mapping[str, Any], *, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != set(ARCHIVES):
        raise StockKitRemapError(f"{label} must bind exactly the three compact archives")
    result = {name: value[name] for name in ARCHIVES}
    if any(not isinstance(digest, str) or not SHA_RE.fullmatch(digest) for digest in result.values()):
        raise StockKitRemapError(f"{label} contains an invalid SHA-256")
    return result


def _case_evidence(row: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Normalize the two checklist row shapes without deriving any mapping."""
    if "stock_seed_and_pixel_evidence" in row:
        proof = row["stock_seed_and_pixel_evidence"]
        if proof.get("target_current_pixels_equal_own_clean_seed_all_archives") is not True:
            raise StockKitRemapError("candidate target is not proven to retain its own clean seed in every archive")
        if proof.get("source_target_record_shape_compatible_all_archives") is not True:
            raise StockKitRemapError("candidate source/target shapes are not compatible")
        return (
            _archive_hashes(proof.get("source_bitmap_sha256_by_archive"), label="source bitmap hashes"),
            _archive_hashes(proof.get("target_current_bitmap_sha256_by_archive"), label="target preimage bitmap hashes"),
            _archive_hashes(proof.get("target_clean_seed_bitmap_sha256_by_archive"), label="target clean-seed hashes"),
        )
    archives = row.get("archives")
    if not isinstance(archives, Mapping) or set(archives) != set(ARCHIVES):
        raise StockKitRemapError("legacy checklist row must bind all three compact archives")
    source: dict[str, str] = {}
    current: dict[str, str] = {}
    own: dict[str, str] = {}
    for name in ARCHIVES:
        proof = archives[name]
        if proof.get("current_equals_own_clean_seed") is not True or proof.get("source_target_size_compatible") is not True:
            raise StockKitRemapError(f"legacy {name} target preimage/shape check is not passing")
        source[name] = proof["source_clean_seed_bitmap_sha256"]
        current[name] = proof["carrier_current_bitmap_sha256"]
        own[name] = proof["own_clean_seed_bitmap_sha256"]
    return (_archive_hashes(source, label="legacy source bitmap hashes"),
            _archive_hashes(current, label="legacy target preimage hashes"),
            _archive_hashes(own, label="legacy target clean-seed hashes"))


def _case_policy(row: Mapping[str, Any]) -> tuple[str, list[str]]:
    if "current_package_kit_policy" in row:
        policy = row["current_package_kit_policy"]
        artifacts = row.get("current_package_kit_artifact_ids")
    else:
        original = row.get("preserved_original_candidate_row", {})
        policy = original.get("kit_policy")
        artifacts = original.get("kit_artifact_ids")
    if not isinstance(artifacts, list) or any(not isinstance(x, str) for x in artifacts):
        raise StockKitRemapError("candidate kit artifact IDs are malformed")
    return str(policy), artifacts


def validate_checklist_bytes(
    checklist_bytes: bytes,
    *,
    expected_checklist_sha256: str,
    season: str,
    parent_release_id: str,
    parent_manifest_sha256: str,
    source_archive_sha256s: Mapping[str, str],
    case_ids: Sequence[str] = (),
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate checklist, season, parent, and case selection without disk writes."""
    if not SHA_RE.fullmatch(expected_checklist_sha256) or sha256_bytes(checklist_bytes) != expected_checklist_sha256:
        raise StockKitRemapError("combined-26 checklist SHA does not match the explicit binding")
    if not SHA_RE.fullmatch(parent_manifest_sha256):
        raise StockKitRemapError("parent manifest SHA is malformed")
    if not isinstance(parent_release_id, str) or not parent_release_id:
        raise StockKitRemapError("explicit parent release ID is required")
    source_hashes = _archive_hashes(source_archive_sha256s, label="sealed source archive hashes")
    try:
        checklist = json.loads(checklist_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StockKitRemapError("combined-26 checklist is not valid JSON") from exc
    if checklist.get("schema") != SCHEMA:
        raise StockKitRemapError("unsupported combined-26 checklist schema")
    validation = checklist.get("validation", {})
    if validation.get("unique_case_ids") is not True:
        raise StockKitRemapError("checklist does not certify unique case IDs")
    cases = checklist.get("cases", [])
    if not isinstance(cases, list) or validation.get("total_cases") != len(cases):
        raise StockKitRemapError("combined checklist case count differs from its validation summary")
    source_inputs = checklist.get("source_inputs", {})
    expected_source_hashes = _archive_hashes(source_inputs.get("legacy_seed_dbdat_hashes"), label="checklist clean-seed archive hashes")
    if source_hashes != expected_source_hashes:
        raise StockKitRemapError("explicit clean-seed archive hashes differ from the checklist binding")
    rows = [r for r in cases if r.get("season") == season]
    if not rows:
        raise StockKitRemapError(f"checklist has no cases for season {season}")
    known: dict[str, dict[str, Any]] = {}
    for row in rows:
        computed = case_id_for(row)
        if row.get("case_id") != computed or not CASE_RE.fullmatch(computed):
            raise StockKitRemapError("candidate case ID does not match its canonical fields")
        if computed in known:
            raise StockKitRemapError("duplicate candidate case ID")
        known[computed] = row
    requested = list(case_ids)
    if requested and (len(set(requested)) != len(requested) or set(requested) - set(known)):
        raise StockKitRemapError("selected case IDs are duplicate or do not belong to this season")
    requested_set = set(requested)
    selected = [row for row in rows if not requested or row["case_id"] in requested_set]
    normalized: list[dict[str, Any]] = []
    for row in selected:
        if row.get("status") != "candidate-only; no kit change approved":
            raise StockKitRemapError("only unmodified candidate rows from this checklist schema are accepted")
        policy, artifact_ids = _case_policy(row)
        if policy != "preserve-existing-mode1" or artifact_ids:
            raise StockKitRemapError("sourced/protected kit rows cannot be remapped by this command")
        binding = row.get("audit_binding", {})
        bound_release = binding.get("catalog_release_id", binding.get("release_id"))
        bound_manifest = binding.get("catalog_manifest_sha256", binding.get("release_manifest_sha256"))
        bound_package = binding.get("rebound_package_sha256", binding.get("package_sha256"))
        current_archives = binding.get("current_actual_compact_archive_sha256",
            binding.get("current_compact_archive_sha256", binding.get("current_archive_sha256")))
        if (bound_release, bound_manifest) != (parent_release_id, parent_manifest_sha256):
            raise StockKitRemapError("candidate row is bound to another parent release/manifest")
        if not isinstance(bound_package, str) or not SHA_RE.fullmatch(bound_package):
            raise StockKitRemapError("candidate row lacks a bound parent package SHA")
        if _archive_hashes(current_archives, label="candidate current archive hashes") == {}:
            raise StockKitRemapError("candidate lacks exact current archive binding")
        source_hashes_by_archive, current_bitmap, own_bitmap = _case_evidence(row)
        if current_bitmap != own_bitmap:
            raise StockKitRemapError("target current bitmap is not its own clean-seed bitmap")
        source_id = int(row["source_baseline_carrier_id"])
        target_id = int(row["target_carrier_id"])
        if target_id != int(row["current_carrier_id"]):
            raise StockKitRemapError("target carrier differs from the audited current carrier")
        original = row.get("preserved_original_candidate_row")
        if original is not None and sha256_bytes(_canonical_bytes(original)) != row.get("source_candidate_sha256"):
            raise StockKitRemapError("preserved main-audit candidate row hash is invalid")
        if not isinstance(row.get("source_candidate_sha256"), str) or not SHA_RE.fullmatch(row["source_candidate_sha256"]):
            raise StockKitRemapError("source candidate digest is malformed")
        normalized.append({
            "case_id": row["case_id"], "source_candidate_sha256": row["source_candidate_sha256"],
            "season": season, "club_id": str(row["club_id"]),
            "logical_club": row["current_logical_club"],
            "source_carrier_id": source_id, "target_carrier_id": target_id,
            "stock_seed_name": row.get("target_stock_seed_name", row.get("target_stock_seed_club_name")),
            "stock_seed_full_name": row.get("target_stock_seed_full_name"),
            "parent_package_sha256": bound_package,
            "current_archive_sha256s": _archive_hashes(current_archives, label="candidate current archive hashes"),
            "source_bitmap_sha256s": source_hashes_by_archive,
            "target_preimage_bitmap_sha256s": current_bitmap,
            "target_file_by_archive": {name: f"EQ96{target_id:04d}.BMP" for name in ARCHIVES},
            "source_file_by_archive": {name: f"EQ96{source_id:04d}.BMP" for name in ARCHIVES},
            "policy": policy, "artifact_ids": artifact_ids,
        })
    targets = [r["target_carrier_id"] for r in normalized]
    if len(set(targets)) != len(targets):
        raise StockKitRemapError("selected mappings reuse a target carrier")
    return checklist, normalized


def _root_path(value: str | Path, *, label: str, must_exist: bool = True) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = registry.ROOT / path
    path = path.resolve()
    try:
        path.relative_to(registry.ROOT.resolve())
    except ValueError as exc:
        raise StockKitRemapError(f"{label} escapes the workspace") from exc
    if must_exist and not path.exists():
        raise StockKitRemapError(f"{label} does not exist: {path}")
    return path


def _seed_map_for(checklist: Mapping[str, Any], row: Mapping[str, Any]) -> tuple[Path, str]:
    inputs = checklist["source_inputs"]
    legacy_row = "current_package_kit_policy" in row
    key_path = "2015_legacy_stock_map_path" if legacy_row else "legacy_seed_stock_map_path"
    key_sha = "2015_legacy_stock_map_sha256" if legacy_row else "legacy_seed_stock_map_sha256"
    return _root_path(inputs[key_path], label="stock carrier map"), inputs[key_sha]


def _check_stock_map(checklist: Mapping[str, Any], row: Mapping[str, Any], source_id: int) -> None:
    path, expected_sha = _seed_map_for(checklist, row)
    if sha256_file(path) != expected_sha:
        raise StockKitRemapError("fixed stock carrier map no longer matches the checklist hash")
    carriers = json.loads(path.read_text()).get("carriers", [])
    matches = [c for c in carriers if int(c.get("carrier_id", -1)) == source_id]
    if len(matches) != 1:
        raise StockKitRemapError("source carrier does not resolve uniquely in the sealed stock map")
    baseline = matches[0].get("baseline_club", {})
    stock_name = row.get("target_stock_seed_name", row.get("target_stock_seed_club_name"))
    if baseline.get("name") != stock_name or baseline.get("full_name") != row.get("target_stock_seed_full_name"):
        raise StockKitRemapError("stock carrier name/full-name mapping differs from the checklist")


def _verify_original_audit(checklist: Mapping[str, Any], row: Mapping[str, Any]) -> None:
    inputs = checklist["source_inputs"]
    legacy_row = "current_package_kit_policy" in row
    key_path = "legacy_2015_audit_path" if legacy_row else "main_audit_path"
    key_sha = "legacy_2015_audit_sha256" if legacy_row else "main_audit_sha256"
    path = _root_path(inputs[key_path], label="original candidate audit")
    if sha256_file(path) != inputs[key_sha]:
        raise StockKitRemapError("original candidate audit changed since combined checklist review")
    original_doc = json.loads(path.read_text())
    if legacy_row:
        matches = [r for r in original_doc.get("candidates", [])
                   if int(r.get("current_carrier_id", -1)) == int(row["current_carrier_id"])
                   and int(r.get("stock_seed_carrier_id", -1)) == int(row["source_baseline_carrier_id"])]
        if len(matches) != 1:
            raise StockKitRemapError("legacy checklist mapping does not resolve uniquely in its original audit")
        original = matches[0]
        if (original.get("current_logical_club"), original.get("stock_seed_club_name"),
            original.get("stock_seed_full_name")) != (
            row.get("current_logical_club"), row.get("target_stock_seed_club_name"),
            row.get("target_stock_seed_full_name")):
            raise StockKitRemapError("legacy candidate identity/name evidence differs from original audit")
        checks = original.get("archive_checks", {})
        for archive in ARCHIVES:
            proof = row.get("archives", {}).get(archive, {})
            old = checks.get(archive, {})
            if (proof.get("source_clean_seed_bitmap_sha256"), proof.get("carrier_current_bitmap_sha256"),
                proof.get("own_clean_seed_bitmap_sha256")) != (
                old.get("source_clean_seed_bitmap_sha256"), old.get("carrier_current_bitmap_sha256"),
                old.get("own_clean_seed_bitmap_sha256")):
                raise StockKitRemapError("legacy candidate pixel proof differs from its original audit")
    else:
        original = row.get("preserved_original_candidate_row")
        if not isinstance(original, dict):
            raise StockKitRemapError("main candidate lacks its preserved original audit row")
        matches = [r for r in original_doc.get("candidate_rows", []) if r == original]
        if len(matches) != 1:
            raise StockKitRemapError("preserved candidate row is absent or ambiguous in the pinned main audit")


def _protected_legacy_carriers(checklist: Mapping[str, Any]) -> set[int]:
    protected = checklist.get("protected_source_exclusions", {}).get("legacy_2015", {})
    result = set(map(int, protected.get("current_main_package_source_kit_carriers", [])))
    for key, fields in (("foreign_source_receipt_path", "foreign_events"),
                        ("english_layer_receipt_path", "patched")):
        receipt_path = _root_path(protected[key], label="legacy protected-kit receipt")
        expected = protected.get(key.replace("_path", "_sha256"))
        if not isinstance(expected, str) or sha256_file(receipt_path) != expected:
            raise StockKitRemapError("protected legacy kit receipt changed")
        document = json.loads(receipt_path.read_text())
        for row in document.get(fields, []):
            carrier = row.get("carrier_id", row.get("team_id"))
            if carrier is not None:
                result.add(int(carrier))
    return result


def _normalize_row_records(release, source_dir: Path, rows: Sequence[Mapping[str, Any]],
                           expected_source_hashes: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    """Validate all selected bitmaps from one parse of each archive."""
    result: dict[str, dict[str, Any]] = {}
    for archive in ARCHIVES:
        source_bytes = (source_dir / archive).read_bytes()
        parent_bytes = (release.game_path / "DBDAT" / archive).read_bytes()
        if sha256_bytes(source_bytes) != expected_source_hashes[archive]:
            raise StockKitRemapError(f"sealed source archive changed: {archive}")
        expected_current = rows[0]["current_archive_sha256s"][archive]
        if any(r["current_archive_sha256s"][archive] != expected_current for r in rows):
            raise StockKitRemapError(f"selected rows do not share one parent archive preimage: {archive}")
        if sha256_bytes(parent_bytes) != expected_current:
            raise StockKitRemapError(f"parent compact archive changed since candidate checklist: {archive}")
        source_records = {r.file_name: r for r in iter_obfuscated_bmp_records_from_bytes(
            archive, source_bytes, file_name_pattern=BMP_RE)}
        current_records = {r.file_name: r for r in iter_obfuscated_bmp_records_from_bytes(
            archive, parent_bytes, file_name_pattern=BMP_RE)}
        events = []
        for row in rows:
            source_name = row["source_file_by_archive"][archive]
            target_name = row["target_file_by_archive"][archive]
            source_record, target_record = source_records.get(source_name), current_records.get(target_name)
            if source_record is None or target_record is None:
                raise StockKitRemapError(f"{archive} is missing a candidate source/target record")
            if sha256_bytes(source_record.raw_bitmap) != row["source_bitmap_sha256s"][archive]:
                raise StockKitRemapError(f"{archive} source bitmap changed for {row['case_id']}")
            if sha256_bytes(target_record.raw_bitmap) != row["target_preimage_bitmap_sha256s"][archive]:
                raise StockKitRemapError(f"{archive} target preimage changed for {row['case_id']}")
            if (source_record.width, source_record.height, source_record.bits_per_pixel,
                source_record.bitmap_length) != (
                target_record.width, target_record.height, target_record.bits_per_pixel,
                target_record.bitmap_length):
                raise StockKitRemapError(f"{archive} source/target shapes differ for {row['case_id']}")
            events.append({"case_id": row["case_id"], "source_id": row["source_carrier_id"],
                "target_id": row["target_carrier_id"], "source_name": source_name,
                "target_name": target_name, "source_bitmap_sha256": sha256_bytes(source_record.raw_bitmap),
                "target_preimage_sha256": sha256_bytes(target_record.raw_bitmap),
                "target_range": [target_record.bitmap_offset, target_record.bitmap_offset + target_record.bitmap_length]})
        result[archive] = {"source_bytes_sha256": sha256_bytes(source_bytes),
            "parent_bytes_sha256": sha256_bytes(parent_bytes), "source_records": source_records,
            "parent_records": current_records, "events": events}
    return result


def _validate_live_binding(checklist: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], release,
                           source_dir: Path, source_hashes: Mapping[str, str]) -> dict[str, Any]:
    if release.season != rows[0]["season"]:
        raise StockKitRemapError("explicit parent release belongs to another season")
    package_sha = sha256_file(release.package_path)
    for row in rows:
        if row["parent_package_sha256"] != package_sha:
            raise StockKitRemapError("candidate row package preimage differs from the explicit parent")
    source_cases = {str(c["case_id"]): c for c in checklist.get("cases", [])}
    package = json.loads(release.package_path.read_text())
    clubs = {str(c["id"]): c for c in package.get("clubs", [])}
    clubs_by_carrier = {int(c["carrier_id"]): c for c in package.get("clubs", [])}
    kits = {str(k["club_id"]): k for k in package.get("assets", {}).get("kits", [])}
    for row in rows:
        if "current_package_kit_policy" in source_cases.get(row["case_id"], {}):
            club = clubs_by_carrier.get(row["target_carrier_id"])
            kit = kits.get(str(club.get("id"))) if club else None
        else:
            club, kit = clubs.get(row["club_id"]), kits.get(row["club_id"])
        if club is None or kit is None:
            raise StockKitRemapError("candidate club or kit row is absent from the explicit parent package")
        if (club.get("name"), int(club.get("carrier_id", -1))) != (
            row["logical_club"], row["target_carrier_id"]):
            raise StockKitRemapError("candidate club label/carrier differs from the explicit parent package")
        if kit.get("policy") != "preserve-existing-mode1" or kit.get("artifact_ids") != []:
            raise StockKitRemapError("parent package shows a sourced/protected kit row")
    for row in rows:
        original_case = source_cases.get(row["case_id"])
        if original_case is None:
            raise StockKitRemapError("selected case is absent from the bound checklist")
        _verify_original_audit(checklist, original_case)
        _check_stock_map(checklist, original_case, row["source_carrier_id"])
    if "current_package_kit_policy" in source_cases[rows[0]["case_id"]]:
        protected = _protected_legacy_carriers(checklist)
        if any(row["target_carrier_id"] in protected for row in rows):
            raise StockKitRemapError("legacy candidate intersects a protected sourced-kit carrier")
    source_palette, source_palette_info = runtime_kit_palette(source_dir)
    target_palette, target_palette_info = runtime_kit_palette(release.game_path / "DBDAT")
    source_rgb_sha = sha256_bytes(bytes(channel for color in source_palette for channel in color))
    target_rgb_sha = sha256_bytes(bytes(channel for color in target_palette for channel in color))
    if source_palette != target_palette or source_rgb_sha != target_rgb_sha:
        raise StockKitRemapError("clean source and parent use different runtime kit palettes")
    if "current_package_kit_policy" in source_cases[rows[0]["case_id"]]:
        if any(source_cases[r["case_id"]].get("palette_equal") is not True
               or source_cases[r["case_id"]].get("palette_rgb_sha256") != source_rgb_sha for r in rows):
            raise StockKitRemapError("legacy palette binding differs from source and parent runtime palettes")
    else:
        audit_path = _root_path(checklist["source_inputs"]["main_audit_path"], label="main stock-kit audit")
        audit = json.loads(audit_path.read_text())
        binding = audit.get("palette_binding", {})
        season_rows = [r for r in binding.get("seasons", []) if r.get("season") == release.season]
        if binding.get("all_25_current_preferred_DAT_palettes_match_the_sealed_clean_render_source") is not True or len(season_rows) != 1:
            raise StockKitRemapError("main audit lacks one sealed palette binding for this season")
        palette_row = season_rows[0]
        source_dat_path = Path(palette_row["source_palette_path"]).resolve()
        if source_dat_path != Path(source_palette_info["path"]).resolve():
            raise StockKitRemapError("palette audit source path differs from explicit clean source DBDAT")
        if (sha256_file(source_dat_path), sha256_file(release.game_path / "DAT.PKF"),
            palette_row["source_palette_sha256"], palette_row["preferred_palette_sha256"]) != (
            palette_row["source_palette_sha256"], palette_row["preferred_palette_sha256"],
            palette_row["source_palette_sha256"], palette_row["preferred_palette_sha256"]):
            raise StockKitRemapError("parent or clean-source DAT.PKF differs from its sealed palette audit")
    expected_hashes = _archive_hashes(source_hashes, label="sealed source archive hashes")
    for name in ARCHIVES:
        if sha256_file(source_dir / name) != expected_hashes[name]:
            raise StockKitRemapError(f"sealed clean source archive changed: {name}")
    return {"package_sha256": package_sha,
        "parent_manifest_sha256": release.manifest_sha256,
        "parent_archive_sha256s": {name: sha256_file(release.game_path / "DBDAT" / name) for name in ARCHIVES},
        "source_archive_sha256s": expected_hashes,
        "palette_sha256": sha256_file(release.game_path / "DAT.PKF"),
        "runtime_kit_palette_rgb_sha256": target_rgb_sha,
        "source_runtime_kit_palette_rgb_sha256": source_rgb_sha,
        "source_runtime_palette_path": source_palette_info["path"],
        "parent_runtime_palette_path": target_palette_info["path"],
        "checklist_sha256": sha256_file(_root_path(checklist["_path"], label="checklist"))}


def _approved_case_ids(path: Path, *, checklist_sha: str, season: str, parent_release_id: str,
                       parent_manifest_sha: str, source_hashes: Mapping[str, str]) -> set[str]:
    document = json.loads(path.read_text())
    if document.get("schema") != APPROVAL_SCHEMA:
        raise StockKitRemapError("materialisation requires an explicit stock-kit remap approval receipt")
    if (document.get("checklist_sha256"), document.get("season"), document.get("parent_release_id"),
        document.get("parent_manifest_sha256"), document.get("source_archive_sha256s")) != (
        checklist_sha, season, parent_release_id, parent_manifest_sha, dict(source_hashes)):
        raise StockKitRemapError("approval receipt does not bind exact checklist, season, parent, and source")
    ids = document.get("approved_case_ids")
    if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)) or any(not CASE_RE.fullmatch(x) for x in ids):
        raise StockKitRemapError("approval receipt has no valid unique case selection")
    if document.get("scope") != "stock-seed-carrier-remap-only; historical kit design not certified":
        raise StockKitRemapError("approval scope must explicitly avoid historical authenticity claims")
    return set(ids)


def prepare(
    *, checklist_path: Path, checklist_sha256: str, season: str,
    parent_release_id: str, parent_manifest_sha256: str,
    source_dbdat: Path, source_archive_sha256s: Mapping[str, str],
    case_ids: Sequence[str] = (),
) -> dict[str, Any]:
    checklist_path = _root_path(checklist_path, label="combined-26 checklist")
    checklist_bytes = checklist_path.read_bytes()
    checklist, rows = validate_checklist_bytes(checklist_bytes,
        expected_checklist_sha256=checklist_sha256, season=season,
        parent_release_id=parent_release_id, parent_manifest_sha256=parent_manifest_sha256,
        source_archive_sha256s=source_archive_sha256s, case_ids=case_ids)
    checklist["_path"] = str(checklist_path)
    release = registry.load_registered_release(season, parent_release_id)
    if release.manifest_sha256 != parent_manifest_sha256:
        raise StockKitRemapError("registered parent manifest differs from explicit parent binding")
    source_dbdat = _root_path(source_dbdat, label="sealed source DBDAT")
    expected_source = _root_path(checklist["source_inputs"]["legacy_seed_dbdat_path"], label="checklist source DBDAT")
    if source_dbdat != expected_source:
        raise StockKitRemapError("explicit source DBDAT path differs from the checklist binding")
    live = _validate_live_binding(checklist, rows, release, source_dbdat, source_archive_sha256s)
    if live["checklist_sha256"] != checklist_sha256:
        raise StockKitRemapError("combined checklist changed after initial read")
    record_proofs = _normalize_row_records(release, source_dbdat, rows, source_archive_sha256s)
    return {"schema": PLAN_SCHEMA, "status": "dry-run-candidate-only",
        "season": season, "parent_release_id": parent_release_id,
        "parent_manifest_sha256": parent_manifest_sha256,
        "parent_package_sha256": live["package_sha256"],
        "checklist_path": str(checklist_path), "checklist_sha256": checklist_sha256,
        "source_dbdat": str(source_dbdat), "source_archive_sha256s": dict(source_archive_sha256s),
        "source_stock_map_sha256": registry.sha256_file(_seed_map_for(checklist, rows[0])[0]),
        "palette_binding": {"runtime_palette_rgb_sha256": live["runtime_kit_palette_rgb_sha256"],
            "source_dat_path": live["source_runtime_palette_path"],
            "source_dat_sha256": sha256_file(Path(live["source_runtime_palette_path"])),
            "parent_dat_sha256": live["palette_sha256"]},
        "selected_cases": rows, "record_preflight": {name: {"parent_archive_sha256": record_proofs[name]["parent_bytes_sha256"],
            "source_archive_sha256": record_proofs[name]["source_bytes_sha256"], "records": record_proofs[name]["events"]}
            for name in ARCHIVES},
        "policy": {"approved_by_this_command": False, "artifact_ids_empty_required": True,
            "historical_kit_authenticity": "not assessed", "write_scope": list(ARCHIVES),
            "native_recipe_photos_unchanged": True, "source_seed_not_current_donor": True}}


def materialise(*, plan: Mapping[str, Any], approval_path: Path, output_root: Path) -> dict[str, Any]:
    """Create only a detached kit probe and combined visual patch artifacts."""
    if plan.get("status") != "dry-run-candidate-only":
        raise StockKitRemapError("materialisation requires a freshly prepared plan")
    if not plan.get("selected_cases"):
        raise StockKitRemapError("no candidate mappings selected")
    approval_path = _root_path(approval_path, label="approval receipt")
    output_root = _root_path(output_root, label="output root", must_exist=False)
    local_root = (registry.ROOT / ".local/season-stock-kit-seed-remaps-v1").resolve()
    try:
        output_root.relative_to(local_root)
    except ValueError as exc:
        raise StockKitRemapError("materialisation output must be a new directory under the local kit-remap root") from exc
    if output_root.exists():
        raise StockKitRemapError("refusing to overwrite an existing output root")
    source_hashes = _archive_hashes(plan["source_archive_sha256s"], label="plan source archives")
    approved = _approved_case_ids(approval_path, checklist_sha=plan["checklist_sha256"],
        season=plan["season"], parent_release_id=plan["parent_release_id"],
        parent_manifest_sha=plan["parent_manifest_sha256"], source_hashes=source_hashes)
    selected = {row["case_id"] for row in plan["selected_cases"]}
    if approved != selected:
        raise StockKitRemapError("approval cases must exactly equal the selected dry-run cases")
    release = registry.load_registered_release(plan["season"], plan["parent_release_id"])
    preferred = registry.load_preferred_release(plan["season"])
    if preferred.release_id != release.release_id or preferred.manifest_sha256 != release.manifest_sha256:
        raise StockKitRemapError("visual-patch materialisation requires this exact parent to be preferred")
    source_dbdat = _root_path(plan["source_dbdat"], label="sealed source DBDAT")
    # Re-run the full parent/checklist/source preflight immediately before writes.
    fresh = prepare(checklist_path=Path(plan["checklist_path"]), checklist_sha256=plan["checklist_sha256"],
        season=plan["season"], parent_release_id=plan["parent_release_id"],
        parent_manifest_sha256=plan["parent_manifest_sha256"], source_dbdat=source_dbdat,
        source_archive_sha256s=source_hashes, case_ids=sorted(selected))
    if _canonical_bytes(fresh) != _canonical_bytes(plan):
        raise StockKitRemapError("freshly prepared plan differs from the submitted plan")

    output_root.mkdir(parents=True)
    plan_path = output_root / "plan.json"
    plan_file_sha256 = pipeline.write_canonical_json(plan_path, dict(fresh))
    shutil.copyfile(approval_path, output_root / "approval.json")
    probe_root = output_root / "kit-probe"
    scratch = probe_root / "game" / "DBDAT"
    scratch.mkdir(parents=True)
    parent_archive_bytes: dict[str, bytes] = {}
    for name in ARCHIVES:
        source_path = release.game_path / "DBDAT" / name
        dest_path = scratch / name
        shutil.copyfile(source_path, dest_path)
        st, source_st, seed_st = dest_path.stat(), source_path.stat(), (source_dbdat / name).stat()
        if st.st_nlink != 1 or (st.st_dev, st.st_ino) in {(source_st.st_dev, source_st.st_ino), (seed_st.st_dev, seed_st.st_ino)}:
            raise StockKitRemapError("scratch target archive is not detached from parent and clean source")
        parent_archive_bytes[name] = dest_path.read_bytes()

    api_events = []
    for row in plan["selected_cases"]:
        api_events.append(carrier_kit.copy_art(source_dir=source_dbdat, target_dir=scratch,
            source_team_id=int(row["source_carrier_id"]), target_team_id=int(row["target_carrier_id"]),
            archive_set="foreign-ui"))
    archive_results = {}
    for name in ARCHIVES:
        before, after = parent_archive_bytes[name], (scratch / name).read_bytes()
        parsed_before = {r.file_name: r for r in iter_obfuscated_bmp_records_from_bytes(name, before, file_name_pattern=BMP_RE)}
        parsed_after = {r.file_name: r for r in iter_obfuscated_bmp_records_from_bytes(name, after, file_name_pattern=BMP_RE)}
        if len(before) != len(after) or set(parsed_before) != set(parsed_after):
            raise StockKitRemapError(f"{name} archive record table or size changed")
        allowed: set[int] = set()
        for row in plan["selected_cases"]:
            target_name = row["target_file_by_archive"][name]
            source_name = row["source_file_by_archive"][name]
            target = parsed_before[target_name]
            source = carrier_kit.record_by_name(source_dbdat / name, source_name)
            result = parsed_after[target_name]
            if sha256_bytes(result.raw_bitmap) != row["source_bitmap_sha256s"][name] or result.raw_bitmap != source.raw_bitmap:
                raise StockKitRemapError("existing copy_art output failed source bitmap read-back")
            allowed.update(range(target.bitmap_offset, target.bitmap_offset + target.bitmap_length))
        changed = {i for i, (old, new) in enumerate(zip(before, after)) if old != new}
        if not changed <= allowed:
            raise StockKitRemapError("patch changed bytes outside selected compact-kit bitmap payloads")
        target_names = {row["target_file_by_archive"][name] for row in plan["selected_cases"]}
        for filename, old_record in parsed_before.items():
            if filename not in target_names and parsed_after[filename].raw_bitmap != old_record.raw_bitmap:
                raise StockKitRemapError(f"unselected bitmap changed in {name}: {filename}")
        archive_results[name] = {"archive_before_sha256": sha256_bytes(before),
            "archive_after_sha256": sha256_bytes(after), "mapping_target_count": len(plan["selected_cases"]),
            "changed_byte_count": len(changed)}

    kit_receipt = output_root / "kit-copy-art-receipt.json"
    probe_doc = {"schema_version": "pm99-season-kit-seed-remap-probe-v1",
        "season": plan["season"], "release_id": release.release_id,
        "club": f"{len(plan['selected_cases'])} source-seed carrier mappings",
        "parent_manifest_sha256": release.manifest_sha256,
        "checklist_sha256": plan["checklist_sha256"], "source_archive_sha256s": source_hashes,
        "input_hashes": {name: sha256_file(release.game_path / name) for name in (
            "MANAGPRE.EXE", "DAT.PKF", "DBDAT/JUG98030.FDI", "DBDAT/EQ98030.FDI",
            "DBDAT/ENT98030.FDI", "DBDAT/MINIFOTO.PKF")},
        "changes": [{"archive": name, **archive_results[name]} for name in ARCHIVES],
        "case_ids": [r["case_id"] for r in plan["selected_cases"]],
        "mapping_count": len(plan["selected_cases"]), "copy_art_events": api_events,
        "scope": "stock seed carrier mapping only; no exact historical-kit claim"}
    pipeline.write_canonical_json(probe_root / "receipt.json", probe_doc)
    pipeline.write_canonical_json(kit_receipt, {"schema": "pm99-stock-kit-seed-remap-copy-art-v1",
        "plan": plan, "probe_receipt_sha256": sha256_file(probe_root / "receipt.json"),
        "archive_results": archive_results})

    envelope_root = output_root / "kit-only-envelope-source"
    season_root = envelope_root / plan["season"]
    season_root.mkdir(parents=True)
    no_photo_plan = {"schema_version": visual_patch.SCHEMA, "season": plan["season"],
        "purpose": "kit-only visual patch; deliberate no-op portrait envelope",
        "inputs": {"release_id": release.release_id, "package_sha256": sha256_file(release.package_path),
            "minifoto_sha256": sha256_file(release.game_path / "DBDAT/MINIFOTO.PKF"),
            "kit_remap_plan_sha256": sha256_file(plan_path)},
        "no_photo": [], "replacements": [],
        "audit_scope": {"stock_kit_case_ids": [r["case_id"] for r in plan["selected_cases"]],
            "portrait_review": False, "historical_kit_authenticity": False}}
    pipeline.write_canonical_json(season_root / "plan.json", no_photo_plan)
    visual_patch.materialise(season_root / "plan.json", season_root / "patch")
    combined_root = output_root / "combined-visual-patch"
    visual_patch.extend_kit(plan["season"], envelope_root, probe_root, combined_root)
    combined = combined_root / plan["season"]
    combined_plan = pipeline.read_json_file(combined / "plan.json")
    combined_receipt = pipeline.read_json_file(combined / "patch/receipt.json")
    if combined_plan.get("no_photo") != [] or combined_plan.get("replacements") != []:
        raise StockKitRemapError("visual-patch envelope unexpectedly added portrait actions")
    if set(combined_receipt.get("outputs", {})) != {
        "DBDAT/MINIFOTO.PKF", "DBDAT/MINIESC.PKF", "DBDAT/NANOESC.PKF", "DBDAT/RIDIESC.PKF"}:
        raise StockKitRemapError("combined visual patch has an unexpected file scope")
    if combined_receipt["outputs"]["DBDAT/MINIFOTO.PKF"] != no_photo_plan["inputs"]["minifoto_sha256"]:
        raise StockKitRemapError("kit-only patch changed the portrait archive")
    for path in ("DBDAT/JUG98030.FDI", "DBDAT/EQ98030.FDI", "DBDAT/ENT98030.FDI", "MANAGPRE.EXE", "DAT.PKF"):
        if sha256_file(release.game_path / path) != probe_doc["input_hashes"][path]:
            raise StockKitRemapError(f"protected parent file changed during patch preparation: {path}")
    if sha256_file(Path(plan["palette_binding"]["source_dat_path"])) != plan["palette_binding"]["source_dat_sha256"]:
        raise StockKitRemapError("clean source runtime palette changed during patch preparation")
    for name in ARCHIVES:
        if sha256_file(release.game_path / "DBDAT" / name) != plan["record_preflight"][name]["parent_archive_sha256"]:
            raise StockKitRemapError(f"registered parent archive changed during patch preparation: {name}")
        if sha256_file(source_dbdat / name) != source_hashes[name]:
            raise StockKitRemapError(f"sealed source archive changed during patch preparation: {name}")
    if sha256_file(release.package_path) != plan["parent_package_sha256"]:
        raise StockKitRemapError("parent package changed during private patch preparation")
    pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    result = {"schema": "pm99-season-stock-kit-seed-remap-materialisation-v1",
        "status": "private-patch-ready-not-applied", "plan_sha256": plan_file_sha256,
        "semantic_plan_sha256": sha256_bytes(_canonical_bytes(fresh)),
        "approval_sha256": sha256_file(approval_path), "kit_probe_receipt_sha256": sha256_file(probe_root / "receipt.json"),
        "combined_plan_sha256": sha256_file(combined / "plan.json"),
        "combined_receipt_sha256": sha256_file(combined / "patch/receipt.json"),
        "output_root": str(output_root), "case_ids": [r["case_id"] for r in plan["selected_cases"]],
        "palette_binding": plan["palette_binding"],
        "archive_results": archive_results,
        "checks": {"only_three_compact_archives_changed_in_probe": True,
            "portrait_actions_empty_and_minifoto_exact_noop": True,
            "recipe_and_native_database_unchanged": True,
            "source_and_parent_directories_unchanged": True,
            "game_apply_publish_build_runner_not_called": True,
            "SOURCE_replay_deferred_to_existing_visual_reconstruction_after_A_build": True},
        "scope": "Logical stock-name to carrier seed remap only; no historical season kit-authenticity claim."}
    pipeline.write_canonical_json(output_root / "materialisation-proof.json", result)
    return result


def parse_archive_hashes(values: Sequence[str]) -> dict[str, str]:
    result = {}
    for value in values:
        if "=" not in value:
            raise StockKitRemapError("archive hash arguments must use NAME=SHA256")
        name, digest = value.split("=", 1)
        if name not in ARCHIVES or name in result or not SHA_RE.fullmatch(digest):
            raise StockKitRemapError("archive hash argument is unknown, duplicate, or malformed")
        result[name] = digest
    if set(result) != set(ARCHIVES):
        raise StockKitRemapError("explicit source hashes are required for exactly all three compact archives")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklist", required=True, type=Path)
    parser.add_argument("--checklist-sha256", required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--parent-release-id", required=True)
    parser.add_argument("--parent-manifest-sha256", required=True)
    parser.add_argument("--source-dbd", required=True, type=Path)
    parser.add_argument("--source-archive-sha256", action="append", default=[], metavar="NAME=SHA256")
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--materialise", action="store_true", help="write a private patch bundle; otherwise dry-run only")
    args = parser.parse_args(argv)
    try:
        hashes = parse_archive_hashes(args.source_archive_sha256)
        plan = prepare(checklist_path=args.checklist, checklist_sha256=args.checklist_sha256,
            season=args.season, parent_release_id=args.parent_release_id,
            parent_manifest_sha256=args.parent_manifest_sha256, source_dbdat=args.source_dbd,
            source_archive_sha256s=hashes, case_ids=args.case_id)
        if not args.materialise:
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0
        if args.approval is None or args.output_root is None:
            raise StockKitRemapError("--materialise requires both --approval and a new --output-root")
        approval = _approved_case_ids(args.approval, checklist_sha=plan["checklist_sha256"],
            season=plan["season"], parent_release_id=plan["parent_release_id"],
            parent_manifest_sha=plan["parent_manifest_sha256"], source_hashes=hashes)
        if set(args.case_id) != approval:
            raise StockKitRemapError("--materialise requires explicit --case-id values equal to approved case IDs")
        print(json.dumps(materialise(plan=plan, approval_path=args.approval, output_root=args.output_root), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, pipeline.PipelineError, registry.RegistryError) as exc:
        print(f"stock kit seed remap refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
