#!/usr/bin/env python3
"""Turn a checked Wikipedia player-fact receipt into a narrow V2 overlay.

This is the write boundary for the polite Wikipedia capture.  It binds an
overlay to one canonical package, changes only fields that were absent in that
package, and retains the receipt as the evidence artifact.  It never changes
ratings, rosters, club allocation or compiled game files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_2015_fifa16_secondary_player_facts_v1 as fifa_capture  # noqa: E402
from scripts import capture_2015_declared_historical_player_facts_v1 as declared_capture  # noqa: E402
from scripts import capture_2015_sofifa_secondary_player_facts_v1 as sofifa_capture  # noqa: E402
from scripts import compose_2015_secondary_player_facts_v1 as composed_capture  # noqa: E402
from scripts import capture_2015_wikipedia_player_facts_v1 as capture  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_review_v2 as review  # noqa: E402


class FactOverrideError(ValueError):
    """A source receipt cannot safely patch the requested package."""


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise FactOverrideError("receipt must be inside the workspace") from exc


def _introduced_collision_patch_ids(
    package: Mapping[str, Any], patches: Sequence[Mapping[str, Any]],
) -> tuple[set[str], list[dict[str, Any]]]:
    """Reject fact patches that reveal an unresolved same-person allocation.

    A precise DOB/nationality can turn two apparently unrelated inherited
    rows into the same target-season person.  That is a roster-ownership
    decision, not permission to duplicate the person in a playable package.
    """
    players = [dict(row) for row in package.get("players") or [] if isinstance(row, Mapping)]
    originals = {str(row.get("id") or ""): row for row in players}
    proposed = {identity: dict(row) for identity, row in originals.items()}
    patch_ids: set[str] = set()
    for patch in patches:
        target_id = str((patch.get("target") or {}).get("id") or "")
        player = proposed.get(target_id)
        if player is None:
            continue
        facts = dict(player.get("facts") or {})
        for path, value in (patch.get("set") or {}).items():
            if str(path).startswith("facts."):
                facts[str(path).split(".", 1)[1]] = value
        player["facts"] = facts
        patch_ids.add(target_id)

    def groups(rows: Mapping[str, Mapping[str, Any]]) -> dict[tuple[str, str], list[str]]:
        result: dict[tuple[str, str], list[str]] = {}
        for identity, player in rows.items():
            key = package_v2._person_candidate_key(dict(player))
            if key is not None:
                result.setdefault(key, []).append(identity)
        return result

    before = groups(originals)
    after = groups(proposed)
    rejected: set[str] = set()
    queue: list[dict[str, Any]] = []
    for key, members in sorted(after.items()):
        if len(members) < 2 or len(before.get(key, [])) > 1:
            continue
        changed = sorted(set(members) & patch_ids)
        if not changed:
            continue
        rejected.update(changed)
        queue.append({
            "person_key": {"normalised_name": key[0], "birth_date": key[1]},
            "conflicting_player_ids": sorted(members),
            "withheld_player_fact_patch_ids": changed,
            "reason": "new-source-facts-reveal-unresolved-same-person-fixed-carrier-ownership",
        })
    return rejected, queue


def build(*, package: Mapping[str, Any], package_sha256: str,
          receipt: Mapping[str, Any], receipt_path: str, receipt_sha256: str) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt_schema = receipt.get("schema_version")
    artifact_id_by_schema = {
        capture.SCHEMA: "wikipedia-player-facts-2015",
        fifa_capture.SCHEMA: "fifa16-secondary-player-facts-2015",
        declared_capture.SCHEMA: "declared-historical-player-facts-2015",
        sofifa_capture.SCHEMA: "sofifa-secondary-player-facts-2015",
        composed_capture.SCHEMA: "composed-secondary-player-facts-2015",
    }
    artifact_id = artifact_id_by_schema.get(receipt_schema)
    if artifact_id is None:
        raise FactOverrideError("unsupported secondary player-fact receipt schema")
    source = receipt.get("sources")
    if not isinstance(source, Mapping) or source.get("base_package_sha256") != package_sha256:
        raise FactOverrideError("Wikipedia player-fact receipt targets a different package")
    players = {str(row.get("id") or ""): row for row in package.get("players") or [] if isinstance(row, Mapping)}
    rows = receipt.get("rows")
    if not isinstance(rows, list):
        raise FactOverrideError("Wikipedia player-fact receipt has no rows")
    patches: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise FactOverrideError("Wikipedia player-fact receipt has a malformed row")
        player_id = str(row.get("player_id") or "")
        player = players.get(player_id)
        values = row.get("facts")
        if player is None or not isinstance(values, Mapping) or not values:
            raise FactOverrideError("Wikipedia player-fact receipt has an unknown player or no facts")
        facts = player.get("facts")
        if not isinstance(facts, Mapping):
            raise FactOverrideError(f"player {player_id} has no fact object")
        expected: dict[str, Any] = {}
        replacement: dict[str, Any] = {}
        for field, value in sorted(values.items()):
            path = f"facts.{field}"
            existing = facts.get(field)
            if existing is not None and not isinstance(existing, Mapping):
                raise FactOverrideError(
                    f"Wikipedia receipt refuses to replace present {player_id} {field}"
                )
            expected[path] = existing
            replacement[path] = value
        patches.append({
            "id": f"wikipedia-fact-{player_id}",
            "target": {"entity": "player", "id": player_id},
            "expected": expected,
            "set": replacement,
            "reason": "exact declared source-name source supplied previously absent secondary player fact(s)",
            "proof": {"grade": "source-receipt", "artifact_id": artifact_id},
        })
    rejected, collisions = _introduced_collision_patch_ids(package, patches)
    patches = [
        row for row in patches
        if str((row.get("target") or {}).get("id") or "") not in rejected
    ]
    override = {
        "schema_version": review.OVERRIDES_SCHEMA,
        "override_id": (
            "wikipedia-player-facts-2015-r1"
            if receipt_schema == capture.SCHEMA else
            "fifa16-secondary-player-facts-2015-r1"
            if receipt_schema == fifa_capture.SCHEMA else
            "declared-historical-player-facts-2015-r1"
            if receipt_schema == declared_capture.SCHEMA else
            "sofifa-secondary-player-facts-2015-r1"
            if receipt_schema == sofifa_capture.SCHEMA else
            "composed-secondary-player-facts-2015-r1"
        ),
        "base_package_canonical_sha256": package_sha256,
        "artifacts": [{
            "id": artifact_id, "kind": "season-input",
            "relative_path": receipt_path, "sha256": receipt_sha256,
        }],
        "sources": [{
            "id": "secondary-player-facts-source-2015",
            "title": (
                "Cached exact-title English Wikipedia player fact receipt"
                if receipt_schema == capture.SCHEMA else
                "Exact-source-name FIFA 16 secondary player fact receipt"
                if receipt_schema == fifa_capture.SCHEMA else
                "Cited exact-identity target-season historical player fact receipt"
                if receipt_schema == declared_capture.SCHEMA else
                "Exact-source-name cached FIFA/SoFIFA secondary player fact receipt"
                if receipt_schema == sofifa_capture.SCHEMA else
                "Composed agreeing exact-identity player fact receipts"
            ),
            "proof_grade": "source-receipt",
            "evidence_artifact_id": artifact_id,
        }],
        "proofs": [{
            "id": "secondary-player-facts-proof-2015", "grade": "source-receipt",
            "artifact_id": artifact_id,
            "covers": ["exact-title sourced missing player secondary facts"],
        }],
        "data_patches": sorted(patches, key=lambda row: str(row["id"])),
        "portrait_patches": [],
    }
    review.validate_overrides(override)
    queue = {
        "schema_version": "pm99-world-2015-player-fact-identity-collision-queue-v1",
        "base_package_canonical_sha256": package_sha256,
        "source_receipt_sha256": receipt_sha256,
        "withheld_patch_count": len(rejected),
        "entries": collisions,
    }
    return override, queue


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--identity-queue", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output.exists() or args.identity_queue.exists():
            raise FactOverrideError("refusing to overwrite output or identity queue")
        package = package_v2.read_canonical_package(args.package)
        package_v2.validate_package(package)
        package_raw = args.package.read_bytes()
        receipt_raw = args.receipt.read_bytes()
        receipt = json.loads(receipt_raw.decode("utf-8"))
        if not isinstance(receipt, dict) or receipt_raw != package_v2.canonical_json_bytes(receipt):
            raise FactOverrideError("Wikipedia player-fact receipt must be canonical JSON")
        result, queue = build(
            package=package, package_sha256=hashlib.sha256(package_raw).hexdigest(),
            receipt=receipt, receipt_path=_relative(args.receipt),
            receipt_sha256=hashlib.sha256(receipt_raw).hexdigest(),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, package_v2.PackageValidationError, FactOverrideError, review.SeasonReviewError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(package_v2.canonical_json_bytes(result))
    args.identity_queue.parent.mkdir(parents=True, exist_ok=True)
    args.identity_queue.write_bytes(package_v2.canonical_json_bytes(queue))
    print(json.dumps({"data_patch_count": len(result["data_patches"]), "withheld_identity_collision_patch_count": queue["withheld_patch_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
