#!/usr/bin/env python3
"""Plan target-season club identities for the remaining 2015 source tail.

This is the bridge between the fixed PM99 carriers and a real 2015 league
membership source.  It produces an editable receipt only: no player, manager,
kit, or PM99 file is written.  A proposed club must still pass a pinned 2015
squad-capacity check before it can enter a source package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "pm99-world-2015-source-tail-replacement-plan-v1"
MEMBERSHIP_SCHEMA = "pm99-world-2015-top-flight-membership-v1"
DISPOSITION_SCHEMA = "pm99-world-2015-unresolved-carrier-dispositions-v1"

# These abbreviations are harmless legal/competition prefixes.  They are
# removed only to recognise that a *source-ready incumbent* already occupies a
# target-season article entry; no fuzzy club matching is performed.
IDENTITY_PREFIXES = {
    "ac", "as", "bk", "cd", "cf", "cs", "fc", "fk", "hnk", "nk", "ofc", "pfc", "sc", "sk",
}

# These are documented historic/abbreviated display forms in the legacy PM99
# carrier ledger.  Each points at one article already present in the captured
# target-season membership receipt.  They establish retention only; they do
# not permit a cross-country or fuzzy club choice.
BASELINE_TARGET_ALIASES = {
    ("bolivia", "oriente petrol"): "/wiki/Oriente_Petrolero",
    ("ecuador", "barc guayaquil"): "/wiki/Barcelona_Sporting_Club",
    ("ecuador", "barcelona guayaquil"): "/wiki/Barcelona_Sporting_Club",
    ("lithuania", "zalguiris"): "/wiki/FC_%C5%BDalgiris",
    ("uruguay", "wanderers"): "/wiki/Montevideo_Wanderers_F.C.",
    ("wales", "aberyswith town"): "/wiki/Aberystwyth_Town_F.C.",
    ("wales", "connah s quay"): "/wiki/Connah%27s_Quay_Nomads_F.C.",
    ("wales", "llasantffraid"): "/wiki/The_New_Saints_F.C.",
    ("wales", "newton"): "/wiki/Newtown_A.F.C.",
}


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    tokens = re.findall(r"[a-z0-9]+", text.casefold())
    return " ".join(token for token in tokens if token not in IDENTITY_PREFIXES | {"club", "football"})


def _load(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _membership_index(membership: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if membership.get("schema_version") != MEMBERSHIP_SCHEMA:
        raise ValueError("membership receipt has an unsupported schema")
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_paths: dict[str, set[str]] = defaultdict(set)
    for league in membership.get("leagues", []):
        family = str(league.get("family") or "")
        teams = league.get("teams")
        if not family or not isinstance(teams, list) or not teams:
            raise ValueError("membership receipt has malformed league rows")
        cleaned = []
        for position, team in enumerate(teams, start=1):
            if not isinstance(team, Mapping):
                raise ValueError(f"membership team is malformed for {family}")
            name, title, path = (str(team.get(key) or "") for key in ("name", "article_title", "article_path"))
            if not name or not title or not path or path in seen_paths[family]:
                raise ValueError(f"membership team identity is malformed for {family}")
            seen_paths[family].add(path)
            cleaned.append({
                "source_published_order": len(result[family]) + position,
                "source_competition_scope": str(league.get("competition_scope") or "top-flight"),
                "name": name,
                "article_title": title,
                "article_path": path,
            })
        result[family].extend(cleaned)
    return dict(result)


def _target_candidates(
    *, family: str, values: list[str], members: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Return target membership identities supported by exact/declared names."""

    result: dict[str, dict[str, Any]] = {}
    for team in members:
        keys = {identity_key(team["name"]), identity_key(team["article_title"])}
        if any(identity_key(value) in keys for value in values if value):
            result[team["article_path"]] = {**team, "identity_method": "safe-prefix-normalised-source-name"}
    for value in values:
        article_path = BASELINE_TARGET_ALIASES.get((family, identity_key(value)))
        if not article_path:
            continue
        team = next((item for item in members if item["article_path"] == article_path), None)
        if team is None:
            raise ValueError(f"documented target alias has no membership target: {family} {value}")
        result[article_path] = {**team, "identity_method": "documented-legacy-name-alias"}
    return result


def _tail_identity_values(row: Mapping[str, Any]) -> list[str]:
    values = [str(row.get("baseline_name") or "")]
    selector = row.get("source_selector")
    if isinstance(selector, Mapping):
        values.append(str(selector.get("club_name") or ""))
    return values


def _incumbent_matches(
    *, draft: Mapping[str, Any], memberships: Mapping[str, list[dict[str, Any]]]
) -> tuple[dict[str, dict[str, list[int]]], list[dict[str, Any]]]:
    proposals = draft.get("proposals")
    if not isinstance(proposals, list):
        raise ValueError("draft has no proposals")
    occupied: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    unmatched: list[dict[str, Any]] = []
    for row in proposals:
        if not isinstance(row, Mapping) or row.get("status") != "source-squad-ready":
            continue
        family = str(row.get("group") or "")
        if family not in memberships:
            continue
        values = [str(row.get("source_club_name") or ""), str(row.get("baseline_name") or "")]
        candidates = _target_candidates(family=family, values=values, members=memberships[family])
        carrier_id = int(row["carrier_id"])
        if len(candidates) == 1:
            occupied[family][next(iter(candidates))].append(carrier_id)
        else:
            unmatched.append({
                "carrier_id": carrier_id,
                "family": family,
                "baseline_name": row.get("baseline_name"),
                "source_club_name": row.get("source_club_name"),
                "status": "outside-target-membership" if not candidates else "ambiguous-target-membership",
                "candidate_membership_article_paths": sorted(candidates),
            })
    for family in occupied:
        for carrier_ids in occupied[family].values():
            carrier_ids.sort()
    return occupied, sorted(unmatched, key=lambda row: int(row["carrier_id"]))


def build_plan(
    *, draft: Mapping[str, Any], dispositions: Mapping[str, Any], membership: Mapping[str, Any]
) -> dict[str, Any]:
    if dispositions.get("schema_version") != DISPOSITION_SCHEMA:
        raise ValueError("disposition receipt has an unsupported schema")
    memberships = _membership_index(membership)
    occupied, incumbents_outside_membership = _incumbent_matches(draft=draft, memberships=memberships)
    incumbent_collisions = {
        family: {path: ids for path, ids in paths.items() if len(ids) > 1}
        for family, paths in occupied.items()
    }
    incumbent_collisions = {family: paths for family, paths in incumbent_collisions.items() if paths}

    tail_rows = [
        row for row in dispositions.get("dispositions", [])
        if isinstance(row, Mapping) and int(row.get("carrier_id", -1)) not in {8800, 8801, 9900, 9950, 9956}
    ]
    by_family: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    unclassified: list[Mapping[str, Any]] = []
    for row in tail_rows:
        family = str(row.get("group") or "")
        if family:
            by_family[family].append(row)
        else:
            unclassified.append(row)

    retained_baselines: dict[int, dict[str, Any]] = {}
    tail_collisions: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for family, rows in by_family.items():
        members = memberships.get(family)
        if members is None:
            continue
        for row in rows:
            carrier_id = int(row["carrier_id"])
            matches = _target_candidates(family=family, values=_tail_identity_values(row), members=members)
            if len(matches) == 1:
                path, target = next(iter(matches.items()))
                retained_baselines[carrier_id] = target
                occupied[family][path].append(carrier_id)
                tail_collisions[family][path].append(carrier_id)

    collisions = {
        family: {path: ids for path, ids in paths.items() if len(ids) > 1}
        for family, paths in occupied.items()
    }
    collisions = {family: paths for family, paths in collisions.items() if paths}

    assignments: list[dict[str, Any]] = []
    for family, rows in sorted(by_family.items()):
        rows.sort(key=lambda row: int(row["carrier_id"]))
        members = memberships.get(family)
        if members is None:
            assignments.extend({
                "carrier_id": int(row["carrier_id"]), "family": family,
                "baseline_name": row.get("baseline_name"),
                "fixed_roster_slot_count": int(row.get("fixed_roster_slot_count") or 0),
                "status": "requires-target-membership-source",
            } for row in rows)
            continue
        conflicted = family in collisions
        available = [team for team in members if team["article_path"] not in occupied.get(family, {})]
        cursor = 0
        for row in rows:
            base = {
                "carrier_id": int(row["carrier_id"]),
                "family": family,
                "baseline_name": row.get("baseline_name"),
                "fixed_roster_slot_count": int(row.get("fixed_roster_slot_count") or 0),
                "prior_release_disposition": row.get("release_disposition"),
            }
            retained_target = retained_baselines.get(int(row["carrier_id"]))
            partial_source = row.get("release_disposition") == "partial-sourced-prefix-preserved-native-tail"
            if partial_source and retained_target is not None:
                assignments.append({
                    **base,
                    "status": "retain-declared-target-club-needs-capacity-source",
                    "target_membership": retained_target,
                    "retained_source_selector": row.get("source_selector"),
                    "next_action": "capture a pinned 2015 squad for the already declared club and verify immutable capacity",
                })
            elif retained_target is not None:
                assignments.append({
                    **base,
                    "status": "retain-baseline-target-membership-awaiting-capacity-source",
                    "target_membership": retained_target,
                    "next_action": "capture an exact Transfermarkt saison_id/2015 squad and accept only if it fills the immutable carrier capacity",
                })
            elif conflicted:
                assignments.append({
                    **base,
                    "status": "blocked-by-existing-target-membership-collision",
                    "next_action": "resolve duplicate incumbent membership claim before choosing a replacement",
                })
            elif cursor >= len(available):
                assignments.append({
                    **base,
                    "status": "no-unclaimed-target-membership-club",
                    "next_action": "add a correctly scoped target-season membership source; do not reuse a club already bound to another carrier",
                })
            else:
                target = available[cursor]
                cursor += 1
                assignments.append({
                    **base,
                    "status": "proposed-target-membership-club-awaiting-capacity-source",
                    "proposed_target": target,
                    "selection_method": "next-unclaimed-club-in-published-target-season-membership-order",
                    **({"displaced_partial_source_selector": row.get("source_selector")}
                       if partial_source else {}),
                    "next_action": "capture an exact Transfermarkt saison_id/2015 squad and accept only if it fills the immutable carrier capacity",
                })

    for row in sorted(unclassified, key=lambda row: int(row["carrier_id"])):
        assignments.append({
            "carrier_id": int(row["carrier_id"]),
            "family": None,
            "baseline_name": row.get("baseline_name"),
            "fixed_roster_slot_count": int(row.get("fixed_roster_slot_count") or 0),
            "prior_release_disposition": row.get("release_disposition"),
            "status": "requires-carrier-family-classification",
            "next_action": "derive the fixed carrier's intended competition family before selecting any 2015 club",
        })

    assignments.sort(key=lambda row: int(row["carrier_id"]))
    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only; preserve existing fixed carriers and capacity; retain a partial source's declared club; "
            "for unrepresented legacy carriers, reserve a unique club from the published 2015 top-flight membership "
            "order; every reservation still requires an exact pinned 2015 squad with sufficient rows; no PM99 write"
        ),
        "summary": {
            "real_source_tail_carrier_count": len(tail_rows),
            "assignment_status_counts": dict(sorted(Counter(row["status"] for row in assignments).items())),
            "retained_baseline_target_membership_count": len(retained_baselines),
            "incumbent_outside_target_membership_count": len(incumbents_outside_membership),
            "existing_target_membership_collision_count": sum(len(paths) for paths in incumbent_collisions.values()),
            "target_membership_collision_count_after_tail_retention": sum(len(paths) for paths in collisions.values()),
        },
        "incumbent_outside_target_membership": incumbents_outside_membership,
        "existing_target_membership_collisions": collisions,
        "assignments": assignments,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--dispositions", required=True, type=Path)
    parser.add_argument("--membership", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    draft = _load(args.draft, label="draft")
    dispositions = _load(args.dispositions, label="dispositions")
    membership = _load(args.membership, label="membership")
    result = build_plan(draft=draft, dispositions=dispositions, membership=membership)
    result["sources"] = {
        "draft_sha256": sha256_file(args.draft),
        "dispositions_sha256": sha256_file(args.dispositions),
        "membership_sha256": sha256_file(args.membership),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
