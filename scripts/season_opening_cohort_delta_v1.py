"""Source-bound opening-cohort edits with immutable-parent SOURCE reconstruction.

The ordinary child package carries
player facts and source artifacts. This provider reads one embedded typed plan,
validates it against an immutable registered parent, and replays standard actor
compilation plus the existing complete mode-1 order writer.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
import shutil
import tempfile
import csv
import re
from bs4 import BeautifulSoup

from app.fdi_indexed import IndexedFDIFile
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as packages
from scripts import season_release_registry_v1 as registry
from scripts import materialise_native_no_photo_v2 as no_photo
from scripts import season_opening_cohort_delta_core_v1 as core

SCHEMA = "pm99-opening-cohort-delta-v1"
PLAN_SCHEMA = core.SCHEMA
PROFILE_SCHEMA = "pm99-opening-cohort-delta-profile-assignment-v1"
MODE = "known-good-baseline-source-bound-opening-cohort-delta-v1"
PLAN_ARTIFACT_IDS = {"molde-opening-cohort-plan"}  # legacy preview ID; promoted IDs use opening-cohort-plan-<transaction>


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify_identity_crosswalks(plan: Mapping[str, Any]) -> None:
    sources = {row["id"]: row for row in plan.get("source_bindings", [])}
    for actor in plan.get("actors", []):
        crosswalk = actor.get("identity_crosswalk")
        if crosswalk is None:
            continue
        official = sources[crosswalk["official_profile_source_id"]]
        roster = sources[crosswalk["period_roster_source_id"]]
        official_path = core._safe_workspace_path(official["path"], "official identity profile")
        roster_path = core._safe_workspace_path(roster["path"], "period published-name row")
        official_text = " ".join(BeautifulSoup(official_path.read_bytes(), "html.parser").stripped_strings)
        claims = crosswalk["same_identity_fields"]
        assertions = crosswalk.get("official_profile_text_claims")
        if (not isinstance(assertions, list) or not assertions
                or not all(isinstance(value, str) and value.casefold() in official_text.casefold()
                           for value in assertions)
                or crosswalk["official_profile_full_name"].casefold() not in official_text.casefold()):
            raise core.CohortDeltaError("official profile does not substantiate the bound identity crosswalk")
        if not isinstance(crosswalk.get("period_row_text"), str) or _sha(crosswalk["period_row_text"].encode()) != crosswalk.get("period_row_sha256"):
            raise core.CohortDeltaError("period crosswalk row lacks its exact text/hash binding")
        if crosswalk["period_row_text"] not in roster_path.read_text(encoding="utf-8", errors="replace"):
            raise core.CohortDeltaError("period published row is absent from its bound source body")
        parsed = core._parse_footballsquads_row(crosswalk["period_row_text"], season_start_year=int(plan["parent"]["season"][:4]))
        parsed_claims = {"birth_date": parsed["birth_date"], "nationality": parsed["nationality"],
                         "height_cm": parsed["height_cm"], "weight_kg": parsed["weight_kg"],
                         "broad_position": parsed["primary_position"]}
        if (parsed["name"] != crosswalk["period_published_name"] or parsed_claims != claims):
            raise core.CohortDeltaError("period published row does not corroborate the official profile identity")


def _verify_fixture_source_membership(plan: Mapping[str, Any]) -> None:
    """Reparse source-bound fixtures and role rows from generic assertions."""
    sources = {row["id"]: row for row in plan.get("source_bindings", [])}
    assertions = plan.get("fixture_assertions")
    if not isinstance(assertions, list) or len(assertions) != len(plan.get("clubs", [])):
        raise core.CohortDeltaError("each opening club needs one typed raw-fixture assertion")
    by_club = {int(row.get("club_carrier_id", -1)): row for row in assertions}
    if len(by_club) != len(assertions):
        raise core.CohortDeltaError("fixture assertion club carriers must be unique")
    for club in plan.get("clubs", []):
        assertion = by_club.get(int(club["club_carrier_id"]))
        referenced = {club["source_fixture_binding_id"]}
        referenced.update(source_id for row in club.get("source_slot_rows", [])
                          for source_id in row.get("evidence_ids", []))
        if (assertion is None or assertion.get("source_binding_id") not in referenced
                or assertion.get("fixture_date") != club.get("fixture_date")):
            raise core.CohortDeltaError("raw fixture assertion differs from the typed club/date binding")
        source = sources.get(assertion.get("source_binding_id"))
        if source is None:
            raise core.CohortDeltaError("raw fixture assertion references no bound body")
        path = core._safe_workspace_path(source["path"], "opening fixture")
        body = path.read_bytes()
        if _sha(body) != source["sha256"] or assertion.get("source_body_sha256") != source["sha256"]:
            raise core.CohortDeltaError("fixture raw body hash differs from the exact source assertion")
        slots = club["source_slot_rows"]
        expected = [(str(row.get("provider_person_id")), str(row["source_name"]))
                    for row in assertion.get("starting_xi", [])]
        slot_identity = [(str(row.get("fiks_person_id", row.get("source_player_id"))),
                          str(row["source_name"])) for row in slots]
        if len(expected) != 11 or expected != slot_identity:
            raise core.CohortDeltaError("fixture assertion does not map all eleven typed slot identities")

        parser = assertion.get("parser")
        if parser == "match-html-team-list-v1":
            soup = BeautifulSoup(body, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            if any(text not in title for text in assertion.get("title_contains", [])):
                raise core.CohortDeltaError("raw match title/date does not match fixture assertion")
            label = assertion.get("club_label")
            teams = [node for node in soup.select(assertion.get("team_selector", "li"))
                     if label and label in node.get_text(" ", strip=True)
                     and assertion.get("team_starting_label", "") in node.get_text(" ", strip=True)]
            if len(teams) != 1:
                raise core.CohortDeltaError("raw match report does not identify one asserted club starting list")
            parsed = []
            for item in teams[0].select(".a_matchPlayerList .matchPlayerListItem"):
                link = item.select_one("a[href*='fiksId=']")
                if link:
                    pid = link.get("href", "").split("fiksId=", 1)[-1].split("&", 1)[0]
                    parsed.append((pid, link.get_text(" ", strip=True)))
            if parsed[:11] != expected:
                raise core.CohortDeltaError("raw match report starting XI IDs/names differ from typed assertions")
            for reserve in assertion.get("bench_members", []):
                hits = [index for index, row in enumerate(parsed)
                        if row == (str(reserve["provider_person_id"]), str(reserve["published_name"]))]
                if len(hits) != 1 or hits[0] < 11 or reserve.get("membership") != "bench":
                    raise core.CohortDeltaError("raw match report does not prove the asserted bench actor")
        elif parser == "lineup-json-v1":
            lineup = json.loads(body)
            fixtures = []
            def find_fixture(node: Any) -> None:
                if isinstance(node, dict):
                    if (str(node.get("source_match_id")) == str(assertion.get("source_match_id"))
                            and node.get("first_league_fixture_date") == assertion.get("fixture_date")
                            and node.get("source_selector", {}).get("transfermarkt_club_name") == assertion.get("club_label")):
                        fixtures.append(node)
                    for value in node.values(): find_fixture(value)
                elif isinstance(node, list):
                    for value in node: find_fixture(value)
            find_fixture(lineup)
            if len(fixtures) != 1:
                raise core.CohortDeltaError("lineup JSON does not contain one exact fixture/date/club record")
            fixture = fixtures[0]
            actual = [(str(row.get("source_player_id")), str(row.get("display_name")))
                      for row in fixture.get("starting_xi", [])]
            if actual != expected:
                raise core.CohortDeltaError("lineup JSON starting XI IDs/names differ from typed assertions")
            substitutes = [(str(row.get("source_player_id")), str(row.get("display_name")))
                           for row in fixture.get("substitutes", [])]
            for reserve in assertion.get("bench_members", []):
                if ((str(reserve["provider_person_id"]), str(reserve["published_name"])) not in substitutes
                        or reserve.get("membership") != "bench"):
                    raise core.CohortDeltaError("lineup JSON does not prove the asserted bench actor")
        else:
            raise core.CohortDeltaError("unsupported raw-fixture parser type")

    # A separate raw report may provide positive membership/profile-link proof
    # for a selected reserve. These claims are data-driven and hash-bound.
    for reserve in plan.get("reserve_identity_assertions", []):
        source = sources.get(reserve.get("source_binding_id"))
        if source is None:
            raise core.CohortDeltaError("reserve identity assertion has no bound source body")
        path = core._safe_workspace_path(source["path"], "reserve identity report")
        body = path.read_bytes()
        if _sha(body) != source["sha256"] or reserve.get("source_body_sha256") != source["sha256"]:
            raise core.CohortDeltaError("reserve identity raw body hash differs")
        if reserve.get("parser") == "profile-link-html-v1":
            soup = BeautifulSoup(body, "html.parser")
            provider_id = str(reserve["provider_person_id"])
            link = soup.find("a", href=lambda href: href and f"/spieler/{provider_id}" in href,
                             title=reserve["published_name"])
            if link is None or link.get_text(" ", strip=True) != reserve["published_name"]:
                raise core.CohortDeltaError("raw report lacks the exact reserve provider identity link")
        else:
            raise core.CohortDeltaError("unsupported reserve identity assertion parser")

    # Every supported published position option carries an exact row from its
    # source body, with role parsing based on the declared row format.
    for club in plan.get("clubs", []):
        for slot in club.get("source_slot_rows", []):
            for option in slot.get("published_position_options", []) or []:
                source_id = option.get("source_id")
                source = sources.get(source_id)
                row_binding = slot.get("published_position_row_bindings", {}).get(source_id)
                if source is None or not isinstance(row_binding, dict):
                    raise core.CohortDeltaError("published position option lacks a bound exact source row")
                path = core._safe_workspace_path(source["path"], "published position source")
                row_format = row_binding.get("row_format")
                if row_format == "preallocation-player-row-v1":
                    document = json.loads(path.read_text())
                    rows = [row for source_club in document.get("source_clubs", [])
                            for row in source_club.get("players", [])]
                    matches = [row for row in rows if row.get("source_row_sha256") == row_binding.get("row_sha256")]
                    if len(matches) != 1 or matches[0] != row_binding.get("source_row"):
                        raise core.CohortDeltaError("published annual position row/hash is absent or ambiguous")
                    position = matches[0].get("facts", {}).get("position")
                elif row_format == "footballsquads-csv-row-v1":
                    raw = path.read_text(encoding="utf-8", errors="replace")
                    text = row_binding.get("row_text")
                    if (not isinstance(text, str) or _sha(text.encode("utf-8")) != row_binding.get("row_sha256")
                            or text not in raw):
                        raise core.CohortDeltaError("published position CSV row text/hash is absent from its bound body")
                    position = core._parse_footballsquads_row(text, season_start_year=int(plan["parent"]["season"][:4]))["primary_position"]
                else:
                    raise core.CohortDeltaError("published position row binding uses an unsupported extraction format")
                if position != option.get("position") or row_binding.get("published_position") != position:
                    raise core.CohortDeltaError("published position option differs from its exact bound source row")

            position_binding = slot.get("source_position_row_binding")
            if position_binding is not None:
                source = sources.get(position_binding.get("source_binding_id"))
                if source is None or source.get("sha256") != position_binding.get("source_body_sha256"):
                    raise core.CohortDeltaError("slot source position binding is not pinned to a source body")
                path = core._safe_workspace_path(source["path"], "slot period-position source")
                raw = path.read_text(encoding="utf-8", errors="replace")
                row_text = position_binding.get("row_text")
                if (position_binding.get("row_format") != "footballsquads-csv-row-v1"
                        or not isinstance(row_text, str)
                        or _sha(row_text.encode("utf-8")) != position_binding.get("row_sha256")
                        or row_text not in raw):
                    raise core.CohortDeltaError("slot period position row text/hash is absent from its bound source")
                parsed = core._parse_footballsquads_row(row_text, season_start_year=int(plan["parent"]["season"][:4]))
                if parsed["primary_position"] != slot.get("source_position"):
                    raise core.CohortDeltaError("slot source position differs from its period CSV row")

            exception = slot.get("utility_exception")
            if exception is not None:
                sources_for_exception = {
                    "fixture": sources.get(exception.get("fixture_source_binding_id")),
                    "period": sources.get(exception.get("period_source_binding_id")),
                }
                if (exception.get("schema") != "pm99-opening-cohort-dated-grid-utility-exception-v1"
                        or exception.get("review_status") != "root-approved"
                        or any(source is None for source in sources_for_exception.values())):
                    raise core.CohortDeltaError("utility exception lacks its typed ROOT approval/source bindings")
                fixture_source = sources_for_exception["fixture"]
                period_source = sources_for_exception["period"]
                exception_text = exception.get("period_source_row_text")
                fixture_path = core._safe_workspace_path(fixture_source["path"], "utility exception fixture")
                period_path = core._safe_workspace_path(period_source["path"], "utility exception period row")
                if (_sha(fixture_path.read_bytes()) != exception.get("fixture_source_body_sha256")
                        or fixture_source["sha256"] != exception.get("fixture_source_body_sha256")
                        or _sha(period_path.read_bytes()) != exception.get("period_source_body_sha256")
                        or period_source["sha256"] != exception.get("period_source_body_sha256")
                        or not isinstance(exception_text, str)
                        or exception_text not in period_path.read_text(encoding="utf-8", errors="replace")
                        or _sha(exception_text.encode("utf-8")) != exception.get("period_source_row_sha256")):
                    raise core.CohortDeltaError("utility exception source body/row hash binding changed")
                period_row = core._parse_footballsquads_row(exception_text, season_start_year=int(plan["parent"]["season"][:4]))
                if (exception.get("fixture_date") != club.get("fixture_date")
                        or exception.get("provider_person_id") != str(slot.get("source_player_id"))
                        or exception.get("grid_position") != slot.get("slot_position")
                        or exception.get("grid_position") != slot.get("formation_grid_position")
                        or exception.get("grid_coordinates") != slot.get("grid_coordinates")
                        or exception.get("period_broad_position") != period_row["primary_position"]
                        or exception.get("preserved_native_broad_position") != period_row["primary_position"]
                        or exception.get("period_source_row_sha256") != position_binding.get("row_sha256")
                        or exception_text != position_binding.get("row_text")):
                    raise core.CohortDeltaError("utility exception differs from its typed fixture/period-position rows")

        grid_source_id = club.get("grid_source_binding_id")
        if grid_source_id:
            source = sources.get(grid_source_id)
            if source is None:
                raise core.CohortDeltaError("formation grid lacks a raw source binding")
            grid_path = core._safe_workspace_path(source["path"], "raw formation grid")
            raw_grid = grid_path.read_bytes()
            if _sha(raw_grid) != source["sha256"]:
                raise core.CohortDeltaError("raw formation grid body hash changed")
            soup = BeautifulSoup(raw_grid, "html.parser")
            nodes = {}
            for node in soup.select(".formation-player-container"):
                link = node.find("a", href=lambda href: href and "/spieler/" in href)
                if link is None:
                    continue
                provider_id = link["href"].split("/spieler/")[-1].split("/")[0]
                style = node.get("style", "")
                top = re.search(r"top:\s*([0-9.]+)%", style)
                left = re.search(r"left:\s*([0-9.]+)%", style)
                if top and left:
                    nodes[provider_id] = (link.get_text(" ", strip=True),
                                         {"left_percent": float(left.group(1)),
                                          "top_percent": float(top.group(1))})
            for slot in club.get("source_slot_rows", []):
                provider_id = str(slot.get("source_player_id"))
                observed = nodes.get(provider_id)
                if (observed is None or observed[0] != slot.get("source_name")
                        or observed[1] != slot.get("grid_coordinates")):
                    raise core.CohortDeltaError("raw formation grid identity/coordinates differ from typed slot")


def verify_native_slot_compatibility(jug: bytes, plan: Mapping[str, Any]) -> dict[str, Any]:
    """Read all typed XI carriers after replay and gate dated utility exceptions."""
    from scripts.season_exact_fifa_role_delta_v1 import compatible as fine_role_compatible
    rows = []
    for club in plan.get("clubs", []):
        for slot in club.get("source_slot_rows", []):
            carrier = int(slot["carrier_id"])
            snapshot = core.native_semantic_snapshot(jug, carrier)
            typed = slot.get("slot_position")
            native = snapshot["broad_position"]
            exception = slot.get("utility_exception")
            if native != typed:
                if not isinstance(exception, dict):
                    raise core.CohortDeltaError(
                        f"native XI broad position mismatch at carrier {carrier} lacks a bound utility exception")
                fine_role = exception.get("native_eligible_fine_role")
                if (exception.get("review_status") != "root-approved"
                        or exception.get("grid_position") != typed
                        or exception.get("preserved_native_broad_position") != native
                        or type(fine_role) is not int
                        or fine_role not in snapshot["fine_roles"]
                        or not fine_role_compatible(typed, fine_role)):
                    raise core.CohortDeltaError(
                        f"native XI utility exception is unsupported by its broad/fine role readback at carrier {carrier}")
                classification = "root-approved-dated-grid-utility-exception"
            else:
                if exception is not None:
                    raise core.CohortDeltaError("utility exception is attached to a natively compatible slot")
                classification = "native-broad-position-matches-typed-slot"
            rows.append({"club_carrier_id": int(club["club_carrier_id"]),
                         "carrier_id": carrier, "typed_slot_position": typed,
                         "native_broad_position": native,
                         "native_fine_roles": snapshot["fine_roles"],
                         "classification": classification})
    return {"slot_count": len(rows), "rows": rows,
            "utility_exception_count": sum(row["classification"] ==
                "root-approved-dated-grid-utility-exception" for row in rows)}


def _safe_relative(raw: Any) -> Path:
    if not isinstance(raw, str):
        raise core.CohortDeltaError("embedded plan path must be relative text")
    path = Path(raw)
    root = registry.ROOT.resolve()
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise core.CohortDeltaError("embedded plan path escapes workspace")
    resolved = (root / path).resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise core.CohortDeltaError("embedded plan path escapes workspace through symlink") from exc
    if not resolved.is_file():
        raise core.CohortDeltaError("embedded plan is not a regular file")
    return resolved


def embedded_plan(package: Mapping[str, Any]) -> tuple[dict[str, Any], Path, str]:
    """Find exactly one season-input artifact containing this provider's plan."""
    found = []
    for artifact in package.get("artifacts", []):
        if (not isinstance(artifact, dict) or artifact.get("kind") != "season-input"
                or not (artifact.get("id") in PLAN_ARTIFACT_IDS
                        or (isinstance(artifact.get("id"), str)
                            and artifact["id"].startswith("opening-cohort-plan-")))):
            continue
        relative, expected = artifact.get("relative_path"), artifact.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            continue
        path = _safe_relative(relative)
        body = path.read_bytes()
        if _sha(body) != expected:
            raise core.CohortDeltaError(f"package artifact changed: {artifact.get('id')}")
        try:
            document = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if document.get("schema") == PLAN_SCHEMA:
            found.append((document, path, expected, artifact.get("id")))
    if len(found) != 1:
        raise core.CohortDeltaError("package must bind exactly one opening-cohort plan artifact")
    plan, path, digest, _artifact_id = found[0]
    return plan, path, digest


def has_plan(package: Mapping[str, Any]) -> bool:
    return any(isinstance(a, dict) and a.get("kind") == "season-input"
               and (a.get("id") in PLAN_ARTIFACT_IDS
                    or (isinstance(a.get("id"), str) and a["id"].startswith("opening-cohort-plan-")))
               for a in package.get("artifacts", []))


def reject_factory_recipe(package: Mapping[str, Any]) -> None:
    """Compiler guard for any package carrying this provider's typed plan."""
    candidates = [a for a in package.get("artifacts", []) if isinstance(a, dict)
                  and a.get("kind") == "season-input"
                  and (a.get("id") in PLAN_ARTIFACT_IDS
                       or (isinstance(a.get("id"), str)
                           and a["id"].startswith("opening-cohort-plan-")))]
    if not candidates:
        return
    if len(candidates) != 1:
        raise core.CohortDeltaError("recipe carries multiple opening-cohort plan artifacts")
    plan, _path, _digest = embedded_plan(package)
    core.validate_plan(plan, verify_source_files=True)
    _verify_identity_crosswalks(plan)
    _verify_fixture_source_membership(plan)
    package_players = {row["id"]: row for row in package.get("players", [])}
    for actor in plan["actors"]:
        row = package_players.get(actor["recipe_player_id"])
        if (row is None or row.get("carrier_id") != actor["post_carrier_id"]
                or row.get("person_id") != actor.get("person_id", actor["player_id"])):
            raise core.CohortDeltaError("recipe actor differs from its immutable opening-cohort plan")


def verify_recipe(parent_release: Any, package: Mapping[str, Any], *,
                  expected_package_sha256: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bind the stored child recipe hash, embedded plan, and frozen parent."""
    observed = packages.sha256_bytes(packages.canonical_json_bytes(dict(package)))
    if observed != expected_package_sha256:
        raise core.CohortDeltaError("child recipe differs from stored compiler/locator SHA")
    plan, _path, plan_sha = embedded_plan(package)
    core.validate_plan(plan, verify_source_files=True)
    _verify_identity_crosswalks(plan)
    _verify_fixture_source_membership(plan)
    core.validate_parent(plan, parent_release)
    season = package.get("season")
    start_text, end_text = parent_release.season.split("-")
    parent_start = int(start_text)
    parent_end = (parent_start // 100) * 100 + int(end_text)
    if parent_end < parent_start:
        parent_end += 100
    if (not isinstance(season, dict) or season.get("start_year") != parent_start
            or season.get("end_year") != parent_end):
        raise core.CohortDeltaError("child recipe season differs from immutable parent")
    parent_package = json.loads(parent_release.package_path.read_text())
    parent_jug = (parent_release.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    parent_eq = (parent_release.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    country_codes = compiler._extract_country_codes_from_textos(
        parent_release.game_path / "DBDAT/TEXTOS.PKF")
    recomputed = core.bind_same_person_preimages(parent_package, parent_jug, parent_eq, plan, country_codes)
    if recomputed != plan:
        raise core.CohortDeltaError("stored typed plan differs from recomputed exact parent preimages")
    bound = recomputed
    _verify_recipe_field_mask(parent_package, package, parent_jug, bound, country_codes)
    by_id = {row["id"]: row for row in package.get("players", [])}
    for actor in bound["actors"]:
        row = by_id.get(actor["recipe_player_id"])
        if row is None or row.get("carrier_id") != actor["post_carrier_id"]:
            raise core.CohortDeltaError("stored child recipe actor carrier differs from bound plan")
        if row.get("person_id") != actor.get("person_id", actor["player_id"]):
            raise core.CohortDeltaError("stored child recipe actor person differs from bound plan")
    return bound, {"child_recipe_sha256": observed, "plan_sha256": plan_sha,
                   "parent_release_id": parent_release.release_id,
                   "parent_package_sha256": plan["parent"]["package_sha256"],
                   "parent_jug_sha256": plan["parent"]["native_sha256"]["JUG98030.FDI"],
                   "parent_eq_sha256": plan["parent"]["native_sha256"]["EQ98030.FDI"]}


def _verify_recipe_field_mask(parent_package: Mapping[str, Any],
                              child_package: Mapping[str, Any],
                              parent_jug: bytes, plan: Mapping[str, Any],
                              country_codes: Mapping[str, int]) -> None:
    """Reject child-recipe edits outside selected actors and roster lists."""
    fixed = ("calendar", "managers", "migration", "schema_version", "scope", "season")
    if set(child_package) != set(parent_package):
        raise core.CohortDeltaError("opening-cohort recipe changed top-level package shape")
    for key in fixed:
        if child_package.get(key) != parent_package.get(key):
            raise core.CohortDeltaError(f"opening-cohort recipe changed closed top-level field: {key}")
    if child_package.get("package_id") == parent_package.get("package_id"):
        raise core.CohortDeltaError("opening-cohort child package_id must be distinct from parent")

    # Parent provenance is append-only, except the legacy cohort proof/artifact
    # superseded by the single typed plan bound below.
    groups = ((parent_package.get("artifacts", []), child_package.get("artifacts", []), "artifact"),
              (parent_package.get("sources", []), child_package.get("sources", []), "source"),
              (parent_package.get("proofs", []), child_package.get("proofs", []), "proof"))
    for original, revised, label in groups:
        after = {row["id"]: row for row in revised}
        for row in original:
            if row["id"].startswith(("molde-opening-cohort-plan", "proof-molde-opening-cohort")):
                continue
            if after.get(row["id"]) != row:
                raise core.CohortDeltaError(f"opening-cohort recipe modified or removed parent {label}: {row['id']}")

    parent_assets, child_assets = parent_package.get("assets", {}), child_package.get("assets", {})
    if set(parent_assets) != set(child_assets):
        raise core.CohortDeltaError("opening-cohort recipe changed asset sections")
    for key in set(parent_assets) - {"portraits"}:
        if child_assets[key] != parent_assets[key]:
            raise core.CohortDeltaError(f"opening-cohort recipe changed closed asset section: {key}")

    actors = list(plan["actors"])
    allowed_ids = {str(actor["recipe_player_id"]) for actor in actors}
    allowed_carriers = {int(actor[field]) for actor in actors
                        for field in ("pre_carrier_id", "post_carrier_id")}
    before_players = {str(row["id"]): row for row in parent_package.get("players", [])}
    after_players = {str(row["id"]): row for row in child_package.get("players", [])}
    allowed_ids.update(str(row["id"]) for row in parent_package.get("players", [])
                       if int(row["carrier_id"]) in allowed_carriers)
    for player_id in set(before_players) | set(after_players):
        if player_id not in allowed_ids and before_players.get(player_id) != after_players.get(player_id):
            raise core.CohortDeltaError(f"opening-cohort recipe changed unselected player row: {player_id}")

    expected_same, _ = core.same_person_recipe_postimages(
        parent_package, parent_jug, plan, country_codes)
    expected_same_by_id = {str(row["id"]): row for row in expected_same}
    rating_source = next((row for row in plan.get("source_bindings", [])
                          if row.get("id") == "rating_output"), None)
    rating_rows = {}
    if rating_source:
        rating_path = core._safe_workspace_path(rating_source["path"], "rating output")
        rating_doc = json.loads(rating_path.read_text())
        rating_rows = {str(row.get("person_id")): row for row in rating_doc.get("rows", [])}
    for actor in actors:
        player_id = str(actor["recipe_player_id"])
        row = after_players.get(player_id)
        if row is None or int(row.get("carrier_id", -1)) != int(actor["post_carrier_id"]):
            raise core.CohortDeltaError(f"opening-cohort actor row/carrier differs: {player_id}")
        if row.get("person_id") != actor.get("person_id", actor["player_id"]):
            raise core.CohortDeltaError(f"opening-cohort actor identity differs: {player_id}")
        if actor["identity_policy"] == "same-person-preserve":
            if expected_same_by_id.get(player_id) != row:
                raise core.CohortDeltaError(f"same-person actor recipe differs from frozen native transfer: {player_id}")
        else:
            facts = actor.get("facts_binding", {})
            recipe_facts = row.get("facts", {})
            for field in ("birth_date", "fine_roles", "height_cm", "nationality",
                          "primary_position", "weight_kg"):
                expected = facts.get(field)
                if isinstance(expected, str) and expected.startswith("preserve destination fallback"):
                    continue
                if recipe_facts.get(field) != expected:
                    raise core.CohortDeltaError(f"new actor fact differs from bound source: {player_id}.{field}")
            if row.get("name") != actor.get("native_display_name"):
                raise core.CohortDeltaError(f"new actor display name differs from bound plan: {player_id}")
            rating = rating_rows.get(str(actor.get("player_id")))
            if rating is not None and row.get("ratings") != rating.get("ratings"):
                raise core.CohortDeltaError(f"new actor rating differs from bound rating source: {player_id}")

    before_clubs = {str(row["id"]): row for row in parent_package.get("clubs", [])}
    after_clubs = {str(row["id"]): row for row in child_package.get("clubs", [])}
    if set(before_clubs) != set(after_clubs):
        raise core.CohortDeltaError("opening-cohort recipe added or removed a club")
    target_club_ids = {str(next(c["id"] for c in parent_package["clubs"]
                                if int(c["carrier_id"]) == int(actor["club_carrier_id"])))
                       for actor in actors}
    for club_id, before in before_clubs.items():
        after = after_clubs[club_id]
        if club_id not in target_club_ids:
            if after != before:
                raise core.CohortDeltaError(f"opening-cohort recipe changed unselected club: {club_id}")
            continue
        for key in set(before) | set(after):
            if key != "roster_player_ids" and before.get(key) != after.get(key):
                raise core.CohortDeltaError(f"opening-cohort recipe changed closed target club field: {club_id}.{key}")
        for row_id in after.get("roster_player_ids", []):
            player = after_players.get(str(row_id))
            if player is None or str(player.get("club_id")) != club_id:
                raise core.CohortDeltaError(f"target club roster references a wrong club actor: {club_id}.{row_id}")

    before_portraits = {str(row.get("player_id")): row for row in parent_assets.get("portraits", [])}
    after_portraits = {str(row.get("player_id")): row for row in child_assets.get("portraits", [])}
    for player_id in set(before_portraits) | set(after_portraits):
        if player_id not in allowed_ids and before_portraits.get(player_id) != after_portraits.get(player_id):
            raise core.CohortDeltaError(f"opening-cohort recipe changed unselected portrait: {player_id}")
    for actor in actors:
        row = after_portraits.get(str(actor["recipe_player_id"]))
        if not isinstance(row, dict) or row.get("status") != "native-no-photo":
            raise core.CohortDeltaError("selected actor portrait is not explicitly deactivated")


def _load_profile_plan(profile_plan: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    if profile_plan.get("schema") != PROFILE_SCHEMA:
        raise core.CohortDeltaError("profile assignment plan schema differs")
    recipe_binding = profile_plan.get("child_recipe")
    plan_binding = profile_plan.get("typed_plan")
    if not isinstance(recipe_binding, dict) or not isinstance(plan_binding, dict):
        raise core.CohortDeltaError("profile plan must bind a child recipe and typed source plan")
    recipe_path = _safe_relative(recipe_binding.get("path"))
    plan_path = _safe_relative(plan_binding.get("path"))
    recipe_body, plan_body = recipe_path.read_bytes(), plan_path.read_bytes()
    if _sha(recipe_body) != recipe_binding.get("sha256") or _sha(plan_body) != plan_binding.get("sha256"):
        raise core.CohortDeltaError("profile plan child recipe or typed plan SHA changed")
    package = json.loads(recipe_body)
    typed_plan = json.loads(plan_body)
    embedded, embedded_path, embedded_sha = embedded_plan(package)
    if embedded_sha != plan_binding["sha256"] or embedded != typed_plan:
        raise core.CohortDeltaError("child package embedded plan differs from the stored profile plan")
    return package, typed_plan, recipe_path, plan_path


def _check_profile_parent(release: Any, profile_plan: Mapping[str, Any]) -> None:
    parent = profile_plan.get("parent")
    if not isinstance(parent, dict) or (parent.get("season"), parent.get("release_id")) != (
            release.season, release.release_id):
        raise core.CohortDeltaError("profile plan immutable parent identity differs")
    if parent.get("package_sha256") != registry.sha256_file(release.package_path):
        raise core.CohortDeltaError("profile plan parent recipe SHA differs")
    for filename, expected in parent.get("native_sha256", {}).items():
        if registry.sha256_file(release.game_path / "DBDAT" / filename) != expected:
            raise core.CohortDeltaError(f"profile plan parent native SHA differs: {filename}")


def filename(profile_plan: Mapping[str, Any]) -> str:
    tx = profile_plan.get("transaction_id")
    if not isinstance(tx, str) or not tx or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in tx):
        raise core.CohortDeltaError("profile plan transaction ID is invalid")
    return f"opening-cohort-delta-{tx}.json"


def verify(parent_release: Any, profile_plan: Mapping[str, Any]) -> dict[str, Any]:
    """Publisher quality-dispatch entry: verify immutable source and recipe pins."""
    _check_profile_parent(parent_release, profile_plan)
    package, plan, recipe_path, plan_path = _load_profile_plan(profile_plan)
    bound, receipt = verify_recipe(parent_release, package,
                                   expected_package_sha256=profile_plan["child_recipe"]["sha256"])
    if bound != plan:
        raise core.CohortDeltaError("publisher plan and embedded typed plan are not identical")
    if profile_plan.get("expected_post_jug_sha256"):
        reconstructed, source_receipt = reconstruct_from_parent(
            parent_release, package,
            expected_package_sha256=profile_plan["child_recipe"]["sha256"])
        if _sha(reconstructed) != profile_plan["expected_post_jug_sha256"]:
            raise core.CohortDeltaError("immutable-parent reconstruction differs from planned JUG postimage")
        receipt["source_reconstruction"] = source_receipt
    receipt.update({"child_recipe_path": str(recipe_path), "typed_plan_path": str(plan_path),
                    "profile_transaction_id": profile_plan.get("transaction_id")})
    return receipt


def verify_source(parent_release: Any, child_release: Any,
                  stored_profile_plan: Mapping[str, Any]) -> dict[str, Any]:
    """Exact SOURCE gate: recompile stored child recipe from its immutable parent."""
    _check_profile_parent(parent_release, stored_profile_plan)
    child_locator = getattr(child_release, "locator", {}) or {}
    stored_path = child_locator.get("sourced_profile_assignment_plan_path")
    if not stored_path:
        raise core.CohortDeltaError("child release has no stored opening-cohort profile plan locator")
    stored_plan_path = _safe_relative(stored_path)
    persisted = json.loads(stored_plan_path.read_text())
    if persisted != dict(stored_profile_plan):
        raise core.CohortDeltaError("SOURCE profile plan differs from its stored release plan")
    child_package_sha = registry.sha256_file(child_release.package_path)
    if child_package_sha != stored_profile_plan.get("child_recipe", {}).get("sha256"):
        raise core.CohortDeltaError("SOURCE child recipe bytes differ from stored profile plan")
    package = json.loads(child_release.package_path.read_text())
    reconstructed, receipt = reconstruct_from_parent(
        parent_release, package, expected_package_sha256=child_package_sha)
    child_jug = (child_release.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    child_eq = (child_release.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    parent_eq = (parent_release.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    if reconstructed != child_jug:
        raise core.CohortDeltaError("SOURCE immutable-parent JUG reconstruction differs from registered child")
    if child_eq != parent_eq:
        raise core.CohortDeltaError("SOURCE child EQ differs from the preserved opening-cohort parent")
    receipt["source_child_release_id"] = child_release.release_id
    receipt["source_child_jug_sha256"] = _sha(child_jug)
    receipt["source_child_eq_sha256"] = _sha(child_eq)
    receipt["stored_profile_plan_sha256"] = _sha(stored_plan_path.read_bytes())
    return receipt


def reconstruction(previous_release: Any, release_id: str, *,
                    minimum_free_bytes: int = 8 * 1024**3) -> dict[str, Any] | None:
    """Create B from the immutable typed-plan parent, using A as its pin.

    This intentionally follows the registered release SOURCE construction
    path. It never treats a nonexistent requested child as an input to verify.
    """
    from scripts import season_disk_budget_v1 as disk_budget
    from scripts import season_pipeline_v2 as pipeline
    from scripts import publish_historical_role_delta_v1 as publisher
    disk_budget.validate_reserve(minimum_free_bytes)
    receipt_path = getattr(previous_release, "compiler_receipt_path", None)
    if receipt_path is None:
        return None
    compiler_receipt = pipeline.read_json_file(receipt_path)
    if compiler_receipt.get("compilation_mode") != MODE:
        return None
    relative = (getattr(previous_release, "locator", {}) or {}).get(
        "sourced_profile_assignment_plan_path")
    if not relative:
        raise core.CohortDeltaError("opening-cohort SOURCE baseline has no stored profile plan")
    plan_path = _safe_relative(relative)
    profile_plan = pipeline.read_json_file(plan_path)
    if profile_plan.get("schema") != PROFILE_SCHEMA:
        raise core.CohortDeltaError("opening-cohort SOURCE stored profile plan has another schema")
    if (plan_path != (previous_release.package_path.parent / filename(profile_plan)).resolve()
            or registry.sha256_file(plan_path) != compiler_receipt.get("original_profile_assignment_plan_sha256")):
        raise core.CohortDeltaError("opening-cohort SOURCE profile plan locator/hash differs from compiler receipt")
    if registry.locator_path(previous_release.season, release_id).exists():
        raise core.CohortDeltaError("opening-cohort SOURCE target release ID is already registered")
    workspace = registry.ROOT / ".local/historical-role-deltas-v1" / previous_release.season / release_id
    destination = registry.locator_path(previous_release.season, release_id).parent
    if workspace.exists() or destination.exists():
        raise core.CohortDeltaError("opening-cohort SOURCE target workspace or release locator already exists")

    parent = registry.load_registered_release(profile_plan["parent"]["season"],
                                              profile_plan["parent"]["release_id"])
    _check_profile_parent(parent, profile_plan)
    # A is itself verified against the immutable parent before using its
    # package/source metadata to create B.
    verify_source(parent, previous_release, profile_plan)
    expected_recipe = bind(json.loads(parent.package_path.read_text()), profile_plan)
    if json.loads(previous_release.package_path.read_text()) != expected_recipe:
        raise core.CohortDeltaError("edited opening-cohort child recipe cannot be silently reconstructed")
    descriptor_path = previous_release.package_path.parent / "role-delta-input.json"
    expected_descriptor = {
        "season": parent.season,
        "release_id": parent.release_id,
        "package_sha256": profile_plan["parent"]["package_sha256"],
        "jug_sha256": profile_plan["parent"]["native_sha256"]["JUG98030.FDI"],
        "updates": [], "unresolved": [],
    }
    if not descriptor_path.is_file() or pipeline.read_json_file(descriptor_path) != expected_descriptor:
        raise core.CohortDeltaError("opening-cohort SOURCE inert parent descriptor differs")
    publisher.publish(parent.season, descriptor_path, release_id=release_id,
                      source_release_id=parent.release_id,
                      profile_assignment_plan_path=plan_path,
                      minimum_free_bytes=minimum_free_bytes)
    rebuilt = registry.load_registered_release(parent.season, release_id)
    inventory = pipeline.read_json_file(previous_release.inventory_path)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, inventory)
    if rebuilt.package_path.read_bytes() != previous_release.package_path.read_bytes():
        raise core.CohortDeltaError("opening-cohort SOURCE whole recipe differs")
    return {"season": rebuilt.season, "release_id": rebuilt.release_id,
            "source_release_id": parent.release_id, "compilation_mode": MODE,
            "complete_game_inventory_identical": True,
            "complete_recipe_identical": True,
            "minimum_free_bytes": minimum_free_bytes,
            "source_reconstruction": verify_source(parent, rebuilt, profile_plan)}


def bind(parent_package: Mapping[str, Any], profile_plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return the pinned ordinary child recipe for existing publisher dispatch."""
    package, plan, _recipe_path, _plan_path = _load_profile_plan(profile_plan)
    parent = profile_plan["parent"]
    if packages.sha256_bytes(packages.canonical_json_bytes(dict(parent_package))) != parent["package_sha256"]:
        raise core.CohortDeltaError("publisher parent package differs from profile plan")
    if embedded_plan(package)[0] != plan:
        raise core.CohortDeltaError("pinned child package does not contain its typed plan")
    return package


def apply(parent_jug: bytes, parent_eq: bytes, profile_plan: Mapping[str, Any]
          ) -> tuple[bytes, bytes]:
    """Existing publisher API; reconstruct both native outputs from pinned parent."""
    package, _plan, _recipe_path, _plan_path = _load_profile_plan(profile_plan)
    release = registry.load_registered_release(profile_plan["parent"]["season"],
                                               profile_plan["parent"]["release_id"])
    expected_jug = (release.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    expected_eq = (release.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    if parent_eq != expected_eq:
        raise core.CohortDeltaError("publisher native preimage differs from immutable registered parent")
    output_jug, _receipt = reconstruct_from_parent(
        release, package, expected_package_sha256=profile_plan["child_recipe"]["sha256"])
    expected = profile_plan.get("expected_post_jug_sha256")
    if expected and _sha(output_jug) != expected:
        raise core.CohortDeltaError("publisher replay JUG differs from planned exact postimage")
    if parent_jug not in (expected_jug, output_jug):
        raise core.CohortDeltaError("publisher native preimage differs from immutable registered parent")
    return output_jug, parent_eq


def apply_profile_minifoto(original_archive: bytes, profile_plan: Mapping[str, Any]
                            ) -> tuple[bytes, dict[int, list[int]]]:
    package, plan, _recipe_path, _plan_path = _load_profile_plan(profile_plan)
    return apply_minifoto(package, plan, original_archive)


def apply_compiled(parent_release: Any, package: Mapping[str, Any], *,
                   compiled_jug: bytes, compiled_eq: bytes,
                   expected_package_sha256: str) -> tuple[bytes, dict[str, Any]]:
    """Shared build/SOURCE callback after ordinary player and EQ compilation."""
    bound, receipt = verify_recipe(parent_release, package,
                                   expected_package_sha256=expected_package_sha256)
    parent_package = json.loads(parent_release.package_path.read_text())
    parent_jug = (parent_release.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    parent_eq = (parent_release.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    if compiled_eq != parent_eq:
        raise core.CohortDeltaError("opening-cohort provider does not authorize EQ changes")
    country_codes = compiler._extract_country_codes_from_textos(
        parent_release.game_path / "DBDAT/TEXTOS.PKF")
    output, callback_receipt = core.canonical_apply_after_standard_actor_compile(
        parent_jug, compiled_jug, compiled_eq, bound, country_codes)
    receipt["native_slot_compatibility"] = verify_native_slot_compatibility(output, bound)
    receipt["callback"] = callback_receipt
    receipt["post_jug_sha256"] = _sha(output)
    receipt["parent_recipe_sha256"] = registry.sha256_file(parent_release.package_path)
    return output, receipt


def replay(package: Mapping[str, Any], *, compiled_jug: bytes, compiled_eq: bytes,
           parent_jug: bytes, parent_eq: bytes,
           expected_package_sha256: str) -> tuple[bytes, dict[str, Any]]:
    """Compiler/SOURCE hook resolving the immutable parent from its stored plan."""
    plan, _path, _sha256 = embedded_plan(package)
    release = registry.load_registered_release(plan["parent"]["season"], plan["parent"]["release_id"])
    frozen_jug = (release.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    frozen_eq = (release.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    if parent_jug != frozen_jug or parent_eq != frozen_eq:
        raise core.CohortDeltaError("compiler SOURCE parent native bytes differ from embedded immutable parent")
    return apply_compiled(release, package, compiled_jug=compiled_jug,
                          compiled_eq=compiled_eq,
                          expected_package_sha256=expected_package_sha256)


def reconstruct_from_parent(parent_release: Any, package: Mapping[str, Any], *,
                            expected_package_sha256: str) -> tuple[bytes, dict[str, Any]]:
    """SOURCE leg: compile ordinary actor rows from the immutable parent, then replay plan."""
    _bound, receipt = verify_recipe(parent_release, package,
                                    expected_package_sha256=expected_package_sha256)
    parent_jug = (parent_release.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    parent_eq = (parent_release.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    country_codes = compiler._extract_country_codes_from_textos(
        parent_release.game_path / "DBDAT/TEXTOS.PKF")
    plan, _plan_path, _plan_sha = embedded_plan(package)
    selected_ids = {actor["recipe_player_id"] for actor in plan["actors"]}
    selected_rows = {row["id"]: row for row in package["players"] if row["id"] in selected_ids}
    if set(selected_rows) != selected_ids:
        raise core.CohortDeltaError("SOURCE child recipe does not contain every typed actor row")
    selected_club_ids = {row["club_id"] for row in selected_rows.values()}
    selected_clubs = []
    for club in package["clubs"]:
        if club["id"] not in selected_club_ids:
            continue
        selected_clubs.append({**club, "roster_player_ids": [row_id for row_id, row in selected_rows.items()
                                                               if row["club_id"] == club["id"]]})
    compile_input = {"players": list(selected_rows.values()), "clubs": selected_clubs}
    replacements, handling, *_ = compiler._player_replacements(
        package=compile_input, jug_data=parent_jug, country_codes=country_codes,
        club_modes={club_id: 1 for club_id in selected_club_ids})
    if set(replacements) != {int(row["carrier_id"]) for row in selected_rows.values()}:
        raise core.CohortDeltaError("SOURCE compiler did not emit exactly the selected actor carriers")
    if handling:
        raise core.CohortDeltaError("opening-cohort SOURCE candidate has unsupported handling writes")
    compiled_jug = compiler._rebuild_indexed(
        parent_jug, IndexedFDIFile.from_bytes(parent_jug), replacements)
    output, replay_receipt = apply_compiled(
        parent_release, package, compiled_jug=compiled_jug, compiled_eq=parent_eq,
        expected_package_sha256=expected_package_sha256)
    receipt["reconstruction"] = replay_receipt
    receipt["ordinary_player_replacement_carriers"] = sorted(replacements)
    return output, receipt


def apply_no_photo(package: Mapping[str, Any], game_tree: Path) -> dict[str, Any]:
    """Use existing no-photo materializer as the publisher quality/asset stage."""
    return no_photo.materialise_native_no_photo(package=package, game_tree=game_tree)


def apply_minifoto(package: Mapping[str, Any], plan: Mapping[str, Any], original_archive: bytes
                   ) -> tuple[bytes, dict[int, list[int]]]:
    """Publisher byte API: route selected no-photo actors through existing archive helper."""
    selected = {int(actor["post_carrier_id"]) for actor in plan["actors"]}
    portraits = {row["player_id"]: row["status"] for row in package["assets"]["portraits"]}
    actor_by_recipe = {actor["recipe_player_id"]: actor for actor in plan["actors"]}
    package_players = {row["id"]: row for row in package["players"]}
    if set(actor_by_recipe) - set(package_players):
        raise core.CohortDeltaError("no-photo package is missing a typed actor")
    for recipe_id, actor in actor_by_recipe.items():
        if portraits.get(recipe_id) != "native-no-photo":
            raise core.CohortDeltaError("opening-cohort actors require an explicit native-no-photo package row")
        if int(package_players[recipe_id]["carrier_id"]) != int(actor["post_carrier_id"]):
            raise core.CohortDeltaError("no-photo actor carrier differs from the typed plan")
    from scripts import season_duplicate_ownership_delta_v1 as existing_portrait_writer
    after, offsets = existing_portrait_writer.no_photo_archive(original_archive, selected)
    if set(offsets) != selected:
        raise core.CohortDeltaError("existing no-photo writer returned an incomplete carrier receipt")
    return after, offsets
