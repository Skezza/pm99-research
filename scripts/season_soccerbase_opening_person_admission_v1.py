"""Source-bound Soccerbase identities for fixed-slot opening corrections.

Replay a published first league fixture or a positive August match and its
profile. This reader never writes Native data or authorises roster ownership.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from bs4 import BeautifulSoup
from scripts import json_storage_io_v1 as storage_io
from scripts import season_release_registry_v1 as registry
from scripts import season_soccerbase_original_opening_v1 as original
from scripts import season_verified_opening_roster_sources_v1 as verified
from scripts.season_exact_fifa_role_delta_v1 import compatible

SCHEMA = "pm99-original-soccerbase-opening-person-admission-v2"
POLICY = "original-soccerbase-profile-and-exact-first-or-later-August-fixture-v2"
ROLE_SCHEMA = "pm99-opening-soccerbase-fine-role-review-v1"
ROLE_POLICY = "explicit-reviewed-fine-role-candidates-compatible-with-dated-broad-position-v2"
CLUB_REVIEW_SCHEMA = "pm99-reviewed-soccerbase-native-club-crosswalk-v1"
WITNESS_POLICY = "original-soccerbase-scheduled-August-fixture-numeric-club-and-person-v2"


def _sha(path: Path) -> str:
    return hashlib.sha256(storage_io.read_bytes(path)).hexdigest()


def _bound(value: Any, label: str, *, require_url: bool = True) -> Path:
    if (not isinstance(value, Mapping) or not isinstance(value.get("path"), str)
            or (require_url and not isinstance(value.get("url"), str))
            or not isinstance(value.get("sha256"), str)
            or len(value["sha256"]) != 64):
        raise ValueError(f"{label} needs exact path, URL and SHA-256")
    path = storage_io.resolve(registry.ROOT / value['path'], strict=True)
    if not path.is_relative_to(storage_io.resolve(registry.ROOT)) or _sha(path) != value["sha256"]:
        raise ValueError(f"{label} body differs from its hash binding")
    return path


def _bound_json(value: Any, label: str) -> dict[str, Any]:
    path = _bound(value, label, require_url=False)
    try:
        payload = json.loads(storage_io.read_text(path, encoding='utf-8'))
    except Exception as exc:
        raise ValueError(f"{label} is not JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} root must be an object")
    return payload


def _verify_role_review(selection: Mapping[str, Any], season: str,
                        source_person: Mapping[str, Any], broad: str) -> tuple[list[int], dict[str, Any]]:
    claim = selection.get("role_review")
    if not isinstance(claim, Mapping) or claim.get("policy") != ROLE_POLICY:
        raise ValueError("explicit role-review binding is required")
    payload = _bound_json(claim.get("source"), "fine-role review")
    expected_keys = {"schema", "status", "review_id", "reviewer", "season", "source_player_id",
                     "full_name", "birth_date", "broad_position", "fine_roles", "source_profile_sha256",
                     "claim_scope"}
    if (set(payload) != expected_keys or payload.get("schema") != ROLE_SCHEMA
            or payload.get("status") != "reviewed"):
        raise ValueError("fine-role source must use the exact reviewed-role payload schema")
    roles = payload.get("fine_roles")
    if (payload.get("season") != season
            or payload.get("source_player_id") != source_person.get("source_player_id")
            or payload.get("full_name") != source_person.get("name")
            or payload.get("birth_date") != source_person.get("birth_date")
            or payload.get("broad_position") != broad
            or payload.get("claim_scope") != "editorial-fine-role-selection-not-a-published-historical-role"):
        raise ValueError("fine-role review is not bound to this season/person/source role")
    if (not isinstance(payload.get("review_id"), str) or not payload["review_id"]
            or not isinstance(payload.get("reviewer"), str) or not payload["reviewer"]):
        raise ValueError("fine-role review needs a stable review ID and reviewer")
    if (not isinstance(roles, list) or not roles or len(roles) > 6
            or any(type(role) is not int or not 0 <= role <= 17 for role in roles)
            or len(set(roles)) != len(roles) or any(not compatible(broad, role) for role in roles)):
        raise ValueError("every fine role must be unique, supported, and broad-position compatible")
    profile_sha = claim.get("profile_sha256")
    if payload.get("source_profile_sha256") != profile_sha:
        raise ValueError("fine-role review does not bind the selected profile bytes")
    return list(roles), payload


def _verify_club_review(selection: Mapping[str, Any], season: str,
                        group: Mapping[str, Any], destination: Mapping[str, Any]) -> dict[str, Any]:
    claim = selection.get("club_review")
    if not isinstance(claim, Mapping):
        raise ValueError("exact source-club crosswalk binding is required")
    payload = _bound_json(claim.get("source"), "source-club crosswalk")
    keys = {"schema", "status", "review_id", "reviewer", "season", "provider",
            "provider_team_id", "provider_club_name", "native_club_id",
            "native_club_carrier_id", "native_club_name", "supporting_sources"}
    if (type(group.get("provider_team_id")) is not int or group["provider_team_id"] <= 0
            or type(destination.get("carrier_id")) is not int
            or set(payload) != keys or payload.get("schema") != CLUB_REVIEW_SCHEMA
            or payload.get("status") != "reviewed-source-club-equivalence"
            or payload.get("season") != season or payload.get("provider") != "soccerbase"
            or type(payload.get("provider_team_id")) is not int
            or type(payload.get("native_club_carrier_id")) is not int
            or payload["provider_team_id"] != group.get("provider_team_id")
            or payload["provider_club_name"] != group.get("club_name")
            or payload["native_club_id"] != destination.get("id")
            or payload["native_club_carrier_id"] != destination.get("carrier_id")
            or payload["native_club_name"] != destination.get("name")
            or not isinstance(payload.get("review_id"), str) or not payload["review_id"]
            or not isinstance(payload.get("reviewer"), str) or not payload["reviewer"]):
        raise ValueError("source-club crosswalk does not bind this season/provider/destination")
    sources = payload["supporting_sources"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("source-club crosswalk needs retained supporting evidence")
    for source in sources:
        _bound(source, "club crosswalk supporting source", require_url=False)
    return copy.deepcopy(payload)


def _opening_fixture(season: str, group: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    schedule_raw = verified.body(group["schedule"])
    fixture = original.first_fixture(schedule_raw, int(group["provider_team_id"]), season,
        str(group["competition"]), str(group["club_name"]), str(group["schedule"]["url"]))
    if fixture["game_id"] != group.get("expected_opening_game_id"):
        raise ValueError("source group no longer reproduces its reviewed first league fixture")
    match_raw = verified.body(group["match"])
    sheet = original.match(match_raw, fixture, int(group["provider_team_id"]),
                           str(group["match"]["url"]), True)
    return fixture, sheet


def _later_august_witness(season: str, group: Mapping[str, Any], provider_player_id: int,
                          witness: Mapping[str, Any], opener_sheet: Mapping[str, Any]) -> dict[str, Any]:
    if set(witness) != {"date", "game_id", "competition", "match"}:
        raise ValueError("later witness must bind date, game ID, competition and match body")
    if type(witness["game_id"]) is not int or witness["game_id"] <= 0:
        raise ValueError("later witness requires a positive numeric game ID")
    day_text = witness.get("date")
    try:
        day = date.fromisoformat(str(day_text))
    except ValueError as exc:
        raise ValueError("later witness date must be canonical ISO") from exc
    year = int(season[:4])
    if (day_text != day.isoformat() or day.month != 8
            or not date(year, 7, 1) <= day <= date(year + 1, 6, 30)):
        raise ValueError("later witness must be in August of the exact target season")
    schedule_raw = verified.body(group["schedule"])
    schedule = BeautifulSoup(schedule_raw, "lxml")
    rows = schedule.select(f"tr#tgc{int(witness['game_id'])}")
    if len(rows) != 1:
        raise ValueError("later witness game ID must be one exact row on the bound team-season schedule")
    row = rows[0]
    stamp = row.select_one("td.dateTime span.hide")
    comp = row.select_one("td.tournament a")
    if (stamp is None or stamp.get_text(" ", strip=True).split()[0] != day.isoformat()
            or comp is None or original.key(comp.get_text(" ", strip=True)) != original.key(str(witness["competition"]))):
        raise ValueError("later witness date or competition differs from the original schedule row")
    sides = []
    from urllib.parse import parse_qs, urlparse
    for side in ("homeTeam", "awayTeam"):
        links = row.select(f"td.{side} a[href]")
        if len(links) != 1:
            raise ValueError("later witness has ambiguous scheduled sides")
        query = parse_qs(urlparse(links[0]["href"]).query)
        ids = query.get("team_id", [])
        if len(ids) != 1 or not ids[0].isdigit():
            raise ValueError("later witness lacks numeric scheduled side identity")
        sides.append({"team_id": int(ids[0]), "name": links[0].get_text(" ", strip=True)})
    goals = row.select("td.score a.vs em")
    if len(goals) != 2 or any(not g.get_text(strip=True).isdigit() for g in goals):
        raise ValueError("later witness requires one completed score from the original schedule")
    fixture = {"date": day.isoformat(), "game_id": int(witness["game_id"]), "sides": sides,
               "score": [int(g.get_text(strip=True)) for g in goals]}
    match = witness["match"]
    _bound(match, "later Soccerbase match")
    sheet = original.match(verified.body(match), fixture, int(group["provider_team_id"]),
                           str(match["url"]), True)
    # Later-only mode cannot disguise a missing source opener membership.
    opener_ids = {p["provider_player_id"] for section in ("starting_xi", "published_bench")
                  for p in opener_sheet[section]}
    if provider_player_id in opener_ids:
        raise ValueError("later-only admission selected a person already in the opening fixture")
    members = [(section, p) for section in ("starting_xi", "published_bench") for p in sheet[section]
               if p["provider_player_id"] == provider_player_id]
    if len(members) != 1:
        raise ValueError("later August fixture does not positively identify selected provider person")
    return {"policy": WITNESS_POLICY, "date": day.isoformat(), "game_id": int(witness["game_id"]),
            "competition": str(witness["competition"]), "source_player_id": f"soccerbase:{provider_player_id}",
            "membership": {"section": members[0][0], **copy.deepcopy(members[0][1])},
            "schedule_path": group["schedule"]["path"],
            "schedule_sha256": group["schedule"]["sha256"], "match": copy.deepcopy(dict(match))}


def _candidate(selection: Mapping[str, Any], *, season: str,
               destination_club: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if selection.get("schema") != SCHEMA or selection.get("policy") != POLICY:
        raise ValueError("unsupported typed Soccerbase admission selection")
    if (not isinstance(season, str) or len(season) != 7 or season[4] != "-"
            or not season[:4].isdigit() or not season[5:].isdigit()
            or season[5:] != f"{(int(season[:4]) + 1) % 100:02d}"):
        raise ValueError("target season must use canonical YYYY-YY form")
    pid = selection.get("provider_player_id")
    if type(pid) is not int or pid <= 0:
        raise ValueError("Soccerbase player ID must be positive integer")
    group = selection.get("source_group")
    if not isinstance(group, Mapping):
        raise ValueError("exact verified Soccerbase opening group is required")
    for key in ("schedule", "match"):
        _bound(group.get(key), f"opening {key}")
    profiles = group.get("profiles")
    if not isinstance(profiles, Mapping) or str(pid) not in profiles:
        raise ValueError("selected person has no bound original Soccerbase profile")
    profile_binding = profiles[str(pid)]
    _bound(profile_binding, "selected Soccerbase profile")
    label_proof = _verify_club_review(selection, season, group, destination_club)
    opening, opener_sheet = _opening_fixture(season, group)
    profile_person, profile_facts, profile_gaps = verified.profile(profile_binding, pid)

    basis = selection.get("membership_basis")
    if not isinstance(basis, Mapping):
        raise ValueError("exact membership basis is required")
    if basis.get("kind") == "first-league-fixture":
        if basis != {"kind": "first-league-fixture"}:
            raise ValueError("first-fixture membership basis has unexpected fields")
        readback = verified.read(season, dict(group), selected_person_ids=[pid])
        desired = readback.get("desired", [])
        if len(desired) != 1:
            raise ValueError("first-fixture source reader did not return one person")
        person = desired[0]
        membership = person["membership"]
        membership_proof = {"kind": "first-league-fixture", "fixture": opening,
                            "source_reader": readback}
        membership_date = opening["date"]
        published_names = [name["name"] for name in
                           (person.get("source_display_aliases") or {}).get("names", [])]
        broad = person["source_player"]["position"]
        facts = person["source_player"]
        gaps = readback.get("secondary_fact_gaps", [])
    elif basis.get("kind") == "positive-August-fixture":
        if set(basis) != {"kind", "witness"}:
            raise ValueError("later-fixture membership basis has unexpected fields")
        membership_proof = _later_august_witness(season, group, pid, basis["witness"], opener_sheet)
        membership = membership_proof["membership"]["section"]
        membership_date = membership_proof["date"]
        published_names = [membership_proof["membership"]["published_match_name"]]
        broad = membership_proof["membership"]["position"]
        facts = copy.deepcopy(profile_facts)
        facts["position"] = broad
        profile_person["source_provider"] = "soccerbase"
        person = {"source_person": profile_person, "source_player": facts,
                  "membership": "published_bench" if membership == "published_bench" else "starting_xi",
                  "raw_evidence": {"status": "raw-source-reparsed", "local_path": profile_binding["path"],
                                   "source_sha256": profile_binding["sha256"]}}
        gaps = [dict(provider_player_id=pid, **gap) for gap in profile_gaps]
        readback = {"policy": "later-fixture-source-readback-v2", "opening_fixture": opening,
                    "later_witness": membership_proof, "native_writes": 0}
    else:
        raise ValueError("membership basis must select exact opener or positive August witness")

    source_person = person["source_person"]
    source_facts = person["source_player"]
    if (source_person.get("source_player_id") != f"soccerbase:{pid}"
            or source_person.get("source_provider") != "soccerbase"
            or source_person.get("name") != selection.get("name")
            or source_person.get("birth_date") != selection.get("birth_date")
            or profile_person.get("name") != source_person.get("name")
            or profile_person.get("birth_date") != source_person.get("birth_date")):
        raise ValueError("full name/DOB/source ID do not agree across provider profile and match")
    if (broad not in {"G", "D", "M", "F"} or selection.get("broad_position") != broad
            or profile_facts.get("position") != broad):
        raise ValueError("source profile broad role and exact dated match role disagree")
    return ({"source_person": source_person, "source_player": source_facts,
             "membership": membership, "membership_proof": membership_proof,
             "membership_date": membership_date, "published_names": published_names,
             "profile_facts": profile_facts, "profile_gaps": profile_gaps,
             "source_gaps": gaps, "readback": readback}, label_proof)


def new_person(selection: Mapping[str, Any], *, season: str,
               destination_club: Mapping[str, Any]) -> dict[str, Any]:
    candidate, label_proof = _candidate(selection, season=season, destination_club=destination_club)
    source_person = candidate["source_person"]
    broad = candidate["source_player"]["position"]
    roles, role_payload = _verify_role_review(selection, season, source_person, broad)
    if selection.get("fine_roles") != roles:
        raise ValueError("requested Native fine roles differ from the reviewed role projection")
    profile_sha = selection["source_group"]["profiles"][str(selection["provider_player_id"])] ["sha256"]
    if role_payload["source_profile_sha256"] != profile_sha:
        raise ValueError("role review profile hash differs from selected original profile")
    requested_display = selection.get("native_display_name")
    if requested_display is not None and (
            not isinstance(requested_display, str) or not requested_display.strip()
            or requested_display not in {source_person["name"], *candidate["published_names"]}):
        raise ValueError("native display must equal the full profile name or an exact published match alias")
    if requested_display is not None and len([name for name in
            {source_person["name"], *candidate["published_names"]} if name == requested_display]) != 1:
        raise ValueError("native display alias is ambiguous")
    raw_evidence = {
        "status": "raw-source-reparsed", "source_policy": POLICY,
        "provider_membership": copy.deepcopy(candidate["membership_proof"]),
        "membership_date": candidate["membership_date"],
        "profile_facts": copy.deepcopy(candidate["profile_facts"]),
        "profile_gaps": copy.deepcopy(candidate["profile_gaps"]),
        "source_gaps": copy.deepcopy(candidate["source_gaps"]),
        "role_review_payload": role_payload,
        "club_review_payload_mapping": label_proof,
        "source_reader_readback": copy.deepcopy(candidate["readback"]),
        "fine_roles": roles,
        "fine_roles_are_historical_fact": False,
    }
    if requested_display is not None:
        raw_evidence["published_display_name"] = requested_display
        raw_evidence["published_display_policy"] = (
            "original-profile-published-full-name-v1" if requested_display == source_person["name"]
            else "original-Soccerbase-match-published-alias-v1")
    return {
        "source_person": copy.deepcopy(candidate["source_person"]),
        "source_player": copy.deepcopy(candidate["source_player"]),
        "raw_evidence": raw_evidence,
        "membership": (
            ("original-published-opening-XI" if candidate["membership"] == "starting_xi"
             else "original-published-opening-bench")
            if candidate["membership_proof"].get("kind") == "first-league-fixture"
            else ("original-published-August-matchday-XI"
                  if candidate["membership_proof"].get("membership", {}).get("section") == "starting_xi"
                  else "original-published-August-matchday-bench")
        ),
    }


def membership_date(selection, *, season, destination_club):
    candidate, _ = _candidate(selection, season=season, destination_club=destination_club)
    return candidate["membership_date"]


def source_bindings(selection):
    """Expose all frozen reader inputs for replay and safe cache retention."""
    group = selection["source_group"]
    profile = group["profiles"][str(selection["provider_player_id"])]
    bodies = [group["schedule"], group["match"], profile]
    basis = selection["membership_basis"]
    if basis["kind"] == "positive-August-fixture":
        bodies.append(basis["witness"]["match"])
    result = {}
    for binding in bodies:
        path = _bound(binding, "Soccerbase original")
        verified.body(binding)
        result[str(path.relative_to(registry.ROOT))] = dict(binding)
        receipt = path.with_suffix(path.suffix + ".source.json")
        result[str(receipt.relative_to(registry.ROOT))] = {
            "path": str(receipt.relative_to(registry.ROOT)), "sha256": _sha(receipt)}
    for key in ("role_review", "club_review"):
        binding = selection[key]["source"]
        path = _bound(binding, key, require_url=False)
        result[str(path.relative_to(registry.ROOT))] = dict(binding)
    crosswalk = _bound_json(selection["club_review"]["source"], "source-club crosswalk")
    for binding in crosswalk["supporting_sources"]:
        path = _bound(binding, "club supporting source", require_url=False)
        result[str(path.relative_to(registry.ROOT))] = dict(binding)
    return [result[key] for key in sorted(result)]
