#!/usr/bin/env python3
"""Create a fail-closed canonical-workspace candidate from a bound V2 draft.

This factory is deliberately an *ingress* step.  It proves that a
calendar-bound, canonical Season Package V2 can be carried into the
year-neutral workspace contract without silently declaring it a playable
release.  It writes:

* a byte-identical canonical-package candidate;
* a verified-base descriptor copy, editorial timeline and valid workspace;
* the deterministic ``prepare`` outputs used by the binary compiler; and
* a non-executable V2 build-plan **candidate** documenting the remaining
  evidence required to create an actual V2 build plan.

It never materialises a game tree, runs the binary compiler, writes a release
manifest, launches PM99, or records runtime/screenshot evidence.  Those are
separate gates and therefore cannot be accidentally implied by this tool.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_editorial_timeline_v1 as editorial_v1  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_pipeline_v2 as pipeline_v2  # noqa: E402
from scripts import season_workspace_v1 as workspace_v1  # noqa: E402


SCHEMA = "pm99-season-canonical-promotion-factory-v1"
BUILD_PLAN_CANDIDATE_SCHEMA = "pm99-season-build-plan-candidate-v1"
CALENDAR_OVERLAY_AUDIT_SCHEMA = "pm99-season-calendar-package-overlay-v1"
SOURCE_BUILD_AUDIT_SCHEMA = "pm99-season-source-package-build-audit-v1"
DISPLAY_ALIAS_AUDIT_SCHEMA = "pm99-season-package-display-alias-repair-v1"
MODE1_ROSTER_RECONCILIATION_SCHEMA = "pm99-mode1-roster-base-reconciliation-v1"
MODE1_ROSTER_RECONCILIATION_STATE = "base-roster-reconciled-static-candidate-only"


class PromotionFactoryError(ValueError):
    """The supplied draft cannot honestly enter the canonical-workspace lane."""


def _bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return package_v2.sha256_file(path)


def _read_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromotionFactoryError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PromotionFactoryError(f"{label} must be a JSON object: {path}")
    return value, payload


def _write(path: Path, value: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _bytes(dict(value))
    path.write_bytes(payload)
    return _sha256_bytes(payload)


def _season_id(package: Mapping[str, Any]) -> str:
    season = package.get("season")
    if not isinstance(season, Mapping):
        raise PromotionFactoryError("package has no season")
    start = season.get("start_year")
    end = season.get("end_year")
    if not isinstance(start, int) or not isinstance(end, int):
        raise PromotionFactoryError("package season has invalid years")
    result = f"{start:04d}-{end % 100:02d}"
    if pipeline_v2.normalise_season_id(result) != result:
        raise PromotionFactoryError("package season is outside the V2 historical range")
    return result


def _calendar_binding(
    *, package: Mapping[str, Any], package_sha256: str, calendar_audit: Mapping[str, Any]
) -> dict[str, Any]:
    """Verify either a direct overlay or a hash-preserving source-build chain."""

    schema = calendar_audit.get("schema_version")
    chain_template_sha256: str | None = None
    if schema == CALENDAR_OVERLAY_AUDIT_SCHEMA:
        overlay_audit = calendar_audit
        if overlay_audit.get("output_package_sha256") != package_sha256:
            raise PromotionFactoryError("calendar audit does not bind this exact package byte stream")
    elif schema == SOURCE_BUILD_AUDIT_SCHEMA:
        if calendar_audit.get("draft_package_sha256") != package_sha256:
            raise PromotionFactoryError("source build audit does not bind this exact package byte stream")
        binding = calendar_audit.get("calendar_binding")
        if not isinstance(binding, Mapping):
            raise PromotionFactoryError("source build audit has no verified calendar-binding chain")
        overlay_audit = binding.get("overlay_audit")
        if not isinstance(overlay_audit, Mapping):
            raise PromotionFactoryError("source build audit lacks the canonical calendar overlay audit")
        if binding.get("audit_sha256") != _sha256_bytes(_bytes(dict(overlay_audit))):
            raise PromotionFactoryError("source build audit calendar-overlay hash is inconsistent")
        chain_template_sha256 = binding.get("template_package_sha256")
        if not package_v2.SHA256_RE.fullmatch(str(chain_template_sha256 or "")):
            raise PromotionFactoryError("source build audit calendar template hash is invalid")
        if overlay_audit.get("output_package_sha256") != chain_template_sha256:
            raise PromotionFactoryError("source build audit calendar chain targets a different template")
        if binding.get("calendar") != package.get("calendar"):
            raise PromotionFactoryError("source build audit did not preserve the calendar contract")
        artifact_id = package.get("calendar", {}).get("patch_artifact_id") if isinstance(package.get("calendar"), Mapping) else None
        artifacts = package.get("artifacts")
        artifact = next(
            (item for item in artifacts if isinstance(item, Mapping) and item.get("id") == artifact_id),
            None,
        ) if isinstance(artifacts, list) else None
        if binding.get("artifact") != artifact:
            raise PromotionFactoryError("source build audit did not preserve the calendar receipt artifact")
    else:
        raise PromotionFactoryError("calendar audit has an unsupported schema")

    if overlay_audit.get("runtime_validation_pending") is not True:
        raise PromotionFactoryError("calendar audit must explicitly retain runtime validation as pending")
    receipt_sha256 = overlay_audit.get("receipt_sha256")
    executable_sha256 = overlay_audit.get("executable_sha256")
    if not package_v2.SHA256_RE.fullmatch(str(receipt_sha256 or "")):
        raise PromotionFactoryError("calendar audit has an invalid receipt SHA-256")
    if not package_v2.SHA256_RE.fullmatch(str(executable_sha256 or "")):
        raise PromotionFactoryError("calendar audit has an invalid executable SHA-256")
    calendar = package.get("calendar")
    if not isinstance(calendar, Mapping):
        raise PromotionFactoryError("package has no calendar contract")
    season = package["season"]
    if (
        calendar.get("base_year") != 1998
        or calendar.get("target_year") != season["start_year"]
        or calendar.get("target_rollover_year") != season["end_year"]
    ):
        raise PromotionFactoryError("package calendar does not match the package season")
    if overlay_audit.get("patch_count") != 853:
        raise PromotionFactoryError("calendar audit does not use the proved PM99 patch count")
    artifact_id = calendar.get("patch_artifact_id")
    artifacts = package.get("artifacts")
    if not isinstance(artifact_id, str) or not isinstance(artifacts, list):
        raise PromotionFactoryError("package calendar has no patch artifact")
    artifact = next((item for item in artifacts if isinstance(item, Mapping) and item.get("id") == artifact_id), None)
    if artifact is None or artifact.get("kind") != "calendar-patch":
        raise PromotionFactoryError("package calendar artifact is absent or has the wrong kind")
    if artifact.get("sha256") != receipt_sha256:
        raise PromotionFactoryError("package calendar artifact is not bound to the audited receipt")
    return {
        "calendar_receipt_sha256": receipt_sha256,
        "calendar_executable_sha256": executable_sha256,
        "calendar_patch_artifact_id": artifact_id,
        "calendar_patch_count": 853,
        "calendar_binding_path": (
            "direct-overlay" if chain_template_sha256 is None else "source-build-preserved-overlay"
        ),
    }


def _workspace(
    *, package: Mapping[str, Any], package_sha256: str, base_sha256: str,
    timeline_sha256: str, alias_bound: bool = False, roster_bound: bool = False,
) -> dict[str, Any]:
    season_id = _season_id(package)
    if roster_bound:
        workspace_suffix = "alias-roster-bound-canonical-candidate"
    elif alias_bound:
        workspace_suffix = "alias-bound-canonical-candidate"
    else:
        workspace_suffix = "canonical-candidate"
    return {
        "schema_version": workspace_v1.SCHEMA,
        "workspace_id": f"world-{season_id}-{workspace_suffix}",
        "season": season_id,
        "base": {
            "role": "clean-original",
            "descriptor": {"relative_path": "verified-base.json", "sha256": base_sha256},
        },
        "package": {"relative_path": "season-package.candidate.json", "sha256": package_sha256},
        "editorial": {
            "timeline": {"relative_path": "editorial-timeline.json", "sha256": timeline_sha256},
            "derived_package_id": f"world-{season_id}-candidate-effective",
            "override_id": f"world-{season_id}-candidate-overrides",
        },
        "ratings": {"precedence": workspace_v1.PRECEDENCE},
        "portraits": {"failure_policy": "native-no-photo", "record_missing": True},
    }


def _inventory_file_sha256(base: Mapping[str, Any], relative_path: str) -> str | None:
    """Return one verified inventory hash without assuming its position."""

    inventory = base.get("inventory")
    files = inventory.get("files") if isinstance(inventory, Mapping) else None
    if not isinstance(files, list):
        return None
    for row in files:
        if isinstance(row, Mapping) and row.get("path") == relative_path:
            value = row.get("sha256")
            return value if isinstance(value, str) else None
    return None


def _alias_binding(
    *, source_package: Mapping[str, Any], source_package_sha256: str,
    alias_package: Mapping[str, Any], alias_package_sha256: str,
    alias_audit: Mapping[str, Any], base: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify a parser-safe display-only derivative of a bound source package.

    Alias repair is permitted only after source ingress.  This checker proves
    that the repair changed no identity, facts, roster, artefact, or calendar
    data, and that its receipt is tied to the same verified clean base.  It
    intentionally does not treat the derivative as a release package.
    """

    if alias_audit.get("schema_version") != DISPLAY_ALIAS_AUDIT_SCHEMA:
        raise PromotionFactoryError("display alias audit has an unsupported schema")
    if alias_audit.get("state") != "alias-bound-static-candidate-only":
        raise PromotionFactoryError("display alias audit does not declare a static-only candidate")
    if alias_audit.get("release_eligible") is not False:
        raise PromotionFactoryError("display alias audit must explicitly remain release-ineligible")
    if alias_audit.get("calendar_contract_preserved") is not True:
        raise PromotionFactoryError("display alias audit did not preserve the calendar contract")
    if source_package.get("calendar") != alias_package.get("calendar"):
        raise PromotionFactoryError("display alias package changed the calendar contract")
    if source_package.get("season") != alias_package.get("season"):
        raise PromotionFactoryError("display alias package changed the season")

    inputs = alias_audit.get("input")
    output = alias_audit.get("output")
    if not isinstance(inputs, Mapping) or not isinstance(output, Mapping):
        raise PromotionFactoryError("display alias audit lacks input or output bindings")
    if inputs.get("package_sha256") != source_package_sha256:
        raise PromotionFactoryError("display alias audit does not bind the source package")
    if output.get("package_sha256") != alias_package_sha256:
        raise PromotionFactoryError("display alias audit does not bind the alias package")
    if inputs.get("calendar_contract_sha256") != _sha256_bytes(_bytes(dict(source_package["calendar"]))):
        raise PromotionFactoryError("display alias audit calendar hash is inconsistent")
    inventory = base["inventory"]
    if inputs.get("base_inventory_fingerprint") != inventory["files_fingerprint"]:
        raise PromotionFactoryError("display alias audit targets a different verified base inventory")
    base_jug_sha256 = _inventory_file_sha256(base, "DBDAT/JUG98030.FDI")
    if base_jug_sha256 is not None and inputs.get("base_jug98030_sha256") != base_jug_sha256:
        raise PromotionFactoryError("display alias audit targets a different verified base player database")

    source_players = source_package.get("players")
    alias_players = alias_package.get("players")
    if not isinstance(source_players, list) or not isinstance(alias_players, list):
        raise PromotionFactoryError("display alias packages have no player lists")
    if len(source_players) != len(alias_players):
        raise PromotionFactoryError("display alias package changed player cardinality")

    observed_changes: list[dict[str, Any]] = []
    for source_player, alias_player in zip(source_players, alias_players):
        if not isinstance(source_player, Mapping) or not isinstance(alias_player, Mapping):
            raise PromotionFactoryError("display alias package contains a malformed player")
        source_without_name = dict(source_player)
        alias_without_name = dict(alias_player)
        source_name = source_without_name.pop("name", None)
        alias_name = alias_without_name.pop("name", None)
        if source_without_name != alias_without_name:
            raise PromotionFactoryError("display alias package changed data other than player display names")
        if source_name != alias_name:
            observed_changes.append({
                "player_id": source_player.get("id"),
                "person_id": source_player.get("person_id"),
                "carrier_id": source_player.get("carrier_id"),
                "source_name": source_player.get("source_name", source_name),
                "previous_display_name": source_name,
                "display_name": alias_name,
            })

    declared_changes = alias_audit.get("changed_players")
    if not isinstance(declared_changes, list) or not declared_changes:
        raise PromotionFactoryError("display alias audit must record one or more changed players")
    expected_changes = [
        {
            key: row.get(key)
            for key in (
                "player_id", "person_id", "carrier_id", "source_name",
                "previous_display_name", "display_name",
            )
        }
        for row in declared_changes
        if isinstance(row, Mapping)
    ]
    if len(expected_changes) != len(declared_changes) or expected_changes != observed_changes:
        raise PromotionFactoryError("display alias audit does not exactly describe package name changes")
    coverage = alias_audit.get("coverage")
    if isinstance(coverage, Mapping) and coverage.get("changed_display_name_count") != len(observed_changes):
        raise PromotionFactoryError("display alias audit change count is inconsistent")
    return {
        "source_package_sha256": source_package_sha256,
        "alias_package_sha256": alias_package_sha256,
        "changed_display_name_count": len(observed_changes),
    }


def _mode1_roster_binding(
    *, source_package: Mapping[str, Any], source_package_sha256: str,
    roster_package: Mapping[str, Any], roster_package_sha256: str,
    roster_audit: Mapping[str, Any], base: Mapping[str, Any],
    base_descriptor_sha256: str,
) -> dict[str, Any]:
    """Verify one exact whole-row mode-1 preservation derivative.

    Unlike a display alias, a fixed-row repair changes player, portrait, and
    roster lists.  It is admitted only when its own parser-backed receipt
    describes every such change exactly.  This remains a static ingress
    contract, never a release or a substitute for later compiler/runtime
    evidence.
    """

    if roster_audit.get("schema_version") != MODE1_ROSTER_RECONCILIATION_SCHEMA:
        raise PromotionFactoryError("mode-1 roster audit has an unsupported schema")
    if roster_audit.get("state") != MODE1_ROSTER_RECONCILIATION_STATE:
        raise PromotionFactoryError("mode-1 roster audit does not declare a static-only candidate")
    if roster_audit.get("release_eligible") is not False:
        raise PromotionFactoryError("mode-1 roster audit must explicitly remain release-ineligible")
    if source_package.get("season") != roster_package.get("season"):
        raise PromotionFactoryError("mode-1 roster package changed the season")
    if source_package.get("calendar") != roster_package.get("calendar"):
        raise PromotionFactoryError("mode-1 roster package changed the calendar contract")

    inputs = roster_audit.get("input")
    output = roster_audit.get("output")
    reconciliation = roster_audit.get("reconciliation")
    if not isinstance(inputs, Mapping) or not isinstance(output, Mapping) or not isinstance(reconciliation, Mapping):
        raise PromotionFactoryError("mode-1 roster audit lacks input, output, or reconciliation bindings")
    if inputs.get("package_sha256") != source_package_sha256:
        raise PromotionFactoryError("mode-1 roster audit does not bind the source package")
    if output.get("package_sha256") != roster_package_sha256:
        raise PromotionFactoryError("mode-1 roster audit does not bind the reconciled package")
    if inputs.get("verified_base_sha256") != base_descriptor_sha256:
        raise PromotionFactoryError("mode-1 roster audit targets a different verified base descriptor")
    inventory = base["inventory"]
    if inputs.get("base_inventory_fingerprint") != inventory["files_fingerprint"]:
        raise PromotionFactoryError("mode-1 roster audit targets a different verified base inventory")
    for relative_path, input_key in (
        ("DBDAT/EQ98030.FDI", "base_eq98030_sha256"),
        ("DBDAT/JUG98030.FDI", "base_jug98030_sha256"),
    ):
        expected = _inventory_file_sha256(base, relative_path)
        if expected is not None and inputs.get(input_key) != expected:
            raise PromotionFactoryError(
                f"mode-1 roster audit targets a different verified base {relative_path}"
            )

    try:
        club_carrier = int(reconciliation["club_carrier_id"])
        input_carriers = [int(value) for value in reconciliation["input_roster_player_carrier_ids"]]
        output_carriers = [int(value) for value in reconciliation["output_roster_player_carrier_ids"]]
        base_carriers = [int(value) for value in reconciliation["base_roster_player_carrier_ids"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise PromotionFactoryError("mode-1 roster audit has invalid roster carrier bindings") from exc
    if base_carriers != output_carriers or len(base_carriers) != len(set(base_carriers)):
        raise PromotionFactoryError("mode-1 roster audit does not restore one exact base roster order")
    if len(input_carriers) >= len(output_carriers) or input_carriers != [
        carrier for carrier in output_carriers if carrier in input_carriers
    ]:
        raise PromotionFactoryError("mode-1 roster audit input is not an ordered base-roster subsequence")
    restored_rows = reconciliation.get("restored_players")
    if not isinstance(restored_rows, list) or not restored_rows:
        raise PromotionFactoryError("mode-1 roster audit must record restored players")

    source_clubs = {int(row["carrier_id"]): row for row in source_package.get("clubs", []) if isinstance(row, Mapping)}
    roster_clubs = {int(row["carrier_id"]): row for row in roster_package.get("clubs", []) if isinstance(row, Mapping)}
    if set(source_clubs) != set(roster_clubs) or club_carrier not in source_clubs:
        raise PromotionFactoryError("mode-1 roster package changed club membership")
    if reconciliation.get("club_id") != source_clubs[club_carrier].get("id"):
        raise PromotionFactoryError("mode-1 roster audit names a different club")
    for carrier, source_club in source_clubs.items():
        roster_club = roster_clubs[carrier]
        source_without_roster = dict(source_club)
        roster_without_roster = dict(roster_club)
        source_roster_ids = source_without_roster.pop("roster_player_ids", None)
        roster_roster_ids = roster_without_roster.pop("roster_player_ids", None)
        if source_without_roster != roster_without_roster:
            raise PromotionFactoryError("mode-1 roster package changed club data other than roster rows")
        if carrier != club_carrier and source_roster_ids != roster_roster_ids:
            raise PromotionFactoryError("mode-1 roster package changed an undeclared club roster")
        if carrier == club_carrier:
            source_players = {str(row["id"]): row for row in source_package.get("players", []) if isinstance(row, Mapping)}
            roster_players = {str(row["id"]): row for row in roster_package.get("players", []) if isinstance(row, Mapping)}
            try:
                observed_input = [int(source_players[str(player_id)]["carrier_id"]) for player_id in source_roster_ids]
                observed_output = [int(roster_players[str(player_id)]["carrier_id"]) for player_id in roster_roster_ids]
            except (KeyError, TypeError, ValueError) as exc:
                raise PromotionFactoryError("mode-1 roster package has an unbound player roster row") from exc
            if observed_input != input_carriers or observed_output != output_carriers:
                raise PromotionFactoryError("mode-1 roster audit does not exactly describe the club roster change")

    source_players = {str(row["id"]): row for row in source_package.get("players", []) if isinstance(row, Mapping)}
    roster_players = {str(row["id"]): row for row in roster_package.get("players", []) if isinstance(row, Mapping)}
    if len(source_players) != len(source_package.get("players", [])) or len(roster_players) != len(roster_package.get("players", [])):
        raise PromotionFactoryError("mode-1 roster package has duplicate or malformed player IDs")
    if any(roster_players.get(player_id) != player for player_id, player in source_players.items()):
        raise PromotionFactoryError("mode-1 roster package changed an existing player declaration")

    restored_by_id: dict[str, Mapping[str, Any]] = {}
    for row in restored_rows:
        if not isinstance(row, Mapping):
            raise PromotionFactoryError("mode-1 roster audit has a malformed restored-player row")
        player_id = row.get("player_id")
        carrier = row.get("carrier_id")
        if not isinstance(player_id, str) or not isinstance(carrier, int) or player_id in restored_by_id:
            raise PromotionFactoryError("mode-1 roster audit has invalid restored-player identities")
        restored_by_id[player_id] = row
    if set(roster_players) - set(source_players) != set(restored_by_id):
        raise PromotionFactoryError("mode-1 roster package adds undeclared player rows")
    for player_id, audit_row in restored_by_id.items():
        player = roster_players[player_id]
        if (
            player.get("id") != player_id
            or player.get("carrier_id") != audit_row.get("carrier_id")
            or player.get("person_id") != audit_row.get("person_id")
            or player.get("name") != audit_row.get("name")
            or player.get("club_id") != reconciliation.get("club_id")
            or player.get("policy") != "preserve-existing-mode1"
            or audit_row.get("whole_record_policy") != "preserve-existing-mode1"
            or not isinstance(audit_row.get("payload_sha256"), str)
            or package_v2.SHA256_RE.fullmatch(audit_row["payload_sha256"]) is None
        ):
            raise PromotionFactoryError("mode-1 roster audit does not exactly describe a preserved player")

    source_assets = source_package.get("assets")
    roster_assets = roster_package.get("assets")
    if not isinstance(source_assets, Mapping) or not isinstance(roster_assets, Mapping):
        raise PromotionFactoryError("mode-1 roster packages have malformed assets")
    source_without_portraits = dict(source_assets)
    roster_without_portraits = dict(roster_assets)
    source_portraits = source_without_portraits.pop("portraits", None)
    roster_portraits = roster_without_portraits.pop("portraits", None)
    if source_without_portraits != roster_without_portraits or not isinstance(source_portraits, list) or not isinstance(roster_portraits, list):
        raise PromotionFactoryError("mode-1 roster package changed non-portrait assets")
    source_portraits_by_id = {
        str(row.get("player_id")): row for row in source_portraits if isinstance(row, Mapping)
    }
    roster_portraits_by_id = {
        str(row.get("player_id")): row for row in roster_portraits if isinstance(row, Mapping)
    }
    if len(source_portraits_by_id) != len(source_portraits) or len(roster_portraits_by_id) != len(roster_portraits):
        raise PromotionFactoryError("mode-1 roster package has duplicate or malformed portrait declarations")
    if any(roster_portraits_by_id.get(player_id) != portrait for player_id, portrait in source_portraits_by_id.items()):
        raise PromotionFactoryError("mode-1 roster package changed an existing portrait declaration")
    if set(roster_portraits_by_id) - set(source_portraits_by_id) != set(restored_by_id):
        raise PromotionFactoryError("mode-1 roster package adds undeclared portrait rows")
    for player_id in restored_by_id:
        portrait = roster_portraits_by_id[player_id]
        proof = portrait.get("proof")
        if portrait.get("status") != "unresolved" or not isinstance(proof, Mapping) or proof.get("grade") != "static-contract":
            raise PromotionFactoryError("mode-1 roster package has an invalid preserved-player portrait declaration")

    return {
        "source_package_sha256": source_package_sha256,
        "roster_package_sha256": roster_package_sha256,
        "mode1_roster_reconciliation_audit_sha256": _sha256_bytes(_bytes(dict(roster_audit))),
        "restored_club_carrier_id": club_carrier,
        "restored_player_count": len(restored_by_id),
    }


def _build_plan_candidate(
    *, package: Mapping[str, Any], effective_package_sha256: str,
    effective_package_size: int, base: Mapping[str, Any], workspace_sha256: str,
) -> dict[str, Any]:
    """Describe the exact upgrade path without faking an executable V2 plan.

    ``pm99-season-build-plan-v2`` contains expected *output* inventories.  It
    is therefore invalid to manufacture one before a clean compiler run has
    generated and audited those inventories.  This explicit non-executable
    object keeps that dependency visible rather than papering over it.
    """
    inventory = base["inventory"]
    return {
        "schema_version": BUILD_PLAN_CANDIDATE_SCHEMA,
        "target_build_plan_schema": "pm99-season-build-plan-v2",
        "season": _season_id(package),
        "state": "blocked-before-binary-compile",
        "workspace": {
            "relative_path": "workspace.json",
            "sha256": workspace_sha256,
        },
        "base": {
            "base_id": base["base_id"],
            "inventory_fingerprint": inventory["files_fingerprint"],
        },
        "effective_package": {
            "relative_path": "prepared/season-package.effective.json",
            "sha256": effective_package_sha256,
            "size": effective_package_size,
            "schema": package["schema_version"],
        },
        "proposed_binary_compile": {
            "entrypoint": "scripts/season_workspace_v1.py",
            "command": "compile",
            "required_arguments": [
                "--workspace", "workspace.json", "--base-tree", "<verified-clean-base-tree>",
                "--materialisation-tree", "<new-disposable-game-tree>", "--output-dir", "<new-build-output-dir>",
                "--copy-base",
            ],
            "implementation_sha256": _sha256_file(ROOT / "scripts" / "season_workspace_v1.py"),
        },
        "blocking_requirements": [
            "clean binary compiler receipt for this exact effective package",
            "two independently materialised output inventories with matching fingerprints",
            "reviewed pm99-season-build-plan-v2 with those locked output inventories",
            "PM99 runtime validation receipt",
            "target-season Stoke City lineup screenshot",
        ],
        "release_eligible": False,
        "runtime_validation_pending": True,
        "screenshot_evidence_pending": True,
    }


def _write_candidate(
    *, package: Mapping[str, Any], package_sha256: str,
    source_package_sha256: str, calendar_audit_sha256: str,
    base_descriptor_sha256: str, calendar: Mapping[str, Any], base: Mapping[str, Any],
    output_dir: Path, alias_binding: Mapping[str, Any] | None = None,
    roster_bindings: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Materialise one already-verified candidate ingress route."""

    if output_dir.exists():
        raise PromotionFactoryError(f"refusing to replace an existing output directory: {output_dir}")
    season_id = _season_id(package)
    alias_bound = alias_binding is not None
    roster_bound = bool(roster_bindings)
    if roster_bound and not alias_bound:
        raise PromotionFactoryError("mode-1 roster binding requires a verified display-alias binding")

    # Validate the output route in a throwaway sibling first so a rejected
    # package does not leave a partial candidate directory behind.
    timeline = editorial_v1.seed_timeline_from_package(
        package,
        timeline_id=(
            f"world-{season_id}-alias-roster-bound-canonical-candidate-timeline"
            if roster_bound else (
                f"world-{season_id}-alias-bound-canonical-candidate-timeline"
                if alias_bound else f"world-{season_id}-canonical-candidate-timeline"
            )
        ),
    )
    output_dir.mkdir(parents=True)
    package_output = output_dir / "season-package.candidate.json"
    base_output = output_dir / "verified-base.json"
    timeline_output = output_dir / "editorial-timeline.json"
    package_v2.write_canonical_package(package_output, copy.deepcopy(package))
    if _sha256_file(package_output) != package_sha256:
        raise PromotionFactoryError("candidate package did not remain byte-identical to the calendar-bound input")
    base_sha256 = _write(base_output, base)
    timeline_sha256 = _write(timeline_output, timeline)
    workspace = _workspace(
        package=package, package_sha256=package_sha256, base_sha256=base_sha256,
        timeline_sha256=timeline_sha256, alias_bound=alias_bound, roster_bound=roster_bound,
    )
    workspace_output = output_dir / "workspace.json"
    workspace_sha256 = _write(workspace_output, workspace)
    # The call verifies the copied input hashes, V2 package, base descriptor,
    # and complete editorial identity map; it is deliberately before prepare.
    workspace_v1.validate_workspace(workspace, workspace_path=workspace_output)
    prepared = workspace_v1.prepare_workspace(
        workspace_path=workspace_output, output_dir=output_dir / "prepared"
    )
    effective_path = Path(prepared["outputs"]["effective_package"])
    effective_package = package_v2.read_canonical_package(effective_path)
    package_v2.validate_package(effective_package, strict=True)
    build_plan = _build_plan_candidate(
        package=effective_package,
        effective_package_sha256=_sha256_file(effective_path),
        effective_package_size=effective_path.stat().st_size,
        base=base,
        workspace_sha256=workspace_sha256,
    )
    plan_output = output_dir / "build-plan.candidate.json"
    plan_sha256 = _write(plan_output, build_plan)
    input_bindings: dict[str, Any] = {
        "calendar_bound_package_sha256": source_package_sha256,
        "calendar_binding_audit_sha256": calendar_audit_sha256,
        "verified_base_descriptor_sha256": base_descriptor_sha256,
    }
    static_contracts = {
        "season_package_v2_strict": "passed",
        "calendar_binding": "passed",
        "verified_base_descriptor": "passed",
        "workspace_contract": "passed",
        "workspace_prepare": "passed",
    }
    if alias_binding is not None:
        input_bindings["display_alias_binding"] = dict(alias_binding)
        static_contracts["display_alias_binding"] = "passed"
    if len(roster_bindings) == 1:
        # Retain the original single-repair wire format so its existing
        # candidates remain byte-for-byte interpretable by operations tools.
        input_bindings["mode1_roster_reconciliation_binding"] = dict(roster_bindings[0])
        static_contracts["mode1_roster_reconciliation_binding"] = "passed"
    elif roster_bindings:
        input_bindings["mode1_roster_reconciliation_bindings"] = [
            dict(binding) for binding in roster_bindings
        ]
        static_contracts["mode1_roster_reconciliation_bindings"] = "passed"
    result = {
        "schema_version": SCHEMA,
        "season": season_id,
        "state": "canonical-workspace-candidate-only",
        "input": input_bindings,
        "calendar": dict(calendar),
        "outputs": {
            "package": {"relative_path": package_output.name, "sha256": package_sha256},
            "workspace": {"relative_path": workspace_output.name, "sha256": workspace_sha256},
            "timeline": {"relative_path": timeline_output.name, "sha256": timeline_sha256},
            "prepared_effective_package": {
                "relative_path": "prepared/season-package.effective.json",
                "sha256": _sha256_file(effective_path),
            },
            "build_plan_candidate": {"relative_path": plan_output.name, "sha256": plan_sha256},
        },
        "static_contracts": static_contracts,
        "not_performed": [
            "binary compiler materialisation",
            "v2 build plan generation",
            "release manifest generation",
            "PM99 runtime validation",
            "Stoke City lineup screenshot capture",
        ],
        "release_eligible": False,
        "runtime_validation_pending": True,
        "screenshot_evidence_pending": True,
    }
    _write(output_dir / "promotion-audit.json", result)
    return result


def create_candidate(
    *, package_path: Path, calendar_audit_path: Path, base_descriptor_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Write a candidate directly from one strict, calendar-bound package."""

    package = package_v2.read_canonical_package(package_path)
    package_v2.validate_package(package, strict=True)
    package_sha256 = _sha256_file(package_path)
    audit_input, audit_bytes = _read_json(calendar_audit_path, label="calendar audit")
    calendar = _calendar_binding(
        package=package, package_sha256=package_sha256, calendar_audit=audit_input
    )
    base_input, _ = _read_json(base_descriptor_path, label="verified base descriptor")
    base = pipeline_v2.validate_verified_base_descriptor(base_input)
    return _write_candidate(
        package=package, package_sha256=package_sha256,
        source_package_sha256=package_sha256,
        calendar_audit_sha256=_sha256_bytes(audit_bytes),
        base_descriptor_sha256=_sha256_file(base_descriptor_path),
        calendar=calendar, base=base, output_dir=output_dir,
    )


def create_alias_bound_candidate(
    *, source_package_path: Path, alias_package_path: Path, alias_audit_path: Path,
    calendar_audit_path: Path, base_descriptor_path: Path, output_dir: Path,
) -> dict[str, Any]:
    """Write a candidate from a verified parser-safe display-name derivative.

    The source package remains the calendar-bound ingress artefact.  The
    alias package must be completely described by its own exact, static-only
    receipt before it may enter the workspace lane.
    """

    source_package = package_v2.read_canonical_package(source_package_path)
    alias_package = package_v2.read_canonical_package(alias_package_path)
    package_v2.validate_package(source_package, strict=True)
    package_v2.validate_package(alias_package, strict=True)
    source_package_sha256 = _sha256_file(source_package_path)
    alias_package_sha256 = _sha256_file(alias_package_path)
    calendar_audit, calendar_audit_bytes = _read_json(calendar_audit_path, label="calendar audit")
    calendar = _calendar_binding(
        package=source_package, package_sha256=source_package_sha256,
        calendar_audit=calendar_audit,
    )
    base_input, _ = _read_json(base_descriptor_path, label="verified base descriptor")
    base = pipeline_v2.validate_verified_base_descriptor(base_input)
    alias_audit, alias_audit_bytes = _read_json(alias_audit_path, label="display alias audit")
    binding = _alias_binding(
        source_package=source_package, source_package_sha256=source_package_sha256,
        alias_package=alias_package, alias_package_sha256=alias_package_sha256,
        alias_audit=alias_audit, base=base,
    )
    binding["display_alias_audit_sha256"] = _sha256_bytes(alias_audit_bytes)
    return _write_candidate(
        package=alias_package, package_sha256=alias_package_sha256,
        source_package_sha256=source_package_sha256,
        calendar_audit_sha256=_sha256_bytes(calendar_audit_bytes),
        base_descriptor_sha256=_sha256_file(base_descriptor_path),
        calendar=calendar, base=base, output_dir=output_dir, alias_binding=binding,
    )


def create_alias_roster_bound_candidate(
    *, source_package_path: Path, alias_package_path: Path, alias_audit_path: Path,
    roster_package_path: Path, roster_audit_path: Path, calendar_audit_path: Path,
    base_descriptor_path: Path, output_dir: Path,
) -> dict[str, Any]:
    """Write a candidate from an alias-bound, whole-row-preservation repair."""

    return create_alias_roster_chain_bound_candidate(
        source_package_path=source_package_path,
        alias_package_path=alias_package_path,
        alias_audit_path=alias_audit_path,
        roster_package_paths=[roster_package_path],
        roster_audit_paths=[roster_audit_path],
        calendar_audit_path=calendar_audit_path,
        base_descriptor_path=base_descriptor_path,
        output_dir=output_dir,
    )


def create_alias_roster_chain_bound_candidate(
    *, source_package_path: Path, alias_package_path: Path, alias_audit_path: Path,
    roster_package_paths: Sequence[Path], roster_audit_paths: Sequence[Path],
    calendar_audit_path: Path, base_descriptor_path: Path, output_dir: Path,
) -> dict[str, Any]:
    """Write a candidate from an ordered chain of exact roster repairs.

    Each receipt is verified against the immediately preceding package.  This
    permits a later fixed-carrier repair without re-creating or weakening the
    already verified repair that preceded it.
    """

    if not roster_package_paths or len(roster_package_paths) != len(roster_audit_paths):
        raise PromotionFactoryError("mode-1 roster packages and audits must be non-empty ordered pairs")

    source_package = package_v2.read_canonical_package(source_package_path)
    alias_package = package_v2.read_canonical_package(alias_package_path)
    package_v2.validate_package(source_package, strict=True)
    package_v2.validate_package(alias_package, strict=True)
    source_package_sha256 = _sha256_file(source_package_path)
    alias_package_sha256 = _sha256_file(alias_package_path)
    calendar_audit, calendar_audit_bytes = _read_json(calendar_audit_path, label="calendar audit")
    calendar = _calendar_binding(
        package=source_package, package_sha256=source_package_sha256,
        calendar_audit=calendar_audit,
    )
    base_input, _ = _read_json(base_descriptor_path, label="verified base descriptor")
    base = pipeline_v2.validate_verified_base_descriptor(base_input)
    alias_audit, alias_audit_bytes = _read_json(alias_audit_path, label="display alias audit")
    alias_binding = _alias_binding(
        source_package=source_package, source_package_sha256=source_package_sha256,
        alias_package=alias_package, alias_package_sha256=alias_package_sha256,
        alias_audit=alias_audit, base=base,
    )
    alias_binding["display_alias_audit_sha256"] = _sha256_bytes(alias_audit_bytes)
    previous_package = alias_package
    previous_package_sha256 = alias_package_sha256
    roster_bindings: list[dict[str, Any]] = []
    restored_club_carriers: set[int] = set()
    for roster_package_path, roster_audit_path in zip(roster_package_paths, roster_audit_paths, strict=True):
        roster_package = package_v2.read_canonical_package(roster_package_path)
        package_v2.validate_package(roster_package, strict=True)
        roster_package_sha256 = _sha256_file(roster_package_path)
        roster_audit, _ = _read_json(roster_audit_path, label="mode-1 roster audit")
        roster_binding = _mode1_roster_binding(
            source_package=previous_package, source_package_sha256=previous_package_sha256,
            roster_package=roster_package, roster_package_sha256=roster_package_sha256,
            roster_audit=roster_audit, base=base,
            base_descriptor_sha256=_sha256_file(base_descriptor_path),
        )
        carrier = roster_binding["restored_club_carrier_id"]
        if carrier in restored_club_carriers:
            raise PromotionFactoryError("mode-1 roster chain repeats a restored club carrier")
        restored_club_carriers.add(carrier)
        roster_bindings.append(roster_binding)
        previous_package = roster_package
        previous_package_sha256 = roster_package_sha256
    return _write_candidate(
        package=previous_package, package_sha256=previous_package_sha256,
        source_package_sha256=source_package_sha256,
        calendar_audit_sha256=_sha256_bytes(calendar_audit_bytes),
        base_descriptor_sha256=_sha256_file(base_descriptor_path),
        calendar=calendar, base=base, output_dir=output_dir,
        alias_binding=alias_binding, roster_bindings=roster_bindings,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--calendar-audit", required=True, type=Path)
    parser.add_argument("--base-descriptor", required=True, type=Path)
    parser.add_argument(
        "--alias-package", type=Path,
        help="parser-safe display-name derivative of --package; requires --alias-audit",
    )
    parser.add_argument(
        "--alias-audit", type=Path,
        help="exact display-alias repair receipt for --alias-package",
    )
    parser.add_argument(
        "--roster-package", type=Path, action="append",
        help="ordered whole-row mode-1 preservation derivative of --alias-package; requires matching --roster-audit",
    )
    parser.add_argument(
        "--roster-audit", type=Path, action="append",
        help="ordered exact mode-1 roster reconciliation receipt for --roster-package",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    if (args.alias_package is None) != (args.alias_audit is None):
        parser.error("--alias-package and --alias-audit must be supplied together")
    if bool(args.roster_package) != bool(args.roster_audit):
        parser.error("--roster-package and --roster-audit must be supplied together")
    if args.roster_package is not None and len(args.roster_package) != len(args.roster_audit):
        parser.error("--roster-package and --roster-audit must have the same ordered count")
    if args.roster_package is not None and args.alias_package is None:
        parser.error("--roster-package requires --alias-package and --alias-audit")
    try:
        if args.roster_package is not None:
            result = create_alias_roster_chain_bound_candidate(
                source_package_path=args.package.resolve(),
                alias_package_path=args.alias_package.resolve(),
                alias_audit_path=args.alias_audit.resolve(),
                roster_package_paths=[path.resolve() for path in args.roster_package],
                roster_audit_paths=[path.resolve() for path in args.roster_audit],
                calendar_audit_path=args.calendar_audit.resolve(),
                base_descriptor_path=args.base_descriptor.resolve(), output_dir=args.output_dir.resolve(),
            )
        elif args.alias_package is None:
            result = create_candidate(
                package_path=args.package.resolve(), calendar_audit_path=args.calendar_audit.resolve(),
                base_descriptor_path=args.base_descriptor.resolve(), output_dir=args.output_dir.resolve(),
            )
        else:
            result = create_alias_bound_candidate(
                source_package_path=args.package.resolve(),
                alias_package_path=args.alias_package.resolve(),
                alias_audit_path=args.alias_audit.resolve(),
                calendar_audit_path=args.calendar_audit.resolve(),
                base_descriptor_path=args.base_descriptor.resolve(), output_dir=args.output_dir.resolve(),
            )
    except (OSError, PromotionFactoryError, package_v2.PackageValidationError,
            pipeline_v2.PipelineError, editorial_v1.TimelineError, workspace_v1.WorkspaceError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "season": result["season"], "state": result["state"],
        "static_contracts": result["static_contracts"],
        "release_eligible": result["release_eligible"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
