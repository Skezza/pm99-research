#!/usr/bin/env python3
"""Recover auditable player-name evidence from a captured squad source.

Historical season packages currently retain ``source_name`` but not the
individual source row that supplied it.  This tool creates a deterministic
sidecar which restores that link without changing a frozen package or its
compiled PM99 database.  It has two deliberately separate outcomes:

* a source-backed player is linked to one exact captured squad row, including
  the source file hash and the exact supplied name; or
* it is placed in an explicit queue.  Native PM99 carrier retention is not a
  historical-source failure and is recorded separately from genuinely
  unresolved source matches.

The sidecar also derives *proposed* PM99 given/surname components from the
captured spelling.  They are evidence for a later package amendment; this
tool never rewrites a package or a game database.

Example:

    python3 scripts/season_name_provenance_v1.py \
      --package .local/season-static-ingress-v1/2000-01-worldwide-source-backed-r1/season-package.source-writable.json \
      --source source-capture-2000-01=seasons/2000-01/sources/footballsquads-2000-01.json \
      --output .local/season-name-provenance-v1/2000-01.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA = "pm99-season-player-name-provenance-v1"
CAPTURE_SCHEMA = "pm99-footballsquads-season-capture-v1"
PREALLOCATION_SCHEMA = "pm99-opening-squad-preallocation-v1"
_NUMBER_PREFIX = re.compile(r"^\s*#\s*\d{1,3}\s+")


class NameProvenanceError(ValueError):
    """An input cannot prove a player-name origin safely."""


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NameProvenanceError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise NameProvenanceError(f"{label} must be a JSON object")
    return value


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalised = unicodedata.normalize("NFC", " ".join(value.split()))
    return normalised or None


def _normalised_name(value: str) -> str:
    """Compare presentation safely while preserving the exact raw spelling."""

    return unicodedata.normalize("NFC", " ".join(value.split())).casefold()


def _without_number_prefix(value: str) -> str:
    return _NUMBER_PREFIX.sub("", value).strip()


def _fact_value(player: Mapping[str, Any], name: str) -> object | None:
    facts = player.get("facts")
    if not isinstance(facts, Mapping):
        return None
    value = facts.get(name)
    # A preserve marker is a policy object, not a historical fact.
    return value if isinstance(value, (str, int)) else None


def _captured_row_sha256(player: Mapping[str, Any]) -> str:
    """Use the same facts-only digest as ``season_source_intake_v1``."""

    facts = {
        "shirt_number": player.get("shirt_number"),
        "name": player.get("name"),
        "nationality": player.get("nationality"),
        "position": player.get("position"),
        "height_cm": player.get("height_cm"),
        "weight_kg": player.get("weight_kg"),
        "birth_date": player.get("birth_date"),
        "unresolved_fields": player.get("unresolved_fields"),
    }
    return _json_sha256(facts)


def _capture_rows(capture: Mapping[str, Any]) -> list[dict[str, Any]]:
    if capture.get("schema_version") != CAPTURE_SCHEMA:
        raise NameProvenanceError(
            f"capture must use {CAPTURE_SCHEMA}, got {capture.get('schema_version')!r}"
        )
    clubs = capture.get("clubs")
    if not isinstance(clubs, list) or not clubs:
        raise NameProvenanceError("capture.clubs must be a non-empty list")
    rows: list[dict[str, Any]] = []
    for club_index, club in enumerate(clubs):
        if not isinstance(club, Mapping):
            raise NameProvenanceError(f"capture club {club_index} is malformed")
        source_path = _text(club.get("source_path"))
        source_sha256 = _text(club.get("source_sha256"))
        players = club.get("players")
        if source_path is None or source_sha256 is None or not isinstance(players, list):
            raise NameProvenanceError(f"capture club {club_index} is missing source evidence")
        for player_index, player in enumerate(players):
            if not isinstance(player, Mapping):
                raise NameProvenanceError(f"capture club {club_index} player {player_index} is malformed")
            name = _text(player.get("name"))
            if name is None:
                raise NameProvenanceError(f"capture club {club_index} player {player_index} has no name")
            rows.append(
                {
                    "raw_name": name,
                    "source_path": source_path,
                    "source_sha256": source_sha256,
                    "source_club_name": _text(club.get("club_name")) or "",
                    "source_row_index": player_index,
                    "source_row_sha256": _captured_row_sha256(player),
                    "facts": dict(player),
                }
            )
    return rows


def _preallocation_rows(preallocation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Read the source-row evidence already retained by opening preallocation."""

    if preallocation.get("schema_version") != PREALLOCATION_SCHEMA:
        raise NameProvenanceError(
            f"preallocation must use {PREALLOCATION_SCHEMA}, got {preallocation.get('schema_version')!r}"
        )
    clubs = preallocation.get("source_clubs")
    if not isinstance(clubs, list) or not clubs:
        raise NameProvenanceError("preallocation.source_clubs must be a non-empty list")
    rows: list[dict[str, Any]] = []
    for club_index, club in enumerate(clubs):
        if not isinstance(club, Mapping):
            raise NameProvenanceError(f"preallocation club {club_index} is malformed")
        selector = club.get("selector")
        players = club.get("players")
        if not isinstance(selector, Mapping) or not isinstance(players, list):
            raise NameProvenanceError(f"preallocation club {club_index} is missing source evidence")
        source_path = _text(selector.get("source_path"))
        source_sha256 = _text(selector.get("source_sha256"))
        source_club_name = _text(selector.get("club_name"))
        if source_path is None or source_sha256 is None or source_club_name is None:
            raise NameProvenanceError(f"preallocation club {club_index} has malformed source evidence")
        for player_index, player in enumerate(players):
            if not isinstance(player, Mapping) or not isinstance(player.get("facts"), Mapping):
                raise NameProvenanceError(f"preallocation club {club_index} player {player_index} is malformed")
            facts = dict(player["facts"])
            name = _text(facts.get("name"))
            row_sha256 = _text(player.get("source_row_sha256"))
            row_index = player.get("source_row_index")
            if name is None or row_sha256 is None or not isinstance(row_index, int):
                raise NameProvenanceError(f"preallocation club {club_index} player {player_index} lacks a source row")
            rows.append(
                {
                    "raw_name": name,
                    "source_path": source_path,
                    "source_sha256": source_sha256,
                    "source_club_name": source_club_name,
                    "source_row_index": row_index,
                    "source_row_sha256": row_sha256,
                    "facts": facts,
                }
            )
    return rows


def _source_rows(source: Mapping[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    """Accept only the two hash-bound squad-source shapes used by this pipeline."""

    schema = _text(source.get("schema_version"))
    season = source.get("season")
    if not isinstance(season, Mapping):
        raise NameProvenanceError("source.season must be an object")
    label = _text(season.get("label"))
    if label is None:
        raise NameProvenanceError("source.season.label must be a non-blank string")
    if schema == CAPTURE_SCHEMA:
        return schema, label, _capture_rows(source)
    if schema == PREALLOCATION_SCHEMA:
        return schema, label, _preallocation_rows(source)
    raise NameProvenanceError(
        f"source must use {CAPTURE_SCHEMA} or {PREALLOCATION_SCHEMA}, got {schema!r}"
    )


def _same_known_fact(package_player: Mapping[str, Any], capture_player: Mapping[str, Any], *, package_field: str, capture_field: str) -> bool:
    expected = _fact_value(package_player, package_field)
    observed = capture_player.get(capture_field)
    if expected is None or observed is None:
        return True
    return expected == observed


def _capture_name_index(rows: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Index captured rows by exact supplied spelling for linear-time audits."""

    index: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        index.setdefault(_normalised_name(str(row["raw_name"])), []).append(row)
    return index


def _matching_capture_rows(
    package_player: Mapping[str, Any], rows_by_name: Mapping[str, Sequence[dict[str, Any]]]
) -> tuple[list[dict[str, Any]], str]:
    """Return unique candidates only when every available fact agrees.

    We intentionally do not fuzzy-match names.  A raw spelling with a shirt
    number prefix is the one safe repairable exception: the capture's exact
    name can be linked after removing only that machine-like prefix and still
    has to agree on every available physical/squad fact.
    """

    source_name = _text(package_player.get("source_name"))
    if source_name is None:
        return [], "no-source-name"
    expected_exact = _normalised_name(source_name)
    expected_without_prefix = _normalised_name(_without_number_prefix(source_name))
    if expected_exact in rows_by_name:
        candidate_rows = rows_by_name[expected_exact]
        match_method = "exact-source-name"
    elif _NUMBER_PREFIX.match(source_name) and expected_without_prefix in rows_by_name:
        candidate_rows = rows_by_name[expected_without_prefix]
        match_method = "stripped-number-prefix"
    else:
        return [], "no-captured-name-match"
    matched: list[dict[str, Any]] = []
    for row in candidate_rows:
        facts = row["facts"]
        if not all(
            _same_known_fact(package_player, facts, package_field=package_field, capture_field=capture_field)
            for package_field, capture_field in (
                ("birth_date", "birth_date"),
                ("primary_position", "position"),
                ("shirt_number", "shirt_number"),
                ("height_cm", "height_cm"),
                ("weight_kg", "weight_kg"),
            )
        ):
            continue
        matched.append(row)
    return matched, match_method


def _number_label_recapture_rows(
    package_player: Mapping[str, Any], rows_by_name: Mapping[str, Sequence[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Recover the plain name from a concrete squad capture when available.

    Opening evidence can contain the presentation label ``#8 Sam Morsy``.
    The underlying FootballSquads capture may retain the same person under the
    plain name but a later shirt number or weight, so those secondary facts
    must not prevent an identity re-capture.  An exact birth date and any
    published broad position must agree; the plain name itself is exact.  This
    is intentionally unavailable for generic names and cannot become a fuzzy
    identity matcher.
    """

    source_name = _text(package_player.get("source_name"))
    if source_name is None or not _NUMBER_PREFIX.match(source_name):
        return []
    birth_date = _fact_value(package_player, "birth_date")
    if not isinstance(birth_date, str):
        return []
    position = _fact_value(package_player, "primary_position")
    candidates: list[dict[str, Any]] = []
    clean_key = _normalised_name(_without_number_prefix(source_name))
    for row in rows_by_name.get(clean_key, []):
        facts = row["facts"]
        if facts.get("birth_date") != birth_date:
            continue
        observed_position = facts.get("position")
        if isinstance(position, str) and isinstance(observed_position, str) and observed_position != position:
            continue
        if row.get("source_schema") != CAPTURE_SCHEMA:
            continue
        candidates.append(row)
    return _distinct_source_rows(candidates)


def _distinct_source_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """A raw row repeated by two derived inputs is one piece of evidence."""

    deduplicated: dict[tuple[str, str, str, int, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row["raw_name"]),
            str(row["source_path"]),
            str(row["source_sha256"]),
            int(row["source_row_index"]),
            str(row["source_row_sha256"]),
        )
        deduplicated.setdefault(key, row)
    return [deduplicated[key] for key in sorted(deduplicated)]


def _component_candidate(raw_name: str) -> dict[str, Any]:
    """Derive a transparent component candidate; never silently discard text."""

    cleaned = _text(raw_name)
    if cleaned is None:
        raise NameProvenanceError("raw name is blank")
    number_label_stripped = bool(_NUMBER_PREFIX.match(cleaned))
    display_name = _without_number_prefix(cleaned) if number_label_stripped else cleaned
    # ``#8 Sam Morsy`` is a rendered squad-number label concatenated with the
    # player label by an earlier opening-lineup parser.  It is not a personal
    # name and can be removed mechanically while the exact captured text is
    # retained in ``captured_source.raw_name``.  This is deliberately more
    # constrained than a general punctuation/name normaliser.
    common = {
        "proposed_display_name": display_name,
        "source_number_label_stripped": number_label_stripped,
    }
    if "," in display_name:
        surname, remainder = (part.strip() for part in display_name.split(",", 1))
        given = " ".join(remainder.split())
        if surname and given and "," not in given:
            return {
                **common,
                "status": "ready-comma-order",
                "method": "captured-comma-order",
                "given_name": given,
                "surname": surname,
                "requires_authoritative_identity_check": True,
                "reasons": ["captured source uses surname, given order"],
            }
        return {
            **common,
            "status": "needs-authoritative-identity-check",
            "method": None,
            "given_name": None,
            "surname": None,
            "requires_authoritative_identity_check": True,
            "reasons": ["captured source has an unsupported comma-name form"],
        }
    tokens = display_name.split()
    if len(tokens) == 1:
        return {
            **common,
            "status": "ready-mononym",
            "method": "captured-mononym-surname",
            "given_name": "",
            "surname": tokens[0],
            "requires_authoritative_identity_check": False,
            "reasons": ["captured source supplies one name token"],
        }
    reasons: list[str] = []
    if len(tokens) > 2:
        reasons.append("captured source has a multi-token surname or given name")
    if number_label_stripped:
        reasons.insert(0, "stripped a rendered squad-number label from captured name text")
    return {
        **common,
        "status": "ready-given-first",
        "method": "captured-first-token-given-remainder-surname",
        "given_name": tokens[0],
        "surname": " ".join(tokens[1:]),
        # The PM99 build's current split uses this form.  A source with no
        # explicit ordering marker cannot prove that a culture-specific order
        # is intended, so retain it in the identity queue without blocking a
        # mechanically correct given-first conversion.
        "requires_authoritative_identity_check": len(tokens) > 2,
        "reasons": reasons,
    }


def _mark_package_number_label_repair(
    component: dict[str, Any], *, source_name: str
) -> dict[str, Any]:
    """Retain a package-level parser-label repair when raw re-capture is clean."""

    if not _NUMBER_PREFIX.match(source_name) or component["source_number_label_stripped"]:
        return component
    result = dict(component)
    result["source_number_label_stripped"] = True
    result["reasons"] = [
        "stripped a rendered squad-number label from package source name",
        *list(result["reasons"]),
    ]
    return result


def _package_season_label(package: Mapping[str, Any]) -> tuple[str, str]:
    """Return canonical ``YYYY-YY`` and displayed ``YYYY/YY`` package labels."""

    value = package.get("season")
    if isinstance(value, str):
        label = _text(value)
        if label is None:
            raise NameProvenanceError("package.season must be a non-blank string")
        canonical = label.replace("/", "-", 1)
        return canonical, label
    if not isinstance(value, Mapping):
        raise NameProvenanceError("package.season must be a string or season object")
    label = _text(value.get("label"))
    start_year = value.get("start_year")
    end_year = value.get("end_year")
    if (
        label is None
        or not isinstance(start_year, int)
        or not isinstance(end_year, int)
        or end_year != start_year + 1
    ):
        raise NameProvenanceError("package.season needs label and consecutive integer start/end years")
    return f"{start_year:04d}-{end_year % 100:02d}", label


def build_provenance(*, package: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Build a non-mutating, hash-bound provenance sidecar."""

    season, package_season_label = _package_season_label(package)
    package_id = _text(package.get("package_id"))
    if package_id is None:
        raise NameProvenanceError("package.package_id must be a non-blank string")
    players = package.get("players")
    if not isinstance(players, list) or not players:
        raise NameProvenanceError("package.players must be a non-empty list")
    if not sources:
        raise NameProvenanceError("at least one source is required")
    expected_capture_labels = {season, package_season_label, season.replace("-", "/", 1)}
    prepared_sources: dict[str, dict[str, Any]] = {}
    for artifact_id, source in sorted(sources.items()):
        if not _text(artifact_id) or not isinstance(source, Mapping):
            raise NameProvenanceError("source bindings need a non-blank artifact id and JSON object")
        source_schema, source_label, rows = _source_rows(source)
        if source_label not in expected_capture_labels:
            raise NameProvenanceError(
                f"package season {season!r} does not match source {artifact_id!r} season {source_label!r}"
            )
        prepared_sources[artifact_id] = {
            "schema_version": source_schema,
            "season_label": source_label,
            "sha256": _json_sha256(source),
            "rows_by_name": _capture_name_index([
                {
                    **row,
                    "source_artifact_id": artifact_id,
                    "source_schema": source_schema,
                }
                for row in rows
            ]),
        }
    all_rows_by_name: dict[str, list[dict[str, Any]]] = {}
    for source in prepared_sources.values():
        for name, rows in source["rows_by_name"].items():
            all_rows_by_name.setdefault(name, []).extend(rows)
    output_players: list[dict[str, Any]] = []
    for index, player in enumerate(players):
        if not isinstance(player, Mapping):
            raise NameProvenanceError(f"package player {index} is malformed")
        player_id = _text(player.get("id"))
        canonical_name = _text(player.get("name"))
        if player_id is None or canonical_name is None:
            raise NameProvenanceError(f"package player {index} needs id and name")
        source_name = _text(player.get("source_name"))
        if source_name is None:
            output_players.append(
                {
                    "player_id": player_id,
                    "canonical_name": canonical_name,
                    "source_name": None,
                    "status": "native-retained-no-historical-source",
                    "source_match": None,
                    "captured_source": None,
                    "component_candidate": None,
                }
            )
            continue
        proof = player.get("proof")
        proof_artifact_id = _text(proof.get("artifact_id")) if isinstance(proof, Mapping) else None
        bound_source = prepared_sources.get(proof_artifact_id or "")
        number_label_candidates = _number_label_recapture_rows(player, all_rows_by_name)
        if len(number_label_candidates) == 1:
            candidates = number_label_candidates
            match_method = "clean-number-label-recapture"
            source_scope = "clean-number-label-recapture"
        else:
            rows_by_name = (
                bound_source["rows_by_name"] if bound_source is not None else all_rows_by_name
            )
            candidates, match_method = _matching_capture_rows(player, rows_by_name)
            candidates = _distinct_source_rows(candidates)
            source_scope = "package-proof-bound" if bound_source is not None else "recaptured-comparison"
        if len(candidates) == 1:
            candidate = candidates[0]
            raw_name = str(candidate["raw_name"])
            output_players.append(
                {
                    "player_id": player_id,
                    "canonical_name": canonical_name,
                    "source_name": source_name,
                    "status": "source-row-linked",
                    "source_match": match_method,
                    "source_scope": source_scope,
                    "package_proof_artifact_id": proof_artifact_id,
                    "captured_source": {
                        "raw_name": raw_name,
                        "source_artifact_id": candidate["source_artifact_id"],
                        "source_club_name": candidate["source_club_name"],
                        "source_path": candidate["source_path"],
                        "source_sha256": candidate["source_sha256"],
                        "source_row_index": candidate["source_row_index"],
                        "source_row_sha256": candidate["source_row_sha256"],
                    },
                    "component_candidate": _mark_package_number_label_repair(
                        _component_candidate(raw_name), source_name=source_name
                    ),
                }
            )
            continue
        output_players.append(
            {
                "player_id": player_id,
                "canonical_name": canonical_name,
                "source_name": source_name,
                "status": "needs-source-rescrape" if not candidates else "ambiguous-captured-source-row",
                "source_match": match_method,
                "source_scope": source_scope,
                "package_proof_artifact_id": proof_artifact_id,
                "captured_source": None,
                "component_candidate": None,
                "candidate_source_rows": [
                    {
                        "raw_name": candidate["raw_name"],
                        "source_artifact_id": candidate["source_artifact_id"],
                        "source_path": candidate["source_path"],
                        "source_sha256": candidate["source_sha256"],
                        "source_row_index": candidate["source_row_index"],
                        "source_row_sha256": candidate["source_row_sha256"],
                    }
                    for candidate in candidates
                ],
            }
        )
    output_players.sort(key=lambda row: row["player_id"])
    counts = Counter(str(row["status"]) for row in output_players)
    component_counts = Counter(
        str(row["component_candidate"]["status"])
        for row in output_players
        if isinstance(row.get("component_candidate"), Mapping)
    )
    authoritative_queue_count = sum(
        1
        for row in output_players
        if isinstance(row.get("component_candidate"), Mapping)
        and row["component_candidate"].get("requires_authoritative_identity_check") is True
    )
    number_label_repair_count = sum(
        1
        for row in output_players
        if isinstance(row.get("component_candidate"), Mapping)
        and row["component_candidate"].get("source_number_label_stripped") is True
    )
    return {
        "schema_version": SCHEMA,
        "season": season,
        "package": {
            "package_id": package_id,
            "sha256": _json_sha256(package),
        },
        "sources": [
            {
                "artifact_id": artifact_id,
                "schema_version": source["schema_version"],
                "season_label": source["season_label"],
                "sha256": source["sha256"],
            }
            for artifact_id, source in sorted(prepared_sources.items())
        ],
        "players": output_players,
        "summary": {
            "player_count": len(output_players),
            "status_counts": dict(sorted(counts.items())),
            "component_status_counts": dict(sorted(component_counts.items())),
            "authoritative_identity_queue_count": authoritative_queue_count,
            "source_number_label_repair_count": number_label_repair_count,
            "historical_source_rescrape_queue_count": (
                counts["needs-source-rescrape"] + counts["ambiguous-captured-source-row"]
            ),
            "native_retained_no_historical_source_count": counts["native-retained-no-historical-source"],
        },
    }


def _write_output(path: Path, value: Mapping[str, Any], *, replace: bool) -> None:
    if path.exists() and not replace:
        raise NameProvenanceError(f"output already exists (use --replace to replace derived sidecar): {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        metavar="ARTIFACT_ID=PATH",
        help="Hash-bound squad source. Repeat for each available source artifact.",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Explicitly replace an existing derived provenance sidecar.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        package = _read_json(args.package, label="package")
        sources: dict[str, dict[str, Any]] = {}
        for raw_source in args.source:
            artifact_id, separator, raw_path = str(raw_source).partition("=")
            path = Path(raw_path)
            if not separator or not _text(artifact_id) or not raw_path:
                raise NameProvenanceError("--source must have the form ARTIFACT_ID=PATH")
            if artifact_id in sources:
                raise NameProvenanceError(f"duplicate source artifact id: {artifact_id}")
            sources[artifact_id] = _read_json(path, label=f"source {artifact_id}")
        output = build_provenance(package=package, sources=sources)
        _write_output(args.output, output, replace=args.replace)
    except NameProvenanceError as exc:
        raise SystemExit(f"season-name-provenance: {exc}") from exc
    print(json.dumps(output["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
