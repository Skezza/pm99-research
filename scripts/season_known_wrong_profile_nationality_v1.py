"""Admit narrowly sourced corrections to known-wrong nationality fields.

The existing source-backed writer authenticates this plan before applying its
one-byte masks. Exact-name Soccerbase and a canonical DFB profile are supported;
this module does not provide a separate native writer or certify club ownership.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from scripts import season_soccerbase_secondary_facts_v2 as soccerbase
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as packages
from scripts import season_quality_only_delta_v1 as native
from scripts import season_opening_order_repair_v1 as ownership
from app.fdi_indexed import IndexedFDIFile
from scripts.season_historical_roster_audit_v1 import native_player, normalise

KIND = "known-wrong-profile-nationality"
DFB_URL = "https://datencenter.dfb.de/en/data-center/people/christian-fiedler/player"
DFB_NAME = "Christian Fiedler"
DFB_DOB = "1975-03-27"
DFB_COUNTRY = "Germany"
WIKIDATA_QID = "Q552710"
WIKIDATA_URL = "https://www.wikidata.org/wiki/Special:EntityData/Q552710.json"
WIKIDATA_LABEL = "Dmitri Kharine"
WIKIDATA_ALIAS = "Dmitri Kharin"
SOCCERBASE_KHARIN_ID = 4177
KEVIN_DFB_URL = "https://datencenter.dfb.de/datencenter/personen/kevin-stuhr-ellegaard/spieler"
KEVIN_DFB_NAME = "Kevin Stuhr-Ellegaard"
KEVIN_DFB_DOB = "1983-05-23"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _one_table_value(raw: bytes, label: str) -> str:
    soup = BeautifulSoup(raw, "lxml")
    found = []
    for row in soup.select("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) != 2:
            continue
        key = " ".join(cells[0].get_text(" ", strip=True).split()).rstrip(":")
        if key == label:
            found.append(" ".join(cells[1].get_text(" ", strip=True).split()))
    if len(found) != 1 or not found[0]:
        raise ValueError(f"DFB profile requires exactly one nonempty {label} row")
    return found[0]


def parse_dfb_fiedler(raw: bytes, *, url: str, name: str, birth_date: str) -> dict:
    """Parse only DFB's canonical Fiedler profile and its explicit Nation row."""
    if url != DFB_URL:
        raise ValueError("DFB profile URL must be the canonical exact profile URL")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "datencenter.dfb.de"
            or parsed.path != "/en/data-center/people/christian-fiedler/player"
            or parsed.query or parsed.fragment):
        raise ValueError("noncanonical DFB profile URL")
    soup = BeautifulSoup(raw, "lxml")
    canonical = soup.find_all("link", rel=lambda value:
        value is not None and "canonical" in (value if isinstance(value, list) else value.split()))
    if len(canonical) != 1 or canonical[0].get("href") != DFB_URL:
        raise ValueError("DFB body must publish exactly the canonical Fiedler profile URL")
    published_name = _one_table_value(raw, "Name")
    published_dob = _one_table_value(raw, "Date of birth")
    nation = _one_table_value(raw, "Nation")
    if (name, birth_date) != (DFB_NAME, DFB_DOB):
        raise ValueError("DFB parser is bound only to exact Christian Fiedler identity")
    if (published_name, published_dob, nation) != (DFB_NAME, DFB_DOB, DFB_COUNTRY):
        raise ValueError("DFB canonical identity, DOB, or explicit Nation claim differs")
    return dict(name=published_name, birth_date=published_dob,
                published_country=nation, nationality="GER",
                provider="dfb-canonical-fiedler-profile-v1", url=DFB_URL,
                target_season_ownership_claimed=False)


def parse_profile_country(raw: bytes, source: dict, *, actor_name: str,
                          birth_date: str) -> dict:
    """Dispatch to exact Soccerbase parser or the one admitted DFB parser."""
    provider = source.get("provider")
    if provider == 'uefa-player-roster-table-pdf-v1':
        from scripts.season_uefa_roster_profile_admission_v1 import parse_country
        return parse_country(raw, source, actor_name=actor_name, birth_date=birth_date)
    if provider == "dfb-kevin-stuhr-ellegaard-canonical":
        return parse_dfb_kevin(raw, url=source["url"], name=actor_name,
                               birth_date=birth_date)
    if provider == "soccerbase":
        bridge_ref = source.get("identity_bridge")
        if bridge_ref is not None:
            return parse_soccerbase_country_with_bridge(raw, source,
                actor_name=actor_name, birth_date=birth_date, bridge_ref=bridge_ref)
        # The downstream parser validates the numeric query, literal name/DOB,
        # and exactly one explicit `Nationality` cell. There is no alias path.
        parsed = soccerbase.country(raw, person_id=source["provider_player_id"],
            name=actor_name, birth_date=birth_date, url=source["url"])
        return dict(name=parsed["identity"]["name"],
            birth_date=parsed["identity"]["birth_date"],
            published_country=parsed["published_country"],
            nationality=parsed["nationality"], provider="soccerbase-exact-profile-v2",
            url=source["url"], provider_player_id=source["provider_player_id"],
            target_season_ownership_claimed=False)
    if provider == "dfb-fiedler-canonical":
        return parse_dfb_fiedler(raw, url=source["url"], name=actor_name,
                                 birth_date=birth_date)
    raise ValueError("unsupported known-wrong nationality source provider")


def parse_dfb_kevin(raw: bytes, *, url: str, name: str, birth_date: str) -> dict:
    """Read one exact German DFB identity/Nation claim, not birthplace or club."""
    if (url != KEVIN_DFB_URL or name != KEVIN_DFB_NAME or birth_date != KEVIN_DFB_DOB):
        raise ValueError("DFB Kevin profile requires the exact canonical URL/full name/DOB")
    page = BeautifulSoup(raw, "lxml")
    if [link.get("href") for link in page.select("link[rel~=canonical]")] != [KEVIN_DFB_URL]:
        raise ValueError("DFB Kevin body must publish exactly one matching canonical URL")
    values = tuple(_one_table_value(raw, label) for label in ("Name", "Geburtstag", "Nation"))
    if values != (KEVIN_DFB_NAME, "23.05.1983", "Dänemark"):
        raise ValueError("DFB Kevin literal name, Geburtstag or Nation differs")
    return dict(name=values[0], birth_date=birth_date, published_country=values[2],
        nationality="DEN", provider="dfb-canonical-kevin-stuhr-ellegaard-v1",
        url=url, target_season_ownership_claimed=False)


def profile_receipt(body_path: Path, source: dict) -> tuple[Path, dict]:
    """Permit a hash-bound explicit capture receipt; preserve legacy lookup."""
    relative, expected = source.get("receipt_path"), source.get("receipt_sha256")
    if (relative is None) != (expected is None):
        raise ValueError("receipt_path and receipt_sha256 must be supplied together")
    from scripts.season_source_verified_player_changes_v1 import original_path
    if relative is None:
        path = body_path.with_suffix(body_path.suffix + ".source.json")
    else:
        if (type(relative) is not str or not relative or type(expected) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected) is None):
            raise ValueError("typed receipt requires a relative path and lowercase SHA256")
        path = original_path(relative)
        if path.is_symlink() or registry.sha256_file(path) != expected:
            raise ValueError("typed receipt file/hash differs")
    receipt = pipeline.read_json_file(path)
    if source.get('provider') == 'uefa-player-roster-table-pdf-v1':
        if receipt.get('url') != source.get('url') or receipt.get('raw_sha256') != source.get('sha256'):
            raise ValueError('UEFA original PDF receipt/body binding differs')
        receipt = {**receipt, 'sha256': receipt['raw_sha256']}
    return path, receipt


def _unique_claim_value(entity: dict, property_id: str):
    statements = entity.get("claims", {}).get(property_id)
    if not isinstance(statements, list) or len(statements) != 1:
        raise ValueError(f"Wikidata bridge requires one unique {property_id} statement")
    statement = statements[0]
    snak = statement.get("mainsnak", {})
    if (statement.get("rank") != "normal" or snak.get("property") != property_id
            or snak.get("snaktype") != "value"):
        raise ValueError(f"Wikidata bridge rejects non-normal or non-value {property_id}")
    datavalue = snak.get("datavalue", {})
    if datavalue.get("type") != ("time" if property_id == "P569" else "string"):
        raise ValueError(f"Wikidata bridge {property_id} datatype differs")
    return datavalue.get("value")


def parse_wikidata_alias_bridge(raw: bytes, receipt: dict, *, expected_sha256: str,
                                expected_qid: str, expected_url: str) -> dict:
    """Strictly validate identity-link facts only; never infer nationality."""
    if (expected_qid != WIKIDATA_QID or expected_url != WIKIDATA_URL
            or sha256(raw) != expected_sha256
            or receipt.get("sha256") != expected_sha256
            or receipt.get("url") != WIKIDATA_URL
            or receipt.get("final_url") != WIKIDATA_URL
            or receipt.get("http_status") != 200
            or receipt.get("method") != "original-network-JSON"):
        raise ValueError("Wikidata bridge body or network receipt binding differs")
    try:
        doc = json.loads(raw)
        entity = doc["entities"][WIKIDATA_QID]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("Wikidata bridge JSON does not contain the exact entity") from exc
    label = entity.get("labels", {}).get("en", {})
    aliases = entity.get("aliases", {}).get("en", [])
    matches = [entry.get("value") for entry in aliases
               if isinstance(entry, dict) and entry.get("language") == "en"
               and entry.get("value") == WIKIDATA_ALIAS]
    dob = _unique_claim_value(entity, "P569")
    soccerbase_id = _unique_claim_value(entity, "P2193")
    expected_time = {"time": "+1968-08-16T00:00:00Z", "timezone": 0,
        "before": 0, "after": 0, "precision": 11,
        "calendarmodel": "http://www.wikidata.org/entity/Q1985727"}
    if (entity.get("id") != WIKIDATA_QID
            or label.get("language") != "en" or label.get("value") != WIKIDATA_LABEL
            or matches != [WIKIDATA_ALIAS] or dob != expected_time
            or soccerbase_id != str(SOCCERBASE_KHARIN_ID)):
        raise ValueError("Wikidata bridge exact QID, English label/alias, DOB, or Soccerbase ID differs")
    return dict(qid=WIKIDATA_QID, english_label=WIKIDATA_LABEL,
        english_alias=WIKIDATA_ALIAS, birth_date="1968-08-16",
        soccerbase_player_id=SOCCERBASE_KHARIN_ID,
        identity_link_only=True, nationality_claimed=False)


def parse_soccerbase_country_with_bridge(raw: bytes, source: dict, *, actor_name: str,
                                         birth_date: str, bridge_ref: dict) -> dict:
    """Use Wikidata solely to bridge exact English name and Soccerbase ID."""
    allowed = {"qid", "url", "path", "sha256", "receipt_path", "receipt_sha256"}
    if (set(bridge_ref) != allowed or actor_name != WIKIDATA_LABEL
            or birth_date != "1968-08-16"
            or source.get("provider_player_id") != SOCCERBASE_KHARIN_ID
            or source.get("url") != "https://www.soccerbase.com/players/player.sd?player_id=4177"):
        raise ValueError("Wikidata alias bridge is only valid for exact Kharine/Kharin source identity")
    from scripts.season_source_verified_player_changes_v1 import original_path
    body_path = original_path(bridge_ref["path"])
    receipt_path = original_path(bridge_ref["receipt_path"])
    bridge_raw = body_path.read_bytes()
    receipt_raw = receipt_path.read_bytes()
    if sha256(bridge_raw) != bridge_ref["sha256"] or sha256(receipt_raw) != bridge_ref["receipt_sha256"]:
        raise ValueError("Wikidata bridge source or receipt-file hash differs")
    try:
        receipt = json.loads(receipt_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Wikidata bridge receipt is not JSON") from exc
    bridge = parse_wikidata_alias_bridge(bridge_raw, receipt,
        expected_sha256=bridge_ref["sha256"], expected_qid=bridge_ref["qid"],
        expected_url=bridge_ref["url"])
    # Soccerbase's existing source table only maps four British nationalities;
    # this exact profile explicitly says Russia. Extend only that exact label.
    parsed = soccerbase.country(raw, person_id=SOCCERBASE_KHARIN_ID,
        name=WIKIDATA_ALIAS, birth_date=birth_date, url=source["url"],
        nationality_codes={**soccerbase.NATIONALITY, "Russia": "RUS"})
    if parsed["identity"]["name"] != WIKIDATA_ALIAS:
        raise ValueError("Soccerbase literal profile name is not the bridged English alias")
    return dict(name=parsed["identity"]["name"], birth_date=parsed["identity"]["birth_date"],
        published_country=parsed["published_country"], nationality=parsed["nationality"],
        provider="soccerbase-exact-profile-with-wikidata-name-bridge-v1",
        url=source["url"], provider_player_id=SOCCERBASE_KHARIN_ID,
        identity_bridge={**bridge, "url": bridge_ref["url"],
            "path": bridge_ref["path"], "sha256": bridge_ref["sha256"],
            "receipt_path": bridge_ref["receipt_path"],
            "receipt_sha256": bridge_ref["receipt_sha256"]},
        target_season_ownership_claimed=False,
        nationality_inferred_from_bridge=False)


def prepare_row(*, season: str, club: dict, actor: dict, source: dict, body: bytes, receipt: dict,
                receipt_path: str, receipt_sha256: str,
                native_name: str, native_birth_date: str, native_country: str,
                recipe_before_nationality,
                owners: set[int], expected_owner: int, record_offset: int,
                file_offset: int, native_byte_before: int, country_codes: dict) -> dict:
    """Validate one exact recipe/native/source/owner preimage and return a row.

    This changes a country fact only. The exclusive owner check is a technical
    native precondition and must not be presented as historical club-membership
    proof; the profile parser does not claim target-season ownership.
    """
    if (receipt.get("url") != source.get("url")
            or receipt.get("sha256") != sha256(body)
            or source.get("sha256") != sha256(body)):
        raise ValueError("source body hash or URL receipt differs")
    actor_source_name = actor.get("source_name") or actor.get("name")
    actor_dob = actor.get("facts", {}).get("birth_date")
    if (not actor_source_name or not actor_dob or normalise(native_name) != normalise(actor.get("name"))
            or native_birth_date != actor_dob):
        raise ValueError("recipe/native actor identity or exact DOB differs")
    if (type(expected_owner) is not int or owners != {expected_owner}
            or club.get("carrier_id") != expected_owner or actor.get("club_id") != club.get("id")):
        raise ValueError("actor must have exactly the declared exclusive native owner")
    recipe_before = actor.get("facts", {}).get("nationality")
    if recipe_before_nationality != recipe_before:
        raise ValueError("explicit recipe nationality preimage differs")
    old_code = country_codes.get(native_country)
    if (old_code is None or native_country == "XXX"
            or native_byte_before != old_code):
        raise ValueError("explicit non-XXX native country preimage differs")
    identity = parse_profile_country(body, source, actor_name=actor_source_name,
                                     birth_date=actor_dob)
    after_code = country_codes.get(identity["nationality"])
    if after_code is None or identity["nationality"] == "XXX":
        raise ValueError("source country has no supported native mapping")
    if old_code == after_code:
        raise ValueError("known-wrong nationality source is a no-op")
    return dict(carrier_id=actor["carrier_id"], before=actor,
        nationality=identity["nationality"], field_mask=["nationality"],
        native_mask=dict(file="DBDAT/JUG98030.FDI", record_offset=record_offset,
            file_offset=file_offset, before=native_byte_before, after=after_code),
        source_identity=identity,
        source=dict(path=source["path"], sha256=sha256(body)),
        source_receipt=dict(path=receipt_path, sha256=receipt_sha256),
        expected_owner=expected_owner)


def validate_row(row: dict) -> None:
    """Reject any proposed row outside the exact one-byte nationality mask."""
    allowed = {"carrier_id", "before", "nationality", "field_mask", "native_mask",
        "source_identity", "source", "source_receipt", "expected_owner"}
    mask = row.get("native_mask", {})
    if set(row) != allowed or row.get("field_mask") != ["nationality"]:
        raise ValueError("known-wrong plan is nationality-only and exact-schema")
    if (set(mask) != {"file", "record_offset", "file_offset", "before", "after"}
            or mask.get("file") != "DBDAT/JUG98030.FDI"
            or type(mask.get("record_offset")) is not int
            or type(mask.get("file_offset")) is not int
            or type(mask.get("before")) is not int or type(mask.get("after")) is not int
            or not 0 <= mask["before"] <= 255 or not 0 <= mask["after"] <= 255
            or mask["before"] == mask["after"] or mask["record_offset"] < 0
            or mask["file_offset"] < mask["record_offset"]):
        raise ValueError("exact distinct one-byte known-wrong native mask required")
    if row["before"].get("facts", {}).get("nationality") is None:
        raise ValueError("exact recipe fact preimage required")


def validate_plan(plan: dict) -> None:
    from scripts.season_source_verified_player_changes_v1 import SCHEMA as CHANGE_SCHEMA
    rows = plan.get("updates", [])
    if (plan.get("schema") != CHANGE_SCHEMA or plan.get("kind") != KIND or not rows
            or len({row.get("carrier_id") for row in rows}) != len(rows)):
        raise ValueError("nonempty exact known-wrong country plan with unique actors required")
    offsets = set()
    for row in rows:
        validate_row(row)
        offset = row["native_mask"]["file_offset"]
        if offset in offsets:
            raise ValueError("known-wrong rows cannot write the same native byte twice")
        offsets.add(offset)


def prepare(base, input_path, request=None) -> dict:
    """Prepare a bound plan using the exact registered current release."""
    path = Path(input_path)
    if not path.is_absolute():
        path = registry.ROOT / path
    path = path.resolve()
    if not path.is_relative_to(registry.ROOT.resolve()) or not path.is_file():
        raise ValueError("known-wrong input must be a retained workspace file")
    if request is None:
        request = pipeline.read_json_file(path)
    from scripts.season_source_verified_player_changes_v1 import INPUT_SCHEMA
    if (request.get("schema") != INPUT_SCHEMA or request.get("kind") != KIND
            or request.get("season") != base.season
            or request.get("release_id") != base.release_id or not request.get("changes")):
        raise ValueError("known-wrong country request needs its exact registered parent")
    package = pipeline.read_json_file(base.package_path)
    actors = {p["carrier_id"]: p for p in package["players"]}
    clubs = {c["id"]: c for c in package["clubs"]}
    jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    owners = ownership.native_owners(eq)
    codes = compiler._extract_country_codes_from_textos(base.game_path / "DBDAT/TEXTOS.PKF")
    updates, seen = [], set()
    for selection in request["changes"]:
        carrier = selection.get("carrier_id")
        if (type(carrier) is not int or carrier in seen
                or selection.get("field_mask") != ["nationality"]):
            raise ValueError("unique literal carriers and nationality-only field mask required")
        seen.add(carrier)
        actor = actors[carrier]
        club = clubs[actor["club_id"]]
        original = selection["source"]
        from scripts.season_source_verified_player_changes_v1 import original_path
        body_path = original_path(original["path"])
        body = body_path.read_bytes()
        receipt_path, receipt = profile_receipt(body_path, original)
        if (original.get("sha256") != sha256(body)
                or receipt.get("url") != original.get("url")
                or receipt.get("sha256") != original.get("sha256")):
            raise ValueError("profile body hash, URL receipt, or receipt hash differs")
        entry = entries[carrier]
        raw = entry.decode_payload(jug)
        observed = native_player(raw, carrier)
        end = observed["name_end"]
        native_facts = __import__("scripts.season_within_club_reserve_repair_v1",
            fromlist=["native_facts"]).native_facts
        facts = native_facts(jug, carrier)
        native_label = selection.get("native_before_country")
        native_code = codes.get(native_label)
        byte_offset = entry.payload_offset + end + 8
        expected_owner = club["carrier_id"]
        # Bind request's recipe preimage explicitly, including mode-1 sentinel
        # values; actual native country is checked independently below.
        if selection.get("recipe_before_nationality") != actor["facts"].get("nationality"):
            raise ValueError("explicit recipe nationality preimage differs")
        if native_code is None or native_label == "XXX" or (raw[end + 8] ^ 0x61) != native_code:
            raise ValueError("explicit non-XXX native country preimage differs")
        if (facts["birth_date"] != actor["facts"].get("birth_date")
                or normalise(observed["name"]) != normalise(actor["name"])):
            raise ValueError("actual native identity/DOB differs from recipe actor")
        # Also check source-specified desired code is not already current.
        source_identity = parse_profile_country(body, original,
            actor_name=actor.get("source_name") or actor["name"],
            birth_date=actor["facts"]["birth_date"])
        after_code = compiler._country_code(source_identity["nationality"], codes)
        if after_code == native_code:
            raise ValueError("known-wrong nationality source is a no-op")
        row = prepare_row(season=base.season, club=club, actor=actor, source=original,
            body=body, receipt=receipt,
            receipt_path=registry.relative_workspace_path(receipt_path),
            receipt_sha256=registry.sha256_file(receipt_path),
            native_name=observed["name"],
            native_birth_date=facts["birth_date"], native_country=native_label,
            recipe_before_nationality=selection.get("recipe_before_nationality"),
            owners=owners.get(carrier, set()), expected_owner=expected_owner,
            record_offset=end + 8, file_offset=byte_offset,
            native_byte_before=jug[byte_offset], country_codes={
                **codes, source_identity["nationality"]: after_code})
        row["source_identity"] = source_identity
        validate_row(row)
        updates.append(row)
    result = dict(schema="pm99-explicit-source-backed-player-field-changes-v1",
        season=base.season, release_id=base.release_id, kind=KIND,
        source_input=dict(path=registry.relative_workspace_path(path), sha256=sha256(path.read_bytes())),
        package_sha256=registry.sha256_file(base.package_path), jug_sha256=native.digest(jug),
        eq_sha256=native.digest(eq), textos_sha256=registry.sha256_file(base.game_path / "DBDAT/TEXTOS.PKF"),
        updates=updates,
        scope="Only selected nationality recipe fields and one country byte per actor; no claim about historical club membership; exact exclusive current owner is a native write guard.",
        source_policy="strict-known-wrong-explicit-profile-nationality-v1")
    result["transaction_id"] = native.digest(packages.canonical_json_bytes(result))[:24]
    validate_plan(result)
    return result
