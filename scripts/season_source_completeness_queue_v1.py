#!/usr/bin/env python3
"""Create a deterministic, carrier-scoped historical-source work queue.

The historical source captures deliberately include more clubs than PM99 can
hold.  This reader therefore scopes its counts and work items to the exact
fixed carriers selected by each hash-bound ``current.json`` allocation.  It
does not fetch, edit, promote, compile, or run a database.

The queue applies the agreed historical policies:

* an opening-date manager is a mandatory, exact, dated and hash-backed name;
* an August/opening squad only needs a capacity-fitting source pool, not a
  complete season's transfer history;
* a sourced XI may use deterministic formation inference from G/D/M/F facts;
* secondary player facts remain visible non-blocking fallbacks; and
* portraits are deliberately out of scope (native no-photo is allowed).

Consequently, this report is a source and authoring planning surface, never a
claim that a draft or package is playable.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pm99-season-source-completeness-queue-v1"
CURRENT_SCHEMA = "pm99-historical-squad-backfill-current-v1"
MANAGER_OVERLAY_SCHEMA = "pm99-season-manager-overlay-v1"
MANAGER_OVERLAY_INDEX_SCHEMA = "pm99-season-manager-overlay-index-v1"
MANAGER_OVERLAY_SELECTION_SCHEMA = "pm99-season-manager-overlay-selection-manifest-v1"
OPENING_XI_OVERLAY_SCHEMA = "pm99-season-opening-lineup-overlay-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FORMATION_RE = re.compile(r"[1-5](?:-[0-5]){1,4}$")


class QueueError(ValueError):
    """An authoritative source pointer or its selected input is malformed."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the stable JSON representation used for receipts and output."""

    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    """Hash a file in bounded memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QueueError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise QueueError(f"{label} must be a JSON object: {path}")
    return value


def _path_record(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {"path": path.as_posix(), "exists": path.is_file()}
    if path.is_file():
        record["sha256"] = sha256_file(path)
        record["bytes"] = path.stat().st_size
    return record


def _safe_child(parent: Path, relative: object, label: str) -> Path:
    """Resolve only a portable child path from a frozen pointer artifact."""

    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise QueueError(f"{label} path is unsafe")
    path = (parent / relative).resolve()
    if path != parent.resolve() and parent.resolve() not in path.parents:
        raise QueueError(f"{label} path escapes its root")
    return path


def _declared_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise QueueError(f"{label} hash must be a lowercase SHA-256")
    return value


def _selector(value: Mapping[str, Any], *, club_name: object | None = None) -> tuple[str, str, str]:
    source = value.get("source_selector", value.get("selector", value))
    if not isinstance(source, Mapping):
        raise QueueError("source selector must be an object")
    result = (
        str(source.get("country_catalog") or "").strip(),
        str(source.get("competition_catalog") or "").strip(),
        str(source.get("club_name") or club_name or value.get("club_name") or "").strip(),
    )
    if not all(result):
        raise QueueError("source selector lacks country_catalog, competition_catalog or club_name")
    return result


def _selector_object(value: tuple[str, str, str]) -> dict[str, str]:
    return dict(zip(("country_catalog", "competition_catalog", "club_name"), value, strict=True))


def _unique_index(
    rows: object, *, label: str, club_name_from_row: bool = False,
) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    if not isinstance(rows, list):
        raise QueueError(f"{label} must be a list")
    result: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise QueueError(f"{label} contains a malformed row")
        key = _selector(row, club_name=row.get("club_name") if club_name_from_row else None)
        if key in result:
            raise QueueError(f"{label} duplicates source selector {key}")
        result[key] = row
    return result


def _resolved_pointer_artifact(
    pointer_path: Path, pointer: Mapping[str, Any], name: str,
) -> tuple[Path, dict[str, Any]]:
    artifact = (pointer.get("artifacts") or {}).get(name)
    if not isinstance(artifact, Mapping):
        raise QueueError(f"{pointer_path}: current pointer has no {name!r} artifact")
    relative = artifact.get("path")
    declared = artifact.get("sha256")
    if not isinstance(relative, str) or not isinstance(declared, str) or not SHA256_RE.fullmatch(declared):
        raise QueueError(f"{pointer_path}: {name!r} artifact is malformed")
    path = pointer_path.parent / relative
    record = _path_record(path)
    record["declared_sha256"] = declared
    record["state"] = "bound" if record.get("sha256") == declared else "hash-mismatch-or-missing"
    if record["state"] != "bound":
        raise QueueError(f"{pointer_path}: {name!r} artifact no longer matches its current pointer")
    return path, record


def _formation_is_published(value: object) -> bool:
    if not isinstance(value, str) or not FORMATION_RE.fullmatch(value):
        return False
    return sum(int(part) for part in value.split("-")) == 10


def _formation_is_inferable(starting_xi: object) -> bool:
    if not isinstance(starting_xi, list) or len(starting_xi) != 11:
        return False
    positions = Counter()
    for row in starting_xi:
        if not isinstance(row, Mapping):
            return False
        positions[str(row.get("source_position") or "").upper()] += 1
    bands = [positions[position] for position in ("D", "M", "F") if positions[position]]
    return (
        positions["G"] == 1
        and sum(bands) == 10
        and len(bands) >= 2
        and all(1 <= count <= 5 for count in bands)
    )


def _valid_manager(row: Mapping[str, Any]) -> tuple[bool, str | None]:
    name = str(row.get("manager_name") or "").strip()
    if not name:
        return False, "manager-name-missing"
    try:
        dt.date.fromisoformat(str(row.get("opening_fixture_date") or ""))
    except ValueError:
        return False, "opening-fixture-date-missing-or-invalid"
    evidence = row.get("evidence")
    if not isinstance(evidence, Mapping) or not str(evidence.get("source_url") or "").strip():
        return False, "dated-manager-source-url-missing"
    snapshot = str(evidence.get("source_snapshot_sha256") or "").strip()
    if not SHA256_RE.fullmatch(snapshot):
        return False, "dated-manager-source-snapshot-missing-or-invalid"
    return True, None


def _manager_indexes(
    ledger: Mapping[str, Any],
) -> tuple[dict[tuple[str, str, str], Mapping[str, Any]], dict[tuple[str, str, str], Mapping[str, Any]]]:
    managers = _unique_index(ledger.get("managers"), label="opening manager ledger managers")
    gaps = _unique_index(ledger.get("gaps"), label="opening manager ledger gaps")
    overlap = sorted(set(managers) & set(gaps))
    if overlap:
        raise QueueError(f"opening manager ledger conflicts for {overlap[0]}")
    return managers, gaps


def _bound_index_artifact(
    *, index_root: Path, record: object, label: str,
) -> tuple[Path, dict[str, Any], str]:
    """Load one root-relative, SHA-pinned artifact named by an overlay index."""

    if not isinstance(record, Mapping):
        raise QueueError(f"manager overlay index has no {label} binding")
    path = _safe_child(index_root, record.get("path"), f"manager overlay index {label}")
    expected = _declared_sha256(record.get("sha256"), f"manager overlay index {label}")
    actual = sha256_file(path) if path.is_file() else None
    if actual != expected:
        raise QueueError(f"manager overlay index {label} is stale or missing")
    return path, _read_object(path, label=f"manager overlay index {label}"), actual


def _manager_overlay_index(
    *, index_path: Path, index_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate the index and every pointer it relies on once per report."""

    try:
        relative_index_path = index_path.resolve().relative_to(index_root.resolve()).as_posix()
    except ValueError as exc:
        raise QueueError("manager overlay index must sit below manager-overlay-index-root") from exc
    index = _read_object(index_path, label="manager overlay index")
    index_sha = sha256_file(index_path)
    if (
        index.get("schema_version") != MANAGER_OVERLAY_INDEX_SCHEMA
        or index.get("state") != "frozen-manager-overlay-selection"
        or index.get("selection_policy") != "every-overlay-id-is-explicitly-selected; no-directory-newest-selection"
    ):
        raise QueueError("manager overlay index has an unsupported schema, state or selection policy")
    baseline_sha = _declared_sha256(index.get("baseline_index_sha256"), "manager overlay index baseline")
    _baseline_path, baseline, actual_baseline_sha = _bound_index_artifact(
        index_root=index_root, record=index.get("baseline_index"), label="baseline index",
    )
    if actual_baseline_sha != baseline_sha:
        raise QueueError("manager overlay index baseline binding disagrees with its declared hash")
    if baseline.get("schema_version") != "pm99-season-baseline-index-v1" or baseline.get("state") != "frozen-provisional-base":
        raise QueueError("manager overlay index baseline has an unsupported schema or state")
    _selection_path, selection, selection_sha = _bound_index_artifact(
        index_root=index_root, record=index.get("selection_manifest"), label="selection manifest",
    )
    if (
        selection.get("schema_version") != MANAGER_OVERLAY_SELECTION_SCHEMA
        or selection.get("state") != "explicit-manager-overlay-selection"
        or selection.get("baseline_index_sha256") != baseline_sha
    ):
        raise QueueError("manager overlay selection manifest is stale or incompatible with its baseline")

    baseline_rows = baseline.get("seasons")
    index_rows = index.get("seasons")
    selection_rows = selection.get("seasons")
    if not isinstance(baseline_rows, list) or not isinstance(index_rows, list) or not isinstance(selection_rows, list):
        raise QueueError("manager overlay index, baseline or selection has no season rows")
    baseline_seasons = [row.get("season") for row in baseline_rows if isinstance(row, Mapping)]
    if len(baseline_seasons) != len(baseline_rows) or any(not isinstance(season, str) for season in baseline_seasons):
        raise QueueError("manager overlay index baseline has malformed season rows")
    selected_by_season: dict[str, str] = {}
    for row in selection_rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("season"), str) or not isinstance(row.get("overlay_id"), str):
            raise QueueError("manager overlay selection manifest has a malformed season row")
        season, overlay_id = row["season"], row["overlay_id"]
        if Path(overlay_id).name != overlay_id or not re.fullmatch(r"manager-v[1-9][0-9]*", overlay_id):
            raise QueueError(f"manager overlay selection manifest has invalid overlay ID for {season}")
        if season in selected_by_season:
            raise QueueError(f"manager overlay selection manifest duplicates {season}")
        selected_by_season[season] = overlay_id
    if set(selected_by_season) != set(baseline_seasons) or len(set(baseline_seasons)) != len(baseline_seasons):
        raise QueueError("manager overlay selection manifest does not select exactly the baseline seasons")
    rows_by_season: dict[str, Mapping[str, Any]] = {}
    for row in index_rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("season"), str):
            raise QueueError("manager overlay index has a malformed season row")
        season = row["season"]
        if season in rows_by_season:
            raise QueueError(f"manager overlay index duplicates {season}")
        if row.get("overlay_id") != selected_by_season.get(season):
            raise QueueError(f"manager overlay index selection is stale for {season}")
        rows_by_season[season] = row
    if set(rows_by_season) != set(baseline_seasons):
        raise QueueError("manager overlay index does not select exactly the baseline seasons")
    return index, {
        "path": relative_index_path,
        "path_base": "manager-overlay-index-root",
        "sha256": index_sha,
        "baseline_index_sha256": baseline_sha,
        "selection_manifest_sha256": selection_sha,
    }


def _manager_ledger_from_index(
    *, season: str, opening_dir: Path, source_sha256: str,
    index: Mapping[str, Any], index_root: Path, index_record: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    """Resolve the one explicitly selected overlay, rejecting every stale link."""

    matching = [row for row in index.get("seasons", []) if isinstance(row, Mapping) and row.get("season") == season]
    if len(matching) != 1:
        raise QueueError(f"manager overlay index does not select exactly one overlay for {season}")
    row = matching[0]
    overlay_id = row.get("overlay_id")
    if not isinstance(overlay_id, str) or not re.fullmatch(r"manager-v[1-9][0-9]*", overlay_id):
        raise QueueError(f"manager overlay index has an invalid overlay ID for {season}")
    audit_path, audit, audit_sha = _bound_index_artifact(
        index_root=index_root, record=row.get("manager_overlay_audit"), label=f"{season} selected overlay audit",
    )
    ledger_path, _ledger, ledger_sha = _bound_index_artifact(
        index_root=index_root, record=row.get("opening_manager_ledger"), label=f"{season} selected manager ledger",
    )
    if audit.get("schema_version") != MANAGER_OVERLAY_SCHEMA or audit.get("season") != season:
        raise QueueError(f"{season}: selected manager overlay audit has the wrong schema or season")
    base = audit.get("base")
    inputs = audit.get("inputs")
    outputs = audit.get("outputs")
    if not isinstance(base, Mapping) or base.get("baseline_index_sha256") != index_record["baseline_index_sha256"]:
        raise QueueError(f"{season}: selected manager overlay is bound to a different baseline")
    if not isinstance(inputs, Mapping) or not isinstance(outputs, Mapping):
        raise QueueError(f"{season}: selected manager overlay audit has no inputs or outputs")
    if inputs.get("source_capture_sha256") != source_sha256:
        raise QueueError(f"{season}: selected manager overlay source capture does not match the current allocation")
    lineups_path = opening_dir / "opening-lineups.json"
    try:
        lineups_sha = sha256_file(lineups_path)
    except OSError as exc:
        raise QueueError(f"{season}: selected manager overlay opening-lineup input is stale or missing") from exc
    if inputs.get("opening_lineups_sha256") != lineups_sha:
        raise QueueError(f"{season}: selected manager overlay opening-lineup input is stale or missing")
    if outputs.get("opening_manager_ledger_sha256") != ledger_sha:
        raise QueueError(f"{season}: selected manager overlay ledger is stale or missing")
    return ledger_path, {
        "overlay_id": overlay_id,
        "overlay_audit": {"path": audit_path.as_posix(), "sha256": audit_sha},
        "overlay_index": dict(index_record),
    }


def _manager_ledger_path(
    *, season: str, opening_dir: Path, source_sha256: str,
    manager_overlay_root: Path | None, manager_overlay_id: str | None,
) -> tuple[Path, dict[str, Any] | None]:
    """Select either the current ledger or one explicitly hash-bound overlay."""
    if manager_overlay_root is None and manager_overlay_id is None:
        return opening_dir / "opening-manager-ledger.json", None
    if manager_overlay_root is None or not manager_overlay_id:
        raise QueueError("manager overlay root and overlay ID must be supplied together")
    if Path(manager_overlay_id).name != manager_overlay_id:
        raise QueueError("manager overlay ID must be a single directory name")
    overlay_dir = manager_overlay_root / season / manager_overlay_id
    audit_path = overlay_dir / "manager-overlay-audit.json"
    ledger_path = overlay_dir / "opening-manager-ledger.json"
    audit = _read_object(audit_path, label="manager overlay audit")
    if audit.get("schema_version") != MANAGER_OVERLAY_SCHEMA or audit.get("season") != season:
        raise QueueError(f"{season}: manager overlay audit has the wrong schema or season")
    inputs = audit.get("inputs")
    outputs = audit.get("outputs")
    if not isinstance(inputs, Mapping) or not isinstance(outputs, Mapping):
        raise QueueError(f"{season}: manager overlay audit has no inputs or outputs")
    if inputs.get("source_capture_sha256") != source_sha256:
        raise QueueError(f"{season}: manager overlay source capture does not match the current allocation")
    expected_lineups = inputs.get("opening_lineups_sha256")
    lineups_path = opening_dir / "opening-lineups.json"
    if not isinstance(expected_lineups, str) or sha256_file(lineups_path) != expected_lineups:
        raise QueueError(f"{season}: manager overlay opening-lineup input is stale or missing")
    expected_ledger = outputs.get("opening_manager_ledger_sha256")
    if not isinstance(expected_ledger, str) or sha256_file(ledger_path) != expected_ledger:
        raise QueueError(f"{season}: manager overlay ledger is stale or missing")
    return ledger_path, {
        "overlay_id": manager_overlay_id,
        "overlay_audit": _path_record(audit_path),
    }


def _opening_reconciliation_path(
    *, season: str, opening_dir: Path, source_sha256: str,
    opening_xi_overlay_root: Path | None, opening_xi_overlay_id: str | None,
) -> tuple[Path, dict[str, Any] | None]:
    """Select the base reconciliation or one explicitly bound XI overlay.

    A caller may not silently consume whatever happens to be newest below an
    overlay directory.  Selecting an ID and checking both the current source
    and immutable base reconciliation prevents a stale historic-ID receipt
    from changing a source-completeness report.
    """
    base_path = opening_dir / "opening-lineup-reconciliation.json"
    if opening_xi_overlay_root is None and opening_xi_overlay_id is None:
        return base_path, None
    if opening_xi_overlay_root is None or not opening_xi_overlay_id:
        raise QueueError("opening-XI overlay root and overlay ID must be supplied together")
    if Path(opening_xi_overlay_id).name != opening_xi_overlay_id:
        raise QueueError("opening-XI overlay ID must be a single directory name")
    overlay_dir = opening_xi_overlay_root / season / opening_xi_overlay_id
    audit_path = overlay_dir / "opening-lineup-overlay-audit.json"
    reconciliation_path = overlay_dir / "opening-lineup-reconciliation.json"
    audit = _read_object(audit_path, label="opening-XI overlay audit")
    if audit.get("schema_version") != OPENING_XI_OVERLAY_SCHEMA or audit.get("season") != season:
        raise QueueError(f"{season}: opening-XI overlay audit has the wrong schema or season")
    inputs = audit.get("inputs")
    outputs = audit.get("outputs")
    if not isinstance(inputs, Mapping) or not isinstance(outputs, Mapping):
        raise QueueError(f"{season}: opening-XI overlay audit has no inputs or outputs")
    if inputs.get("source_capture_sha256") != source_sha256:
        raise QueueError(f"{season}: opening-XI overlay source capture does not match the current allocation")
    expected_base = inputs.get("base_reconciliation_sha256")
    if not isinstance(expected_base, str) or sha256_file(base_path) != expected_base:
        raise QueueError(f"{season}: opening-XI overlay base reconciliation is stale or missing")
    expected_output = outputs.get("opening_reconciliation_sha256")
    if not isinstance(expected_output, str) or sha256_file(reconciliation_path) != expected_output:
        raise QueueError(f"{season}: opening-XI overlay reconciliation is stale or missing")
    return reconciliation_path, {
        "overlay_id": opening_xi_overlay_id,
        "overlay_audit": _path_record(audit_path),
    }


def _opening_index(reconciliation: Mapping[str, Any]) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    return _unique_index(reconciliation.get("clubs"), label="opening-lineup reconciliation clubs")


def _kit_index(catalogue: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    rows = catalogue.get("rows")
    if not isinstance(rows, list):
        raise QueueError("kit catalogue rows must be a list")
    result: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("carrier_id"), int):
            raise QueueError("kit catalogue contains a malformed carrier row")
        carrier_id = int(row["carrier_id"])
        if carrier_id in result:
            raise QueueError(f"kit catalogue duplicates carrier {carrier_id}")
        result[carrier_id] = row
    return result


def _kit_binding_index(bindings: Mapping[str, Any]) -> dict[int, list[Mapping[str, Any]]]:
    rows = bindings.get("clubs")
    if not isinstance(rows, list):
        raise QueueError("kit render bindings clubs must be a list")
    result: dict[int, list[Mapping[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("carrier_id"), int):
            raise QueueError("kit render bindings contain a malformed carrier row")
        artifacts = row.get("artifacts")
        if not isinstance(artifacts, list):
            raise QueueError("kit render bindings artifacts must be a list")
        carrier_id = int(row["carrier_id"])
        if carrier_id in result:
            raise QueueError(f"kit render bindings duplicate carrier {carrier_id}")
        result[carrier_id] = [artifact for artifact in artifacts if isinstance(artifact, Mapping)]
    return result


def _binding_is_materialised(artifacts: Iterable[Mapping[str, Any]], *, binding_root: Path) -> bool:
    materialised = list(artifacts)
    if not materialised:
        return False
    for artifact in materialised:
        relative = artifact.get("relative_path")
        declared = artifact.get("sha256")
        if not isinstance(relative, str) or not isinstance(declared, str) or not SHA256_RE.fullmatch(declared):
            return False
        path = binding_root / relative
        if not path.is_file() or sha256_file(path) != declared:
            return False
    return True


def _secondary_fact_counts(source_row: Mapping[str, Any]) -> tuple[int, Counter[str]]:
    players = source_row.get("players")
    if not isinstance(players, list):
        raise QueueError("source intake club players must be a list")
    unresolved = Counter()
    for player in players:
        if not isinstance(player, Mapping):
            raise QueueError("source intake player row is malformed")
        facts = player.get("facts")
        if not isinstance(facts, Mapping):
            raise QueueError("source intake player facts are malformed")
        fields = facts.get("unresolved_fields")
        if fields is None:
            continue
        if not isinstance(fields, list) or not all(isinstance(field, str) and field for field in fields):
            raise QueueError("source intake unresolved_fields must be a list of field names")
        unresolved.update(fields)
    return len(players), unresolved


def _work_item(
    *, carrier_id: int, club_name: str, selector: tuple[str, str, str], lane: str,
    reason: str, required_resolution: str, opening_row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "carrier_id": carrier_id,
        "club_name": club_name,
        "source_selector": _selector_object(selector),
        "lane": lane,
        "reason": reason,
        "required_resolution": required_resolution,
    }
    if opening_row is not None and opening_row.get("first_league_fixture_date"):
        result["known_opening_fixture_date"] = opening_row["first_league_fixture_date"]
    return result


def _season_commands(
    *, source_path: Path, opening_dir: Path, output_root: Path, season: str,
) -> dict[str, str]:
    output_dir = output_root / season
    return {
        "inspect": (
            "python3 scripts/season_source_completeness_queue_v1.py "
            f"--season {season} --output-json {output_root / (season + '.json')}"
        ),
        "capture_manager_history": (
            "python3 scripts/capture_opening_manager_history_supplements_v1.py "
            f"--source-capture {source_path} --opening-lineups {opening_dir / 'opening-lineups.json'} "
            f"--lineup-source-selection {opening_dir / 'source-selectors.json'} "
            f"--competition-map {opening_dir / 'competition-map.json'} "
            "--cache-dir .local/external-sources/cache.transfermarkt-opening "
            f"--output {output_dir / 'opening-manager-supplement.transfermarkt.json'}"
        ),
        "rebuild_manager_ledger": (
            "python3 scripts/materialise_opening_manager_ledger_v1.py "
            f"--source-capture {source_path} --opening-lineups {opening_dir / 'opening-lineups.json'} "
            f"--supplement {output_dir / 'opening-manager-supplement.json'} "
            f"--output {output_dir / 'opening-manager-ledger.json'} --strict"
        ),
        "reconcile_opening_xi": (
            "python3 scripts/reconcile_transfermarkt_opening_lineups_v1.py "
            f"--source-capture {source_path} --opening-lineups {opening_dir / 'opening-lineups.json'} "
            f"--output {output_dir / 'opening-lineup-reconciliation.json'}"
        ),
    }


def _build_season(
    *, pointer_path: Path, current_root: Path, opening_root: Path, kit_root: Path,
    kit_bindings_root: Path, calendar_root: Path, output_root: Path,
    manager_overlay_root: Path | None, manager_overlay_id: str | None,
    manager_overlay_index: Mapping[str, Any] | None,
    manager_overlay_index_root: Path | None, manager_overlay_index_record: Mapping[str, Any] | None,
    opening_xi_overlay_root: Path | None, opening_xi_overlay_id: str | None,
) -> dict[str, Any]:
    season = pointer_path.parent.name
    pointer = _read_object(pointer_path, label="current pointer")
    if pointer.get("schema_version") != CURRENT_SCHEMA or pointer.get("season") != season:
        raise QueueError(f"{pointer_path}: unsupported or mismatched current pointer")
    source_path, source_record = _resolved_pointer_artifact(pointer_path, pointer, "source")
    intake_path, intake_record = _resolved_pointer_artifact(pointer_path, pointer, "intake")
    allocation_path, allocation_record = _resolved_pointer_artifact(pointer_path, pointer, "allocation")
    source = _read_object(source_path, label="source capture")
    intake = _read_object(intake_path, label="source intake")
    allocation = _read_object(allocation_path, label="carrier allocation")
    if not isinstance(source.get("clubs"), list) or not isinstance(intake.get("source_clubs"), list):
        raise QueueError(f"{season}: source capture or source intake lacks club rows")
    source_clubs = _unique_index(intake["source_clubs"], label="source intake clubs")
    assignments = allocation.get("assignments")
    if not isinstance(assignments, list):
        raise QueueError(f"{season}: carrier allocation assignments must be a list")

    opening_dir = opening_root / season
    if manager_overlay_index is not None:
        if manager_overlay_index_root is None or manager_overlay_index_record is None:
            raise QueueError("manager overlay index state is incomplete")
        manager_path, manager_overlay = _manager_ledger_from_index(
            season=season, opening_dir=opening_dir, source_sha256=str(source_record["sha256"]),
            index=manager_overlay_index, index_root=manager_overlay_index_root,
            index_record=manager_overlay_index_record,
        )
    else:
        manager_path, manager_overlay = _manager_ledger_path(
            season=season, opening_dir=opening_dir, source_sha256=str(source_record["sha256"]),
            manager_overlay_root=manager_overlay_root, manager_overlay_id=manager_overlay_id,
        )
    reconciliation_path, opening_xi_overlay = _opening_reconciliation_path(
        season=season, opening_dir=opening_dir, source_sha256=str(source_record["sha256"]),
        opening_xi_overlay_root=opening_xi_overlay_root, opening_xi_overlay_id=opening_xi_overlay_id,
    )
    if not manager_path.is_file() or not reconciliation_path.is_file():
        raise QueueError(f"{season}: opening manager ledger or lineup reconciliation is missing")
    managers, manager_gaps = _manager_indexes(_read_object(manager_path, label="opening manager ledger"))
    openings = _opening_index(_read_object(reconciliation_path, label="opening lineup reconciliation"))

    kit_path = kit_root / season / "kit-catalogue-v1.json"
    binding_path = kit_bindings_root / season / "kit-render-bindings-v1.json"
    kit_catalogue = _read_object(kit_path, label="kit catalogue") if kit_path.is_file() else None
    kit_bindings = _read_object(binding_path, label="kit render bindings") if binding_path.is_file() else None
    kit_rows = _kit_index(kit_catalogue) if kit_catalogue is not None else {}
    binding_rows = _kit_binding_index(kit_bindings) if kit_bindings is not None else {}
    kit_binding_matches_catalogue = (
        kit_catalogue is not None
        and kit_bindings is not None
        and kit_bindings.get("kit_catalogue_sha256") == sha256_file(kit_path)
    )
    calendar_path = calendar_root / season / "calendar-receipt.json"

    assigned: set[int] = set()
    manager_counts = Counter()
    opening_counts = Counter()
    squad_counts = Counter()
    kit_counts = Counter()
    fact_counts = Counter()
    manager_queue: list[dict[str, Any]] = []
    opening_queue: list[dict[str, Any]] = []
    kit_queue: list[dict[str, Any]] = []

    for assignment in assignments:
        if not isinstance(assignment, Mapping):
            raise QueueError(f"{season}: carrier allocation contains a malformed assignment")
        carrier_id = assignment.get("carrier_id")
        club_name = str(assignment.get("club_name") or "").strip()
        capacity = assignment.get("roster_capacity")
        if not isinstance(carrier_id, int) or carrier_id <= 0 or carrier_id in assigned:
            raise QueueError(f"{season}: carrier allocation has an invalid or duplicate carrier")
        if not club_name or not isinstance(capacity, int) or capacity < 11:
            raise QueueError(f"{season}: carrier allocation has an invalid club or roster capacity")
        assigned.add(carrier_id)
        selector = _selector(assignment, club_name=club_name)
        source_row = source_clubs.get(selector)
        if source_row is None:
            raise QueueError(f"{season}: allocation source selector is absent from current intake: {selector}")
        player_count, unresolved_facts = _secondary_fact_counts(source_row)
        fact_counts.update(unresolved_facts)
        squad_counts["required_carriers"] += 1
        squad_counts["source_player_rows"] += player_count
        if player_count >= 11:
            squad_counts["at_least_eleven_player_rows"] += 1
        else:
            squad_counts["under_eleven_player_rows"] += 1
        if player_count < capacity:
            squad_counts["below_fixed_capacity"] += 1
        elif player_count > capacity:
            squad_counts["capacity_trim_required"] += 1
        else:
            squad_counts["exact_fixed_capacity"] += 1

        opening_row = openings.get(selector)
        manager_row = managers.get(selector)
        if manager_row is not None:
            valid_manager, manager_problem = _valid_manager(manager_row)
            if valid_manager:
                manager_counts["exact_dated_hash_backed"] += 1
            else:
                manager_counts["invalid_evidence"] += 1
                manager_queue.append(_work_item(
                    carrier_id=carrier_id, club_name=club_name, selector=selector, lane="manager",
                    reason=str(manager_problem),
                    required_resolution="replace with one exact opening-date manager name and dated hash-backed evidence",
                    opening_row=opening_row,
                ))
        else:
            gap = manager_gaps.get(selector)
            reason = str((gap or {}).get("reason") or "manager-ledger-has-no-selector")
            manager_counts["unresolved"] += 1
            manager_queue.append(_work_item(
                carrier_id=carrier_id, club_name=club_name, selector=selector, lane="manager",
                reason=reason,
                required_resolution="add one exact opening-date manager string with dated hash-backed evidence; no native fallback",
                opening_row=opening_row,
            ))

        if opening_row is None:
            opening_counts["missing_reconciliation_row"] += 1
            opening_queue.append(_work_item(
                carrier_id=carrier_id, club_name=club_name, selector=selector, lane="opening-xi",
                reason="opening-lineup-reconciliation-has-no-selector",
                required_resolution="capture and reconcile the first league XI, then use a published or deterministically inferred formation",
            ))
        elif opening_row.get("starting_xi_reconciled") is not True:
            opening_counts["unreconciled_xi"] += 1
            opening_queue.append(_work_item(
                carrier_id=carrier_id, club_name=club_name, selector=selector, lane="opening-xi",
                reason="opening-xi-not-reconciled-to-source-squad",
                required_resolution="reconcile the sourced first league XI to the opening squad",
                opening_row=opening_row,
            ))
        elif not isinstance(opening_row.get("starting_xi"), list) or len(opening_row["starting_xi"]) != 11:
            opening_counts["invalid_xi_cardinality"] += 1
            opening_queue.append(_work_item(
                carrier_id=carrier_id, club_name=club_name, selector=selector, lane="opening-xi",
                reason="reconciled-opening-xi-does-not-have-eleven-players",
                required_resolution="repair the source receipt or reconciliation to exactly eleven starters",
                opening_row=opening_row,
            ))
        elif _formation_is_published(opening_row.get("formation")):
            opening_counts["usable_published_formation"] += 1
        elif _formation_is_inferable(opening_row["starting_xi"]):
            opening_counts["usable_deterministic_formation"] += 1
        else:
            opening_counts["formation_unusable"] += 1
            opening_queue.append(_work_item(
                carrier_id=carrier_id, club_name=club_name, selector=selector, lane="opening-xi",
                reason="sourced-xi-has-no-published-or-deterministically-inferable-formation",
                required_resolution="capture a published formation or reconcile G/D/M/F positions so the authorised deterministic inference can run",
                opening_row=opening_row,
            ))

        kit_row = kit_rows.get(carrier_id)
        if kit_row is None:
            kit_counts["catalogue_missing"] += 1
            kit_queue.append(_work_item(
                carrier_id=carrier_id, club_name=club_name, selector=selector, lane="kit",
                reason="kit-catalogue-has-no-carrier-row",
                required_resolution="supply historical kit evidence and a rendered receipt; native fallback is only valid for exited carriers",
            ))
        elif (
            kit_row.get("status") == "native-fallback-authorized"
            and kit_row.get("carrier_status") == "exited"
        ):
            kit_counts["native_exited_fallback_authorized"] += 1
        elif kit_row.get("status") == "source-ready" and kit_binding_matches_catalogue and _binding_is_materialised(
            binding_rows.get(carrier_id, []), binding_root=binding_path.parent,
        ):
            kit_counts["source_ready_rendered"] += 1
        else:
            kit_counts["source_or_render_unresolved"] += 1
            reason = "kit-render-binding-stale-or-missing" if kit_binding_matches_catalogue else "kit-catalogue-or-binding-hash-mismatch"
            kit_queue.append(_work_item(
                carrier_id=carrier_id, club_name=club_name, selector=selector, lane="kit",
                reason=reason,
                required_resolution="complete the historical kit source and matching rendered receipt, or prove the carrier exited before native fallback",
            ))

    allocation_gaps = allocation.get("gaps")
    if not isinstance(allocation_gaps, list):
        raise QueueError(f"{season}: carrier allocation gaps must be a list")
    blocking_allocation_gaps = sum(
        isinstance(row, Mapping) and row.get("status") == "source-unavailable-or-insufficient-country-capacity-blocked"
        for row in allocation_gaps
    )
    for key in ("exact_dated_hash_backed", "invalid_evidence", "unresolved"):
        manager_counts.setdefault(key, 0)
    for key in (
        "missing_reconciliation_row", "unreconciled_xi", "invalid_xi_cardinality",
        "formation_unusable", "usable_published_formation", "usable_deterministic_formation",
    ):
        opening_counts.setdefault(key, 0)
    for key in (
        "at_least_eleven_player_rows", "under_eleven_player_rows", "below_fixed_capacity",
        "capacity_trim_required", "exact_fixed_capacity",
    ):
        squad_counts.setdefault(key, 0)
    for key in (
        "catalogue_missing", "native_exited_fallback_authorized", "source_ready_rendered",
        "source_or_render_unresolved",
    ):
        kit_counts.setdefault(key, 0)
    manager_counts["required_carriers"] = len(assigned)
    opening_counts["required_carriers"] = len(assigned)
    opening_counts["usable_total"] = (
        opening_counts["usable_published_formation"] + opening_counts["usable_deterministic_formation"]
    )
    manager_counts["queue_total"] = manager_counts["unresolved"] + manager_counts["invalid_evidence"]
    opening_counts["queue_total"] = len(opening_queue)
    kit_counts["queue_total"] = len(kit_queue)

    return {
        "season": season,
        "classification": "source-queue-not-a-playable-claim",
        "inputs": {
            "current_pointer": _path_record(pointer_path),
            "current_revision_id": pointer.get("revision_id"),
            "source": source_record,
            "intake": intake_record,
            "allocation": allocation_record,
            "opening_manager_ledger": _path_record(manager_path),
            "manager_overlay": manager_overlay,
            "opening_reconciliation": _path_record(reconciliation_path),
            "opening_xi_overlay": opening_xi_overlay,
            "kit_catalogue": _path_record(kit_path),
            "kit_render_bindings": _path_record(binding_path),
            "calendar_receipt": _path_record(calendar_path),
        },
        "scope": {
            "source_capture_club_count": len(source["clubs"]),
            "source_intake_club_count": len(source_clubs),
            "assigned_fixed_carrier_count": len(assigned),
            "allocation_gap_count": len(allocation_gaps),
            "blocking_allocation_gap_count": blocking_allocation_gaps,
        },
        "manager_identity": dict(sorted(manager_counts.items())),
        "opening_xi_and_august_squad": {
            "opening_xi": dict(sorted(opening_counts.items())),
            "opening_squad": dict(sorted(squad_counts.items())),
        },
        "secondary_player_facts": {
            "policy": "logged-nonblocking-fallback",
            "unresolved_field_count": sum(fact_counts.values()),
            "unresolved_field_counts": dict(sorted(fact_counts.items())),
        },
        "portraits": {
            "policy": "optional-native-no-photo-fallback",
            "source_queue_count": 0,
        },
        "kits": {
            "policy": "historical-source-and-render-required-for-continuing-carriers; native-only-if-exited",
            "catalogue_binding_matches": kit_binding_matches_catalogue,
            "coverage": dict(sorted(kit_counts.items())),
        },
        "work_queues": {
            "manager": sorted(manager_queue, key=lambda row: (row["carrier_id"], row["club_name"])),
            "opening_xi": sorted(opening_queue, key=lambda row: (row["carrier_id"], row["club_name"])),
            "kit": sorted(kit_queue, key=lambda row: (row["carrier_id"], row["club_name"])),
        },
        "commands": _season_commands(
            source_path=source_path, opening_dir=opening_dir, output_root=output_root, season=season,
        ),
    }


def _sum(rows: Iterable[Mapping[str, Any]], *path: str) -> int:
    total = 0
    for row in rows:
        value: Any = row
        for key in path:
            value = value.get(key, {}) if isinstance(value, Mapping) else {}
        if isinstance(value, int) and not isinstance(value, bool):
            total += value
    return total


def build_report(
    *, current_root: Path, opening_root: Path, kit_root: Path, kit_bindings_root: Path,
    calendar_root: Path, output_root: Path, seasons: Sequence[str] | None = None,
    manager_overlay_root: Path | None = None, manager_overlay_id: str | None = None,
    manager_overlay_index_path: Path | None = None, manager_overlay_index_root: Path = ROOT,
    opening_xi_overlay_root: Path | None = None, opening_xi_overlay_id: str | None = None,
) -> dict[str, Any]:
    """Return a fixed-carrier source queue without changing any input artifact."""

    if manager_overlay_index_path is not None and (manager_overlay_root is not None or manager_overlay_id is not None):
        raise QueueError("manager overlay index cannot be combined with a root/ID overlay selection")
    manager_overlay_index: dict[str, Any] | None = None
    manager_overlay_index_record: dict[str, Any] | None = None
    if manager_overlay_index_path is not None:
        manager_overlay_index, manager_overlay_index_record = _manager_overlay_index(
            index_path=manager_overlay_index_path, index_root=manager_overlay_index_root,
        )
    wanted = set(seasons or ())
    pointers = sorted(current_root.glob("*/current.json"))
    if wanted:
        pointers = [path for path in pointers if path.parent.name in wanted]
        missing = wanted - {path.parent.name for path in pointers}
        if missing:
            raise QueueError(f"missing current pointers: {', '.join(sorted(missing))}")
    if not pointers:
        raise QueueError("no current pointers selected")
    rows = [
        _build_season(
            pointer_path=pointer, current_root=current_root, opening_root=opening_root,
            kit_root=kit_root, kit_bindings_root=kit_bindings_root,
            calendar_root=calendar_root, output_root=output_root,
            manager_overlay_root=manager_overlay_root, manager_overlay_id=manager_overlay_id,
            manager_overlay_index=manager_overlay_index,
            manager_overlay_index_root=manager_overlay_index_root if manager_overlay_index is not None else None,
            manager_overlay_index_record=manager_overlay_index_record,
            opening_xi_overlay_root=opening_xi_overlay_root, opening_xi_overlay_id=opening_xi_overlay_id,
        )
        for pointer in pointers
    ]
    return {
        "schema_version": SCHEMA,
        "classification": "source-completeness-queue-not-a-release-or-playable-claim",
        "inputs": {
            "manager_overlay_index": manager_overlay_index_record,
        },
        "policies": {
            "manager": "exact-opening-date-name-with-dated-hash-backed-evidence; no-native-fallback",
            "opening_squad": "first-league-XI-plus-capacity-fitting-opening-squad; no-later-season-arrivals-required",
            "formation": "published-opening-formation-or-deterministic-inference-from-reconciled-G-D-M-F-XI",
            "secondary_player_facts": "logged-nonblocking-fallback",
            "portraits": "optional-native-no-photo-fallback",
            "kits": "historical-source-and-render-for-continuing-carriers; native-only-if-exited",
        },
        "seasons": rows,
        "summary": {
            "season_count": len(rows),
            "assigned_fixed_carrier_count": _sum(rows, "scope", "assigned_fixed_carrier_count"),
            "blocking_allocation_gap_count": _sum(rows, "scope", "blocking_allocation_gap_count"),
            "exact_dated_hash_backed_manager_count": _sum(rows, "manager_identity", "exact_dated_hash_backed"),
            "manager_work_item_count": sum(len(row["work_queues"]["manager"]) for row in rows),
            "usable_opening_xi_count": _sum(rows, "opening_xi_and_august_squad", "opening_xi", "usable_total"),
            "published_formation_count": _sum(rows, "opening_xi_and_august_squad", "opening_xi", "usable_published_formation"),
            "deterministically_inferred_formation_count": _sum(rows, "opening_xi_and_august_squad", "opening_xi", "usable_deterministic_formation"),
            "opening_xi_work_item_count": sum(len(row["work_queues"]["opening_xi"]) for row in rows),
            "opening_squad_under_eleven_count": _sum(rows, "opening_xi_and_august_squad", "opening_squad", "under_eleven_player_rows"),
            "secondary_player_fact_fallback_count": _sum(rows, "secondary_player_facts", "unresolved_field_count"),
            "kit_work_item_count": sum(len(row["work_queues"]["kit"]) for row in rows),
            "portrait_work_item_count": 0,
            "playable_count": 0,
        },
    }


def markdown_report(report: Mapping[str, Any]) -> str:
    """Render a compact, stable handover view while JSON keeps every work item."""

    summary = report["summary"]
    lines = [
        "# Season source-completeness queue",
        "",
        "This is a deterministic source and authoring queue, not a release or playable-game claim.",
        "",
        "| Measure | Count |",
        "| --- | ---: |",
    ]
    labels = (
        ("Seasons", "season_count"),
        ("Assigned fixed carriers", "assigned_fixed_carrier_count"),
        ("Exact dated, hash-backed managers", "exact_dated_hash_backed_manager_count"),
        ("Manager work items", "manager_work_item_count"),
        ("Usable opening XIs", "usable_opening_xi_count"),
        ("Published formations", "published_formation_count"),
        ("Authorised deterministic formation inferences", "deterministically_inferred_formation_count"),
        ("Opening-XI work items", "opening_xi_work_item_count"),
        ("Opening squads under eleven players", "opening_squad_under_eleven_count"),
        ("Non-blocking secondary fact fallbacks", "secondary_player_fact_fallback_count"),
        ("Kit work items", "kit_work_item_count"),
        ("Playable", "playable_count"),
    )
    lines.extend(f"| {label} | {summary[key]} |" for label, key in labels)
    lines.extend(["", "## Per-season priority", "", "| Season | Managers queued | XI queued | Kits queued |", "| --- | ---: | ---: | ---: |"])
    for row in report["seasons"]:
        queues = row["work_queues"]
        lines.append(
            f"| {row['season']} | {len(queues['manager'])} | {len(queues['opening_xi'])} | {len(queues['kit'])} |"
        )
    lines.extend([
        "",
        "The JSON companion retains one stable selector, carrier ID and required resolution for each work item.",
        "Portraits are intentionally absent from the queue: the agreed native no-photo fallback is valid.",
        "",
    ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-root", type=Path, default=ROOT / ".local/season-historical-squad-backfill-v1")
    parser.add_argument("--opening-root", type=Path, default=ROOT / ".local/transfermarkt-opening-plans-current-v1")
    parser.add_argument("--kit-root", type=Path, default=ROOT / ".local/season-kit-sources-historical-backfill-v1")
    parser.add_argument("--kit-bindings-root", type=Path, default=ROOT / ".local/season-kit-renders-historical-backfill-v1")
    parser.add_argument("--calendar-root", type=Path, default=ROOT / ".local/calendar-v1")
    parser.add_argument("--manager-overlay-root", type=Path,
                        help="root containing explicit append-only manager overlays")
    parser.add_argument("--manager-overlay-id",
                        help="one explicit overlay directory name (for example manager-v2)")
    parser.add_argument("--manager-overlay-index", type=Path,
                        help="hash-bound per-season manager-overlay index; cannot be combined with root/ID")
    parser.add_argument("--manager-overlay-index-root", type=Path, default=ROOT,
                        help="workspace root used by safe relative paths in --manager-overlay-index")
    parser.add_argument("--opening-xi-overlay-root", type=Path,
                        help="root containing explicit append-only opening-XI overlays")
    parser.add_argument("--opening-xi-overlay-id",
                        help="one explicit opening-XI overlay directory name (for example opening-xi-v1)")
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-markdown", type=Path)
    parser.add_argument("--season", action="append", dest="seasons")
    args = parser.parse_args(argv)
    try:
        report = build_report(
            current_root=args.current_root, opening_root=args.opening_root,
            kit_root=args.kit_root, kit_bindings_root=args.kit_bindings_root,
            calendar_root=args.calendar_root, output_root=args.output_json.parent,
            seasons=args.seasons, manager_overlay_root=args.manager_overlay_root,
            manager_overlay_id=args.manager_overlay_id,
            manager_overlay_index_path=args.manager_overlay_index,
            manager_overlay_index_root=args.manager_overlay_index_root,
            opening_xi_overlay_root=args.opening_xi_overlay_root,
            opening_xi_overlay_id=args.opening_xi_overlay_id,
        )
    except QueueError as exc:
        parser.error(str(exc))
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_bytes(canonical_json_bytes(report))
    if args.output_markdown is not None:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
