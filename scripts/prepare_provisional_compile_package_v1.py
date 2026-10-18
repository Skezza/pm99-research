#!/usr/bin/env python3
"""Make a source draft mechanically compilable without hiding editorial gaps.

Whole-season squad sources can claim the same person at two clubs after a
loan or transfer.  A PM99 opening-date database cannot.  This provisional
normalizer retains a uniquely opening-XI-backed claim when one exists;
otherwise it retains one stable candidate and records that ownership as an
editorial gap.  Every other fixed mode-1 carrier is restored from the verified
clean base rather than deleted or filled with another historical person.

It also applies the global position-aware Handling rules: 1..20 for known
outfield players and at least max(35, quality - 12) for goalkeepers.  The input
package, source snapshots and previous builds are never modified.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from scripts import reconcile_mode1_roster_base_v1 as base_rows  # noqa: E402
from scripts import season_editorial_ratings_v1 as rating_model  # noqa: E402
from scripts import season_package_compiler_v2 as compiler  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_pipeline_v2 as pipeline  # noqa: E402


SCHEMA = "pm99-provisional-compile-package-preparation-v1"
PRESERVATION_ARTIFACT_ID = "world-mode1-runtime-contract"
PRESERVATION_SOURCE_ID = "baseline-runtime-contract"


class ProvisionalPreparationError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _duplicate_groups(package: Mapping[str, Any]) -> list[tuple[tuple[str, str], list[dict[str, Any]]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in package["players"]:
        row = dict(raw)
        key = package_v2._person_candidate_key(row)
        if key is not None:
            groups[key].append(row)
    return sorted((key, rows) for key, rows in groups.items() if len(rows) > 1)


def _opening_player_ids(club: Mapping[str, Any]) -> set[str]:
    opening = club.get("opening")
    if not isinstance(opening, Mapping) or opening.get("policy") == "preserve-existing-mode1":
        return set()
    result: set[str] = set()
    for field in ("starting_xi_player_ids", "substitute_player_ids"):
        values = opening.get(field)
        if isinstance(values, list):
            result.update(str(value) for value in values)
    return result


def _retained_candidate(rows: list[dict[str, Any]], clubs: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], str]:
    dated = [row for row in rows if str(row["id"]) in _opening_player_ids(clubs[str(row["club_id"])])]
    if len(dated) == 1:
        return dated[0], "unique-package-opening-xi-or-bench-claim"
    source_captured = [
        row for row in rows
        if isinstance(row.get("proof"), Mapping)
        and row["proof"].get("grade") == "source-captured"
    ]
    if len(source_captured) == 1:
        return source_captured[0], "unique-source-captured-player-claim"
    # This choice exists only to permit a provisional compile.  It is stable
    # across carrier ordering changes because club and player IDs are canonical
    # package identities, and it remains an explicit editorial queue item.
    retained = min(rows, key=lambda row: (str(row["club_id"]), str(row["id"])))
    return retained, "stable-provisional-choice-editorial-ownership-unresolved"


def _normalise_position_handling(players: Mapping[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Apply deterministic Handling guardrails without changing unknown positions."""
    outfield_rows: list[dict[str, Any]] = []
    goalkeeper_rows: list[dict[str, Any]] = []
    for player_id, player in players.items():
        facts = player.get("facts")
        ratings = player.get("ratings")
        values = ratings.get("values") if isinstance(ratings, Mapping) else None
        if not isinstance(facts, Mapping) or not isinstance(values, dict):
            continue
        position = facts.get("primary_position")
        handling = values.get("handling")
        if not isinstance(handling, int) or isinstance(handling, bool):
            continue
        person_id = str(player.get("person_id") or player_id)
        if isinstance(position, str) and position in {"D", "M", "F"} and handling > 20:
            after = max(1, min(20, 8 + rating_model._variation(
                person_id=person_id, field="handling"
            )))
            values["handling"] = after
            outfield_rows.append({"player_id": player_id, "before": handling, "after": after})
        elif position == "G" and handling < 35:
            quality = values.get("quality")
            quality = quality if isinstance(quality, int) and not isinstance(quality, bool) else 47
            after = max(
                35,
                quality - 12,
                rating_model._clamp(
                    quality + rating_model._variation(person_id=person_id, field="handling")
                ),
            )
            values["handling"] = after
            goalkeeper_rows.append({"player_id": player_id, "before": handling, "after": after})

    return {
        "outfield": sorted(outfield_rows, key=lambda row: row["player_id"]),
        "goalkeeper": sorted(goalkeeper_rows, key=lambda row: row["player_id"]),
    }


def prepare(
    *, package_path: Path, base_tree: Path, verified_base_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    package = package_v2.read_canonical_package(package_path)
    package_v2.validate_package(package, strict=False)
    verified = pipeline.validate_verified_base_descriptor(
        json.loads(verified_base_path.read_text(encoding="utf-8"))
    )
    pipeline.verify_base_tree(tree=base_tree, verified_base=verified)
    if PRESERVATION_ARTIFACT_ID not in base_rows._artifact_ids(package):
        raise ProvisionalPreparationError("package lacks the clean-base preservation artifact")
    if PRESERVATION_SOURCE_ID not in base_rows._source_ids(package):
        raise ProvisionalPreparationError("package lacks the clean-base preservation source")

    eq_data = (base_tree / "DBDAT/EQ98030.FDI").read_bytes()
    jug_data = (base_tree / "DBDAT/JUG98030.FDI").read_bytes()
    _owners, _rosters, modes = compiler._source_roster_owners(eq_data)
    jug_entries = {
        int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(jug_data).entries
    }

    output = copy.deepcopy(package)
    clubs = {str(row["id"]): row for row in output["clubs"]}
    players = {str(row["id"]): row for row in output["players"]}
    resolution_rows: list[dict[str, Any]] = []
    restored_ids: set[str] = set()
    removed_mode0_ids: set[str] = set()
    unresolved_count = 0

    for candidate, rows in _duplicate_groups(output):
        retained, method = _retained_candidate(rows, clubs)
        if method.startswith("stable-provisional"):
            unresolved_count += 1
        replacements: list[dict[str, Any]] = []
        for row in sorted(rows, key=lambda value: str(value["id"])):
            if row["id"] == retained["id"]:
                continue
            club = clubs[str(row["club_id"])]
            team_carrier = int(club["carrier_id"])
            player_carrier = int(row["carrier_id"])
            if modes.get(team_carrier) == 0:
                player_id = str(row["id"])
                roster = club["roster_player_ids"]
                opening = club.get("opening") if isinstance(club.get("opening"), dict) else {}
                starters = opening.get("starting_xi_player_ids") if isinstance(opening.get("starting_xi_player_ids"), list) else []
                substitutes = opening.get("substitute_player_ids") if isinstance(opening.get("substitute_player_ids"), list) else []
                if player_id in starters:
                    replacement = next(
                        (value for value in substitutes if value != player_id and value not in starters),
                        None,
                    )
                    if replacement is None:
                        replacement = next(
                            (value for value in roster if value != player_id and value not in starters),
                            None,
                        )
                    if replacement is None:
                        raise ProvisionalPreparationError(
                            f"duplicate {player_id} has no same-club opening-XI replacement"
                        )
                    opening["starting_xi_player_ids"] = [
                        replacement if value == player_id else value for value in starters
                    ]
                    opening["substitute_player_ids"] = [
                        value for value in substitutes if value not in {player_id, replacement}
                    ]
                else:
                    opening["substitute_player_ids"] = [
                        value for value in substitutes if value != player_id
                    ]
                club["roster_player_ids"] = [value for value in roster if value != player_id]
                if len(club["roster_player_ids"]) < 16:
                    raise ProvisionalPreparationError(
                        f"removing duplicate {player_id} would leave {club['id']} below 16 players"
                    )
                players.pop(player_id)
                removed_mode0_ids.add(player_id)
                replacements.append({
                    "player_id": player_id,
                    "club_id": row["club_id"],
                    "carrier_id": player_carrier,
                    "mode0_action": "leave-clean-base-carrier-untouched-and-unselected",
                })
                continue
            if modes.get(team_carrier) != 1 or player_carrier not in jug_entries:
                raise ProvisionalPreparationError(
                    f"duplicate {row['id']} cannot be restored as a fixed mode-1 clean-base row"
                )
            payload = jug_entries[player_carrier].decode_payload(jug_data)
            fallback = base_rows._preserved_player(
                payload=payload,
                player_carrier=player_carrier,
                club_id=str(row["club_id"]),
                artifact_id=PRESERVATION_ARTIFACT_ID,
                source_id=PRESERVATION_SOURCE_ID,
            )
            if fallback["id"] != row["id"]:
                raise ProvisionalPreparationError(f"clean-base player identity changed for {row['id']}")
            players[str(row["id"])] = fallback
            restored_ids.add(str(row["id"]))
            replacements.append({
                "player_id": row["id"], "club_id": row["club_id"],
                "carrier_id": player_carrier, "restored_native_name": fallback["name"],
            })
        resolution_rows.append({
            "candidate": {
                "normalised_name": candidate[0], "birth_date": candidate[1],
            },
            "method": method,
            "retained": {
                "player_id": retained["id"], "club_id": retained["club_id"],
                "carrier_id": retained["carrier_id"],
            },
            "restored_clean_base_rows": replacements,
            "editorial_review_required": method.startswith("stable-provisional"),
        })

    handling_rows = _normalise_position_handling(players)

    output["players"] = sorted(players.values(), key=lambda row: str(row["id"]))
    portraits = []
    for portrait in output["assets"]["portraits"]:
        if str(portrait["player_id"]) in removed_mode0_ids:
            continue
        if str(portrait["player_id"]) not in restored_ids:
            portraits.append(portrait)
        else:
            portraits.append({
                "player_id": portrait["player_id"], "status": "unresolved",
                "review_reason": "provisional duplicate ownership restored this carrier to its clean native row",
                "proof": {"artifact_id": PRESERVATION_ARTIFACT_ID, "grade": "static-contract"},
            })
    output["assets"]["portraits"] = sorted(portraits, key=lambda row: str(row["player_id"]))
    package_v2.validate_package(output, strict=True)

    opening_resolved_count = sum(
        row["method"] == "unique-package-opening-xi-or-bench-claim"
        for row in resolution_rows
    )
    source_resolved_count = sum(
        row["method"] == "unique-source-captured-player-claim"
        for row in resolution_rows
    )
    not_claimed = ["runtime-validation", "release-eligibility"]
    if unresolved_count:
        not_claimed.insert(
            0, "historically-correct-opening-club-for-unresolved-duplicate-candidates"
        )
    audit = {
        "schema_version": SCHEMA,
        "state": (
            "strict-package-ready-provisional"
            if unresolved_count == 0
            else "strict-package-ready-provisional-editorial-gaps-retained"
        ),
        "release_eligible": False,
        "season": output["season"],
        "input": {
            "package_sha256": _sha256(package_path),
            "verified_base_sha256": _sha256(verified_base_path),
            "base_inventory_fingerprint": verified["inventory"]["files_fingerprint"],
        },
        "duplicate_ownership": {
            "group_count": len(resolution_rows),
            "opening_evidence_resolved_count": opening_resolved_count,
            "source_evidence_resolved_count": source_resolved_count,
            "editorial_review_required_count": unresolved_count,
            "restored_clean_base_player_count": len(restored_ids),
            "unselected_mode0_player_count": len(removed_mode0_ids),
            "rows": resolution_rows,
        },
        "outfield_handling": {
            "policy": "deterministic-editorial-1-to-20",
            "changed_player_count": len(handling_rows["outfield"]),
            "rows": handling_rows["outfield"],
        },
        "goalkeeper_handling": {
            "policy": "deterministic-editorial-floor-max-35-or-quality-minus-12",
            "changed_player_count": len(handling_rows["goalkeeper"]),
            "rows": handling_rows["goalkeeper"],
        },
        "not_claimed": not_claimed,
    }
    return output, audit


def _write_new(path: Path, value: Any) -> str:
    if path.exists() or path.is_symlink():
        raise ProvisionalPreparationError(f"refusing to replace output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = package_v2.canonical_json_bytes(value)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--verified-base", required=True, type=Path)
    parser.add_argument("--output-package", required=True, type=Path)
    parser.add_argument("--output-audit", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        package, audit = prepare(
            package_path=args.package.resolve(), base_tree=args.base_tree.resolve(),
            verified_base_path=args.verified_base.resolve(),
        )
        package_sha = _write_new(args.output_package.resolve(), package)
        audit["output"] = {"package_sha256": package_sha}
        _write_new(args.output_audit.resolve(), audit)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "duplicate_groups": audit["duplicate_ownership"]["group_count"],
        "editorial_ownership_gaps": audit["duplicate_ownership"]["editorial_review_required_count"],
        "outfield_handling_changes": audit["outfield_handling"]["changed_player_count"],
        "goalkeeper_handling_changes": audit["goalkeeper_handling"]["changed_player_count"],
        "package_sha256": package_sha,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
