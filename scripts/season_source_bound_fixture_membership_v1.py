"""Private integration prototype for source-bound opening XI/owner updates.

This is QA-only. It consumes a fully pinned source/native crossmatch and two
canonical recipe layers, then returns in-memory EQ/JUG and recipe postimages.
It has no publication, runner, filesystem write, or registry operation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any, Mapping

from bs4 import BeautifulSoup

from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import read_initial_order
from scripts import season_contextual_tactics_v1 as contextual
from scripts import season_opening_order_repair_v1 as order_repair
from scripts import season_opening_identity_exchange_v1 as identity_exchange
from scripts import season_package_v2 as package_v2
from scripts import season_release_registry_v1 as registry
from scripts import season_roster_visibility_v1 as visibility

from scripts.season_roster_membership_payload_core_v1 import (
    MembershipPayloadError,
    _read_rosters,
    reassign_memberships,
)


class OpeningXICompositionError(ValueError):
    """The source, parent, package layers, or native before-image is stale."""


PLAN_ARTIFACT_ID = "source-bound-opening-fixture-membership-plan"


def embedded_source_plan(package: Mapping[str, Any], package_path: Path) -> tuple[dict[str, Any], Path, str]:
    """Load one child-owned, hash-bound plan artifact without path traversal."""
    rows = [row for row in package.get("artifacts", []) if row.get("id") == PLAN_ARTIFACT_ID]
    if len(rows) != 1:
        raise OpeningXICompositionError("child package must bind exactly one source fixture membership plan")
    relative = rows[0].get("relative_path")
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise OpeningXICompositionError("source fixture plan path must stay package-relative")
    path = package_path.parent / relative
    cursor = package_path.parent
    for part in Path(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise OpeningXICompositionError("source fixture plan may not traverse symlinks")
    raw = path.read_bytes()
    digest = _sha(raw)
    if digest != rows[0].get("sha256"):
        raise OpeningXICompositionError("child-owned source fixture plan hash differs")
    try:
        plan = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpeningXICompositionError("source fixture plan is not canonical JSON") from exc
    if not isinstance(plan, dict):
        raise OpeningXICompositionError("source fixture plan root must be an object")
    return plan, path, digest


def has_plan(package: Mapping[str, Any]) -> bool:
    return any(row.get("id") == PLAN_ARTIFACT_ID for row in package.get("artifacts", []))


def _layer_path(package: Mapping[str, Any], package_path: Path, suffix: str) -> Path:
    rows = [row for row in package.get("artifacts", [])
            if str(row.get("relative_path", "")).endswith(suffix)]
    if len(rows) != 1:
        raise OpeningXICompositionError(f"recipe layer must bind exactly one {suffix} artifact")
    relative = Path(rows[0]["relative_path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise OpeningXICompositionError("recipe layer artifact path escapes its package")
    path = package_path.parent / relative
    if not path.is_file() or _sha(path.read_bytes()) != rows[0].get("sha256"):
        raise OpeningXICompositionError(f"recipe layer artifact hash differs: {suffix}")
    return path


def replay_package(package: Mapping[str, Any], package_path: Path, *,
                   compiled_eq: bytes, compiled_jug: bytes) -> dict[str, Any]:
    """Common compiler hook: bind child plan, reload immutable parent, replay SOURCE."""
    source_doc, _source_path_value, source_plan_sha = embedded_source_plan(package, package_path)
    parent_ref = source_doc.get("parent")
    if not isinstance(parent_ref, dict):
        raise OpeningXICompositionError("source plan lacks an exact immutable parent")
    parent = registry.load_registered_release(parent_ref.get("season"), parent_ref.get("release_id"))
    if parent.manifest_sha256 != parent_ref.get("manifest_sha256"):
        raise OpeningXICompositionError("registered parent release manifest differs from source plan")
    parent_main = json.loads(parent.package_path.read_bytes())
    parent_overlay_path = _layer_path(parent_main, parent.package_path, "english-season-package.json")
    parent_english = json.loads(parent_overlay_path.read_bytes())
    candidate_overlay_path = _layer_path(package, package_path, "english-season-package.json")
    candidate_english = json.loads(candidate_overlay_path.read_bytes())
    receipt = verify_source_candidate(
        parent, parent_main, parent_english,
        (parent.game_path / "DBDAT/EQ98030.FDI").read_bytes(),
        (parent.game_path / "DBDAT/JUG98030.FDI").read_bytes(),
        package, candidate_english, compiled_eq, compiled_jug, source_doc)
    receipt["source_plan_sha256"] = source_plan_sha
    receipt["source_plan_artifact_id"] = PLAN_ARTIFACT_ID
    return receipt


def verify_source_candidate(parent: Any, parent_main: Mapping[str, Any],
                            parent_english: Mapping[str, Any], parent_eq: bytes,
                            parent_jug: bytes, candidate_main: Mapping[str, Any],
                            candidate_english: Mapping[str, Any], candidate_eq: bytes,
                            candidate_jug: bytes, source_doc: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct a candidate from the immutable parent and compare all postimages.

    This is the SOURCE leg: no candidate native output is fed back as an input
    to reconstruction. The child plan is separately loaded via
    ``embedded_source_plan`` by the common compiler dispatch.
    """
    replay = compose_in_memory(parent, parent_main, parent_english, parent_eq,
                               parent_jug, source_doc)
    expected = replay["outputs"]
    def without_plan_artifact(package: Mapping[str, Any]) -> dict[str, Any]:
        normalized = copy.deepcopy(dict(package))
        artifacts = normalized.get("artifacts", [])
        normalized["artifacts"] = [row for row in artifacts if row.get("id") != PLAN_ARTIFACT_ID]
        if len(artifacts) - len(normalized["artifacts"]) != 1:
            raise OpeningXICompositionError("candidate recipe must contain exactly one source plan artifact")
        return normalized
    if (package_v2.canonical_json_bytes(without_plan_artifact(candidate_main)) !=
            package_v2.canonical_json_bytes(expected["main_package"])):
        raise OpeningXICompositionError("candidate main recipe does not equal parent/source reconstruction")
    if (package_v2.canonical_json_bytes(dict(candidate_english)) !=
            package_v2.canonical_json_bytes(expected["english_package"])):
        raise OpeningXICompositionError("candidate English recipe does not equal parent/source reconstruction")
    if candidate_eq != expected["eq"] or candidate_jug != expected["jug"]:
        raise OpeningXICompositionError("candidate native postimage differs from parent/source reconstruction")
    return {"schema_version": "pm99-source-fixture-membership-source-replay-v1",
            "state": "verified-exact-parent-source-reconstruction",
            "parent_release_id": parent.release_id,
            "reconstructed_eq_sha256": _sha(expected["eq"]),
            "reconstructed_jug_sha256": _sha(expected["jug"]),
            "source_bindings": replay["source_bindings"],
            "raw_report_reconstruction": replay["raw_report_reconstruction"],
            "unresolved_identity_candidates": [candidate
                for receipt in replay["raw_report_reconstruction"]
                for candidate in receipt["identity_review_exceptions"]],
            "identity_disposition_remains_open": any(
                row.get("status", "").startswith("unresolved-confirmed-")
                for fixture in replay["raw_report_reconstruction"]
                for row in fixture["identity_review_exceptions"]),
            "membership_stage_unselected_eq_payloads_byte_identical": True,
            "plan_semantics_contain_no_extractor_or_code_version": True}


def _package_validation_state(package: Mapping[str, Any]) -> str | None:
    try:
        package_v2.validate_package(copy.deepcopy(dict(package)), strict=True)
    except package_v2.PackageValidationError as exc:
        return str(exc)
    return None


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _source_path(raw: str) -> Path:
    if not isinstance(raw, str):
        raise OpeningXICompositionError("source path must be workspace-relative text")
    path = Path(raw)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise OpeningXICompositionError("source path escapes the workspace")
    resolved = (registry.ROOT / path).resolve(strict=True)
    try:
        resolved.relative_to(registry.ROOT.resolve())
    except ValueError as exc:
        raise OpeningXICompositionError("source path escapes through a symlink") from exc
    cursor = registry.ROOT
    for part in path.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise OpeningXICompositionError("source evidence path may not use symlinks")
    return resolved


def _check_sources(source_doc: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = source_doc.get("source_files")
    if not isinstance(rows, dict) or not rows:
        raise OpeningXICompositionError("source crossmatch lacks retained source bindings")
    checked = []
    for raw_path, row in sorted(rows.items()):
        path = _source_path(raw_path)
        digest = _sha(path.read_bytes())
        if digest != row.get("sha256"):
            raise OpeningXICompositionError(f"retained source hash changed: {raw_path}")
        checked.append({"path": raw_path, "sha256": digest})
    return checked


def _verify_report_url(url: str, match_id: Any) -> None:
    if not isinstance(url, str):
        raise OpeningXICompositionError("fixture source URL must be a string")
    parsed = urlsplit(url)
    allowed_hosts = {"transfermarkt.co.uk", "www.transfermarkt.co.uk", "transfermarkt.com", "www.transfermarkt.com"}
    if (parsed.scheme != "https" or parsed.hostname not in allowed_hosts
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443) or parsed.query or parsed.fragment
            or re.fullmatch(r"/[A-Za-z0-9_-]+/index/spielbericht/" + re.escape(str(match_id)), parsed.path) is None):
        raise OpeningXICompositionError("fixture source must pin an HTTPS Transfermarkt report route and exact match ID")


def _identity_key(value: str) -> str:
    # Case/whitespace normalization only. Keep accents and punctuation so the
    # join cannot silently become a transliteration or alias policy.
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def _verify_raw_match_reports(source_doc: Mapping[str, Any], main_package: Mapping[str, Any],
                              jug_data: bytes, native_rosters: Mapping[int, Any],
                              native_owners: Mapping[int, set[int]]) -> list[dict[str, Any]]:
    """Reparse each bound Transfermarkt XI page and compare its team/player IDs.

    The dossier is a convenience crosswalk, not authority by itself. This
    verifier reconstructs the published line-up from the body hashed in
    `source_files`, selecting the team by exact provider club carrier.
    """
    source_rows = source_doc.get("source_files")
    person_bindings = [(raw_path, row) for raw_path, row in source_rows.items()
                       if raw_path.endswith("opening-lineup-person-evidence.json")]
    if len(person_bindings) > 1:
        raise OpeningXICompositionError("provider-person evidence binding is ambiguous")
    person_evidence = None
    if person_bindings:
        person_path, person_binding = person_bindings[0]
        person_body = _source_path(person_path).read_bytes()
        if _sha(person_body) != person_binding.get("sha256"):
            raise OpeningXICompositionError("provider-person evidence hash differs")
        person_evidence = json.loads(person_body)
    preallocation_bindings = [(raw_path, row) for raw_path, row in source_rows.items()
                              if raw_path.endswith("opening-squad-preallocation.json")]
    if len(preallocation_bindings) != 1:
        raise OpeningXICompositionError("one exact annual preallocation source binding is required")
    preallocation_path, preallocation_binding = preallocation_bindings[0]
    preallocation_body = _source_path(preallocation_path).read_bytes()
    if _sha(preallocation_body) != preallocation_binding.get("sha256"):
        raise OpeningXICompositionError("annual preallocation source hash differs")
    preallocation = json.loads(preallocation_body)
    fixture_bindings = [(raw_path, row) for raw_path, row in source_rows.items()
                        if raw_path.endswith("opening-lineups.json")]
    if len(fixture_bindings) != 1:
        raise OpeningXICompositionError("one hash-bound season opening-fixture capture is required")
    fixture_path, fixture_binding = fixture_bindings[0]
    fixture_body = _source_path(fixture_path).read_bytes()
    if _sha(fixture_body) != fixture_binding.get("sha256"):
        raise OpeningXICompositionError("season opening-fixture capture hash differs")
    fixture_capture = json.loads(fixture_body)
    player_by_carrier = {int(row["carrier_id"]): row for row in main_package.get("players", [])}
    jug_entries = {int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(jug_data).entries}
    from scripts.season_historical_roster_audit_v1 import native_player
    receipts: list[dict[str, Any]] = []
    target_ids = source_doc.get("membership_target_club_carriers")
    if (not isinstance(target_ids, list) or not target_ids
            or any(type(value) is not int for value in target_ids)
            or len(target_ids) != len(set(target_ids))):
        raise OpeningXICompositionError("source plan must pin unique target club carriers")
    for club in source_doc.get("club_crossmatches", []):
        if club.get("carrier_id") not in set(target_ids):
            continue
        url = club.get("source_url")
        _verify_report_url(url, club.get("match_id"))
        matches = []
        for raw_path, row in source_rows.items():
            if not raw_path.lower().endswith(".html"):
                continue
            raw_candidate = _source_path(raw_path).read_bytes()
            if url and url.encode("utf-8") in raw_candidate:
                matches.append((raw_path, row))
        if len(matches) != 1:
            raise OpeningXICompositionError("each source fixture must bind one exact Transfermarkt report body")
        raw_path, binding = matches[0]
        body = _source_path(raw_path).read_bytes()
        if _sha(body) != binding["sha256"]:
            raise OpeningXICompositionError("raw fixture body hash differs during report reconstruction")
        soup = BeautifulSoup(body, "html.parser")
        og_url = soup.find("meta", attrs={"property": "og:url"})
        og_title = soup.find("meta", attrs={"property": "og:title"})
        description = soup.find("meta", attrs={"name": "description"})
        if not og_url or not og_title or not description:
            raise OpeningXICompositionError("raw fixture report lacks canonical URL/title/date metadata")
        if og_url.get("content") != url:
            raise OpeningXICompositionError("raw fixture report identity differs from its bound URL")
        report_id = re.search(r"/spielbericht/(\d+)$", og_url.get("content", ""))
        if report_id is None or report_id.group(1) != str(club.get("match_id")):
            raise OpeningXICompositionError("raw fixture report match ID differs from the source crosswalk")
        selector = club.get("selector")
        if not isinstance(selector, dict) or type(selector.get("transfermarkt_club_id")) is not int:
            raise OpeningXICompositionError("target fixture selector lacks an exact provider club ID")
        expected_club_id = selector["transfermarkt_club_id"]
        lineup_boxes = [box for box in soup.select("div.box")
                        if (heading := box.find(["h2", "h3"])) is not None
                        and heading.get_text(" ", strip=True) == "Line-Ups"]
        if len(lineup_boxes) != 1:
            raise OpeningXICompositionError("raw report lacks one explicit Line-Ups container")
        team_columns = [node for node in lineup_boxes[0].find_all("div", recursive=False)
                        if "large-6" in (node.get("class") or []) and "columns" in (node.get("class") or [])]
        teams = []
        for team in team_columns:
            links = team.select('a[href*="/startseite/verein/"]')
            ids = [re.search(r"/verein/(\d+)(?:/|$)", link.get("href", "")) for link in links]
            if any(match and int(match.group(1)) == expected_club_id for match in ids):
                teams.append(team)
        if len(teams) != 1:
            raise OpeningXICompositionError("raw report does not identify one exact selected club line-up")
        parsed: list[tuple[str, str, str]] = []
        for tr in teams[0].select("table tr"):
            label = tr.find("b")
            if label is None:
                continue
            group = label.get_text(" ", strip=True)
            if group == "Manager":
                continue
            broad = {"Goalkeeper": "G", "Defenders": "D", "Midfielders": "M", "Forwards": "F"}.get(group)
            if broad is None:
                raise OpeningXICompositionError("raw report uses an unsupported published position group")
            for link in tr.select('a[href*="/profil/spieler/"]'):
                match = re.search(r"/spieler/(\d+)(?:$|[/?#])", link.get("href", ""))
                name = link.get("title") or link.get_text(" ", strip=True)
                if match is None or not name:
                    raise OpeningXICompositionError("raw report player link lacks exact provider ID/name")
                parsed.append((match.group(1), name, broad))
        actual = [(str(row.get("provider_id")), str(row.get("published_full_name")),
                   {"Goalkeeper": "G", "Defenders": "D", "Midfielders": "M", "Forwards": "F"}.get(row.get("position_group")))
                  for row in club.get("xi", [])]
        if len(parsed) != 11 or parsed != actual:
            raise OpeningXICompositionError("raw report XI IDs/names/position groups differ from the crosswalk")
        captured_fixtures = [row for row in fixture_capture.get("clubs", [])
            if str(row.get("source_match_id")) == str(club.get("match_id"))
            and row.get("lineup_source_url") == url
            and row.get("source_selector", {}).get("transfermarkt_club_id") == expected_club_id]
        if len(captured_fixtures) != 1:
            raise OpeningXICompositionError("source schedule capture does not bind one exact first-fixture club row")
        captured = captured_fixtures[0]
        captured_xi = [(str(slot.get("source_player_id")), str(slot.get("display_name")),
                        {"Goalkeeper": "G", "Defenders": "D", "Midfielders": "M", "Forwards": "F"}.get(
                            slot.get("source_position_group")))
                       for slot in captured.get("starting_xi", [])]
        if (captured.get("source_status") != "source-qualified-with-explicit-gaps"
                or captured_xi != parsed):
            raise OpeningXICompositionError("raw first-fixture report differs from its hash-bound season schedule capture")
        identity_exceptions = []
        for slot in club.get("xi", []):
            selector = club["selector"]
            source_clubs = [row for row in preallocation.get("source_clubs", [])
                            if (row.get("selector", {}).get("club_name"),
                                row.get("selector", {}).get("competition_catalog"),
                                row.get("selector", {}).get("country_catalog")) ==
                               (selector["club_name"], selector["competition_catalog"], selector["country_catalog"])]
            if len(source_clubs) != 1:
                raise OpeningXICompositionError("fixture selector lacks one exact annual preallocation club")
            index_matches = [row for row in source_clubs[0].get("players", [])
                             if row.get("source_row_index") == slot.get("preallocation_source_row_index")]
            if len(index_matches) != 1:
                raise OpeningXICompositionError("source annual row index is absent or duplicated")
            annual = index_matches[0]
            if (annual.get("source_row_sha256") != slot.get("preallocation_source_row_sha256")
                    or str(annual.get("opening_source_player_id")) != str(slot.get("provider_id"))
                    or _identity_key(str(annual.get("facts", {}).get("name", ""))) !=
                       _identity_key(str(slot.get("preallocation_source_name", "")))
                    or annual.get("facts", {}).get("birth_date") != slot.get("preallocation_source_birth_date")
                    or slot.get("preallocation_source_birth_date") != slot.get("published_dob")):
                raise OpeningXICompositionError("raw provider player ID does not join its exact annual row hash/name/DOB")
            if person_evidence is not None:
                people = [row for row in person_evidence.get("players", [])
                          if str(row.get("source_player_id")) == str(slot.get("provider_id"))
                          and row.get("source_selector") == {
                              "club_name": selector["club_name"],
                              "competition_catalog": selector["competition_catalog"],
                              "country_catalog": selector["country_catalog"],
                          }]
                if people and (len(people) != 1
                        or people[0].get("published_full_name") != slot.get("published_full_name")
                        or people[0].get("published_birth_date") != slot.get("published_dob")
                        or people[0].get("source_position_group") != slot.get("position_group")):
                    raise OpeningXICompositionError("optional profile identity evidence conflicts with the raw/annual source join")
            target_carrier = int(club["carrier_id"])
            source_name = str(slot.get("preallocation_source_name") or "")
            source_dob = slot.get("preallocation_source_birth_date")
            if not source_name or not source_dob or source_dob != slot.get("published_dob"):
                raise OpeningXICompositionError("source person lacks the exact name/DOB annual row join")
            exact = sorted(cid for cid, actor in player_by_carrier.items()
                           if _identity_key(str(actor.get("source_name") or actor["name"])) == _identity_key(source_name)
                           and actor.get("facts", {}).get("birth_date") == source_dob)
            if exact != slot.get("exact_full_name_carriers") or len(exact) != 1:
                raise OpeningXICompositionError("annual full-name/DOB join is not globally unique in the parent recipe")
            selected = int(slot.get("selected_carrier_id", -1))
            selected_owners = native_owners.get(selected)
            if selected != exact[0] or not isinstance(selected_owners, set) or len(selected_owners) != 1:
                raise OpeningXICompositionError("selected source actor differs from its exact exclusive parent owner")
            source_owner = next(iter(selected_owners))
            actor = player_by_carrier[selected]
            entry = jug_entries.get(selected)
            if entry is None:
                raise OpeningXICompositionError("selected native player carrier is absent")
            payload = entry.decode_payload(jug_data)
            native = native_player(payload, selected)
            end = int(native["name_end"])
            native_dob = f"{int.from_bytes(bytes(value ^ 0x61 for value in payload[end+14:end+16]), 'little'):04d}-{payload[end+13] ^ 0x61:02d}-{payload[end+12] ^ 0x61:02d}"
            if (_identity_key(native["name"]) != _identity_key(source_name)
                    or native_dob != source_dob or actor.get("facts", {}).get("birth_date") != native_dob):
                raise OpeningXICompositionError("selected person source does not match the exact native name/DOB preimage")
            # Same-DOB native namesakes remain visible as an explicit review
            # exception even when full source name selects one exact carrier.
            namesake_ids = sorted(int(row.player_record_id) for row in native_rosters[source_owner].rows
                                  if int(row.player_record_id) != selected
                                  and player_by_carrier.get(int(row.player_record_id), {}).get("facts", {}).get("birth_date") == source_dob)
            if namesake_ids:
                identity_exceptions.append({"provider_player_id": str(slot["provider_id"]),
                    "published_full_name": source_name, "birth_date": source_dob,
                    "selected_exact_name_carrier": selected, "same_dob_namesake_carrier_ids": namesake_ids,
                    "status": "unresolved-confirmed-duplicate-namesake-candidate-pending-source-backed-disposition"})
        title = og_title.get("content", "")
        date_match = re.search(r", (\d{2}/\d{2}/\d{4}) - ", title)
        page_date = None
        if date_match:
            day, month, year = date_match.group(1).split("/")
            page_date = f"{year}-{month}-{day}"
        if club.get("date") != page_date:
            raise OpeningXICompositionError("typed fixture date differs from exact report metadata date")
        body_date_link = soup.select_one('a[href*="/datum/"]')
        body_date = None
        if body_date_link:
            date_link = re.search(r"/datum/(\d{4}-\d{2}-\d{2})", body_date_link.get("href", ""))
            if date_link:
                body_date = date_link.group(1)
        receipts.append({"match_id": str(club["match_id"]), "source_url": url,
                         "selected_club_provider_id": expected_club_id,
                         "first_fixture_capture_date": captured.get("first_league_fixture_date"),
                         "first_fixture_schedule_url": captured.get("schedule_url"),
                         "first_fixture_competition_code": captured.get("source_competition_code"),
                         "published_xi_count": len(parsed), "page_metadata_date": page_date,
                         "body_matchday_date": body_date,
                         "date_claims_differ": bool(page_date and body_date and page_date != body_date),
                         "identity_review_exceptions": identity_exceptions,
                         "report_title": title})
    return receipts


def _package_rows(package: Mapping[str, Any]) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    players = package.get("players")
    clubs = package.get("clubs")
    if not isinstance(players, list) or not isinstance(clubs, list):
        raise OpeningXICompositionError("recipe layer lacks player/club arrays")
    by_carrier = {int(row["carrier_id"]): row for row in players}
    by_club_carrier = {int(row["carrier_id"]): row for row in clubs}
    by_player_id = {str(row["id"]): row for row in players}
    if len(by_carrier) != len(players) or len(by_club_carrier) != len(clubs) or len(by_player_id) != len(players):
        raise OpeningXICompositionError("recipe layer has duplicate carrier or recipe IDs")
    return by_carrier, by_club_carrier, by_player_id


def _verify_selected_package_owners(package: Mapping[str, Any], selected_clubs: set[int], roster_ids: Mapping[int, list[int]]) -> None:
    by_carrier, club_by_carrier, _ = _package_rows(package)
    for cid in selected_clubs:
        club = club_by_carrier.get(cid)
        if club is None:
            raise OpeningXICompositionError(f"selected recipe club carrier is absent: {cid}")
        ids = club["roster_player_ids"]
        resolved = []
        player_id_map = {row["id"]: row for row in package["players"]}
        for player_id in ids:
            actor = player_id_map.get(player_id)
            if actor is None:
                raise OpeningXICompositionError("club roster references a missing recipe player")
            resolved.append(int(actor["carrier_id"]))
            if actor["club_id"] != club["id"]:
                raise OpeningXICompositionError("recipe owner field differs from its club roster")
        if resolved != roster_ids[cid]:
            raise OpeningXICompositionError(f"recipe/native parent roster order differs for club {cid}")


def _update_recipe_layer(
    package: Mapping[str, Any], *, move_rows: list[dict[str, int]],
    target_clubs: list[dict[str, Any]], source_xis: dict[int, list[int]],
    native_names: Mapping[int, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    before = copy.deepcopy(dict(package))
    after = copy.deepcopy(before)
    before_players, before_clubs, _ = _package_rows(before)
    players, clubs, player_ids = _package_rows(after)
    changes: list[dict[str, Any]] = []

    for move in move_rows:
        carrier = move["player_record_id"]
        actor_before = before_players.get(carrier)
        actor = players.get(carrier)
        source_club = clubs.get(move["from_club_carrier_id"])
        target_club = clubs.get(move["to_club_carrier_id"])
        if actor_before is None or actor is None or source_club is None or target_club is None:
            raise OpeningXICompositionError("owner move is missing a recipe actor or club")
        if actor_before["club_id"] != source_club["id"]:
            raise OpeningXICompositionError("recipe actor owner differs from the exact native source owner")
        if actor_before["id"] not in source_club["roster_player_ids"]:
            raise OpeningXICompositionError("recipe owner roster does not contain its moved actor")
        if actor_before["id"] in target_club["roster_player_ids"]:
            raise OpeningXICompositionError("target recipe roster already contains the moved actor")
        source_club["roster_player_ids"].remove(actor_before["id"])
        target_club["roster_player_ids"].append(actor_before["id"])
        actor["club_id"] = target_club["id"]
        source_opening = source_club.get("opening")
        if not isinstance(source_opening, dict):
            raise OpeningXICompositionError("moved actor source club has no explicit opening package")
        if actor_before["id"] in source_opening.get("starting_xi_player_ids", []):
            raise OpeningXICompositionError("owner move would remove a donor opening starter")
        source_opening["substitute_player_ids"] = [
            player_id for player_id in source_opening.get("substitute_player_ids", [])
            if player_id != actor_before["id"]
        ]
        changes.append({"carrier_id": carrier, "before_club_id": actor_before["club_id"],
                        "after_club_id": actor["club_id"], "only_actor_field_changed": "club_id"})

    for club_row in target_clubs:
        cid = int(club_row["carrier_id"])
        club = clubs[cid]
        opening = club.get("opening")
        if not isinstance(opening, dict):
            raise OpeningXICompositionError("target club has no explicit opening recipe")
        carrier_order = source_xis[cid]
        if len(carrier_order) != 11 or len(set(carrier_order)) != 11:
            raise OpeningXICompositionError("source-bound XI needs eleven unique actors")
        new_ids = []
        for carrier in carrier_order:
            actor = players.get(carrier)
            if actor is None or actor["id"] not in club["roster_player_ids"] or actor["club_id"] != club["id"]:
                raise OpeningXICompositionError("source XI actor is not uniquely target-owned in the recipe")
            new_ids.append(actor["id"])
        old_ids = list(opening.get("starting_xi_player_ids", []))
        if len(old_ids) != 11 or len(set(old_ids)) != 11 or len(opening.get("tactics_positions", [])) != 11:
            raise OpeningXICompositionError("target opening/tactics preimage is malformed")
        context = opening.get("tactics_context")
        if not isinstance(context, dict) or len(context.get("slots", [])) != 11:
            raise OpeningXICompositionError("target contextual tactics need an exact eleven-slot preimage")
        if [slot.get("player_id") for slot in context["slots"]] != old_ids:
            raise OpeningXICompositionError("context slot identities differ from the parent XI")
        opening["starting_xi_player_ids"] = new_ids
        for slot, player_id in zip(context["slots"], new_ids, strict=True):
            actor = player_ids[player_id]
            if slot["player_id"] == player_id:
                continue
            slot["player_id"] = player_id
            slot["native_player_id"] = int(actor["carrier_id"])
            slot["native_name"] = native_names[int(actor["carrier_id"])]
        contextual.validate_context(context, expected_player_ids=new_ids)

    moved_carriers = {int(row["carrier_id"]) for row in changes}
    after_by_id = {row["id"]: row for row in after["players"]}
    for original in before["players"]:
        after_row = after_by_id[original["id"]]
        expected = copy.deepcopy(original)
        if int(original["carrier_id"]) in moved_carriers:
            move = next(row for row in move_rows if row["player_record_id"] == int(original["carrier_id"]))
            expected["club_id"] = clubs[move["to_club_carrier_id"]]["id"]
        if after_row != expected:
            raise OpeningXICompositionError("player fields changed outside selected owner fields")
    # Selected-player and non-player rows are checked in the source wrapper;
    # package validation here catches dangling rosters, owner inconsistencies,
    # invalid source IDs, and broken opening-context references.
    validation_before = _package_validation_state(before)
    validation_after = _package_validation_state(after)
    if validation_after != validation_before:
        raise OpeningXICompositionError("recipe package validation errors changed outside the selected roster edits")
    delta = {"owner_rows": changes,
             "target_xi_carriers": {str(cid): source_xis[cid] for cid in sorted(source_xis)},
             "strict_validation_state_unchanged": True,
             "recipe_written": False}
    return after, delta


def compose_in_memory(parent: Any, main_package: Mapping[str, Any], english_package: Mapping[str, Any],
                      eq_data: bytes, jug_data: bytes, source_doc: Mapping[str, Any]) -> dict[str, Any]:
    """Create and verify exact main+English recipe, EQ roster, and JUG order postimages."""
    if source_doc.get("schema_version") != "pm99-opening-xi-transfer-crossmatch-v1":
        raise OpeningXICompositionError("unsupported pinned first-fixture crossmatch")
    parent_pin = source_doc.get("parent")
    if (not isinstance(parent_pin, dict) or parent_pin.get("season") != parent.season
            or parent_pin.get("release_id") != parent.release_id
            or parent_pin.get("manifest_sha256") != parent.manifest_sha256
            or parent_pin.get("package_sha256") != registry.sha256_file(parent.package_path)
            or parent_pin.get("EQ_sha256") != _sha(eq_data)
            or parent_pin.get("JUG_sha256") != _sha(jug_data)):
        raise OpeningXICompositionError("exact registered parent package/EQ/JUG pin differs")
    source_files = _check_sources(source_doc)
    overlay_artifacts = [row for row in main_package.get("artifacts", [])
                         if str(row.get("relative_path", "")).endswith("english-season-package.json")]
    if len(overlay_artifacts) != 1:
        raise OpeningXICompositionError("parent main package lacks its exact English overlay binding")
    overlay_path = parent.package_path.parent / "english-season-package.json"
    if _sha(overlay_path.read_bytes()) != overlay_artifacts[0].get("sha256"):
        raise OpeningXICompositionError("English overlay file differs from the main recipe artifact pin")
    if package_v2.canonical_json_bytes(dict(english_package)) != overlay_path.read_bytes():
        raise OpeningXICompositionError("supplied English overlay differs from its retained canonical file")
    target_ids = source_doc.get("membership_target_club_carriers")
    if (not isinstance(target_ids, list) or not target_ids
            or any(type(value) is not int for value in target_ids)
            or len(target_ids) != len(set(target_ids))):
        raise OpeningXICompositionError("source plan must pin unique target club carriers")
    target_rows = [row for row in source_doc.get("club_crossmatches", [])
                   if row.get("carrier_id") in set(target_ids)]
    if (len(target_rows) != len(target_ids)
            or len({row.get("carrier_id") for row in target_rows}) != len(target_ids)):
        raise OpeningXICompositionError("each selected target needs one exact source club row")
    target_rows.sort(key=lambda row: int(row["carrier_id"]))
    _index, _raw, native_rosters, owners = _read_rosters(eq_data)
    main_players, main_clubs, main_ids = _package_rows(main_package)
    raw_report_receipts = _verify_raw_match_reports(source_doc, main_package, jug_data,
                                                     native_rosters, owners)
    selected_clubs = {int(row["carrier_id"]) for row in target_rows}
    source_xis: dict[int, list[int]] = {}
    all_source_carriers: set[int] = set()
    for row in target_rows:
        target = int(row["carrier_id"])
        source_xi = row.get("xi")
        if (not isinstance(source_xi, list) or len(source_xi) != 11
                or any(not isinstance(slot.get("selected_carrier_id"), int) for slot in source_xi)):
            raise OpeningXICompositionError("source XI lacks eleven identity-bound carrier matches")
        carrier_order = [int(slot["selected_carrier_id"]) for slot in source_xi]
        if len(set(carrier_order)) != 11 or any(carrier not in slot.get("exact_full_name_carriers", [])
                                                 for carrier, slot in zip(carrier_order, source_xi, strict=True)):
            raise OpeningXICompositionError("source XI identity must be a unique exact name+DOB match")
        if all_source_carriers.intersection(carrier_order):
            raise OpeningXICompositionError("one native actor is claimed by both target source XIs")
        all_source_carriers.update(carrier_order)
        source_xis[target] = carrier_order
        if target not in main_clubs or target not in native_rosters:
            raise OpeningXICompositionError("target club is absent from native or recipe parent")
    donor_ids: dict[int, int] = {}
    for carrier in sorted(all_source_carriers):
        actor = main_players.get(carrier)
        if actor is None:
            raise OpeningXICompositionError(f"source actor carrier is absent from main recipe: {carrier}")
        owner_ids = owners.get(carrier)
        if not isinstance(owner_ids, set) or len(owner_ids) != 1:
            raise OpeningXICompositionError("source actor lacks exact exclusive native owner")
        source_club = next(iter(owner_ids))
        recipe_source_club = main_clubs.get(source_club)
        if recipe_source_club is None or actor["club_id"] != recipe_source_club["id"]:
            raise OpeningXICompositionError("source actor recipe owner differs from native owner")
        target_club = next(cid for cid, xi in source_xis.items() if carrier in xi)
        if source_club != target_club:
            donor_ids[carrier] = source_club
    moves = []
    for target, xi in source_xis.items():
        for carrier in xi:
            source = donor_ids.get(carrier)
            if source is not None:
                moves.append({"player_record_id": carrier, "from_club_carrier_id": source,
                              "to_club_carrier_id": target})
    if not moves:
        raise OpeningXICompositionError("no exact cross-club source XI admission is required")

    selected_native_clubs = set(source_xis) | set(donor_ids.values())
    _verify_selected_package_owners(main_package, selected_native_clubs, {
        cid: [int(row.player_record_id) for row in native_rosters[cid].rows] for cid in selected_native_clubs})
    english_players, english_clubs, _english_ids = _package_rows(english_package)
    _verify_selected_package_owners(english_package, selected_native_clubs, {
        cid: [int(row.player_record_id) for row in native_rosters[cid].rows] for cid in selected_native_clubs})
    for carrier in all_source_carriers:
        if carrier not in english_players or english_players[carrier]["id"] != main_players[carrier]["id"]:
            raise OpeningXICompositionError("main and English overlay actor identities differ")
        if english_players[carrier]["club_id"] != main_players[carrier]["club_id"]:
            raise OpeningXICompositionError("main and English overlay owner preimages differ")
    eq_after, roster_receipt = reassign_memberships(eq_data, moves)
    parent_jug_index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug_data).entries}
    native_names = {carrier: read_initial_order(parent_jug_index[carrier].decode_payload(jug_data)).name
                    for carrier in all_source_carriers}
    main_after, main_delta = _update_recipe_layer(
        main_package, move_rows=moves, target_clubs=target_rows, source_xis=source_xis,
        native_names=native_names)
    english_after, english_delta = _update_recipe_layer(
        english_package, move_rows=moves, target_clubs=target_rows, source_xis=source_xis,
        native_names=native_names)
    eq_after, _visibility_receipt = visibility.replay(eq_after, main_after, parent.package_path)
    overlay_artifacts_after = [row for row in main_after.get("artifacts", [])
                               if str(row.get("relative_path", "")).endswith("english-season-package.json")]
    if len(overlay_artifacts_after) != 1:
        raise OpeningXICompositionError("main recipe must pin one English overlay artifact")
    overlay_artifacts_after[0]["sha256"] = _sha(package_v2.canonical_json_bytes(english_after))

    # Existing complete-order provider writes only target players' JUG startup
    # bytes; the source-bound EQ ownership rows already exist in memory above.
    players_by_id = {row["id"]: row for row in main_after["players"]}
    clubs_by_carrier = {int(row["carrier_id"]): row for row in main_after["clubs"]}
    jug_index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug_data).entries}
    order_rows = [order_repair.repair_club(clubs_by_carrier[cid], players_by_id, jug_index, jug_data)
                  for cid in sorted(source_xis)]
    order_layer = {"schema_version": order_repair.SCHEMA, "season": parent.season,
                   "source_jug_sha256": _sha(jug_data), "clubs": order_rows}
    jug_after = order_repair.apply_layer(eq_after, jug_data, order_layer, allow_compact=True)
    # Reconstruct the same contextual EQ layers the canonical compiler applies
    # after roster/order work, so SOURCE compares the actual final bytes.
    context_layers = contextual.package_layers(main_after, parent.package_path)
    inline_contexts = [{"carrier_id": row["carrier_id"], "context": row["opening"]["tactics_context"]}
                       for row in main_after["clubs"]
                       if isinstance(row.get("opening"), dict)
                       and "tactics_context" in row["opening"]]
    if ({row["carrier_id"] for row in inline_contexts}
            & {row["carrier_id"] for layer in context_layers for row in layer["clubs"]}):
        raise OpeningXICompositionError("inline and artifact contextual layers conflict during SOURCE replay")
    if inline_contexts:
        from scripts.season_contextual_tactics_v1 import SCHEMA as CONTEXT_SCHEMA
        eq_after = contextual.apply_layer(eq_after, jug_after,
            {"schema_version": CONTEXT_SCHEMA, "clubs": inline_contexts})
    for context_layer in context_layers:
        eq_after = contextual.apply_layer(eq_after, jug_after, context_layer)
    after_jug_index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug_after).entries}
    before_jug_index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug_data).entries}
    order_changes = []
    for carrier in before_jug_index:
        before_payload = before_jug_index[carrier].decode_payload(jug_data)
        after_payload = after_jug_index[carrier].decode_payload(jug_after)
        if before_payload == after_payload:
            continue
        identity_exchange.verify_order_only_record(before_payload, after_payload)
        order_changes.append(carrier)

    for target, carrier_order in source_xis.items():
        qe = next(e for e in IndexedFDIFile.from_bytes(eq_after).entries if e.record_id == target)
        eq_entry = eq_after[qe.payload_offset:qe.payload_offset + qe.payload_length]
        if order_repair.tactics.native_xi(eq_entry, jug_after) != [
                (carrier, order_repair.read_initial_order(after_jug_index[carrier].decode_payload(jug_after)).name)
                for carrier in carrier_order]:
            raise OpeningXICompositionError("native source XI does not match the exact named carrier order")

    # `_update_recipe_layer` already compared complete strict-validation state
    # before/after for each layer. Do not rerun the whole strict validator here;
    # it reports pre-existing parent ambiguities and does not add information.
    return {
        "schema_version": "pm99-opening-xi-owner-composition-inmemory-v2",
        "state": "verified-in-memory-only-no-publication",
        "parent": {"season": parent.season, "release_id": parent.release_id,
                   "manifest_sha256": parent.manifest_sha256,
                   "package_sha256": parent_pin["package_sha256"],
                   "eq_sha256": parent_pin["EQ_sha256"], "jug_sha256": parent_pin["JUG_sha256"]},
        "source_bindings": source_files,
        "raw_report_reconstruction": raw_report_receipts,
        "owner_moves": moves,
        "roster_payload_receipt": roster_receipt,
        "main_recipe_delta": main_delta,
        "english_recipe_delta": english_delta,
        "in_memory_postimages": {"eq_sha256": _sha(eq_after), "jug_sha256": _sha(jug_after)},
        "startup_order_only_carrier_ids": sorted(order_changes),
        "outputs": {"main_package": main_after, "english_package": english_after,
                    "eq": eq_after, "jug": jug_after},
        "write_policy": "all outputs are returned as in-memory values; no registered files were written",
    }
