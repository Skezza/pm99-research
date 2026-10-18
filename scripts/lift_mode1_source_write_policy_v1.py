#!/usr/bin/env python3
"""Derive a writable fixed-carrier candidate for already-bound source people.

Older source-draft packages could inherit ``preserve-existing-mode1`` from a
native template row after that row had been assigned a dated source person.
That policy skips the whole PM99 record, so the package would claim the source
person while the game retained the baseline person.  This narrow migration
removes only that contradictory whole-record policy.  It preserves every
explicit per-field fallback, source fact, identity and roster assignment.

It is source-package repair only: no source capture, allocation, binary,
release, runtime or screenshot changes are made.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts import season_package_compiler_v2 as compiler_v2  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_pipeline_v2 as pipeline_v2  # noqa: E402


SCHEMA = "pm99-mode1-source-write-policy-lift-v1"
STATE = "source-bound-mode1-write-policy-lifted-static-candidate-only"


class SourceWritePolicyLiftError(ValueError):
    """The input cannot safely be derived into a writable source candidate."""


def _canonical_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_verified_base(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceWritePolicyLiftError(f"cannot read verified base descriptor: {path}: {exc}") from exc
    if not isinstance(value, dict) or raw != _canonical_bytes(value):
        raise SourceWritePolicyLiftError(f"verified base descriptor is not canonical JSON: {path}")
    return pipeline_v2.validate_verified_base_descriptor(value)


def lift_source_write_policy(
    *, package_path: Path, base_tree: Path, verified_base_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    package = package_v2.read_canonical_package(package_path)
    package_v2.validate_package(package, strict=True)
    base = _read_verified_base(verified_base_path)
    pipeline_v2.verify_base_tree(tree=base_tree, verified_base=base)
    eq_path = base_tree / "DBDAT" / "EQ98030.FDI"
    jug_path = base_tree / "DBDAT" / "JUG98030.FDI"
    if not eq_path.is_file() or not jug_path.is_file():
        raise SourceWritePolicyLiftError("verified base is missing required DBDAT/EQ98030.FDI or JUG98030.FDI")
    _owners, _rosters, modes = compiler_v2._source_roster_owners(eq_path.read_bytes())
    club_modes = {str(club["id"]): modes.get(int(club["carrier_id"])) for club in package["clubs"]}
    output = copy.deepcopy(package)
    changed: list[dict[str, Any]] = []
    for player in output["players"]:
        if player.get("policy") != "preserve-existing-mode1":
            continue
        person_id = str(player.get("person_id") or "")
        if not person_id.startswith("person-source-"):
            continue
        if club_modes.get(str(player["club_id"])) != 1:
            raise SourceWritePolicyLiftError(
                f"source person {player['id']} carries a whole-record mode-1 policy outside a mode-1 club"
            )
        source_name = player.get("source_name")
        if not isinstance(source_name, str) or not source_name.strip():
            raise SourceWritePolicyLiftError(
                f"source person {player['id']} has no recorded source_name for a writable-policy lift"
            )
        player.pop("policy")
        changed.append({
            "player_id": player["id"],
            "carrier_id": int(player["carrier_id"]),
            "club_id": player["club_id"],
            "person_id": person_id,
            "source_name": source_name,
            "display_name_before_alias": player["name"],
            "retained_field_fallbacks": [
                row["field"] for row in player.get("fact_fallbacks", [])
            ],
        })
    if not changed:
        raise SourceWritePolicyLiftError("no contradictory source-bound whole-record preserve policies were found")
    package_v2.validate_package(output, strict=True)
    audit = {
        "schema_version": SCHEMA,
        "state": STATE,
        "season": output["season"],
        "release_eligible": False,
        "input": {
            "package_sha256": package_v2.sha256_file(package_path),
            "verified_base_sha256": package_v2.sha256_file(verified_base_path),
            "base_inventory_fingerprint": base["inventory"]["files_fingerprint"],
            "base_eq98030_sha256": hashlib.sha256(eq_path.read_bytes()).hexdigest(),
            "base_jug98030_sha256": hashlib.sha256(jug_path.read_bytes()).hexdigest(),
        },
        "lift": {
            "policy": "remove-whole-record-preserve-only-for-existing-source-bound-mode1-persons",
            "changed_player_count": len(changed),
            "changed_players": changed,
        },
        "next_required_stage": "parser-safe-display-alias-binding",
        "not_performed": [
            "source acquisition",
            "source manifest change",
            "carrier allocation change",
            "binary compiler materialisation",
            "clean static audit",
            "release manifest generation",
            "PM99 runtime validation",
            "target-season runtime screenshot",
        ],
    }
    return output, audit


def _write_new(path: Path, payload: bytes) -> str:
    if path.exists() or path.is_symlink():
        raise SourceWritePolicyLiftError(f"refusing to replace existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return _sha256_bytes(payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--verified-base", required=True, type=Path)
    parser.add_argument("--output-package", required=True, type=Path)
    parser.add_argument("--output-audit", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output_package.resolve() == args.output_audit.resolve():
        print("mode-1 source write-policy lift error: output package and audit must differ", file=sys.stderr)
        return 2
    if args.output_package.exists() or args.output_audit.exists():
        existing = args.output_package if args.output_package.exists() else args.output_audit
        print(f"mode-1 source write-policy lift error: refusing to replace existing output: {existing.resolve()}", file=sys.stderr)
        return 2
    try:
        output, audit = lift_source_write_policy(
            package_path=args.package.resolve(),
            base_tree=args.base_tree.resolve(),
            verified_base_path=args.verified_base.resolve(),
        )
        package_sha256 = _write_new(args.output_package.resolve(), _canonical_bytes(output))
        audit["output"] = {"package_path": str(args.output_package), "package_sha256": package_sha256}
        _write_new(args.output_audit.resolve(), _canonical_bytes(audit))
    except (
        SourceWritePolicyLiftError,
        package_v2.PackageValidationError,
        pipeline_v2.PipelineError,
        OSError,
        ValueError,
    ) as exc:
        print(f"mode-1 source write-policy lift error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "changed_player_count": audit["lift"]["changed_player_count"],
        "output_audit": str(args.output_audit),
        "output_package_sha256": package_sha256,
        "state": STATE,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
