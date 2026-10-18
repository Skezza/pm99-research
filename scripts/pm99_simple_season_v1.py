#!/usr/bin/env python3
"""Collect and compile one forgiving, explicitly provisional PM99 season.

This is the simple front door: source gaps and editorial gaps are reported,
not treated as permission failures.  Only malformed inputs and unsafe binary
writes stop the build.  The current V1 front door authors the proved foreign
fixed-carrier families; English fixed-league authoring remains a reported gap.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream/pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.ent_manager_profiles import parse_indexed_ent_manager_profile  # noqa: E402
from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from scripts import capture_transfermarkt_historical_squads_v1 as capture_v1  # noqa: E402
from scripts import compose_season_source_captures_v1 as compose_v1  # noqa: E402
from scripts import reconcile_mode1_roster_base_v1 as base_rows  # noqa: E402
from scripts import season_carrier_allocation_v1 as allocation_v1  # noqa: E402
from scripts import season_editorial_rating_input_builder_v1 as rating_input_v1  # noqa: E402
from scripts import season_editorial_ratings_v1 as ratings_v1  # noqa: E402
from scripts import season_package_compiler_v2 as compiler_v2  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_player_identity_v1 as identity_v1  # noqa: E402
from scripts import season_source_intake_from_allocation_v1 as allocation_intake_v1  # noqa: E402
from scripts import season_source_intake_v1 as intake_v1  # noqa: E402
from scripts import season_source_package_builder_v1 as package_builder_v1  # noqa: E402
from scripts import season_static_ingress_v1 as ingress_v1  # noqa: E402
from tools import pm99_calendar_patcher as calendar_v1  # noqa: E402


SCHEMA = "pm99-simple-season-preview-v1"
DEFAULT_SCOPES = (
    ROOT / "seasons/2000-01/sources/transfermarkt-historical-squad-scope-v1.json",
    ROOT / "scripts/data/transfermarkt-historical-squad-scope-core-six-v1.json",
)
DEFAULT_TEMPLATE = (
    ROOT / ".local/season-static-ingress-v1/2000-01-20260904-r2/season-package.reconciled.json"
)


class SimpleSeasonError(ValueError):
    pass


def _write(path: Path, value: Any) -> str:
    if path.exists() or path.is_symlink():
        raise SimpleSeasonError(f"refusing to replace output: {path}")
    payload = package_v2.canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != package_v2.canonical_json_bytes(value):
        raise SimpleSeasonError(f"input is not canonical JSON: {path}")
    return value


def _season(value: str) -> tuple[str, int, int, str]:
    match = re.fullmatch(r"(19|20)(\d{2})[-/](\d{2})", value)
    if match is None:
        raise SimpleSeasonError("season must be YYYY-YY or YYYY/YY")
    start = int(match.group(1) + match.group(2))
    end = start // 100 * 100 + int(match.group(3))
    if end <= start:
        end += 100
    if end != start + 1 or not 1900 <= start <= 2025:
        raise SimpleSeasonError("season must be consecutive and start in 1900..2025")
    return f"{start:04d}-{end % 100:02d}", start, end, f"{start:04d}/{end % 100:02d}"


def _normalise_capture(capture: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    result = copy.deepcopy(dict(capture))
    seen: dict[str, str] = {}
    suppressed: list[dict[str, str]] = []
    cross_club_claims: list[dict[str, str]] = []
    identity_clubs: dict[tuple[str, str], set[str]] = {}
    competition_codes: list[dict[str, str]] = []
    for club in result["clubs"]:
        # The assignment/intake contracts accept only the canonical club field
        # set.  Keep the capture's competition-code provenance in the receipt
        # instead of letting the first downstream validator reject the club.
        code = club.pop("source_competition_code", None)
        if code is not None:
            competition_codes.append({
                "club_name": str(club["club_name"]), "competition_catalog": str(club["competition_catalog"]),
                "country_catalog": str(club["country_catalog"]), "source_competition_code": str(code),
                "source_path": str(club["source_path"]),
            })
        retained = []
        seen_here: set[str] = set()
        for player in club["players"]:
            digest = hashlib.sha256(package_v2.canonical_json_bytes(player)).hexdigest()
            if digest in seen_here:
                suppressed.append({
                    "player_name": str(player["name"]), "kept_club": str(club["club_name"]),
                    "suppressed_club": str(club["club_name"]), "player_row_sha256": digest,
                })
            else:
                if digest in seen:
                    cross_club_claims.append({
                        "player_name": str(player["name"]), "first_club": seen[digest],
                        "claiming_club": str(club["club_name"]), "player_row_sha256": digest,
                    })
                seen.setdefault(digest, str(club["club_name"]))
                seen_here.add(digest)
                retained.append(player)
                if player.get(identity_v1.IDENTITY_FIELD) is not None:
                    identity_clubs.setdefault(
                        identity_v1.identity_key(player[identity_v1.IDENTITY_FIELD]), set()
                    ).add(str(club["club_name"]))
        club["players"] = retained
    result["summary"]["player_count"] = sum(len(row["players"]) for row in result["clubs"])
    result["summary"]["player_rows_with_unresolved_facts"] = sum(
        bool(player.get("unresolved_fields")) for club in result["clubs"] for player in club["players"]
    )
    receipt = {
        "schema_version": "pm99-simple-source-normalization-v1",
        "policy": "deduplicate-within-club-retain-cross-club-claims-for-dated-reconciliation",
        "suppressed_count": len(suppressed), "suppressed": suppressed,
        "cross_club_claim_count": len(cross_club_claims), "cross_club_claims": cross_club_claims,
    }
    if competition_codes:
        receipt["club_source_competition_codes"] = competition_codes
    if identity_clubs:
        # Same provider ID in several squads is reported, never resolved here:
        # a transfer, loan or capture error needs dated reconciliation.
        id_claims = [
            {"provider": key[0], "player_id": key[1], "clubs": sorted(clubs)}
            for key, clubs in sorted(identity_clubs.items()) if len(clubs) > 1
        ]
        receipt["source_identity_cross_club_claim_count"] = len(id_claims)
        receipt["source_identity_cross_club_claims"] = id_claims
    return result, receipt


def _neutral_template(
    *, template: Mapping[str, Any], registry: Mapping[str, Any], base_tree: Path,
) -> dict[str, Any]:
    result = copy.deepcopy(dict(template))
    base_clubs = {int(row["carrier_id"]): row["baseline_club"] for row in registry["carriers"]}
    for club in result["clubs"]:
        carrier = int(club["carrier_id"])
        baseline = base_clubs[carrier]
        club.update({
            "name": baseline["name"], "full_name": baseline["full_name"],
            "ground_name": baseline["ground_name"], "seated_capacity": int(baseline["seated_capacity"]),
            "ground_policy": "write", "capacity_policy": "write",
            "identity_id": f"club-native-{carrier}",
            "proof": {"artifact_id": "world-mode1-runtime-contract", "grade": "static-contract"},
        })

    ent_data = (base_tree / "DBDAT/ENT98030.FDI").read_bytes()
    ent_entries = {int(row.record_id): row for row in IndexedFDIFile.from_bytes(ent_data).entries}
    for manager in result["managers"]:
        carrier = int(manager["carrier_id"])
        entry = ent_entries[carrier]
        raw = ent_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        manager.update({
            "name": parse_indexed_ent_manager_profile(raw, record_id=carrier).display_name,
            "person_id": f"manager-native-{carrier}", "policy": "preserve-existing-mode1",
            "proof": {"artifact_id": "world-mode1-runtime-contract", "grade": "static-contract"},
        })

    jug_data = (base_tree / "DBDAT/JUG98030.FDI").read_bytes()
    jug_entries = {int(row.record_id): row for row in IndexedFDIFile.from_bytes(jug_data).entries}
    preserve = {"policy": "preserve-existing-mode1"}
    for index, player in enumerate(result["players"]):
        carrier = int(player["carrier_id"])
        payload = jug_entries[carrier].decode_payload(jug_data)
        family = base_rows._player_family(payload, player_carrier=carrier)
        if family == "dd6360":
            result["players"][index] = base_rows._preserved_player(
                payload=payload, player_carrier=carrier, club_id=str(player["club_id"]),
                artifact_id="world-mode1-runtime-contract", source_id="baseline-runtime-contract",
            )
        else:
            replacement = copy.deepcopy(player)
            replacement.pop("source_name", None)
            replacement.pop("source_identity", None)
            replacement.pop("fact_fallbacks", None)
            replacement.update({
                "carrier_family": "dd6361", "name": compiler_v2._player_name(payload, record_id=carrier),
                "person_id": f"person-{carrier}", "policy": "preserve-existing-mode1",
                "proof": {"artifact_id": "world-mode1-runtime-contract", "grade": "static-contract"},
                "facts": {key: copy.deepcopy(preserve) for key in (
                    "birth_date", "fine_roles", "height_cm", "nationality", "primary_position",
                    "shirt_number", "weight_kg",
                )},
            })
            result["players"][index] = replacement
    result["players"].sort(key=lambda row: str(row["id"]))
    package_v2.validate_package(result, strict=True)
    return result


def _apply_ratings_and_calendar(
    *, draft: Mapping[str, Any], rating_output: Mapping[str, Any],
    rating_path: Path, calendar_receipt_path: Path, start: int, end: int,
) -> dict[str, Any]:
    result = copy.deepcopy(dict(draft))
    rating_artifact = f"editorial-ratings-{start}-{end % 100:02d}"
    rating_source = "reviewed-editorial-country-strength-v1"
    result["artifacts"] = [row for row in result["artifacts"] if row["id"] != rating_artifact]
    result["artifacts"].append({
        "id": rating_artifact, "kind": "season-input", "relative_path": rating_path.name,
        "sha256": package_v2.sha256_file(rating_path),
    })
    result["sources"] = [row for row in result["sources"] if row["id"] != rating_source]
    result["sources"].append({
        "id": rating_source, "title": "Deterministic editorial country-strength model v1",
        "proof_grade": "reviewed-editorial", "evidence_artifact_id": rating_artifact,
    })
    rating_by_player = {row["player_id"]: row for row in rating_output["player_ratings"]}
    for player in result["players"]:
        row = rating_by_player.get(player["id"])
        if row is None:
            continue
        rating = copy.deepcopy(row["ratings"])
        rating["provenance"] = {
            "method": "deterministic editorial rating model v1", "proof_grade": "reviewed-editorial",
            "source_ids": [rating_source],
        }
        player["ratings"] = rating

    calendar_artifact = f"calendar-{start}-{end % 100:02d}-receipt"
    result["artifacts"] = [row for row in result["artifacts"] if row["id"] != calendar_artifact]
    result["artifacts"].append({
        "id": calendar_artifact, "kind": "calendar-patch", "relative_path": calendar_receipt_path.name,
        "sha256": package_v2.sha256_file(calendar_receipt_path),
    })
    result["calendar"] = {
        "base_year": 1998, "target_year": start, "target_rollover_year": end,
        "patch_artifact_id": calendar_artifact,
        "proof": {"artifact_id": calendar_artifact, "grade": "source-receipt"},
    }
    result["artifacts"].sort(key=lambda row: str(row["id"]))
    result["sources"].sort(key=lambda row: str(row["id"]))
    package_v2.validate_package(result, strict=True)
    return result


def build(
    *, season_text: str, output_root: Path, cache_root: Path, scopes: Sequence[Path],
    registry_path: Path, template_path: Path, base_tree: Path, verified_base: Path,
    offline: bool, delay: float,
) -> dict[str, Any]:
    season_id, start, end, label = _season(season_text)
    output_root = output_root.resolve()
    if output_root.exists() or output_root.is_symlink():
        raise SimpleSeasonError(f"output root must be new: {output_root}")
    output_root.mkdir(parents=True)

    captures = []
    source_gap_rows = []
    for index, scope_path in enumerate(scopes):
        scope, scope_sha = capture_v1.load_scope(scope_path)
        capture, gaps = capture_v1.build_capture(
            season_start_year=start, scope=scope, scope_sha256=scope_sha,
            cache=capture_v1.SnapshotCache(cache_root, offline=offline, delay=delay),
        )
        capture_path = output_root / f"source-{index + 1}.json"
        _write(capture_path, capture)
        _write(output_root / f"source-{index + 1}-gaps.json", gaps)
        captures.append((capture_path.name, capture, package_v2.sha256_file(capture_path)))
        source_gap_rows.extend(gaps["gaps"])
    composed = compose_v1.compose(inputs=captures, catalog=f"{start}-{end}", label=label)
    normalized, normalization = _normalise_capture(composed)
    _write(output_root / "world-squads.json", normalized)
    _write(output_root / "source-normalization.json", normalization)

    registry = _read(registry_path)
    allocation = allocation_v1.build_allocation(source=normalized, registry=registry)
    _write(output_root / "foreign-carrier-allocation.json", allocation)
    assignment = allocation_intake_v1.adapt(
        allocation=allocation, registry=registry, source=normalized,
        assignment_id=f"world-{season_id}-simple-preview",
    )
    intake = intake_v1.build_intake(
        registry=registry, source_capture=normalized, assignment=assignment,
        intake_id=f"world-{season_id}-simple-preview-intake",
    )
    _write(output_root / "source-intake.json", intake)

    template = _neutral_template(template=_read(template_path), registry=registry, base_tree=base_tree)
    draft, package_audit = package_builder_v1.build_draft(
        template=template, source_intake=intake, registry=registry,
        carrier_allocation=allocation, template_prevalidated=True,
    )
    _write(output_root / "package-audit.json", package_audit)
    rating_input, rating_audit = rating_input_v1.build_input(draft=draft, allocation=allocation)
    rating_output = ratings_v1.build_rating_output(rating_input)
    rating_path = output_root / "editorial-ratings.json"
    _write(rating_path, rating_output)
    _write(output_root / "editorial-rating-audit.json", rating_audit)

    calendar_exe = output_root / "MANAGPRE.EXE"
    calendar_receipt_path = output_root / "calendar-receipt.json"
    calendar_receipt = calendar_v1.patch_calendar(base_tree / "MANAGPRE.EXE", calendar_exe, start)
    _write(calendar_receipt_path, calendar_receipt)
    package = _apply_ratings_and_calendar(
        draft=draft, rating_output=rating_output, rating_path=rating_path,
        calendar_receipt_path=calendar_receipt_path, start=start, end=end,
    )
    package_path = output_root / "season-package.json"
    _write(package_path, package)

    ingress_dir = output_root / "compiled"
    ingress = ingress_v1.ingress(
        package_path=package_path, base_tree=base_tree,
        verified_base_path=verified_base, output_dir=ingress_dir,
    )
    shutil.copy2(calendar_exe, ingress_dir / "game/MANAGPRE.EXE")
    report = {
        "schema_version": SCHEMA, "season": season_id,
        "state": "compiled-provisional-partial-not-runtime-validated",
        "game": "compiled/game", "release_eligible": False,
        "coverage": {
            "captured_club_count": len(normalized["clubs"]),
            "captured_unique_player_row_count": normalized["summary"]["player_count"],
            "source_competition_gap_count": len(source_gap_rows),
            "exact_duplicate_player_claim_count": normalization["suppressed_count"],
            "target_season_foreign_club_count": allocation["coverage"]["assignment_count"],
            "target_season_player_count": rating_output["coverage"]["player_count"],
            "native_foreign_club_fallback_count": len(package["clubs"]) - allocation["coverage"]["assignment_count"],
            "native_manager_fallback_count": len(package["managers"]),
            "opening_lineup_count": 0, "target_season_kit_count": 0,
        },
        "gaps": {
            "source_competitions": source_gap_rows,
            "carrier_allocation": allocation["gaps"],
            "package": package_audit["hard_blockers"],
            "english_fixed_leagues": "captured source rows are not yet authored by this foreign-carrier V1 front door",
            "managers": "native byte-preserving fallback; target-season manager source not acquired",
            "opening_lineups": "not acquired; native tactics preserved",
            "kits": "not acquired; native archives preserved",
            "portraits": "native/no-image state preserved",
        },
        "hashes": {
            "season_package": package_v2.sha256_file(package_path),
            "calendar": package_v2.sha256_file(calendar_exe),
            "compiler_receipt": package_v2.sha256_file(ingress_dir / "compiler-receipt.json"),
        },
    }
    _write(output_root / "preview-report.json", report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--cache-root", type=Path, default=ROOT / ".local/source-cache/transfermarkt-season-v1")
    parser.add_argument("--scope", action="append", type=Path)
    parser.add_argument("--registry", type=Path, default=ROOT / "seasons/2000-01/fixed-carrier-registry.json")
    parser.add_argument("--template-package", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--base-tree", type=Path, default=ROOT / ".local/season-pipeline-v2/pm99-base-clean")
    parser.add_argument("--verified-base", type=Path, default=ROOT / ".local/season-pipeline-v2/verified-base.json")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.5)
    args = parser.parse_args(argv)
    try:
        season_id, _start, _end, _label = _season(args.season)
        output_root = args.output_root or ROOT / ".local/simple-season-previews" / season_id / "run-v1"
        report = build(
            season_text=args.season, output_root=output_root, cache_root=args.cache_root,
            scopes=tuple(args.scope or DEFAULT_SCOPES), registry_path=args.registry,
            template_path=args.template_package, base_tree=args.base_tree.resolve(),
            verified_base=args.verified_base.resolve(), offline=args.offline, delay=args.delay,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps({"state": report["state"], **report["coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
