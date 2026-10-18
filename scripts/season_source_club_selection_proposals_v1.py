#!/usr/bin/env python3
"""Produce a deterministic, read-only human-review queue for source clubs.

The collision matrix records strict same-person conflicts in already authored
season packages.  A subset have a transparent club-label signal such as
``Kettering`` versus ``Kettering Town``.  That is useful evidence for a human
to review a possible all-season/opening-date source substitution, but it is
not evidence that either source owns the fixed carrier or that either source
is the dated opening squad.

This module groups those direct label-normalised signals into *review
proposals*.  It puts every source/source collision without that narrow signal
in a separate ambiguous-player-overlap queue.  Neither queue is a selection
manifest, and this module never writes an intake, package, allocation, or
binary.  A reviewer must create a separately hash-bound
``pm99-season-source-club-selection-manifest-v1`` only after checking dated
source evidence.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-season-source-club-selection-proposal-report-v1"
STATE = "read-only-human-review-proposals-not-selection"
MATRIX_SCHEMA = "pm99-season-source-collision-matrix-v1"
MATRIX_STATE = "read-only-source-current-collision-matrix"
SELECTION_MANIFEST_SCHEMA = "pm99-season-source-club-selection-manifest-v1"
SELECTION_BASIS = "opening-date-squad-authoritative"
SOURCE_SELECTOR_FIELDS = (
    "country_catalog",
    "competition_catalog",
    "club_name",
    "source_path",
    "source_sha256",
)
SHA256_RE = package_v2.SHA256_RE


class ProposalError(ValueError):
    """The collision matrix cannot safely produce the requested review queue."""


def canonical_json_bytes(value: Any) -> bytes:
    """Use the same canonical bytes as the season package and collision matrix."""

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


def _read_canonical_matrix(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProposalError(f"cannot read collision matrix {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProposalError("collision matrix root must be an object")
    if raw != canonical_json_bytes(value):
        raise ProposalError("collision matrix must be canonical UTF-8 JSON")
    if value.get("schema_version") != MATRIX_SCHEMA or value.get("state") != MATRIX_STATE:
        raise ProposalError("collision matrix has an unsupported schema or state")
    return value, _sha256_bytes(raw)


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ProposalError(f"{label} must be a lowercase SHA-256")
    return value


def _source_selector(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != set(SOURCE_SELECTOR_FIELDS):
        raise ProposalError(f"{label} must contain exactly the canonical source selector fields")
    result: dict[str, str] = {}
    for field in SOURCE_SELECTOR_FIELDS:
        raw = value.get(field)
        if not isinstance(raw, str) or not raw:
            raise ProposalError(f"{label}.{field} must be a non-blank string")
        result[field] = raw
    _require_sha256(result["source_sha256"], f"{label}.source_sha256")
    return result


def _selector_key(selector: Mapping[str, str]) -> tuple[str, str, str, str, str]:
    return tuple(selector[field] for field in SOURCE_SELECTOR_FIELDS)  # type: ignore[return-value]


def _candidate(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {
        "normalised_name", "birth_date", "nationality",
    }:
        raise ProposalError(f"{label} must contain exactly normalised_name, birth_date and nationality")
    result: dict[str, str] = {}
    for field in ("normalised_name", "birth_date", "nationality"):
        raw = value.get(field)
        if not isinstance(raw, str) or not raw:
            raise ProposalError(f"{label}.{field} must be a non-blank string")
        result[field] = raw
    return result


def _source_evidence(collision: Mapping[str, Any], label: str) -> list[dict[str, Any]]:
    """Return one exact, hash-bound source trace per current-source row.

    A proposal must never turn an imprecise trace into a possible selection.
    If a future collision matrix cannot trace a source row exactly, the report
    refuses it rather than accidentally presenting a guessed source selector.
    """

    rows = collision.get("rows")
    if not isinstance(rows, list):
        raise ProposalError(f"{label}.rows must be a list")
    result: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ProposalError(f"{label}.rows[{row_index}] must be an object")
        if row.get("role") != "current-source":
            continue
        trace = row.get("source_trace")
        if not isinstance(trace, Mapping) or trace.get("state") != "exact-source-row-match":
            raise ProposalError(
                f"{label}.rows[{row_index}] is current-source without one exact source trace"
            )
        matches = trace.get("matches")
        if not isinstance(matches, list) or len(matches) != 1 or not isinstance(matches[0], Mapping):
            raise ProposalError(
                f"{label}.rows[{row_index}] must have exactly one source row match for a proposal"
            )
        match = matches[0]
        selector = _source_selector(match.get("selector"), f"{label}.rows[{row_index}].selector")
        source_row_sha256 = _require_sha256(
            match.get("source_row_sha256"), f"{label}.rows[{row_index}].source_row_sha256"
        )
        player_id = row.get("id")
        person_id = row.get("person_id")
        if not isinstance(player_id, str) or not player_id or not isinstance(person_id, str) or not person_id:
            raise ProposalError(f"{label}.rows[{row_index}] lacks a stable package player/person id")
        mapped = trace.get("mapped_source_club_name")
        if mapped is not None and not isinstance(mapped, str):
            raise ProposalError(f"{label}.rows[{row_index}] mapped source club name must be text when present")
        result.append({
            "package_player_id": player_id,
            "person_id": person_id,
            "mapped_source_club_name": mapped,
            "selector": selector,
            "source_row_sha256": source_row_sha256,
        })
    if len(result) < 2:
        raise ProposalError(f"{label} is not a source/source collision")
    result.sort(key=lambda item: (
        _selector_key(item["selector"]), item["source_row_sha256"], item["package_player_id"]
    ))
    return result


def _signal(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"clubs", "method"}:
        raise ProposalError(f"{label} must contain exactly clubs and method")
    clubs = value.get("clubs")
    method = value.get("method")
    if (
        not isinstance(clubs, list)
        or len(clubs) != 2
        or not all(isinstance(club, str) and club for club in clubs)
        or not isinstance(method, str)
        or not method
    ):
        raise ProposalError(f"{label} is malformed")
    ordered_clubs = sorted(clubs)
    if ordered_clubs[0] == ordered_clubs[1]:
        raise ProposalError(f"{label}.clubs must name two different clubs")
    return {"clubs": ordered_clubs, "method": method}


def _source_source_collision(collision: Mapping[str, Any]) -> bool:
    return collision.get("classification") in {"source-source", "source-source-and-legacy"}


def _dedupe_evidence(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: dict[tuple[tuple[str, str, str, str, str], str, str], dict[str, Any]] = {}
    for row in rows:
        selector = row["selector"]
        key = (_selector_key(selector), str(row["source_row_sha256"]), str(row["package_player_id"]))
        result[key] = copy.deepcopy(dict(row))
    return [result[key] for key in sorted(result)]


def _selectors_from_evidence(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    selectors: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    for row in rows:
        selector = row["selector"]
        selectors[_selector_key(selector)] = copy.deepcopy(dict(selector))
    return [selectors[key] for key in sorted(selectors)]


def _direct_group_key(
    *, method: str, selectors: Sequence[Mapping[str, str]], season_label: str,
) -> tuple[str, str, tuple[tuple[str, str, str, str, str], ...]]:
    return season_label, method, tuple(_selector_key(selector) for selector in selectors)


def _review_contract(selectors: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """Describe the later manifest action without making either choice here."""

    return {
        "automatic_choice": "prohibited",
        "basis_required": SELECTION_BASIS,
        "candidate_source_selectors": [copy.deepcopy(dict(item)) for item in selectors],
        "target_manifest_schema": SELECTION_MANIFEST_SCHEMA,
        "required_human_decisions": [
            "which source selector remains the fixed-carrier canonical identity",
            "which other selector is the dated opening-squad source",
            "whether dated source evidence supports this substitution at all",
        ],
    }


def _proposal_id(prefix: str, value: Mapping[str, Any]) -> str:
    return f"{prefix}-{_sha256_value(value)[:20]}"


def _season_proposals(season: Mapping[str, Any]) -> tuple[dict[str, Any], Counter[str]]:
    season_value = season.get("season")
    if not isinstance(season_value, Mapping):
        raise ProposalError("matrix season has no season object")
    season_label = season_value.get("label")
    if not isinstance(season_label, str) or not season_label:
        raise ProposalError("matrix season label is missing")
    collisions = season.get("collisions")
    if not isinstance(collisions, list):
        raise ProposalError(f"{season_label}: collisions must be a list")
    input_package = season.get("input_package")
    build_audit = season.get("build_audit")
    intake_trace = season.get("source_intake_trace")
    if not isinstance(input_package, Mapping) or not isinstance(build_audit, Mapping) or not isinstance(intake_trace, Mapping):
        raise ProposalError(f"{season_label}: matrix provenance is incomplete")
    _require_sha256(input_package.get("sha256"), f"{season_label}.input_package.sha256")
    _require_sha256(build_audit.get("sha256"), f"{season_label}.build_audit.sha256")
    _require_sha256(build_audit.get("source_intake_sha256"), f"{season_label}.build_audit.source_intake_sha256")

    direct_groups: dict[tuple[str, str, tuple[tuple[str, str, str, str, str], ...]], dict[str, Any]] = {}
    ambiguous: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for index, raw_collision in enumerate(collisions):
        if not isinstance(raw_collision, Mapping) or not _source_source_collision(raw_collision):
            continue
        label = f"{season_label}.collisions[{index}]"
        counts["source_source_collision_count"] += 1
        candidate = _candidate(raw_collision.get("candidate"), f"{label}.candidate")
        evidence = _source_evidence(raw_collision, label)
        raw_signals = raw_collision.get("likely_duplicate_club_representation_signals")
        if not isinstance(raw_signals, list):
            raise ProposalError(f"{label}.likely_duplicate_club_representation_signals must be a list")

        direct_created = False
        for signal_index, raw_signal in enumerate(raw_signals):
            signal = _signal(raw_signal, f"{label}.signals[{signal_index}]")
            club_names = set(signal["clubs"])
            paired_evidence = [row for row in evidence if row["selector"]["club_name"] in club_names]
            selectors = _selectors_from_evidence(paired_evidence)
            # A direct label signal is useful only when the collision matrix
            # gives one exact source selector for each of its two labels.  A
            # richer/messier source trace remains explicitly ambiguous.
            if len(selectors) != 2 or {row["club_name"] for row in selectors} != club_names:
                continue
            key = _direct_group_key(
                method=signal["method"], selectors=selectors, season_label=season_label,
            )
            group = direct_groups.setdefault(key, {
                "direct_label_normalised_alias_signal": signal,
                "evidence": [],
                "source_selectors": selectors,
            })
            group["evidence"].append({"candidate": candidate, "source_rows": paired_evidence})
            direct_created = True

        if direct_created:
            counts["direct_label_normalised_collision_count"] += 1
            continue
        # No direct label signal means this might be an abbreviation the weak
        # normaliser does not know, or it might be a genuine transfer.  It is
        # deliberately not transformed into a source selection proposal.
        selectors = _selectors_from_evidence(evidence)
        ambiguous.append({
            "candidate": candidate,
            "classification": "ambiguous-player-overlap",
            "evidence": [{"source_rows": evidence}],
            "required_resolution": (
                "Obtain dated opening evidence before deciding whether these are alternate "
                "representations of one club or a genuine inter-club player claim."
            ),
            "source_selectors": selectors,
        })
        counts["ambiguous_player_overlap_count"] += 1

    direct: list[dict[str, Any]] = []
    for key in sorted(direct_groups):
        group = direct_groups[key]
        evidence: list[dict[str, Any]] = []
        for raw_evidence in group["evidence"]:
            evidence.append({
                "candidate": raw_evidence["candidate"],
                "source_rows": _dedupe_evidence(raw_evidence["source_rows"]),
            })
        evidence.sort(key=lambda item: (
            item["candidate"]["normalised_name"],
            item["candidate"]["birth_date"],
            item["candidate"]["nationality"],
        ))
        proposal_base = {
            "direct_label_normalised_alias_signal": group["direct_label_normalised_alias_signal"],
            "source_selectors": group["source_selectors"],
        }
        direct.append({
            "classification": "direct-label-normalised-alias-candidate",
            "evidence": evidence,
            "proposal_id": _proposal_id("source-club-review", proposal_base),
            "review_contract": _review_contract(group["source_selectors"]),
            **proposal_base,
        })
    for item in ambiguous:
        item["proposal_id"] = _proposal_id(
            "ambiguous-player-overlap", {"candidate": item["candidate"], "source_selectors": item["source_selectors"]}
        )
    ambiguous.sort(key=lambda item: (
        item["candidate"]["normalised_name"],
        item["candidate"]["birth_date"],
        item["candidate"]["nationality"],
    ))
    counts["direct_label_normalised_alias_candidate_count"] = len(direct)
    return {
        "build_audit": copy.deepcopy(dict(build_audit)),
        "counts": dict(sorted(counts.items())),
        "direct_label_normalised_alias_candidates": direct,
        "ambiguous_player_overlaps": ambiguous,
        "input_package": copy.deepcopy(dict(input_package)),
        "season": copy.deepcopy(dict(season_value)),
        "source_intake_trace": copy.deepcopy(dict(intake_trace)),
    }, counts


def build_report(*, matrix: Mapping[str, Any], matrix_path: Path, matrix_sha256: str) -> dict[str, Any]:
    """Group every source/source collision in one immutable collision matrix."""

    if matrix.get("schema_version") != MATRIX_SCHEMA or matrix.get("state") != MATRIX_STATE:
        raise ProposalError("collision matrix has an unsupported schema or state")
    source_seasons = matrix.get("seasons")
    if not isinstance(source_seasons, list) or not source_seasons:
        raise ProposalError("collision matrix seasons must be a non-empty list")
    proposals: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    prior_label: str | None = None
    for raw_season in source_seasons:
        if not isinstance(raw_season, Mapping):
            raise ProposalError("collision matrix season must be an object")
        season, season_counts = _season_proposals(raw_season)
        label = season["season"].get("label")
        if not isinstance(label, str) or (prior_label is not None and label <= prior_label):
            raise ProposalError("collision matrix seasons must have unique ascending labels")
        prior_label = label
        proposals.append(season)
        counts.update(season_counts)
    counts["season_count"] = len(proposals)
    counts["direct_label_normalised_alias_candidate_count"] = sum(
        len(row["direct_label_normalised_alias_candidates"]) for row in proposals
    )
    counts["ambiguous_player_overlap_count"] = sum(len(row["ambiguous_player_overlaps"]) for row in proposals)
    return {
        "input_collision_matrix": {
            "path": _relative(matrix_path),
            "schema_version": MATRIX_SCHEMA,
            "sha256": matrix_sha256,
            "state": MATRIX_STATE,
        },
        "not_performed": [
            "historical club ownership decision",
            "source selection change",
            "raw source intake mutation",
            "draft package or allocation mutation",
            "binary compiler materialisation",
            "static or runtime release validation",
        ],
        "schema_version": SCHEMA,
        "seasons": proposals,
        "state": STATE,
        "summary": dict(sorted(counts.items())),
    }


def validate_report(report: Mapping[str, Any], *, expected_season_count: int | None = None) -> None:
    """Check the report remains a non-decisive accounting of its input matrix."""

    if report.get("schema_version") != SCHEMA or report.get("state") != STATE:
        raise ProposalError("report has an unsupported schema or state")
    source = report.get("input_collision_matrix")
    if not isinstance(source, Mapping):
        raise ProposalError("report has no collision matrix provenance")
    _require_sha256(source.get("sha256"), "report collision matrix sha256")
    seasons = report.get("seasons")
    summary = report.get("summary")
    if not isinstance(seasons, list) or not isinstance(summary, Mapping):
        raise ProposalError("report seasons and summary are required")
    if expected_season_count is not None and len(seasons) != expected_season_count:
        raise ProposalError(f"report has {len(seasons)} seasons, expected {expected_season_count}")
    direct_count = 0
    ambiguous_count = 0
    source_source_count = 0
    seen_labels: set[str] = set()
    for season in seasons:
        if not isinstance(season, Mapping):
            raise ProposalError("report has a malformed season")
        season_value = season.get("season")
        label = season_value.get("label") if isinstance(season_value, Mapping) else None
        if not isinstance(label, str) or label in seen_labels:
            raise ProposalError("report season labels must be unique")
        seen_labels.add(label)
        direct = season.get("direct_label_normalised_alias_candidates")
        ambiguous = season.get("ambiguous_player_overlaps")
        if not isinstance(direct, list) or not isinstance(ambiguous, list):
            raise ProposalError(f"{label}: proposal queues must be lists")
        direct_count += len(direct)
        ambiguous_count += len(ambiguous)
        source_source_count += len(ambiguous)
        for proposal in direct:
            if not isinstance(proposal, Mapping):
                raise ProposalError(f"{label}: malformed direct proposal")
            if proposal.get("classification") != "direct-label-normalised-alias-candidate":
                raise ProposalError(f"{label}: direct proposal has a wrong classification")
            contract = proposal.get("review_contract")
            if not isinstance(contract, Mapping) or contract.get("automatic_choice") != "prohibited":
                raise ProposalError(f"{label}: direct proposal must prohibit automatic selection")
            selectors = proposal.get("source_selectors")
            if not isinstance(selectors, list) or len(selectors) != 2:
                raise ProposalError(f"{label}: direct proposal must expose exactly two source selectors")
            if "canonical_selector" in proposal or "selected_selector" in proposal:
                raise ProposalError(f"{label}: report must not make a source selection")
        for proposal in ambiguous:
            if not isinstance(proposal, Mapping) or proposal.get("classification") != "ambiguous-player-overlap":
                raise ProposalError(f"{label}: ambiguous proposal has a wrong classification")
            if "review_contract" in proposal or "canonical_selector" in proposal or "selected_selector" in proposal:
                raise ProposalError(f"{label}: ambiguous item must not be selectable")
    if summary.get("season_count") != len(seasons):
        raise ProposalError("report summary season count is wrong")
    if summary.get("direct_label_normalised_alias_candidate_count") != direct_count:
        raise ProposalError("report summary direct proposal count is wrong")
    if summary.get("ambiguous_player_overlap_count") != ambiguous_count:
        raise ProposalError("report summary ambiguous proposal count is wrong")
    direct_collision_count = summary.get("direct_label_normalised_collision_count")
    if not isinstance(direct_collision_count, int) or direct_collision_count < direct_count:
        raise ProposalError("report summary direct label evidence count is wrong")
    source_source_count += direct_collision_count
    if summary.get("source_source_collision_count") != source_source_count:
        raise ProposalError("report summary source/source collision count is wrong")


def _write_new(path: Path, value: Mapping[str, Any]) -> str:
    if path.exists() or path.is_symlink():
        raise ProposalError(f"refusing to replace existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(value)
    path.write_bytes(payload)
    return _sha256_bytes(payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matrix", type=Path,
        default=ROOT / ".local" / "season-source-collision-matrix-v1" / "20260904" / "collision-matrix.json",
        help="canonical collision-matrix JSON to read",
    )
    parser.add_argument("--output", type=Path, help="new canonical JSON proposal report path")
    parser.add_argument(
        "--expected-season-count", type=int, default=25,
        help="exact number of V6 seasons required in this report (default: 25)",
    )
    args = parser.parse_args(argv)
    try:
        if args.expected_season_count < 1:
            raise ProposalError("expected season count must be positive")
        matrix_path = args.matrix.resolve()
        matrix, matrix_sha256 = _read_canonical_matrix(matrix_path)
        report = build_report(matrix=matrix, matrix_path=matrix_path, matrix_sha256=matrix_sha256)
        validate_report(report, expected_season_count=args.expected_season_count)
        report_sha256 = _sha256_value(report)
        summary: dict[str, Any] = {
            "input_collision_matrix_sha256": matrix_sha256,
            "proposal_report_sha256": report_sha256,
            "summary": report["summary"],
        }
        if args.output is not None:
            output = args.output.resolve()
            summary["output_path"] = _relative(output)
            summary["output_sha256"] = _write_new(output, report)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    except (ProposalError, OSError, ValueError, package_v2.PackageValidationError) as exc:
        print(f"source club selection proposal error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
