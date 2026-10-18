#!/usr/bin/env python3
"""Materialise an explicit, provenance-preserving source-club selection.

Some source projects publish an all-season squad and a separate opening-date
capture for the same real club.  They are both valuable immutable evidence,
but they must not be independently allocated to one fixed PM99 carrier.  This
module applies *only* an explicit, content-addressed selection manifest:

* every canonical and selected selector must be an exact selector in the
  hash-bound source intake;
* the canonical selector remains the fixed-carrier/allocation identity while
  its effective player rows come verbatim from the selected source selector;
* the selected alias is omitted from the effective source-club list, so it
  cannot be allocated a second time; and
* the raw intake, raw source-capture hash, complete manifest and both source
  selector row-hash ledgers remain in the output.

This is deliberately a source-authoring projection, not an identity guess, a
player edit, a package promotion, or a PM99 database build.  Transfers and
any other ambiguous source claims must remain absent from the manifest until
they have their own dated evidence.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-season-source-club-selection-v1"
AUDIT_SCHEMA = "pm99-season-source-club-selection-audit-v1"
MANIFEST_SCHEMA = "pm99-season-source-club-selection-manifest-v1"
SOURCE_INTAKE_SCHEMA = "pm99-season-source-intake-v1"
STATE = "source-club-selection-provisional-not-release"
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
SELECTOR_FIELDS = {
    "country_catalog",
    "competition_catalog",
    "club_name",
    "source_path",
    "source_sha256",
}
SELECTION_FIELDS = {"id", "canonical_selector", "selected_selector", "basis"}
MANIFEST_FIELDS = {"schema_version", "selection_id", "season", "inputs", "selections"}
INPUT_FIELDS = {"source_intake_sha256", "source_capture_sha256"}
SEASON_FIELDS = {"catalog", "label"}
SELECTION_BASIS = "opening-date-squad-authoritative"


class SourceClubSelectionError(ValueError):
    """A selection is incomplete, stale, or would make an implicit decision."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the canonical JSON representation shared by source artifacts."""

    return package_v2.canonical_json_bytes(value)


def _sha256_document(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_text(value: object, label: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise SourceClubSelectionError(f"{label} must be a non-blank string of at most {maximum} characters")
    return value


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not package_v2.SHA256_RE.fullmatch(value):
        raise SourceClubSelectionError(f"{label} must be a lowercase SHA-256")
    return value


def _require_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise SourceClubSelectionError(f"{label} must be a lower-case stable id")
    return value


def _selector_key(selector: object, *, label: str) -> tuple[str, str, str, str, str]:
    if not isinstance(selector, Mapping) or set(selector) != SELECTOR_FIELDS:
        raise SourceClubSelectionError(f"{label} must contain exactly the canonical source selector fields")
    return (
        _require_text(selector.get("country_catalog"), f"{label}.country_catalog"),
        _require_text(selector.get("competition_catalog"), f"{label}.competition_catalog"),
        _require_text(selector.get("club_name"), f"{label}.club_name"),
        _require_text(selector.get("source_path"), f"{label}.source_path"),
        _require_sha256(selector.get("source_sha256"), f"{label}.source_sha256"),
    )


def _selector_value(selector: Mapping[str, Any]) -> dict[str, str]:
    """Copy a validated selector in its stable, human-reviewable field order."""

    _selector_key(selector, label="selector")
    return {
        "country_catalog": str(selector["country_catalog"]),
        "competition_catalog": str(selector["competition_catalog"]),
        "club_name": str(selector["club_name"]),
        "source_path": str(selector["source_path"]),
        "source_sha256": str(selector["source_sha256"]),
    }


def _read_canonical(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceClubSelectionError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise SourceClubSelectionError(f"{label} must be canonical UTF-8 JSON: {path}")
    return value, _sha256_bytes(raw)


def _source_clubs(source_intake: Mapping[str, Any]) -> tuple[dict[tuple[str, str, str, str, str], dict[str, Any]], list[tuple[str, str, str, str, str]]]:
    """Validate the narrow immutable intake surface needed by this projection."""

    if source_intake.get("schema_version") != SOURCE_INTAKE_SCHEMA:
        raise SourceClubSelectionError(f"source intake schema must be {SOURCE_INTAKE_SCHEMA!r}")
    season = source_intake.get("season")
    if not isinstance(season, Mapping) or set(season) != SEASON_FIELDS:
        raise SourceClubSelectionError("source intake season must contain exactly catalog and label")
    _require_text(season.get("catalog"), "source intake season.catalog")
    _require_text(season.get("label"), "source intake season.label")
    _require_sha256(source_intake.get("source_capture_sha256"), "source intake source_capture_sha256")
    credits = source_intake.get("source")
    if not isinstance(credits, Mapping):
        raise SourceClubSelectionError("source intake source credits must be an object")
    rows = source_intake.get("source_clubs")
    if not isinstance(rows, list) or not rows:
        raise SourceClubSelectionError("source intake source_clubs must be a non-empty list")
    by_selector: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    sorted_keys: list[tuple[str, str, str, str, str]] = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise SourceClubSelectionError(f"source intake source club {index} must be an object")
        if set(raw) != {"selector", "competition_name", "players"}:
            raise SourceClubSelectionError(
                f"source intake source club {index} must contain exactly selector, competition_name and players"
            )
        selector = raw["selector"]
        key = _selector_key(selector, label=f"source intake source club {index}.selector")
        if key in by_selector:
            raise SourceClubSelectionError("source intake contains duplicate source club selectors")
        _require_text(raw.get("competition_name"), f"source intake source club {index}.competition_name")
        players = raw.get("players")
        if not isinstance(players, list) or not players:
            raise SourceClubSelectionError(f"source intake source club {index}.players must be non-empty")
        player_hashes: set[str] = set()
        for player_index, player in enumerate(players):
            if not isinstance(player, Mapping):
                raise SourceClubSelectionError(
                    f"source intake source club {index}.players[{player_index}] must be an object"
                )
            _require_sha256(
                player.get("source_row_sha256"),
                f"source intake source club {index}.players[{player_index}].source_row_sha256",
            )
            row_digest = str(player["source_row_sha256"])
            if row_digest in player_hashes:
                raise SourceClubSelectionError(
                    f"source intake source club {index} duplicates a source player row digest"
                )
            player_hashes.add(row_digest)
        by_selector[key] = copy.deepcopy(dict(raw))
        sorted_keys.append(key)
    return by_selector, sorted_keys


def _source_row_ledger(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "selector": _selector_value(row["selector"]),
        "player_count": len(row["players"]),
        "player_row_sha256s": [str(player["source_row_sha256"]) for player in row["players"]],
    }


def validate_manifest(*, manifest: Mapping[str, Any], source_intake: Mapping[str, Any]) -> None:
    """Require every declared selection to be exact, reviewed and hash-bound."""

    source_by_selector, _source_order = _source_clubs(source_intake)
    if set(manifest) != MANIFEST_FIELDS:
        raise SourceClubSelectionError(f"manifest must contain exactly {sorted(MANIFEST_FIELDS)}")
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise SourceClubSelectionError(f"manifest schema must be {MANIFEST_SCHEMA!r}")
    _require_id(manifest.get("selection_id"), "manifest selection_id")
    season = manifest.get("season")
    if not isinstance(season, Mapping) or set(season) != SEASON_FIELDS:
        raise SourceClubSelectionError("manifest season must contain exactly catalog and label")
    expected_season = source_intake["season"]
    if dict(season) != dict(expected_season):
        raise SourceClubSelectionError("manifest season differs from source intake")
    inputs = manifest.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != INPUT_FIELDS:
        raise SourceClubSelectionError(f"manifest inputs must contain exactly {sorted(INPUT_FIELDS)}")
    if inputs.get("source_intake_sha256") != _sha256_document(source_intake):
        raise SourceClubSelectionError("manifest source_intake_sha256 does not bind this source intake")
    if inputs.get("source_capture_sha256") != source_intake.get("source_capture_sha256"):
        raise SourceClubSelectionError("manifest source_capture_sha256 does not bind this source intake")
    _require_sha256(inputs.get("source_intake_sha256"), "manifest inputs.source_intake_sha256")
    _require_sha256(inputs.get("source_capture_sha256"), "manifest inputs.source_capture_sha256")
    selections = manifest.get("selections")
    if not isinstance(selections, list):
        raise SourceClubSelectionError("manifest selections must be a list")
    previous_id: str | None = None
    seen_ids: set[str] = set()
    canonical_keys: set[tuple[str, str, str, str, str]] = set()
    selected_keys: set[tuple[str, str, str, str, str]] = set()
    for index, selection in enumerate(selections):
        if not isinstance(selection, Mapping) or set(selection) != SELECTION_FIELDS:
            raise SourceClubSelectionError(
                f"manifest selections[{index}] must contain exactly {sorted(SELECTION_FIELDS)}"
            )
        selection_id = _require_id(selection.get("id"), f"manifest selections[{index}].id")
        if previous_id is not None and selection_id <= previous_id:
            raise SourceClubSelectionError("manifest selection ids must be unique and sorted lexicographically")
        previous_id = selection_id
        if selection_id in seen_ids:
            raise SourceClubSelectionError(f"manifest repeats selection id {selection_id!r}")
        seen_ids.add(selection_id)
        if selection.get("basis") != SELECTION_BASIS:
            raise SourceClubSelectionError(
                f"manifest selections[{index}].basis must be {SELECTION_BASIS!r}"
            )
        canonical = _selector_key(
            selection.get("canonical_selector"), label=f"manifest selections[{index}].canonical_selector"
        )
        selected = _selector_key(
            selection.get("selected_selector"), label=f"manifest selections[{index}].selected_selector"
        )
        if canonical == selected:
            raise SourceClubSelectionError("manifest selection canonical and selected selectors must differ")
        if canonical not in source_by_selector:
            raise SourceClubSelectionError("manifest canonical selector is absent from source intake")
        if selected not in source_by_selector:
            raise SourceClubSelectionError("manifest selected selector is absent from source intake")
        if canonical in canonical_keys or canonical in selected_keys:
            raise SourceClubSelectionError("manifest reuses a canonical selector")
        if selected in canonical_keys or selected in selected_keys:
            raise SourceClubSelectionError("manifest reuses a selected selector")
        canonical_keys.add(canonical)
        selected_keys.add(selected)


def build_selection(
    *, source_intake: Mapping[str, Any], manifest: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a deterministic source-only effective-club projection and receipt."""

    source_intake = copy.deepcopy(dict(source_intake))
    manifest = copy.deepcopy(dict(manifest))
    validate_manifest(manifest=manifest, source_intake=source_intake)
    source_by_selector, source_order = _source_clubs(source_intake)
    substitutions: dict[tuple[str, str, str, str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    selected_keys: set[tuple[str, str, str, str, str]] = set()
    selection_rows: list[dict[str, Any]] = []
    for raw in manifest["selections"]:
        canonical = _selector_key(raw["canonical_selector"], label="manifest canonical selector")
        selected = _selector_key(raw["selected_selector"], label="manifest selected selector")
        canonical_row = source_by_selector[canonical]
        selected_row = source_by_selector[selected]
        substitutions[canonical] = (selected_row, dict(raw))
        selected_keys.add(selected)
        selection_rows.append({
            "id": str(raw["id"]),
            "basis": SELECTION_BASIS,
            "canonical_source": _source_row_ledger(canonical_row),
            "selected_source": _source_row_ledger(selected_row),
        })

    effective_rows: list[dict[str, Any]] = []
    for key in source_order:
        if key in selected_keys:
            continue
        original = source_by_selector[key]
        if key not in substitutions:
            effective_rows.append(copy.deepcopy(original))
            continue
        selected_row, _selection = substitutions[key]
        # The canonical selector is deliberately retained so existing carrier
        # allocations remain valid.  Only the exact, hash-addressed source
        # player rows change, and their provenance is carried in selection_rows.
        effective_rows.append({
            "selector": copy.deepcopy(original["selector"]),
            "competition_name": str(original["competition_name"]),
            "players": copy.deepcopy(selected_row["players"]),
        })

    raw_source_player_count = sum(len(row["players"]) for row in source_by_selector.values())
    effective_source_player_count = sum(len(row["players"]) for row in effective_rows)
    source_intake_sha256 = _sha256_document(source_intake)
    manifest_sha256 = _sha256_document(manifest)
    output = {
        "schema_version": SCHEMA,
        "selection_id": manifest["selection_id"],
        "state": STATE,
        "season": copy.deepcopy(source_intake["season"]),
        "inputs": {
            "source_intake_sha256": source_intake_sha256,
            "source_capture_sha256": source_intake["source_capture_sha256"],
            "selection_manifest_sha256": manifest_sha256,
        },
        # Copying the exact manifest makes the output independently reviewable.
        # validate_selection rebuilds it from the immutable intake and this
        # embedded manifest, so it is not a mutable second source of truth.
        "manifest": manifest,
        "source_credits": copy.deepcopy(source_intake["source"]),
        "selections": selection_rows,
        "effective_source_clubs": effective_rows,
        "summary": {
            "raw_source_club_count": len(source_order),
            "explicit_selection_count": len(selection_rows),
            "suppressed_alias_source_club_count": len(selected_keys),
            "effective_source_club_count": len(effective_rows),
            "raw_source_player_count": raw_source_player_count,
            "effective_source_player_count": effective_source_player_count,
        },
    }
    output_sha256 = _sha256_document(output)
    audit = {
        "schema_version": AUDIT_SCHEMA,
        "state": STATE,
        "season": copy.deepcopy(source_intake["season"]),
        "inputs": {
            "source_intake_sha256": source_intake_sha256,
            "source_capture_sha256": source_intake["source_capture_sha256"],
            "selection_manifest_sha256": manifest_sha256,
        },
        "output": {"source_club_selection_sha256": output_sha256},
        "coverage": copy.deepcopy(output["summary"]),
        "not_performed": [
            "raw source capture modification",
            "automatic club-alias inference",
            "transfer or player-identity decision",
            "player fact edit",
            "fixed-carrier allocation edit",
            "package promotion",
            "database compilation",
            "PM99 runtime validation",
            "screenshot capture",
        ],
    }
    return output, audit


def validate_selection(*, selection: Mapping[str, Any], source_intake: Mapping[str, Any]) -> None:
    """Verify a selection is exactly reproducible from one raw intake/manifest."""

    if selection.get("schema_version") != SCHEMA or selection.get("state") != STATE:
        raise SourceClubSelectionError("unsupported source-club selection artifact")
    manifest = selection.get("manifest")
    if not isinstance(manifest, Mapping):
        raise SourceClubSelectionError("source-club selection lacks its embedded manifest")
    expected, _audit = build_selection(source_intake=source_intake, manifest=manifest)
    if dict(selection) != expected:
        raise SourceClubSelectionError("source-club selection does not exactly match its hash-bound inputs")


def effective_source_clubs(*, selection: Mapping[str, Any], source_intake: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return validated effective source clubs for the package-authoring bridge."""

    validate_selection(selection=selection, source_intake=source_intake)
    return copy.deepcopy(list(selection["effective_source_clubs"]))


def assess_existing_package_duplicate_sources(
    *, selection: Mapping[str, Any], source_intake: Mapping[str, Any], package: Mapping[str, Any],
    package_sha256: str,
) -> dict[str, Any]:
    """Measure which existing strict-source collisions one projection addresses.

    This is deliberately read-only diagnostic evidence.  It does not alter the
    supplied package and does not assert that an older package has already
    consumed the selection.  A later authoring replay is still required.
    """

    validate_selection(selection=selection, source_intake=source_intake)
    package_v2.validate_package(dict(package), strict=False)
    package_season = package.get("season")
    if not isinstance(package_season, Mapping) or package_season.get("label") != selection.get("season", {}).get("label"):
        raise SourceClubSelectionError("strict-package preflight targets a different season")
    source_capture_sha256 = selection["inputs"]["source_capture_sha256"]
    artifacts = package.get("artifacts")
    if not isinstance(artifacts, list) or not any(
        isinstance(row, Mapping) and row.get("sha256") == source_capture_sha256 for row in artifacts
    ):
        raise SourceClubSelectionError(
            "strict-package preflight package is not bound to the selection source capture"
        )
    clubs = package.get("clubs")
    players = package.get("players")
    if not isinstance(clubs, list) or not isinstance(players, list):
        raise SourceClubSelectionError("strict-package preflight package has malformed clubs or players")
    club_names = {str(row.get("id")): str(row.get("name")) for row in clubs if isinstance(row, Mapping)}
    candidates: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for player in players:
        if not isinstance(player, Mapping) or not str(player.get("person_id") or "").startswith("person-source-"):
            continue
        key = package_v2._person_candidate_key(dict(player))
        if key is not None:
            candidates.setdefault(key, []).append(player)
    duplicate_groups = {
        key: rows for key, rows in candidates.items()
        if len(rows) > 1
    }
    aliases = {
        (
            str(row["canonical_source"]["selector"]["club_name"]),
            str(row["selected_source"]["selector"]["club_name"]),
        )
        for row in selection["selections"]
    }
    covered: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    for key, rows in sorted(duplicate_groups.items()):
        group_club_names = sorted({club_names.get(str(row.get("club_id")), "<unknown-club>") for row in rows})
        exact_alias = next((pair for pair in sorted(aliases) if set(pair) == set(group_club_names)), None)
        row = {
            "normalised_name": key[0],
            "birth_date": key[1],
            "club_names": group_club_names,
        }
        if exact_alias is None:
            remaining.append(row)
        else:
            covered.append({**row, "explicit_selection_alias": list(exact_alias)})
    return {
        "state": "strict-source-duplicate-preflight-projection-only-not-recompiled",
        "input": {
            "source_club_selection_sha256": _sha256_document(selection),
            "package_sha256": package_sha256,
            "source_capture_sha256": source_capture_sha256,
        },
        "coverage": {
            "current_source_duplicate_candidate_group_count": len(duplicate_groups),
            "explicit_selection_covered_candidate_group_count": len(covered),
            "remaining_unselected_candidate_group_count": len(remaining),
        },
        "explicit_selection_covered_groups": covered,
        "remaining_unselected_groups": remaining,
        "not_performed": [
            "package modification",
            "automatic transfer resolution",
            "strict package promotion",
            "database compilation",
            "PM99 runtime validation",
        ],
    }


def _write_new(path: Path, value: Mapping[str, Any]) -> str:
    if path.exists() or path.is_symlink():
        raise SourceClubSelectionError(f"refusing to replace existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(value)
    path.write_bytes(payload)
    return _sha256_bytes(payload)


def write_selection(
    *, source_intake_path: Path, manifest_path: Path, output_root: Path,
    strict_package_path: Path | None = None,
) -> dict[str, Any]:
    """Write one new source-only selection root, never replacing prior evidence."""

    output_root = output_root.resolve()
    if output_root.exists() or output_root.is_symlink():
        raise SourceClubSelectionError(f"refusing to overwrite source-club selection root: {output_root}")
    source_intake, _input_sha256 = _read_canonical(source_intake_path.resolve(), "source intake")
    manifest, _manifest_sha256 = _read_canonical(manifest_path.resolve(), "selection manifest")
    selection, audit = build_selection(source_intake=source_intake, manifest=manifest)
    if strict_package_path is not None:
        strict_package, strict_package_sha256 = _read_canonical(
            strict_package_path.resolve(), "strict-package preflight package"
        )
        audit["strict_package_preflight"] = assess_existing_package_duplicate_sources(
            selection=selection,
            source_intake=source_intake,
            package=strict_package,
            package_sha256=strict_package_sha256,
        )
    output_root.mkdir(parents=True, exist_ok=False)
    selection_path = output_root / "source-club-selection.json"
    audit_path = output_root / "source-club-selection-audit.json"
    selection_sha256 = _write_new(selection_path, selection)
    audit = copy.deepcopy(audit)
    audit["output"] = {
        "source_club_selection_sha256": selection_sha256,
        "selection_relative_path": selection_path.name,
    }
    _write_new(audit_path, audit)
    return audit


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-intake", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--strict-package",
        type=Path,
        help="optional existing package used only for a read-only duplicate-source preflight",
    )
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        audit = write_selection(
            source_intake_path=args.source_intake,
            manifest_path=args.manifest,
            output_root=args.output_root,
            strict_package_path=args.strict_package,
        )
    except (OSError, SourceClubSelectionError, ValueError) as exc:
        print(f"source-club selection error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"coverage": audit["coverage"], "state": STATE}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
