"""Isolated proposal for annual squad biography + exact August match evidence.

This deliberately does not alter or monkey-patch the canonical opening-exchange
API. It reuses its existing original-source readers and only tests the proposed
input contract for a narrowly scoped used-substitute admission.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_release_registry_v1 as registry
from scripts import season_transfermarkt_squad_biography_v1 as biographies
from scripts.season_exact_fifa_role_delta_v1 import compatible
from scripts.season_historical_role_plan_v1 import HTML_ROLES


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _receipt(value: dict) -> Path:
    """Bind one explicit provider receipt to its retained original body."""
    body_path = exchange.original(value)
    claim = value.get("receipt")
    if not isinstance(claim, dict) or set(claim) != {"path", "sha256"}:
        raise ValueError("original squad/person source receipt binding required")
    receipt_path = (registry.ROOT / claim["path"]).resolve()
    if not receipt_path.is_relative_to(registry.ROOT.resolve()) or not receipt_path.is_file():
        raise ValueError("source receipt must be a retained workspace file")
    if registry.sha256_file(receipt_path) != claim["sha256"]:
        raise ValueError("source receipt hash differs")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt != {"sha256": value["sha256"], "url": value["url"]}:
        raise ValueError("source receipt URL/body hash differs")
    return body_path


def prepare(selection: dict, evidence: dict, *, season: str) -> dict:
    """Prepare one exact annual-biography + played-August-substitute person.

    The sole membership route here is `squad_context` plus `match`. It does
    not accept an opening-contract claim, a profile substitute, or annual
    membership alone. The match proves an appearance, not an unused bench.
    """
    if not isinstance(selection, dict) or not isinstance(evidence, dict):
        raise ValueError("explicit person selection and original evidence map required")
    if ("squad_biography" not in selection or "squad_context" not in selection
            or "match" not in selection or "opening_contract" in selection
            or "profile" in selection or "native_display_name" in selection):
        raise ValueError("this route requires only squad biography + exclusive dated context + match")
    context = selection["squad_context"]
    if (not isinstance(context, dict)
            or set(context) != {"season_start_year", "provider_club_id", "club_name"}
            or type(context["season_start_year"]) is not int or context["season_start_year"] < 1900
            or type(context["provider_club_id"]) is not int or context["provider_club_id"] <= 0
            or not isinstance(context["club_name"], str) or not context["club_name"].strip()):
        raise ValueError("one exact target-season/provider-club squad context required")
    year = context["season_start_year"]
    expected_season = f"{year}-{str(year + 1)[-2:]}"
    if season != expected_season:
        raise ValueError("squad context season differs from the requested season")
    pid = selection.get("provider_player_id")
    if type(pid) is not int or pid <= 0:
        raise ValueError("exact numeric Transfermarkt person ID required")

    annual = evidence[selection["squad_biography"]]
    _receipt(annual)
    witness = annual.get("birth_date_witness")
    if not isinstance(witness, dict):
        raise ValueError("independent exact birthday witness required")
    _receipt(witness)
    parsed = biographies.read(annual, pid, season=season,
        club_name=context["club_name"], provider_club_id=context["provider_club_id"])
    if (parsed["published_full_name"], parsed["published_birth_date"]) != (
            selection.get("name"), selection.get("birth_date")):
        raise ValueError("annual row source identity or literal DOB differs")
    role = selection.get("profile_position")
    role_key = re.sub(r"[^a-z]", "", role.casefold()) if isinstance(role, str) else ""
    if (role != parsed["published_profile_position"] or role_key not in HTML_ROLES
            or selection.get("fine_roles") != [HTML_ROLES[role_key]]
            or not compatible(selection.get("position"), HTML_ROLES[role_key])):
        raise ValueError("exact annual detailed role and broad/fine selection disagree")
    labels = parsed["published_nationality_label"].split(" / ")
    label = selection.get("nationality_label")
    if label not in labels or exchange.SOURCE_COUNTRIES.get(label) != selection.get("nationality"):
        raise ValueError("selected country must be one exact annual row nationality label")

    fixture = evidence[selection["match"]]
    exchange.original(fixture)
    url = urlsplit(fixture.get("url", ""))
    match_id = re.search(r"^/spielbericht/index/spielbericht/([1-9][0-9]*)$", url.path)
    try:
        played = date.fromisoformat(fixture["date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("exact ISO August match date required") from exc
    if (url.scheme != "https" or url.netloc not in {"www.transfermarkt.co.uk", "www.transfermarkt.com"}
            or url.query or url.fragment or match_id is None
            or fixture.get("provider_club_id") != context["provider_club_id"]
            or played.year != year or played.month != 8
            or fixture.get("membership_mode") != "classic-played-substitutes"):
        raise ValueError("match must be an exact same-club, same-season August played-substitute report")
    exchange.verify_match_club(fixture, context["club_name"])
    xi, played_subs = exchange.match_people(fixture)
    if (any(row.get("source_player_id") == str(pid) for row in xi)
            or sum(row.get("source_player_id") == str(pid) for row in played_subs) != 1):
        raise ValueError("same numeric person must occur exactly once as a played substitute")

    return dict(
        source_person=dict(name=selection["name"], birth_date=parsed["published_birth_date"],
            source_player_id=pid, source_provider="transfermarkt",
            source_profile_url=parsed["linked_profile_url"]),
        source_player=dict(name=selection["name"], birth_date=parsed["published_birth_date"],
            position=selection["position"], nationality=selection["nationality"],
            height_cm=parsed["published_height_cm"], weight_kg=None,
            shirt_number=parsed["published_shirt_number"]),
        raw_evidence=dict(status="raw-source-reparsed", local_path=annual["path"],
            source_sha256=annual["sha256"], biography_source_kind=parsed["biography_source_kind"],
            profile_page_captured=False),
        membership="original-published-August-used-substitute",
        membership_evidence=dict(match_url=fixture["url"], match_id=int(match_id[1]),
            provider_club_id=context["provider_club_id"], date=played.isoformat(),
            source_player_id=str(pid), basis="published-used-substitute-not-complete-bench"))
