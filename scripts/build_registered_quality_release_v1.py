#!/usr/bin/env python3
"""Build one cumulative, non-destructive quality release from registered inputs."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import apply_compiled_nationality_readback_repair_v1 as nationality  # noqa: E402
from scripts import compose_registered_quality_package_v1 as composition  # noqa: E402
from scripts import finalize_season_release_v1 as finalizer  # noqa: E402
from scripts import pm99_season_qa_v1 as qa  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_package_compiler_v2 as compiler  # noqa: E402
from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts import season_release_registry_v1 as registry  # noqa: E402
from scripts import season_disk_budget_v1 as disk_budget  # noqa: E402


DATABASE_FILES = ("DBDAT/JUG98030.FDI", "DBDAT/EQ98030.FDI", "DBDAT/ENT98030.FDI")
DEFAULT_RELEASE_ID = "rc-quality-20260913-r1"


class QualityBuildError(ValueError):
    """The cumulative quality release failed a required gate."""


def _write_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(path, value)


def _hardlink_clone(source: Path, target: Path) -> None:
    if target.exists() or target.is_symlink():
        raise QualityBuildError(f"refusing existing output game: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, copy_function=os.link)
    for relative in DATABASE_FILES:
        path = target / relative
        path.unlink()
        shutil.copyfile(finalizer.DEFAULT_BASE / relative, path)


def _recipe_artifact_matches(path, artifact):
    if registry.sha256_file(path) == artifact['sha256']:
        return True
    # These four older metadata descriptors hash canonical JSON content
    # without its disk newline. Respect that explicit historical convention,
    # requiring exact canonical on-disk bytes; new layers use raw file hashes.
    legacy = ('historical-role-plan-', 'historical-nationality-plan-',
              'historical-manager-plan-', 'historical-club-label-plan-')
    if not artifact['id'].startswith(legacy):
        return False
    try:
        value = json.loads(path.read_text())
        encoded = pipeline.canonical_json_bytes(value)
        return path.read_bytes() == encoded + b'\n' and hashlib.sha256(encoded).hexdigest() == artifact['sha256']
    except (ValueError, UnicodeError):
        return False


def _carry_recipe_local_artifacts(package, source_package_path, target_package_path):
    """Move immutable local inputs with the recipe, without guessing cache paths."""
    for artifact in package.get('artifacts', []):
        relative = artifact.get('relative_path')
        if not relative:
            continue
        rel = Path(relative)
        if rel.is_absolute() or '..' in rel.parts:
            raise QualityBuildError('unsafe recipe-local artifact path')
        source, target = source_package_path.parent / rel, target_package_path.parent / rel
        # Some legacy descriptors are external/declarative only. Preserve
        # existing behaviour for those; actual replay layers require files.
        if not source.is_file():
            continue
        if not _recipe_artifact_matches(source, artifact):
            raise QualityBuildError('recipe-local artifact source hash changed')
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not _recipe_artifact_matches(target, artifact):
                raise QualityBuildError('recipe-local artifact destination conflicts')
        else:
            os.link(source, target)


def _kit_receipt(season: str, *, source_release=None) -> Path:
    # An artwork-only update can supersede the V5 archive without changing
    # the database. Reuse its hash-bound complete receipt on later DB builds.
    release = source_release if source_release is not None else registry.load_preferred_release(season)
    if source_release is not None and release.season != season:
        raise QualityBuildError('kit receipt source belongs to another season')
    application_path = release.locator.get('kit_patch_application_path')
    if application_path:
        application = pipeline.read_json_file(ROOT / application_path)
        materialisation_path = application.get('materialisation_path')
        if materialisation_path:
            materialisation_path = Path(materialisation_path)
            if registry.sha256_file(materialisation_path) != application['materialisation_sha256']:
                raise QualityBuildError('kit materialisation receipt changed')
            materialisation = pipeline.read_json_file(materialisation_path)
            complete_path = materialisation.get('complete_kit_receipt_path')
            if complete_path:
                path = Path(complete_path)
                if registry.sha256_file(path) != materialisation['complete_kit_receipt_sha256']:
                    raise QualityBuildError('complete kit receipt changed')
                complete = pipeline.read_json_file(path)
                for name in ('MINIESC.PKF', 'NANOESC.PKF', 'RIDIESC.PKF'):
                    if registry.sha256_file(release.game_path / 'DBDAT' / name) != complete['archives'][name]['sha256_after']:
                        raise QualityBuildError(f'complete kit receipt is stale: {name}')
                return path
    path = ROOT / f".local/season-kit-runtime-overlays-v1/{season}/v5/receipt.json"
    if not path.is_file():
        raise QualityBuildError(f"missing V5 kit receipt: {path}")
    return path


def _reuse_completed(season: str, release_id: str) -> dict[str, Any] | None:
    """Return an already finalized candidate after rechecking immutable bytes."""
    path = registry.locator_path(season, release_id)
    if not path.is_file():
        return None
    locator = pipeline.read_json_file(path)
    if (
        locator.get("schema_version") != registry.LOCATOR_SCHEMA
        or locator.get("season") != season
        or locator.get("release_id") != release_id
    ):
        raise QualityBuildError(f"completed release has an invalid locator: {path}")
    game = (ROOT / str(locator.get("game_path"))).resolve()
    inventory_path = (ROOT / str(locator.get("inventory_path"))).resolve()
    manifest_path = (ROOT / str(locator.get("release_manifest_path"))).resolve()
    package_path = (ROOT / str(locator.get("package_path"))).resolve()
    for candidate in (game, inventory_path, manifest_path, package_path):
        if ROOT not in candidate.parents:
            raise QualityBuildError(f"completed release points outside the workspace: {candidate}")
    pipeline.assert_tree_matches_inventory(game, pipeline.read_json_file(inventory_path))
    if registry.canonical_document_sha256(package_path) != locator.get("package_canonical_sha256"):
        raise QualityBuildError(f"completed release package hash changed: {path}")
    required = locator.get("required_file_hashes")
    if not isinstance(required, dict):
        raise QualityBuildError(f"completed release has no required-file hashes: {path}")
    for relative in registry.REQUIRED_GAME_FILES:
        target = game / relative
        if not target.is_file() or registry.sha256_file(target) != required.get(relative):
            raise QualityBuildError(f"completed release required file changed: {target}")
    return {
        "season": season,
        "release_id": release_id,
        "release_manifest_sha256": registry.sha256_file(manifest_path),
        "reused": True,
    }


def _static_gates(package: dict[str, Any], game: Path, *, season: str) -> dict[str, Any]:
    recipe = qa.audit_recipe(package, season=season)
    managers = qa.audit_compiled_managers(package, game=game, season=season)
    handling = qa.audit_compiled_handling(package, game=game)
    nationalities = qa.audit_compiled_nationalities(package, game=game)
    counts = {
        "rating": recipe["rating_failure_count"],
        "date": recipe["date_failure_count"],
        "secondary_fact": recipe["secondary_fact_failure_count"],
        "lineup": recipe["lineup_failure_count"],
        "objective_profile": recipe["objective_input_failure_count"],
        "compiled_manager": managers["failure_count"],
        "compiled_handling": handling["failure_count"],
        "compiled_nationality": nationalities["failure_count"],
    }
    if any(counts.values()):
        raise QualityBuildError(f"static quality gates failed for {season}: {counts}")
    return {
        "schema_version": "pm99-cumulative-quality-static-gate-v1",
        "season": season,
        "result": "pass",
        "failure_counts": counts,
        "warnings": {
            "missing_secondary_facts": recipe["missing_secondary_fact_counts"],
            "unrepresentable_nationalities": nationalities["unrepresentable_nationality_count"],
            "rating_distribution": recipe["distribution_warning_count"],
        },
    }


def _build_manager_reconstruction(previous, *, release_id,
                                  minimum_free_bytes=disk_budget.DEFAULT_RESERVE):
    """Reapply an exact manager-only layer to its immutable known-good source.

    Extra recipe edits are refused, never discarded. Existing Italian lineup
    layers stay in the baseline recipe and every non-manager game file must
    remain identical. This is not a full factory compilation.
    """
    disk_budget.validate_reserve(minimum_free_bytes)
    from scripts import publish_historical_role_delta_v1 as publisher
    receipt_path = getattr(previous, 'compiler_receipt_path', None)
    if receipt_path is None:
        return None
    receipt = pipeline.read_json_file(receipt_path)
    mode = receipt.get('compilation_mode')
    if mode not in ('known-good-baseline-manager-name-delta', 'known-good-baseline-club-and-manager-name-delta'):
        return None
    folder = previous.package_path.parent
    descriptor_path = folder / 'role-delta-input.json'
    manager_sha = receipt.get('manager_plan_sha256')
    if not isinstance(manager_sha, str) or not re.fullmatch(r'[0-9a-f]{64}', manager_sha):
        raise QualityBuildError('manager reconstruction plan binding missing')
    candidates = [path for path in folder.glob('manager-update-*.json')
                  if re.fullmatch(r'manager-update-[0-9a-f]{64}\.json', path.name)
                  and registry.sha256_file(path) == manager_sha]
    if len(candidates) > 1:
        raise QualityBuildError('ambiguous manager reconstruction plan')
    manager_path = candidates[0] if candidates else folder / 'manager-plan.json'
    descriptor = pipeline.read_json_file(descriptor_path)
    manager_plan = pipeline.read_json_file(manager_path)
    club_path = None
    if mode == 'known-good-baseline-club-and-manager-name-delta':
        club_candidates = [p for p in folder.glob('club-update-*.json')
            if re.fullmatch(r'club-update-[0-9a-f]{64}\.json',p.name)
            and registry.sha256_file(p) == receipt.get('club_plan_sha256')]
        if len(club_candidates) > 1:
            raise QualityBuildError('ambiguous club-and-manager reconstruction plan')
        club_path = club_candidates[0] if club_candidates else folder/'club-plan.json'
    club_plan = pipeline.read_json_file(club_path) if club_path is not None else None
    if club_path is not None and registry.sha256_file(club_path) != receipt.get('club_plan_sha256'):
        raise QualityBuildError('club-and-manager reconstruction source plan changed')
    if club_path is not None and club_path.name.startswith('club-update-'):
        canonical_sha = hashlib.sha256(pipeline.canonical_json_bytes(club_plan)).hexdigest()
        if club_path.name != 'club-update-' + canonical_sha + '.json':
            raise QualityBuildError('club reconstruction canonical plan name changed')
    if candidates:
        canonical_sha = hashlib.sha256(pipeline.canonical_json_bytes(manager_plan)).hexdigest()
        if manager_path.name != 'manager-update-' + canonical_sha + '.json':
            raise QualityBuildError('manager reconstruction canonical plan name changed')
    if descriptor.get('updates') or descriptor.get('season') != previous.season:
        raise QualityBuildError('manager replay requires an inert source descriptor')
    baseline = registry.load_registered_release(previous.season, descriptor['release_id'])
    expected_descriptor = {'season': previous.season, 'release_id': baseline.release_id,
        'package_sha256': registry.sha256_file(baseline.package_path),
        'jug_sha256': registry.sha256_file(baseline.game_path / DATABASE_FILES[0]),
        'updates': [], 'unresolved': []}
    if descriptor != expected_descriptor:
        raise QualityBuildError('manager reconstruction source descriptor changed')
    if (receipt.get('manager_plan_sha256') != registry.sha256_file(manager_path)
            or receipt.get('source_season_package_sha256') != registry.canonical_document_sha256(baseline.package_path)
            or receipt.get('source_compiler_receipt_sha256') != registry.sha256_file(baseline.compiler_receipt_path)
            or receipt.get('source_build_chain_sha256') != registry.sha256_file(baseline.build_chain_path)):
        raise QualityBuildError('manager reconstruction provenance changed')
    expected = publisher.updated_package(pipeline.read_json_file(baseline.package_path), descriptor,
                                         manager_plan=manager_plan, club_plan=club_plan)
    package = pipeline.read_json_file(previous.package_path)
    if package_v2.canonical_json_bytes(expected) != package_v2.canonical_json_bytes(package):
        raise QualityBuildError('edited manager recipe cannot use exact reconstruction; no edits discarded')
    for release in (baseline, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season, descriptor_path, release_id=release_id,
                      register=False, manager_plan_path=manager_path,
                      club_plan_path=club_path,
                      source_release_id=baseline.release_id,
                      minimum_free_bytes=minimum_free_bytes)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if package_v2.canonical_json_bytes(pipeline.read_json_file(rebuilt.package_path)) != package_v2.canonical_json_bytes(package):
        raise QualityBuildError('manager reconstruction complete recipe differs')
    return {'season': previous.season, 'release_id': release_id,
            'previous_release_id': previous.release_id, 'source_release_id': baseline.release_id,
            'release_manifest_sha256': registry.sha256_file(rebuilt.release_manifest_path),
            'compilation_mode': ('source-bound-club-and-manager-reconstruction-not-factory-compile'
                if club_path is not None else 'source-bound-manager-only-reconstruction-not-factory-compile'),
            'complete_game_inventory_identical': True, 'complete_recipe_identical': True,
            'minimum_free_bytes': minimum_free_bytes, 'reused': False}


def _build_italian_reconstruction(previous, *, release_id):
    """Normal build support for exact source-bound known-good reconstruction.

This is not a full factory compile and does not bypass its historical duplicate
gate. An edited recipe requires another supported edit/delta path; refusing it
is safer than discarding that edit or silently regenerating unrelated people.
"""
    from scripts import season_italian_opening_layer_v1 as italian
    from scripts import publish_historical_role_delta_v1 as publisher
    package = pipeline.read_json_file(previous.package_path)
    if not any(a['id'].startswith(italian.PREFIX) for a in package['artifacts']):
        return None
    plans = italian.layers(package, previous.package_path)
    if len(plans) != 1:
        raise QualityBuildError('known-good Italian reconstruction requires exactly one explicit layer')
    plan = plans[0]
    baseline = registry.load_registered_release(previous.season, plan['source_release_id'])
    expected = italian.bind(pipeline.read_json_file(baseline.package_path), plan)
    if package_v2.canonical_json_bytes(package) != package_v2.canonical_json_bytes(expected):
        raise QualityBuildError('edited Italian recipe cannot use exact known-good reconstruction; no edits discarded')
    # Entire game, not merely the three database files, must still be bound.
    pipeline.assert_tree_matches_inventory(baseline.game_path, pipeline.read_json_file(baseline.inventory_path))
    pipeline.assert_tree_matches_inventory(previous.game_path, pipeline.read_json_file(previous.inventory_path))
    delta_input = previous.package_path.parent / 'role-delta-input.json'
    descriptor = {'season': previous.season, 'release_id': baseline.release_id,
                  'package_sha256': registry.sha256_file(baseline.package_path),
                  'jug_sha256': registry.sha256_file(baseline.game_path / DATABASE_FILES[0]),
                  'updates': [], 'unresolved': []}
    # The bounded publication already saved this exact inert descriptor.
    # Rebuilds never add or alter evidence in the immutable input workspace.
    if not delta_input.is_file() or pipeline.read_json_file(delta_input) != descriptor:
        raise QualityBuildError('Italian reconstruction descriptor missing or changed')
    plan_path = previous.package_path.parent / italian.FILENAME
    result = publisher.publish(previous.season, delta_input, release_id=release_id,
        register=False, italian_opening_plan_path=plan_path, source_release_id=baseline.release_id)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    expected_inventory = pipeline.read_json_file(previous.inventory_path)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, expected_inventory)
    return {'season': previous.season, 'release_id': release_id,
            'release_manifest_sha256': registry.sha256_file(rebuilt.release_manifest_path),
            'previous_release_id': previous.release_id,
            'compilation_mode': 'source-bound-known-good-reconstruction-not-factory-compile',
            'source_release_id': baseline.release_id,
            'complete_game_inventory_identical': True, 'reused': False}


def build(season: str, *, release_id: str, resume: bool = False) -> dict[str, Any]:
    season = pipeline.normalise_season_id(season)
    if resume:
        completed = _reuse_completed(season, release_id)
        if completed is not None:
            return completed
    previous = registry.load_preferred_release(season)
    from scripts import season_opening_cohort_delta_v1 as opening_cohort
    reconstructed = opening_cohort.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    # This current typed transaction includes its artwork; do not let an
    # inherited ancestor coach/artwork locator reconstruct an older recipe.
    from scripts import season_owned_club_composition_v1 as retained_composition
    reconstructed = retained_composition.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    # Artwork leaves the inherited compiler receipt untouched. Its exact
    # last-stage guard must run before older typed player/coach receipts;
    # otherwise a later icon-only fix is mistaken for its older shirt layer.
    from scripts import season_visual_patch_reconstruction_v1 as artwork
    reconstructed = artwork.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    # A complete-club transaction inherits older coach/player locators. Its
    # current typed receipt must be checked first; older whole-recipe guards
    # must not reject or reconstruct an ancestor in place of this newer layer.
    # The coupled reader returns None for every other current receipt mode.
    from scripts import season_paired_whole_club_reconstruction_v1 as coupled
    reconstructed = coupled.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    # Artwork above can deliberately inherit a compiler receipt. Only after
    # handling its last-stage guard may this direct keeper receipt supersede
    # inherited older roster/coach locators.
    from scripts import season_sourced_goalkeeper_roles_v1 as keeper_roles
    reconstructed = keeper_roles.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    # A newer coach-only layer retains the older player-layer locator. Select
    # the latest typed receipt before asking inherited player reconstructors
    # to compare their older whole recipe (which correctly rejects later edits).
    from scripts import season_opening_identity_exchange_v1 as opening_exchange
    from scripts import season_amavisca_retirement_xi_r194_v4 as amavisca_tx
    reconstructed = amavisca_tx.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    reconstructed = opening_exchange.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    reconstructed = _build_manager_reconstruction(previous, release_id=release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_source_bound_birthday_disagreements_v1 as birthday_disagreements
    reconstructed = birthday_disagreements.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_source_bound_maccabi_role_r129_v1 as maccabi_roles
    reconstructed = maccabi_roles.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_annual_position_role_candidate_v1 as annual_roles
    reconstructed = annual_roles.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_barrow_winger_fine_role_v1 as barrow_roles
    reconstructed = barrow_roles.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_horne_26979_facts_v1 as horne_facts
    reconstructed = horne_facts.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_rawle_forbes_standard_v1 as rawle_forbes
    reconstructed = rawle_forbes.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_evers_mcclune_opening_v1 as evers_mcclune
    reconstructed = evers_mcclune.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_ballymena_shevlin_reserve_v1 as shevlin_reserve
    reconstructed = shevlin_reserve.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_english_woolley_mcloughlin_v1 as english_reserves
    reconstructed = english_reserves.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_anelka_traore_lens_chain_v1 as anelka_chain
    reconstructed = anelka_chain.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_coady_centerback_cascade_v1 as coady_cascade
    reconstructed = coady_cascade.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_coady_centerback_exchange_v1 as coady_role
    reconstructed = coady_role.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_batth_wolves_opening_transfer_v1 as batth_wolves
    reconstructed = batth_wolves.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_shuker_city_reserve_move_v1 as shuker_move
    reconstructed = shuker_move.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_blackburn_ostenstad_etuhu_atomic_v1 as blackburn_city
    reconstructed = blackburn_city.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_altrincham_2001_role_overlay_v3 as alty_2001_roles
    reconstructed = alty_2001_roles.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_altrincham_2001_whole_club_v2 as alty_2001
    reconstructed = alty_2001.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_altrincham_macc_joint_exchange_v1 as alty_joint
    reconstructed = alty_joint.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_vokes_crouch_opening_exchange_v2 as vokes_crouch
    reconstructed = vokes_crouch.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_riera_postownership_country_role_v1 as riera_country_role
    reconstructed = riera_country_role.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_madrid_mode1_activation_v1 as madrid_activation
    reconstructed = madrid_activation.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    # Select the current typed opening transaction before inherited older
    # player-layer locators. The receipt guard leaves later coach edits intact.
    from scripts import season_original_alias_countries_v1 as alias_countries
    reconstructed = alias_countries.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_stoke_commons_number_v1 as commons_number
    reconstructed = commons_number.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_source_bound_shirt_numbers_v1 as shirt_numbers
    reconstructed = shirt_numbers.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_arsenal_2021_owned_opening_v1 as arsenal_owned
    reconstructed = arsenal_owned.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_morecambe_2000_owned_opening_v1 as morecambe_owned
    reconstructed = (morecambe_owned.reconstruction(previous, release_id)
                     if getattr(previous, 'compiler_receipt_path', None) is not None else None)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_takano_period_country_v1 as takano_country
    reconstructed = takano_country.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_preetz_period_profile_v1 as preetz_profile
    reconstructed = preetz_profile.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_haladas2000_opening_keeper_v1 as haladas_keeper
    reconstructed = haladas_keeper.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_kiraly_period_profile_v1 as kiraly_profile
    reconstructed = kiraly_profile.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_donor_keeper_role_delta_v1 as donor_roles
    reconstructed = donor_roles.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_original_country_policy_v2 as country_policy
    from scripts import season_source_verified_player_changes_v1 as source_changes
    reconstructed = source_changes.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_verified_owned_roster_transaction_v1 as owned_roster
    reconstructed = owned_roster.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_resolved_period_country_v3 as resolved_country
    reconstructed = resolved_country.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    reconstructed = country_policy.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_exact_primary_position_delta_v1 as primary_positions
    from scripts import season_exact_primary_position_delta_v2 as alias_primary_positions
    reconstructed = alias_primary_positions.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    reconstructed = primary_positions.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_cross_club_reserve_repair_v1 as cross_club
    from scripts import season_frozen_fixture_reserve_v2 as public_fixture
    reconstructed = public_fixture.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_frozen_fixture_reserve_v1 as frozen_fixture
    reconstructed = frozen_fixture.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_stoke_original_alias_reserve_v1 as original_alias
    from scripts import season_shtanyuk_2002_coupled_alias_v1 as coupled_alias
    reconstructed = coupled_alias.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    reconstructed = original_alias.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    reconstructed = cross_club.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_2015_english_fifa_roles_v1 as english_roles
    reconstructed = english_roles.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_exact_fifa_role_delta_v2 as conservative_roles
    reconstructed = conservative_roles.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_exact_fifa_role_delta_v1 as exact_roles
    reconstructed = exact_roles.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_quality_only_delta_v1 as quality_only
    reconstructed = quality_only.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_foreign_fixed_roster_delta_v1 as foreign
    reconstructed = foreign.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_number_label_names_v2 as number_labels
    reconstructed = number_labels.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_biographic_birth_years_v1 as biography
    from scripts import season_cross_period_birth_years_v1 as cross_period
    from scripts import season_original_person_birth_years_v1 as original_person
    reconstructed = original_person.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    reconstructed = cross_period.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    reconstructed = biography.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_profile_assignment_pruning_layer_v1 as assignments
    from scripts import season_inter_gimmelli_serena_exchange_v1 as gimmelli_serena
    reconstructed = gimmelli_serena.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    reconstructed = assignments.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    from scripts import season_maccabi_name_layer_v1 as names
    reconstructed = names.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    if season == "2015-16":
        raise QualityBuildError("2015-16 uses its separately verified manager-graph release path")
    from scripts import season_trabzon_opening_layer_v1 as trabzon
    reconstructed = trabzon.reconstruction(previous, release_id)
    if reconstructed is not None:
        return reconstructed
    reconstructed = _build_italian_reconstruction(previous, release_id=release_id)
    if reconstructed is not None:
        return reconstructed
    build_root = ROOT / ".local/season-release-builds-v1" / season / release_id
    game = ROOT / ".local/season-runtime-candidates-v1" / season / release_id / "game"
    if build_root.exists() or game.exists() or registry.locator_path(season, release_id).parent.exists():
        raise QualityBuildError(f"release ID already exists for {season}: {release_id}")
    build_root.mkdir(parents=True)
    package, composition_audit = composition.compose(season)
    package_path = build_root / "season-package.json"
    composition_path = build_root / "composition-audit.json"
    _write_new(package_path, package)
    _write_new(composition_path, composition_audit)
    _carry_recipe_local_artifacts(package, previous.package_path, package_path)

    _hardlink_clone(previous.game_path, game)
    receipt = compiler.compile_package_to_tree(
        package_path=package_path,
        base_tree=finalizer.DEFAULT_BASE,
        materialisation_tree=game,
    )
    compiler_path = build_root / "compiler-receipt.json"
    compiler.write_canonical_receipt(compiler_path, receipt)
    nationality_path = build_root / "nationality-transform-receipt.json"
    nationality.repair(
        package_path=package_path, runtime_game=game,
        receipt_path=nationality_path, apply=True,
    )
    gate = _static_gates(package, game, season=season)
    gate_path = build_root / "static-quality-gate.json"
    _write_new(gate_path, gate)

    # Prove the hard-link optimization did not mutate the prior immutable game.
    old_inventory = pipeline.read_json_file(previous.inventory_path)
    pipeline.assert_tree_matches_inventory(previous.game_path, old_inventory)
    result = finalizer.finalize(
        season=season,
        release_id=release_id,
        game=game,
        package=package_path,
        compiler_receipt=compiler_path,
        static_receipt=gate_path,
        kit_receipt=_kit_receipt(season),
        calendar_source=ROOT / f".local/calendar-v1/{season}/MANAGPRE.EXE",
        extra_receipts=[nationality_path],
        legacy_revision=previous.revision,
    )
    return {**result, "previous_release_id": previous.release_id, "quality_gate": registry.relative_workspace_path(gate_path)}


def register(results: list[dict[str, Any]]) -> None:
    catalog = registry.load_catalog()
    for result in results:
        catalog[result["season"]] = {
            "season": result["season"],
            "release_id": result["release_id"],
            "release_manifest_sha256": result["release_manifest_sha256"],
        }
    value = {"schema_version": registry.CATALOG_SCHEMA, "seasons": [catalog[key] for key in sorted(catalog)]}
    temporary = registry.CATALOG_PATH.with_suffix(".json.tmp")
    temporary.write_bytes(pipeline.canonical_json_bytes(value) + b"\n")
    os.replace(temporary, registry.CATALOG_PATH)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", help="YYYY-YY or all (2015-16 remains on its specialist release)")
    parser.add_argument("--release-id", default=DEFAULT_RELEASE_ID)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--register", action="store_true", help="switch the preferred catalogue only after every requested build passes")
    parser.add_argument("--resume", action="store_true", help="reuse completed hash-verified candidates and build only missing seasons")
    args = parser.parse_args(argv)
    seasons = [s for s in registry.supported_seasons() if s != "2015-16"] if args.season == "all" else [args.season]
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    results = []
    try:
        if args.jobs == 1 or len(seasons) == 1:
            for season in seasons:
                result = build(season, release_id=args.release_id, resume=args.resume)
                results.append(result)
                print(json.dumps(result, sort_keys=True), flush=True)
        else:
            with concurrent.futures.ProcessPoolExecutor(max_workers=min(args.jobs, len(seasons))) as pool:
                futures = {
                    pool.submit(build, season, release_id=args.release_id, resume=args.resume): season
                    for season in seasons
                }
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    results.append(result)
                    print(json.dumps(result, sort_keys=True), flush=True)
            results.sort(key=lambda row: str(row["season"]))
        if args.register:
            register(results)
    except (OSError, ValueError, pipeline.PipelineError, registry.RegistryError) as exc:
        print(f"quality release build error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"built": len(results), "registered": args.register, "seasons": [row["season"] for row in results]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
