#!/usr/bin/env python3
"""Report strict-V2 current-source collision candidates across season drafts.

This is a read-only diagnostic.  It reads canonical draft packages and their
source-package build audits, classifies each duplicate strict-person candidate
as a current-source/current-source or current-source/legacy collision, and
tries to join current source rows back to the hash-bound source-intake selector
which supplied the row.  It never selects a club owner, mutates a source
package, or writes a PM99 binary.

The optional receipt is canonical JSON and is deliberately free of timestamps
so a fixed set of input packages produces the same matrix bytes every time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-season-source-collision-matrix-v1"
STATE = "read-only-source-current-collision-matrix"
SOURCE_PREFIX = "person-source-"


class CollisionMatrixError(ValueError):
    """The requested collision matrix cannot be reproduced safely."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CollisionMatrixError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CollisionMatrixError(f"JSON root must be an object: {path}")
    return value


def _relative(path: Path) -> str:
    """Use workspace-relative paths in receipts, falling back to normalized text."""

    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _is_current_source(player: Mapping[str, Any]) -> bool:
    return str(player.get("person_id") or "").startswith(SOURCE_PREFIX)


def _person_name(player: Mapping[str, Any]) -> str:
    value = player.get("source_name") or player.get("name")
    return value if isinstance(value, str) else ""


def _candidate_groups(package: Mapping[str, Any]) -> list[tuple[tuple[str, str], list[dict[str, Any]]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for player in package.get("players", []):
        if not isinstance(player, dict):
            continue
        key = package_v2._person_candidate_key(player)
        if key is not None:
            groups[key].append(player)
    return [(key, rows) for key, rows in sorted(groups.items()) if len(rows) > 1]


def _classification(rows: Sequence[Mapping[str, Any]]) -> str:
    source_count = sum(_is_current_source(row) for row in rows)
    legacy_count = len(rows) - source_count
    if source_count >= 2 and legacy_count:
        return "source-source-and-legacy"
    if source_count >= 2:
        return "source-source"
    if source_count and legacy_count:
        return "source-legacy"
    return "legacy-only"


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return _sha256_bytes(package_v2.canonical_json_bytes(dict(value)))


def _intake_candidates(season_id: str, intake_root: Path, seasons_root: Path) -> list[Path]:
    """Return a deliberately small, deterministic set of known intake locations."""

    return [
        intake_root / season_id / "source-intake.json",
        seasons_root / season_id / "source-intake.json",
    ]


def _load_matching_intake(
    *, season_id: str, expected_sha256: object, intake_root: Path, seasons_root: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Load a sidecar-selected source intake only after exact canonical hash match."""

    if not isinstance(expected_sha256, str) or not package_v2.SHA256_RE.fullmatch(expected_sha256):
        return None, []
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in _intake_candidates(season_id, intake_root, seasons_root):
        if not path.is_file():
            continue
        value = _read_json(path)
        if _canonical_sha256(value) == expected_sha256:
            matches.append((path, value))
    if not matches:
        return None, []
    # Identical hash-bound intake bytes may have a mirrored path.  Use one
    # document for indexing but retain every matching location as provenance.
    matches.sort(key=lambda item: _relative(item[0]))
    return matches[0][1], [_relative(path) for path, _value in matches]


def _selector_value(raw: object) -> dict[str, str] | None:
    if not isinstance(raw, Mapping):
        return None
    fields = ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256")
    if any(not isinstance(raw.get(field), str) for field in fields):
        return None
    return {field: str(raw[field]) for field in fields}


def _source_row_index(
    intake: Mapping[str, Any] | None,
) -> dict[tuple[str, str, str, str], list[dict[str, Any]]]:
    """Index source rows by club plus exact person facts, retaining selectors."""

    result: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    if intake is None:
        return result
    source_clubs = intake.get("source_clubs")
    if not isinstance(source_clubs, list):
        return result
    for source_club in source_clubs:
        if not isinstance(source_club, Mapping):
            continue
        selector = _selector_value(source_club.get("selector"))
        players = source_club.get("players")
        if selector is None or not isinstance(players, list):
            continue
        club_name = selector["club_name"]
        for source_player in players:
            if not isinstance(source_player, Mapping):
                continue
            facts = source_player.get("facts")
            source_row_sha256 = source_player.get("source_row_sha256")
            if not isinstance(facts, Mapping) or not isinstance(source_row_sha256, str):
                continue
            name = facts.get("name")
            birth_date = facts.get("birth_date")
            nationality = facts.get("nationality")
            if not all(isinstance(value, str) for value in (name, birth_date, nationality)):
                continue
            key = (club_name, name, birth_date, nationality)
            result[key].append({
                "selector": selector,
                "source_row_sha256": source_row_sha256,
            })
    for matches in result.values():
        matches.sort(key=lambda row: (
            row["selector"]["country_catalog"],
            row["selector"]["competition_catalog"],
            row["selector"]["source_path"],
            row["source_row_sha256"],
        ))
    return result


def _club_source_names(build_audit: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    mappings = build_audit.get("club_mappings")
    if not isinstance(mappings, list):
        return result
    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            continue
        club_id = mapping.get("club_id")
        source_club_name = mapping.get("source_club_name")
        if isinstance(club_id, str) and isinstance(source_club_name, str):
            result[club_id] = source_club_name
    return result


def _trace_source_row(
    player: Mapping[str, Any], *, club_source_names: Mapping[str, str], source_index: Mapping[tuple[str, str, str, str], list[dict[str, Any]]], intake_available: bool,
) -> dict[str, Any]:
    """Trace one current source record back to source intake, never guessing a match."""

    club_id = player.get("club_id")
    mapped_source_club = club_source_names.get(club_id) if isinstance(club_id, str) else None
    facts = player.get("facts")
    name = _person_name(player)
    birth_date = facts.get("birth_date") if isinstance(facts, Mapping) else None
    nationality = facts.get("nationality") if isinstance(facts, Mapping) else None
    base: dict[str, Any] = {"mapped_source_club_name": mapped_source_club}
    if not intake_available:
        base["state"] = "source-intake-unavailable"
        return base
    if not isinstance(mapped_source_club, str) or not all(isinstance(value, str) for value in (name, birth_date, nationality)):
        base["state"] = "insufficient-package-facts-for-exact-trace"
        return base
    matches = source_index.get((mapped_source_club, name, birth_date, nationality), [])
    if not matches:
        base["state"] = "no-exact-source-row-match"
        return base
    base["matches"] = matches
    base["state"] = "exact-source-row-match" if len(matches) == 1 else "multiple-exact-source-row-matches"
    return base


def _club_tokens(value: str) -> tuple[str, ...]:
    """A transparent, deliberately weak representation key for review triage."""

    text = unicodedata.normalize("NFKD", value)
    text = "".join(char.casefold() if char.isalnum() else " " for char in text)
    replacements = {"utd": "united"}
    organisations = {"fc", "afc", "cf", "ac", "as", "sc", "fk", "nk", "sk", "football", "club"}
    return tuple(
        replacements.get(token, token)
        for token in text.split()
        if token not in organisations
    )


def _club_representation_signals(club_names: Iterable[str]) -> list[dict[str, Any]]:
    """Flag label shapes worth review, without treating them as ownership decisions."""

    names = sorted({name for name in club_names if name})
    signals: list[dict[str, Any]] = []
    for left_index, left in enumerate(names):
        left_tokens = _club_tokens(left)
        if not left_tokens:
            continue
        for right in names[left_index + 1:]:
            right_tokens = _club_tokens(right)
            if not right_tokens:
                continue
            if left_tokens == right_tokens:
                signals.append({
                    "clubs": [left, right],
                    "method": "organisation-and-abbreviation-normalised-label-equality",
                })
                continue
            # A bare town/city name paired with the same name plus one generic
            # suffix is a common alternate source representation (e.g. a club
            # listed once as 'Forest Green' and once as 'Forest Green Rovers').
            # We intentionally do not collapse two different suffixes such as
            # 'Manchester United' and 'Manchester City'.
            if len(left_tokens) < len(right_tokens):
                short_tokens, long_tokens = left_tokens, right_tokens
                short_name, long_name = left, right
            else:
                short_tokens, long_tokens = right_tokens, left_tokens
                short_name, long_name = right, left
            suffix = long_tokens[len(short_tokens):]
            if long_tokens[:len(short_tokens)] == short_tokens and suffix and all(
                token in {"town", "rovers", "united", "athletic"} for token in suffix
            ):
                signals.append({
                    "clubs": [short_name, long_name],
                    "method": "bare-name-versus-terminal-generic-club-suffix",
                })
    return signals


def _row_summary(
    player: Mapping[str, Any], *, clubs_by_id: Mapping[str, Mapping[str, Any]], trace: dict[str, Any] | None,
) -> dict[str, Any]:
    club_id = str(player.get("club_id") or "")
    club = clubs_by_id.get(club_id, {})
    summary: dict[str, Any] = {
        "carrier_id": player.get("carrier_id"),
        "club_carrier_id": club.get("carrier_id"),
        "club_id": club_id,
        "club_identity_id": club.get("identity_id"),
        "id": player.get("id"),
        "name": player.get("name"),
        "person_id": player.get("person_id"),
        "role": "current-source" if _is_current_source(player) else "legacy-or-native",
        "source_name": player.get("source_name"),
    }
    if trace is not None:
        summary["source_trace"] = trace
    return summary


def _season_matrix(
    *, package_path: Path, audit_path: Path, intake_root: Path, seasons_root: Path,
) -> tuple[dict[str, Any], Counter[str]]:
    package = package_v2.read_canonical_package(package_path)
    # This tool is a read-only index of already-authored canonical packages.
    # Full JSON-Schema validation of roughly 9,000 players per package makes a
    # cross-season report needlessly slow and does not improve the identity
    # result.  Keep the inexpensive format guard here; promotion boundaries
    # retain the complete strict package validator.
    if package.get("schema_version") != package_v2.SCHEMA_VERSION:
        raise CollisionMatrixError(f"package has unsupported schema: {package_path}")
    if not isinstance(package.get("players"), list) or not isinstance(package.get("clubs"), list):
        raise CollisionMatrixError(f"package lacks player or club arrays: {package_path}")
    build_audit = _read_json(audit_path)
    season = package.get("season")
    if not isinstance(season, Mapping) or not isinstance(season.get("label"), str):
        raise CollisionMatrixError(f"package has no season label: {package_path}")
    season_id = f"{season.get('start_year')}-{str(season.get('end_year'))[-2:]}"
    intake, intake_paths = _load_matching_intake(
        season_id=season_id,
        expected_sha256=build_audit.get("source_intake_sha256"),
        intake_root=intake_root,
        seasons_root=seasons_root,
    )
    source_index = _source_row_index(intake)
    club_source_names = _club_source_names(build_audit)
    clubs_by_id = {
        str(club["id"]): club
        for club in package.get("clubs", [])
        if isinstance(club, Mapping) and isinstance(club.get("id"), str)
    }
    classifications: Counter[str] = Counter()
    trace_states: Counter[str] = Counter()
    representation_group_count = 0
    collisions: list[dict[str, Any]] = []
    for candidate, rows in _candidate_groups(package):
        classification = _classification(rows)
        classifications[classification] += 1
        source_rows = [row for row in rows if _is_current_source(row)]
        source_traces = {
            str(row.get("id")): _trace_source_row(
                row,
                club_source_names=club_source_names,
                source_index=source_index,
                intake_available=intake is not None,
            )
            for row in source_rows
        }
        for trace in source_traces.values():
            trace_states[str(trace["state"])] += 1
        club_labels: list[str] = []
        for row in source_rows:
            trace = source_traces[str(row.get("id"))]
            mapped = trace.get("mapped_source_club_name")
            if isinstance(mapped, str):
                club_labels.append(mapped)
            for match in trace.get("matches", []):
                if isinstance(match, Mapping):
                    selector = match.get("selector")
                    if isinstance(selector, Mapping) and isinstance(selector.get("club_name"), str):
                        club_labels.append(selector["club_name"])
        signals = _club_representation_signals(club_labels) if classification.startswith("source-source") else []
        if signals:
            representation_group_count += 1
        collisions.append({
            "candidate": {
                "birth_date": candidate[1],
                "normalised_name": candidate[0],
            },
            "classification": classification,
            "likely_duplicate_club_representation_signals": signals,
            "rows": [
                _row_summary(
                    row,
                    clubs_by_id=clubs_by_id,
                    trace=source_traces.get(str(row.get("id"))),
                )
                for row in sorted(rows, key=lambda item: str(item.get("id")))
            ],
        })
    counts: Counter[str] = Counter(classifications)
    counts["duplicate_candidate_group_count"] = len(collisions)
    counts["likely_duplicate_club_representation_group_count"] = representation_group_count
    for state, count in trace_states.items():
        counts[f"trace:{state}"] = count
    return {
        "build_audit": {
            "path": _relative(audit_path),
            "sha256": _sha256_bytes(audit_path.read_bytes()),
            "source_intake_sha256": build_audit.get("source_intake_sha256"),
        },
        "collisions": collisions,
        "counts": dict(sorted(counts.items())),
        "input_package": {
            "path": _relative(package_path),
            "sha256": _sha256_bytes(package_path.read_bytes()),
        },
        "season": dict(season),
        "source_intake_trace": {
            "matched_paths": intake_paths,
            "state": "matched" if intake is not None else "no-known-path-matched-audit-hash",
        },
    }, counts


def build_matrix(*, authoring_root: Path, intake_root: Path, seasons_root: Path) -> dict[str, Any]:
    if not authoring_root.is_dir():
        raise CollisionMatrixError(f"authoring root is not a directory: {authoring_root}")
    season_dirs = sorted(path for path in authoring_root.iterdir() if path.is_dir())
    if not season_dirs:
        raise CollisionMatrixError(f"authoring root has no season directories: {authoring_root}")
    aggregate: Counter[str] = Counter()
    seasons: list[dict[str, Any]] = []
    for season_dir in season_dirs:
        package_path = season_dir / "draft-season-package.json"
        audit_path = season_dir / "source-package-build-audit.json"
        if not package_path.is_file() or not audit_path.is_file():
            raise CollisionMatrixError(
                f"season {season_dir.name} requires draft-season-package.json and source-package-build-audit.json"
            )
        season, counts = _season_matrix(
            package_path=package_path,
            audit_path=audit_path,
            intake_root=intake_root,
            seasons_root=seasons_root,
        )
        seasons.append(season)
        aggregate.update(counts)
    # Counts prefixed trace: and the strict collision classifications are
    # additive across seasons.  The independent aggregate total is explicit.
    aggregate["season_count"] = len(seasons)
    return {
        "aggregate_counts": dict(sorted(aggregate.items())),
        "authoring_root": _relative(authoring_root),
        "schema_version": SCHEMA,
        "seasons": seasons,
        "state": STATE,
        "not_performed": [
            "historical club ownership decision",
            "source selection change",
            "package or source mutation",
            "binary compiler materialisation",
            "static or runtime release validation",
        ],
    }


def _write_new(path: Path, value: Mapping[str, Any]) -> str:
    if path.exists() or path.is_symlink():
        raise CollisionMatrixError(f"refusing to replace existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = package_v2.canonical_json_bytes(dict(value))
    path.write_bytes(payload)
    return _sha256_bytes(payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--authoring-root", type=Path,
        default=ROOT / ".local" / "season-authoring-post-calendar-binding-v6",
        help="directory containing one draft package and build audit per season",
    )
    parser.add_argument(
        "--intake-root", type=Path,
        default=ROOT / ".local" / "season-historical-squad-backfill-v1",
        help="hash-bound source-intake mirror root used for source row tracing",
    )
    parser.add_argument(
        "--seasons-root", type=Path, default=ROOT / "seasons",
        help="secondary source-intake mirror root used only if its canonical hash matches",
    )
    parser.add_argument("--output", type=Path, help="new optional canonical JSON receipt path")
    args = parser.parse_args(argv)
    try:
        matrix = build_matrix(
            authoring_root=args.authoring_root.resolve(),
            intake_root=args.intake_root.resolve(),
            seasons_root=args.seasons_root.resolve(),
        )
        payload = package_v2.canonical_json_bytes(matrix)
        summary = {
            "aggregate_counts": matrix["aggregate_counts"],
            "matrix_sha256": _sha256_bytes(payload),
            "season_count": len(matrix["seasons"]),
        }
        if args.output is not None:
            summary["output_sha256"] = _write_new(args.output.resolve(), matrix)
            summary["output_path"] = _relative(args.output.resolve())
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    except (CollisionMatrixError, OSError, package_v2.PackageValidationError, ValueError) as exc:
        print(f"source collision matrix error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
