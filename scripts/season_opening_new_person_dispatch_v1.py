"""Isolated strict source dispatch for three retained 2005-06 new-person cases.

This adapter adds no native writer. It returns the existing exchange
``new_person`` result shape and delegates ordinary profile/opening-contract
selections to the unchanged canonical implementation.
"""
from __future__ import annotations

import hashlib
import importlib.util
import copy
import json
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_release_registry_v1 as registry

ROOT = registry.ROOT
POLICY = "editorial-right-wing-from-broad-M-and-period-role-witness-v1"
RM_BIRTH_FORMAT = "real-madrid-official-biography-birthday-v1"
RM_URL = "https://www.realmadrid.com/es-ES/el-club/historia/leyendas-futbol/ruben-de-la-red-gutierrez"
RM_PATH = ".local/consolidated-audit-20261009/parallel-rc-20261023/celtic/crossclub-2005-first5/real-madrid-amavisca-candidate/real-madrid-official-ruben-de-la-red.html"
RM_SHA = "c3bf5aaa27eb634a6cba8427e35e93057436e508af5e0694c84a73ef650b3e95"
RM_RECEIPT_PATH = RM_PATH.removesuffix(".html") + ".source.json"
RM_RECEIPT_SHA = "9d2ec537f9fc0c0032fe8cb3a63933a30359cf486b509a022590858075fead74"
RM_NAME = "Rubén de la Red"
RM_OFFICIAL_NAME = "Rubén De la Red Gutiérrez"
RM_DOB = "1985-06-05"
RM_ANNUAL_PATH = ".local/external-sources/historical-detailed-roles-v1/2005-06/squad/2005/spain/418.html"
RM_ANNUAL_SHA = "7d57e90f36bdc3990648066f0a3aa2aab19d06b01e50ee16ff87730ac5f39f8e"
RM_ANNUAL_URL = "https://www.transfermarkt.com/club/kader/verein/418/saison_id/2005/plus/1"
RM_ANNUAL_RECEIPT_SHA = "753b281348cf935ea41931d9d26b5707f6f0cf40b9db831a9560fa6e2b755b53"
RM_MATCH_PATH = ".local/transfermarkt-opening-plans-current-v1/2005-06/cache/report/37219.html"
RM_MATCH_SHA = "b5552dd3cf86bb152bf54ba195db361aa920dfee62775f78eaf9324e25c240f3"
RM_MATCH_URL = "https://www.transfermarkt.co.uk/spielbericht/index/spielbericht/37219"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound_source(value: dict, *, path: str, sha: str, url: str,
                  receipt_path: str | None = None, receipt_sha: str | None = None) -> Path:
    if not isinstance(value, dict) or value.get("path") != path or value.get("sha256") != sha or value.get("url") != url:
        raise ValueError("source path/hash/URL differs from retained original")
    body = (ROOT / path).resolve(strict=True)
    if not body.is_relative_to(ROOT.resolve()) or _sha(body) != sha:
        raise ValueError("retained original body hash differs")
    if receipt_path is not None:
        receipt = (ROOT / receipt_path).resolve(strict=True)
        if not receipt.is_relative_to(ROOT.resolve()) or _sha(receipt) != receipt_sha:
            raise ValueError("retained source receipt hash differs")
        parsed = json.loads(receipt.read_text(encoding="utf-8"))
        if parsed != {"sha256": sha, "url": url}:
            raise ValueError("source receipt does not bind exact body URL/hash")
    return body


def _official_rm_birthday(witness: dict, annual_name: str) -> str:
    expected = {"format", "path", "sha256", "url", "receipt_path", "receipt_sha256"}
    if not isinstance(witness, dict) or set(witness) != expected or witness["format"] != RM_BIRTH_FORMAT:
        raise ValueError("exact official Real Madrid DOB witness required")
    if (witness["path"], witness["sha256"], witness["url"], witness["receipt_path"], witness["receipt_sha256"]) != (
            RM_PATH, RM_SHA, RM_URL, RM_RECEIPT_PATH, RM_RECEIPT_SHA):
        raise ValueError("official Real Madrid witness binding differs")
    body = (ROOT / RM_PATH).resolve(strict=True)
    receipt = (ROOT / RM_RECEIPT_PATH).resolve(strict=True)
    if (not body.is_relative_to(ROOT.resolve()) or _sha(body) != RM_SHA
            or not receipt.is_relative_to(ROOT.resolve()) or _sha(receipt) != RM_RECEIPT_SHA):
        raise ValueError("official Real Madrid body/receipt hash differs")
    receipt_data = json.loads(receipt.read_text(encoding="utf-8"))
    if (receipt_data.get("schema_version") != "pm99-original-source-body-receipt-v1"
            or receipt_data.get("url") != RM_URL or receipt_data.get("path") != RM_PATH
            or receipt_data.get("sha256") != RM_SHA):
        raise ValueError("official Real Madrid receipt does not bind body URL/hash")
    soup = BeautifulSoup(body.read_bytes(), "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = " ".join(soup.get_text(" ", strip=True).split())
    if title != f"{RM_OFFICIAL_NAME} - Historia y palmarés | Web oficial Real Madrid C.F.":
        raise ValueError("official Real Madrid biography identity title differs")
    if annual_name != RM_NAME or text.count(RM_OFFICIAL_NAME) < 1:
        raise ValueError("official biography-to-annual name bridge differs")
    labelled = []
    for small in soup.find_all("small"):
        if small.get_text(" ", strip=True) == "Fecha de nacimiento":
            sibling = small.find_next_sibling("span")
            if sibling is not None:
                labelled.append(sibling.get_text(" ", strip=True))
    if len(labelled) < 1 or any(value != "05/06/1985" for value in labelled):
        raise ValueError("official Real Madrid literal birthday differs")
    return datetime.strptime(labelled[0], "%d/%m/%Y").date().isoformat()


@lru_cache(maxsize=1)
def _private_biography_reader():
    """Load a private module instance; adapt only its birthday witness hook."""
    source = ROOT / "scripts/season_transfermarkt_squad_biography_v1.py"
    spec = importlib.util.spec_from_file_location("isolated_biographies_rm_witness_v1", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load private squad biography reader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.independent_birthday = _official_rm_birthday
    return module


def _rm_bench(selection: dict, evidence: dict, season: str) -> dict:
    fixture = evidence[selection["match"]]
    if not isinstance(fixture, dict) or set(fixture) != {
            "path", "sha256", "url", "provider_club_id", "date", "membership_mode"}:
        raise ValueError("exact published match evidence fields required")
    if (fixture["path"], fixture["sha256"], fixture["url"], fixture["provider_club_id"],
            fixture["date"], fixture["membership_mode"]) != (
            RM_MATCH_PATH, RM_MATCH_SHA, RM_MATCH_URL, 418, "2005-08-28", "classic-played-substitutes"):
        raise ValueError("exact Real Madrid August fixture binding differs")
    exchange.original(fixture)
    played = date.fromisoformat(fixture["date"])
    if season != "2005-06" or played.year != 2005 or played.month != 8:
        raise ValueError("same-season August membership is required")
    exchange.verify_match_club(fixture, "Real Madrid")
    pid = str(selection["provider_player_id"])
    page = BeautifulSoup(exchange.original(fixture).read_bytes(), "html.parser")
    stamp = page.select_one(".sb-datum")
    dates = re.findall(r"\b\d{2}/\d{2}/\d{2}\b", stamp.get_text(" ", strip=True) if stamp else "")
    if len(dates) != 1 or datetime.strptime(dates[0], "%d/%m/%y").date() != played:
        raise ValueError("original match report date differs")
    boxes = []
    for box in page.select("div.large-6"):
        ids = {int(m.group(1)) for a in box.select("a[href]")
               if (m := re.search(r"/startseite/verein/(\d+)(?:/|$)", a["href"]))}
        if ids == {418} and box.select_one(".formation-player-container"):
            boxes.append(box)
    if len(boxes) != 1:
        raise ValueError("one exact Real Madrid matchday lineup box required")
    starter_ids = []
    for link in boxes[0].select(".formation-player-container a[href]"):
        match = re.search(r"/profil/spieler/([1-9][0-9]*)(?:/|$)", urlsplit(link["href"]).path)
        if match:
            starter_ids.append(match.group(1))
    if len(starter_ids) != 11 or len(set(starter_ids)) != 11 or pid in starter_ids:
        raise ValueError("published Real Madrid starting XI is malformed or contains target")
    banks = boxes[0].select(".aufstellung-ersatzbank-box")
    if len(banks) != 1:
        raise ValueError("published Real Madrid lineup must contain one exact bench table")
    bank = banks[0]
    bench_rows = []
    for row in bank.select("table.ersatzbank > tr"):
        if not row.select_one("td.nummer.formation-number-substitute"):
            continue
        links = []
        for link in row.select('a[href*="/profil/spieler/"]'):
            match = re.search(r"/profil/spieler/([1-9][0-9]*)(?:/|$)", urlsplit(link["href"]).path)
            if match:
                links.append((match.group(1), link.get_text(" ", strip=True)))
        if len(links) != 1:
            raise ValueError("bench row lacks one exact numeric person link")
        bench_rows.append((row, links[0][0], links[0][1]))
    selected = [entry for entry in bench_rows if entry[1] == pid]
    if len(selected) != 1 or selected[0][2] != RM_NAME:
        raise ValueError("exact numeric person is not one published substitute/bench row")
    if selected[0][0].select_one(".icon-einwechslung-formation"):
        raise ValueError("published substitute entered match; this policy is unused bench only")
    return dict(match_url=fixture["url"], match_id=37219, provider_club_id=418,
        date=played.isoformat(), source_player_id=pid,
        basis="published-named-bench-not-playing-appearance")


def _ruben_new_person(selection: dict, evidence: dict, season: str) -> dict:
    expected = {"provider_player_id", "name", "birth_date", "position", "profile_position",
        "fine_roles", "nationality", "nationality_label", "squad_biography", "squad_context",
        "official_biography", "match"}
    if set(selection) != expected or selection != {
            "provider_player_id": 35522, "name": RM_NAME, "birth_date": RM_DOB,
            "position": "M", "profile_position": "Central Midfield", "fine_roles": [9],
            "nationality": "ESP", "nationality_label": "Spain", "squad_biography": "rm_annual",
            "squad_context": {"season_start_year": 2005, "provider_club_id": 418, "club_name": "Real Madrid"},
            "official_biography": "rm_official", "match": "rm_august_bench"}:
        raise ValueError("only exact reviewed Rubén de la Red selection is admitted")
    if set(evidence) != {"rm_annual", "rm_official", "rm_august_bench"}:
        raise ValueError("unexpected or mixed Real Madrid source evidence keys")
    if season != "2005-06":
        raise ValueError("Real Madrid annual context differs from requested season")
    annual = evidence[selection["squad_biography"]]
    if (annual.get("format"), annual.get("path"), annual.get("sha256"), annual.get("url"),
            annual.get("receipt", {}).get("sha256"), annual.get("receipt", {}).get("path")) != (
            "original-target-year-transfermarkt-squad-person-row-v1", RM_ANNUAL_PATH, RM_ANNUAL_SHA,
            RM_ANNUAL_URL, RM_ANNUAL_RECEIPT_SHA, RM_ANNUAL_PATH + ".source.json"):
        raise ValueError("exact Real Madrid 2005/06 annual source/receipt required")
    _bound_source(annual, path=RM_ANNUAL_PATH, sha=RM_ANNUAL_SHA, url=RM_ANNUAL_URL,
        receipt_path=RM_ANNUAL_PATH + ".source.json", receipt_sha=RM_ANNUAL_RECEIPT_SHA)
    witness = evidence[selection["official_biography"]]
    if annual.get("birth_date_witness") != witness:
        raise ValueError("same official birthday witness must be embedded in annual row evidence")
    reader = _private_biography_reader()
    parsed = reader.read(annual, 35522, season=season, club_name="Real Madrid", provider_club_id=418)
    if (parsed["published_full_name"], parsed["published_birth_date"],
            parsed["published_profile_position"], parsed["published_nationality_label"]) != (
            RM_NAME, RM_DOB, "Central Midfield", "Spain"):
        raise ValueError("same-row annual identity, DOB, role, or country differs")
    from scripts.season_exact_fifa_role_delta_v1 import compatible
    if (exchange.SOURCE_COUNTRIES.get("Spain") != "ESP" or selection["fine_roles"] != [9]
            or not compatible("M", selection["fine_roles"][0])):
        raise ValueError("source country or compatible Central Midfield role differs")
    match_proof = _rm_bench(selection, evidence, season)
    return dict(source_person=dict(name=RM_NAME, birth_date=RM_DOB, source_player_id=35522,
            source_provider="transfermarkt", source_profile_url=parsed["linked_profile_url"]),
        source_player=dict(name=RM_NAME, birth_date=RM_DOB, position="M", nationality="ESP",
            height_cm=parsed["published_height_cm"], weight_kg=None,
            shirt_number=parsed["published_shirt_number"]),
        raw_evidence=dict(status="raw-source-reparsed", local_path=annual["path"],
            source_sha256=annual["sha256"], biography_source_kind=parsed["biography_source_kind"],
            profile_page_captured=False, source_inputs=copy.deepcopy(evidence),
            official_birthday_witness=dict(url=RM_URL, path=RM_PATH,
                sha256=RM_SHA, full_name=RM_OFFICIAL_NAME, birth_date=RM_DOB)),
        membership="original-published-August-bench-not-playing-claim",
        membership_evidence=match_proof)


def new_person(selection: dict, evidence: dict, *, season: str = "2005-06") -> dict:
    """Versioned dispatch; old canonical paths are untouched and remain fallback."""
    if not isinstance(selection, dict) or not isinstance(evidence, dict):
        raise ValueError("selection and evidence maps required")
    keys = set(selection)
    riera_keys = {"provider_player_id", "name", "birth_date", "position", "profile_position",
        "fine_roles", "nationality", "nationality_label", "squad_biography", "squad_context", "match"}
    ruben_keys = riera_keys | {"official_biography"}
    if "editorial_role_policy" in keys:
        if keys.intersection({"squad_context", "squad_biography", "official_biography", "opening_contract", "profile"}):
            raise ValueError("mixed editorial and biography/membership routes are forbidden")
        if season != "2005-06":
            raise ValueError("Croft source context differs from requested season")
        if set(evidence) != {"city_annual", "tm_entity", "soccerbase", "city_role", "uefa_country", "city_august_match"}:
            raise ValueError("unexpected or mixed Croft source evidence keys")
        from scripts import season_opening_croft_admission_v1 as croft
        result = croft.prepare(selection, evidence)
        result["raw_evidence"]["source_inputs"] = copy.deepcopy(evidence)
        return result
    if keys == ruben_keys:
        return _ruben_new_person(selection, evidence, season)
    if keys == riera_keys:
        if season != "2005-06":
            raise ValueError("Riera source context differs from requested season")
        if set(evidence) != {"espanyol_annual", "espanyol_august_match"}:
            raise ValueError("unexpected or mixed Riera source evidence keys")
        from scripts import season_opening_riera_admission_v1 as riera
        result = riera.prepare(selection, evidence, season=season)
        result["raw_evidence"]["source_inputs"] = copy.deepcopy(evidence)
        return result
    if keys.intersection({"squad_context", "official_biography", "editorial_role_policy"}):
        raise ValueError("unknown/mixed source admission policy or unexpected selection keys")
    return exchange._canonical_new_person(selection, evidence)
