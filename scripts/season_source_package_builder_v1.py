#!/usr/bin/env python3
"""Build a deterministic Season Package V2 draft from a dated squad capture.

This is the deliberately mechanical bridge which was missing between the
all-carrier source intake and the existing package compiler.  It performs only
safe, repeatable operations:

* match a captured club to one fixed carrier when its Unicode-normalised name
  exactly equals one unique native/template club name;
* retain an exact, same-carrier source-person slot when a prior provisional
  draft already carries that hash-bound person, then allocate the remaining
  captured players in source/slot order, truncating only at the fixed capacity;
* resolve a duplicate source person only when one hash-bound, first-fixture
  claim is uniquely earlier than every competing opening-fixture claim; and
* write source facts which the foreign-player compiler understands, recording
  an explicit preserve-existing fallback for unavailable secondary facts.

It never guesses a club mapping, person identity, manager, kit, opening XI,
rating, or calendar artifact.  The output package is therefore called a
*draft*.  A separate canonical audit lists every hard release blocker.  The CLI
will only write ``--output-package`` when that list is empty; otherwise callers
may inspect ``--output-draft-package`` without mistaking it for a release.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_source_intake_v1 as source_intake_v1  # noqa: E402
from scripts import season_source_club_selection_v1 as source_club_selection_v1  # noqa: E402
from scripts import materialise_opening_squad_preallocation_v1 as opening_preallocation_v1  # noqa: E402
from scripts import season_carrier_allocation_v1 as carrier_allocation_v1  # noqa: E402
from scripts import world_fixed_carrier_ledger_v2 as registry_v2  # noqa: E402
from scripts.prepare_2015_world_fifa16_carrier_allocation import group_for_carrier  # noqa: E402


AUDIT_SCHEMA = "pm99-season-source-package-build-audit-v1"
OPENING_PREALLOCATION_SCHEMA = "pm99-opening-squad-preallocation-v1"
CALENDAR_BINDING_AUDIT_SCHEMA = "pm99-season-calendar-package-overlay-v1"
CALENDAR_BASE_YEAR = 1998
CALENDAR_PATCH_COUNT = 853
PRESERVE = {"policy": "preserve-existing-mode1"}


class SourcePackageBuildError(ValueError):
    """The supplied template, source intake, or fixed registry is unsafe."""


def _carrier_group(carrier_id: int) -> str | None:
    # These two clean-database records are the proven non-contiguous English
    # non-league carriers used by the canonical allocator.
    if carrier_id in carrier_allocation_v1.ENGLISH_NON_LEAGUE_CARRIER_IDS:
        return "english-non-league"
    return group_for_carrier(carrier_id)


def _sha256_document(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(package_v2.canonical_json_bytes(dict(value))).hexdigest()


def _carrier_allocation_selector_key(selector: Mapping[str, Any]) -> tuple[str, str, str, str]:
    """Return the exact four fields carried by allocation source references."""

    return tuple(str(selector.get(key) or "") for key in (
        "country_catalog", "competition_catalog", "source_path", "source_sha256"
    ))


def _selection_authorized_allocation_aliases(
    source_club_selection: Mapping[str, Any],
) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    """Map only manifest-authorized suppressed aliases to canonical selectors.

    Carrier allocation precedes this selection stage and consequently retains
    references to an August source alias in a small number of historical
    cases.  The effective projection deliberately suppresses that alias.  A
    translation is therefore safe only when an exact embedded selection
    manifest authorizes it.  Allocation selector references omit club name,
    so any collision on those four persisted fields is rejected rather than
    guessed.
    """

    manifest = source_club_selection.get("manifest")
    selections = manifest.get("selections") if isinstance(manifest, Mapping) else None
    if not isinstance(selections, list):
        raise SourcePackageBuildError("source-club selection lacks an allocation alias manifest")
    aliases: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    canonical_keys: set[tuple[str, str, str, str]] = set()
    for index, row in enumerate(selections):
        if not isinstance(row, Mapping):
            raise SourcePackageBuildError("source-club selection allocation alias is malformed")
        canonical = row.get("canonical_selector")
        selected = row.get("selected_selector")
        if not isinstance(canonical, Mapping) or not isinstance(selected, Mapping):
            raise SourcePackageBuildError("source-club selection allocation alias has no exact selectors")
        canonical_key = _carrier_allocation_selector_key(canonical)
        selected_key = _carrier_allocation_selector_key(selected)
        if not all(canonical_key) or not all(selected_key):
            raise SourcePackageBuildError("source-club selection allocation alias has an incomplete selector")
        if canonical_key == selected_key:
            raise SourcePackageBuildError(
                "source-club selection allocation alias is ambiguous without a club-name selector"
            )
        if (
            canonical_key in canonical_keys
            or canonical_key in aliases
            or selected_key in aliases
            or selected_key in canonical_keys
        ):
            raise SourcePackageBuildError(
                "source-club selection allocation aliases are ambiguous without a club-name selector"
            )
        canonical_keys.add(canonical_key)
        aliases[selected_key] = {
            "canonical_selector_key": canonical_key,
            "canonical_club_name": str(canonical.get("club_name") or ""),
            "selected_club_name": str(selected.get("club_name") or ""),
            "selection_id": str(row.get("id") or f"selection-{index}"),
        }
    return aliases


def _normalise_club_name(value: str) -> str:
    """Return the sole conservative club-name comparison key.

    No aliases or football-specific token removal occur here.  For example,
    ``Manchester United`` cannot silently match ``Man Utd``.  Punctuation,
    accents and case are presentation differences and are normalised.
    """

    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char.casefold() for char in decomposed if char.isalnum())


def _source_person_id(
    source_player: Mapping[str, Any], *, source_selector: Mapping[str, Any] | None = None,
) -> str:
    digest = source_player.get("source_row_sha256")
    if not isinstance(digest, str) or not package_v2.SHA256_RE.fullmatch(digest):
        # Tests and older source intakes can be rebuilt without fabricating an
        # identity: hash the complete immutable captured row instead.
        digest = _sha256_document(dict(source_player))
    if source_selector is not None:
        # Some aggregators repeat one raw person row across two season squads
        # (usually a transfer). Until dated identity reconciliation chooses one
        # human, retain both claims as distinct club-scoped identities rather
        # than emitting an invalid duplicate person assertion.
        digest = _sha256_document({
            "raw_source_row_sha256": digest,
            "source_selector": dict(source_selector),
        })
    return f"person-source-{digest}"


def _source_club_identity_id(country_group: str, club_name: str) -> str:
    payload = {"country_group": country_group, "normalised_name": _normalise_club_name(club_name)}
    return f"club-source-{_sha256_document(payload)}"


def _person_candidate(source_player: Mapping[str, Any]) -> tuple[str, str]:
    facts = source_player["facts"]
    source_identity = facts.get("source_identity")
    if source_identity is not None:
        # Use the same namespace for an annual row and a profiled opening row.
        # Otherwise one person acquires two keys simply by passing through the
        # opening-lineup path.
        return ("source-identity", f"{source_identity['provider']}:{source_identity['player_id']}")
    opening_source_player_id = str(source_player.get("opening_source_player_id") or "").strip()
    if opening_source_player_id:
        # Transfermarkt's published person ID is stronger than a coincidental
        # same-name/same-birth-date pair across clubs.  The preallocation join
        # supplies it only for sourced opening-XI rows.
        return ("opening-source-player-id", opening_source_player_id)
    return (
        _normalise_club_name(str(facts.get("name") or "")),
        str(facts.get("birth_date") or "unknown-date"),
    )


def _opening_fixture_date(value: object) -> str | None:
    """Return a verified ISO opening-fixture date, otherwise ``None``.

    A dated first-fixture claim may break a duplicate-person tie only when it
    is the *unique* earliest claim.  Keeping this parser narrow prevents an
    imprecise season label, a free-text date, or a current-squad timestamp from
    being mistaken for historical ownership evidence.
    """

    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _verified_calendar_binding(
    *, template: Mapping[str, Any], calendar_binding_audit: Mapping[str, Any],
    start_year: int, end_year: int, season_label: str,
) -> dict[str, Any]:
    """Validate the immutable calendar overlay evidence carried by a template.

    The overlay audit hash-binds a strict-V2 package to the generated calendar
    receipt and its output executable.  Source authoring may subsequently
    change club/player facts, but it must preserve this exact calendar claim;
    otherwise the calendar gate remains unresolved.  This is deliberately not
    a runtime/playability assertion: that evidence is owned by the later
    compile/runtime validation layer.
    """

    if calendar_binding_audit.get("schema_version") != CALENDAR_BINDING_AUDIT_SCHEMA:
        raise SourcePackageBuildError("calendar binding audit schema is unsupported")
    expected_season = {
        "start_year": start_year,
        "end_year": end_year,
        "label": season_label,
    }
    if calendar_binding_audit.get("season") != expected_season:
        raise SourcePackageBuildError("calendar binding audit targets a different season")
    if calendar_binding_audit.get("patch_count") != CALENDAR_PATCH_COUNT:
        raise SourcePackageBuildError("calendar binding audit has an unsupported patch count")
    if not isinstance(calendar_binding_audit.get("runtime_validation_pending"), bool):
        raise SourcePackageBuildError("calendar binding audit runtime status is malformed")

    for field in ("receipt_sha256", "executable_sha256", "output_package_sha256"):
        value = calendar_binding_audit.get(field)
        if not isinstance(value, str) or not package_v2.SHA256_RE.fullmatch(value):
            raise SourcePackageBuildError(f"calendar binding audit has an invalid {field}")
    if calendar_binding_audit["output_package_sha256"] != _sha256_document(template):
        raise SourcePackageBuildError("calendar binding audit does not hash-bind this template package")

    suffix = f"{start_year}-{str(end_year)[-2:]}"
    artifact_id = f"calendar-{suffix}-receipt"
    expected_proof = {"grade": "static-contract", "artifact_id": artifact_id}
    calendar = template.get("calendar")
    if not isinstance(calendar, Mapping) or any((
        calendar.get("base_year") != CALENDAR_BASE_YEAR,
        calendar.get("target_year") != start_year,
        calendar.get("target_rollover_year") != end_year,
        calendar.get("patch_artifact_id") != artifact_id,
        calendar.get("proof") != expected_proof,
    )):
        raise SourcePackageBuildError("template calendar does not carry the verified binding claim")
    artifacts = [
        row for row in template.get("artifacts", [])
        if isinstance(row, Mapping) and row.get("id") == artifact_id
    ]
    if len(artifacts) != 1:
        raise SourcePackageBuildError("template lacks one verified calendar receipt artifact")
    artifact = dict(artifacts[0])
    if (
        artifact.get("kind") != "calendar-patch"
        or artifact.get("sha256") != calendar_binding_audit["receipt_sha256"]
        or not isinstance(artifact.get("relative_path"), str)
        or not artifact["relative_path"].strip()
    ):
        raise SourcePackageBuildError("template calendar receipt artifact disagrees with its binding audit")
    return {
        "audit_sha256": _sha256_document(calendar_binding_audit),
        "template_package_sha256": _sha256_document(template),
        "receipt_sha256": calendar_binding_audit["receipt_sha256"],
        "executable_sha256": calendar_binding_audit["executable_sha256"],
        "patch_count": CALENDAR_PATCH_COUNT,
        "runtime_validation_pending": calendar_binding_audit["runtime_validation_pending"],
        # Retain the canonical overlay audit so a later strict-promotion
        # boundary can verify the full template -> source-draft proof chain,
        # rather than treating an unbound receipt hash as sufficient.
        "overlay_audit": copy.deepcopy(dict(calendar_binding_audit)),
        "calendar": copy.deepcopy(dict(calendar)),
        "artifact": artifact,
    }


def _season_years(label: str) -> tuple[int, int]:
    match = re.fullmatch(r"(19|20)(\d{2})/(\d{2})", label)
    if match is None:
        raise SourcePackageBuildError(f"unsupported season label {label!r}")
    start = int(match.group(1) + match.group(2))
    end_suffix = int(match.group(3))
    end = (start // 100) * 100 + end_suffix
    if end <= start:
        end += 100
    if end != start + 1:
        raise SourcePackageBuildError(f"season label is not consecutive: {label!r}")
    return start, end


def _proof(artifact_id: str) -> dict[str, str]:
    return {"grade": "source-captured", "artifact_id": artifact_id}


def _fallback(field: str, artifact_id: str) -> dict[str, Any]:
    return {
        "field": field,
        "method": "preserve-existing-mode1",
        "value": copy.deepcopy(PRESERVE),
        "reason": "The dated squad capture does not supply this writable PM99 fact.",
        "proof": _proof(artifact_id),
    }


def _updated_facts(source: Mapping[str, Any], artifact_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    birth_date = source.get("birth_date")
    if isinstance(birth_date, str):
        try:
            dt.date.fromisoformat(birth_date)
        except ValueError:
            birth_date = None
    facts: dict[str, Any] = {
        "birth_date": birth_date if birth_date is not None else copy.deepcopy(PRESERVE),
        "nationality": source.get("nationality") if source.get("nationality") is not None else copy.deepcopy(PRESERVE),
        "height_cm": source.get("height_cm") if source.get("height_cm") is not None else copy.deepcopy(PRESERVE),
        "weight_kg": source.get("weight_kg") if source.get("weight_kg") is not None else copy.deepcopy(PRESERVE),
        "primary_position": source.get("position") if source.get("position") is not None else copy.deepcopy(PRESERVE),
        # Broad source positions do not justify inventing PM99 fine roles.
        "fine_roles": copy.deepcopy(PRESERVE),
        # The compiler's foreign shirt-number storage is not proven writable.
        "shirt_number": copy.deepcopy(PRESERVE),
    }
    fallback_fields = [
        field
        for field in ("birth_date", "height_cm", "nationality", "shirt_number", "weight_kg")
        if isinstance(facts[field], Mapping)
    ]
    return facts, [_fallback(field, artifact_id) for field in sorted(fallback_fields)]


# Keep source-country routing identical to the allocator.  The earlier
# five-country pilot table made a valid Portugal (and every other expanded
# world-family) allocation fail only when the package bridge consumed it.
# English fixed carriers remain a separate mode-0 authoring lane because the
# allocator deliberately has no ``eng`` country-group entry.
SOURCE_CATALOG_GROUPS = dict(carrier_allocation_v1.COUNTRY_GROUPS)


def _name_index(
    registry: Mapping[str, Any], template: Mapping[str, Any]
) -> dict[tuple[str, str], set[int]]:
    result: dict[tuple[str, str], set[int]] = defaultdict(set)
    for carrier in registry["carriers"]:
        carrier_id = int(carrier["carrier_id"])
        group = _carrier_group(carrier_id)
        if group is None:
            continue
        for value in carrier["baseline_club"].values():
            if isinstance(value, str) and value.strip():
                result[(group, _normalise_club_name(value))].add(carrier_id)
    for club in template["clubs"]:
        carrier_id = int(club["carrier_id"])
        group = _carrier_group(carrier_id)
        if group is None:
            continue
        for field in ("name", "full_name"):
            value = club.get(field)
            if isinstance(value, str) and value.strip():
                result[(group, _normalise_club_name(value))].add(carrier_id)
    return result


def build_draft(
    *,
    template: Mapping[str, Any],
    source_intake: Mapping[str, Any],
    registry: Mapping[str, Any],
    carrier_allocation: Mapping[str, Any] | None = None,
    source_club_selection: Mapping[str, Any] | None = None,
    opening_squad_preallocation: Mapping[str, Any] | None = None,
    calendar_binding_audit: Mapping[str, Any] | None = None,
    template_prevalidated: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a structurally strict draft package and deterministic audit."""

    template = copy.deepcopy(dict(template))
    original_template_sha256 = _sha256_document(template)
    source_intake = copy.deepcopy(dict(source_intake))
    registry = copy.deepcopy(dict(registry))
    carrier_allocation = (
        copy.deepcopy(dict(carrier_allocation)) if carrier_allocation is not None else None
    )
    source_club_selection = (
        copy.deepcopy(dict(source_club_selection)) if source_club_selection is not None else None
    )
    opening_squad_preallocation = (
        copy.deepcopy(dict(opening_squad_preallocation))
        if opening_squad_preallocation is not None else None
    )
    calendar_binding_audit = (
        copy.deepcopy(dict(calendar_binding_audit))
        if calendar_binding_audit is not None else None
    )
    # Batch callers validate their immutable template once before fan-out.
    # A standalone hash-bound calendar overlay can originate from a blocked
    # source draft: strict V2 rejects its unresolved same-person candidates,
    # even though those candidates must remain visible in the new draft audit.
    # Validate that narrow path structurally here; _verified_calendar_binding
    # below still requires the exact overlay/package hash and calendar receipt.
    # Unbound standalone templates retain the fail-closed strict default.
    if not template_prevalidated:
        package_v2.validate_package(template, strict=calendar_binding_audit is None)
    registry_v2.validate_registry(registry)
    if source_intake.get("schema_version") != source_intake_v1.SCHEMA:
        raise SourcePackageBuildError("source intake schema is unsupported")
    if source_intake.get("registry_sha256") != _sha256_document(registry):
        raise SourcePackageBuildError("source intake targets a different fixed-carrier registry")
    source_season = source_intake.get("season")
    if not isinstance(source_season, dict) or not isinstance(source_season.get("label"), str):
        raise SourcePackageBuildError("source intake season is malformed")
    start_year, end_year = _season_years(source_season["label"])
    calendar_binding: dict[str, Any] | None = None
    if calendar_binding_audit is not None:
        calendar_binding = _verified_calendar_binding(
            template=template,
            calendar_binding_audit=calendar_binding_audit,
            start_year=start_year,
            end_year=end_year,
            season_label=source_season["label"],
        )

    source_club_selection_sha256: str | None = None
    selection_allocation_aliases: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    selection_allocation_translations: list[dict[str, Any]] = []
    selection_allocation_suppressions: list[dict[str, Any]] = []
    if source_club_selection is not None:
        try:
            source_club_selection_v1.validate_selection(
                selection=source_club_selection, source_intake=source_intake
            )
        except source_club_selection_v1.SourceClubSelectionError as exc:
            raise SourcePackageBuildError(f"source-club selection is invalid: {exc}") from exc
        if source_club_selection.get("season") != source_season:
            raise SourcePackageBuildError("source-club selection targets a different season")
        selection_allocation_aliases = _selection_authorized_allocation_aliases(
            source_club_selection
        )
        source_rows = source_club_selection_v1.effective_source_clubs(
            selection=source_club_selection, source_intake=source_intake
        )
        source_club_selection_sha256 = _sha256_document(source_club_selection)
    else:
        source_rows = list(source_intake.get("source_clubs", []))

    template_clubs = {int(row["carrier_id"]): row for row in template["clubs"]}
    template_players = {str(row["id"]): row for row in template["players"]}
    registry_carriers = {int(row["carrier_id"]): row for row in registry["carriers"]}
    if set(template_clubs) != set(registry_carriers):
        raise SourcePackageBuildError("template club carriers do not exactly cover the registry")

    name_index = _name_index(registry, template)
    source_names: Counter[tuple[str, str]] = Counter(
        (
            SOURCE_CATALOG_GROUPS.get(str(row["selector"]["country_catalog"]), ""),
            _normalise_club_name(str(row["selector"]["club_name"])),
        )
        for row in source_rows
    )
    mappings: list[tuple[dict[str, Any], int, str]] = []
    unresolved_sources: list[dict[str, Any]] = []
    out_of_scope_sources: list[dict[str, str]] = []
    used_carriers: set[int] = set()
    opening_preallocation_sha256: str | None = None
    if opening_squad_preallocation is not None:
        if opening_squad_preallocation.get("schema_version") != OPENING_PREALLOCATION_SCHEMA:
            raise SourcePackageBuildError("opening squad preallocation schema is unsupported")
        opening_sources = opening_squad_preallocation.get("sources")
        if not isinstance(opening_sources, Mapping):
            raise SourcePackageBuildError("opening squad preallocation sources are malformed")
        if opening_sources.get("source_intake_sha256") != _sha256_document(source_intake):
            raise SourcePackageBuildError("opening squad preallocation targets a different source intake")
        if opening_sources.get("source_capture_sha256") != source_intake.get("source_capture_sha256"):
            raise SourcePackageBuildError("opening squad preallocation targets a different source capture")
        if source_club_selection is None:
            if opening_sources.get("source_club_selection_sha256") is not None:
                raise SourcePackageBuildError(
                    "selection-bound opening squad preallocation requires its source-club selection"
                )
        elif opening_sources.get("source_club_selection_sha256") != source_club_selection_sha256:
            raise SourcePackageBuildError(
                "opening squad preallocation targets a different source-club selection"
            )
        if opening_squad_preallocation.get("season") != source_season:
            raise SourcePackageBuildError("opening squad preallocation targets a different season")
        projected_rows = opening_squad_preallocation.get("source_clubs")
        if not isinstance(projected_rows, list):
            raise SourcePackageBuildError("opening squad preallocation has no source clubs")
        if source_club_selection is not None:
            try:
                opening_preallocation_v1.validate_selection_bound_preallocation(
                    preallocation=opening_squad_preallocation,
                    source_intake=source_intake,
                    source_club_selection=source_club_selection,
                )
            except opening_preallocation_v1.PreallocationError as exc:
                raise SourcePackageBuildError(
                    f"selection-bound opening squad preallocation is invalid: {exc}"
                ) from exc
        base_selectors = {
            tuple(str(row["selector"][key]) for key in (
                "country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256"
            ))
            for row in source_rows
        }
        projected_selectors = [
            tuple(str(row["selector"][key]) for key in (
                "country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256"
            ))
            for row in projected_rows if isinstance(row, Mapping) and isinstance(row.get("selector"), Mapping)
        ]
        if len(projected_selectors) != len(projected_rows) or set(projected_selectors) != base_selectors or len(set(projected_selectors)) != len(projected_selectors):
            raise SourcePackageBuildError("opening squad preallocation does not exactly cover source intake clubs")
        for row in projected_rows:
            if row.get("opening_xi_complete") is True:
                players = row.get("players")
                orders = [player.get("opening_xi_order") for player in (players[:11] if isinstance(players, list) else [])]
                if orders != list(range(1, 12)):
                    raise SourcePackageBuildError("complete opening squad preallocation must put XI orders 1..11 first")
        source_rows = list(projected_rows)
        opening_preallocation_sha256 = _sha256_document(opening_squad_preallocation)
    if carrier_allocation is not None:
        if carrier_allocation.get("schema_version") != carrier_allocation_v1.SCHEMA:
            raise SourcePackageBuildError("carrier allocation schema is unsupported")
        if carrier_allocation.get("source_sha256") != source_intake.get("source_capture_sha256"):
            raise SourcePackageBuildError("carrier allocation targets a different source capture")
        if carrier_allocation.get("registry_sha256") != _sha256_document(registry):
            raise SourcePackageBuildError("carrier allocation targets a different fixed-carrier registry")
        allocation_season = carrier_allocation.get("season")
        if not isinstance(allocation_season, Mapping) or allocation_season.get("label") != source_season["label"]:
            raise SourcePackageBuildError("carrier allocation targets a different season")
        if carrier_allocation.get("topology_policy") != "fixed-country-family-preserve-continuing-then-canonical-replacement":
            raise SourcePackageBuildError("carrier allocation topology policy is unsupported")
        source_by_selector: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for source_club in source_rows:
            selector = source_club["selector"]
            selector_key = _carrier_allocation_selector_key(selector)
            if selector_key in source_by_selector:
                raise SourcePackageBuildError("source intake duplicates a carrier-allocation selector")
            source_by_selector[selector_key] = source_club
        for alias_key, alias in selection_allocation_aliases.items():
            if alias_key in source_by_selector:
                raise SourcePackageBuildError(
                    "source-club selection allocation alias collides with an effective source selector"
                )
            canonical_key = alias["canonical_selector_key"]
            if canonical_key not in source_by_selector:
                raise SourcePackageBuildError(
                    "source-club selection allocation alias has no effective canonical source selector"
                )
        # A prior allocation may have treated both all-season and August
        # source rows as independently assignable.  The selection manifest
        # establishes that the canonical row is the one fixed-carrier identity.
        # If that canonical allocation reference is present, retain it and
        # suppress the duplicate alias reference rather than assigning one
        # real club to two carriers.  The vacated fixed carrier remains an
        # explicit downstream identity disposition; it is never silently
        # reassigned here.
        canonical_allocation_reference_keys = {
            _carrier_allocation_selector_key(row["source_selector"])
            for row in carrier_allocation.get("assignments", [])
            if isinstance(row, Mapping)
            and isinstance(row.get("source_selector"), Mapping)
            and _carrier_allocation_selector_key(row["source_selector"])
            in {alias["canonical_selector_key"] for alias in selection_allocation_aliases.values()}
        }
        used_selectors: set[tuple[str, str, str, str]] = set()
        previous_carrier = 0
        for row in carrier_allocation.get("assignments", []):
            if not isinstance(row, Mapping):
                raise SourcePackageBuildError("carrier allocation assignment is malformed")
            carrier_id = row.get("carrier_id")
            if not isinstance(carrier_id, int) or carrier_id <= previous_carrier or carrier_id not in registry_carriers:
                raise SourcePackageBuildError("carrier allocation assignments must be carrier-sorted and known")
            previous_carrier = carrier_id
            if row.get("country_group") != _carrier_group(carrier_id):
                raise SourcePackageBuildError(f"carrier allocation crosses country group at {carrier_id}")
            selector = row.get("source_selector")
            if not isinstance(selector, Mapping):
                raise SourcePackageBuildError(f"carrier allocation {carrier_id} has no source selector")
            selector_key = _carrier_allocation_selector_key(selector)
            source_club = source_by_selector.get(selector_key)
            effective_selector_key = selector_key
            selected_alias = None
            if source_club is None:
                selected_alias = selection_allocation_aliases.get(selector_key)
                if selected_alias is not None:
                    effective_selector_key = selected_alias["canonical_selector_key"]
                    source_club = source_by_selector.get(effective_selector_key)
            if source_club is None:
                raise SourcePackageBuildError(f"carrier allocation {carrier_id} has an unknown or reused source selector")
            expected_club_name = (
                selected_alias["selected_club_name"]
                if selected_alias is not None
                else str(source_club["selector"]["club_name"])
            )
            if str(row.get("club_name")) != expected_club_name:
                raise SourcePackageBuildError(f"carrier allocation {carrier_id} club name disagrees with source")
            method = str(row.get("method"))
            if method not in {
                "continuing-club-normalized-identity",
                "same-country-replacement-canonical-source-order",
            }:
                raise SourcePackageBuildError(f"carrier allocation {carrier_id} has unsupported method")
            if (
                selected_alias is not None
                and effective_selector_key in canonical_allocation_reference_keys
            ):
                selection_allocation_suppressions.append({
                    "carrier_id": carrier_id,
                    "selection_id": selected_alias["selection_id"],
                    "allocation_alias_club_name": selected_alias["selected_club_name"],
                    "effective_canonical_club_name": selected_alias["canonical_club_name"],
                    "allocation_source_selector": dict(selector),
                    "effective_source_selector": dict(source_club["selector"]),
                    "reason": "canonical-allocation-reference-retained-alias-reference-suppressed",
                })
                continue
            if effective_selector_key in used_selectors:
                raise SourcePackageBuildError(f"carrier allocation {carrier_id} has an unknown or reused source selector")
            used_carriers.add(carrier_id)
            used_selectors.add(effective_selector_key)
            if selected_alias is not None:
                selection_allocation_translations.append({
                    "carrier_id": carrier_id,
                    "selection_id": selected_alias["selection_id"],
                    "allocation_alias_club_name": selected_alias["selected_club_name"],
                    "effective_canonical_club_name": selected_alias["canonical_club_name"],
                    "allocation_source_selector": dict(selector),
                    "effective_source_selector": dict(source_club["selector"]),
                })
            mappings.append((source_club, carrier_id, method))
        for source_club in source_rows:
            selector = source_club["selector"]
            selector_key = _carrier_allocation_selector_key(selector)
            if selector_key in used_selectors:
                continue
            source_catalog = str(selector["country_catalog"])
            # Once a canonical allocation is supplied it is the sole owner of
            # top-flight selection and fixed-capacity decisions.  Captures may
            # legitimately include lower divisions or parallel catalogues;
            # those rows are evidence outside this foreign-carrier projection,
            # not failed club matches.
            out_of_scope_sources.append({
                "source_club_name": str(selector["club_name"]),
                "country_catalog": source_catalog,
                "reason": "not-selected-by-canonical-carrier-allocation",
            })
    else:
        for source_club in source_rows:
            source_name = str(source_club["selector"]["club_name"])
            source_catalog = str(source_club["selector"]["country_catalog"])
            group = SOURCE_CATALOG_GROUPS.get(source_catalog)
            if group is None:
                out_of_scope_sources.append({
                    "source_club_name": source_name,
                    "country_catalog": source_catalog,
                    "reason": "catalog-is-not-part-of-the-fixed-foreign-carrier-registry",
                })
                continue
            key = _normalise_club_name(source_name)
            candidates = sorted(name_index.get((group, key), set()))
            if source_names[(group, key)] == 1 and len(candidates) == 1 and candidates[0] not in used_carriers:
                mappings.append((source_club, candidates[0], "continuing-club-exact-normalised-name"))
                used_carriers.add(candidates[0])
            else:
                unresolved_sources.append({
                    "source_club_name": source_name,
                    "carrier_group": group,
                    "normalised_name": key,
                    "candidate_carrier_ids": candidates,
                    "reason": "non-unique-or-absent-exact-normalised-name-match",
                })

    artifact_id = f"source-capture-{start_year}-{str(end_year)[-2:]}"
    source_id = f"footballsquads-{start_year}-{str(end_year)[-2:]}"
    source_artifact = {
        "id": artifact_id,
        "kind": "season-input",
        "sha256": str(source_intake["source_capture_sha256"]),
    }
    template["artifacts"] = sorted(
        [row for row in template["artifacts"] if row["id"] != artifact_id] + [source_artifact],
        key=lambda row: str(row["id"]),
    )
    if source_club_selection_sha256 is not None:
        selection_artifact_id = f"source-club-selection-{start_year}-{str(end_year)[-2:]}"
        selection_artifact = {
            "id": selection_artifact_id,
            "kind": "season-input",
            "sha256": source_club_selection_sha256,
        }
        template["artifacts"] = sorted(
            [row for row in template["artifacts"] if row["id"] != selection_artifact_id]
            + [selection_artifact],
            key=lambda row: str(row["id"]),
        )
    opening_artifact_id: str | None = None
    if opening_preallocation_sha256 is not None:
        opening_artifact_id = f"opening-squad-preallocation-{start_year}-{str(end_year)[-2:]}"
        opening_artifact = {
            "id": opening_artifact_id,
            "kind": "season-input",
            "sha256": opening_preallocation_sha256,
        }
        template["artifacts"] = sorted(
            [row for row in template["artifacts"] if row["id"] != opening_artifact_id] + [opening_artifact],
            key=lambda row: str(row["id"]),
        )
    source_metadata = source_intake.get("source", {})
    source_entry = {
        "id": source_id,
        "title": str(source_metadata.get("title") or "Dated FootballSquads capture"),
        "proof_grade": "source-captured",
        "evidence_artifact_id": artifact_id,
    }
    template["sources"] = sorted(
        [row for row in template["sources"] if row["id"] != source_id] + [source_entry],
        key=lambda row: str(row["id"]),
    )
    proof_id = f"proof-source-{start_year}-{str(end_year)[-2:]}"
    proof_entry = {
        "id": proof_id,
        "grade": "source-captured",
        "artifact_id": artifact_id,
        "covers": ["dated club squad rows and player facts"],
    }
    template["proofs"] = sorted(
        [row for row in template["proofs"] if row["id"] != proof_id] + [proof_entry],
        key=lambda row: str(row["id"]),
    )

    # Plan allocations first. Shared package IDs are removed from writable
    # capacity before source rows are assigned, so they cannot consume a row
    # and cannot be overwritten across clubs.
    roster_occurrences: dict[str, list[int]] = defaultdict(list)
    for club_carrier_id, club in template_clubs.items():
        for player_id in club["roster_player_ids"]:
            roster_occurrences[str(player_id)].append(club_carrier_id)
    shared_player_ids = {
        player_id for player_id, carrier_ids in roster_occurrences.items() if len(carrier_ids) > 1
    }
    source_person_candidates: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    source_row_claims: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source_club, _carrier_id, _method in mappings:
        for source_player in source_club["players"]:
            raw_digest = str(source_player.get("source_row_sha256") or _sha256_document(source_player))
            claim = {
                "club": str(source_club["selector"]["club_name"]),
                "selector": dict(source_club["selector"]),
                "opening_fixture_date": _opening_fixture_date(source_club.get("opening_fixture_date")),
                "opening_source_player_id": str(source_player.get("opening_source_player_id") or ""),
                "opening_xi_order": source_player.get("opening_xi_order"),
            }
            source_row_claims[raw_digest].append(claim)
            source_person_candidates[_person_candidate(source_player)].append({
                "source_club_name": str(source_club["selector"]["club_name"]),
                "source_row_sha256": raw_digest,
                "opening_fixture_date": claim["opening_fixture_date"],
                "opening_xi_order": claim["opening_xi_order"],
            })

    # The first valid fixture is a dated snapshot of the season's opening
    # squad.  When the exact same source person appears in more than one
    # squad, one *uniquely earlier* opening-fixture claim deterministically
    # wins; the later squad cannot safely retain that person at the opening
    # snapshot.  Equal-date claims (or undated rows) remain hard conflicts.
    # This deliberately does not invent a transfer date or choose between
    # clubs by their name, country, or carrier order.
    person_identity_conflicts: dict[tuple[str, str], list[dict[str, Any]]] = {}
    person_identity_resolutions: list[dict[str, Any]] = []
    person_identity_losers: set[tuple[str, str]] = set()
    for candidate, claims in sorted(source_person_candidates.items()):
        if len(claims) < 2:
            continue
        opening_claims = [
            row for row in claims
            if isinstance(row["opening_xi_order"], int) and row["opening_fixture_date"] is not None
        ]
        earliest = min((str(row["opening_fixture_date"]) for row in opening_claims), default=None)
        winners = [row for row in opening_claims if row["opening_fixture_date"] == earliest]
        if earliest is not None and len(winners) == 1:
            winner = winners[0]
            for row in claims:
                if row is not winner:
                    person_identity_losers.add((str(row["source_row_sha256"]), str(row["source_club_name"])))
            resolution = "unique-earliest-dated-opening-fixture-owner-retained-later-or-undated-claims-excluded"
        else:
            winner = None
            person_identity_conflicts[candidate] = claims
            resolution = "unresolved-person-identity-claims-lack-a-unique-earliest-dated-opening-fixture-owner"
        person_identity_resolutions.append({
            "normalised_name": candidate[0],
            "birth_date": candidate[1],
            "claims": claims,
            "resolution": resolution,
            "winner_club": winner["source_club_name"] if winner is not None else None,
            "winner_opening_fixture_date": winner["opening_fixture_date"] if winner is not None else None,
        })

    repeated_row_resolutions: list[dict[str, Any]] = []
    repeated_row_losers: set[tuple[str, str]] = set()
    distinct_profile_rows: set[str] = set()
    for digest, claims in sorted(source_row_claims.items()):
        if len(claims) < 2:
            continue
        opening_claims = [row for row in claims if isinstance(row["opening_xi_order"], int)]
        profile_ids = [row["opening_source_player_id"] for row in claims]
        if len(opening_claims) == 1:
            winner = opening_claims[0]
            for row in claims:
                if row is not winner:
                    repeated_row_losers.add((digest, str(row["club"])))
            resolution = "unique-sourced-opening-xi-owner-retained-other-season-squad-claims-excluded"
        elif all(profile_ids) and len(set(profile_ids)) == len(profile_ids):
            distinct_profile_rows.add(digest)
            winner = None
            resolution = "distinct-published-profile-ids-retained-as-club-scoped-homonyms"
        else:
            dated_opening_claims = [
                row for row in opening_claims if row["opening_fixture_date"] is not None
            ]
            earliest = min((str(row["opening_fixture_date"]) for row in dated_opening_claims), default=None)
            winners = [row for row in dated_opening_claims if row["opening_fixture_date"] == earliest]
            if earliest is not None and len(winners) == 1:
                winner = winners[0]
                for row in claims:
                    if row is not winner:
                        repeated_row_losers.add((digest, str(row["club"])))
                resolution = "unique-earliest-dated-opening-fixture-owner-retained-later-or-undated-claims-excluded"
            else:
                winner = None
                for row in claims:
                    repeated_row_losers.add((digest, str(row["club"])))
                resolution = "unresolved-repeated-person-claim-all-copies-excluded"
        repeated_row_resolutions.append({
            "source_row_sha256": digest,
            "claims": claims,
            "resolution": resolution,
            "winner_club": winner["club"] if winner is not None else None,
        })

    planned: dict[str, list[tuple[int, dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    mapping_rows: list[dict[str, Any]] = []
    for source_club, carrier_id, allocation_method in mappings:
        # A strict template may already contain reviewed recycle/append
        # transactions.  Its package player IDs are therefore the safe target
        # slots, while the registry remains authoritative for club grouping.
        all_slots = list(template_clubs[carrier_id]["roster_player_ids"])
        slots = [player_id for player_id in all_slots if str(player_id) not in shared_player_ids]
        all_players = list(source_club["players"])
        required_xi_hashes = {
            str(player.get("source_row_sha256") or _sha256_document(player))
            for player in all_players[:11]
        } if source_club.get("opening_xi_complete") is True else set()
        players = [
            source_player for source_player in all_players
            if _person_candidate(source_player) not in person_identity_conflicts
            and (
                str(source_player.get("source_row_sha256") or _sha256_document(source_player)),
                str(source_club["selector"]["club_name"]),
            ) not in person_identity_losers
            and (
                str(source_player.get("source_row_sha256") or _sha256_document(source_player)),
                str(source_club["selector"]["club_name"]),
            ) not in repeated_row_losers
        ]
        # A later current intake may be replayed over an earlier provisional
        # source draft.  If that draft already has an *exactly identical*
        # source-person ID in an unshared slot of this same carrier, it is a
        # deterministic identity-preserving target for the current source
        # row.  Reserve it before the normal source-order/slot-order pass.
        # This avoids duplicating one proved source person merely because its
        # stale slot falls after newly allocated slots.  No name/date heuristic
        # or cross-carrier reuse is permitted.
        # Capacity selection remains source-order first.  Identity retention
        # may only choose the destination slot for a row already selected by
        # that rule; it must never displace an earlier opening-squad row with
        # a later source row merely because the later row has a legacy slot.
        selected_players = players[:len(slots)]
        source_person_ids = [
            _source_person_id(
                source_player,
                source_selector=(
                    source_club["selector"]
                    if str(source_player.get("source_row_sha256") or _sha256_document(source_player))
                    in distinct_profile_rows
                    else None
                ),
            )
            for source_player in selected_players
        ]
        source_person_id_counts = Counter(source_person_ids)
        slots_by_person_id: dict[str, list[str]] = defaultdict(list)
        for player_id in slots:
            target = template_players[str(player_id)]
            if target.get("club_id") == template_clubs[carrier_id]["id"]:
                slots_by_person_id[str(target.get("person_id") or "")].append(str(player_id))
        identity_retained_pairs: list[tuple[str, dict[str, Any]]] = []
        reserved_slot_ids: set[str] = set()
        reserved_source_indexes: set[int] = set()
        for index, (source_player, person_id) in enumerate(zip(selected_players, source_person_ids)):
            candidate_slots = slots_by_person_id.get(person_id, [])
            if source_person_id_counts[person_id] == 1 and len(candidate_slots) == 1:
                player_id = candidate_slots[0]
                identity_retained_pairs.append((player_id, source_player))
                reserved_slot_ids.add(player_id)
                reserved_source_indexes.add(index)
        remaining_slots = [str(player_id) for player_id in slots if str(player_id) not in reserved_slot_ids]
        remaining_players = [
            source_player for index, source_player in enumerate(selected_players)
            if index not in reserved_source_indexes
        ]
        ordered_pairs = identity_retained_pairs + list(zip(
            remaining_slots[:len(remaining_players)],
            remaining_players[:len(remaining_slots)],
        ))
        allocated_count = len(ordered_pairs)
        allocated_hashes = {
            str(source_player.get("source_row_sha256") or _sha256_document(source_player))
            for _player_id, source_player in ordered_pairs
        }
        for player_id, source_player in ordered_pairs:
            planned[str(player_id)].append((carrier_id, source_club, source_player))
        mapping_rows.append({
            "carrier_id": carrier_id,
            "club_id": str(template_clubs[carrier_id]["id"]),
            "source_club_name": str(source_club["selector"]["club_name"]),
            "allocation_method": allocation_method,
            "fixed_slot_count": len(all_slots),
            "writable_unique_slot_count": len(slots),
            "shared_slot_exclusion_count": len(all_slots) - len(slots),
            "source_player_count": len(all_players),
            "ambiguous_source_player_exclusion_count": len(all_players) - len(players),
            "identity_retained_source_slot_count": len(identity_retained_pairs),
            "allocated_player_count": allocated_count,
            "retained_native_slot_count": max(0, len(slots) - len(players)),
            "truncated_source_player_count": max(0, len(players) - len(slots)),
            "opening_xi_preallocation_complete": source_club.get("opening_xi_complete") if opening_squad_preallocation is not None else None,
            "xi_capacity_satisfied": (
                source_club.get("opening_xi_complete") is True
                and allocated_count >= 11 and required_xi_hashes <= allocated_hashes
                if opening_squad_preallocation is not None else allocated_count >= 11
            ),
        })
    updated_players = 0
    for player_id, rows in sorted(planned.items()):
        if len(rows) != 1:
            raise SourcePackageBuildError(f"unique writable player slot was allocated twice: {player_id}")
        target = template_players.get(player_id)
        if target is None:
            raise SourcePackageBuildError(
                f"fixed package player {player_id} is absent from template package"
            )
        carrier_id, _source_club, source_player = rows[0]
        source_facts = source_player["facts"]
        target["club_id"] = str(template_clubs[carrier_id]["id"])
        source_display_name = unicodedata.normalize("NFC", str(source_facts["name"]))
        target["name"] = source_display_name
        target["source_name"] = source_display_name
        # Carry the optional provider identity to the recipe, and never leave
        # one from a replayed earlier draft attached to a different source row.
        target.pop("source_identity", None)
        if source_facts.get("source_identity") is not None:
            target["source_identity"] = copy.deepcopy(source_facts["source_identity"])
        raw_row_digest = str(source_player.get("source_row_sha256") or _sha256_document(source_player))
        target["person_id"] = _source_person_id(
            source_player,
            source_selector=_source_club["selector"] if raw_row_digest in distinct_profile_rows else None,
        )
        # A source-bound person must remain writable even when this fixed
        # carrier was a whole-record native fallback in an earlier template.
        # Secondary facts below can still retain their explicit per-field
        # preserve policy.  Leaving the *player* policy in place would skip
        # the entire record, silently retaining the baseline person's name,
        # ratings and facts while claiming a target-season identity.
        target.pop("policy", None)
        target["facts"], target["fact_fallbacks"] = _updated_facts(source_facts, artifact_id)
        target["proof"] = _proof(opening_artifact_id or artifact_id)
        # Ratings are deliberately untouched: their independent editorial
        # layer owns that claim.
        updated_players += 1

    # A source-selection suppression means the old template still carries
    # historical source-person assertions in an allocation row which is no
    # longer allowed to own that club.  Retaining those IDs would make the
    # structural V2 validator reject the draft as a duplicate person when the
    # canonical owner receives the same selected opening squad.  Quarantine
    # only those stale source IDs under a deterministic carrier/slot-scoped
    # provisional identity and preserve their write policy.  This does not
    # assign a club, alter the raw intake, or resolve the carrier: the audit
    # below keeps both the suppressed allocation and every affected player
    # visible as blockers for a later identity disposition.
    suppressed_player_identity_quarantines: list[dict[str, Any]] = []
    for suppression in selection_allocation_suppressions:
        carrier_id = int(suppression["carrier_id"])
        club = template_clubs[carrier_id]
        for player_id in club["roster_player_ids"]:
            target = template_players[str(player_id)]
            previous_person_id = target.get("person_id")
            if not isinstance(previous_person_id, str) or not previous_person_id.startswith("person-source-"):
                continue
            provisional_person_id = f"person-hold-{_sha256_document({
                'source_club_selection_sha256': source_club_selection_sha256,
                'carrier_id': carrier_id,
                'player_id': str(player_id),
                'previous_person_id': previous_person_id,
            })}"
            target["person_id"] = provisional_person_id
            target["policy"] = "preserve-existing-mode1"
            target.pop("source_identity", None)
            suppressed_player_identity_quarantines.append({
                "carrier_id": carrier_id,
                "player_id": str(player_id),
                "previous_person_id": previous_person_id,
                "provisional_person_id": provisional_person_id,
                "selection_id": suppression["selection_id"],
            })

    for source_club, carrier_id, allocation_method in mappings:
        club = template_clubs[carrier_id]
        club["proof"] = _proof(artifact_id)
        source_name = str(source_club["selector"]["club_name"])
        # A continuing match may come from the original carrier registry,
        # while this template already describes a different season. Its
        # players must not acquire the historical squad but retain an
        # unrelated template label (e.g. Bremen under Hannover in 2012/13).
        # Keep an already equivalent friendly spelling unchanged.
        if (allocation_method == "same-country-replacement-canonical-source-order" or
                _normalise_club_name(str(club["name"])) != _normalise_club_name(source_name)):
            country_group = _carrier_group(carrier_id)
            if country_group is None:
                raise SourcePackageBuildError(f"source-mapped carrier {carrier_id} has no fixed country group")
            club["name"] = source_name
            club["full_name"] = source_name
            club["identity_id"] = _source_club_identity_id(country_group, source_name)

    template["season"] = {
        "start_year": start_year,
        "end_year": end_year,
        "label": source_season["label"],
    }
    template["package_id"] = f"world-{start_year}-{str(end_year)[-2:]}-source-draft"
    template["calendar"]["target_year"] = start_year
    template["calendar"]["target_rollover_year"] = end_year
    if calendar_binding is not None:
        bound_artifacts = [
            row for row in template["artifacts"]
            if row.get("id") == calendar_binding["artifact"]["id"]
        ]
        if (
            template["calendar"] != calendar_binding["calendar"]
            or bound_artifacts != [calendar_binding["artifact"]]
        ):
            raise SourcePackageBuildError("source authoring changed a verified calendar binding claim")
    # This is an explicitly blocked authoring draft.  Strict validation is a
    # release gate and rejects target-season people who still collide with an
    # untouched legacy tail slot.  Preserve that collision as audit data so
    # sparse seasons can still materialise and be repaired deterministically.
    package_v2.validate_package(template, strict=False)

    candidate_players: dict[tuple[str, str], list[str]] = defaultdict(list)
    for player in template["players"]:
        candidate = package_v2._person_candidate_key(player)
        if candidate is not None:
            candidate_players[candidate].append(str(player["id"]))
    retained_candidate_conflicts = {
        key: ids for key, ids in candidate_players.items() if len(ids) > 1
    }

    below_capacity = [row for row in mapping_rows if row["retained_native_slot_count"]]
    xi_shortfalls = [row for row in mapping_rows if not row["xi_capacity_satisfied"]]
    mapped_carrier_ids = {int(row["carrier_id"]) for row in mapping_rows}
    relevant_shared_player_ids = sorted(
        player_id
        for player_id in shared_player_ids
        if any(carrier_id in mapped_carrier_ids for carrier_id in roster_occurrences[player_id])
    )
    allocation_gaps = list(carrier_allocation.get("gaps", [])) if carrier_allocation is not None else []
    blocking_allocation_gaps = [
        row for row in allocation_gaps
        if row.get("status") == "source-unavailable-or-insufficient-country-capacity-blocked"
    ]
    blocker_rows: list[dict[str, Any]] = []
    unresolved_repeated_rows = [
        row for row in repeated_row_resolutions
        if row["resolution"] == "unresolved-repeated-person-claim-all-copies-excluded"
    ]
    if unresolved_repeated_rows:
        blocker_rows.append({
            "code": "repeated-source-person-identity-unresolved",
            "count": len(unresolved_repeated_rows),
            "message": (
                "Repeated source rows without one dated opening-XI owner or distinct "
                "published profile IDs were excluded and require explicit identity reconciliation."
            ),
        })
    if unresolved_sources:
        blocker_rows.append({
            "code": "source-club-carrier-unresolved",
            "count": len(unresolved_sources),
            "message": "These source clubs need an explicit fixed-carrier identity decision.",
        })
    if blocking_allocation_gaps:
        blocker_rows.append({
            "code": "carrier-allocation-gaps-unresolved",
            "count": len(blocking_allocation_gaps),
            "message": "The canonical same-country allocation has real carriers without a source-complete target-season assignment.",
        })
    real_registry_carriers = set(registry_carriers) - carrier_allocation_v1.SYSTEM_SELECTION_IDS
    unmatched_carriers = sorted(real_registry_carriers - used_carriers)
    if unmatched_carriers:
        blocker_rows.append({
            "code": "fixed-carrier-season-identity-unresolved",
            "count": len(unmatched_carriers),
            "message": "Each remaining carrier needs a continuing/exited season identity disposition.",
        })
    if below_capacity:
        blocker_rows.append({
            "code": "source-squad-below-fixed-capacity",
            "count": len(below_capacity),
            "message": "Native tail slots remain and need opening-date squad evidence or an explicit vacancy policy.",
        })
    if xi_shortfalls:
        blocker_rows.append({
            "code": "safe-opening-xi-capacity-unavailable",
            "count": len(xi_shortfalls),
            "message": "After shared-slot and ambiguous-person exclusions, fewer than eleven safe source assignments remain.",
        })
    if retained_candidate_conflicts:
        blocker_rows.append({
            "code": "retained-native-person-candidate-conflicts",
            "count": len(retained_candidate_conflicts),
            "message": "Source-authored people still collide with legacy tail records; complete the target-season country pool before strict compilation.",
        })
    # These are unconditional because this bridge owns none of these facts.
    blocker_rows.extend([
        {"code": "opening-lineups-required", "count": len(real_registry_carriers), "message": "Opening XI/formation evidence is owned by the opening-fixture layer."},
        {"code": "target-season-managers-required", "count": len(real_registry_carriers), "message": "Correct target-season manager strings are required; template fallback is forbidden."},
        {"code": "target-season-kit-dispositions-required", "count": len(real_registry_carriers), "message": "Continuing clubs need historical kits; native fallback is allowed only for exited carriers."},
        {"code": "ratings-reconciliation-required", "count": updated_players, "message": "This bridge retains ratings pending their deterministic owner layer."},
    ])
    if calendar_binding is None:
        blocker_rows.append({
            "code": "target-season-calendar-receipt-required",
            "count": 1,
            "message": "Changed calendar years require a matching generated patch artifact and receipt.",
        })
    audit = {
        "schema_version": AUDIT_SCHEMA,
        "season": dict(template["season"]),
        "registry_sha256": _sha256_document(registry),
        "source_intake_sha256": _sha256_document(source_intake),
        "source_club_selection_sha256": source_club_selection_sha256,
        "opening_squad_preallocation_sha256": opening_preallocation_sha256,
        "carrier_allocation_sha256": (
            _sha256_document(carrier_allocation) if carrier_allocation is not None else None
        ),
        "calendar_binding": calendar_binding,
        "template_package_sha256": original_template_sha256,
        "draft_package_sha256": _sha256_document(template),
        "release_eligible": not blocker_rows,
        "coverage": {
            "fixed_carrier_count": len(registry_carriers),
            "raw_source_club_count": len(source_intake.get("source_clubs", [])),
            "source_club_count": len(source_rows),
            "source_club_selection_count": (
                len(source_club_selection.get("selections", []))
                if source_club_selection is not None else 0
            ),
            "source_club_selection_allocation_translation_count": len(
                selection_allocation_translations
            ),
            "source_club_selection_allocation_suppression_count": len(
                selection_allocation_suppressions
            ),
            "source_club_selection_suppressed_player_identity_quarantine_count": len(
                suppressed_player_identity_quarantines
            ),
            "opening_xi_preallocated_club_count": sum(
                row.get("opening_xi_complete") is True for row in source_rows
            ) if opening_squad_preallocation is not None else 0,
            "out_of_scope_source_club_count": len(out_of_scope_sources),
            "exact_unique_club_match_count": len(mappings),
            "continuing_club_assignment_count": sum(
                row["allocation_method"] in {
                    "continuing-club-normalized-identity",
                    "continuing-club-exact-normalised-name",
                }
                for row in mapping_rows
            ),
            "same_country_replacement_count": sum(
                row["allocation_method"] == "same-country-replacement-canonical-source-order"
                for row in mapping_rows
            ),
            "unresolved_source_club_count": len(unresolved_sources),
            "updated_player_slot_count": updated_players,
            "identity_retained_source_slot_count": sum(
                row["identity_retained_source_slot_count"] for row in mapping_rows
            ),
            "shared_player_slot_exclusion_count": len(relevant_shared_player_ids),
            "source_person_identity_conflict_count": len(person_identity_conflicts),
            "source_person_identity_unique_earliest_opening_fixture_resolution_count": sum(
                row["resolution"]
                == "unique-earliest-dated-opening-fixture-owner-retained-later-or-undated-claims-excluded"
                for row in person_identity_resolutions
            ),
            "repeated_source_row_resolution_count": len(repeated_row_resolutions),
            "calendar_binding_verified_count": 1 if calendar_binding is not None else 0,
        },
        "club_mappings": sorted(mapping_rows, key=lambda row: int(row["carrier_id"])),
        "unresolved_source_clubs": sorted(unresolved_sources, key=lambda row: str(row["source_club_name"])),
        "out_of_scope_source_clubs": sorted(out_of_scope_sources, key=lambda row: str(row["source_club_name"])),
        "unmatched_carrier_ids": unmatched_carriers,
        "carrier_allocation_gaps": allocation_gaps,
        "source_club_selection_allocation_translations": selection_allocation_translations,
        "source_club_selection_allocation_suppressions": selection_allocation_suppressions,
        "source_club_selection_suppressed_player_identity_quarantines": (
            suppressed_player_identity_quarantines
        ),
        "shared_player_ids_excluded_from_writes": relevant_shared_player_ids,
        "source_person_identity_conflicts": [
            {
                "normalised_name": key[0],
                "birth_date": key[1],
                "source_rows": [
                    {
                        "source_club_name": row["source_club_name"],
                        "source_row_sha256": row["source_row_sha256"],
                    }
                    for row in source_rows
                ],
            }
            for key, source_rows in sorted(person_identity_conflicts.items())
        ],
        "source_person_identity_resolutions": person_identity_resolutions,
        "repeated_source_row_resolutions": repeated_row_resolutions,
        "retained_native_person_candidate_conflicts": [
            {"normalised_name": key[0], "birth_date": key[1], "player_ids": ids}
            for key, ids in sorted(retained_candidate_conflicts.items())
        ],
        "non_blocking_warnings": [
            {
                "code": "shared-player-slots-retained",
                "count": len(relevant_shared_player_ids),
                "message": "Shared package player IDs were removed from writable capacity and retained unchanged.",
            },
            {
                "code": "ambiguous-source-people-skipped",
                "count": len(person_identity_conflicts),
                "message": "Normalized-name and birth-date collisions were skipped rather than assigned unsafe identities.",
            },
            {
                "code": "unique-earliest-opening-fixture-person-owners",
                "count": sum(
                    row["resolution"]
                    == "unique-earliest-dated-opening-fixture-owner-retained-later-or-undated-claims-excluded"
                    for row in person_identity_resolutions
                ),
                "message": "A unique earlier, dated opening-fixture claim owns a duplicate source person; later or undated claims were excluded.",
            },
        ],
        "hard_blockers": blocker_rows,
    }
    identified_slots = sum(
        rows[0][2]["facts"].get("source_identity") is not None for rows in planned.values()
    )
    if identified_slots:
        audit["coverage"]["updated_player_slots_with_provider_identity"] = identified_slots
    return template, audit


def _read(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourcePackageBuildError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or raw != package_v2.canonical_json_bytes(value):
        raise SourcePackageBuildError(f"{label} must be canonical UTF-8 JSON")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(package_v2.canonical_json_bytes(dict(value)))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-package", required=True, type=Path)
    parser.add_argument("--source-intake", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument(
        "--source-club-selection",
        type=Path,
        help="hash-bound explicit opening-date source-club projection; raw source intake remains immutable",
    )
    parser.add_argument(
        "--carrier-allocation",
        type=Path,
        help="canonical same-country carrier plan; without it only unique exact names are used",
    )
    parser.add_argument(
        "--opening-squad-preallocation",
        type=Path,
        help="hash-bound opening-XI-first projection consumed before carrier slot allocation",
    )
    parser.add_argument(
        "--calendar-binding-audit",
        type=Path,
        help="hash-bound calendar-overlay audit that may close only the calendar receipt gate",
    )
    parser.add_argument("--output-audit", required=True, type=Path)
    parser.add_argument("--output-draft-package", type=Path)
    parser.add_argument("--output-package", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        template = _read(args.template_package, "template package")
        intake = _read(args.source_intake, "source intake")
        registry = _read(args.registry, "fixed-carrier registry")
        allocation = (
            _read(args.carrier_allocation, "carrier allocation")
            if args.carrier_allocation is not None
            else None
        )
        source_club_selection = (
            _read(args.source_club_selection, "source-club selection")
            if args.source_club_selection is not None
            else None
        )
        opening_preallocation = (
            _read(args.opening_squad_preallocation, "opening squad preallocation")
            if args.opening_squad_preallocation is not None
            else None
        )
        calendar_binding_audit = (
            _read(args.calendar_binding_audit, "calendar binding audit")
            if args.calendar_binding_audit is not None
            else None
        )
        draft, audit = build_draft(
            template=template,
            source_intake=intake,
            registry=registry,
            carrier_allocation=allocation,
            source_club_selection=source_club_selection,
            opening_squad_preallocation=opening_preallocation,
            calendar_binding_audit=calendar_binding_audit,
        )
        _write(args.output_audit, audit)
        if args.output_draft_package is not None:
            _write(args.output_draft_package, draft)
        if args.output_package is not None:
            if audit["hard_blockers"]:
                raise SourcePackageBuildError(
                    "release package refused: hard blockers remain; inspect output audit"
                )
            _write(args.output_package, draft)
    except (SourcePackageBuildError, package_v2.PackageValidationError) as exc:
        print(f"season source package build error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(audit["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
