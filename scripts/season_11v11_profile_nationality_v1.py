"""Strict 11v11 Norway biography-nationality admission for the common country delta.

This module admits explicit biography nationality only. A target-season scope is
bound to the same full identity and dated club-career row; it does not claim
national-team eligibility or citizenship at a particular instant. This provider
policy is limited to Norwegian nationality and its reviewed Ostenstad source
packet; other country/provider combinations remain unsupported.
"""
from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_nationality import rewrite_indexed_native_nationalities
from scripts import season_package_v2 as packages
from scripts import season_package_compiler_v2 as compiler
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_opening_order_repair_v1 as ownership
from scripts.season_historical_roster_audit_v1 import native_player, normalise
from scripts.season_within_club_reserve_repair_v1 import native_facts
from scripts.season_historical_player_facts_audit_v1 import country as source_country_code

SCHEMA = "pm99-explicit-source-backed-player-field-changes-v1"
INPUT_SCHEMA = "pm99-explicit-source-backed-player-change-input-v1"
KIND = "known-wrong-profile-nationality"
MODE = "known-good-baseline-explicit-source-backed-player-changes-v1"
FIELD_MASK = ["nationality"]
SOURCE_CODES = {"Norwegian": "NOR", "Norway": "NOR", "Norge": "NOR"}


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _workspace_file(relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute():
        raise ValueError("source paths must be workspace relative")
    resolved = (registry.ROOT / path).resolve()
    if not resolved.is_relative_to(registry.ROOT.resolve()) or not resolved.is_file():
        raise ValueError("source path is outside retained workspace evidence")
    return resolved


def _capture(source: dict) -> tuple[bytes, dict]:
    required = {"provider", "provider_player_id", "url", "path", "sha256",
                "receipt_path", "receipt_sha256", "receipt_key"}
    if set(source) != required or source["provider"] != "11v11":
        raise ValueError("exact typed 11v11 source binding required")
    pid = source["provider_player_id"]
    if type(pid) is not int or pid < 1:
        raise ValueError("positive numeric 11v11 profile ID required")
    parsed = urlsplit(source["url"])
    if (parsed.scheme != "https" or parsed.netloc != "www.11v11.com"
            or parsed.query or parsed.fragment
            or not re.fullmatch(rf"/players/[a-z0-9-]+-{pid}/?", parsed.path)):
        raise ValueError("11v11 canonical player URL/ID differs")
    body_path = _workspace_file(source["path"])
    receipt_path = _workspace_file(source["receipt_path"])
    body = body_path.read_bytes()
    receipt = pipeline.read_json_file(receipt_path)
    row = receipt.get("sources", {}).get(source["receipt_key"])
    if (not isinstance(row, dict)
            or row.get("requested_url") != source["url"]
            or row.get("final_url") != source["url"]
            or row.get("status") != 200
            or row.get("body_path") != registry.relative_workspace_path(body_path)
            or row.get("body_sha256") != source["sha256"]
            or row.get("body_sha256") != sha256(body)
            or registry.sha256_file(receipt_path) != source["receipt_sha256"]):
        raise ValueError("11v11 body/URL/original capture receipt differs")
    return body, row


def _text(page) -> str:
    return " ".join(page.get_text(" ", strip=True).split())


def _one_value(raw: bytes, label: str) -> str:
    page = BeautifulSoup(raw, "lxml")
    matches = []
    for row in page.select("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) != 2:
            continue
        if " ".join(cells[0].get_text(" ", strip=True).split()).rstrip(":") == label:
            matches.append(" ".join(cells[1].get_text(" ", strip=True).split()))
    if len(matches) != 1 or not matches[0]:
        raise ValueError(f"11v11 requires exactly one explicit {label} field")
    return matches[0]


def parse_profile(raw: bytes, source: dict, *, full_name: str,
                  birth_date: str, requested_country: str) -> dict:
    """Parse full identity and the profile's own `Nationality` row."""
    pid = source["provider_player_id"]
    url = source["url"]
    page = BeautifulSoup(raw, "lxml")
    title = page.title.get_text(" ", strip=True) if page.title else ""
    h1 = [" ".join(node.get_text(" ", strip=True).split())
          for node in page.find_all("h1")]
    # 11v11 identifies the profile in its title and h1 rather than a canonical
    # link; the numeric ID is bound by the exact retained URL path and receipt.
    expected_title = f"{full_name} Football Player Statistics | 11v11.com"
    if title != expected_title or h1 != [full_name]:
        raise ValueError("11v11 title/profile heading does not publish the exact full name")
    dob_label = _one_value(raw, "Date of birth")
    try:
        published_dob = datetime.strptime(dob_label, "%d %B %Y").date().isoformat()
    except ValueError as exc:
        raise ValueError("11v11 date of birth is not an exact published date") from exc
    if published_dob != birth_date:
        raise ValueError("11v11 exact DOB differs from the selected recipe identity")
    label = _one_value(raw, "Nationality")
    code = SOURCE_CODES.get(label) or source_country_code(label)
    if code is None or code != requested_country:
        raise ValueError("11v11 explicit nationality label/code differs")
    if "Place of birth" in [
            " ".join(c.get_text(" ", strip=True).split()).rstrip(":")
            for tr in page.select("tr") for c in tr.find_all(["th", "td"], recursive=False)[:1]]:
        # Retain this explicit distinction as a guard against future parser
        # edits that accidentally reuse the birthplace row.
        place = _one_value(raw, "Place of birth")
    else:
        place = None
    return dict(provider="11v11", provider_player_id=pid, url=url,
        name=full_name, birth_date=published_dob,
        published_nationality_label=label, nationality=code,
        place_of_birth=place, target_season_ownership_claimed=False,
        national_team_eligibility_claimed=False,
        policy="explicit-11v11-biography-nationality-not-birthplace-or-cap-eligibility-v1")


def _verify_period(raw: bytes, period: dict, *, full_name: str,
                   birth_date: str) -> dict:
    """Require a declared reviewed year/club scope supported by profile rows."""
    allowed = {"season", "club", "opening_date", "scope_review", "evidence"}
    if set(period) != allowed or period["scope_review"] != (
            "biographical-nationality-on-exact-person; not national-team eligibility"):
        raise ValueError("explicit narrow period scope and nonclaim required")
    season = period["season"]
    if not re.fullmatch(r"\d{4}-\d{2}", season):
        raise ValueError("target season must be YYYY-YY")
    start = int(season[:4])
    if period["opening_date"] != f"{start:04d}-08-01":
        raise ValueError("period scope must name the August 1 identity checkpoint")
    evidence = period["evidence"]
    if evidence != {"provider": "11v11", "basis": "same-profile exact full-name/DOB and season club row"}:
        raise ValueError("period evidence must bind to the parsed 11v11 profile row")
    if period["club"] != "Blackburn Rovers":
        raise ValueError("this reusable 11v11 candidate is limited to an explicit reviewed club row")
    page = BeautifulSoup(raw, "lxml")
    matches = []
    for table in page.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header = [" ".join(cell.get_text(" ", strip=True).split())
                  for cell in rows[0].find_all(["th", "td"], recursive=False)]
        if not {"Season", "Team"}.issubset(set(header)):
            continue
        si, ti = header.index("Season"), header.index("Team")
        for row in rows[1:]:
            cells = [" ".join(cell.get_text(" ", strip=True).split())
                     for cell in row.find_all(["th", "td"], recursive=False)]
            if len(cells) > max(si, ti) and cells[si] == season and cells[ti] == period["club"]:
                matches.append(cells)
    if not matches:
        raise ValueError("11v11 profile has no exact target-season club-career row")
    return dict(season=season, club=period["club"], profile_rows=matches,
                ownership_or_appearance_claimed=False)


def _capture_source(source: dict) -> tuple[bytes, dict]:
    body_path = _workspace_file(source["path"])
    receipt_path = _workspace_file(source["receipt_path"])
    body = body_path.read_bytes()
    receipt = pipeline.read_json_file(receipt_path)
    row = receipt.get("sources", {}).get(source["receipt_key"])
    if (row is None or row.get("requested_url") != source["url"]
            or row.get("final_url") != source["url"] or row.get("status") != 200
            or row.get("body_path") != registry.relative_workspace_path(body_path)
            or row.get("body_sha256") != source["sha256"]
            or source["sha256"] != sha256(body)
            or registry.sha256_file(receipt_path) != source["receipt_sha256"]):
        raise ValueError("supporting source receipt/body binding differs")
    return body, row


def _supporting_identity(source: dict, full_name: str, nationality: str) -> dict:
    raw, _ = _capture_source(source)
    text = _text(BeautifulSoup(raw, "lxml"))
    requirements = source.get("period_literal_claims")
    country_label = source.get("nationality_label")
    country_literal = source.get("nationality_literal")
    name_literal = source.get("identity_name_literal")
    from scripts.season_opening_identity_exchange_v1 import published_name_key
    profile_tokens = sorted(published_name_key(token) for token in full_name.split())
    cited_names = name_literal.replace(",", " ").split() if isinstance(name_literal, str) else []
    if (not isinstance(requirements, list) or not requirements
            or any(not isinstance(v, str) or not v for v in requirements)
            or any(v not in text for v in requirements)
            or not any(sorted(published_name_key(token) for token in name) == profile_tokens
                       for name in [cited_names])
            or not isinstance(country_label, str) or not isinstance(country_literal, str)
            or f"{country_label} {country_literal}" not in text
            or (SOURCE_CODES.get(country_literal) or source_country_code(country_literal)) != nationality):
        raise ValueError("independent career/nationality source lacks its declared literal claims")
    return dict(provider=source["provider"], url=source["url"],
        sha256=source["sha256"], identity_name_literal=name_literal,
        nationality_label=country_label, nationality_literal=country_literal,
        verified_period_literals=requirements, nationality=nationality,
        profile_dob_not_claimed=True)


def prepare(base, input_path):
    path = Path(input_path)
    if not path.is_absolute():
        path = registry.ROOT / path
    path = path.resolve()
    if not path.is_relative_to(registry.ROOT.resolve()) or not path.is_file():
        raise ValueError("11v11 country input must be retained in the workspace")
    request = pipeline.read_json_file(path)
    if (request.get("schema") != INPUT_SCHEMA or request.get("kind") != KIND
            or request.get("season") != base.season or request.get("release_id") != base.release_id
            or not request.get("changes")):
        raise ValueError("exact registered parent and known-wrong country request required")
    package = pipeline.read_json_file(base.package_path)
    actors = {p["carrier_id"]: p for p in package["players"]}
    clubs = {c["id"]: c for c in package["clubs"]}
    jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    owners = ownership.native_owners(eq)
    codes = compiler._extract_country_codes_from_textos(base.game_path / "DBDAT/TEXTOS.PKF")
    updates, seen = [], set()
    for selected in request["changes"]:
        carrier = selected.get("carrier_id")
        if (type(carrier) is not int or carrier in seen
                or selected.get("field_mask") != FIELD_MASK):
            raise ValueError("unique actor and nationality-only field mask required")
        seen.add(carrier)
        actor = actors[carrier]
        club = clubs[actor["club_id"]]
        full_name = selected.get("full_name")
        dob = selected.get("birth_date")
        country = selected.get("nationality")
        period = selected.get("period_scope")
        if (full_name != (actor.get("source_name") or actor["name"])
                or dob != actor["facts"].get("birth_date")
                or country != "NOR" or not isinstance(period, dict)
                or period.get("season") != base.season):
            raise ValueError("source full identity, ISO country, and target period must match actor")
        source = selected["source"]
        body, _ = _capture(source)
        identity = parse_profile(body, source, full_name=full_name,
            birth_date=dob, requested_country=country)
        career = _verify_period(body, period, full_name=full_name, birth_date=dob)
        supporting = _supporting_identity(selected["supporting_source"], full_name, country)
        native = native_facts(jug, carrier)
        entry = entries[carrier]
        payload = entry.decode_payload(jug)
        end = native_player(payload, carrier)["name_end"]
        old_code = codes.get(selected.get("native_before_country"))
        offset = entry.payload_offset + end + 8
        if (selected.get("recipe_before_nationality") != actor["facts"].get("nationality")
                or native["birth_date"] != dob
                or normalise(native["name"]) != normalise(actor["name"])
                or owners.get(carrier) != {club["carrier_id"]}
                or old_code is None or old_code == codes["XXX"]
                or (payload[end + 8] ^ 0x61) != old_code
                or jug[offset] != (payload[end + 8] ^ 0x61)):
            raise ValueError("native/recipe/DOB/owner country preimage differs")
        after_code = compiler._country_code(identity["nationality"], codes)
        if after_code == old_code:
            raise ValueError("11v11 country source is a native no-op")
        updates.append(dict(carrier_id=carrier, before=copy.deepcopy(actor),
            nationality=identity["nationality"], field_mask=FIELD_MASK[:],
            native_mask=dict(file="DBDAT/JUG98030.FDI", record_offset=end+8,
                file_offset=offset, before=jug[offset], after=after_code),
            source_identity=dict(**identity, target_period_career=career,
                supporting_career_country_source=supporting),
            source=dict(path=source["path"], sha256=source["sha256"]),
            source_receipt=dict(path=source["receipt_path"], sha256=source["receipt_sha256"]),
            expected_owner=club["carrier_id"]))
    result = dict(schema=SCHEMA, season=base.season, release_id=base.release_id,
        kind=KIND, source_input=dict(path=registry.relative_workspace_path(path),
            sha256=registry.sha256_file(path)), package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=sha256(jug), eq_sha256=sha256(eq),
        textos_sha256=registry.sha256_file(base.game_path / "DBDAT/TEXTOS.PKF"),
        updates=updates,
        scope="Only exact recipe nationality fields and one native country byte per actor; biography nationality applies to the reviewed same-person club period, without claiming national-team eligibility, exact citizenship-at-date, appearances, or changes to any other facts/assets.",
        source_policy="11v11-exact-numeric-profile-name-DOB-explicit-Nationality-plus-reviewed-season-career-row-v1")
    result["transaction_id"] = sha256(packages.canonical_json_bytes(result))[:24]
    validate_plan(result)
    return result


def validate_plan(plan):
    rows = plan.get("updates", [])
    if (plan.get("schema") != SCHEMA or plan.get("kind") != KIND or not rows
            or len({r.get("carrier_id") for r in rows}) != len(rows)):
        raise ValueError("nonempty unique 11v11 country-only plan required")
    offsets = set()
    for row in rows:
        if (set(row) != {"carrier_id", "before", "nationality", "field_mask",
                "native_mask", "source_identity", "source", "source_receipt", "expected_owner"}
                or row["field_mask"] != FIELD_MASK or row["nationality"] != "NOR"
                or row["source_identity"].get("provider") != "11v11"
                or row["source_identity"].get("national_team_eligibility_claimed") is not False):
            raise ValueError("country-only plan has unsupported fields or claims")
        mask = row["native_mask"]
        if (set(mask) != {"file", "record_offset", "file_offset", "before", "after"}
                or mask["file"] != "DBDAT/JUG98030.FDI"
                or type(mask["record_offset"]) is not int or type(mask["file_offset"]) is not int
                or type(mask["before"]) is not int or type(mask["after"]) is not int
                or mask["before"] == mask["after"] or mask["file_offset"] in offsets):
            raise ValueError("exact unique one-byte native country mask required")
        offsets.add(mask["file_offset"])


def verify(base, plan):
    if plan.get("schema") != SCHEMA:
        raise ValueError("unsupported 11v11 country plan")
    source = _workspace_file(plan["source_input"]["path"])
    if (registry.sha256_file(source) != plan["source_input"]["sha256"]
            or prepare(base, source) != plan):
        raise ValueError("11v11 country plan did not reproduce from exact sources")


def bind(package, plan):
    """Use the common recipe binder so proof shape stays uniform."""
    from scripts import season_source_verified_player_changes_v1 as common
    return common.bind(package, plan)


def apply(jug, eq, plan):
    """Use the common paired-native writer and its exact byte-mask checks."""
    from scripts import season_source_verified_player_changes_v1 as common
    return common.apply(jug, eq, plan)

def source_artifact(plan):
    validate_plan(plan)
    return packages.canonical_json_bytes(plan)


def reject_factory_recipe(package):
    if any(a.get("id", "").startswith("source-backed-player-changes-")
           for a in package.get("artifacts", [])):
        raise ValueError("11v11 source-country proof requires source-bound reconstruction")
