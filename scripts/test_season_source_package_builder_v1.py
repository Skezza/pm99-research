"""Tests for the deterministic source-intake to package-draft bridge."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize('position, expected', [
    ('G', [0]), ('D', {'policy': 'preserve-existing-mode1'}),
    ('M', {'policy': 'preserve-existing-mode1'}),
    ('F', {'policy': 'preserve-existing-mode1'}),
    (None, {'policy': 'preserve-existing-mode1'}),
])
def test_literal_goalkeeper_derives_keeper_role_without_guessing_outfield_roles(position, expected):
    from scripts import season_source_package_builder_v1 as builder
    facts, _ = builder._updated_facts({'position': position}, 'original-source')
    assert facts['fine_roles'] == expected


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_source_package_builder_v1 as builder  # noqa: E402
from scripts import season_source_club_selection_v1 as selection_v1  # noqa: E402


HASH = "a" * 64


def test_non_contiguous_english_non_league_carriers_use_allocator_group() -> None:
    assert builder._carrier_group(377) == "english-non-league"
    assert builder._carrier_group(381) == "english-non-league"


def _template() -> dict:
    player = {
        "id": "player-one",
        "carrier_id": 10,
        "carrier_family": "dd6360",
        "club_id": "club-one",
        "name": "Native One",
        "person_id": "person-native-one",
        "facts": {},
        "ratings": {"sentinel": "must-not-change"},
        "proof": {},
    }
    player_two = copy.deepcopy(player)
    player_two.update({"id": "player-two", "carrier_id": 11, "name": "Native Two", "person_id": "person-native-two"})
    return {
        "schema_version": "pm99-season-package-v2",
        "package_id": "template-package",
        "season": {"start_year": 2015, "end_year": 2016, "label": "2015/16"},
        "scope": {},
        "artifacts": [],
        "sources": [],
        "clubs": [{
            "id": "club-one",
            "carrier_id": 1,
            "name": "Real Sociedad",
            "full_name": "Real Sociedad de Fútbol",
            "roster_player_ids": ["player-one", "player-two"],
            "proof": {},
        }],
        "players": [player, player_two],
        "managers": [],
        "assets": {"kits": [], "portraits": []},
        "calendar": {"target_year": 2015, "target_rollover_year": 2016},
        "proofs": [],
        "migration": {"known_gaps": []},
    }


def _registry() -> dict:
    return {
        "carriers": [{
            "carrier_id": 1,
            "baseline_club": {"name": "Real Sociedad", "full_name": "Real Sociedad de Fútbol"},
            "roster_slots": [],
        }],
    }


def _intake(*, catalog: str = "spain") -> dict:
    return {
        "schema_version": "pm99-season-source-intake-v1",
        "registry_sha256": builder._sha256_document(_registry()),
        "source_capture_sha256": HASH,
        "season": {"catalog": "2000-2001", "label": "2000/01"},
        "source": {"title": "FootballSquads fixture"},
        "source_clubs": [{
            "selector": {
                "country_catalog": catalog,
                "competition_catalog": "laliga",
                "club_name": "Réal Sociedad",
                "source_path": "spain/2000-2001/laliga/rsociedad.txt",
                "source_sha256": HASH,
            },
            "competition_name": "La Liga",
            "players": [
                {"facts": {"name": "First Source Player", "birth_date": "1978-01-02", "nationality": None, "position": "G", "height_cm": 188, "weight_kg": 80, "shirt_number": 1}},
                {"facts": {"name": "Second Source Player", "birth_date": "1979-02-03", "nationality": "ESP", "position": "D", "height_cm": 181, "weight_kg": 76, "shirt_number": 2}},
                {"facts": {"name": "Capacity Overflow", "birth_date": "1980-03-04", "nationality": "ESP", "position": "M", "height_cm": 175, "weight_kg": 70, "shirt_number": 3}},
            ],
        }],
    }


def _allocation(*, source_hash: str = HASH) -> dict:
    return {
        "schema_version": builder.carrier_allocation_v1.SCHEMA,
        "season": {"catalog": "2000-2001", "label": "2000/01"},
        "source_sha256": source_hash,
        "registry_sha256": builder._sha256_document(_registry()),
        "topology_policy": "fixed-country-family-preserve-continuing-then-canonical-replacement",
        "assignments": [{
            "carrier_id": 1,
            "country_group": "spain",
            "club_name": "Réal Sociedad",
            "source_selector": {
                "country_catalog": "spain",
                "competition_catalog": "laliga",
                "source_path": "spain/2000-2001/laliga/rsociedad.txt",
                "source_sha256": HASH,
            },
            "method": "same-country-replacement-canonical-source-order",
            "roster_capacity": 2,
        }],
        "gaps": [],
        "coverage": {},
    }


def _disable_full_validators(monkeypatch) -> None:
    monkeypatch.setattr(builder.package_v2, "validate_package", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(builder.registry_v2, "validate_registry", lambda *_args, **_kwargs: None)


def test_exact_group_match_allocates_source_order_and_preserves_ratings(monkeypatch) -> None:
    _disable_full_validators(monkeypatch)
    draft, audit = builder.build_draft(
        template=_template(), source_intake=_intake(), registry=_registry()
    )

    assert audit["coverage"]["exact_unique_club_match_count"] == 1
    assert audit["club_mappings"][0]["truncated_source_player_count"] == 1
    assert [row["name"] for row in draft["players"]] == ["First Source Player", "Second Source Player"]
    assert draft["players"][0]["ratings"] == {"sentinel": "must-not-change"}
    assert draft["players"][0]["facts"]["nationality"] == builder.PRESERVE
    assert draft["players"][0]["fact_fallbacks"][1]["field"] == "shirt_number"
    assert draft["players"][1]["facts"]["nationality"] == "ESP"
    assert audit["release_eligible"] is False


@pytest.mark.parametrize('explicit_allocation', [False, True])
def test_continuing_registry_identity_cannot_retain_unrelated_template_name(monkeypatch, explicit_allocation) -> None:
    _disable_full_validators(monkeypatch)
    template = _template()
    template['clubs'][0].update(name='Valencia', full_name='Valencia CF')
    allocation = _allocation() if explicit_allocation else None
    if allocation:
        allocation['assignments'][0]['method'] = 'continuing-club-normalized-identity'
    original = copy.deepcopy(template)
    draft, audit = builder.build_draft(template=template, source_intake=_intake(), registry=_registry(), carrier_allocation=allocation)
    assert draft['clubs'][0]['name'] == 'Réal Sociedad'
    assert draft['clubs'][0]['full_name'] == 'Réal Sociedad'
    assert draft['clubs'][0]['identity_id'] == builder._source_club_identity_id('spain', 'Réal Sociedad')
    assert draft['clubs'][0]['roster_player_ids'] == original['clubs'][0]['roster_player_ids']
    assert draft['players'][0]['ratings'] == original['players'][0]['ratings']
    assert audit['club_mappings'][0]['source_club_name'] == 'Réal Sociedad'
    assert template == original


def test_equivalent_continuing_display_spelling_is_not_unnecessarily_renamed(monkeypatch) -> None:
    _disable_full_validators(monkeypatch)
    draft, _ = builder.build_draft(template=_template(), source_intake=_intake(), registry=_registry())
    assert draft['clubs'][0]['name'] == 'Real Sociedad'
    assert draft['clubs'][0]['full_name'] == 'Real Sociedad de Fútbol'


def test_country_group_prevents_cross_country_name_match(monkeypatch) -> None:
    _disable_full_validators(monkeypatch)
    _draft, audit = builder.build_draft(
        template=_template(), source_intake=_intake(catalog="italy"), registry=_registry()
    )

    assert audit["coverage"]["exact_unique_club_match_count"] == 0
    assert audit["unresolved_source_clubs"][0]["candidate_carrier_ids"] == []


def test_build_is_byte_deterministic(monkeypatch) -> None:
    _disable_full_validators(monkeypatch)
    first = builder.build_draft(template=_template(), source_intake=_intake(), registry=_registry())
    second = builder.build_draft(template=_template(), source_intake=_intake(), registry=_registry())
    assert builder.package_v2.canonical_json_bytes(first[0]) == builder.package_v2.canonical_json_bytes(second[0])
    assert builder.package_v2.canonical_json_bytes(first[1]) == builder.package_v2.canonical_json_bytes(second[1])


def test_canonical_allocation_authorizes_same_country_replacement(monkeypatch) -> None:
    _disable_full_validators(monkeypatch)
    draft, audit = builder.build_draft(
        template=_template(),
        source_intake=_intake(),
        registry=_registry(),
        carrier_allocation=_allocation(),
    )
    assert audit["coverage"]["same_country_replacement_count"] == 1
    assert draft["clubs"][0]["name"] == "Réal Sociedad"
    assert draft["clubs"][0]["identity_id"].startswith("club-source-")
    assert draft["players"][0]["person_id"].startswith("person-source-")
    assert audit["carrier_allocation_sha256"] == builder._sha256_document(_allocation())


def test_refuses_stale_canonical_allocation(monkeypatch) -> None:
    _disable_full_validators(monkeypatch)
    with pytest.raises(builder.SourcePackageBuildError, match="different source capture"):
        builder.build_draft(
            template=_template(),
            source_intake=_intake(),
            registry=_registry(),
            carrier_allocation=_allocation(source_hash="b" * 64),
        )


def test_opening_preallocation_is_consumed_before_carrier_slots(monkeypatch) -> None:
    _disable_full_validators(monkeypatch)
    template = _template()
    prototype = copy.deepcopy(template["players"][0])
    template["players"] = []
    template["clubs"][0]["roster_player_ids"] = []
    for number in range(1, 12):
        player = copy.deepcopy(prototype)
        player.update({"id": f"player-{number}", "name": f"Native {number}", "person_id": f"native-{number}"})
        template["players"].append(player)
        template["clubs"][0]["roster_player_ids"].append(player["id"])
    intake = _intake()
    intake_players = []
    for number in range(1, 12):
        facts = {"name": f"Source {number}", "birth_date": f"1980-01-{number:02d}", "nationality": "ESP", "position": "M", "height_cm": 180, "weight_kg": 75, "shirt_number": number}
        intake_players.append({"source_row_index": number - 1, "source_row_sha256": f"{number:064x}", "facts": facts})
    intake["source_clubs"][0]["players"] = intake_players
    projected_players = []
    for order, player in enumerate(reversed(intake_players), 1):
        row = copy.deepcopy(player)
        row["opening_xi_order"] = order
        projected_players.append(row)
    preallocation = {
        "schema_version": builder.OPENING_PREALLOCATION_SCHEMA,
        "season": copy.deepcopy(intake["season"]),
        "sources": {
            "source_intake_sha256": builder._sha256_document(intake),
            "source_capture_sha256": intake["source_capture_sha256"],
        },
        "source_clubs": [{
            **copy.deepcopy(intake["source_clubs"][0]),
            "opening_xi_complete": True,
            "players": projected_players,
        }],
    }

    draft, audit = builder.build_draft(
        template=template, source_intake=intake, registry=_registry(),
        opening_squad_preallocation=preallocation,
    )

    assert [row["name"] for row in draft["players"]] == [f"Source {number}" for number in range(11, 0, -1)]
    assert audit["coverage"]["opening_xi_preallocated_club_count"] == 1
    assert audit["club_mappings"][0]["xi_capacity_satisfied"] is True
    assert audit["opening_squad_preallocation_sha256"] == builder._sha256_document(preallocation)


def test_cli_exposes_opening_preallocation_bridge() -> None:
    options = {action.dest for action in builder._parser()._actions}
    assert "opening_squad_preallocation" in options
    assert "calendar_binding_audit" in options


def _selection_bound_preallocation_inputs(*, registry: dict | None = None) -> tuple[dict, dict, dict]:
    """Build one raw/all-season to selected/August preallocation fixture."""

    intake = _intake()
    if registry is not None:
        intake["registry_sha256"] = builder._sha256_document(registry)
    for index, player in enumerate(intake["source_clubs"][0]["players"]):
        player["source_row_index"] = index
        player["source_row_sha256"] = f"{index + 1:064x}"
    selected_selector = {
        "country_catalog": "english-non-league",
        "competition_catalog": "soccerbase-august",
        "club_name": "Real Sociedad",
        "source_path": "soccerbase/rsociedad/august",
        "source_sha256": "b" * 64,
    }
    selected_players = []
    for index, player in enumerate(intake["source_clubs"][0]["players"]):
        row = copy.deepcopy(player)
        row["source_row_index"] = index
        row["source_row_sha256"] = f"{index + 101:064x}"
        row["facts"]["name"] = f"Selected Source Player {index + 1}"
        selected_players.append(row)
    intake["source_clubs"].append({
        "selector": selected_selector,
        "competition_name": "August squad",
        "players": selected_players,
    })
    manifest = {
        "schema_version": selection_v1.MANIFEST_SCHEMA,
        "selection_id": "world-2000-01-opening-source-selection",
        "season": copy.deepcopy(intake["season"]),
        "inputs": {
            "source_intake_sha256": selection_v1._sha256_document(intake),
            "source_capture_sha256": intake["source_capture_sha256"],
        },
        "selections": [{
            "id": "real-sociedad-opening-source",
            "canonical_selector": copy.deepcopy(intake["source_clubs"][0]["selector"]),
            "selected_selector": selected_selector,
            "basis": selection_v1.SELECTION_BASIS,
        }],
    }
    selection, _audit = selection_v1.build_selection(source_intake=intake, manifest=manifest)
    preallocation = {
        "schema_version": builder.OPENING_PREALLOCATION_SCHEMA,
        "season": copy.deepcopy(intake["season"]),
        "sources": {
            "source_intake_sha256": builder._sha256_document(intake),
            "source_capture_sha256": intake["source_capture_sha256"],
            "source_club_selection_sha256": builder._sha256_document(selection),
        },
        "source_clubs": [{
            **copy.deepcopy(row),
            "opening_xi_complete": False,
            "opening_xi_player_count": 0,
            "opening_xi_blockers": [],
            "opening_fixture_date": None,
            "opening_source_match_id": None,
        } for row in selection["effective_source_clubs"]],
        "gaps": [],
    }
    return intake, selection, preallocation


def test_selection_bound_opening_preallocation_is_consumed_and_rejects_stale_rows(monkeypatch) -> None:
    _disable_full_validators(monkeypatch)
    intake, selection, preallocation = _selection_bound_preallocation_inputs()
    draft, audit = builder.build_draft(
        template=_template(), source_intake=intake, registry=_registry(),
        carrier_allocation=_allocation(), source_club_selection=selection,
        opening_squad_preallocation=preallocation,
    )

    assert [row["name"] for row in draft["players"]] == [
        "Selected Source Player 1", "Selected Source Player 2",
    ]
    assert audit["source_club_selection_sha256"] == builder._sha256_document(selection)
    assert audit["opening_squad_preallocation_sha256"] == builder._sha256_document(preallocation)

    alias_allocation = _allocation()
    selected_selector = selection["manifest"]["selections"][0]["selected_selector"]
    alias_allocation["assignments"][0]["source_selector"] = {
        key: selected_selector[key]
        for key in ("country_catalog", "competition_catalog", "source_path", "source_sha256")
    }
    alias_allocation["assignments"][0]["club_name"] = selected_selector["club_name"]
    alias_draft, alias_audit = builder.build_draft(
        template=_template(), source_intake=intake, registry=_registry(),
        carrier_allocation=alias_allocation, source_club_selection=selection,
        opening_squad_preallocation=preallocation,
    )
    assert [row["name"] for row in alias_draft["players"]] == [
        "Selected Source Player 1", "Selected Source Player 2",
    ]
    assert alias_audit["coverage"]["source_club_selection_allocation_translation_count"] == 1
    assert alias_audit["source_club_selection_allocation_translations"][0]["selection_id"] == (
        "real-sociedad-opening-source"
    )

    legacy_preallocation = copy.deepcopy(preallocation)
    del legacy_preallocation["sources"]["source_club_selection_sha256"]
    with pytest.raises(builder.SourcePackageBuildError, match="different source-club selection"):
        builder.build_draft(
            template=_template(), source_intake=intake, registry=_registry(),
            carrier_allocation=_allocation(), source_club_selection=selection,
            opening_squad_preallocation=legacy_preallocation,
        )

    tampered_preallocation = copy.deepcopy(preallocation)
    tampered_preallocation["source_clubs"][0]["players"][0]["facts"]["name"] = "Unsourced edit"
    with pytest.raises(builder.SourcePackageBuildError, match="does not exactly match"):
        builder.build_draft(
            template=_template(), source_intake=intake, registry=_registry(),
            carrier_allocation=_allocation(), source_club_selection=selection,
            opening_squad_preallocation=tampered_preallocation,
        )


def test_selection_allocation_aliases_refuse_ambiguous_four_field_references() -> None:
    canonical_one = {
        "country_catalog": "eng", "competition_catalog": "national", "club_name": "Canonical One",
        "source_path": "eng/one", "source_sha256": "1" * 64,
    }
    canonical_two = {
        "country_catalog": "eng", "competition_catalog": "national", "club_name": "Canonical Two",
        "source_path": "eng/two", "source_sha256": "2" * 64,
    }
    shared_alias = {
        "country_catalog": "english-non-league", "competition_catalog": "soccerbase-august",
        "source_path": "soccerbase/shared", "source_sha256": "3" * 64,
    }
    selection = {"manifest": {"selections": [
        {
            "id": "one", "canonical_selector": canonical_one,
            "selected_selector": {**shared_alias, "club_name": "Alias One"},
        },
        {
            "id": "two", "canonical_selector": canonical_two,
            "selected_selector": {**shared_alias, "club_name": "Alias Two"},
        },
    ]}}
    with pytest.raises(builder.SourcePackageBuildError, match="aliases are ambiguous"):
        builder._selection_authorized_allocation_aliases(selection)


def test_selection_suppresses_alias_allocation_when_canonical_owner_exists(monkeypatch) -> None:
    _disable_full_validators(monkeypatch)
    template = _template()
    second_club = copy.deepcopy(template["clubs"][0])
    second_club.update({"id": "club-two", "carrier_id": 2, "roster_player_ids": ["player-three", "player-four"]})
    template["clubs"].append(second_club)
    for target_id, carrier_id in (("player-three", 12), ("player-four", 13)):
        player = copy.deepcopy(template["players"][0])
        player.update({
            "id": target_id,
            "carrier_id": carrier_id,
            "club_id": "club-two",
            "person_id": f"person-source-{carrier_id:064x}",
        })
        template["players"].append(player)
    registry = _registry()
    registry["carriers"].append({
        "carrier_id": 2,
        "baseline_club": {"name": "Native Two", "full_name": "Native Two"},
        "roster_slots": [],
    })
    intake, selection, preallocation = _selection_bound_preallocation_inputs(registry=registry)
    allocation = _allocation()
    allocation["registry_sha256"] = builder._sha256_document(registry)
    selected_selector = selection["manifest"]["selections"][0]["selected_selector"]
    allocation["assignments"].append({
        "carrier_id": 2,
        "country_group": "spain",
        "club_name": selected_selector["club_name"],
        "source_selector": {
            key: selected_selector[key]
            for key in ("country_catalog", "competition_catalog", "source_path", "source_sha256")
        },
        "method": "same-country-replacement-canonical-source-order",
        "roster_capacity": 2,
    })

    _draft, audit = builder.build_draft(
        template=template, source_intake=intake, registry=registry,
        carrier_allocation=allocation, source_club_selection=selection,
        opening_squad_preallocation=preallocation,
    )

    assert audit["coverage"]["source_club_selection_allocation_translation_count"] == 0
    assert audit["coverage"]["source_club_selection_allocation_suppression_count"] == 1
    assert audit["coverage"]["source_club_selection_suppressed_player_identity_quarantine_count"] == 2
    assert audit["source_club_selection_allocation_suppressions"][0]["carrier_id"] == 2
    assert all(row["provisional_person_id"].startswith("person-hold-") for row in (
        audit["source_club_selection_suppressed_player_identity_quarantines"]
    ))
    assert 2 in audit["unmatched_carrier_ids"]


def test_hash_bound_calendar_overlay_closes_only_calendar_receipt_gate(monkeypatch) -> None:
    validation_modes: list[bool] = []
    monkeypatch.setattr(
        builder.package_v2,
        "validate_package",
        lambda _value, *, strict: validation_modes.append(strict),
    )
    monkeypatch.setattr(builder.registry_v2, "validate_registry", lambda _value: None)
    template = _template()
    template["season"] = {"start_year": 2000, "end_year": 2001, "label": "2000/01"}
    calendar_artifact = {
        "id": "calendar-2000-01-receipt",
        "kind": "calendar-patch",
        "relative_path": ".local/calendar-v1/2000-01/calendar-receipt.json",
        "sha256": "c" * 64,
    }
    template["artifacts"].append(calendar_artifact)
    template["calendar"] = {
        "base_year": 1998,
        "target_year": 2000,
        "target_rollover_year": 2001,
        "patch_artifact_id": calendar_artifact["id"],
        "proof": {"grade": "static-contract", "artifact_id": calendar_artifact["id"]},
    }
    calendar_audit = {
        "schema_version": builder.CALENDAR_BINDING_AUDIT_SCHEMA,
        "season": copy.deepcopy(template["season"]),
        "receipt_sha256": calendar_artifact["sha256"],
        "executable_sha256": "d" * 64,
        "patch_count": 853,
        "output_package_sha256": builder._sha256_document(template),
        "runtime_validation_pending": True,
    }

    draft, audit = builder.build_draft(
        template=template,
        source_intake=_intake(),
        registry=_registry(),
        calendar_binding_audit=calendar_audit,
    )

    assert audit["coverage"]["calendar_binding_verified_count"] == 1
    assert audit["calendar_binding"]["receipt_sha256"] == "c" * 64
    assert draft["calendar"] == template["calendar"]
    assert validation_modes == [False, False]
    assert "target-season-calendar-receipt-required" not in {
        row["code"] for row in audit["hard_blockers"]
    }
    assert "target-season-managers-required" in {row["code"] for row in audit["hard_blockers"]}

    stale_audit = copy.deepcopy(calendar_audit)
    stale_audit["output_package_sha256"] = "e" * 64
    with pytest.raises(builder.SourcePackageBuildError, match="does not hash-bind"):
        builder.build_draft(
            template=template,
            source_intake=_intake(),
            registry=_registry(),
            calendar_binding_audit=stale_audit,
        )


def test_unbound_template_retains_strict_initial_validation(monkeypatch) -> None:
    validation_modes: list[bool] = []
    monkeypatch.setattr(
        builder.package_v2,
        "validate_package",
        lambda _value, *, strict: validation_modes.append(strict),
    )
    monkeypatch.setattr(builder.registry_v2, "validate_registry", lambda _value: None)

    builder.build_draft(template=_template(), source_intake=_intake(), registry=_registry())

    assert validation_modes == [True, False]


def test_exact_existing_source_person_slot_is_reserved_without_changing_source_capacity_order(monkeypatch) -> None:
    _disable_full_validators(monkeypatch)
    template = _template()
    intake = _intake()
    source_hashes = ["a" * 64, "b" * 64, "c" * 64]
    for player, source_hash in zip(intake["source_clubs"][0]["players"], source_hashes):
        player["source_row_sha256"] = source_hash
    # The prior provisional draft already puts source row two in slot one.
    # Reserving that exact hash-bound identity lets the replay update it there;
    # source row one still occupies the remaining slot.  This is not a name or
    # date match and does not select source row three beyond the fixed capacity.
    template["players"][0]["person_id"] = f"person-source-{source_hashes[1]}"

    draft, audit = builder.build_draft(
        template=template,
        source_intake=intake,
        registry=_registry(),
    )

    assert [row["name"] for row in draft["players"]] == [
        "Second Source Player", "First Source Player",
    ]
    assert audit["coverage"]["identity_retained_source_slot_count"] == 1
    assert audit["club_mappings"][0]["allocated_player_count"] == 2
    assert audit["club_mappings"][0]["truncated_source_player_count"] == 1


def test_unresolved_repeated_source_person_is_an_explicit_hard_blocker(monkeypatch) -> None:
    _disable_full_validators(monkeypatch)
    template = _template()
    second_club = copy.deepcopy(template["clubs"][0])
    second_club.update({"id": "club-two", "carrier_id": 2, "name": "Real Betis", "full_name": "Real Betis"})
    second_players = []
    for player in template["players"]:
        duplicate = copy.deepcopy(player)
        duplicate.update({
            "id": f'{player["id"]}-betis',
            "club_id": "club-two",
            "person_id": f'{player["person_id"]}-betis',
        })
        second_players.append(duplicate)
    second_club["roster_player_ids"] = [row["id"] for row in second_players]
    template["clubs"].append(second_club)
    template["players"].extend(second_players)

    registry = _registry()
    registry["carriers"].append({
        "carrier_id": 2,
        "baseline_club": {"name": "Real Betis", "full_name": "Real Betis"},
        "roster_slots": [],
    })
    intake = _intake()
    shared = "f" * 64
    intake["source_clubs"][0]["players"][0]["source_row_sha256"] = shared
    second_source_club = copy.deepcopy(intake["source_clubs"][0])
    second_source_club["selector"].update({"club_name": "Real Betis", "source_path": "spain/2000-2001/laliga/betis.txt"})
    second_source_club["players"][0]["source_row_sha256"] = shared
    intake["source_clubs"].append(second_source_club)
    intake["registry_sha256"] = builder._sha256_document(registry)

    _draft, audit = builder.build_draft(template=template, source_intake=intake, registry=registry)

    blocker = next(row for row in audit["hard_blockers"] if row["code"] == "repeated-source-person-identity-unresolved")
    assert blocker["count"] >= 1
    resolution = next(row for row in audit["repeated_source_row_resolutions"] if row["source_row_sha256"] == shared)
    assert resolution["resolution"] == "unresolved-repeated-person-claim-all-copies-excluded"


def test_unique_earliest_opening_fixture_claim_owns_duplicate_source_profile(monkeypatch) -> None:
    """A later dated squad cannot retain the same sourced opening player."""

    _disable_full_validators(monkeypatch)
    template = _template()
    prototype = copy.deepcopy(template["players"][0])
    second_club = copy.deepcopy(template["clubs"][0])
    second_club.update({"id": "club-two", "carrier_id": 2, "name": "Real Betis", "full_name": "Real Betis"})
    template["players"] = []
    template["clubs"][0]["roster_player_ids"] = []
    second_club["roster_player_ids"] = []
    for club, prefix in ((template["clubs"][0], "one"), (second_club, "two")):
        for number in range(1, 12):
            player = copy.deepcopy(prototype)
            player.update({
                "id": f"player-{prefix}-{number}", "club_id": club["id"],
                "name": f"Native {prefix} {number}", "person_id": f"native-{prefix}-{number}",
            })
            template["players"].append(player)
            club["roster_player_ids"].append(player["id"])
    template["clubs"].append(second_club)

    registry = _registry()
    registry["carriers"].append({
        "carrier_id": 2,
        "baseline_club": {"name": "Real Betis", "full_name": "Real Betis"},
        "roster_slots": [],
    })
    intake = _intake()
    second_source = copy.deepcopy(intake["source_clubs"][0])
    second_source["selector"].update({"club_name": "Real Betis", "source_path": "spain/2000-2001/laliga/betis.txt"})
    intake["source_clubs"].append(second_source)
    intake["registry_sha256"] = builder._sha256_document(registry)
    for club_index, source_club in enumerate(intake["source_clubs"], 1):
        players = []
        for number in range(1, 12):
            players.append({
                "source_row_index": number - 1,
                "source_row_sha256": f"{club_index * 100 + number:064x}",
                "facts": {
                    "name": f"Source {club_index} {number}", "birth_date": f"1980-01-{number:02d}",
                    "nationality": "ESP", "position": "M", "height_cm": 180,
                    "weight_kg": 75, "shirt_number": number,
                },
            })
        # Both dated first XIs assert the same published Transfermarkt person
        # ID for their first player.  The earlier claim is the only safe owner.
        players[0]["facts"]["name"] = "Shared Opening Player"
        source_club["players"] = players

    preallocation_clubs = []
    for club_index, source_club in enumerate(intake["source_clubs"], 1):
        players = copy.deepcopy(source_club["players"])
        for order, player in enumerate(players, 1):
            player["opening_xi_order"] = order
            player["opening_source_player_id"] = "shared-profile" if order == 1 else f"club-{club_index}-profile-{order}"
        preallocation_clubs.append({
            **copy.deepcopy(source_club),
            "opening_xi_complete": True,
            "opening_fixture_date": f"2000-08-0{club_index}",
            "players": players,
        })
    preallocation = {
        "schema_version": builder.OPENING_PREALLOCATION_SCHEMA,
        "season": copy.deepcopy(intake["season"]),
        "sources": {
            "source_intake_sha256": builder._sha256_document(intake),
            "source_capture_sha256": intake["source_capture_sha256"],
        },
        "source_clubs": preallocation_clubs,
    }
    allocation = _allocation()
    allocation["registry_sha256"] = builder._sha256_document(registry)
    allocation["assignments"].append({
        **copy.deepcopy(allocation["assignments"][0]),
        "carrier_id": 2,
        "club_name": "Real Betis",
        "source_selector": {
            **copy.deepcopy(second_source["selector"]),
        },
    })

    draft, audit = builder.build_draft(
        template=template, source_intake=intake, registry=registry,
        carrier_allocation=allocation, opening_squad_preallocation=preallocation,
    )

    assert audit["coverage"]["source_person_identity_conflict_count"] == 0
    assert audit["coverage"]["source_person_identity_unique_earliest_opening_fixture_resolution_count"] == 1
    resolution = next(
        row for row in audit["source_person_identity_resolutions"]
        if row["birth_date"] == "shared-profile"
    )
    assert resolution["winner_club"] == "Réal Sociedad"
    assert resolution["winner_opening_fixture_date"] == "2000-08-01"
    assert any(row["name"] == "Shared Opening Player" for row in draft["players"][:11])

    tied_preallocation = copy.deepcopy(preallocation)
    tied_preallocation["source_clubs"][1]["opening_fixture_date"] = "2000-08-01"
    _draft, tied_audit = builder.build_draft(
        template=template, source_intake=intake, registry=registry,
        carrier_allocation=allocation, opening_squad_preallocation=tied_preallocation,
    )
    assert tied_audit["coverage"]["source_person_identity_conflict_count"] == 1
    assert tied_audit["coverage"]["source_person_identity_unique_earliest_opening_fixture_resolution_count"] == 0


def test_label_postimage_rejects_duplicate_carrier_mapping():
    rows = [{"carrier_id": 1, "source_club_name": "Real Sociedad"}] * 2
    with pytest.raises(builder.SourcePackageBuildError, match="duplicate source-club label mapping"):
        builder._verify_source_club_label_postimage(rows, {1: {"name": "Real Sociedad"}})


def test_build_return_rejects_stale_label_after_mapping(monkeypatch):
    monkeypatch.setattr(builder.package_v2, "validate_package", lambda *_a, **_k: None)
    monkeypatch.setattr(builder.registry_v2, "validate_registry", lambda *_a, **_k: None)
    monkeypatch.setattr(builder, "_apply_source_club_label", lambda *args, **kwargs: None)
    template = _template()
    template["clubs"][0]["name"] = "Valencia"
    with pytest.raises(builder.SourcePackageBuildError, match="source-club label postimage mismatch"):
        builder.build_draft(template=template, source_intake=_intake(), registry=_registry(), template_prevalidated=True)


def test_label_postimage_accepts_spelling_alias_and_unmapped_club():
    builder._verify_source_club_label_postimage(
        [{"carrier_id": 1, "source_club_name": "Réal Sociedad"}],
        {1: {"name": "Real Sociedad"}, 2: {"name": "Unmapped Club"}},
    )


def test_label_postimage_rejects_missing_carrier():
    with pytest.raises(builder.SourcePackageBuildError, match="source-club label postimage mismatch"):
        builder._verify_source_club_label_postimage(
            [{"carrier_id": 1, "source_club_name": "Real Sociedad"}], {},
        )
