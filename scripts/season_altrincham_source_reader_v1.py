"""Private typed Altrincham source reader and whole-club allocation proposal.

Uses the existing fixed-capacity whole-club recipe/native helper contracts as
the proposal shape. This reader is PREPARE-ONLY: it does not invoke the
Soccerbase source verifier, compile a package, or write game bytes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from app.editor_actions import _patch_indexed_player_variable_name_payload
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import read_initial_order
from scripts import prepare_duplicate_club_disposition_v1 as allocation_core
from scripts import season_duplicate_ownership_delta_v1 as ownership_delta
from scripts import season_historical_roster_audit_v1 as roster_reader
from scripts import season_release_registry_v1 as registry
from scripts import season_within_club_reserve_repair_v1 as native_facts
from scripts.prepare_duplicate_whole_club_native_v1 import _manager_graph

HERE = Path(__file__).resolve().parent
DATA_INPUT = (registry.ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/"
              "resume-qa/altrincham-18-data-proposal-v1/altrincham-18-data-input-proposal-v1.json")
NATIONALITY_INPUT = (registry.ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/"
                     "resume-qa/altrincham-nationality-evidence-v1/"
                     "altrincham-3310-nationality-evidence-v1.json")
DATA_INPUT_SHA256 = "fb4cecba82ae6029ac0ec78dca09bd3a5cf9562fd1e1040d4e306a99d5dd7434"
NATIONALITY_INPUT_SHA256 = "a5abf3e733e8277d705abc75d6f271793469f7bc4ac7e6853fee1956afc65e7e"
NATIONALITY_RECEIPT = (".local/consolidated-audit-20261009/parallel-rc-20261023/"
                       "resume-qa/altrincham-nationality-evidence-v1/"
                       "altrincham-3310-nationality-evidence-v1-final-receipt.json")
NATIONALITY_RECEIPT_SHA256 = "a08acc6a40695f3476bd425bcb0098345e95e49bd3310865cff0ea46ab146872"
EXPANSION_SHA256 = "d056f3b4d3f0ebee9a3954b5b98ac2350abe1ef27709a742efbc447e4bfde890"
PARENT_RELEASE = "sourced-walsall-opening-ownership-20261023-r207a"
PARENT_PACKAGE_SHA256 = "f6881696402a410362b7f80cfe6e499a1524c99a2c9deed74d96c278842479ae"
PARENT_JUG_SHA256 = "ed0334b43fc1edbeccc9db6533689eda02fc1d413931a6c0af9071ea10cb4d88"
PARENT_EQ_SHA256 = "ed137403df4f1ed498800d0621548645ccfd94bde332d8194b184b66aa2b7482"
FIXTURE_PATH = (".local/consolidated-audit-20261009/parallel-rc-20261023/"
                "resume-qa/kidderminster-3310-coherent-allocation-investigation-v4/"
                "sources/altrincham-stockport-friendly-2000-08-02.html")
FIXTURE_SHA256 = "d15419b9aceabe8cafdbf25bd0bebba650df2460647a8575f1f014d9e67b1edf"
ALTY_NAMESPACE = "altrincham-aug02-source-row"
IDENTITY_POLICY = "original-altrincham-aug02-friendly-full-name-row-v1"
UNKNOWN_DOB_POLICY = "preserve-existing-mode1-explicit-unpublished-or-conflicted-dob-v1"
UNKNOWN_COUNTRY_POLICY = "deterministic-XXX-explicit-nationality-unavailable-v1"
KIND = "complete-aug02-18-person-altrincham-whole-club-replacement-v1"

EXPECTED_NAMES = [
    "Stuart Coburn", "Barry Crowe", "Danny Adams", "Mark Maddix", "Gary Talbot",
    "Steve Hawes", "Stuart Quinn", "Stuart Scheuber", "Richard Landon",
    "Leroy Chambers", "Kevin Ellison", "Jason Gallagher", "Adam Farley", "Mark Ward",
    "Paul Walsham", "Carl Furlong", "Scott Wilson", "Mark O'Connor",
]
STARTERS = EXPECTED_NAMES[:11]
USED_SUBS = EXPECTED_NAMES[11:17]
UNUSED_KEEPER = EXPECTED_NAMES[17]
DOB_CONFLICTS = {
    "Stuart Coburn": {
        "selected_period_profile_claim": "1975-05-05",
        "counterclaim": "Transfermarkt discovery profile gives 1976-05-05; no identity-linked nationality accepted.",
    },
    "Mark Maddix": {
        "selected_period_profile_claim": "1973-03-11",
        "counterclaim": "The Altrincham profile spells the name Maddox; Soccerbase discovery DOB is 1973-03-01.",
    },
    "Leroy Chambers": {
        "selected_period_profile_claim": "1974-02-25",
        "counterclaim": "Wikipedia discovery claims Leroy Dean Chambers, 1972-10-25; identity unresolved.",
    },
}
UNAVAILABLE_DOB = {"Paul Walsham", "Scott Wilson", "Mark O'Connor"}
EXPLICIT_ENG = {
    "Danny Adams", "Steve Hawes", "Stuart Quinn", "Richard Landon",
    "Kevin Ellison", "Adam Farley", "Mark Ward",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(path: str, digest: str, *, receipt_path: str | None = None,
           receipt_sha256: str | None = None) -> bytes:
    target = registry.ROOT / path
    registry.relative_workspace_path(target)
    data = target.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"bound source bytes changed: {path}")
    if receipt_path is not None:
        receipt_file = registry.ROOT / receipt_path
        registry.relative_workspace_path(receipt_file)
        if _sha(receipt_file) != receipt_sha256:
            raise ValueError(f"source receipt hash changed: {receipt_path}")
        receipt = json.loads(receipt_file.read_text())
        recorded = receipt.get("body_sha256", receipt.get("sha256"))
        receipt_body = receipt.get("body_path", receipt.get("local_path"))
        if recorded != digest or receipt_body not in (path, Path(path).name):
            raise ValueError(f"source receipt does not bind exact body: {path}")
    return data


def _role_code(player: dict) -> tuple[str, str]:
    broad = (player.get("source_facts", {}).get("broad_role") or "").casefold()
    if "goalkeeper" in broad:
        return "G", "profile-stated-broad-goalkeeper"
    if "defender" in broad:
        return "D", "profile-stated-broad-defender"
    if "midfielder" in broad:
        return "M", "profile-stated-broad-midfielder"
    if "forward" in broad or "striker" in broad:
        return "F", "profile-stated-broad-forward"
    if player.get("source_name") == "Paul Walsham":
        return "M", "editorial-compatible-position-of-Stuart-Quinn-he-replaced"
    raise ValueError(f"no conservative broad role or explicit editorial mapping for {player.get('source_name')}")


def validate_typed_input(data: dict, nationality_doc: dict) -> None:
    """Fail-closed data/fallback gates; pure so adversarial negatives are cheap."""
    if data.get("schema") != "pm99-altrincham-2000-01-opening-18-data-proposal-v1":
        raise ValueError("unexpected private Altrincham typed source input")
    rows = data.get("players")
    if not isinstance(rows, list) or len(rows) != 18:
        raise ValueError("Altrincham source cohort must contain exactly 18 rows")
    if [row.get("source_name") for row in rows] != EXPECTED_NAMES:
        raise ValueError("source rows differ from exact dated ordered XI/used/unused cohort")
    cohort = data.get("ordered_fixture_cohort", {})
    if (cohort.get("starting_xi") != STARTERS or cohort.get("used_substitutes") != USED_SUBS
            or cohort.get("selected_unused") != [UNUSED_KEEPER]
            or cohort.get("capacity_excluded") != ["Phil Power"]):
        raise ValueError("Altrincham 11+6+first-unused source count/order changed")
    roles = {row["source_name"]: _role_code(row)[0] for row in rows}
    if sum(roles[name] == "G" for name in STARTERS) != 1 or roles[STARTERS[0]] != "G":
        raise ValueError("target source XI must have one goalkeeper, first in original lineup")
    unknown_policy = data.get("unknown_and_editorial_fact_policy", {})
    dob_policy = unknown_policy.get("birth_date", "")
    country_policy = unknown_policy.get("nationality", "")
    if "deterministic-default fallback" not in dob_policy or "never label it researched DOB" not in dob_policy:
        raise ValueError("missing DOB must use a declared existing fallback policy, not a factual date")
    if ("do not infer from birthplace" not in country_policy.casefold()
            or "deterministic-default/fallback" not in country_policy):
        raise ValueError("unknown nationality must have explicit logged fallback and no birthplace inference")
    if nationality_doc.get("schema") != "pm99-altrincham-3310-nationality-evidence-v1":
        raise ValueError("unexpected Altrincham nationality evidence schema")
    accepted = {x["candidate"] for x in nationality_doc.get("positive_explicit_nationalities", [])
                if x.get("nationality") == "ENG"}
    if accepted != EXPLICIT_ENG:
        raise ValueError("explicit English nationality set differs from exact reviewed cohort")
    macc = data.get("transaction_scope", {}).get("joint_macc_adams_resolution", {})
    if (macc.get("state") != "pending" or "never create second Danny Adams" not in macc.get("dependency", "")):
        raise ValueError("Altrincham request must stay blocked pending the linked Macc Bettney/Danny resolution")


def require_joint_adams_resolution(data: dict) -> None:
    macc = data.get("transaction_scope", {}).get("joint_macc_adams_resolution", {})
    if macc.get("state") != "source-native-correction-verified" or not macc.get("verification_receipt"):
        raise ValueError("native allocation blocked until the Macc Bettney/Danny correction is independently verified")


def _check_nationality_sources(nat_doc: dict) -> dict[str, dict]:
    result = {}
    for row in nat_doc.get("positive_explicit_nationalities", []):
        source = row["source"]
        raw = _bound(source["body_path"], source["body_sha256"],
                     receipt_path=source["receipt_path"], receipt_sha256=source["receipt_sha256"])
        page = BeautifulSoup(raw, "lxml")
        text = " ".join(page.get_text(" ", strip=True).split())
        explicit_english = (re.search(r"\bNationality\s*:?\s*(?:English|England)\b", text, re.I)
                            or re.search(r"\bis an English\b", text, re.I)
                            or re.search(r"\bis a[n]? English\b", text, re.I))
        if (row["nationality"] != "ENG" or not row["candidate"]
                or row["candidate"].split()[-1].casefold() not in text.casefold()
                or not explicit_english):
            raise ValueError("explicit ENG source no longer parses to the exact claim")
        result[row["candidate"]] = copy.deepcopy(row)
    return result


def _local_identity_key(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    if not slug:
        raise ValueError("Altrincham source row has no stable local name key")
    return f"{ALTY_NAMESPACE}:2000-08-02:{slug}"


def _candidate_display_options(name: str) -> list[tuple[str, str]]:
    family = name.split()[-1]
    choices = [(name, "exact-full-name-from-dated-Alty-fixture")]
    if family.casefold() != name.casefold():
        choices.append((family, "family-only-display-component-from-dated-name"))
    return choices


def _build_desired(data: dict, nationality_rows: dict[str, dict]) -> list[dict]:
    output = []
    for row in data["players"]:
        name = row["source_name"]
        position, role_basis = _role_code(row)
        if name in DOB_CONFLICTS:
            dob = None
            dob_status = "selected-period-profile-DOB-retained-as-conflict-only-not-verified"
        elif name in UNAVAILABLE_DOB:
            dob = None
            dob_status = "not-published-or-not-linked; unknown"
        else:
            dob = row["source_facts"].get("birth_date")
            if not isinstance(dob, str):
                raise ValueError(f"unexpected missing DOB policy row: {name}")
            dob_status = "retained-period-profile-DOB"
        nationality = "ENG" if name in nationality_rows else None
        person = {
            "source_player_id": _local_identity_key(name),
            "source_provider": "altrincham-aug02-source-row",
            "name": name,
            "given_name": name.split()[0],
            "family_name": name.split()[-1],
            "birth_date": dob,
            "identity_policy": IDENTITY_POLICY,
            "identity_evidence": {
                "policy": IDENTITY_POLICY,
                "fixture_path": FIXTURE_PATH,
                "fixture_sha256": FIXTURE_SHA256,
                "fixture_date": "2000-08-02",
                "raw_name": name,
                "local_profile_sources": [
                    {k: data["source_bindings"][source_id].get(k)
                     for k in ("path", "sha256", "url", "receipt_path", "receipt_sha256")
                     if k in data["source_bindings"][source_id]}
                    for source_id in row["evidence_source_ids"]
                    if source_id in data["source_bindings"]
                ],
                "dob_claim_status": dob_status,
                "dob_counterclaim": copy.deepcopy(DOB_CONFLICTS.get(name)),
                "nationality_source": copy.deepcopy(nationality_rows.get(name)),
            },
        }
        source_player = {
            "name": name,
            "birth_date": dob,
            "position": position,
            "nationality": nationality,
            "height_cm": None,
            "weight_kg": None,
            "membership": row["dated_status"],
        }
        fallback = {}
        if dob is None:
            fallback["birth_date"] = {
                "policy": UNKNOWN_DOB_POLICY,
                "method": "preserve-existing-mode1",
                "native_value_is_not_identity_fact": True,
                "source_claim": copy.deepcopy(DOB_CONFLICTS.get(name)),
            }
        if nationality is None:
            fallback["nationality"] = {
                "policy": UNKNOWN_COUNTRY_POLICY,
                "method": "deterministic-default",
                "value": "XXX",
                "not_a_citizenship_claim": True,
            }
        fallback["height_cm"] = {"method": "preserve-existing-mode1", "source_claim": None}
        fallback["weight_kg"] = {"method": "preserve-existing-mode1", "source_claim": None}
        fallback["shirt_number"] = {"method": "preserve-existing-mode1", "source_claim": None}
        output.append({
            "source_person": person,
            "source_player": source_player,
            "membership": ("starting_xi" if name in STARTERS else
                           "published_bench" if name in USED_SUBS else
                           "published_unused_bench"),
            "membership_source": {"path": FIXTURE_PATH, "sha256": FIXTURE_SHA256,
                                  "date": "2000-08-02", "source_family": "Altrincham/Stockport friendly archive"},
            "raw_evidence": {
                "source_family": "altrincham-club-archive-plus-dated-stockport-friendly",
                "source_name": name,
                "role_projection": {"position": position, "basis": role_basis,
                                    "historical_fine_role_claimed": False},
                "fact_fallbacks": fallback,
                "ratings_policy": "existing editor editorial calibration; never inherit the displaced Kidderminster player's ratings as identity fact",
            },
        })
    return output


def _native_parent_and_slots():
    release = registry.load_registered_release("2000-01", PARENT_RELEASE)
    if release.release_id != PARENT_RELEASE:
        raise ValueError("r207a research parent registration changed")
    package_path = release.package_path
    jug_path = release.game_path / "DBDAT/JUG98030.FDI"
    eq_path = release.game_path / "DBDAT/EQ98030.FDI"
    if (registry.canonical_document_sha256(package_path) != PARENT_PACKAGE_SHA256
            or registry.sha256_file(jug_path) != PARENT_JUG_SHA256
            or registry.sha256_file(eq_path) != PARENT_EQ_SHA256):
        raise ValueError("explicit r207a research package/JUG/EQ pin changed")
    package = json.loads(package_path.read_text())
    club = next((c for c in package["clubs"] if c.get("carrier_id") == 3310), None)
    if club is None or club["id"] != "club-3310" or club["manager_id"] != "manager-807":
        raise ValueError("r207a exact duplicate club/manager target changed")
    slots = sorted((copy.deepcopy(p) for p in package["players"] if p["club_id"] == club["id"]),
                   key=lambda p: p["carrier_id"])
    if len(slots) != 18 or len({p["carrier_id"] for p in slots}) != 18:
        raise ValueError("r207a Kidderminster 3310 target is not exact 18 unique slots")
    jug = jug_path.read_bytes()
    eq = eq_path.read_bytes()
    jindex = IndexedFDIFile.from_bytes(jug)
    jentries = {e.record_id: e for e in jindex.entries}
    if not set(p["carrier_id"] for p in slots) <= set(jentries):
        raise ValueError("one or more exact 3310 player records is absent")
    eq_index = IndexedFDIFile.from_bytes(eq)
    eentries = {e.record_id: e for e in eq_index.entries}
    ee = eentries.get(3310)
    roster = parse_eq_external_team_roster_payload(eq[ee.payload_offset:ee.payload_offset + ee.payload_length], {})
    expected_ids = {p["carrier_id"] for p in slots}
    if (roster is None or roster.mode_byte != 1 or len(roster.rows) != 18
            or {row.player_record_id for row in roster.rows} != expected_ids):
        raise ValueError("3310 native target must be exact 18-row visible mode1")
    roster_flags = {row.player_record_id: row.flag for row in roster.rows}
    flag_repairs = []
    for row in roster.rows:
        if row.flag:
            flag_offset = ee.payload_offset + row.raw_row_offset
            flag_repairs.append({"club_carrier_id": 3310, "player_record_id": row.player_record_id,
                                 "slot_index": row.slot_index, "flag_before": row.flag,
                                 "physical_flag_offset": flag_offset, "stored_byte_before": eq[flag_offset],
                                 "source_row_bytes_before": eq[flag_offset:flag_offset + 5].hex()})
    all_owners: dict[int, set[int]] = {}
    for entry in eq_index.entries:
        raw = eq[entry.payload_offset:entry.payload_offset + entry.payload_length]
        current = parse_eq_external_team_roster_payload(raw, {})
        if current is None:
            continue
        for row in current.rows:
            all_owners.setdefault(row.player_record_id, set()).add(entry.record_id)
    if any(all_owners.get(carrier) != {3310} for carrier in expected_ids):
        raise ValueError("Altrincham allocation carriers must be exact exclusive 3310 owners")
    manager_holders, manager_names = _manager_graph(eq_path=eq_path, ent_path=release.game_path / "DBDAT/ENT98030.FDI")
    if [c.get("carrier_id") for c in manager_holders.get(807, [])] != [3310]:
        raise ValueError("manager 807 must be the exclusive current owner under 3310")
    if manager_names.get(807) != "Graham Allner":
        raise ValueError("r207a native manager 807 preimage display differs")
    raw_manager = (release.game_path / "DBDAT/ENT98030.FDI").read_bytes()
    return release, package, club, slots, jug, eq, jentries, all_owners, manager_names, roster_flags, flag_repairs


def _assign_carriers(slots: list[dict], jug: bytes, jentries: dict[int, object], desired: list[dict]) -> list[dict]:
    costs = [[None for _ in desired] for _ in slots]
    choices: dict[tuple[int, int], tuple[str, str, str, int, str]] = {}
    slot_info = []
    for i, slot in enumerate(slots):
        carrier = slot["carrier_id"]
        payload = jentries[carrier].decode_payload(jug)
        native = roster_reader.native_player(payload, carrier)
        startup = read_initial_order(payload)
        if startup.family not in ("dd6360", "dd6361"):
            raise ValueError(f"carrier {carrier} has unsupported native order family {startup.family}")
        old_position = native["position"]
        slot_info.append({"carrier_id": carrier, "player_id": slot["id"],
                          "native_order_before": startup.order, "native_name_before": native["name"],
                          "native_position_before": old_position, "payload_sha256": hashlib.sha256(payload).hexdigest()})
        for j, replacement in enumerate(desired):
            source = replacement["source_player"]
            chosen = None
            for display, method in _candidate_display_options(source["name"]):
                try:
                    changed, _meta = _patch_indexed_player_variable_name_payload(payload, native["name"], display)
                    readback = roster_reader.native_player(changed, carrier)["name"]
                    if roster_reader.normalise(readback) != roster_reader.normalise(display):
                        continue
                    chosen = (display, method)
                    break
                except (ValueError, RuntimeError, UnicodeError):
                    continue
            if chosen is None:
                continue
            src_role = source["position"]
            same_role = src_role == old_position
            # Prefer source-exact full display, keep compatible broad native
            # roles where possible, then use stable carrier/source order.
            penalty = 10000 * (not same_role) + 500 * (chosen[0] != source["name"]) + abs(i - j)
            costs[i][j] = penalty
            choices[i, j] = (chosen[0], chosen[1], native["name"], startup.order, old_position)
    assignment = allocation_core.minimum_assignment(costs)
    used = set()
    by_source_order = {}
    for slot_index, desired_index in enumerate(assignment):
        slot = slots[slot_index]
        replacement = desired[desired_index]
        display, method, old_name, old_order, old_position = choices[slot_index, desired_index]
        carrier = slot["carrier_id"]
        target_order = desired_index + 1
        if carrier in used:
            raise ValueError("native allocation repeats a source carrier")
        used.add(carrier)
        by_source_order[desired_index] = {
            "player_id": slot["id"], "carrier_id": carrier,
            "before_recipe": slot,
            "replacement": replacement,
            "display": {"source_name": replacement["source_player"]["name"],
                        "display_name": display, "method": method,
                        "display_projection": "source full name or exact last-name component from the dated full name; no invented alias"},
            "native_before": {"name": old_name, "position": old_position, "startup_order": old_order,
                              "payload_sha256": slot_info[slot_index]["payload_sha256"]},
            "native_after": {"broad_position": replacement["source_player"]["position"],
                             "startup_order": target_order,
                             "startup_order_policy": "complete original fixture order 1..18; exact XI first"},
        }
    if len(used) != 18:
        raise ValueError("source allocation failed to cover all fixed 3310 carriers")
    return [by_source_order[i] for i in range(len(desired))]


def _verify_source_and_report(data: dict, nat_doc: dict) -> dict:
    validate_typed_input(data, nat_doc)
    if _sha(DATA_INPUT) != DATA_INPUT_SHA256:
        raise ValueError("typed Altrincham data input changed")
    if _sha(NATIONALITY_INPUT) != NATIONALITY_INPUT_SHA256:
        raise ValueError("nationality evidence report differs from the locally retained exact revision")
    receipt_path = registry.ROOT / NATIONALITY_RECEIPT
    if _sha(receipt_path) != NATIONALITY_RECEIPT_SHA256:
        raise ValueError("nationality report revision receipt changed")
    nat_receipt = json.loads(receipt_path.read_text())
    if (nat_receipt.get("current_report_path") != registry.relative_workspace_path(NATIONALITY_INPUT)
            or nat_receipt.get("current_report_sha256") != NATIONALITY_INPUT_SHA256
            or nat_receipt.get("superseded_by_current_report") is not True):
        raise ValueError("nationality corrected-report receipt does not bind current report")
    parent = data["transaction_scope"]["parent_rebase"]["source_expansion_parent"]
    expansion_path = registry.ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/altrincham-3310-source-expansion-v1/altrincham-3310-source-expansion-v1.json"
    if _sha(expansion_path) != EXPANSION_SHA256 or parent.get("source_expansion_sha256") != EXPANSION_SHA256:
        raise ValueError("original Altrincham source-expansion basis changed")
    fixture_raw = _bound(FIXTURE_PATH, FIXTURE_SHA256,
        receipt_path=(FIXTURE_PATH + ".source.json"),
        receipt_sha256="63421a573889329a8a91fad43b5ad6b3d21adf52994fb935c20f51aefc20c910")
    fixture = BeautifulSoup(fixture_raw, "lxml")
    text = " ".join(fixture.get_text(" ", strip=True).split())
    for name in EXPECTED_NAMES + ["Phil Power"]:
        if name not in text:
            raise ValueError(f"exact Alty source lineup name missing from original fixture: {name}")
    if "Unused Sub(s): Mark O'Connor, Phil Power" not in text:
        raise ValueError("source unused substitute ordering/capacity row changed")
    nat_rows = _check_nationality_sources(nat_doc)
    # Profile inputs are pinned to exact original bodies + capture receipts.
    profile_sources = data["source_bindings"]
    for key in ("2000_01_altrincham_profiles", "departed_player_biographies", "season_appearances_matrix"):
        row = profile_sources[key]
        raw = _bound(row["path"], row["sha256"], receipt_path=row["receipt_path"],
                     receipt_sha256=row["receipt_sha256"])
        if not raw:
            raise ValueError(f"empty profile/appearance source: {key}")
    manager = profile_sources["mark_ward_wikipedia_revision"]
    raw_manager = _bound(manager["path"], manager["sha256"], receipt_path=manager["receipt_path"],
                         receipt_sha256=manager["receipt_sha256"])
    manager_doc = json.loads(raw_manager)
    pages = manager_doc.get("query", {}).get("pages", [])
    revisions = [r for page in pages if page.get("pageid") == 2874712 for r in page.get("revisions", [])
                 if r.get("revid") == 1381399721]
    if len(revisions) != 1:
        raise ValueError("exact retained Mark Ward API revision 1381399721 missing")
    content = revisions[0].get("slots", {}).get("main", {}).get("content", "")
    if not all(x in content for x in ("| manager_years1  = 2000–2001", "| manager_clubs1  = [[Altrincham F.C.|Altrincham]]")):
        raise ValueError("Mark Ward manager fields differ in exact retained API revision")
    return {"fixture": text, "nationality_rows": nat_rows, "manager_wikitext": content}


def prepare_proposal() -> dict:
    data = json.loads(DATA_INPUT.read_text())
    nat_doc = json.loads(NATIONALITY_INPUT.read_text())
    source_proof = _verify_source_and_report(data, nat_doc)
    release, package, before_club, slots, jug, eq, jentries, owners, manager_names, roster_flags, flag_repairs = _native_parent_and_slots()
    desired = _build_desired(data, source_proof["nationality_rows"])
    allocation = _assign_carriers(slots, jug, jentries, desired)
    for repair in flag_repairs:
        admitted = next((r for r in allocation if r["carrier_id"] == repair["player_record_id"]), None)
        if admitted is None or not admitted["replacement"].get("membership_source", {}).get("sha256") == FIXTURE_SHA256:
            raise ValueError("nonzero EQ row can be source-cleared only for its positively admitted Alty fixture person")
        repair["replacement_source_name"] = admitted["replacement"]["source_player"]["name"]
        repair["replacement_source_person_id"] = admitted["replacement"]["source_person"]["source_player_id"]
        repair["replacement_membership"] = admitted["replacement"]["membership"]
    by_name = {row["replacement"]["source_person"]["name"]: row for row in allocation}
    starters = [by_name[name] for name in STARTERS]
    if (sum(r["replacement"]["source_player"]["position"] == "G" for r in starters) != 1
            or starters[0]["replacement"]["source_player"]["name"] != "Stuart Coburn"
            or starters[0]["native_after"]["startup_order"] != 1):
        raise ValueError("selected Altrincham XI must map exactly one keeper to slot one")
    source_ids = [p["source_person"]["source_player_id"] for p in desired]
    if len(set(source_ids)) != 18:
        raise ValueError("Altrincham local source-row identity keys are not unique")
    crosswalk = data["old_3310_to_374_preservation_crosswalk"]
    if crosswalk.get("row_count") != 18 or len(crosswalk.get("rows", [])) != 18:
        raise ValueError("old 3310 to canonical 374 preservation counterpart map is incomplete")
    old_to_374 = {r["3310_native_id"]: r["374_native_id"] for r in crosswalk["rows"]}
    if len(old_to_374) != 18 or len(set(old_to_374.values())) != 18:
        raise ValueError("3310 source actor counterpart mapping is not one-to-one")
    manager = data["manager"]
    return {
        "schema_version": "pm99-duplicate-whole-club-disposition-source-plan-v1",
        "proposal_kind": KIND,
        "source_adapter": "altrincham-aug02-source-row-v1",
        "source_family": "Altrincham club archive and dated Stockport County friendly report",
        "season": "2000-01",
        "release_id": PARENT_RELEASE,
        "package_sha256": PARENT_PACKAGE_SHA256,
        "jug_sha256": PARENT_JUG_SHA256,
        "eq_sha256": PARENT_EQ_SHA256,
        "execution_binding_status": "r207a research-only; must be retargeted to preferred post-Horne r210 exact parent before canonical prepare",
        "before_club": before_club,
        "new_club": "Altrincham",
        "source_target": {
            "carrier_id": 3310,
            "source_club_name": "Altrincham F.C.",
            "cohort_type": "observed 2000-08-02 friendly participants; not an official registered roster",
            "roster_count": 18,
            "source_order_ids": [p["source_person"]["source_player_id"] for p in desired],
        },
        "original_opening": {
            "fixture": {"date": "2000-08-02", "opponent": "Stockport County", "competition": "friendly",
                        "starting_xi": STARTERS, "used_substitutes": USED_SUBS,
                        "first_unused": UNUSED_KEEPER, "excluded_second_unused": "Phil Power"},
            "source_capture": {"source_family": "Altrincham fixture archive", "path": FIXTURE_PATH,
                               "sha256": FIXTURE_SHA256,
                               "url": "https://hedgegrower.blogspot.com/2026/08/this-week-in-county-history-2000.html"},
        },
        "bindings": {
            "altrincham_data_input": {"path": registry.relative_workspace_path(DATA_INPUT), "sha256": DATA_INPUT_SHA256},
            "nationality_evidence": {"path": registry.relative_workspace_path(NATIONALITY_INPUT),
                                     "sha256": NATIONALITY_INPUT_SHA256},
            "nationality_report_revision_receipt": {"path": NATIONALITY_RECEIPT,
                                                    "sha256": NATIONALITY_RECEIPT_SHA256},
            "fixture": {"path": FIXTURE_PATH, "sha256": FIXTURE_SHA256},
            "club_profiles": data["source_bindings"]["2000_01_altrincham_profiles"],
            "departed_profiles": data["source_bindings"]["departed_player_biographies"],
            "manager_revision": {"path": manager["manager_source"]["path"],
                                 "sha256": manager["manager_source"]["sha256"],
                                 "revision_id": 1381399721, "page_id": 2874712,
                                 "receipt_path": manager["manager_source"]["receipt_path"],
                                 "receipt_sha256": manager["manager_source"]["receipt_sha256"]},
        },
        "desired_people": desired,
        "allocation": allocation,
        "allocation_contract": {
            "fixed_carrier_ids": sorted(r["carrier_id"] for r in allocation),
            "all_18_exclusive_old_3310_players_reassigned": True,
            "startup_order_before": {str(r["carrier_id"]): r["native_before"]["startup_order"] for r in allocation},
            "startup_order_after": {str(r["carrier_id"]): r["native_after"]["startup_order"] for r in allocation},
            "order_writer": "app.player_initial_order.patch_initial_orders with explicit caller-side exclusive-mode1/flag/one-GK/permutation preflight; high-level patch_owned_mode1_complete_orders refuses carrier10958 family dd6361",
            "order_reason": "Current 3310 record has duplicate/missing startup orders and is not a valid sourced Alty XI; assign exact dated source sequence 1..18, one keeper at startup slot1.",
            "roster_writer": "scripts.prepare_duplicate_whole_club_native_v1.rewrite_roster after exact source-bound 10958 flag correction; current helper rejects any nonzero mode1 row",
            "roster_mode": 1, "roster_count": 18,
            "flags_before": {str(k): v for k, v in sorted(roster_flags.items())},
            "flags_after": {str(k): (0 if k in {r['player_record_id'] for r in flag_repairs} else v)
                            for k, v in sorted(roster_flags.items())},
            "flag_repairs": flag_repairs,
            "flag_repair_policy": "only the preimage-bound 3310 row that now admits a positively sourced Alty identity may be changed via the existing edit_team_roster_eq_jug_linked temp-native API; no global or batch flag clear",
            "selected_eq_record_only": 3310,
            "all_nonselected_owners_and_records": "preserve exactly; 374 canonical counterparts remain untouched",
        },
        "old_3310_to_374_counterparts": {
            "source_crosswalk_path": crosswalk["source_path"],
            "source_crosswalk_sha256": crosswalk["source_sha256"],
            "rows": [dict(row,
                          prior_research_disposition=row.get("preservation_disposition"),
                          current_atomic_disposition=(
                              "preserve the mapped canonical 374 actor/owner; this exact exclusive 3310 carrier "
                              "is reassigned to one Alty source row, with its 3310 before-payload hash retained "
                              "as transaction evidence"))
                     for row in crosswalk["rows"]],
            "interpretation": "The 18 old 3310 identities each have a counterpart in canonical Kidderminster374. The mapped 374 actor bytes/links are protected; selected 3310 player records are the explicit Altrincham target slots and will be replaced only inside this atomic transaction. The 3310 before-payload hashes remain in the transaction evidence; do not claim those old payload bytes stay in the new game.",
        },
        "manager": {
            "manager_id": manager["native_record_id"],
            "source_name": "Mark Ward", "recipe_full_name": "Mark Ward", "native_display_name": "Ward",
            "source_provider": "retained Wikipedia API revision; user-approved source class",
            "source_revision_id": 1381399721,
            "exclusive_old_owner_carrier": 3310,
            "writer": "existing ENT indexed manager name writer",
            "requires_post_Horne_parent_owner_graph_recheck": True,
        },
        "assets": {
            "ground": {"candidate_name": "Moss Lane", "evidence": "retained Altrincham profile pages use Moss Lane in club/home context", "binding_paths": [data["source_bindings"]["2000_01_altrincham_profiles"]["path"], data["source_bindings"]["departed_player_biographies"]["path"]], "policy": "use existing accepted seed ground fallback if no exact native ground carrier mapping; no unsupported historical mapping claim"},
            "kit": {"status": "no retained dated kit evidence", "policy": "existing declared seed fallback accepted; no new art or era claim"},
            "portraits": {"policy": "clear changed-identity photos through existing whole-club no-photo archive path"},
        },
        "source_and_fact_policy": {
            "semantic_source_namespace": "altrincham-aug02-source-row with deterministic local event/name keys; these are local record keys, not external provider IDs",
            "prohibited_identity_inputs": ["fabricated Soccerbase player URLs", "fabricated Soccerbase numeric IDs", "fuzzy same-name join", "Rangers Scott Wilson alias"],
            "DOB_missing_or_conflicted": {"policy": UNKNOWN_DOB_POLICY, "write": "preserve-existing-mode1 with explicit fact_fallback; stored native date is not a sourced DOB", "rows": sorted(UNAVAILABLE_DOB | set(DOB_CONFLICTS))},
            "nationality_unavailable": {"policy": UNKNOWN_COUNTRY_POLICY, "value": "XXX", "fact_fallback": True, "explicit_ENG_rows": sorted(EXPLICIT_ENG), "unknown_or_conflicting_rows": sorted(set(EXPECTED_NAMES)-EXPLICIT_ENG)},
            "height_weight_shirt": "unavailable; use explicit existing project fallback/preserve policy only",
            "broad_roles": "source profile broad roles; Paul Walsham M is an editorial slot-compatible projection after replacing Stuart Quinn; all fine roles/formation/ratings are editorial",
            "DOB_conflicts": copy.deepcopy(DOB_CONFLICTS),
            "Scott_Wilson": "full-name positive in Aug02 source; Alty profile describes a midfielder; season matrix row Scott with 30 counts is unresolved and excluded as identity evidence; do not connect to Rangers namesake",
            "Maddix_Maddox": "dated source spelling Mark Maddix retained; profile's Mark Maddox is an unresolved spelling/DOB conflict and is not consumed as a canonical identity alias",
            "Danny_Adams": "Alty Aug02 dated actor is included once. Macc opening carrier32951 must become Bettney before joint transaction eligibility; pending and fail-closed.",
        },
        "minimal_canonical_integration_seam": {
            "typed_dispatch": "private source_adapter=altrincham-aug02-source-row-v1 branch in prepare_duplicate_whole_club_native.prepare; preserve existing generic Soccerbase reader path unchanged",
            "reusable_helpers": ["prepare_duplicate_whole_club_native.validate_allocation", "prepare_duplicate_whole_club_native.compile_recipe after person_id resolver accepts the strict local namespace", "prepare_duplicate_whole_club_native.rewrite_roster", "season_duplicate_ownership_delta.compile_players", "season_same_carrier_name_capacity only if future parent binding requires it", "app.player_initial_order.patch_owned_mode1_complete_orders", "existing ENT manager writer", "existing MINIFOTO no-photo archive writer"],
            "typed_reader": "verify fixture/body/receipt, profile bodies, explicit nationality bodies, manager revision, exact old parent and all 18 slots before calling shared helpers",
            "required_strict_identity_branch": "source_provider=altrincham-aug02-source-row; validate exact event key/name/date and retained fixture SHA plus local profile/source evidence; no guessed external provider ID",
            "required_fact_fallback_branch": "explicit preserve-existing-mode1 for source-null/conflicted DOB and XXX deterministic-default for unknown nationality; preserve existing stock fallback receipts",
            "required_order_change": "set exact 1..18 sequence after source-bound row-flag repair. The high-level mode1 complete writer rejects dd6361 carrier10958; use lower-level exact patch_initial_orders only after caller proves all 18 exclusive owners, the single accepted row flag disposition, the complete permutation and exactly one starting GK, or replace carrier with a separately evidenced compact slot",
            "manager_branch": "validate exact Wikipedia revision/page/raw-SHA/API receipt and source fields, compact via existing short_name('Mark Ward') -> Ward; never use Soccerbase URL/ID",
        },
        "native_execution_eligibility": {
            "status": "blocked pending post-Horne parent rebase and linked Macc Bettney correction",
            "reasons": ["Alty data input is pinned to r207a only as research parent; preferred post-Horne r210 package/JUG/EQ/ENT/locator pins not yet supplied", "Macc Bettney correction remains proposal-only; cannot authorize a second Alty Danny Adams identity while Macc carrier32951 remains Danny Adams", "EQ3310 player10958/slot8 has flag1 and must be changed only by the exact source-bound single-row temp API after the carrier admits an Alty person", "JUG carrier10958 is dd6361; the high-level mode1 complete-order writer rejects it. Use an exact lower-level order writer only with the caller-side full ownership and goalkeeper guards described above, or provide another positive compact carrier", "no native compilation or byte readback performed by this reader"],
        },
    }


def main() -> dict:
    plan = prepare_proposal()
    _release, package, _club, _slots, _jug, _eq, _entries, _owners, _managers, _flags, _repairs = _native_parent_and_slots()
    # This pure common validation checks the fixed-capacity whole-club shape;
    # the typed reader replaces only the upstream Soccerbase source verification.
    common = __import__("scripts.prepare_duplicate_whole_club_native_v1", fromlist=["validate_allocation"])
    common.validate_allocation(package, plan)
    return plan


def require_source_hash(path: Path, expected: str) -> None:
    if _sha(path) != expected:
        raise ValueError(f"source bytes differ from exact Altrincham proposal pin: {path}")


