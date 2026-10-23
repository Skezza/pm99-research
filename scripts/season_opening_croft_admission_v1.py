"""Isolated proposal for an annual broad-role source plus editorial fine role.

Not a production writer and not a historical fine-position claim. The returned
mapping follows the existing opening-exchange ``new_person`` result shape so
the existing transaction/bind/write path can be reused after lead review.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_release_registry_v1 as registry

ROOT = registry.ROOT
POLICY = "editorial-right-wing-from-broad-M-and-period-role-witness-v1"


def _raw(path: str, sha: str) -> bytes:
    p = ROOT / path
    raw = p.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError(f"original source hash differs: {path}")
    return raw


def _receipt(value: dict) -> None:
    receipt_path = ROOT / value["receipt_path"]
    receipt_raw = receipt_path.read_bytes()
    if hashlib.sha256(receipt_raw).hexdigest() != value["receipt_sha256"]:
        raise ValueError("retained source receipt hash differs")
    receipt = json.loads(receipt_raw)
    if receipt != {"sha256": value["sha256"], "url": value["url"]}:
        raise ValueError("retained source receipt/body URL binding differs")


def prepare(selection: dict, evidence: dict) -> dict:
    """Validate Croft's exact identity, 2005 annual row, and August appearance."""
    if selection != {
        "provider_player_id": 27510, "name": "Lee Croft",
        "birth_date": "1985-06-21", "position": "M",
        "editorial_fine_role": 11, "editorial_role_policy": POLICY,
        "annual_squad": "city_annual", "entity": "tm_entity",
        "identity_witness": "soccerbase", "role_witness": "city_role",
        "country_witness": "uefa_country", "nationality": selection.get("nationality"),
        "nationality_label": selection.get("nationality_label"), "match": "city_august_match",
    }:
        raise ValueError("only the reviewed, literal Lee Croft selection is admitted")

    annual = evidence[selection["annual_squad"]]
    annual_raw = _raw(annual["path"], annual["sha256"])
    title = annual_raw.decode("utf-8-sig").splitlines()[0]
    if title.strip() != "=  Manchester City - English Premiership 2005/06":
        raise ValueError("annual FootballSquads title/period differs")
    lines = annual_raw.decode("utf-8-sig").splitlines()
    header = next((i for i, line in enumerate(lines) if line.startswith("Number,")), None)
    if header is None:
        raise ValueError("annual FootballSquads player table missing")
    rows = list(csv.DictReader(lines[header:], skipinitialspace=True))
    matches = [r for r in rows if (r.get("Name") or "").strip() == "Lee Croft"]
    if len(matches) != 1:
        raise ValueError("annual source must contain one literal Lee Croft row")
    row = matches[0]
    if row.get("Pos", "").strip() != "M" or row.get("Date of Birth", "").strip() != "21-06-85":
        raise ValueError("annual broad position or literal birthday differs")
    if row.get("Number", "").strip() != "40":
        raise ValueError("annual shirt number differs from retained row")

    entity = evidence[selection["entity"]]
    _receipt(entity)
    entity_raw = _raw(entity["path"], entity["sha256"])
    doc = json.loads(entity_raw)
    people = [p for p in doc.get("data", []) if p.get("id") == "27510"]
    if len(people) != 1:
        raise ValueError("original Transfermarkt entity response must contain exact ID")
    person = people[0]
    if (person.get("name"), person.get("lifeDates", {}).get("dateOfBirth")) != (
            "Lee Croft", "1985-06-21"):
        raise ValueError("entity identity/DOB differs")

    identity = evidence[selection["identity_witness"]]
    _receipt(identity)
    identity_raw = _raw(identity["path"], identity["sha256"])
    if identity["url"] != "https://www.soccerbase.com/players/player.sd?player_id=39644":
        raise ValueError("Soccerbase identity URL differs")
    # Secondary identity corroboration only; do not use its present-day role.
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(identity_raw, "html.parser")
    description = soup.select_one('meta[name="description"]')
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    desc = description.get("content", "") if description else ""
    if ("Lee Croft" not in title or "Born 21 Jun, 1985" not in desc):
        raise ValueError("retained Soccerbase page lacks exact identity description")

    country = evidence[selection["country_witness"]]
    country_raw = _raw(country["path"], country["sha256"])
    country_soup = BeautifulSoup(country_raw, "html.parser")
    country_title = country_soup.title.get_text(" ", strip=True) if country_soup.title else ""
    country_pub = country_soup.select_one('meta[property="article:published_time"]')
    country_text = " ".join(country_soup.get_text(" ", strip=True).split())
    if (country["url"] != "https://www.uefa.com/under17/news/0252-0cdd9fd52242-ec682b6a8221-1000--england-through-as-dutch-falter/"
            or not country_pub or country_pub.get("content", "")[:10] != "2002-04-29"
            or not country_title.startswith("England through")
            or "Lee Croft cut inside from the right" not in country_text):
        raise ValueError("official UEFA England youth match does not bind the exact named player/team/date")
    if (exchange.SOURCE_COUNTRIES.get(selection["nationality_label"]) != selection["nationality"]
            or selection["nationality"] != "ENG"
            or selection["nationality_label"] != "England"):
        raise ValueError("requested footballing-country code differs from the UEFA England witness")

    role = evidence[selection["role_witness"]]
    role_raw = _raw(role["path"], role["sha256"])
    role_text = BeautifulSoup(role_raw, "html.parser").get_text(" ", strip=True)
    if not all(term in role_text.casefold() for term in ("lee croft", "winger", "right wing")):
        raise ValueError("original Man City role witness does not support winger/right wing")
    if b'"datePublished":"2008-03-04"' not in role_raw:
        raise ValueError("official City role article date marker differs")
    if role["url"] != "https://www.mancity.com/news/first-team/first-team-news/archive/2008/march/the-25-who-broke-through-16-lee-croft":
        raise ValueError("role witness URL differs")

    fixture = evidence[selection["match"]]
    exchange.original(fixture)
    played = date.fromisoformat(fixture["date"])
    if (fixture.get("provider_club_id") != 281 or played.isoformat() != "2005-08-13"
            or fixture.get("membership_mode") != "classic-played-substitutes"
            or fixture.get("url") != "https://www.transfermarkt.co.uk/spielbericht/index/spielbericht/35796"):
        raise ValueError("fixture is not the exact dated City used-substitute witness")
    exchange.verify_match_club(fixture, "Manchester City")
    xi, subs = exchange.match_people(fixture)
    if (any(p.get("source_player_id") == "27510" for p in xi)
            or sum(p.get("source_player_id") == "27510" for p in subs) != 1):
        raise ValueError("numeric person 27510 must be exactly one played substitute")

    return dict(
        source_person=dict(name="Lee Croft", birth_date="1985-06-21",
            source_player_id=27510, source_provider="transfermarkt",
            source_profile_url="https://www.transfermarkt.co.uk/lee-croft/profil/spieler/27510"),
        source_player=dict(name="Lee Croft", birth_date="1985-06-21",
            position="M", nationality="ENG", height_cm=None, weight_kg=None,
            shirt_number=40),
        raw_evidence=dict(status="raw-source-reparsed", local_path=annual["path"],
            source_sha256=annual["sha256"], biography_source_kind="footballsquads-annual-broad-role",
            profile_page_captured=False,
            country=dict(code="ENG", label="England", basis="UEFA youth-team representation",
                country_is_exclusive_citizenship=False, witness_url=country["url"],
                witness_sha256=country["sha256"], witness_date="2002-04-29"),
            editorial_fine_role=dict(value=11,
                label="Right Winger", policy=POLICY, role_is_historical_fact=False,
                witness_url=role["url"], witness_sha256=role["sha256"])),
        membership="original-published-August-used-substitute",
        membership_evidence=dict(match_url=fixture["url"], date=played.isoformat(),
            provider_club_id=281, source_player_id="27510",
            basis="published-used-substitute-not-complete-bench"))
