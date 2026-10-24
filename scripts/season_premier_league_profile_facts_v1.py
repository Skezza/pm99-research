"""Read exact official Premier League player JSON facts.

The historical identity gate and native field writer remain separate.
"""
import json
import re
from urllib.parse import urlsplit
from scripts.capture_2015_source_tail_squads_v1 import NATIONALITY_CODES


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Premier League JSON contains an ambiguous repeated property')
        result[key] = value
    return result


def parse_player_json(raw: bytes, *, url: str, provider_player_id: int, full_name: str) -> dict:
    if type(provider_player_id) is not int or provider_player_id <= 0 or not full_name:
        raise ValueError("explicit positive PL player ID and full name required")
    parsed = urlsplit(url)
    expected = f"/api/v1/players/{provider_player_id}"
    if (parsed.scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment) != (
            "https", "sdp-prem-prod.premier-league-prod.pulselive.com", expected, "", ""):
        raise ValueError("Premier League player JSON must use its exact public player endpoint")
    try:
        rows = json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Premier League player body must be original JSON") from exc
    if not isinstance(rows, list) or not rows:
        raise ValueError("Premier League player response must contain career records")
    parsed_rows = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Premier League career record must be an object")
        if any(not isinstance(row.get(key), dict) for key in ('id', 'name', 'dates', 'country')):
            raise ValueError('Premier League identity/fact objects are missing or malformed')
        pid = row.get("id", {}).get("playerId")
        name = row.get("name", {}).get("display")
        birth = row.get("dates", {}).get("birth")
        country = row.get("country", {}).get("country")
        if str(pid) != str(provider_player_id) or name != full_name:
            raise ValueError("Premier League record ID or complete display name differs")
        if not isinstance(birth, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", birth):
            raise ValueError("Premier League birth date must be an exact ISO calendar date")
        from datetime import date
        date.fromisoformat(birth)
        if not isinstance(country, str) or not country.strip():
            raise ValueError("Premier League country literal is missing")
        code = NATIONALITY_CODES.get(country)
        if code is None:
            raise ValueError("Premier League country is not in the existing nationality map")
        parsed_rows.append((name, birth, country, code))
    if len(set(parsed_rows)) != 1:
        raise ValueError("Premier League career rows disagree on identity or biographical facts")
    name, birth, country, code = parsed_rows[0]
    return {"full_name": name, "provider_player_id": provider_player_id,
            "birth_date": birth, "nationality_label": country, "nationality": code,
            "representation": "official-premier-league-sdp-player-json"}
