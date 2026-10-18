#!/usr/bin/env python3
"""Run source, semantic, binary and runtime QA for preferred season builds.

This is deliberately stricter than ``pm99-season validate``.  The latter is a
fast availability/hash check; this command asks whether the recipe is
historically supported, internally plausible, present in the compiled files,
and demonstrated under the matching calendar executable.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts.audit_2015_world_release_semantics_v1 import (  # noqa: E402
    SemanticQaError,
    audit_kits,
    audit_managers,
    _manager_graph,
    _package_player_rows,
    _runtime_handling_indexes,
)
from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from app.ent_manager_profiles import parse_indexed_ent_manager_profile  # noqa: E402
from app.indexed_jug_identity import read_indexed_player_id  # noqa: E402
from app.indexed_jug_roles import read_indexed_native_roles  # noqa: E402
from app.models import PlayerRecord  # noqa: E402
from scripts import season_package_compiler_v2 as compiler  # noqa: E402
from scripts import season_player_identity_v1 as identity_lib  # noqa: E402
from scripts.build_2015_english92_release import (  # noqa: E402
    UNKNOWN_NATIONALITY,
    UNREPRESENTABLE_NATIONALITY,
    _country_code,
)
from scripts.pm99_season_play_v1 import game_path, validate as validate_candidate  # noqa: E402
from scripts import season_release_registry_v1 as release_registry  # noqa: E402
from scripts import season_pipeline_v2 as pipeline_v2  # noqa: E402
from scripts.season_package_v2 import PackageValidationError, validate_package  # noqa: E402


SCHEMA = "pm99-season-quality-qa-v1"
RATING_FIELDS = {
    "quality", "speed", "stamina", "aggression", "passing",
    "tackling", "heading", "shooting", "dribbling", "handling",
}
POSITIONS = {"G", "D", "M", "F"}
OUTFIELD_HANDLING_MAXIMUM = 20
SEASONS = release_registry.supported_seasons()
QA_IDENTITY_LIST_LIMIT = 100
EVIDENCE_SUFFIX = {
    "2000-01": "r2",
    "2001-02": "r3",
    "2002-03": "r3",
    # The original final1 artifact was a mixed retry: it selected Stockport
    # on one pass and retained an earlier stale line-up image on another.
    # Keep it as diagnostic history; bind QA only to the clean, hash-matched
    # capture made with the observed Stoke selector coordinates.
    "2004-05": "coordfix1",
    "2007-08": "retry2",
    "2013-14": "retry2",
}
RUNTIME_EVIDENCE_TAGS = {
    # This is a corrected, full 2004/05 calendar profile rather than the
    # legacy final1 tag.  Its executable hash is the current calendar-v1
    # runtime hash, and its screenshot is an unambiguous Stoke Line-Up.
    "2004-05": "post1999_2004_05_calendar-dayfix-817_20260909",
}


class QaError(ValueError):
    """A QA input cannot be resolved safely."""


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QaError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise QaError(f"{label} must be a JSON object: {path}")
    return value


def _normalise(value: object) -> str:
    text = str(value or "").translate(str.maketrans({
        "ı": "i", "İ": "I", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D",
        "ð": "d", "Ð": "D", "þ": "th", "Þ": "Th", "æ": "ae", "Æ": "Ae",
        "ø": "o", "Ø": "O", "ß": "ss",
    }))
    text = unicodedata.normalize("NFKD", text)
    return "".join(character.casefold() for character in text if character.isalnum() and not unicodedata.combining(character))


def _issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"code": code, "message": message}
    if details:
        row["details"] = details
    return row


def resolve_package(season: str) -> Path:
    return release_registry.load_preferred_release(season).package_path


def _latest_manager_layer(season: str) -> Path | None:
    root = ROOT / ".local/season-english-source-chain-v1" / season
    candidates = list(root.glob("*/english-manager-layer.json"))
    if not candidates:
        return None

    def key(path: Path) -> tuple[int, str]:
        match = re.fullmatch(r"r(\d+)", path.parent.name)
        return (int(match.group(1)) if match else -1, str(path))

    return max(candidates, key=key)


def _manager_reference_rows(season: str) -> tuple[list[dict[str, Any]], Path | None]:
    if season == "2015-16":
        path = ROOT / ".local/season-2015-16/2015-16-opening-manager-ledger.json"
    else:
        path = _latest_manager_layer(season)
    if path is None or not path.is_file():
        return [], path
    value = _read_object(path, "opening manager reference")
    rows = value.get("rows")
    if not isinstance(rows, list):
        raise QaError(f"opening manager reference has no rows: {path}")
    return [dict(row) for row in rows if isinstance(row, Mapping)], path


def verified_manager_plan_rows(season, package):
    """A proof label alone is not independent dated manager evidence."""
    artifact_id = 'historical-manager-plan-' + season
    descriptor = next((a for a in package.get('artifacts', []) if a.get('id') == artifact_id), None)
    if descriptor is None:
        return verified_reconciled_2015_manager_rows(season, package)
    release = release_registry.load_preferred_release(season)
    if descriptor.get('relative_path') != 'manager-plan.json':
        raise QaError('manager plan has an unexpected recipe-local path')
    path = release.package_path.parent / 'manager-plan.json'
    plan = _read_object(path, 'independent manager plan')
    if (hashlib.sha256(pipeline_v2.canonical_json_bytes(plan)).hexdigest() != descriptor['sha256'] or
            plan.get('schema_version') != 'pm99-historical-manager-plan-v1' or plan.get('season') != season):
        raise QaError('independent manager plan hash/schema/season differs')
    rows = {}; checked_sources = {}
    for row in plan['updates']:
        evidence = row['evidence']
        if (row['club_id'] in rows or row['after'] != evidence['manager'] or
                row['first_fixture_date'] != evidence['date'] or row['native_manager_owner_count'] != 1):
            raise QaError('manager dated identity/ownership proof is ambiguous')
        for source in evidence['raw_sources']:
            source_path = ROOT / source['path']
            if source_path not in checked_sources: checked_sources[source_path] = _sha256(source_path)
            if checked_sources[source_path] != source['sha256']:
                raise QaError('independent manager original source bytes changed')
        rows[row['club_id']] = row
    return rows, path


def verified_reconciled_2015_manager_rows(season, package):
    """Recognise the dated legacy repair only after its native graph is bound.

    This does not pretend that old manager-history receipts are new first-match
    reparses. All their original input hashes and actual native owners are checked.
    """
    from scripts import reconcile_2015_recipe_manager_graph_v1 as reconciliation
    descriptor = next((a for a in package.get('artifacts', [])
                       if a.get('id') == reconciliation.ARTIFACT), None)
    if season != '2015-16' or descriptor is None:
        return {}, None
    release = release_registry.load_preferred_release(season)
    if descriptor.get('relative_path') != 'manager-graph-reconciliation.json':
        raise QaError('2015 reconciled manager evidence has an unexpected path')
    path = release.package_path.parent / descriptor['relative_path']
    document = _read_object(path, 'reconciled 2015 manager graph')
    if (hashlib.sha256(pipeline_v2.canonical_json_bytes(document)).hexdigest() != descriptor['sha256']
            or document.get('schema_version') != reconciliation.SCHEMA or document.get('season') != season):
        raise QaError('2015 reconciled manager graph hash/schema differs')
    source_plan, bindings = reconciliation.checked_inputs(release)
    if document.get('source_bindings') != bindings:
        raise QaError('2015 reconciled manager graph source bindings changed')
    holders, names = _manager_graph(eq_path=release.game_path / 'DBDAT/EQ98030.FDI',
                                   ent_path=release.game_path / 'DBDAT/ENT98030.FDI')
    aliases = reconciliation.recipe_native_aliases(release, package)
    aligned, changes = reconciliation.align_package(package, holders, names, source_plan, native_aliases=aliases)
    targets = [row for row in source_plan['targets'] if row['scope'] == 'foreign']
    if (changes or aligned['managers'] != package['managers']
            or document.get('dated_foreign_managers') != targets):
        raise QaError('2015 reconciled declarations differ from dated native graph')
    clubs = {club['carrier_id']: club for club in package['clubs']}
    rows = {clubs[row['team_carrier_id']]['id']: {
        'carrier_id': row['manager_carrier_id'], 'club_carrier_id': row['team_carrier_id'],
        'after': row['manager_name'], 'artifact_id': reconciliation.ARTIFACT,
        'source_status': row['source_status'], 'source_scope': 'retained dated manager-history repair'}
        for row in targets}
    for row in source_plan['preserved_non_club_links']:
        rows[clubs[row['team_carrier_id']]['id']] = {
            'out_of_scope_non_club': True, 'club_carrier_id': row['team_carrier_id'],
            'carrier_id': row['manager_carrier_id']}
    return rows, path


def audit_manager_sources(season: str, package: Mapping[str, Any]) -> dict[str, Any]:
    rows, path = _manager_reference_rows(season)
    package_managers = {
        str(row.get("id") or ""): row for row in package.get("managers") or [] if isinstance(row, Mapping)
    }
    package_clubs = [row for row in package.get("clubs") or [] if isinstance(row, Mapping)]
    if season == "2015-16":
        manifest_path = ROOT / ".local/season-2015-16/english92-2015-16-build36-native-no-photo/2015-16-english92-manifest.json"
        manifest = _read_object(manifest_path, "2015/16 English build manifest")
        managers = {
            str(row.get("record_id") or ""): {"name": row.get("surname")}
            for row in manifest.get("managers") or [] if isinstance(row, Mapping)
        }
        clubs = [
            {"id": f"english-club-{row.get('record_id')}", "name": row.get("club"), "manager_id": str(row.get("manager_record_id") or "")}
            for row in manifest.get("teams") or [] if isinstance(row, Mapping)
        ]
    else:
        managers = package_managers
        clubs = package_clubs
    clubs_by_name: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for club in clubs:
        clubs_by_name[_normalise(club.get("name"))].append(club)
    matched: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    referenced_club_ids: set[str] = set()
    for reference_row in rows:
        club_name = str(reference_row.get("club") or "")
        expected = str(reference_row.get("manager_name") or "").strip()
        candidates = clubs_by_name.get(_normalise(club_name), [])
        english_candidates = [
            club for club in candidates
            if str(club.get("id") or "").startswith("english-club-")
        ]
        if len(english_candidates) == 1:
            candidates = english_candidates
        if len(candidates) != 1:
            missing.append({
                "club": club_name,
                "expected_manager": expected,
                "reason": "club absent or ambiguous in package",
                "package_club_match_count": len(candidates),
            })
            continue
        club = candidates[0]
        referenced_club_ids.add(str(club.get("id") or ""))
        manager = managers.get(str(club.get("manager_id") or ""), {})
        actual = str(manager.get("name") or "")
        row = {"club": club_name, "expected_manager": expected, "package_manager": actual}
        if _normalise(expected) != _normalise(actual):
            mismatches.append(row)
        else:
            matched.append(row)

    foreign = package_clubs if season == "2015-16" else [
        row for row in package_clubs if str(row.get("id") or "") not in referenced_club_ids
    ]
    independently_sourced_foreign = 0
    provisional_foreign = 0
    out_of_scope_non_clubs = 0
    independently_verified, manager_plan_path = verified_manager_plan_rows(season, package)
    for club in foreign:
        manager = package_managers.get(str(club.get("manager_id") or ""), {})
        proof = manager.get("proof") if isinstance(manager, Mapping) else None
        artifact = str(proof.get("artifact_id") or "") if isinstance(proof, Mapping) else ""
        policy = str(manager.get("policy") or "") if isinstance(manager, Mapping) else ""
        source = independently_verified.get(club['id'])
        if (source and source.get('out_of_scope_non_club') is True and policy == 'preserve-existing-mode1'
                and club.get('carrier_id') == source['club_carrier_id']
                and manager.get('carrier_id') == source['carrier_id']):
            out_of_scope_non_clubs += 1
            continue
        if (policy == 'write' and source and artifact == source.get('artifact_id', 'historical-manager-plan-' + season) and
                manager.get('carrier_id') == source['carrier_id'] and club.get('carrier_id') == source['club_carrier_id'] and
                _normalise(manager.get('name')) == _normalise(source['after'])):
            independently_sourced_foreign += 1
        else:
            provisional_foreign += 1
    return {
        "reference_path": str(path.relative_to(ROOT)) if path is not None and path.exists() else None,
        "english_club_count": len(referenced_club_ids),
        "reference_row_count": len(rows),
        "matched_count": len(matched),
        "mismatch_count": len(mismatches),
        "missing_reference_count": len(missing),
        "mismatches": mismatches[:50],
        "missing_references": missing[:50],
        "foreign_club_count": len(foreign) - out_of_scope_non_clubs,
        "foreign_carrier_count": len(foreign),
        "out_of_scope_non_club_manager_links": out_of_scope_non_clubs,
        "independently_sourced_foreign_manager_count": independently_sourced_foreign,
        "provisional_foreign_manager_count": provisional_foreign,
        "independent_foreign_manager_plan_path": str(manager_plan_path.relative_to(ROOT)) if manager_plan_path else None,
        "independent_manager_policy": "Original hash-bound dated match or retained dated manager-history repair evidence and exact club/manager identity; artifact labels alone do not certify history",
    }


def audit_recipe(package: Mapping[str, Any], *, season: str) -> dict[str, Any]:
    start_year = int(season[:4])
    snapshot = dt.date(start_year, 8, 1)
    clubs = {str(row.get("id") or ""): row for row in package.get("clubs") or [] if isinstance(row, Mapping)}
    players = {str(row.get("id") or ""): row for row in package.get("players") or [] if isinstance(row, Mapping)}
    rating_failures: list[dict[str, Any]] = []
    date_failures: list[dict[str, Any]] = []
    secondary_fact_failures: list[dict[str, Any]] = []
    missing_secondary = Counter()
    provenance = Counter()
    position_counts = Counter()
    editorial_count = 0
    source_rating_count = 0
    club_qualities: dict[str, list[int]] = defaultdict(list)
    for player_id, player in players.items():
        facts = player.get("facts") if isinstance(player.get("facts"), Mapping) else {}
        position = facts.get("primary_position")
        position_text = str(position) if isinstance(position, str) else ""
        if position_text in POSITIONS:
            position_counts[position_text] += 1
        ratings = player.get("ratings") if isinstance(player.get("ratings"), Mapping) else {}
        values = ratings.get("values") if isinstance(ratings.get("values"), Mapping) else {}
        method = str((ratings.get("provenance") or {}).get("method") or "") if isinstance(ratings.get("provenance"), Mapping) else ""
        provenance[method or "missing"] += 1
        if "editorial" in method.casefold() or "deterministic" in method.casefold():
            editorial_count += 1
        else:
            source_rating_count += 1
        # PM99 stores visible ratings on the full byte range used by this
        # package contract.  Zero is a valid inactive/placeholder value and
        # 100 is representable; semantic position checks below catch values
        # that are mechanically valid but implausible in context.
        bad_fields = {
            field: values.get(field) for field in RATING_FIELDS
            if not isinstance(values.get(field), int) or isinstance(values.get(field), bool) or not 0 <= int(values[field]) <= 100
        }
        if bad_fields:
            rating_failures.append({"player_id": player_id, "name": player.get("name"), "reason": "missing-or-out-of-range-rating", "fields": bad_fields})
        handling = values.get("handling")
        if position_text in {"D", "M", "F"} and isinstance(handling, int) and handling > OUTFIELD_HANDLING_MAXIMUM:
            rating_failures.append({"player_id": player_id, "name": player.get("name"), "club_id": player.get("club_id"), "reason": "outfield-handling-above-20", "handling": handling})
        if position_text == "G" and isinstance(handling, int) and handling < 35:
            rating_failures.append({"player_id": player_id, "name": player.get("name"), "club_id": player.get("club_id"), "reason": "goalkeeper-handling-below-35", "handling": handling})
        quality = values.get("quality")
        if isinstance(quality, int):
            club_qualities[str(player.get("club_id") or "")].append(quality)

        birth = facts.get("birth_date")
        if isinstance(birth, str):
            try:
                born = dt.date.fromisoformat(birth)
                age = snapshot.year - born.year - ((snapshot.month, snapshot.day) < (born.month, born.day))
                if born > snapshot or age < 14 or age > 55:
                    date_failures.append({"player_id": player_id, "name": player.get("name"), "birth_date": birth, "age_at_snapshot": age})
            except ValueError:
                date_failures.append({"player_id": player_id, "name": player.get("name"), "birth_date": birth, "reason": "invalid-date"})
        else:
            missing_secondary["birth_date"] += 1
        for field, low, high in (("height_cm", 140, 220), ("weight_kg", 40, 130)):
            value = facts.get(field)
            if value is None or isinstance(value, Mapping):
                missing_secondary[field] += 1
            elif not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
                secondary_fact_failures.append({"player_id": player_id, "name": player.get("name"), "field": field, "value": value})
        nationality = facts.get("nationality")
        if nationality is None or isinstance(nationality, Mapping):
            missing_secondary["nationality"] += 1

    lineup_failures: list[dict[str, Any]] = []
    objective_strength_by_division: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for club_id, club in clubs.items():
        opening = club.get("opening")
        if not isinstance(opening, Mapping) or opening.get("policy") == "preserve-existing-mode1":
            continue
        eleven = opening.get("starting_xi_player_ids")
        if not isinstance(eleven, list) or len(eleven) != 11:
            continue
        positions = []
        for player_id in eleven:
            facts = players.get(str(player_id), {}).get("facts")
            positions.append(facts.get("primary_position") if isinstance(facts, Mapping) else None)
        if positions.count("G") != 1:
            lineup_failures.append({"club_id": club_id, "club": club.get("name"), "reason": "opening-xi-needs-one-goalkeeper", "positions": positions})
        # PM99 derives the start-screen objective from the squad profile.  A
        # full English division with effectively one opening-XI quality level
        # is therefore a release-blocking input defect, even though every
        # individual rating remains mechanically in range.
        if str(club_id).startswith("english-club-") and len(eleven) == 11:
            qualities = [
                players.get(str(player_id), {}).get("ratings", {}).get("values", {}).get("quality")
                for player_id in eleven
            ]
            if all(isinstance(value, int) and not isinstance(value, bool) for value in qualities):
                objective_strength_by_division[str(club.get("division") or "English league")].append({
                    "club_id": club_id,
                    "club": club.get("name"),
                    "opening_xi_quality_mean": round(sum(int(value) for value in qualities) / len(qualities), 2),
                })

    objective_input_failures: list[dict[str, Any]] = []
    for division, rows in sorted(objective_strength_by_division.items()):
        # A small incomplete import should not be judged as a whole league.
        # The normal English divisions have 20 or 24 clubs, and 12 is enough
        # to distinguish a real league profile from a few isolated records.
        if len(rows) < 12:
            continue
        values = [float(row["opening_xi_quality_mean"]) for row in rows]
        spread = max(values) - min(values)
        # The former division-only model produced a spread of only a few
        # points from person-level separators.  Eight points is deliberately
        # well below the prior-finish policy's expected top-to-bottom spread.
        if spread < 8:
            objective_input_failures.append({
                "division": division,
                "club_count": len(rows),
                "minimum_opening_xi_quality_mean": min(values),
                "maximum_opening_xi_quality_mean": max(values),
                "spread": round(spread, 2),
                "reason": "opening-xi-strength-profile-too-flat-for-pm99-objectives",
                "clubs": rows,
            })

    distribution_warnings: list[dict[str, Any]] = []
    for club_id, qualities in club_qualities.items():
        if len(qualities) >= 16 and max(qualities) - min(qualities) <= 2:
            distribution_warnings.append({"club_id": club_id, "club": clubs.get(club_id, {}).get("name"), "reason": "implausibly-flat-quality-distribution", "minimum": min(qualities), "maximum": max(qualities), "player_count": len(qualities)})
        if sum(value >= 95 for value in qualities) > 3:
            distribution_warnings.append({"club_id": club_id, "club": clubs.get(club_id, {}).get("name"), "reason": "more-than-three-players-at-quality-95-plus", "count": sum(value >= 95 for value in qualities)})

    return {
        "club_count": len(clubs),
        "player_count": len(players),
        "position_counts": dict(sorted(position_counts.items())),
        "rating_provenance_counts": dict(sorted(provenance.items())),
        "editorial_rating_count": editorial_count,
        "source_rating_count": source_rating_count,
        "rating_failure_count": len(rating_failures),
        "rating_failure_reason_counts": dict(sorted(Counter(row["reason"] for row in rating_failures).items())),
        "rating_failures": rating_failures[:100],
        "date_failure_count": len(date_failures),
        "date_failures": date_failures[:100],
        "secondary_fact_failure_count": len(secondary_fact_failures),
        "secondary_fact_failures": secondary_fact_failures[:100],
        "missing_secondary_fact_counts": dict(sorted(missing_secondary.items())),
        "lineup_failure_count": len(lineup_failures),
        "lineup_failures": lineup_failures[:100],
        "objective_input_failure_count": len(objective_input_failures),
        "objective_input_failures": objective_input_failures[:100],
        "distribution_warning_count": len(distribution_warnings),
        "distribution_warnings": distribution_warnings[:100],
    }


def audit_player_identities(package: Mapping[str, Any]) -> dict[str, Any]:
    """Provider-ID and name/birth-date candidate screening of recipe players."""

    audit = identity_lib.audit_entries(
        identity_lib.entries_from_package(row for row in package.get("players") or [] if isinstance(row, Mapping))
    )
    # ``counts`` keeps the exact totals; the stored report lists are bounded.
    audit["lists_truncated_to"] = QA_IDENTITY_LIST_LIMIT
    for name in audit["counts"]:
        audit[name] = audit[name][:QA_IDENTITY_LIST_LIMIT]
    return audit


def player_identity_issues(audit: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map identity findings to (blockers, warnings).

    Blockers are only facts that make a recipe internally inconsistent: a
    malformed identity, or one provider ID held by several players/described
    inconsistently.  Absent IDs, unscreenable rows and name/birth-date
    candidates are warnings (the strict package validator already gates the
    latter for strict seasons).  None of these is a historical verdict.
    """

    coverage, counts = audit["coverage"], audit["counts"]
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if counts["malformed_identities"]:
        blockers.append(_issue("player-identity-metadata-malformed", "player source identities are malformed",
                               count=counts["malformed_identities"], samples=audit["malformed_identities"][:20]))
    if counts["same_provider_id_candidates"]:
        blockers.append(_issue("player-provider-id-repeated",
                               "one provider player ID is held by several recipe players; this is an unreviewed duplicate candidate, not a resolved historical finding",
                               count=counts["same_provider_id_candidates"], samples=audit["same_provider_id_candidates"][:20]))
    if counts["metadata_conflicts"]:
        blockers.append(_issue("player-provider-id-metadata-conflict",
                               "one provider player ID is described with conflicting names or birth dates",
                               count=counts["metadata_conflicts"], samples=audit["metadata_conflicts"][:20]))
    if coverage["missing_provider_identity"]:
        warnings.append(_issue("player-provider-identity-missing",
                               "players without a provider ID are screened by name and birth date only; duplicate-free status is not verified",
                               count=coverage["missing_provider_identity"], coverage=coverage))
    if coverage["missing_identity_and_birth_date"]:
        warnings.append(_issue("player-duplicate-screening-insufficient-facts",
                               "players with neither a provider ID nor a birth date cannot be screened for duplicates",
                               count=coverage["missing_identity_and_birth_date"],
                               samples=audit["insufficient_identity_facts"][:20]))
    if counts["name_birth_date_candidates"]:
        warnings.append(_issue("player-name-birth-date-candidates",
                               "players share a normalised name and birth date without proof of distinct provider IDs",
                               count=counts["name_birth_date_candidates"], samples=audit["name_birth_date_candidates"][:20]))
    if counts["distinct_provider_id_namesakes"]:
        warnings.append(_issue("player-distinct-provider-id-namesakes",
                               "same-name same-birth-date players have distinct provider IDs; strict package validation still requires explicit review",
                               count=counts["distinct_provider_id_namesakes"], samples=audit["distinct_provider_id_namesakes"][:20]))
    return blockers, warnings


def audit_compiled_managers(package: Mapping[str, Any], *, game: Path, season: str, package_path: Path | None = None) -> dict[str, Any]:
    """Check ownership and aliases in effective recipes, not old input snapshots."""
    result = _audit_compiled_manager_ownership(package, game=game, season=season, package_path=package_path)
    declarations = [m for m in package.get('managers', []) if m.get('native_names')]
    superseded_input_aliases = 0
    for artifact in package.get('artifacts', []):
        if not artifact['id'].startswith('english-contextual-package-'):
            continue
        base = package_path or release_registry.load_preferred_release(season).package_path
        relative = Path(artifact['relative_path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise QaError('unsafe English manager alias recipe path')
        path = base.parent / relative
        if _sha256(path) != artifact['sha256']:
            raise QaError('English manager alias recipe hash changed')
        historical = [m for m in _read_object(path, 'English manager alias recipe')['managers'] if m.get('native_names')]
        # Only 2015's English contextual artifact is an active separate layer.
        # Other seasons' artifacts are retained compiler/source inputs: the
        # current full main recipe already owns these same native carriers.
        # Comparing both would reject a source-proved whole-club replacement
        # against the old club/manager it deliberately retired.
        if artifact['id'] == 'english-contextual-package-2015-16' and season == '2015-16':
            declarations.extend(historical)
        else:
            current_carriers = {m['carrier_id'] for m in package.get('managers', [])}
            if any(m['carrier_id'] not in current_carriers for m in historical):
                raise QaError('historical English input contains a manager absent from the current recipe')
            superseded_input_aliases += len(historical)
    failures = []
    if declarations:
        data = (game / 'DBDAT/ENT98030.FDI').read_bytes()
        entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(data).entries}
        for manager in declarations:
            carrier = manager['carrier_id']
            entry = entries.get(carrier)
            profile = parse_indexed_ent_manager_profile(data[entry.payload_offset:entry.payload_offset + entry.payload_length], record_id=carrier) if entry else None
            alias = manager['native_names']
            if profile is None or (profile.surname, profile.display_name) != (alias['surname'], alias['display_name']):
                failures.append({'manager_record_id': carrier, 'reason': 'short/full native alias readback failed',
                                 'expected_native_names': alias, 'canonical_manager_name': manager['name']})
    return {**result, 'native_alias_checked_count': len(declarations), 'native_alias_failure_count': len(failures),
            'historical_input_aliases_not_current_declarations': superseded_input_aliases,
            'failure_count': result['failure_count'] + len(failures), 'failures': result['failures'] + failures}


def _audit_compiled_manager_ownership(package: Mapping[str, Any], *, game: Path, season: str, package_path: Path | None = None) -> dict[str, Any]:
    """Audit manager ownership exactly, tolerating storage transliteration only."""
    raw = audit_managers(
        package=package,
        eq_path=game / "DBDAT/EQ98030.FDI",
        ent_path=game / "DBDAT/ENT98030.FDI",
    )
    failures = []
    for row in raw["failures"]:
        expected_ids = [int(club["carrier_id"]) for club in row["expected_clubs"]]
        actual_ids = [int(club["carrier_id"]) for club in row["actual_active_clubs"]]
        owner_ok = actual_ids == expected_ids and len(actual_ids) == 1
        name_ok = _normalise(row.get("stored_manager_name")) == _normalise(row.get("manager_name"))
        if not (owner_ok and name_ok):
            failures.append({**row, "exclusive_correct_owner": owner_ok, "stored_name_matches_package": name_ok})
    result = {
        **raw,
        "exclusive_correct_owner_count": raw["written_manager_count"] - sum(not row["exclusive_correct_owner"] for row in failures),
        "name_match_count": raw["written_manager_count"] - sum(not row["stored_name_matches_package"] for row in failures),
        "failure_count": len(failures),
        "failures": failures,
        "comparison_policy": "exact carrier ownership; accent-insensitive manager name",
    }
    if season != "2015-16":
        return result

    manifest_path = ROOT / ".local/season-2015-16/english92-2015-16-build36-native-no-photo/2015-16-english92-manifest.json"
    manifest = _read_object(manifest_path, "2015/16 English build manifest")
    holders, stored_names = _manager_graph(
        eq_path=game / "DBDAT/EQ98030.FDI",
        ent_path=game / "DBDAT/ENT98030.FDI",
    )
    club_to_manager: dict[int, int] = {}
    for manager_id, owned_clubs in holders.items():
        for club in owned_clubs:
            club_to_manager[int(club["carrier_id"])] = int(manager_id)
    english_failures = []
    english_rows = []
    native_aliases = {}
    english_by_club = {}
    dated_graph_bound = False
    dated_english = {}
    if any(a.get('id') == 'reconciled-native-manager-graph-2015' for a in package.get('artifacts', [])):
        from types import SimpleNamespace
        from scripts.reconcile_2015_recipe_manager_graph_v1 import checked_inputs
        base = package_path or release_registry.load_preferred_release(season).package_path
        plan, _ = checked_inputs(SimpleNamespace(game_path=game, package_path=base))
        dated_english = {row['team_carrier_id']: row for row in plan['targets'] if row['scope'] == 'english'}
        dated_graph_bound = len(dated_english) == 92
    for artifact in package.get('artifacts', []):
        if artifact['id'].startswith('english-contextual-package-'):
            base = package_path or release_registry.load_preferred_release(season).package_path
            relative = Path(artifact['relative_path'])
            if relative.is_absolute() or '..' in relative.parts:
                raise QaError('unsafe English manager alias recipe path')
            english_path = base.parent / relative
            if _sha256(english_path) != artifact['sha256']:
                raise QaError('English manager alias recipe hash changed')
            english = _read_object(english_path, 'English manager alias recipe')
            native_aliases = {m['carrier_id']: m for m in english['managers'] if m.get('native_names')}
            english_managers = {m['id']: m for m in english['managers']}
            english_by_club = {c['carrier_id']: english_managers[c['manager_id']] for c in english['clubs']}
    for team in manifest.get("teams") or []:
        if not isinstance(team, Mapping):
            continue
        club_id = int(team.get("record_id") or 0)
        expected_manager_id = int(team.get("manager_record_id") or 0)
        expected_name = str(team.get("manager_name") or "")
        if club_id in dated_english:
            reference = dated_english[club_id]
            if _normalise(reference['manager_name']) != _normalise(expected_name):
                raise QaError('dated English manager differs from opening manifest')
            expected_manager_id = reference['manager_carrier_id']
        declaration = english_by_club.get(club_id) or native_aliases.get(expected_manager_id)
        expected_native_name = expected_name
        if declaration is not None and declaration.get('native_names'):
            if _normalise(declaration['name']) != _normalise(expected_name):
                raise QaError('English display alias names another canonical manager')
            expected_native_name = declaration['native_names']['display_name']
            expected_manager_id = declaration['carrier_id']
        actual_manager_id = club_to_manager.get(club_id)
        actual_name = stored_names.get(actual_manager_id) if actual_manager_id is not None else None
        row = {
            "club": team.get("club"),
            "club_record_id": club_id,
            "expected_manager_name": expected_name,
            "expected_native_manager_name": expected_native_name,
            "expected_manager_record_id": expected_manager_id,
            "actual_manager_name": actual_name,
            "actual_manager_record_id": actual_manager_id,
            "pass": actual_manager_id == expected_manager_id and _normalise(actual_name) == _normalise(expected_native_name),
        }
        english_rows.append(row)
        if not row["pass"]:
            english_failures.append(row)
    graph_receipt_path = ROOT / ".local/operations/2015-16/manager-facts-manager-graph-application-v1-r2-20260913.json"
    graph_receipt = _read_object(graph_receipt_path, "2015 manager-graph transform receipt")
    contract = graph_receipt.get("byte_contract")
    graph_receipt_bound = (
        graph_receipt.get("state") == "applied-to-candidate-game"
        and graph_receipt.get("readback_failure_count") == 0
        and isinstance(contract, Mapping)
        and contract.get("eq_after_sha256") == _sha256(game / "DBDAT/EQ98030.FDI")
        and contract.get("ent_after_sha256") == _sha256(game / "DBDAT/ENT98030.FDI")
        # Manager ownership lives in EQ/ENT. A separately proved player-role
        # edit must not invalidate the unchanged manager graph's hashes.
        and all(_normalise(row['actual_manager_name']) == _normalise(row['expected_native_manager_name'])
                for row in english_rows)
    )
    if graph_receipt_bound or (dated_graph_bound and all(row['pass'] for row in english_rows)):
        return {
            **result,
            "failure_count": 0,
            "failures": [],
            "english_reference_count": len(english_rows),
            "foreign_collision_failure_count": 0,
            "manager_graph_transform_receipt": str(graph_receipt_path.relative_to(ROOT)),
            "manager_graph_transform_receipt_sha256": _sha256(graph_receipt_path),
            "manager_graph_readback_failure_count": 0,
            "manager_graph_scope": "Original dated source hashes plus exact exclusive native manager edges/names; unrelated tactics are not manager changes",
            "legacy_carrier_id_difference_count": len(english_failures),
            "comparison_policy": "hash-bound final manager graph receipt; accent-insensitive visible-name readback",
        }
    return {
        **result,
        "failure_count": len(english_failures),
        "failures": english_failures,
        "english_reference_count": len(english_rows),
        "foreign_collision_failure_count": raw["failure_count"],
        "comparison_policy": "2015 English manifest manager/club carrier link and accent-insensitive name",
    }


def audit_compiled_handling(package: Mapping[str, Any], *, game: Path) -> dict[str, Any]:
    """Read Handling back by stable carrier ID, with unique-name fallback."""
    rows = list(_package_player_rows(package))
    claims: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        claims[int(row["record_id"])].append(row)
    collisions = [
        {"record_id": record_id, "claims": owned}
        for record_id, owned in sorted(claims.items()) if len(owned) > 1
    ]
    runtime_by_record, runtime_by_name = _runtime_handling_indexes(game / "DBDAT/JUG98030.FDI", rows)
    failures = []
    unverified_position_count = 0
    for row in rows:
        if row["position"] not in POSITIONS:
            # Whole-record preservation rows intentionally make no semantic
            # position or rating claim.  Their binary invariance is covered
            # by the clean-base audit; treating their placeholder rating map
            # as a requested write creates false readback failures.
            unverified_position_count += 1
            continue
        record_id = int(row["record_id"])
        observed = runtime_by_record.get(record_id)
        observed_record_id = record_id if observed is not None else None
        resolution = "carrier-id"
        if observed is None:
            candidates = runtime_by_name.get(_normalise(row["name"]), [])
            if len(candidates) == 1:
                observed = int(candidates[0]["handling"])
                observed_record_id = int(candidates[0]["record_id"])
                resolution = "unique-normalised-name"
        is_outfield = row["position"] in {"D", "M", "F"}
        semantic_ok = not is_outfield or 1 <= int(row["handling"]) <= OUTFIELD_HANDLING_MAXIMUM
        runtime_semantic_ok = not is_outfield or (
            observed is not None and 1 <= observed <= OUTFIELD_HANDLING_MAXIMUM
        )
        readback_ok = observed == int(row["handling"])
        if not (semantic_ok and runtime_semantic_ok and readback_ok):
            failures.append({
                **row,
                "runtime_record_id": observed_record_id,
                "runtime_handling": observed,
                "resolution": resolution,
                "outfield_handling_in_range": semantic_ok,
                "runtime_outfield_handling_in_range": runtime_semantic_ok,
                "runtime_readback_matches": readback_ok,
            })
    return {
        "player_count": len(rows),
        "unique_player_record_count": len(claims),
        "outfield_player_count": sum(row["position"] in {"D", "M", "F"} for row in rows),
        "unverified_position_player_count": unverified_position_count,
        "outfield_handling_maximum": OUTFIELD_HANDLING_MAXIMUM,
        "ownership_collision_count": len(collisions),
        "semantic_or_readback_failure_count": len(failures),
        "failure_count": len(collisions) + len(failures),
        "ownership_collisions": collisions,
        "failures": failures,
        "comparison_policy": "carrier-id first; unique normalised name only when carrier is absent",
    }


def _runtime_nationality_offset(payload: bytes, *, carrier: int, declared_family: str) -> int:
    """Locate the proven compact-player country byte.

    ``dd6361`` has more than one name-adjacent byte sequence that resembles
    the compact block.  Its visible country is instead the parser-backed
    ``PlayerRecord.nationality`` field.  Returning an offset for that family
    made the QA read biography bytes as a country code, producing false
    nationality failures despite a correct compiler write.
    """
    family = payload[2:5]
    if declared_family == "dd6360" and family == b"\xdd\x63\x60":
        offset = int(compiler._native_dd6360_role_start(payload)) + 8
    elif declared_family == "dd6361" and family == b"\xdd\x63\x61":
        raise QaError(
            f"player carrier {carrier} uses dd6361; read nationality through PlayerRecord"
        )
    else:
        raise QaError(
            f"player carrier {carrier} has {family.hex()} but package declares {declared_family}"
        )
    if offset < 0 or offset >= len(payload):
        raise QaError(f"player carrier {carrier} nationality offset is outside its JUG payload")
    return offset


def audit_compiled_nationalities(package: Mapping[str, Any], *, game: Path) -> dict[str, Any]:
    """Read every declared nationality back by fixed JUG carrier ID.

    ``XXX`` is valid only where the package explicitly says it is unknown or
    PM99's fixed country table has no native row.  A valid, representable
    source code must match the numeric country byte in the compiled game.
    """
    jugadores = package.get("players")
    if not isinstance(jugadores, list):
        raise QaError("package has no players list for nationality QA")
    jug_path = game / "DBDAT/JUG98030.FDI"
    textos_path = game / "DBDAT/TEXTOS.PKF"
    country_codes = compiler._extract_country_codes_from_textos(textos_path)
    xxx_code = country_codes.get("XXX")
    if not isinstance(xxx_code, int):
        raise QaError("PM99 TEXTOS table has no numeric XXX country code")
    jug_data = jug_path.read_bytes()
    payloads = {
        int(entry.record_id): entry.decode_payload(jug_data)
        for entry in IndexedFDIFile.from_bytes(jug_data).entries
    }
    failures: list[dict[str, Any]] = []
    unrepresentable: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    preserved_count = 0
    checked_count = 0
    seen_carriers: set[int] = set()
    for player in jugadores:
        if not isinstance(player, Mapping):
            raise QaError("package player list contains a non-object row")
        facts = player.get("facts")
        if not isinstance(facts, Mapping):
            raise QaError(f"player {player.get('id')!r} has no facts object")
        source = facts.get("nationality")
        if isinstance(source, Mapping):
            if source.get("policy") != "preserve-existing-mode1":
                raise QaError(f"player {player.get('id')!r} has unsupported nationality policy")
            preserved_count += 1
            continue
        if not isinstance(source, str):
            raise QaError(f"player {player.get('id')!r} nationality is not text")
        source_code = source.strip().upper()
        common = {
            "player_id": str(player.get("id") or ""),
            "name": str(player.get("name") or ""),
            "carrier_id": int(player.get("carrier_id") or 0),
            "source_nationality": source_code,
        }
        if source_code in UNKNOWN_NATIONALITY:
            unknown.append(common)
            continue
        if source_code in UNREPRESENTABLE_NATIONALITY:
            unrepresentable.append(common)
            continue
        expected = _country_code(source_code, dict(country_codes))
        if expected == xxx_code:
            raise QaError(f"representable source nationality {source_code!r} resolves to XXX")
        carrier = common["carrier_id"]
        if carrier <= 0 or carrier in seen_carriers:
            raise QaError(f"package has duplicate or invalid nationality carrier {carrier}")
        seen_carriers.add(carrier)
        payload = payloads.get(carrier)
        if payload is None:
            failures.append({**common, "reason": "carrier-absent-from-runtime-jug"})
            continue
        family = str(player.get("carrier_family") or "")
        if family == "dd6361":
            # The generic player codec validates the indexed metadata layout
            # and selects the actual visible nationality field.  Do not infer
            # an offset from a variable-length biography payload.
            actual_value = getattr(PlayerRecord.from_bytes(payload, 0), "nationality", None)
            if not isinstance(actual_value, int) or isinstance(actual_value, bool):
                raise QaError(f"player carrier {carrier} has no parser-backed dd6361 nationality")
            actual = int(actual_value)
        else:
            offset = _runtime_nationality_offset(
                payload, carrier=carrier, declared_family=family,
            )
            actual = int(payload[offset] ^ 0x61)
        checked_count += 1
        if actual != expected:
            failures.append({
                **common,
                "expected_country_code": expected,
                "runtime_country_code": actual,
                "runtime_is_xxx": actual == xxx_code,
            })
    return {
        "checked_representable_player_count": checked_count,
        "failure_count": len(failures),
        "failures": failures,
        "unrepresentable_nationality_count": len(unrepresentable),
        "unrepresentable_nationalities": unrepresentable,
        "explicit_unknown_nationality_count": len(unknown),
        "preserved_nationality_field_count": preserved_count,
        "comparison_policy": (
            "fixed carrier; dd6360 country byte or parser-backed dd6361 PlayerRecord nationality; "
            "source code translated only through the PM99 TEXTOS country table"
        ),
    }


def _runtime_evidence_path(season: str) -> Path:
    registered = release_registry.load_preferred_release(season).runtime_evidence_path
    if registered is not None:
        return registered
    tag = RUNTIME_EVIDENCE_TAGS.get(season)
    if tag is None:
        key = season.replace("-", "_")
        suffix = EVIDENCE_SUFFIX.get(season, "final1")
        tag = f"post1999_{key}_stoke_lineup_20260907_{suffix}"
    return ROOT / "upstream/pm99-runner/docs/artifacts/pm99_runner" / tag


def audit_runtime(season: str) -> dict[str, Any]:
    release = release_registry.load_preferred_release(season)
    root = _runtime_evidence_path(season)
    summary_path = root / "summary.json"
    if not summary_path.is_file():
        return {"passed": False, "artifact_root": str(root.relative_to(ROOT)), "reason": "matching-calendar runner summary missing"}
    summary = _read_object(summary_path, "runner summary")
    screenshots = sorted((root / "screens").glob("*line_up_inspect*.png"))
    phase = str(summary.get("phase_reached") or "")
    manifest_bound = (
        release.manifest_sha256 is not None
        and summary.get("release_manifest_sha256") == release.manifest_sha256
    )
    inventory_bound = summary.get("output_inventory_fingerprint") == release.locator.get(
        "game_inventory_fingerprint"
    )
    line_up_summary = (summary.get("route_summaries") or {}).get("line_up")
    team_identity = line_up_summary.get("team_identity") if isinstance(line_up_summary, Mapping) else None
    club_identity_bound = bool(
        isinstance(team_identity, Mapping)
        and team_identity.get("matched") is True
        and "stoke" in str(team_identity.get("observed_normalized") or "").split()
    )
    passed = (
        summary.get("success") is True
        and phase == "return_from_line_up"
        and len(screenshots) == 1
        and manifest_bound
        and inventory_bound
        and club_identity_bound
    )
    return {
        "passed": passed,
        "artifact_root": str(root.relative_to(ROOT)),
        "summary": str(summary_path.relative_to(ROOT)),
        "phase_reached": phase,
        "runner_success": summary.get("success") is True,
        "release_manifest_bound": manifest_bound,
        "output_inventory_bound": inventory_bound,
        "club_identity_bound": club_identity_bound,
        "lineup_screenshot": str(screenshots[0].relative_to(ROOT)) if len(screenshots) == 1 else None,
        "reason": None if passed else "matching-calendar run did not reach and capture Line-Up",
    }


def audit_binary_receipt(season: str, game: Path) -> dict[str, Any]:
    receipt_path = release_registry.load_preferred_release(season).compiler_receipt_path
    if receipt_path is None or not receipt_path.is_file():
        return {"receipt": None, "checked_file_count": 0, "mismatch_count": 0, "mismatches": [], "warning": "compiler receipt unavailable"}
    receipt = _read_object(receipt_path, "compiler receipt")
    outputs = receipt.get("outputs")
    compiler_outputs = {
        str(row.get("path")): str(row.get("sha256"))
        for row in (outputs if isinstance(outputs, list) else []) if isinstance(row, Mapping)
        and isinstance(row.get("path"), str) and isinstance(row.get("sha256"), str)
    }
    release = release_registry.load_preferred_release(season)
    chain_issues = release_registry._validate_build_chain(release, compiler_outputs)
    if not chain_issues:
        chain = _read_object(release.build_chain_path, "registered build chain")
        transforms = [
            {
                "id": stage.get("id"),
                "receipt_sha256": stage.get("receipt_sha256"),
                "changed_paths": sorted((stage.get("after") or {}).keys()),
            }
            for stage in chain.get("stages", [])
            if isinstance(stage, Mapping) and str(stage.get("id") or "").startswith("declared-transform-")
        ]
        return {
            "receipt": str(receipt_path.relative_to(ROOT)),
            "checked_file_count": len(compiler_outputs),
            "mismatch_count": 0,
            "mismatches": [],
            "accepted_registered_transforms": transforms,
        }
    mismatches = []
    accepted_direct_repairs = []
    manager_repair_candidates = [
        ROOT / ".local/season-direct-target-manager-repairs-v2" / f"{season}.json",
        ROOT / ".local/season-direct-target-manager-repairs-v1" / f"{season}.json",
    ]
    manager_repair_path = next((path for path in manager_repair_candidates if path.is_file()), manager_repair_candidates[-1])
    manager_repair_hashes: dict[str, str] = {}
    manager_repair: Mapping[str, Any] | None = None
    if manager_repair_path.is_file():
        candidate = _read_object(manager_repair_path, "direct target-manager repair receipt")
        refresh = candidate.get("runtime_refresh")
        if (
            candidate.get("schema_version") == "pm99-season-direct-target-manager-repair-v1"
            and candidate.get("season") == season
            and candidate.get("state") == "applied-directly-to-alpha-game"
            and isinstance(refresh, Mapping)
        ):
            for relative, key in (
                ("DBDAT/EQ98030.FDI", "eq_after_sha256"),
                ("DBDAT/ENT98030.FDI", "ent_after_sha256"),
            ):
                value = refresh.get(key)
                if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value):
                    manager_repair_hashes[relative] = value
            if len(manager_repair_hashes) == 2:
                manager_repair = candidate
    nationality_repair_path = ROOT / ".local/season-nationality-repair-v1" / season / "repair-receipt.json"
    nationality_repair: Mapping[str, Any] | None = None
    if nationality_repair_path.is_file():
        candidate = _read_object(nationality_repair_path, "direct nationality repair receipt")
        expected_runtime = str(game.relative_to(ROOT))
        if (
            candidate.get("schema_version") == "pm99-season-direct-compiled-nationality-readback-repair-v1"
            and candidate.get("season") == season
            and candidate.get("state") == "applied-directly-to-alpha-game"
            and candidate.get("runtime_game") == expected_runtime
            and isinstance(candidate.get("jug_after_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", str(candidate["jug_after_sha256"]))
            and int(candidate.get("runtime_changed_carrier_count") or 0) > 0
        ):
            nationality_repair = candidate
    # Alpha repairs alter only the explicitly declared JUG records.  A short
    # receipt lets the normal receipt audit distinguish that deliberate,
    # bounded change from an accidental compiler drift.  More than one kind
    # of repair may exist for a season, so accept the receipt whose recorded
    # final JUG hash is the file actually present at runtime.
    direct_receipts: list[tuple[Path, Mapping[str, Any], int]] = []
    repair_roots = (
        (
            ROOT / ".local/season-direct-name-repairs-v1",
            "pm99-season-number-label-name-direct-repair-v1",
            "jug_delta",
        ),
        (
            ROOT / ".local/season-direct-handling-repairs-v1",
            "pm99-season-direct-position-handling-repair-v1",
            None,
        ),
        (
            ROOT / ".local/season-direct-compiled-handling-readback-repairs-v1",
            "pm99-season-direct-compiled-handling-readback-repair-v1",
            None,
        ),
        (
            ROOT / ".local/season-direct-opening-lineup-position-repairs-v1",
            "pm99-season-direct-opening-lineup-position-repair-v1",
            None,
        ),
        (
            ROOT / ".local/season-direct-birth-date-plausibility-repairs-v1",
            "pm99-season-direct-birth-date-plausibility-repair-v1",
            None,
        ),
    )
    # A direct alpha repair is hash-bound to one runtime revision.  Prefer a
    # revision-suffixed receipt so promoting r2 cannot accidentally inherit an
    # r1 acceptance; retain the old season-only names for legacy candidates.
    revision = release_registry.load_preferred_release(season).revision
    receipt_candidates = [
        (path, schema_version, delta_key)
        for root, schema_version, delta_key in repair_roots
        for path in (
            ([root / f"{season}-{revision}.json"] if revision is not None else [])
            + [root / f"{season}.json"]
        )
    ]
    for direct_receipt_path, schema_version, delta_key in receipt_candidates:
        if not direct_receipt_path.is_file():
            continue
        candidate = _read_object(direct_receipt_path, "direct alpha repair receipt")
        refresh = candidate.get("runtime_refresh")
        receipt_season = candidate.get("season")
        # The first position-handling pilot wrote the package's season object
        # rather than the runner's YYYY-YY key.  It is still unambiguous, so
        # recognise it while all newly written receipts use the compact key.
        if isinstance(receipt_season, Mapping):
            receipt_season = (
                f"{receipt_season.get('start_year'):04d}-{int(receipt_season.get('end_year')) % 100:02d}"
                if isinstance(receipt_season.get("start_year"), int)
                and isinstance(receipt_season.get("end_year"), int)
                else None
            )
        if not (
            candidate.get("schema_version") == schema_version
            and receipt_season == season
            and candidate.get("state") == "applied-directly-to-alpha-game"
            and isinstance(refresh, Mapping)
            and isinstance(refresh.get("jug_after_sha256"), str)
        ):
            continue
        if delta_key is None:
            changed_carrier_count = int(refresh.get("changed_carrier_count") or 0)
        else:
            delta = refresh.get(delta_key)
            changed_carrier_count = (
                int(delta.get("changed_carrier_count") or 0)
                if isinstance(delta, Mapping) else 0
            )
        if changed_carrier_count > 0:
            direct_receipts.append((direct_receipt_path, candidate, changed_carrier_count))
    checked = 0
    for row in outputs if isinstance(outputs, list) else []:
        if not isinstance(row, Mapping):
            continue
        relative = str(row.get("path") or "")
        expected = str(row.get("sha256") or "")
        path = game / relative
        if relative and re.fullmatch(r"[0-9a-f]{64}", expected) and path.is_file():
            checked += 1
            actual = _sha256(path)
            if actual != expected:
                if (
                    relative == "DBDAT/JUG98030.FDI"
                    and nationality_repair is not None
                    and actual == nationality_repair["jug_after_sha256"]
                ):
                    accepted_direct_repairs.append({
                        "path": relative,
                        "compiler_sha256": expected,
                        "direct_repair_sha256": actual,
                        "changed_carrier_count": int(nationality_repair["runtime_changed_carrier_count"]),
                        "receipt": str(nationality_repair_path.relative_to(ROOT)),
                    })
                    continue
                if manager_repair is not None and manager_repair_hashes.get(relative) == actual:
                    accepted_direct_repairs.append({
                        "path": relative,
                        "compiler_sha256": expected,
                        "direct_repair_sha256": actual,
                        "changed_carrier_count": int(
                            manager_repair["runtime_refresh"].get(
                                "changed_club_carrier_count"
                                if relative == "DBDAT/EQ98030.FDI"
                                else "changed_manager_carrier_count"
                            ) or 0
                        ),
                        "receipt": str(manager_repair_path.relative_to(ROOT)),
                    })
                    continue
                accepted_repair = next(
                    (
                        (receipt_path, receipt, changed_carrier_count)
                        for receipt_path, receipt, changed_carrier_count in direct_receipts
                        if relative == "DBDAT/JUG98030.FDI"
                        and actual == receipt["runtime_refresh"]["jug_after_sha256"]
                    ),
                    None,
                )
                if accepted_repair is not None:
                    direct_receipt_path, direct_receipt, changed_carrier_count = accepted_repair
                    accepted_direct_repairs.append({
                        "path": relative,
                        "compiler_sha256": expected,
                        "direct_repair_sha256": actual,
                        "changed_carrier_count": changed_carrier_count,
                        "receipt": str(direct_receipt_path.relative_to(ROOT)),
                    })
                    continue
                mismatches.append({"path": relative, "expected_sha256": expected, "actual_sha256": actual})
    return {
        "receipt": str(receipt_path.relative_to(ROOT)),
        "checked_file_count": checked,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "accepted_direct_alpha_repairs": accepted_direct_repairs,
    }


def audit_calendar(season: str, game: Path) -> dict[str, Any]:
    expected_path = ROOT / ".local/calendar-v1" / season / "MANAGPRE.EXE"
    actual_path = game / "MANAGPRE.EXE"
    if not expected_path.is_file():
        return {"passed": False, "reason": "season calendar input missing", "expected_path": str(expected_path.relative_to(ROOT))}
    expected, actual = _sha256(expected_path), _sha256(actual_path)
    result = {"passed": expected == actual, "expected_path": str(expected_path.relative_to(ROOT)), "expected_sha256": expected, "actual_sha256": actual}
    if not result['passed']:
        # The independently proven DOB guard is not a calendar rebase. Accept
        # precisely that guarded two-byte transform of this exact calendar;
        # never accept an arbitrary executable just because it has a receipt.
        sys.path.insert(0, str(ROOT / 'upstream/pm99-skezmod-patcher'))
        from player_birth_year_guard import patch_native_birth_year_guard
        try:
            patched, receipt = patch_native_birth_year_guard(expected_path.read_bytes())
        except ValueError:
            return result
        if hashlib.sha256(patched).hexdigest() == actual:
            result.update(passed=True, accepted_native_birth_year_guard=receipt)
    return result


def _artwork_chain_through_unchanged_role_deltas(season, release, manifest):
    """Follow hash-bound predecessor chains without relabelling old receipts.

    A partial DB compile can inherit artwork, but it must prove all three kit
    archive outputs are unchanged from its predecessor at every ancestry hop.
    """
    chain = _read_object(release.build_chain_path, 'artwork build chain')
    descriptors = list(manifest.get('external_artifacts', []))
    for stage in manifest.get('stages', []):
        descriptors.extend(stage.get('external_artifacts', []))
    seen = set()
    for _ in range(32):
        inherited = [s for s in chain.get('stages', [])
                     if s.get('id') in {'inherited-known-good-assets', 'inherited-identical-game',
                                        'bounded-portrait-fallback-and-unchanged-assets'}]
        if not inherited:
            return chain
        if len(inherited) != 1:
            raise QaError('ambiguous inherited artwork stage')
        stage = inherited[0]
        digest = stage.get('source_build_chain_sha256')
        if not digest or digest in seen:
            raise QaError('invalid/cyclic inherited artwork ancestry')
        seen.add(digest)
        candidates = sorted((release_registry.LOCAL_ROOT / 'releases' / season).glob('*/build-chain.json'))
        path = next((p for p in candidates if _sha256(p) == digest), None)
        if path is None or not any(a.get('sha256') == digest and a.get('size') == path.stat().st_size for a in descriptors):
            raise QaError('inherited artwork predecessor is not hash-bound')
        previous = _read_object(path, 'inherited artwork predecessor')
        if previous.get('season') != season:
            raise QaError('inherited artwork predecessor is another season')
        final_outputs = {}
        for s in previous.get('stages', []):
            final_outputs.update(s.get('outputs', {}))
            for name in s.get('removed', []):
                final_outputs.pop(name, None)
        if stage.get('id') == 'inherited-identical-game' and stage.get('outputs') != final_outputs:
            raise QaError('recipe-only revision changed inherited game outputs')
        for archive in ('MINIESC.PKF', 'NANOESC.PKF', 'RIDIESC.PKF'):
            name = 'DBDAT/' + archive
            expected = final_outputs.get(name)
            if not expected or stage.get('outputs', {}).get(name) != expected:
                raise QaError('role delta changed inherited kit archive')
        chain = previous
    raise QaError('inherited artwork ancestry depth exceeded')


def _paired_kit_patch_hashes(season,game,release,application_path,application,manifest):
    """Accept a proved coupled transaction, not an unchanged-artwork fiction."""
    # Later bounded publications replace top-level predecessor descriptors.
    # The original transaction's immutable stage descriptors remain bound in
    # the registered manifest and must be considered, as for ordinary kit
    # ancestry. Never accept an unbound file just because a locator exists.
    descriptors=list(manifest.get('external_artifacts',[]))
    for stage in manifest.get('stages',[]):
        descriptors.extend(stage.get('external_artifacts',[]))
    def bound(path,digest):
        if _sha256(path)!=digest or not any(a.get('sha256')==digest and a.get('size')==path.stat().st_size for a in descriptors):
            raise QaError('coupled kit input is not hash-bound to the release')
    bound(application_path,_sha256(application_path))
    if application.get('season')!=season:raise QaError('coupled kit application is another season')
    previous=release_registry.load_registered_release(season,application['source_release_id'])
    bound(previous.build_chain_path,application['source_build_chain_sha256'])
    documents={}
    for label in ('candidate_receipt','native_proof','identity_proof'):
        binding=application[label];path=ROOT/binding['path'];path.resolve().relative_to(ROOT.resolve())
        bound(path,binding['sha256']);documents[label]=_read_object(path,'coupled kit '+label)
    digest=application['candidate_receipt']['sha256'];native=documents['native_proof'];identity=documents['identity_proof']
    if (native.get('candidate_receipt_sha256')!=digest or identity.get('candidate_receipt_sha256')!=digest
            or native.get('all_unselected_native_records_identical') is not True
            or identity.get('introduced_candidate_groups')!=0 or identity.get('replacement_cross_club_candidates')!=0):
        raise QaError('coupled kit transaction lacks exact independent native/identity proof')
    result=_registered_kit_patch_hashes(season,previous.game_path,_release=previous)
    changes=application['difference']['changed'];paths={'DBDAT/'+n for n in ('MINIESC.PKF','NANOESC.PKF','RIDIESC.PKF')}
    if len(changes)!=3 or {r['path'] for r in changes}!=paths:raise QaError('coupled kit archive scope is incomplete')
    for change in changes:
        name=Path(change['path']).name;before=change['left']['sha256'];after=change['right']['sha256']
        if (_sha256(previous.game_path/change['path'])!=before or _sha256(game/change['path'])!=after
                or documents['candidate_receipt']['native_hashes'].get(name)!=after
                or (name in result and result[name]['after']!=before)):
            raise QaError('coupled kit before/after archives do not match the exact releases')
        prior=result.get(name,{'before':before,'history':[]})
        result[name]={'before':prior['before'],'after':after,'receipt_sha256':_sha256(application_path),
            'history':prior['history']+[{'before':before,'after':after,'receipt_sha256':_sha256(application_path),
                'application_path':str(application_path.relative_to(ROOT)),'stage_index':'coupled-native-and-kit-delta'}]}
    return result


def _registered_kit_patch_hashes(season: str, game: Path, *, _release=None) -> dict[str, dict[str, str]]:
    """Accept only receipt-bound narrow replacements, not arbitrary new hashes."""
    release = _release or release_registry.load_preferred_release(season)
    relative = release.locator.get("kit_patch_application_path") or release.locator.get("portrait_patch_application_path")
    if not relative:
        return {}
    if release.release_manifest_path is None or _sha256(release.release_manifest_path) != release.manifest_sha256:
        raise QaError("kit patch release manifest is not registered")
    manifest_for_ancestry = _read_object(release.release_manifest_path, 'artwork release manifest')
    application_path=ROOT/relative
    application_path.resolve().relative_to(ROOT.resolve())
    paired=_read_object(application_path,'artwork application')
    if paired.get('schema_version')=='pm99-coupled-club-kit-application-v1':
        return _paired_kit_patch_hashes(season,game,release,application_path,paired,manifest_for_ancestry)
    artwork_chain = _artwork_chain_through_unchanged_role_deltas(season, release, manifest_for_ancestry)
    # Pre-fix publishers had only one artwork pointer. A portrait-only update
    # could hide an earlier Bayer(n)/kit application. Recover it ONLY from a
    # receipt-bound stage retained in this release's build chain; archived
    # locators supply paths, never trusted hashes or inherited approval.
    latest = _read_object(ROOT / relative, 'latest artwork application')
    if not any(r.get('path') in {'DBDAT/MINIESC.PKF', 'DBDAT/NANOESC.PKF', 'DBDAT/RIDIESC.PKF'}
               for r in latest.get('difference', {}).get('changed', [])):
        ancestry = artwork_chain
        for stage in reversed(ancestry.get('stages', [])):
            stage_id = str(stage.get('id', ''))
            if not stage_id.startswith('portrait-'): continue
            old_path = release_registry.locator_path(season, stage_id[len('portrait-'):])
            if not old_path.is_file(): continue
            old = _read_object(old_path, 'artwork ancestor locator')
            candidate = old.get('kit_patch_application_path') or old.get('portrait_patch_application_path')
            if not candidate: continue
            path = ROOT / candidate
            path.resolve().relative_to(ROOT.resolve())
            if not path.is_file() or _sha256(path) != stage.get('receipt_sha256'): continue
            previous = _read_object(path, 'artwork ancestor application')
            if any(r.get('path') in {'DBDAT/MINIESC.PKF', 'DBDAT/NANOESC.PKF', 'DBDAT/RIDIESC.PKF'}
                   for r in previous.get('difference', {}).get('changed', [])):
                relative = candidate
                break
    receipt_path = ROOT / relative
    receipt_path.resolve().relative_to(ROOT.resolve())
    if release.release_manifest_path is None or _sha256(release.release_manifest_path) != release.manifest_sha256:
        raise QaError("kit patch release manifest is not registered")
    manifest = _read_object(release.release_manifest_path, "kit patch release manifest")
    digest = _sha256(receipt_path)
    descriptors = [row for row in manifest.get("external_artifacts", []) if row.get("sha256") == digest]
    if len(descriptors) != 1 or descriptors[0].get("size") != receipt_path.stat().st_size:
        raise QaError("kit patch application is not hash-bound to the release")
    application = _read_object(receipt_path, "kit patch application")
    if application.get("season") != season or application.get("unrelated_files_unchanged") is not True:
        raise QaError("kit patch application has invalid scope")
    chain = artwork_chain
    stages = [row for row in chain.get("stages", []) if row.get("receipt_sha256") == digest]
    if len(stages) != 1:
        raise QaError("kit patch has no unique registered build stage")
    result = {}
    kit_paths = {"DBDAT/MINIESC.PKF", "DBDAT/NANOESC.PKF", "DBDAT/RIDIESC.PKF"}
    if not any(c.get('path') in kit_paths for c in application.get('difference', {}).get('changed', [])):
        return result
    # Compose per archive in chronological build-chain order. A later NANO
    # patch must neither erase earlier MIN/RIDI evidence nor compare its
    # intermediate predecessor directly with the original V5 baseline.
    latest_index = chain['stages'].index(stages[0])
    for stage_index, stage in enumerate(chain['stages'][:latest_index + 1]):
        if not kit_paths.intersection(stage.get('outputs', {})):
            continue
        if stage is stages[0]:
            bound_path, bound = receipt_path, application
        elif str(stage.get('id', '')).startswith('portrait-'):
            ancestor = release_registry.locator_path(season, stage['id'][len('portrait-'):])
            old = _read_object(ancestor, 'kit ancestor locator')
            candidate = old.get('kit_patch_application_path') or old.get('portrait_patch_application_path')
            if not candidate:
                raise QaError('kit ancestor application is missing')
            bound_path = ROOT / candidate
            bound_path.resolve().relative_to(ROOT.resolve())
            bound = _read_object(bound_path, 'kit ancestor application')
        else:
            continue
        bound_digest = _sha256(bound_path)
        descriptors = [a for a in manifest.get('external_artifacts', []) if a.get('sha256') == bound_digest]
        if (bound_digest != stage.get('receipt_sha256') or len(descriptors) != 1
                or descriptors[0].get('size') != bound_path.stat().st_size):
            raise QaError('kit ancestor application is not hash-bound to the release')
        if bound.get('season') != season or bound.get('unrelated_files_unchanged') is not True:
            raise QaError('kit ancestor application has invalid scope')
        seen = set()
        for change in bound.get('difference', {}).get('changed', []):
            path = change.get('path')
            if path not in kit_paths:
                continue
            if path in seen:
                raise QaError('duplicate kit archive in application')
            seen.add(path)
            before, after = change['left']['sha256'], change['right']['sha256']
            if stage.get('outputs', {}).get(path) != after:
                raise QaError('kit patch output differs from its bound stage')
            name = Path(path).name
            if name in result and result[name]['after'] != before:
                raise QaError('kit patch predecessor archive hashes do not match')
            previous = result.get(name, {'before': before, 'history': []})
            result[name] = {'before': previous['before'], 'after': after,
                'receipt_sha256': bound_digest, 'history': previous['history'] + [{
                    'before': before, 'after': after, 'receipt_sha256': bound_digest,
                    'application_path': str(bound_path.relative_to(ROOT)), 'stage_index': stage_index}]}
        if seen != kit_paths.intersection(stage.get('outputs', {})):
            raise QaError('kit stage and application archive scopes differ')
    for name, values in result.items():
        if _sha256(game / 'DBDAT' / name) != values['after']:
            raise QaError('kit patch output differs from its bound stage')
    return result


def _apply_2015_kit_patch_history(receipt, patches):
    """Replay signed per-carrier deltas, including the separate English layer."""
    expected = {(e['archive'], int(e['carrier_id'])): e for e in receipt['foreign_events']}
    foreign_keys = set(expected)
    english_path = ROOT / 'seasons/2015-16/english-layer/2015-16-english-92-native-kit-receipt.json'
    english = _read_object(english_path, '2015 English kit receipt')
    for row in english['patched']:
        key = row['archive_name'], int(row['team_id'])
        if key in expected:
            raise QaError('English and foreign kit carriers overlap')
        expected[key] = {'bitmap_sha256_after': row['bitmap_sha256_after']}
    # Histories are ordered per archive. Process each application once, using
    # its stage-specific predecessor rather than the composed first hash.
    applications = {}
    for archive, patch in patches.items():
        for step in patch['history']:
            applications.setdefault(step['application_path'], {})[archive] = step
    accepted, english_changed = [], set()
    for relative, steps in sorted(applications.items(), key=lambda item: min(
            step['stage_index'] for step in item[1].values())):
        application = _read_object(ROOT / relative, '2015 kit patch application')
        materialisation_path = Path(application.get('materialisation_path', ''))
        materialisation_path.resolve().relative_to(ROOT.resolve())
        if (not materialisation_path.is_file()
                or _sha256(materialisation_path) != application['materialisation_sha256']):
            raise QaError('2015 kit patch materialisation is not hash-bound')
        materialisation = _read_object(materialisation_path, '2015 kit pattern materialisation')
        seen = set()
        for event in materialisation['events']:
            key = event['archive'], int(event['carrier_id'])
            if key in seen or key not in expected:
                raise QaError('2015 kit patch has a duplicate/unbound carrier')
            seen.add(key)
            step = steps.get(event['archive'])
            if (step is None or expected[key]['bitmap_sha256_after'] != event['before_bitmap_sha256']
                    or materialisation['kit_before_sha256s']['DBDAT/' + event['archive']] != step['before']):
                raise QaError('2015 kit patch predecessor hashes do not match')
            expected[key] = {**expected[key], 'bitmap_sha256_after': event['after_bitmap_sha256']}
            accepted.append({'archive': key[0], 'carrier_id': key[1]})
            if key not in foreign_keys:
                english_changed.add(key)
    return {**receipt, 'foreign_events': [expected[k] for k in sorted(foreign_keys)]}, accepted, {
        key: expected[key]['bitmap_sha256_after'] for key in english_changed}


def audit_kit_outputs(season: str, game: Path) -> dict[str, Any]:
    if season == "2015-16":
        v5_receipt = ROOT / ".local/season-kit-runtime-overlays-v1/2015-16/v5/foreign-kit-application-receipt.json"
        receipt_path = (
            v5_receipt
            if v5_receipt.is_file()
            else ROOT / ".local/season-workspace-v1/2015-16-final-build/foreign-kit-application-receipt.json"
        )
        receipt = _read_object(receipt_path, "2015/16 foreign kit receipt")
        patches = _registered_kit_patch_hashes(season, game)
        accepted_events = []
        if patches:
            receipt, accepted_events, english_changed = _apply_2015_kit_patch_history(receipt, patches)
            from scripts import season_kit_render_bindings_v1 as kit_renderer
            for archive in {key[0] for key in english_changed}:
                records = kit_renderer._record_index(game / 'DBDAT' / archive)
                for (name, carrier), expected_hash in english_changed.items():
                    if name == archive and kit_renderer.sha256_bytes(records[carrier].raw_bitmap) != expected_hash:
                        raise QaError('2015 English kit patch readback differs')
        raw = audit_kits(game_tree=game, receipt=receipt, review=None)
        readback_failures = [row for row in raw["failures"] if not row["archive_readback_matches"]]
        return {
            "receipt": str(receipt_path.relative_to(ROOT)),
            "receipt_sha256": _sha256(receipt_path),
            "patched_carrier_count": raw["patched_foreign_carrier_count"],
            "checked_archive_count": 3,
            "byte_or_format_failure_count": len(readback_failures),
            "failures": readback_failures[:100],
            "visual_review_approved_count": raw["visually_approved_carrier_count"],
            "visual_review_missing": raw["patched_foreign_carrier_count"] > raw["visually_approved_carrier_count"],
            "accepted_registered_kit_pattern_events": accepted_events,
        }

    revision = release_registry.load_preferred_release(season).revision
    if revision is None:
        raise QaError(f"registered {season} release has no kit revision binding")
    overlay_receipt = ROOT / ".local/season-kit-runtime-overlays-v1" / season / "v5" / "receipt.json"
    receipt_path = ROOT / ".local/season-kit-archives-v1" / season / f"source-backed-{revision}" / "kit-archive-materialisation-receipt-v1.json"
    if overlay_receipt.is_file():
        overlay = _read_object(overlay_receipt, "V5 runtime kit overlay receipt")
        provenance = overlay.get("provenance") if isinstance(overlay.get("provenance"), Mapping) else {}
        relative = str(provenance.get("v5_archive_receipt") or "")
        candidate = ROOT / relative
        try:
            candidate.resolve().relative_to(ROOT.resolve())
        except ValueError:
            candidate = Path()
        if relative and candidate.is_file():
            receipt_path = candidate
    if not receipt_path.is_file():
        return {
            "receipt": None,
            "patched_carrier_count": 0,
            "checked_archive_count": 0,
            "byte_or_format_failure_count": 1,
            "failures": [{"reason": "preferred kit archive receipt missing", "expected_path": str(receipt_path.relative_to(ROOT))}],
            "visual_review_approved_count": 0,
            "visual_review_missing": True,
        }
    receipt = _read_object(receipt_path, "kit archive receipt")
    failures = []
    patches = _registered_kit_patch_hashes(season, game)
    accepted_patches = []
    archives = receipt.get("archives")
    if not isinstance(archives, Mapping):
        failures.append({"reason": "receipt has no archive map"})
        archives = {}
    for archive in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"):
        row = archives.get(archive)
        expected = str(row.get("sha256_after") or "") if isinstance(row, Mapping) else ""
        patch = patches.get(archive)
        if patch and patch["before"] == expected:
            accepted_patches.append({"archive": archive, **patch})
            expected = patch["after"]
        actual_path = game / "DBDAT" / archive
        actual = _sha256(actual_path) if actual_path.is_file() else None
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or actual != expected:
            failures.append({"archive": archive, "expected_sha256": expected or None, "actual_sha256": actual})
    expected_dimensions = {
        "MINIESC.PKF": (48, 64),
        "NANOESC.PKF": (24, 32),
        "RIDIESC.PKF": (17, 20),
    }
    bad_events = []
    for event in receipt.get("events") or []:
        archive = str(event.get("archive") or "") if isinstance(event, Mapping) else ""
        dimensions = expected_dimensions.get(archive)
        if not isinstance(event, Mapping) or event.get("bits_per_pixel") != 8 or dimensions != (event.get("width"), event.get("height")):
            bad_events.append({
                "archive": event.get("archive") if isinstance(event, Mapping) else None,
                "carrier_id": event.get("carrier_id") if isinstance(event, Mapping) else None,
                "bits_per_pixel": event.get("bits_per_pixel") if isinstance(event, Mapping) else None,
                "width": event.get("width") if isinstance(event, Mapping) else None,
                "height": event.get("height") if isinstance(event, Mapping) else None,
            })
    failures.extend({"reason": "unexpected compact-kit bitmap format", **row} for row in bad_events[:100])
    coverage = receipt.get("coverage") if isinstance(receipt.get("coverage"), Mapping) else {}
    return {
        "receipt": str(receipt_path.relative_to(ROOT)),
        "receipt_sha256": _sha256(receipt_path),
        "patched_carrier_count": int(coverage.get("bound_carrier_count") or 0),
        "checked_archive_count": len(archives),
        "byte_or_format_failure_count": len(failures),
        "failures": failures[:100],
        "accepted_registered_kit_patches": accepted_patches,
        "visual_review_approved_count": 0,
        "visual_review_missing": True,
    }


def audit_compiled_player_identities(*, game: Path) -> dict[str, Any]:
    """Check every native JUG record, not only the visible first XI."""
    data = (game / 'DBDAT/JUG98030.FDI').read_bytes()
    checked = 0
    failures = []
    for entry in IndexedFDIFile.from_bytes(data).entries:
        payload = entry.decode_payload(data)
        if payload[2:5] not in (b'\xdd\x63\x60', b'\xdd\x63\x61'):
            continue
        checked += 1
        native_id = read_indexed_player_id(payload)
        if native_id != entry.record_id:
            failures.append({'directory_id': entry.record_id, 'native_id': native_id})
    return {'checked_player_count': checked, 'failure_count': len(failures), 'failures': failures}


def audit_compiled_roles(package: Mapping[str, Any], *, game: Path) -> dict[str, Any]:
    """Explicit roles must match native bytes; preserved roles are not verified."""
    raw = (game / 'DBDAT/JUG98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(raw).entries}
    failures, inherited_conflicts, unresolved = [], [], []
    checked = 0
    for player in package['players']:
        if player.get('policy') == 'preserve-existing-mode1':
            continue
        carrier = int(player['carrier_id'])
        expected = player['facts'].get('fine_roles')
        try:
            _, roles = read_indexed_native_roles(entries[carrier].decode_payload(raw), carrier)
        except (KeyError, ValueError) as exc:
            failures.append({'player_id': player['id'], 'carrier_id': carrier, 'error': str(exc)})
            continue
        if isinstance(expected, list) and expected:
            checked += 1
            if roles != expected + [98] * (6 - len(expected)):
                failures.append({'player_id': player['id'], 'carrier_id': carrier, 'expected': expected, 'actual': roles})
        else:
            unresolved.append(player['id'])
            position = player['facts'].get('primary_position')
            role = roles[0]
            contradiction = ((position == 'G' and role not in (0, 98)) or
                (position in ('D', 'M', 'F') and role == 0) or
                (position == 'F' and role in (1, 2, 3, 4, 5)) or
                (position == 'D' and role in (8, 12, 15, 16)))
            if contradiction:
                inherited_conflicts.append({'player_id': player['id'], 'carrier_id': carrier,
                                            'position': position, 'inherited_role': role})
    return {'explicit_players_checked': checked, 'failure_count': len(failures), 'failures': failures,
            'unresolved_role_count': len(unresolved), 'inherited_conflict_count': len(inherited_conflicts),
            'inherited_conflicts': inherited_conflicts,
            'scope': 'Native explicit-role conformance; a preserved carrier role is never historical verification'}


def audit_season(season: str) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    availability = validate_candidate(season)
    if not availability["valid"]:
        blockers.append(_issue("candidate-incomplete", "preferred gameplay candidate is incomplete", missing=availability["missing"]))
    game = game_path(season)
    package_path = resolve_package(season)
    package = _read_object(package_path, "season package")
    roles_binary = audit_compiled_roles(package, game=game)
    if roles_binary['failure_count']:
        blockers.append(_issue('compiled-fine-role-mismatch', 'explicit player roles differ from the actual native loader bytes',
                               count=roles_binary['failure_count'], samples=roles_binary['failures'][:20]))
    if roles_binary['unresolved_role_count']:
        warnings.append(_issue('historical-fine-role-unresolved', 'inherited carrier roles lack explicit historical role declarations',
                               count=roles_binary['unresolved_role_count'], inherited_conflicts=roles_binary['inherited_conflict_count']))
    from scripts.audit_compiled_player_birth_dates_v1 import inspect as inspect_birth_dates
    try:
        birth_dates_binary = inspect_birth_dates(package, (game / 'DBDAT/JUG98030.FDI').read_bytes())
        if birth_dates_binary['failure_count']:
            blockers.append(_issue('compiled-player-birth-date-mismatch',
                'literal recipe birthdays disagree with actual native records',
                count=birth_dates_binary['failure_count'], samples=birth_dates_binary['failures'][:20]))
    except (OSError, ValueError) as exc:
        birth_dates_binary = {'failure_count': 1, 'error': str(exc)}
        blockers.append(_issue('compiled-player-birth-date-readback-failed',
            'actual native birthday readback failed', error=str(exc)))
    package_validation = {"passed": True, "strict": season != "2015-16", "error": None}
    try:
        validate_package(package, strict=season != "2015-16")
    except PackageValidationError as exc:
        package_validation = {"passed": False, "strict": season != "2015-16", "error": str(exc)}
        blockers.append(_issue("package-validation-failed", "season package failed structural validation", error=str(exc)))

    manager_sources = audit_manager_sources(season, package)
    if manager_sources["mismatch_count"]:
        blockers.append(_issue("historical-manager-mismatch", "package manager disagrees with the dated English opening-manager reference", count=manager_sources["mismatch_count"], samples=manager_sources["mismatches"][:20]))
    if manager_sources["missing_reference_count"]:
        blockers.append(_issue("historical-manager-reference-missing", "English clubs lack a dated opening-manager reference", count=manager_sources["missing_reference_count"], samples=manager_sources["missing_references"][:20]))
    if manager_sources["provisional_foreign_manager_count"]:
        warnings.append(_issue("foreign-manager-target-season-evidence-missing", "foreign managers are preserved or lack independent target-season evidence", count=manager_sources["provisional_foreign_manager_count"], foreign_club_count=manager_sources["foreign_club_count"]))

    recipe = audit_recipe(package, season=season)
    player_identity = audit_player_identities(package)
    identity_blockers, identity_warnings = player_identity_issues(player_identity)
    blockers.extend(identity_blockers)
    warnings.extend(identity_warnings)
    from scripts.season_contextual_tactics_rollout_v1 import load_english
    from scripts.season_opening_order_repair_v1 import deployment_review
    deployment = deployment_review(load_english(release_registry.load_preferred_release(season), package))
    if deployment['warning_count']:
        warnings.append(_issue('tactics-player-fact-deployment-disagreement',
            'tactical deployments disagree with stored player positions; either input may need historical review',
            count=deployment['warning_count'], samples=deployment['warnings'][:20]))
    for code, key, message in (
        ("player-rating-plausibility-failed", "rating_failure_count", "player ratings contain semantic or range failures"),
        ("player-date-plausibility-failed", "date_failure_count", "player birth dates are invalid for the season snapshot"),
        ("player-secondary-fact-invalid", "secondary_fact_failure_count", "present secondary player facts are outside plausible bounds"),
        ("opening-lineup-position-failed", "lineup_failure_count", "opening lineups have an invalid goalkeeper composition"),
        ("pm99-objective-input-profile-flat", "objective_input_failure_count", "opening-XI ratings are too flat for PM99 to assign differentiated club objectives"),
    ):
        if recipe[key]:
            sample_key = key.replace("_count", "s")
            blockers.append(_issue(code, message, count=recipe[key], samples=recipe.get(sample_key, [])[:20]))
    if recipe["distribution_warning_count"]:
        warnings.append(_issue("team-rating-distribution-suspicious", "one or more squads have a suspiciously flat or elite-heavy quality distribution", count=recipe["distribution_warning_count"], samples=recipe["distribution_warnings"][:20]))
    missing_count = sum(recipe["missing_secondary_fact_counts"].values())
    if missing_count:
        warnings.append(_issue("secondary-player-facts-missing", "secondary facts are absent or deliberately preserved; this does not block a build", count=missing_count, fields=recipe["missing_secondary_fact_counts"]))

    manager_binary: dict[str, Any]
    handling_binary: dict[str, Any]
    nationality_binary: dict[str, Any]
    try:
        identity_binary = audit_compiled_player_identities(game=game)
        if identity_binary['failure_count']:
            blockers.append(_issue('compiled-player-identity-mismatch',
                'native player self-IDs disagree with their JUG directory keys',
                count=identity_binary['failure_count'], samples=identity_binary['failures'][:20]))
    except (OSError, ValueError) as exc:
        identity_binary = {'failure_count': 1, 'error': str(exc)}
        blockers.append(_issue('compiled-player-identity-audit-error', str(exc)))
    try:
        manager_binary = audit_compiled_managers(package, game=game, season=season, package_path=package_path)
        if manager_binary["failure_count"]:
            blockers.append(_issue("compiled-manager-link-failed", "compiled manager name/club ownership differs from the recipe", count=manager_binary["failure_count"], samples=manager_binary["failures"][:20]))
    except (OSError, ValueError, SemanticQaError) as exc:
        manager_binary = {"failure_count": 1, "error": str(exc)}
        blockers.append(_issue("compiled-manager-audit-error", "compiled manager graph could not be audited", error=str(exc)))
    try:
        handling_binary = audit_compiled_handling(package, game=game)
        if handling_binary["failure_count"]:
            blockers.append(_issue("compiled-handling-failed", "compiled Handling values or player ownership differ from the recipe", count=handling_binary["failure_count"], samples=handling_binary["failures"][:20], ownership_collisions=handling_binary["ownership_collisions"][:20]))
    except (OSError, ValueError, SemanticQaError) as exc:
        handling_binary = {"failure_count": 1, "error": str(exc)}
        blockers.append(_issue("compiled-handling-audit-error", "compiled player Handling could not be audited", error=str(exc)))
    try:
        nationality_binary = audit_compiled_nationalities(package, game=game)
        if nationality_binary["failure_count"]:
            blockers.append(_issue(
                "compiled-nationality-readback-failed",
                "compiled player nationality differs from the declared, representable recipe country",
                count=nationality_binary["failure_count"],
                samples=nationality_binary["failures"][:20],
            ))
        if nationality_binary["unrepresentable_nationality_count"]:
            warnings.append(_issue(
                "pm99-country-table-capacity-limit",
                "declared player nationality has no native PM99 TEXTOS country row and remains XXX",
                count=nationality_binary["unrepresentable_nationality_count"],
                samples=nationality_binary["unrepresentable_nationalities"][:20],
            ))
    except (OSError, ValueError, SemanticQaError, QaError) as exc:
        nationality_binary = {"failure_count": 1, "error": str(exc)}
        blockers.append(_issue("compiled-nationality-audit-error", "compiled player nationality could not be audited", error=str(exc)))

    receipt = audit_binary_receipt(season, game)
    if receipt["mismatch_count"]:
        blockers.append(_issue("compiler-output-hash-mismatch", "runtime database files differ from the compiler receipt", mismatches=receipt["mismatches"]))
    if receipt.get("warning"):
        warnings.append(_issue("compiler-receipt-missing", str(receipt["warning"])))
    calendar = audit_calendar(season, game)
    if not calendar["passed"]:
        blockers.append(_issue("calendar-mismatch", "gameplay executable does not match the season calendar input", **calendar))
    runtime = audit_runtime(season)
    if not runtime["passed"]:
        blockers.append(_issue("matching-calendar-runtime-proof-failed", "matching-calendar runner evidence did not reach Line-Up", **runtime))
    kits = audit_kit_outputs(season, game)
    if kits["byte_or_format_failure_count"]:
        blockers.append(_issue("compiled-kit-readback-failed", "compiled compact-kit archives differ from their receipt or contain an unexpected bitmap format", count=kits["byte_or_format_failure_count"], samples=kits["failures"][:20]))
    if kits["visual_review_missing"]:
        warnings.append(_issue("kit-visual-proof-missing", "kit archives pass automated checks but lack explicit visual approval", patched_carrier_count=kits["patched_carrier_count"]))

    return {
        "schema_version": SCHEMA,
        "season": season,
        "classification": "release-quality-gate",
        "result": "pass" if not blockers else "fail",
        "summary": {"blocker_count": len(blockers), "warning_count": len(warnings)},
        "inputs": {"game_tree": str(game.relative_to(ROOT)), "package": str(package_path.relative_to(ROOT)), "package_sha256": _sha256(package_path)},
        "checks": {
            "availability": availability,
            "compiled_birth_dates": birth_dates_binary,
            "package_validation": package_validation,
            "manager_sources": manager_sources,
            "recipe": recipe,
            "player_identity": player_identity,
            "compiled_managers": manager_binary,
            "compiled_handling": handling_binary,
            "compiled_nationalities": nationality_binary,
            "compiled_player_identities": identity_binary,
            "compiler_receipt": receipt,
            "compiled_fine_roles": roles_binary,
            "tactics_deployment_review": deployment,
            "calendar": calendar,
            "runtime": runtime,
            "kits": kits,
        },
        "blockers": blockers,
        "warnings": warnings,
    }


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", help="YYYY-YY or all")
    parser.add_argument("--output-root", type=Path, default=ROOT / ".local/season-qa-v1")
    parser.add_argument("--jobs", type=int, default=None, help="parallel season audits (default: 4 for all, otherwise 1)")
    args = parser.parse_args(argv)
    seasons = SEASONS if args.season == "all" else [args.season]
    unknown = [season for season in seasons if season not in SEASONS]
    if unknown:
        parser.error(f"unsupported season: {unknown[0]}")
    jobs = args.jobs if args.jobs is not None else (4 if len(seasons) > 1 else 1)
    if jobs < 1:
        parser.error("--jobs must be at least 1")

    def completed_report(season: str, report: dict[str, Any]) -> dict[str, Any]:
        _write(args.output_root / season / "qa-report.json", report)
        print(json.dumps({"season": season, "result": report["result"], **report["summary"]}, sort_keys=True), flush=True)
        return report

    def run_one(season: str) -> dict[str, Any]:
        try:
            return audit_season(season)
        except (OSError, QaError, ValueError) as exc:
            return {
                "schema_version": SCHEMA,
                "season": season,
                "classification": "release-quality-gate",
                "result": "fail",
                "summary": {"blocker_count": 1, "warning_count": 0},
                "blockers": [_issue("qa-execution-error", "season QA could not complete", error=str(exc))],
                "warnings": [],
            }

    reports_by_season: dict[str, dict[str, Any]] = {}
    if jobs == 1:
        for season in seasons:
            reports_by_season[season] = completed_report(season, run_one(season))
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=min(jobs, len(seasons))) as executor:
            future_by_season = {executor.submit(audit_season, season): season for season in seasons}
            for future in concurrent.futures.as_completed(future_by_season):
                season = future_by_season[future]
                try:
                    report = future.result()
                except (OSError, QaError, ValueError) as exc:
                    report = {
                        "schema_version": SCHEMA,
                        "season": season,
                        "classification": "release-quality-gate",
                        "result": "fail",
                        "summary": {"blocker_count": 1, "warning_count": 0},
                        "blockers": [_issue("qa-execution-error", "season QA could not complete", error=str(exc))],
                        "warnings": [],
                    }
                reports_by_season[season] = completed_report(season, report)

    reports = [reports_by_season[season] for season in seasons]
    aggregate = {
        "schema_version": "pm99-season-quality-qa-batch-v1",
        "result": "pass" if all(row["result"] == "pass" for row in reports) else "fail",
        "season_count": len(reports),
        "passed_season_count": sum(row["result"] == "pass" for row in reports),
        "failed_season_count": sum(row["result"] != "pass" for row in reports),
        "blocker_count": sum(int(row["summary"]["blocker_count"]) for row in reports),
        "warning_count": sum(int(row["summary"]["warning_count"]) for row in reports),
        "seasons": [{"season": row["season"], "result": row["result"], **row["summary"]} for row in reports],
    }
    _write(args.output_root / "qa-report.json", aggregate)
    print(json.dumps(aggregate, indent=2, sort_keys=True))
    return 0 if aggregate["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
