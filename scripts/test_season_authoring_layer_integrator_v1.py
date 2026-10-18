"""Tests for the generic authoring-layer join."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_authoring_layer_integrator_v1 as integrator  # noqa: E402
from scripts import season_intake_package_v1 as projector  # noqa: E402
from scripts.test_season_intake_package_v1 import _intake, _overlay  # noqa: E402


HASH = "b" * 64
SELECTOR = {"country_catalog": "eng", "competition_catalog": "prem", "club_name": "Example Town"}


def _draft() -> dict:
    intake = _intake()
    overlay = _overlay(intake)
    package, _receipt = projector.project_package(
        intake=intake, overlays=[(overlay, projector._sha256_document(overlay))]
    )
    positions = ["G", *("D" for _ in range(4)), *("M" for _ in range(4)), *("F" for _ in range(2))]
    for player, position in zip(package["players"], positions, strict=True):
        player["person_id"] = "person-source-" + hashlib_for(player["id"])
        player["facts"]["primary_position"] = position
    return package


def hashlib_for(value: str) -> str:
    import hashlib
    return hashlib.sha256(value.encode()).hexdigest()


def _allocation() -> dict:
    return {
        "schema_version": "pm99-season-carrier-allocation-v1",
        "assignments": [{
            "carrier_id": 600, "country_group": "england", "club_name": "Example Town",
            "method": "continuing-club-normalized-identity", "roster_capacity": 11,
            "source_selector": {**SELECTOR, "source_path": "eng/example.txt", "source_sha256": HASH},
        }],
    }


def _manager() -> dict:
    return {
        "schema_version": "pm99-opening-manager-ledger-v1", "season_start_year": 2000,
        "managers": [{"source_selector": SELECTOR, "opening_fixture_date": "2000-08-12",
                      "manager_name": "Historical Manager", "evidence": {"source_url": "https://example.test/report"}}],
        "gaps": [],
    }


def _opening() -> dict:
    positions = ["G", *("D" for _ in range(4)), *("M" for _ in range(4)), *("F" for _ in range(2))]
    return {
        "schema_version": "pm99-transfermarkt-opening-lineup-reconciliation-v1",
        "clubs": [{
            "source_selector": SELECTOR, "first_league_fixture_date": "2000-08-12",
            "formation": None, "starting_xi_reconciled": True,
            "starting_xi": [
                {"source_name": f"Player {number}", "source_position": position}
                for number, position in enumerate(positions, 1)
            ],
        }],
    }


def _kits() -> dict:
    return {
        "schema_version": "pm99-season-kit-catalogue-v1",
        "rows": [{"carrier_id": 600, "carrier_status": "continuing", "club_name": "Example Town",
                  "status": "source-ready", "render_contract": {"kind": "reviewed-pm99-style"}}],
    }


def _ratings(draft: dict) -> dict:
    values = {key: 60 for key in integrator.ratings_v1.RATING_FIELDS}
    return {
        "schema_version": "pm99-season-editorial-rating-output-v1",
        "player_ratings": [{
            "player_id": player["id"], "person_id": player["person_id"],
            "ratings": {"profile": "pm99-visible-skills-v1", "values": values,
                        "provenance": {"method": "deterministic editorial rating model v1", "source_ids": ["hierarchy"]}},
        } for player in draft["players"]],
    }


def _bindings(catalogue: dict) -> dict:
    return {
        "schema_version": integrator.KIT_BINDING_SCHEMA,
        "kit_catalogue_sha256": integrator._digest(catalogue),
        "clubs": [{"carrier_id": 600, "artifacts": [{"id": "kit-example-render", "kind": "kit-render", "sha256": HASH}]}],
    }


def test_integrates_complete_layers_and_infers_only_formation() -> None:
    draft = _draft()
    kits = _kits()
    package, audit = integrator.integrate(
        draft_package=draft, carrier_allocation=_allocation(), manager_ledger=_manager(),
        opening_reconciliation=_opening(), kit_catalogue=kits, rating_output=_ratings(draft),
        kit_render_bindings=_bindings(kits),
    )
    assert audit["release_eligible"] is True
    assert audit["coverage"]["formation-deterministic-position-inference"] == 1
    assert package["clubs"][0]["opening"]["formation"] == "4-4-2"
    assert package["managers"][0]["name"] == "Historical Manager"
    assert package["assets"]["kits"][0]["artifact_ids"] == ["kit-example-render"]
    assert all(row["status"] == "native-no-photo" for row in package["assets"]["portraits"])


def test_source_ready_kit_without_render_is_an_exact_blocker() -> None:
    draft = _draft()
    _package, audit = integrator.integrate(
        draft_package=draft, carrier_allocation=_allocation(), manager_ledger=_manager(),
        opening_reconciliation=_opening(), kit_catalogue=_kits(), rating_output=_ratings(draft),
    )
    assert audit["hard_blocker_counts"] == {"kit-render-artifact-required": 1}


def test_missing_manager_and_unreconciled_xi_are_not_native_fallbacks() -> None:
    draft = _draft()
    manager = copy.deepcopy(_manager())
    manager["managers"] = []
    opening = copy.deepcopy(_opening())
    opening["clubs"][0]["starting_xi_reconciled"] = False
    _package, audit = integrator.integrate(
        draft_package=draft, carrier_allocation=_allocation(), manager_ledger=manager,
        opening_reconciliation=opening, kit_catalogue=_kits(), rating_output=_ratings(draft),
    )
    assert audit["hard_blocker_counts"]["opening-manager-unresolved"] == 1
    assert audit["hard_blocker_counts"]["opening-xi-unresolved"] == 1


def test_rejects_stale_kit_render_binding() -> None:
    draft = _draft()
    bindings = _bindings(_kits())
    bindings["kit_catalogue_sha256"] = "0" * 64
    with pytest.raises(integrator.LayerIntegrationError, match="different kit catalogue"):
        integrator.integrate(
            draft_package=draft, carrier_allocation=_allocation(), manager_ledger=_manager(),
            opening_reconciliation=_opening(), kit_catalogue=_kits(), rating_output=_ratings(draft),
            kit_render_bindings=bindings,
        )
