#!/usr/bin/env python3
"""Materialise only mechanically-safe source-club selection manifests.

The collision proposal report is intentionally a human-review queue.  This
tool consumes that immutable queue under a narrower, explicit policy which is
safe to apply without a second ownership judgement:

* exactly two hash-bound source selectors have one of the report's direct
  duplicate-label signals;
* exactly one is a Soccerbase ``/august`` source and exactly one is a
  non-August source;
* the non-August selector is uniquely present as the canonical allocated club
  in the immutable carrier allocation; and
* neither selector occurs in any reported ambiguous player/inter-club overlap.

The generated manifests use the existing
``pm99-season-source-club-selection-manifest-v1`` schema.  They preserve the
raw source intake and credits by binding the exact intake and capture hashes;
they never rewrite that intake, an allocation, a package, or a binary.  A
manifest is still a provisional source-authoring input, not a release claim.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_source_club_selection_proposals_v1 as proposals  # noqa: E402
from scripts import season_source_club_selection_v1 as source_selection  # noqa: E402


SCHEMA = "pm99-season-safe-source-club-selection-receipt-v1"
STATE = "safe-selection-manifests-provisional-not-release"
EXCLUSION_SCHEMA = "pm99-season-safe-source-club-selection-exclusion-manifest-v1"
MANIFEST_FILENAME = "selection-manifest.json"
SELECTION_ID_PREFIX = "safe-source-club-selection"
SELECTION_ENTRY_PREFIX = "safe-"
OPENING_COMPETITION = "soccerbase-august"
OPENING_PATH_RE = re.compile(r"^soccerbase/team/[1-9][0-9]*/august$")
SAFE_SIGNAL_METHODS = {
    "organisation-and-abbreviation-normalised-label-equality",
    "bare-name-versus-terminal-generic-club-suffix",
}
ALLOCATION_SELECTOR_FIELDS = {
    "competition_catalog",
    "country_catalog",
    "source_path",
    "source_sha256",
}
EXCLUSION_ROOT_FIELDS = {"schema_version", "policy_id", "inputs", "exclusions"}
EXCLUSION_INPUT_FIELDS = {"proposal_report_sha256", "collision_matrix_sha256"}
EXCLUSION_FIELDS = {
    "id",
    "reason",
    "proposal_id",
    "season",
    "source_intake_sha256",
    "source_capture_sha256",
    "source_selectors",
    "person_claims",
}
EXCLUSION_PERSON_FIELDS = {"name", "birth_date", "nationality"}


class SafeSelectionError(ValueError):
    """The hash-bound inputs cannot safely yield selection manifests."""


def canonical_json_bytes(value: Any) -> bytes:
    """Use the canonical JSON bytes shared by package and source artifacts."""

    return package_v2.canonical_json_bytes(value)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_value(value: Any) -> str:
    return _sha256_bytes(canonical_json_bytes(value))


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _read_canonical(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SafeSelectionError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise SafeSelectionError(f"{label} must be canonical UTF-8 JSON: {path}")
    return value, _sha256_bytes(raw)


def _season_id(season: Mapping[str, Any]) -> str:
    start_year = season.get("start_year")
    end_year = season.get("end_year")
    if not isinstance(start_year, int) or not isinstance(end_year, int):
        raise SafeSelectionError("proposal season must have integer start_year and end_year")
    if end_year != start_year + 1:
        raise SafeSelectionError("proposal season must span exactly one rollover year")
    return f"{start_year}-{end_year % 100:02d}"


def _selector_key(selector: object, *, label: str) -> tuple[str, str, str, str, str]:
    return source_selection._selector_key(selector, label=label)


def _selector_value(selector: Mapping[str, Any]) -> dict[str, str]:
    return source_selection._selector_value(selector)


def _selector_sort_key(selector: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return _selector_key(selector, label="source selector")


def _opening_selector(selector: Mapping[str, Any]) -> bool:
    """Accept only the explicit August capture form used in this source family."""

    return (
        selector.get("competition_catalog") == OPENING_COMPETITION
        and isinstance(selector.get("source_path"), str)
        and OPENING_PATH_RE.fullmatch(str(selector["source_path"])) is not None
    )


def _allocation_selector_key(selector: object, *, label: str) -> tuple[str, str, str, str]:
    if not isinstance(selector, Mapping) or set(selector) != ALLOCATION_SELECTOR_FIELDS:
        raise SafeSelectionError(
            f"{label} must contain exactly {sorted(ALLOCATION_SELECTOR_FIELDS)}"
        )
    values: list[str] = []
    for field in ("competition_catalog", "country_catalog", "source_path", "source_sha256"):
        value = selector.get(field)
        if not isinstance(value, str) or not value:
            raise SafeSelectionError(f"{label}.{field} must be a non-blank string")
        values.append(value)
    if not package_v2.SHA256_RE.fullmatch(values[3]):
        raise SafeSelectionError(f"{label}.source_sha256 must be a lowercase SHA-256")
    return tuple(values)  # type: ignore[return-value]


def _selector_allocation_key(selector: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(selector["competition_catalog"]),
        str(selector["country_catalog"]),
        str(selector["source_path"]),
        str(selector["source_sha256"]),
    )


def _allocation_matches(
    allocation: Mapping[str, Any], canonical_selector: Mapping[str, Any], *, label: str,
) -> list[dict[str, Any]]:
    assignments = allocation.get("assignments")
    if not isinstance(assignments, list):
        raise SafeSelectionError(f"{label}.assignments must be a list")
    expected = _selector_allocation_key(canonical_selector)
    matches: list[dict[str, Any]] = []
    for index, raw in enumerate(assignments):
        if not isinstance(raw, Mapping):
            raise SafeSelectionError(f"{label}.assignments[{index}] must be an object")
        selector = raw.get("source_selector")
        if _allocation_selector_key(selector, label=f"{label}.assignments[{index}].source_selector") != expected:
            continue
        if raw.get("club_name") != canonical_selector.get("club_name"):
            continue
        carrier_id = raw.get("carrier_id")
        if not isinstance(carrier_id, int) or carrier_id < 1:
            raise SafeSelectionError(f"{label}.assignments[{index}].carrier_id must be a positive integer")
        matches.append({
            "allocation_method": raw.get("method"),
            "carrier_id": carrier_id,
            "club_name": raw["club_name"],
        })
    matches.sort(key=lambda item: (item["carrier_id"], str(item["allocation_method"])))
    return matches


def _proposal_evidence_is_exact(
    proposal: Mapping[str, Any], selector_keys: set[tuple[str, str, str, str, str]], *, label: str,
) -> tuple[bool, int]:
    """Require each supporting same-person item to trace exactly the pair."""

    evidence = proposal.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return False, 0
    for evidence_index, item in enumerate(evidence):
        if not isinstance(item, Mapping):
            return False, 0
        rows = item.get("source_rows")
        if not isinstance(rows, list) or len(rows) != 2:
            return False, 0
        row_keys: set[tuple[str, str, str, str, str]] = set()
        for row_index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                return False, 0
            try:
                selector_key = _selector_key(
                    row.get("selector"),
                    label=f"{label}.evidence[{evidence_index}].source_rows[{row_index}].selector",
                )
            except source_selection.SourceClubSelectionError:
                return False, 0
            row_digest = row.get("source_row_sha256")
            if not isinstance(row_digest, str) or not package_v2.SHA256_RE.fullmatch(row_digest):
                return False, 0
            row_keys.add(selector_key)
        if row_keys != selector_keys:
            return False, 0
    return True, len(evidence)


def _ambiguous_selector_keys(season: Mapping[str, Any]) -> set[tuple[str, str, str, str, str]]:
    ambiguous = season.get("ambiguous_player_overlaps")
    if not isinstance(ambiguous, list):
        raise SafeSelectionError("proposal season ambiguous_player_overlaps must be a list")
    result: set[tuple[str, str, str, str, str]] = set()
    for proposal_index, proposal in enumerate(ambiguous):
        if not isinstance(proposal, Mapping):
            raise SafeSelectionError(f"ambiguous proposal {proposal_index} must be an object")
        selectors = proposal.get("source_selectors")
        if not isinstance(selectors, list) or len(selectors) < 2:
            raise SafeSelectionError(f"ambiguous proposal {proposal_index} has malformed source selectors")
        for selector_index, selector in enumerate(selectors):
            result.add(_selector_key(
                selector,
                label=f"ambiguous proposal {proposal_index}.source_selectors[{selector_index}]",
            ))
    return result


def _source_person_keys(source_row: Mapping[str, Any]) -> set[tuple[str, str, str]]:
    facts = source_row.get("facts")
    if not isinstance(facts, Mapping):
        return set()
    name = facts.get("name")
    birth_date = facts.get("birth_date")
    nationality = facts.get("nationality")
    if not all(isinstance(value, str) and value for value in (name, birth_date, nationality)):
        return set()
    return {(str(name), str(birth_date), str(nationality))}


def _exclusion_person_claims(raw: object, *, label: str) -> set[tuple[str, str, str]]:
    if not isinstance(raw, list) or not raw:
        raise SafeSelectionError(f"{label}.person_claims must be a non-empty list")
    result: set[tuple[str, str, str]] = set()
    for index, person in enumerate(raw):
        if not isinstance(person, Mapping) or set(person) != EXCLUSION_PERSON_FIELDS:
            raise SafeSelectionError(
                f"{label}.person_claims[{index}] must contain exactly {sorted(EXCLUSION_PERSON_FIELDS)}"
            )
        values: list[str] = []
        for field in ("name", "birth_date", "nationality"):
            value = person.get(field)
            if not isinstance(value, str) or not value:
                raise SafeSelectionError(f"{label}.person_claims[{index}].{field} must be non-blank text")
            values.append(value)
        key = tuple(values)  # type: ignore[assignment]
        if key in result:
            raise SafeSelectionError(f"{label} repeats a person claim")
        result.add(key)
    return result


def _validated_exclusions(
    *, exclusion_manifest: Mapping[str, Any], exclusion_manifest_sha256: str,
    proposal_report_sha256: str, collision_matrix_sha256: str,
    proposal_report: Mapping[str, Any], source_intakes: Mapping[str, tuple[Mapping[str, Any], str]],
) -> tuple[dict[str, dict[tuple[tuple[str, str, str, str, str], ...], dict[str, Any]]], dict[str, Any]]:
    """Validate explicit known conflicts before they can block automatic output.

    This is deliberately an exclusion, never a second route to selection.  It
    must name the exact report proposal, source pair and people which caused
    the prior review decision, and bind the current raw source hashes.
    """

    if set(exclusion_manifest) != EXCLUSION_ROOT_FIELDS:
        raise SafeSelectionError(f"exclusion manifest must contain exactly {sorted(EXCLUSION_ROOT_FIELDS)}")
    if exclusion_manifest.get("schema_version") != EXCLUSION_SCHEMA:
        raise SafeSelectionError(f"exclusion manifest schema must be {EXCLUSION_SCHEMA!r}")
    policy_id = exclusion_manifest.get("policy_id")
    if not isinstance(policy_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,79}", policy_id):
        raise SafeSelectionError("exclusion manifest policy_id must be a lower-case stable id")
    inputs = exclusion_manifest.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != EXCLUSION_INPUT_FIELDS:
        raise SafeSelectionError(f"exclusion manifest inputs must contain exactly {sorted(EXCLUSION_INPUT_FIELDS)}")
    if inputs.get("proposal_report_sha256") != proposal_report_sha256:
        raise SafeSelectionError("exclusion manifest does not bind the supplied proposal report")
    if inputs.get("collision_matrix_sha256") != collision_matrix_sha256:
        raise SafeSelectionError("exclusion manifest does not bind the supplied collision matrix")
    exclusions = exclusion_manifest.get("exclusions")
    if not isinstance(exclusions, list):
        raise SafeSelectionError("exclusion manifest exclusions must be a list")
    report_proposals: dict[tuple[str, str], Mapping[str, Any]] = {}
    report_seasons = proposal_report.get("seasons")
    if not isinstance(report_seasons, list):
        raise SafeSelectionError("proposal report has no seasons")
    for report_season in report_seasons:
        if not isinstance(report_season, Mapping) or not isinstance(report_season.get("season"), Mapping):
            raise SafeSelectionError("proposal report season is malformed")
        label = report_season["season"].get("label")
        direct = report_season.get("direct_label_normalised_alias_candidates")
        if not isinstance(label, str) or not isinstance(direct, list):
            raise SafeSelectionError("proposal report direct queue is malformed")
        for proposal in direct:
            if not isinstance(proposal, Mapping) or not isinstance(proposal.get("proposal_id"), str):
                raise SafeSelectionError("proposal report direct proposal lacks an id")
            report_proposals[(label, proposal["proposal_id"])] = proposal

    result: dict[str, dict[tuple[tuple[str, str, str, str, str], ...], dict[str, Any]]] = {}
    manifest_rows: list[dict[str, Any]] = []
    previous_id: str | None = None
    for index, raw in enumerate(exclusions):
        label = f"exclusion manifest exclusions[{index}]"
        if not isinstance(raw, Mapping) or set(raw) != EXCLUSION_FIELDS:
            raise SafeSelectionError(f"{label} must contain exactly {sorted(EXCLUSION_FIELDS)}")
        exclusion_id = raw.get("id")
        if not isinstance(exclusion_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,79}", exclusion_id):
            raise SafeSelectionError(f"{label}.id must be a lower-case stable id")
        if previous_id is not None and exclusion_id <= previous_id:
            raise SafeSelectionError("exclusion ids must be unique and sorted lexicographically")
        previous_id = exclusion_id
        reason = raw.get("reason")
        if not isinstance(reason, str) or not reason:
            raise SafeSelectionError(f"{label}.reason must be non-blank text")
        season = raw.get("season")
        if not isinstance(season, Mapping) or set(season) != {"catalog", "label"}:
            raise SafeSelectionError(f"{label}.season must contain exactly catalog and label")
        catalog = season.get("catalog")
        season_label = season.get("label")
        if not isinstance(catalog, str) or not isinstance(season_label, str):
            raise SafeSelectionError(f"{label}.season fields must be text")
        source_intake, source_intake_sha256 = source_intakes.get(season_label, ({}, ""))
        if not source_intake:
            raise SafeSelectionError(f"{label} targets a season absent from the proposal report")
        if raw.get("source_intake_sha256") != source_intake_sha256:
            raise SafeSelectionError(f"{label} source intake hash is stale")
        if raw.get("source_capture_sha256") != source_intake.get("source_capture_sha256"):
            raise SafeSelectionError(f"{label} source capture hash is stale")
        source_season = source_intake.get("season")
        if not isinstance(source_season, Mapping) or dict(season) != dict(source_season):
            raise SafeSelectionError(f"{label} season does not match the raw source intake")
        proposal_id = raw.get("proposal_id")
        proposal = report_proposals.get((season_label, proposal_id)) if isinstance(proposal_id, str) else None
        if proposal is None:
            raise SafeSelectionError(f"{label} must reference one direct proposal from its season")
        selectors_raw = raw.get("source_selectors")
        if not isinstance(selectors_raw, list) or len(selectors_raw) != 2:
            raise SafeSelectionError(f"{label}.source_selectors must contain exactly two selectors")
        selectors = [_selector_value(item) for item in selectors_raw if isinstance(item, Mapping)]
        if len(selectors) != 2:
            raise SafeSelectionError(f"{label}.source_selectors are malformed")
        selector_pair = tuple(sorted(_selector_sort_key(item) for item in selectors))
        if len(set(selector_pair)) != 2:
            raise SafeSelectionError(f"{label}.source_selectors must differ")
        proposal_selectors = proposal.get("source_selectors")
        if not isinstance(proposal_selectors, list):
            raise SafeSelectionError(f"{label} proposal source selectors are malformed")
        proposal_pair = tuple(sorted(_selector_key(item, label=f"{label}.proposal selector") for item in proposal_selectors))
        if selector_pair != proposal_pair:
            raise SafeSelectionError(f"{label} source selector pair differs from the report proposal")
        claims = _exclusion_person_claims(raw.get("person_claims"), label=label)
        try:
            source_by_selector, _source_order = source_selection._source_clubs(source_intake)
        except source_selection.SourceClubSelectionError as exc:
            raise SafeSelectionError(f"{label} cannot validate source intake: {exc}") from exc
        for selector in selectors:
            source_row = source_by_selector.get(_selector_sort_key(selector))
            if source_row is None:
                raise SafeSelectionError(f"{label} selector is absent from source intake")
            available: set[tuple[str, str, str]] = set()
            for player in source_row["players"]:
                if isinstance(player, Mapping):
                    available.update(_source_person_keys(player))
            if not claims <= available:
                raise SafeSelectionError(f"{label} person claims are absent from selector {selector['club_name']!r}")
        row = {
            "exclusion_id": exclusion_id,
            "person_claim_count": len(claims),
            "proposal_id": proposal_id,
            "reason": reason,
            "source_selector_club_names": [selector["club_name"] for selector in sorted(selectors, key=_selector_sort_key)],
        }
        per_season = result.setdefault(season_label, {})
        if selector_pair in per_season:
            raise SafeSelectionError(f"{label} repeats a source selector pair")
        per_season[selector_pair] = row
        manifest_rows.append({"season": copy.deepcopy(dict(season)), **row})
    return result, {
        "path": None,
        "policy_id": policy_id,
        "sha256": exclusion_manifest_sha256,
        "validated_exclusion_count": len(manifest_rows),
        "validated_exclusions": manifest_rows,
    }


def _selection_entry_id(proposal: Mapping[str, Any]) -> str:
    proposal_id = proposal.get("proposal_id")
    if not isinstance(proposal_id, str) or not proposal_id.startswith("source-club-review-"):
        raise SafeSelectionError("direct proposal has no stable source-club review id")
    suffix = proposal_id.removeprefix("source-club-review-")
    if not re.fullmatch(r"[0-9a-f]{20}", suffix):
        raise SafeSelectionError("direct proposal id has an unsupported digest form")
    return f"{SELECTION_ENTRY_PREFIX}{suffix}"


def _candidate_or_rejection(
    *, proposal: Mapping[str, Any], allocation: Mapping[str, Any], ambiguous_keys: set[tuple[str, str, str, str, str]],
    exclusion_by_pair: Mapping[tuple[tuple[str, str, str, str, str], ...], Mapping[str, Any]], label: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Turn one direct proposal into a selection only when every rule proves out."""

    proposal_id = proposal.get("proposal_id")
    if not isinstance(proposal_id, str):
        raise SafeSelectionError(f"{label} direct proposal id must be text")
    selectors_raw = proposal.get("source_selectors")
    if not isinstance(selectors_raw, list) or len(selectors_raw) != 2:
        return None, {"proposal_id": proposal_id, "reason": "not-exactly-two-source-selectors"}
    try:
        selectors = [_selector_value(selector) for selector in selectors_raw if isinstance(selector, Mapping)]
    except source_selection.SourceClubSelectionError:
        return None, {"proposal_id": proposal_id, "reason": "malformed-source-selector"}
    if len(selectors) != 2:
        return None, {"proposal_id": proposal_id, "reason": "malformed-source-selector"}
    selector_keys = {_selector_sort_key(selector) for selector in selectors}
    if len(selector_keys) != 2:
        return None, {"proposal_id": proposal_id, "reason": "duplicate-source-selector"}
    signal = proposal.get("direct_label_normalised_alias_signal")
    method = signal.get("method") if isinstance(signal, Mapping) else None
    if method not in SAFE_SIGNAL_METHODS:
        return None, {"proposal_id": proposal_id, "reason": "unsupported-direct-duplicate-label-signal"}
    selector_pair = tuple(sorted(selector_keys))
    exclusion = exclusion_by_pair.get(selector_pair)
    if exclusion is not None:
        return None, {
            "exclusion_id": exclusion["exclusion_id"],
            "proposal_id": proposal_id,
            "reason": "known-interclub-conflict-explicitly-excluded-from-auto-selection",
        }
    opening = [selector for selector in selectors if _opening_selector(selector)]
    canonical = [selector for selector in selectors if not _opening_selector(selector)]
    if len(opening) != 1 or len(canonical) != 1:
        return None, {"proposal_id": proposal_id, "reason": "not-one-explicit-august-and-one-non-august-source"}
    if selector_keys & ambiguous_keys:
        return None, {"proposal_id": proposal_id, "reason": "selector-occurs-in-ambiguous-player-interclub-overlap"}
    exact_evidence, evidence_count = _proposal_evidence_is_exact(
        proposal, selector_keys, label=label,
    )
    if not exact_evidence:
        return None, {"proposal_id": proposal_id, "reason": "direct-same-person-evidence-is-not-exactly-the-selector-pair"}
    allocation_matches = _allocation_matches(allocation, canonical[0], label=label)
    if len(allocation_matches) != 1:
        return None, {
            "proposal_id": proposal_id,
            "reason": "canonical-source-is-not-a-unique-exact-allocated-club",
            "matching_allocated_carrier_count": len(allocation_matches),
        }
    selection = {
        "basis": source_selection.SELECTION_BASIS,
        "canonical_selector": canonical[0],
        "id": _selection_entry_id(proposal),
        "selected_selector": opening[0],
    }
    audit = {
        "allocated_canonical_club": allocation_matches[0],
        "direct_duplicate_label_method": method,
        "exact_same_person_evidence_count": evidence_count,
        "proposal_id": proposal_id,
        "selection_id": selection["id"],
    }
    return selection, audit


def _source_intake_manifest(
    *, season: Mapping[str, Any], source_intake: Mapping[str, Any], source_intake_sha256: str,
    selections: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    source_season = source_intake.get("season")
    if not isinstance(source_season, Mapping):
        raise SafeSelectionError("source intake has no season")
    expected_label = season.get("label")
    if source_season.get("label") != expected_label:
        raise SafeSelectionError("source intake season does not match proposal season")
    catalog = source_season.get("catalog")
    label = source_season.get("label")
    capture_sha256 = source_intake.get("source_capture_sha256")
    if not isinstance(catalog, str) or not isinstance(label, str) or not isinstance(capture_sha256, str):
        raise SafeSelectionError("source intake has malformed manifest provenance")
    manifest = {
        "inputs": {
            "source_capture_sha256": capture_sha256,
            "source_intake_sha256": source_intake_sha256,
        },
        "schema_version": source_selection.MANIFEST_SCHEMA,
        "season": {"catalog": catalog, "label": label},
        "selection_id": f"{SELECTION_ID_PREFIX}-{_season_id(season)}",
        "selections": [copy.deepcopy(dict(item)) for item in sorted(selections, key=lambda item: str(item["id"]))],
    }
    try:
        source_selection.validate_manifest(manifest=manifest, source_intake=source_intake)
    except source_selection.SourceClubSelectionError as exc:
        raise SafeSelectionError(f"generated source-selection manifest is invalid: {exc}") from exc
    return manifest


def build_safe_manifests(
    *, proposal_report: Mapping[str, Any], proposal_report_path: Path, proposal_report_sha256: str,
    collision_matrix: Mapping[str, Any], collision_matrix_path: Path, collision_matrix_sha256: str,
    exclusion_manifest: Mapping[str, Any], exclusion_manifest_path: Path, exclusion_manifest_sha256: str,
    intake_root: Path, allocation_root: Path, expected_season_count: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Build source-only manifests and a receipt, without writing any artifacts."""

    try:
        proposals.validate_report(proposal_report, expected_season_count=expected_season_count)
    except proposals.ProposalError as exc:
        raise SafeSelectionError(f"proposal report failed validation: {exc}") from exc
    report_matrix = proposal_report.get("input_collision_matrix")
    if not isinstance(report_matrix, Mapping):
        raise SafeSelectionError("proposal report lacks collision-matrix provenance")
    if report_matrix.get("sha256") != collision_matrix_sha256:
        raise SafeSelectionError("proposal report does not bind the supplied collision matrix")
    if collision_matrix.get("schema_version") != proposals.MATRIX_SCHEMA or collision_matrix.get("state") != proposals.MATRIX_STATE:
        raise SafeSelectionError("collision matrix has an unsupported schema or state")

    source_intakes: dict[str, tuple[Mapping[str, Any], str]] = {}
    seasons = proposal_report["seasons"]
    assert isinstance(seasons, list)  # established by validate_report above
    for season_index, report_season in enumerate(seasons):
        if not isinstance(report_season, Mapping):
            raise SafeSelectionError(f"proposal report season {season_index} must be an object")
        season = report_season.get("season")
        build_audit = report_season.get("build_audit")
        if not isinstance(season, Mapping) or not isinstance(build_audit, Mapping):
            raise SafeSelectionError(f"proposal report season {season_index} has incomplete provenance")
        season_id = _season_id(season)
        source_intake, source_intake_sha256 = _read_canonical(
            intake_root / season_id / "source-intake.json", f"{season_id} source intake",
        )
        if build_audit.get("source_intake_sha256") != source_intake_sha256:
            raise SafeSelectionError(f"{season_id} source intake does not match proposal build-audit hash")
        source_label = source_intake.get("season", {}).get("label") if isinstance(source_intake.get("season"), Mapping) else None
        if not isinstance(source_label, str) or source_label in source_intakes:
            raise SafeSelectionError(f"{season_id} source intake season label is missing or duplicated")
        source_intakes[source_label] = (source_intake, source_intake_sha256)
    exclusions_by_season, exclusion_audit = _validated_exclusions(
        exclusion_manifest=exclusion_manifest,
        exclusion_manifest_sha256=exclusion_manifest_sha256,
        proposal_report_sha256=proposal_report_sha256,
        collision_matrix_sha256=collision_matrix_sha256,
        proposal_report=proposal_report,
        source_intakes=source_intakes,
    )
    exclusion_audit["path"] = _relative(exclusion_manifest_path)

    manifest_by_season: dict[str, dict[str, Any]] = {}
    receipts: list[dict[str, Any]] = []
    summary: Counter[str] = Counter()
    for season_index, report_season in enumerate(seasons):
        if not isinstance(report_season, Mapping):
            raise SafeSelectionError(f"proposal report season {season_index} must be an object")
        season = report_season.get("season")
        if not isinstance(season, Mapping):
            raise SafeSelectionError(f"proposal report season {season_index} has no season object")
        season_id = _season_id(season)
        intake_path = intake_root / season_id / "source-intake.json"
        allocation_path = allocation_root / season_id / "carrier-allocation.json"
        season_label = season.get("label")
        if not isinstance(season_label, str):
            raise SafeSelectionError(f"{season_id} proposal season has no label")
        source_intake, source_intake_sha256 = source_intakes[season_label]
        allocation, allocation_sha256 = _read_canonical(allocation_path, f"{season_id} carrier allocation")
        build_audit = report_season.get("build_audit")
        if allocation.get("source_sha256") != source_intake.get("source_capture_sha256"):
            raise SafeSelectionError(f"{season_id} carrier allocation does not bind the source intake capture")

        ambiguous_keys = _ambiguous_selector_keys(report_season)
        direct = report_season.get("direct_label_normalised_alias_candidates")
        ambiguous = report_season.get("ambiguous_player_overlaps")
        if not isinstance(direct, list) or not isinstance(ambiguous, list):
            raise SafeSelectionError(f"{season_id} proposal queues are malformed")
        safe_entries: list[dict[str, Any]] = []
        safe_audit: list[dict[str, Any]] = []
        rejected_direct: list[dict[str, Any]] = []
        for proposal_index, proposal in enumerate(direct):
            if not isinstance(proposal, Mapping):
                raise SafeSelectionError(f"{season_id} direct proposal {proposal_index} must be an object")
            entry, entry_audit = _candidate_or_rejection(
                proposal=proposal,
                allocation=allocation,
                ambiguous_keys=ambiguous_keys,
                exclusion_by_pair=exclusions_by_season.get(season_label, {}),
                label=f"{season_id}.direct[{proposal_index}]",
            )
            if entry is None:
                assert entry_audit is not None
                rejected_direct.append(entry_audit)
            else:
                assert entry_audit is not None
                safe_entries.append(entry)
                safe_audit.append(entry_audit)
        safe_entries.sort(key=lambda item: str(item["id"]))
        safe_audit.sort(key=lambda item: str(item["selection_id"]))
        rejected_direct.sort(key=lambda item: str(item["proposal_id"]))
        manifest = _source_intake_manifest(
            season=season,
            source_intake=source_intake,
            source_intake_sha256=source_intake_sha256,
            selections=safe_entries,
        )
        manifest_sha256 = _sha256_value(manifest)
        manifest_by_season[season_id] = manifest
        rejected_ambiguous = []
        for proposal in ambiguous:
            if not isinstance(proposal, Mapping) or not isinstance(proposal.get("proposal_id"), str):
                raise SafeSelectionError(f"{season_id} ambiguous proposal lacks a stable id")
            rejected_ambiguous.append({
                "proposal_id": proposal["proposal_id"],
                "reason": "ambiguous-player-interclub-overlap-never-auto-selected",
            })
        rejected_ambiguous.sort(key=lambda item: item["proposal_id"])
        receipts.append({
            "carrier_allocation": {
                "path": _relative(allocation_path),
                "sha256": allocation_sha256,
            },
            "generated_manifest": {
                "relative_path": f"{season_id}/{MANIFEST_FILENAME}",
                "sha256": manifest_sha256,
            },
            "excluded_known_interclub_conflicts": sorted(
                exclusions_by_season.get(season_label, {}).values(),
                key=lambda item: str(item["exclusion_id"]),
            ),
            "rejected_ambiguous_player_interclub_overlaps": rejected_ambiguous,
            "rejected_direct_alias_candidates": rejected_direct,
            "safe_selections": safe_audit,
            "season": copy.deepcopy(dict(season)),
            "source_intake": {
                "path": _relative(intake_path),
                "sha256": source_intake_sha256,
                "source_capture_sha256": source_intake.get("source_capture_sha256"),
            },
        })
        summary["season_count"] += 1
        summary["direct_alias_candidate_count"] += len(direct)
        summary["safe_selection_count"] += len(safe_entries)
        summary["rejected_direct_alias_candidate_count"] += len(rejected_direct)
        summary["excluded_known_interclub_conflict_count"] += len(
            exclusions_by_season.get(season_label, {})
        )
        summary["rejected_ambiguous_player_interclub_overlap_count"] += len(rejected_ambiguous)
        if safe_entries:
            summary["season_with_safe_selection_count"] += 1
    receipt = {
        "input_collision_matrix": {
            "path": _relative(collision_matrix_path),
            "sha256": collision_matrix_sha256,
        },
        "input_proposal_report": {
            "path": _relative(proposal_report_path),
            "sha256": proposal_report_sha256,
        },
        "input_exclusion_manifest": exclusion_audit,
        "not_performed": [
            "raw source capture or source-intake mutation",
            "source-credit mutation",
            "carrier-allocation mutation",
            "draft-package or fixed-carrier mutation",
            "ambiguous player or inter-club ownership decision",
            "database compilation",
            "static or runtime validation",
            "playable-game or screenshot assertion",
        ],
        "policy": {
            "canonical_source_requirement": "one unique exact carrier-allocation assignment with the same source selector and club name",
            "direct_duplicate_label_methods": sorted(SAFE_SIGNAL_METHODS),
            "opening_source_requirement": "exactly one selector with competition_catalog soccerbase-august and source_path soccerbase/team/<id>/august",
            "overlap_requirement": "neither selector may occur in any ambiguous-player-interclub-overlap item",
        },
        "schema_version": SCHEMA,
        "seasons": receipts,
        "state": STATE,
        "summary": dict(sorted(summary.items())),
    }
    return manifest_by_season, receipt


def _write_new(path: Path, value: Mapping[str, Any]) -> str:
    if path.exists() or path.is_symlink():
        raise SafeSelectionError(f"refusing to replace existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(value)
    path.write_bytes(payload)
    return _sha256_bytes(payload)


def write_safe_manifests(*, output_root: Path, manifests: Mapping[str, Mapping[str, Any]], receipt: Mapping[str, Any]) -> str:
    """Write a completely new manifest root, preserving all prior revisions."""

    if output_root.exists() or output_root.is_symlink():
        raise SafeSelectionError(f"refusing to overwrite safe-selection output root: {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)
    for season_id in sorted(manifests):
        _write_new(output_root / season_id / MANIFEST_FILENAME, manifests[season_id])
    return _write_new(output_root / "safe-selection-receipt.json", receipt)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--proposal-report", type=Path,
        default=ROOT / ".local" / "season-source-club-selection-proposals-v1" / "20260904-r1" / "proposal-report.json",
    )
    parser.add_argument(
        "--collision-matrix", type=Path,
        default=ROOT / ".local" / "season-source-collision-matrix-v1" / "20260904" / "collision-matrix.json",
    )
    parser.add_argument(
        "--exclusion-manifest", type=Path,
        default=ROOT / ".local" / "season-safe-source-club-selection-v1" / "known-interclub-exclusions-v1.json",
        help="canonical known-conflict exclusions which block automatic selection",
    )
    parser.add_argument(
        "--intake-root", type=Path,
        default=ROOT / ".local" / "season-historical-squad-backfill-v1",
    )
    parser.add_argument(
        "--allocation-root", type=Path,
        default=ROOT / ".local" / "season-historical-squad-backfill-v1",
    )
    parser.add_argument("--output-root", type=Path, help="new root for 25 manifests and one receipt")
    parser.add_argument("--expected-season-count", type=int, default=25)
    args = parser.parse_args(argv)
    try:
        if args.expected_season_count < 1:
            raise SafeSelectionError("expected season count must be positive")
        proposal_report_path = args.proposal_report.resolve()
        collision_matrix_path = args.collision_matrix.resolve()
        exclusion_manifest_path = args.exclusion_manifest.resolve()
        proposal_report, proposal_report_sha256 = _read_canonical(proposal_report_path, "proposal report")
        collision_matrix, collision_matrix_sha256 = _read_canonical(collision_matrix_path, "collision matrix")
        exclusion_manifest, exclusion_manifest_sha256 = _read_canonical(
            exclusion_manifest_path, "known-interclub exclusion manifest",
        )
        manifests, receipt = build_safe_manifests(
            proposal_report=proposal_report,
            proposal_report_path=proposal_report_path,
            proposal_report_sha256=proposal_report_sha256,
            collision_matrix=collision_matrix,
            collision_matrix_path=collision_matrix_path,
            collision_matrix_sha256=collision_matrix_sha256,
            exclusion_manifest=exclusion_manifest,
            exclusion_manifest_path=exclusion_manifest_path,
            exclusion_manifest_sha256=exclusion_manifest_sha256,
            intake_root=args.intake_root.resolve(),
            allocation_root=args.allocation_root.resolve(),
            expected_season_count=args.expected_season_count,
        )
        summary: dict[str, Any] = {
            "safe_selection_manifest_receipt_sha256": _sha256_value(receipt),
            "state": STATE,
            "summary": receipt["summary"],
        }
        if args.output_root is not None:
            output_root = args.output_root.resolve()
            summary["output_receipt_sha256"] = write_safe_manifests(
                output_root=output_root,
                manifests=manifests,
                receipt=receipt,
            )
            summary["output_root"] = _relative(output_root)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    except (OSError, SafeSelectionError, ValueError) as exc:
        print(f"safe source-club selection error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
