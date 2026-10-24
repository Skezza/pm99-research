"""PRIVATE in-memory native compiler for the Alty/Macc joint proposal.

No game tree is copied or written. Source adapter is local and strict; actual
JUG/EQ/ENT/MINIFOTO edits use the existing project native writers.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup

from app.editor_actions import _patch_indexed_eq_team_string_payload
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement, read_initial_order, patch_initial_orders
from app.indexed_jug_roles import rewrite_indexed_native_roles
from scripts import prepare_duplicate_whole_club_native_v1 as whole
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_editorial_ratings_v1 as ratings
from scripts import season_editorial_rating_input_builder_v1 as rating_input
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_manager_display_repair_v1 as manager_display
from scripts import season_package_v2 as package_v2
from scripts import season_release_registry_v1 as registry
from scripts import season_release_registry_v1 as release_registry
from scripts import season_within_club_reserve_repair_v1 as native_facts
from scripts import season_duplicate_ownership_delta_v1 as ownership_delta
from scripts import season_package_compiler_v2 as compiler
from app.eq_jug_linked import parse_eq_external_team_roster_payload

HERE = Path(__file__).resolve().parent
PROTOTYPE = registry.ROOT / "scripts/season_altrincham_source_reader_v1.py"
SPEC = importlib.util.spec_from_file_location("alty_prepare_private", PROTOTYPE)
assert SPEC is not None and SPEC.loader is not None
typed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(typed)

BETTNEY_REQUEST = registry.ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/macc-opening-adams-v2/bettney-request.json"
BETTNEY_REQUEST_SHA256 = "6f7bca76f3ad424cc5552c1c8224f0b0e1590da20eed85e8260a12e1004b5855"
BETTNEY_PROFILE_PATH = ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/macc-opening-adams-v1/11v11-chris-bettney-6310.html"
BETTNEY_PROFILE_SHA256 = "72718f99daa3d5ab5eda0633c24e181270d503afc12679d91ef2886f62412432"
BETTNEY_MATCH_PATH = ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/macc-opening-adams-v1/guardian-macc-scunthorpe-2000-08-12.html"
BETTNEY_MATCH_SHA256 = "64d7e0940fcb85868e399660368bde90dd3632161dddc2ce6763b72bd68394ba"
BETTNEY_RECEIPT_PROFILE_SHA256 = "c12bead37b767fc11246137422fe5fcc84ea9594e0f5e5733e01bbe9599ccfb0"
BETTNEY_RECEIPT_MATCH_SHA256 = "ffd8a73f9cab4c170815c5408e2ddb92edec07551b6e16e0ecffafe3794fcc0e"
R210_ID = "sourced-horne-kidder-facts-20261024-r210a"
R210_PACKAGE_SHA256 = "930c864992d2398714f25ae962db5f90e3025b065b1370f3cf46bfd15b390911"
R210_JUG_SHA256 = "0099ff4ed3afd54a8c2b9062cb02f3c638df0ac89c502ded2daf6f97dfc9801e"
R210_EQ_SHA256 = "ed137403df4f1ed498800d0621548645ccfd94bde332d8194b184b66aa2b7482"
R210_ENT_SHA256 = "a648dc9901350c88fd1e7416ae4849d50e6bdff5175c694e0e966b601353ff1b"
R210_MINIFOTO_SHA256 = "765b2c9870423878eaaba541ede7ed402958163d5be040ad3a320f3c9d6e4849"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _source(path: str, digest: str, receipt_path: str, receipt_digest: str) -> bytes:
    body_path = registry.ROOT / path
    if _sha(body_path.read_bytes()) != digest:
        raise ValueError(f"source body digest changed: {path}")
    receipt_file = registry.ROOT / receipt_path
    receipt_raw = receipt_file.read_bytes()
    if _sha(receipt_raw) != receipt_digest:
        raise ValueError(f"source receipt digest changed: {receipt_path}")
    receipt = json.loads(receipt_raw)
    if (receipt.get("body_sha256") != digest
            or receipt.get("body_path") not in (path, Path(path).name)):
        raise ValueError(f"receipt does not bind source body: {path}")
    return body_path.read_bytes()


def _verify_bettney() -> dict:
    request_raw = BETTNEY_REQUEST.read_bytes()
    if _sha(request_raw) != BETTNEY_REQUEST_SHA256:
        raise ValueError("Bettney typed request bytes changed")
    request = json.loads(request_raw)
    repl = request["replacement"]
    person = repl["source_person"]
    if (person.get("source_provider"), person.get("source_player_id"), person.get("name"),
            person.get("birth_date"), person.get("source_profile_url"),
            person.get("source_profile_sha256")) != (
            "11v11", "11v11:6310", "Chris Bettney", "1977-10-27",
            "https://www.11v11.com/players/chris-bettney-6310/", BETTNEY_PROFILE_SHA256):
        raise ValueError("Bettney identity is not the exact retained 11v11 profile")
    pbody = _source(BETTNEY_PROFILE_PATH, BETTNEY_PROFILE_SHA256,
        BETTNEY_PROFILE_PATH + ".source.json", BETTNEY_RECEIPT_PROFILE_SHA256)
    mbody = _source(BETTNEY_MATCH_PATH, BETTNEY_MATCH_SHA256,
        BETTNEY_MATCH_PATH + ".source.json", BETTNEY_RECEIPT_MATCH_SHA256)
    ppage, mpage = BeautifulSoup(pbody, "lxml"), BeautifulSoup(mbody, "lxml")
    ptext = " ".join(ppage.get_text(" ", strip=True).split())
    mtext = " ".join(mpage.get_text(" ", strip=True).split())
    ptitle = ppage.title.get_text(" ", strip=True) if ppage.title else ""
    expected = ("Chris Bettney Football Player Statistics | 11v11.com",
        "Date of birth 27 October 1977", "Nationality English", "Position Midfielder",
        "Weight 71 kg", "Height 1.78 m", "Macclesfield Town 01 Aug 2000 30 Sep 2000")
    if ptitle != expected[0] or any(x not in ptext for x in expected[1:]):
        raise ValueError("retained 11v11 profile does not bind Bettney's claimed person/facts")
    match_fragments = (
        "MACCLESFIELD TOWN (0) 0 SCUNTHORPE UNITED (0) 1",
        "Durkan (Bettney 59)", "Subs not used: Priest, Came")
    if any(x not in mtext for x in match_fragments):
        raise ValueError("retained Guardian match report does not prove Bettney as used substitute")
    # The two career publishers disagree on the exact transfer date; neither is selected.
    return {"person": person, "profile_sha256": BETTNEY_PROFILE_SHA256,
            "match_sha256": BETTNEY_MATCH_SHA256, "match_date": "2000-08-12",
            "transfer_date": "disputed; no exact day asserted"}


def _parent():
    release = registry.load_preferred_release("2000-01")
    if release.release_id != R210_ID:
        raise ValueError("preferred 2000 parent is no longer the reviewed r210a")
    package_path = release.package_path
    paths = {n: release.game_path / "DBDAT" / n for n in (
        "JUG98030.FDI", "EQ98030.FDI", "ENT98030.FDI", "MINIFOTO.PKF", "TEXTOS.PKF")}
    if (registry.canonical_document_sha256(package_path) != R210_PACKAGE_SHA256
            or registry.sha256_file(paths["JUG98030.FDI"]) != R210_JUG_SHA256
            or registry.sha256_file(paths["EQ98030.FDI"]) != R210_EQ_SHA256
            or registry.sha256_file(paths["ENT98030.FDI"]) != R210_ENT_SHA256
            or registry.sha256_file(paths["MINIFOTO.PKF"]) != R210_MINIFOTO_SHA256):
        raise ValueError("r210a package or native input file digest changed")
    package = json.loads(package_path.read_text())
    return release, package, {k: v.read_bytes() for k, v in paths.items()}


def _indexes(package, files):
    club = next(c for c in package["clubs"] if c["carrier_id"] == 3310)
    if (club["id"], club["manager_id"]) != ("club-3310", "manager-807"):
        raise ValueError("r210a Alty target club or manager link changed")
    alty_rows = sorted((copy.deepcopy(p) for p in package["players"] if p["club_id"] == club["id"]),
                       key=lambda p: p["carrier_id"])
    macc = next(c for c in package["clubs"] if c["carrier_id"] == 382)
    macc_rows = [p for p in package["players"] if p["carrier_id"] == 32951]
    if (len(alty_rows) != 18 or len(macc_rows) != 1 or macc_rows[0]["club_id"] != macc["id"]
            or macc_rows[0]["source_name"] != "Danny Adams"):
        raise ValueError("r210a exact Alty 18 or Macc Adams carrier changed")
    jug = files["JUG98030.FDI"]
    jidx = IndexedFDIFile.from_bytes(jug)
    jentries = {e.record_id: e for e in jidx.entries}
    eq = files["EQ98030.FDI"]
    eidx = IndexedFDIFile.from_bytes(eq)
    eentries = {e.record_id: e for e in eidx.entries}
    owners: dict[int, set[int]] = {}
    for entry in eidx.entries:
        parsed = parse_eq_external_team_roster_payload(eq[entry.payload_offset:entry.payload_offset + entry.payload_length], {})
        if parsed is not None:
            for row in parsed.rows:
                owners.setdefault(row.player_record_id, set()).add(entry.record_id)
    alty_ids = {p["carrier_id"] for p in alty_rows}
    if any(owners.get(pid) != {3310} for pid in alty_ids):
        raise ValueError("all 18 Alty destination carriers must have sole EQ owner 3310")
    if owners.get(32951) != {382}:
        raise ValueError("Macc Adams must be sole owned by Macc; no other club can be changed")
    er = parse_eq_external_team_roster_payload(eq[eentries[3310].payload_offset:eentries[3310].payload_offset + eentries[3310].payload_length], {})
    mr = parse_eq_external_team_roster_payload(eq[eentries[382].payload_offset:eentries[382].payload_offset + eentries[382].payload_length], {})
    if er is None or er.mode_byte != 1 or len(er.rows) != 18 or {r.player_record_id for r in er.rows} != alty_ids:
        raise ValueError("r210a Alty 3310 row set changed")
    if [(r.player_record_id, r.slot_index, r.flag) for r in er.rows if r.flag] != [(10958, 8, 1)]:
        raise ValueError("only the approved exact flag1 preimage at 10958/slot8 is accepted")
    if mr is None or mr.mode_byte != 0 or len(mr.rows) != 25:
        raise ValueError("Macc mode0/25 roster is not exact")
    return club, alty_rows, macc, macc_rows[0], jentries, eentries, owners, er, mr


def _new_ratings(player_id: str, person_id: str, club_id: str, position: str,
                 birth_date: str | None, height_cm: int | None, day: str, strength: int,
                 source_id: str) -> dict:
    hierarchy = {"schema_version": ratings.HIERARCHY_SCHEMA, "snapshot_date": day,
        "clubs": [{"club_id": club_id, "strength": strength, "source_ids": [source_id]}]}
    result = ratings.build_rating_output({"schema_version": ratings.INPUT_SCHEMA,
        "snapshot_date": day, "hierarchy": hierarchy,
        "players": [{"player_id": player_id, "person_id": person_id, "club_id": club_id,
                     "position": position, "birth_date": birth_date, "height_cm": height_cm,
                     "squad_status": "substitute"}]})
    values = result["player_ratings"][0]["ratings"]
    values["provenance"] = {k: values["provenance"][k] for k in ("method", "proof_grade", "source_ids")}
    return values


def _apply_source_person(old: dict, desired: dict, display_name: str, artifact_id: str,
                         strength: int, source_index: int, original_payload: bytes) -> dict:
    person = desired["source_person"]
    src = desired["source_player"]
    position = src["position"]
    if position not in {"G", "D", "M", "F"}:
        raise ValueError("Alty broad role projection is outside native values")
    dob = src["birth_date"]
    if dob is None:
        dob = {"policy": "preserve-existing-mode1"}
    nationality = src["nationality"] or {"policy": "preserve-existing-mode1"}
    facts = {"birth_date": dob, "nationality": nationality,
        "primary_position": position,
        "fine_roles": [{"G": 0, "D": 4, "M": 9, "F": 12}[position]],
        "height_cm": {"policy": "preserve-existing-mode1"},
        "weight_kg": {"policy": "preserve-existing-mode1"},
        "shirt_number": {"policy": "preserve-existing-mode1"}}
    pid = person["source_player_id"]
    output = copy.deepcopy(old)
    fallback_rows = ([{"field": "birth_date", "method": "preserve-existing-mode1", "proof":{"artifact_id":artifact_id,"grade":"source-receipt"},
             "value":{"policy":"preserve-existing-mode1"}, "reason":"Alty DOB is unavailable or explicitly conflicted; native fallback is not the sourced DOB."}
            ] if src["birth_date"] is None else [])
    if src["nationality"] is None:
        fallback_rows.append({"field": "nationality", "method": "preserve-existing-mode1", "proof":{"artifact_id":artifact_id,"grade":"source-receipt"},
             "value":{"policy":"preserve-existing-mode1"}, "reason":"No identity-linked explicit nationality; preserve native value without citizenship claim."})
    fallback_rows.extend({"field": field, "method":"preserve-existing-mode1", "proof":{"artifact_id":artifact_id,"grade":"source-receipt"},
             "value":{"policy":"preserve-existing-mode1"},"reason":"No supported physical or shirt fact; preserve native value."}
            for field in ("height_cm","weight_kg","shirt_number"))
    output.update(person_id="person-altrincham-" + hashlib.sha256(pid.encode()).hexdigest()[:20],
        name=display_name, source_name=person["name"], facts=facts,
        proof={"artifact_id": artifact_id, "grade": "source-receipt"},
        ratings=_new_ratings(old["id"], pid, old["club_id"], position,
            src["birth_date"], None, "2000-08-02", strength, "alty-joint-input-v1"),
        fact_fallbacks=sorted(fallback_rows,key=lambda row:row["field"]))
    return output


def _bettney_player(old: dict, claim: dict, artifact_id: str, strength: int, original_payload: bytes) -> dict:
    person = claim["person"]
    facts = {"birth_date": "1977-10-27", "nationality": "ENG", "primary_position": "M",
        "fine_roles": [9],
        "height_cm": 178, "weight_kg": 71,
        "shirt_number": {"policy": "preserve-existing-mode1"}}
    out = copy.deepcopy(old)
    out.update(person_id="person-11v11-6310", name="Chris BETTNEY", source_name="Chris Bettney",
        facts=facts,
        proof={"artifact_id":artifact_id,"grade":"source-receipt"},
        ratings=_new_ratings(old["id"], "person-11v11-6310", old["club_id"], "M",
            "1977-10-27", 178, "2000-08-12", 60, "alty-joint-input-v1"),
        fact_fallbacks=[{"field":"shirt_number","method":"preserve-existing-mode1",
            "proof":{"artifact_id":artifact_id,"grade":"source-receipt"},
            "value":{"policy":"preserve-existing-mode1"},
            "reason":"18 is the prior carrier fallback, not a claimed Bettney shirt number."}])
    return out


def _compile_changed_players(original: bytes, package: dict, changed_ids: set[str],
                             country_codes: dict[str, int]) -> bytes:
    """Run the existing package writer with a source-fallback-aware readback.

    delta.compile_players currently assumes every selected nationality/date is
    concrete in its final assertion. The underlying compiler supports explicit
    preserve-existing-mode1 fields and reports their exact unchanged byte
    ranges, so this wrapper keeps that native writer and verifies those ranges.
    """
    subset = ownership_delta._compiler_subset(package, changed_ids)
    role_targets = {p["carrier_id"]: p["facts"]["fine_roles"] for p in subset["players"]}
    # The core compiler's dd6361 lane is intentionally preserve-only for role
    # bytes. Supply exact preimage roles there, then use the separate existing
    # indexed role writer for our declared compatible editorial projections.
    original_index = IndexedFDIFile.from_bytes(original)
    original_entries = {e.record_id:e for e in original_index.entries}
    for player in subset["players"]:
        if player["carrier_family"] == "dd6361":
            payload=original_entries[player["carrier_id"]].decode_payload(original)
            player["facts"]["fine_roles"] = compiler._dd6361_active_fine_roles_in_order(
                payload, carrier=player["carrier_id"])
    modes = {c["id"]: 1 for c in package["clubs"]}
    replacements, handling, _a, _b, _c, preserved = compiler._player_replacements(
        package=subset, jug_data=original, country_codes=country_codes, club_modes=modes)
    patched = compiler._rebuild_indexed(original, IndexedFDIFile.from_bytes(original), replacements)
    index = IndexedFDIFile.from_bytes(patched)
    entries = {e.record_id: e for e in index.entries}
    tails = {}
    for row in handling:
        payload = bytearray(entries[row["record_id"]].decode_payload(patched))
        values = row["visible_skills"]
        if [payload[-16 + i] ^ 0x61 for i in range(len(compiler.SKILLS))] != [values[k] for k in compiler.SKILLS]:
            raise ValueError("native compiler Handling tail anchor disagrees")
        payload[-7] = values["handling"] ^ 0x61
        tails[row["record_id"]] = bytes(payload)
    if tails:
        patched = compiler._rebuild_indexed(patched, index, tails)
    patched, role_receipt = rewrite_indexed_native_roles(patched, role_targets)
    old_index, new_index = IndexedFDIFile.from_bytes(original), IndexedFDIFile.from_bytes(patched)
    old_entries = {e.record_id: e for e in old_index.entries}
    new_entries = {e.record_id: e for e in new_index.entries}
    if old_entries.keys() != new_entries.keys():
        raise ValueError("existing native compiler changed fixed JUG directory")
    expected_carriers = {p["carrier_id"] for p in package["players"] if p["id"] in changed_ids}
    if set(replacements) != expected_carriers:
        raise ValueError("existing native compiler changed selected JUG carrier set")
    if any(old_entries[c].decode_payload(original) != new_entries[c].decode_payload(patched)
           for c in old_entries.keys() - expected_carriers):
        raise ValueError("existing native compiler changed an unrelated JUG record")
    preserved_by_carrier = {row["carrier_id"]: row for row in preserved}
    player_by_id = {p["id"]: p for p in subset["players"]}
    for player_id in changed_ids:
        player = player_by_id[player_id]
        carrier = player["carrier_id"]
        before = old_entries[carrier].decode_payload(original)
        after = new_entries[carrier].decode_payload(patched)
        new_native = typed.roster_reader.native_player(after, carrier)
        if new_native["name"].casefold() != player["name"].casefold():
            raise ValueError(f"native player name readback mismatch for {carrier}")
        if new_native["position"] != player["facts"]["primary_position"]:
            raise ValueError(f"native broad-role readback mismatch for {carrier}")
        if [r for r in new_native["roles"] if r != 98] != role_targets[carrier]:
            raise ValueError(f"editorial compatible role readback mismatch for {carrier}")
        old_end = typed.roster_reader.native_player(before, carrier)["name_end"]
        end = new_native["name_end"]
        if before[:8] != after[:8] or before[old_end+9:old_end+10] != after[end+9:end+10]:
            raise ValueError(f"native indexed identity/control bytes changed unexpectedly for {carrier}")
        dob = player["facts"]["birth_date"]
        if isinstance(dob, dict):
            dob_row = preserved_by_carrier.get(carrier, {}).get("fields", {}).get("birth_date")
            if (not dob_row or dob_row["before_hex"] != dob_row["after_hex"]
                    or before[old_end+12:old_end+16] != after[end+12:end+16]):
                raise ValueError(f"native preserved DOB fallback changed for {carrier}")
        else:
            import datetime as dt
            parsed = dt.date.fromisoformat(dob)
            native_date = (after[end+12] ^ 0x61, after[end+13] ^ 0x61,
                int.from_bytes(bytes(v ^ 0x61 for v in after[end+14:end+16]), "little"))
            if native_date != (parsed.day, parsed.month, parsed.year):
                raise ValueError(f"native sourced DOB readback mismatch for {carrier}")
        nationality = player["facts"]["nationality"]
        if isinstance(nationality, dict):
            nat_row = preserved_by_carrier.get(carrier, {}).get("fields", {}).get("nationality")
            if (not nat_row or nat_row["before_hex"] != nat_row["after_hex"]
                    or before[old_end+8] != after[end+8]):
                raise ValueError(f"native preserved nationality fallback changed for {carrier}")
        else:
            expected_country = compiler._country_code(nationality, dict(country_codes))
            if after[end+8] ^ 0x61 != expected_country:
                raise ValueError(f"native sourced nationality readback mismatch for {carrier}")
        if player["carrier_family"] == "dd6361":
            preserve_row = preserved_by_carrier.get(carrier)
            if not preserve_row:
                raise ValueError(f"dd6361 source fallback lacks native compiler preservation receipt: {carrier}")
            # The native compiler itself checked every declared range; assert
            # its exact report remains present for all requested fallback facts.
            wanted = {k for k,v in player["facts"].items()
                      if k != "shirt_number" and isinstance(v, dict)
                      and v.get("policy")=="preserve-existing-mode1"}
            if not wanted <= set(preserve_row["fields"]):
                raise ValueError(f"preserve-mode1 receipt omits selected fields for {carrier}")
            for field in wanted:
                if preserve_row["fields"][field]["before_hex"] != preserve_row["fields"][field]["after_hex"]:
                    raise ValueError(f"mode1 native fallback proof is not byte-identical for {carrier}/{field}")
    return patched


def _postimages():
    release, package, files = _parent()
    data = json.loads(typed.DATA_INPUT.read_text())
    nat = json.loads(typed.NATIONALITY_INPUT.read_text())
    source_proof = typed._verify_source_and_report(data, nat)
    ground_source = registry.ROOT / data["source_bindings"]["2000_01_altrincham_profiles"]["path"]
    ground_text = " ".join(BeautifulSoup(ground_source.read_bytes(), "lxml").get_text(" ", strip=True).split())
    if "Moss Lane" not in ground_text:
        raise ValueError("retained Altrincham period source lacks the Moss Lane ground context")
    claim = _verify_bettney()
    club, slots, macc, macc_old, jentries, eentries, owners, roster3310, macc_roster = _indexes(package, files)
    allocation = typed._assign_carriers(slots, files["JUG98030.FDI"], jentries,
                                        typed._build_desired(data, source_proof["nationality_rows"]))
    desired = [row["replacement"] for row in allocation]
    starters = [p for p in desired if p["membership"] == "starting_xi"]
    if len(starters) != 11 or starters[0]["source_player"]["position"] != "G" or sum(p["source_player"]["position"] == "G" for p in starters) != 1:
        raise ValueError("Alty source allocation does not have exactly one opening goalkeeper")
    repairs = []
    for row in roster3310.rows:
        if row.flag:
            target = next(a for a in allocation if a["carrier_id"] == row.player_record_id)
            repairs.append((row, target))
    if len(repairs) != 1 or repairs[0][0].player_record_id != 10958 or repairs[0][1]["replacement"]["source_person"]["name"] != "Leroy Chambers":
        raise ValueError("only the pre-approved positive Alty 10958/Chambers single-row flag correction is allowed")
    old_374 = {r["3310_native_id"]: r["374_native_id"]
               for r in data["old_3310_to_374_preservation_crosswalk"]["rows"]}
    if len(old_374) != 18 or len(set(old_374.values())) != 18:
        raise ValueError("old Kidderminster 3310 to preserved 374 counterpart crosswalk changed")
    source_id = "alty-joint-input-v1"
    artifact_id = "alty-macc-joint-original-source-v1"
    result = copy.deepcopy(package)
    by_carrier = {p["carrier_id"]: p for p in result["players"]}
    source_club = next(c for c in result["clubs"] if c["carrier_id"] == 3310)
    strength = rating_input.COUNTRY_STRENGTH.get(roster.club_group(source_club), 60)
    for alloc in allocation:
        source_person = alloc["replacement"]
        target = by_carrier[alloc["carrier_id"]]
        replacement = _apply_source_person(target, source_person, alloc["display"]["display_name"],
            artifact_id, strength, alloc["native_after"]["startup_order"],
            jentries[alloc["carrier_id"]].decode_payload(files["JUG98030.FDI"]))
        target.clear(); target.update(replacement)
    bettney_artifact = artifact_id
    target = by_carrier[32951]
    replacement = _bettney_player(target, claim, bettney_artifact, 60,
        jentries[32951].decode_payload(files["JUG98030.FDI"]))
    target.clear(); target.update(replacement)
    source_club.update(name="Altrincham", full_name="Altrincham F.C.", ground_policy="write",
        ground_name="Moss Lane", identity_id=whole.builder._source_club_identity_id("england","Altrincham"),
        roster_player_ids=[alloc["player_id"] for alloc in allocation])
    manager = next(m for m in result["managers"] if m["id"] == source_club["manager_id"])
    manager_source = data["source_bindings"]["mark_ward_wikipedia_revision"]
    manager_source_raw = (registry.ROOT / manager_source["path"]).read_bytes()
    if _sha(manager_source_raw) != manager_source["sha256"]:
        raise ValueError("Mark Ward exact Wikipedia API source changed")
    native_manager_name, _ = manager_display.short_name("Mark Ward")
    if native_manager_name != "Ward":
        raise ValueError("existing manager short-name policy did not select Ward")
    manager.update(name="Mark Ward", policy="write", person_id="manager-wikipedia-mark-ward-1381399721",
        native_names={"surname":"Ward","display_name":"Ward"},
        proof={"artifact_id":artifact_id,"grade":"source-receipt"})
    for pid in [r["carrier_id"] for r in allocation] + [32951]:
        player = by_carrier[pid]
        result["assets"]["portraits"] = [x for x in result["assets"]["portraits"] if x["player_id"] != player["id"]]
        result["assets"]["portraits"].append({"player_id":player["id"],"status":"native-no-photo",
            "proof":{"artifact_id":artifact_id if pid != 32951 else bettney_artifact,"grade":"source-receipt"},
            "review_reason":"Changed player identity; no replacement portrait sourced."})
    result["assets"]["portraits"].sort(key=lambda row: row["player_id"])
    # Keep the whole-club trace small, source-bound and visible to plan readers.
    plan_doc = {"schema":"pm99-private-alty-macc-joint-native-plan-v1",
        "source_release_id":release.release_id,"parent_package_sha256":R210_PACKAGE_SHA256,
        "parent_native_sha256":{k:_sha(files[k]) for k in ("JUG98030.FDI","EQ98030.FDI","ENT98030.FDI","MINIFOTO.PKF")},
        "source_fixture":{"path":typed.FIXTURE_PATH,"sha256":typed.FIXTURE_SHA256,"date":"2000-08-02"},
        "altrincham_source_order":[a["replacement"]["source_person"]["source_player_id"] for a in allocation],
        "allocation":[{"source_name":a["replacement"]["source_player"]["name"],"carrier_id":a["carrier_id"],
                       "display_name":a["display"]["display_name"],"order":a["native_after"]["startup_order"],
                       "broad_position":a["replacement"]["source_player"]["position"],
                       "fine_role_projection":a["replacement"]["source_player"]["position"],
                       "fine_role_policy":"compatible-editorial-default G0/D4/M9/F12; no displaced fine role inherited"} for a in allocation],
        "macc_bettney":{"carrier_id":32951,"provider":"11v11","id":"6310","profile_sha256":claim["profile_sha256"],
                         "profile_path":BETTNEY_PROFILE_PATH,"profile_receipt_sha256":BETTNEY_RECEIPT_PROFILE_SHA256,
                         "match_sha256":claim["match_sha256"],"match_path":BETTNEY_MATCH_PATH,
                         "match_receipt_sha256":BETTNEY_RECEIPT_MATCH_SHA256,
                         "date":"2000-08-12","transfer_date":claim["transfer_date"]},
        "preserve_374_counterparts":sorted(old_374.values()),
        "formation_policy":{"value":"4-3-3","basis":"inferred editorially from source XI broad-role count G+4D+3M+3F",
            "historical_formation_claimed":False,"compatible_role_projection":True,
            "opaque_mode1_native_grid":"preserve existing bytes; supported mode0 tactics reader rejects mode1 and mode1 candidate split remains unproven",
            "tactical_grid_rewritten":False,"runtime_verified":False},
        "only_flag_repair":{"club":3310,"carrier":10958,"slot":8,"before":1,"after":0,
                             "positive_replacement":"Leroy Chambers","source_sha256":typed.FIXTURE_SHA256},
        "dob_nationality_policy":"For source-missing/conflicted DOB and nationality preserve native mode1 bytes and record only explicit fallback provenance; never call native values researched facts.",
        "source_inputs":{"data_input":{"path":registry.relative_workspace_path(typed.DATA_INPUT),"sha256":typed.DATA_INPUT_SHA256},
                         "nationality_report":{"path":registry.relative_workspace_path(typed.NATIONALITY_INPUT),"sha256":typed.NATIONALITY_INPUT_SHA256},
                         "nationality_receipt":{"path":typed.NATIONALITY_RECEIPT,"sha256":typed.NATIONALITY_RECEIPT_SHA256},
        "macc_request":{"path":registry.relative_workspace_path(BETTNEY_REQUEST),"sha256":BETTNEY_REQUEST_SHA256,
                         "usage":"identity/membership request context only; its r207a research-parent field is superseded by this exact r210a binding"},
                         "alty_profile_sources":data["source_bindings"]},
        "manager":{"id":807,"source":"Wikipedia API revision 1381399721","source_sha256":manager_source["sha256"],"native_display":"Ward"},
        "runtime_or_publication":False}
    # Persist one small private source artifact and reference it from the
    # package's source/proof graph; native bytes remain in-memory only.
    plan_path = HERE / "altrincham-macc-joint-native-plan-v1.json"
    plan_bytes = package_v2.canonical_json_bytes(plan_doc) + b"\n"
    plan_digest = _sha(plan_bytes)
    artifact = {"id": artifact_id, "kind":"season-input", "sha256":plan_digest,
                "media_type":"application/json", "relative_path":plan_path.name}
    result["artifacts"].append(artifact)
    result["artifacts"].sort(key=lambda row:row["id"])
    result["sources"].append({"id":source_id,"title":"Altrincham observed August friendly cohort plus joint Macc Bettney correction",
        "uri":"https://hedgegrower.blogspot.com/2026/08/this-week-in-county-history-2000.html",
        "proof_grade":"source-receipt","evidence_artifact_id":artifact_id})
    result["sources"].sort(key=lambda row:row["id"])
    result["proofs"].append({"id":"proof-"+artifact_id,"artifact_id":artifact_id,
        "grade":"source-receipt","covers":["Altrincham original friendly 11+6+1 membership and exclusive allocation",
            "Macc Bettney exact 11v11 identity and dated used-sub evidence","atomic 3310 label/roster/manager correction"]})
    result["proofs"].sort(key=lambda row:row["id"])
    source_club["proof"]={"artifact_id":artifact_id,"grade":"source-receipt"}
    package_v2.validate_package(result,strict=False)
    # Compile only the selected player records through the existing native player compiler.
    changed_ids={by_carrier[pid]["id"] for pid in [a["carrier_id"] for a in allocation]+[32951]}
    countries=compiler._extract_country_codes_from_textos(release.game_path/"DBDAT/TEXTOS.PKF")
    jug=_compile_changed_players(files["JUG98030.FDI"],result,changed_ids,countries)
    # Caller-side complete safety proof for lower-level order writer, which supports this mixed family set.
    before_eq_idx=IndexedFDIFile.from_bytes(files["EQ98030.FDI"])
    owners_now={}
    for ent in before_eq_idx.entries:
        raw=files["EQ98030.FDI"][ent.payload_offset:ent.payload_offset+ent.payload_length]
        parsed=parse_eq_external_team_roster_payload(raw,{})
        if parsed:
            for row in parsed.rows: owners_now.setdefault(row.player_record_id,set()).add(ent.record_id)
    if any(owners_now.get(a["carrier_id"])!={3310} for a in allocation):
        raise ValueError("preorder caller guard: every Alty carrier must have exclusive EQ3310 owner")
    # Exact temporary-file API clears only flag byte 10958, slot 9, from this bound preimage.
    with tempfile.TemporaryDirectory(prefix="alty-eq-flag-") as tmp:
        t=Path(tmp); eqp=t/"EQ98030.FDI"; jugp=t/"JUG98030.FDI"
        eqp.write_bytes(files["EQ98030.FDI"]); jugp.write_bytes(files["JUG98030.FDI"])
        from app.editor_actions import edit_team_roster_eq_jug_linked
        edit_team_roster_eq_jug_linked(team_file=str(eqp),player_file=str(jugp),eq_record_id=3310,
            slot_number=9,flag=0,write_changes=True)
        eq_cleared=eqp.read_bytes()
    old_entry=eentries[3310]
    differences=[i for i,(x,y) in enumerate(zip(files["EQ98030.FDI"],eq_cleared)) if x!=y]
    if differences != [old_entry.payload_offset+repairs[0][0].raw_row_offset]:
        raise ValueError("existing EQ writer changed more than the one approved flag byte")
    ordered=[a["carrier_id"] for a in allocation]
    eq=whole.rewrite_roster(eq_cleared,3310,ordered)
    # Indexed EQ label writer composes on the already verified row/order result.
    idx=IndexedFDIFile.from_bytes(eq); entry=next(e for e in idx.entries if e.record_id==3310)
    payload=entry.decode_payload(eq)
    labeled,changes=_patch_indexed_eq_team_string_payload(payload,short_name="Altrincham",
        stadium_name="Moss Lane",full_club_name="Altrincham F.C.")
    eq=delta.compiler._rebuild_indexed(eq,idx,{3310:labeled})
    # Startup orders reflect the full observed friendly order; no Macc carrier order changes.
    read_index=IndexedFDIFile.from_bytes(jug); entries={e.record_id:e for e in read_index.entries}
    order_changes=[]
    byorder={a["carrier_id"]:a["native_after"]["startup_order"] for a in allocation}
    for a in allocation:
        pid=a["carrier_id"]; raw=entries[pid].decode_payload(jug); current=read_initial_order(raw)
        order_changes.append(OrderReplacement(pid,current.name,current.order,byorder[pid]))
    # Require one keeper at native order 1 after the source role compiler pass.
    indexed=IndexedFDIFile.from_bytes(jug); entries={e.record_id:e for e in indexed.entries}
    from scripts.season_historical_roster_audit_v1 import native_player
    goalkeepers=[]
    for row in order_changes:
        payload=entries[row.record_id].decode_payload(jug)
        view=native_player(payload,row.record_id)
        if view["position"]=="G" and row.after<=11: goalkeepers.append(row.after)
    if goalkeepers != [1]:
        raise ValueError(f"native source XI must have only its keeper in order 1; got {goalkeepers}")
    jug=patch_initial_orders(jug,order_changes,allow_compact=True)
    final_index=IndexedFDIFile.from_bytes(jug)
    final_entries={e.record_id:e for e in final_index.entries}
    for row in order_changes:
        actual=read_initial_order(final_entries[row.record_id].decode_payload(jug))
        if actual.name != row.expected_name or actual.order != row.after:
            raise ValueError(f"existing lower-level order writer readback mismatch for {row.record_id}")
    # ENT manager writer and owner graph guard.
    manager_holders, manager_names=whole._manager_graph(eq_path=release.game_path/"DBDAT/EQ98030.FDI",
        ent_path=release.game_path/"DBDAT/ENT98030.FDI")
    if [c["carrier_id"] for c in manager_holders.get(807,[])] != [3310] or manager_names.get(807)!="Graham Allner":
        raise ValueError("manager 807 exact exclusive preimage changed")
    entidx=IndexedFDIFile.from_bytes(files["ENT98030.FDI"]); me=next(e for e in entidx.entries if e.record_id==807)
    ent_payload=compiler._patch_ent_name(me.decode_payload(files["ENT98030.FDI"]),807,
        compiler._pm99_text("Mark Ward",label="dated Alty manager"),native_names={"surname":"Ward","display_name":"Ward"})
    ent=delta.compiler._rebuild_indexed(files["ENT98030.FDI"],entidx,{807:ent_payload})
    archive, photo_offsets=delta.no_photo_archive(files["MINIFOTO.PKF"],
        {a["carrier_id"] for a in allocation}|{32951})
    # Verify exact fixed directories and unrelated decoded payloads.
    whole.preserve_other_records(files["JUG98030.FDI"],jug,{a["carrier_id"] for a in allocation}|{32951})
    whole.preserve_other_records(files["EQ98030.FDI"],eq,{3310})
    whole.preserve_other_records(files["ENT98030.FDI"],ent,{807})
    neweq=IndexedFDIFile.from_bytes(eq); team=next(e for e in neweq.entries if e.record_id==3310)
    afterroster=parse_eq_external_team_roster_payload(eq[team.payload_offset:team.payload_offset+team.payload_length],{})
    if [r.player_record_id for r in afterroster.rows] != ordered or any(r.flag for r in afterroster.rows):
        raise ValueError("3310 final EQ row order/zero-flag readback differs")
    native_club=extract_team_labels(team.decode_payload(eq))
    if native_club != ("Altrincham","Moss Lane","Altrincham F.C."):
        raise ValueError(f"3310 label readback differs: {native_club}")
    # Verify manager readback on in-memory postimage.
    with tempfile.TemporaryDirectory(prefix="alty-manager-readback-") as tmp:
        temp_eq, temp_ent = Path(tmp)/"EQ98030.FDI", Path(tmp)/"ENT98030.FDI"
        temp_eq.write_bytes(eq); temp_ent.write_bytes(ent)
        after_holders, after_names=whole._manager_graph(eq_path=temp_eq,ent_path=temp_ent)
    if after_names.get(807)!="Ward" or [c["carrier_id"] for c in after_holders.get(807,[])] != [3310]:
        raise ValueError("native Mark Ward manager name/owner readback failed")
    return {"package":result,"native_files":{"JUG98030.FDI":jug,"EQ98030.FDI":eq,
                "ENT98030.FDI":ent,"MINIFOTO.PKF":archive},
        "plan":plan_doc,"plan_path":plan_path,"plan_bytes":plan_bytes,
        "allocation":allocation,"photo_offsets":photo_offsets,
        "parent_release":release,"source_claim":claim,"equal_label_changes":changes}


def extract_team_labels(payload: bytes) -> tuple[str,str,str]:
    from app.editor_actions import _read_eq_inline_string
    sig=payload.find(b"\xdd\x63\x61")
    cursor=sig+4
    short,_,cursor=_read_eq_inline_string(payload,cursor)
    stadium,_,cursor=_read_eq_inline_string(payload,cursor)
    cursor+=2
    full,_,_= _read_eq_inline_string(payload,cursor)
    return short,stadium,full


