"""Source-bound Hertha 2004/06 annual-cohort and dated-coach admission.

This does not alter or monkeypatch the frozen 2002/03–2003/04 coach-v3
admission. It reuses its hash-bound original readers and the established
historical-label / ENT-name patch primitives, but supplies a new, typed Götz
period witness for exactly 2004/05 and 2006/07. No writer is invoked here.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
from functools import lru_cache
from pathlib import Path
import sys
import unicodedata

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EDITOR = ROOT / "upstream/pm99-skezmod-db-editor"
if str(EDITOR) not in sys.path:
    sys.path.insert(0, str(EDITOR))

from scripts import admit_hertha_dated_cohort_coach_20261017 as old_admission
from scripts import build_2015_english92_release as native_writer
from scripts import season_period_cohort_coach_v3 as frozen_v3
from scripts import season_release_registry_v1 as registry
from scripts import season_within_club_reserve_repair_v1 as birth_facts

SCHEMA = "pm99-hertha-annual-cohort-dated-coach-v4-revision3"
METHOD = "annual-cohort-closed-manager-tenure-dfb-corroboration-v1"
MANAGER_SOURCE_METHOD = "dated-closed-manager-tenure-v1"
CASE = "CLUB421-HERTHA-REIDENTITY-2004-05-2006-07"
EVIDENCE_ROOT = ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/horne/fiedler-label-v1"
DFB = {
    "2004-05": {
        "team": "dfb-hertha-squad-2004-05",
        "fixture": "dfb-hertha-first-match-2004-05",
        "home_fixture": "dfb-hertha-first-match-2004-05",
        "fixture_date": "2004-08-07",
    },
    "2006-07": {
        "team": "dfb-hertha-squad-2006-07",
        "fixture": "dfb-hertha-first-match-2006-07",
        "home_fixture": "dfb-hertha-first-home-match-2006-07",
        "fixture_date": "2006-08-13",
    },
}
RELEASES = {
    "2004-05": "sourced-dated-tokic-croatia-20261019-r170a",
    "2006-07": "sourced-kiraly-period-profiles-20261017-r141a",
}


def _sha(path: Path) -> str:
    return registry.sha256_file(path)


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text.casefold() if not unicodedata.combining(ch) and ch.isalnum())


def _binding(path: Path) -> dict:
    return {"path": registry.relative_workspace_path(path), "sha256": _sha(path)}


def _validate_html_identity(raw: bytes, *, expected_url: str, title: str) -> str:
    """Validate page identity from HTML bytes, not capture-receipt metadata."""
    page = BeautifulSoup(raw, "html.parser")
    title_node = page.find("title")
    raw_title = " ".join(title_node.get_text(" ", strip=True).split()) if title_node else ""
    canonicals = page.find_all("link", rel=lambda value: value and "canonical" in value)
    if raw_title != title:
        raise ValueError("raw source title does not match the approved original page identity")
    if len(canonicals) != 1 or canonicals[0].get("href") != expected_url:
        raise ValueError("raw source canonical URL does not match the approved original page identity")
    title_node.decompose()
    return " ".join(page.get_text(" ", strip=True).split())


def _captured_page(key: str, *, expected_url: str, title: str, phrases: tuple[str, ...]) -> tuple[dict, str]:
    raw_path = EVIDENCE_ROOT / "raw" / f"{key}.html"
    receipt_path = EVIDENCE_ROOT / "raw" / f"{key}.source.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    raw = raw_path.read_bytes()
    raw_sha = hashlib.sha256(raw).hexdigest()
    if (receipt.get("status") != "original-captured" or receipt.get("url") != expected_url
            or receipt.get("sha256") != raw_sha or _sha(raw_path) != raw_sha
            or receipt.get("bytes") != len(raw) or receipt.get("original_title") != title):
        raise ValueError(f"primary original source/receipt does not bind: {key}")
    text = _validate_html_identity(raw, expected_url=expected_url, title=title)
    if not all(phrase in text for phrase in phrases):
        raise ValueError(f"literal target-season primary claim missing: {key}")
    return {
        "id": key,
        "url": expected_url,
        "raw": _binding(raw_path),
        "receipt": _binding(receipt_path),
        "bytes": len(raw),
        "title": title,
        "literal_claims": list(phrases),
    }, text


def _writer_source(capture: dict) -> dict:
    """Keep ordinary path/body bindings plus the adjacent capture receipt."""
    return {
        **capture["raw"],
        "url": capture["url"],
        "source_receipt_path": capture["receipt"]["path"],
        "source_receipt_sha256": capture["receipt"]["sha256"],
    }


def _dated_gotz(season: str) -> dict:
    binding = old_admission.external("hertha-original-coach-list-asof2024")
    raw = old_admission.prior.originals.publisher_original(binding)
    target = date(int(season[:4]), 8, 1)
    decision = old_admission.dated_coach(raw, target)
    if (decision["name"], decision["from_date"], decision["to_date"]) != (
            "Falko Götz", "2004-07-01", "2007-04-10"):
        raise ValueError("dated original manager chronology does not identify Götz for target opening date")
    return {"decision": decision, "original": binding}


def _native_preflight(base, club_update: dict, manager_update: dict) -> dict:
    """Exercise only existing in-memory label and ENT writer primitives."""
    prior = old_admission.prior
    eq_path = base.game_path / "DBDAT/EQ98030.FDI"
    ent_path = base.game_path / "DBDAT/ENT98030.FDI"
    eq = eq_path.read_bytes()
    ent = ent_path.read_bytes()
    after_eq, changes = prior.labels.rewrite_club_labels(eq, [club_update])
    if len(changes) != 1 or changes[0]["after"] != "Hertha Berlin":
        raise ValueError("existing EQ label writer did not produce exactly the requested club label change")
    ent_index = prior.IndexedFDIFile.from_bytes(ent)
    ent_entries = {row.record_id: row for row in ent_index.entries}
    before_manager = ent_entries[1313].decode_payload(ent)
    after_manager = native_writer._patch_ent_name(before_manager, 1313, "Götz")
    if after_manager == before_manager:
        raise ValueError("existing ENT manager-name writer produced no change")
    after_ent = native_writer._rebuild_indexed(ent, ent_index, {1313: after_manager})
    after_index = {row.record_id: row for row in prior.IndexedFDIFile.from_bytes(after_ent).entries}
    if set(after_index) != set(ent_entries):
        raise ValueError("ENT preflight changed directory IDs")
    for record_id, entry in after_index.items():
        expected = after_manager if record_id == 1313 else ent_entries[record_id].decode_payload(ent)
        if entry.decode_payload(after_ent) != expected:
            raise ValueError("ENT preflight changed an unrelated manager record")
    # The native helper has already checked the ID and CP1252 representation.
    # Read back the proposed name directly from the patched indexed profile.
    patched = after_index[1313].decode_payload(after_ent)
    marker = patched.find(b"\xdd\x63\x60")
    if marker < 0:
        marker = patched.find(b"\xdd\x63\x61")
    if marker < 2:
        raise ValueError("proposed manager ENT profile is not parseable")
    surname, _, _ = native_writer._read_inner_string(patched, marker + 5)
    if surname != "Götz":
        raise ValueError("proposed native surname readback differs")
    return {
        "eq_delta": changes,
        "eq_preimage_sha256": _sha(eq_path),
        "ent_preimage_sha256": _sha(ent_path),
        "manager_carrier_id": 1313,
        "manager_native_before": "Röber",
        "manager_native_after": surname,
        "ent_decoded_records_changed": [1313],
        "all_other_manager_records_preserved": True,
        "writes_performed": 0,
    }


@lru_cache(maxsize=64)
def _cached_native_facts(jug_bytes: bytes, carrier_id: int) -> dict:
    return birth_facts.native_facts(jug_bytes, carrier_id)


def _native_birth_date_crosswalk(season: str, annual_path: Path,
        residents: list[dict], jug_bytes: bytes) -> dict:
    """Compare original annual rows, recipe facts and exact native DOBs.

    A mismatch is disclosed as a diagnostic and never repaired here. It is not
    silently treated as a match or used to alter an unrelated birth date.
    """
    source = birth_facts.roster.csv_source._read_club_file(
        annual_path.resolve(), root=registry.ROOT,
        season_start=int(season[:4]), season_label=(
            f"{season[:4]}/{str(int(season[:4]) + 1)[-2:]}"))
    source_rows = {}
    for row in source["players"]:
        source_rows.setdefault(birth_facts.roster.normalise(row["name"]), []).append(row)
    entries, mismatches = [], []
    for person in sorted(residents, key=lambda row: row["carrier_id"]):
        source_name = person.get("source_name") or person["name"]
        candidates = source_rows.get(birth_facts.roster.normalise(source_name), [])
        native = _cached_native_facts(jug_bytes, int(person["carrier_id"]))
        recipe_dob = person.get("facts", {}).get("birth_date")
        source_dob = candidates[0].get("birth_date") if len(candidates) == 1 else None
        row = {
            "carrier_id": person["carrier_id"], "source_name": source_name,
            "annual_row_count": len(candidates), "annual_birth_date": source_dob,
            "recipe_birth_date": recipe_dob,
            "native_birth_date": native["birth_date"],
            "native_full_name": native["name"],
        }
        entries.append(row)
        if (len(candidates) != 1 or source_dob != recipe_dob
                or native["birth_date"] != recipe_dob
                or native["birth_date"] != source_dob):
            mismatches.append(row)
    return {"status": "all-25-exact" if len(entries) == 25 and not mismatches else "mismatch",
        "source_capture_sha256": _sha(annual_path), "count": len(entries),
        "mismatches": mismatches, "entries": entries,
        "birthday_changes_proposed": 0}


def prepare(base, *, expected_release_id: str | None = None) -> dict:
    """Return source-bound club and standard manager plans, without mutation."""
    season = base.season
    if season not in DFB:
        raise ValueError("v4 explicitly supports only 2004-05 and 2006-07")
    expected_release_id = expected_release_id or RELEASES[season]
    if not isinstance(expected_release_id, str) or base.release_id != expected_release_id:
        raise ValueError("explicit expected parent release does not match the supplied base")

    prior = old_admission.prior
    package = prior.pipeline.read_json_file(base.package_path)
    club = next(row for row in package["clubs"] if row.get("carrier_id") == 421)
    residents = [row for row in package["players"] if row["club_id"] == club["id"]]
    if ({row["id"] for row in residents} != set(club["roster_player_ids"])
            or len(residents) != 25):
        raise ValueError("club-421 declared cohort and recipe player rows are not exactly 25")

    preallocation = registry.ROOT / ".local/transfermarkt-opening-plans-current-v1" / season / "opening-squad-preallocation.json"
    preallocation_binding = _binding(preallocation)
    artifact = next(row for row in package["artifacts"] if row["id"] == "opening-squad-preallocation-" + season)
    if artifact["sha256"] != preallocation_binding["sha256"]:
        raise ValueError("annual-cohort source preallocation no longer binds this parent package")
    index, sources = prior.old.indexed_claims(prior.pipeline.read_json_file(preallocation))
    authored = prior.cohort_source(club, residents, artifact["id"], index, sources)
    if authored["selector"]["club_name"] != "Hertha Berlin":
        raise ValueError("all authored annual source identities do not resolve to Hertha Berlin")

    captures, _ = prior.old.roster.load_sources(season)
    matched = [row for row in captures if prior.old.selector_key(row) == prior.old.selector_key(authored["selector"])]
    if len(matched) != 1:
        raise ValueError("annual Hertha source capture is not unique")
    raw_period = prior.old.roster.SourceVerifier(season).verify(matched[0])
    if raw_period["status"] != "raw-source-reparsed":
        raise ValueError("annual Hertha source did not reparse from retained raw original")
    annual = old_admission.annual.dated_annual_title(
        registry.ROOT / raw_period["local_path"], season, prior.old.roster.club_group(club))

    fixed_path = registry.ROOT / "seasons" / season / "fixed-carrier-registry.json"
    fixed = prior.pipeline.read_json_file(fixed_path)
    original = next(row for row in fixed["carriers"] if row["carrier_id"] == 421)
    if (original["record_mode"] != 1
            or prior.old.builder._normalise_club_name(original["baseline_club"]["name"]) != "herthaberlin"):
        raise ValueError("carrier 421 is not the original fixed Hertha carrier")
    group = prior.old.roster.club_group(club)
    for other in package["clubs"]:
        if other["id"] != club["id"] and prior.old.roster.club_group(other) == group and (
                prior.old.roster.club_names(group, other["name"])
                & prior.old.roster.club_names(group, "Hertha Berlin")):
            raise ValueError("another represented carrier conflicts with target Hertha identity")

    jug_path = base.game_path / "DBDAT/JUG98030.FDI"
    eq_path = base.game_path / "DBDAT/EQ98030.FDI"
    ent_path = base.game_path / "DBDAT/ENT98030.FDI"
    jug, eq = jug_path.read_bytes(), eq_path.read_bytes()
    jug_entries = {row.record_id: row for row in prior.IndexedFDIFile.from_bytes(jug).entries}
    ownership = prior.owners.native_owners(eq)
    for person in residents:
        native = prior.old.roster.native_player(jug_entries[person["carrier_id"]].decode_payload(jug), person["carrier_id"])
        if (ownership.get(person["carrier_id"]) != {421}
                or prior.old.roster.normalise(native["name"]) != prior.old.roster.normalise(person["name"])):
            raise ValueError(f"native exact-name/exclusive-owner mismatch for carrier {person['carrier_id']}")
    fiedler = next((row for row in residents if row["carrier_id"] == 13196), None)
    if (fiedler is None or fiedler.get("source_name") != "Christian Fiedler"
            or fiedler.get("facts", {}).get("birth_date") != "1975-03-27"):
        raise ValueError("Fiedler source identity/DOB preimage differs from the DFB team page")

    eq_entries = {row.record_id: row for row in prior.IndexedFDIFile.from_bytes(eq).entries}
    eq_payload = eq_entries[421].decode_payload(eq)
    short, full, _preserved = prior.labels.prefix_parts(eq_payload)
    marker = eq_payload.find(bytes.fromhex("dd6361"))
    if marker < 0:
        raise ValueError("EQ carrier 421 has no indexed club name")
    _short, _, end = prior._read_eq_inline_string(eq_payload, marker + 4)
    ground = prior._read_eq_inline_string(eq_payload, end)[0]
    holders, native_manager_names = prior.old._manager_graph(eq_path=eq_path, ent_path=ent_path)
    manager = next(row for row in package["managers"] if row["id"] == club["manager_id"])
    if (short != club["name"] or manager["carrier_id"] != 1313 or manager["name"] != "Röber"
            or native_manager_names.get(1313) != "Röber"
            or [row["carrier_id"] for row in holders.get(1313, [])] != [421]
            or original["baseline_club"]["active_manager_carrier_id"] != 1313
            or ground != original["baseline_club"]["ground_name"]
            or ground != "Olympiastadion"):
        raise ValueError("current manager/ground link or original manager/ground preimage differs")
    if any(_norm(row["name"]) in ("falkogotz", "gotz") for row in package["managers"] if row["id"] != manager["id"]):
        raise ValueError("Götz already occupies another recipe manager identity")
    if any(_norm(name) in ("falkogotz", "gotz") for carrier, name in native_manager_names.items() if carrier != 1313):
        raise ValueError("Götz already occupies another native manager identity")

    dated = _dated_gotz(season)
    source_spec = DFB[season]
    season_name = "2004/05" if season == "2004-05" else "2006/07"
    team_url = f"https://datencenter.dfb.de/competitions/bundesliga/seasons/{season[:4]}-{int(season[:4])+1}/teams/hertha-bsc"
    team_title = f"Hertha BSC, Bundesliga {season_name} - DFB Datencenter"
    team_capture, team_text = _captured_page(source_spec["team"], expected_url=team_url,
        title=team_title, phrases=("Hertha BSC", "Falko Götz", "Christian Fiedler", "27.03.1975"))
    fixture_url = ("https://datencenter.dfb.de/datencenter/bundesliga/2004-2005/1/hertha-bsc-vfl-bochum-175431"
        if season == "2004-05" else "https://datencenter.dfb.de/datencenter/bundesliga/2006-2007/1/vfl-wolfsburg-hertha-bsc-48595")
    fixture_title = ("Hertha BSC - VfL Bochum, 2:2, Bundesliga 2004/05 1. Spieltag - DFB Datencenter"
        if season == "2004-05" else "VfL Wolfsburg - Hertha BSC, 0:0, Bundesliga 2006/07 1. Spieltag - DFB Datencenter")
    fixture_phrases = (("Samstag, 07. August 2004", "Olympiastadion, Berlin", "Christian Fiedler", "Falko Götz")
        if season == "2004-05" else ("Sonntag, 13. August 2006", "Volkswagen Arena, Wolfsburg", "Christian Fiedler", "Falko Götz"))
    fixture_capture, _ = _captured_page(source_spec["fixture"], expected_url=fixture_url,
        title=fixture_title, phrases=fixture_phrases)
    home_url = "https://datencenter.dfb.de/datencenter/bundesliga/2004-2005/1/hertha-bsc-vfl-bochum-175431" if season == "2004-05" else "https://datencenter.dfb.de/datencenter/bundesliga/2006-2007/2/hertha-bsc-hannover-96-48607"
    home_title = fixture_title if season == "2004-05" else "Hertha BSC - Hannover 96, 4:0, Bundesliga 2006/07 2. Spieltag - DFB Datencenter"
    home_phrases = fixture_phrases if season == "2004-05" else ("Samstag, 19. August 2006", "Olympiastadion, Berlin", "Christian Fiedler", "Falko Götz")
    home_capture, _ = _captured_page(source_spec["home_fixture"], expected_url=home_url,
        title=home_title, phrases=home_phrases)
    stadium_key = "hertha-official-olympiastadion-history"
    stadium_capture, stadium_text = _captured_page(stadium_key,
        expected_url="https://www.herthabsc.com/de/club/olympiastadion",
        title="Olympiastadion | Hertha BSC", phrases=("Hertha BSC", "seit 1963", "1986 und 1988"))
    if not all(word in stadium_text for word in ("Heimspiele", "Westend")):
        raise ValueError("official Hertha stadium history no longer states home ground continuity")
    ground_evidence = {"kind": "official-Hertha-Olympiastadion-continuity-v1",
        "original": {"url": stadium_capture["url"], **stadium_capture["raw"]}}
    ground_proof = old_admission.annual.ground(
        (EVIDENCE_ROOT / "raw" / f"{stadium_key}.html").read_bytes(), ground_evidence,
        "Hertha Berlin", ground, int(season[:4]))

    club_update = {
        "club_id": club["id"], "carrier_id": 421, "before": club["name"],
        "before_full": club.get("full_name"), "after": "Hertha Berlin",
        "identity_after": prior.old.builder._source_club_identity_id(group, "Hertha Berlin"),
        "native_before": short, "native_full_before": full, "native_after": "Hertha Berlin",
    }
    coach_sources = [dated["original"]]
    # Bind the official first-match record that directly names Götz at the
    # target-season boundary; the team page is independent squad corroboration.
    coach_sources.extend([_writer_source(fixture_capture), _writer_source(team_capture)])
    manager_update = {
        "club_id": club["id"], "club_carrier_id": 421, "club": "Hertha Berlin",
        "manager_id": manager["id"], "carrier_id": 1313, "before": manager["name"],
        "before_policy": manager.get("policy"), "native_before": native_manager_names[1313],
        "after": "Falko Götz", "native_after": "Götz",
        "effective_opening_date": season[:4] + "-08-01", "native_manager_owner_count": 1,
        "evidence": {"raw_sources": coach_sources,
            "dated_closed_tenure": dated["decision"],
            "dfb_target_year_squad": team_capture,
            "dfb_first_league_fixture": fixture_capture,
            "source_cohort_not_first_fixture": True},
    }
    native_delta = _native_preflight(base, club_update, manager_update)
    native_dob_crosswalk = _native_birth_date_crosswalk(
        season, registry.ROOT / raw_period["local_path"], residents, jug)
    input_paths = [Path(m.__file__) for m in (old_admission, old_admission.annual,
        old_admission.prior, old_admission.prior.old, old_admission.prior.labels,
        old_admission.prior.originals, native_writer, frozen_v3, birth_facts)] + [Path(__file__)]
    implementation_inputs = [_binding(path) for path in input_paths]
    manager_plan = {
        "schema_version": "pm99-historical-manager-plan-v1", "source_method": MANAGER_SOURCE_METHOD,
        "season": season, "release_id": base.release_id,
        "package_sha256": _sha(base.package_path), "eq_sha256": _sha(eq_path),
        "ent_sha256": _sha(ent_path), "unresolved": [], "updates": [manager_update],
    }
    admission = {
        "case_id": CASE, "season": season, "release_id": base.release_id,
        "package": _binding(base.package_path), "jug": _binding(jug_path),
        "eq": _binding(eq_path), "ent": _binding(ent_path),
        "preallocation": preallocation_binding, "fixed_registry": _binding(fixed_path),
        "annual_capture": {"selector": authored["selector"], "period_title": annual,
            "source": _binding(registry.ROOT / raw_period["local_path"]),
            "raw_source_reparsed": True, "represented_members": len(residents)},
        "coach_history": {"original": dated["original"], "decision": dated["decision"]},
        "primary_dfb_sources": [team_capture, fixture_capture, home_capture, stadium_capture],
        "current_preimages": {"club_label": short, "club_full_label": full,
            "ground": ground, "manager_carrier_id": 1313, "manager_native_name": native_manager_names[1313],
            "manager_recipe_name": manager["name"], "manager_owner_carriers": [421],
            "native_player_count": len(residents)},
        "fiedler_identity": {"carrier_id": 13196, "source_name": fiedler["source_name"],
            "recipe_birth_date": fiedler["facts"]["birth_date"],
            "dfb_literal_birth_date": "27.03.1975",
            "native_birth_date": next(row["native_birth_date"] for row in native_dob_crosswalk["entries"]
                if row["carrier_id"] == 13196)},
        "native_birth_date_crosswalk": native_dob_crosswalk,
        "native_writer_preflight": native_delta,
        "source_only": True, "writes": 0,
    }
    result = {
        "schema_version": SCHEMA, "case_id": CASE, "method": METHOD,
        "season": season, "release_id": base.release_id,
        "expected_release_id": expected_release_id,
        "package_sha256": _sha(base.package_path), "jug_sha256": _sha(jug_path),
        "eq_sha256": _sha(eq_path), "ent_sha256": _sha(ent_path),
        "updates": [club_update], "manager_plan": manager_plan,
        "admission": admission, "implementation_inputs": implementation_inputs,
        "ground_proof": ground_proof, "native_writer_preflight": native_delta,
        "scope": "Only original carrier-421 short/full club labels and its exclusively owned dated coach identity. Current native and recipe manager link is Röber; sourced manager identity required for the 2004/06 opening dates is Falko Götz. Preserve native ground, all 25 players/ownership/order/roles, tactics, kits, portraits, capacity and EXE. Not an opening-XI or full-cohort completeness certification.",
    }
    # A saved plan is the canonical contract. Normalize tuple/list and other
    # JSON distinctions before returning so a persisted plan freshly verifies.
    return json.loads(json.dumps(result, ensure_ascii=False))


def verify(base, plan: dict) -> None:
    if plan.get("schema_version") != SCHEMA or prepare(base, expected_release_id=plan.get("expected_release_id")) != plan:
        raise ValueError("Hertha 2004/06 annual-cohort + Götz source/native plan does not reproduce")


def verify_manager_pair(plan: dict, manager_plan: dict) -> None:
    if plan.get("schema_version") != SCHEMA or manager_plan != plan.get("manager_plan"):
        raise ValueError("v4 Hertha club/dated-coach plans are not the exact source-bound pair")
