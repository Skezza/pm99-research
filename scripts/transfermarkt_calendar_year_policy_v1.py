"""Fail-closed season-year routing backed by the retained calendar audit.

The retained audit covers 25 source years (2000-2014 and 2016-2025): all
931 Brazil, Ireland, Norway, and Sweden rows have their first fixture in
source-year + 1. For those four explicitly mapped competitions, target-year -
1 is therefore a candidate provider-season request, not acceptance evidence.
Every result must pass an actual target-year fixture-date check and a title
check on both schedule and squad source pages. Missing or mismatched evidence
becomes a gap. Split-season leagues retain provider_season_id == target_year.
Russia <= 2010 is quarantined only.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
import re
from bs4 import BeautifulSoup

AUDIT_RELATIVE_PATH = Path("data/transfermarkt-calendar-year-routing-evidence-v1.json")
AUDIT_SHA256 = "8a1bf8a1958528458e86e7b0708a54a992604e8f50946933e13c5442a03b1494"
POLICY_SCHEMA = "pm99-transfermarkt-calendar-provider-year-policy-v1"
CALENDAR_CODE_COUNTRY = {
    "BRA1": "brazil",
    "IR1": "ireland",
    "NO1": "norway",
    "SE1": "sweden",
}
AUDIT_CALENDAR_COUNTRIES = ("brazil", "ireland", "norway", "sweden")


class RoutingError(ValueError):
    """No reviewed provider-year route exists for this target and competition."""


@dataclass(frozen=True)
class YearRoute:
    target_year: int
    provider_season_id: int
    source_competition_code: str
    country_catalog: str | None
    policy: str

    def document(self) -> dict[str, object]:
        return {
            "schema": POLICY_SCHEMA,
            "target_calendar_year": self.target_year,
            "provider_season_id": self.provider_season_id,
            "source_competition_code": self.source_competition_code,
            "country_catalog": self.country_catalog,
            "policy": self.policy,
            "audit_path": AUDIT_RELATIVE_PATH.as_posix(),
            "audit_sha256": AUDIT_SHA256,
        }


def verify_audit(repo_root: Path) -> dict[str, str]:
    path = repo_root / AUDIT_RELATIVE_PATH
    try:
        raw = path.read_bytes()
        doc = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RoutingError(f"calendar routing audit is unavailable: {path}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if digest != AUDIT_SHA256 or doc.get("schema_version") != "pm99-calendar-league-year-routing-audit-v3":
        raise RoutingError("calendar routing audit v3 hash or schema differs")
    audited_rows = 0
    for season in doc.get("season_rows", []):
        start_year = season.get("start_year")
        counts = season.get("counts")
        fixture_years = season.get("fixture_years")
        if type(start_year) is not int or not isinstance(counts, dict) or not isinstance(fixture_years, dict):
            raise RoutingError("calendar audit season row is malformed")
        for country in AUDIT_CALENDAR_COUNTRIES:
            count = counts.get(country)
            years = fixture_years.get(country)
            if type(count) is not int or count <= 0 or years != {str(start_year + 1): count}:
                raise RoutingError(
                    f"calendar audit does not prove one next-calendar-year fixture bucket for {country}/{start_year}"
                )
            audited_rows += count
    if audited_rows != 931:
        raise RoutingError("calendar audit coverage differs from the reviewed 931-row source count")
    return {"path": AUDIT_RELATIVE_PATH.as_posix(), "sha256": digest}


def route_provider_year(target_year: int, code: str, country: str | None = None) -> YearRoute:
    if type(target_year) is not int or target_year < 1900:
        raise RoutingError("target calendar year must be an integer >= 1900")
    if code == "RU1" and target_year <= 2010:
        raise RoutingError("RU1 target year <= 2010 is quarantined pending reviewed transition-year policy")
    expected_country = CALENDAR_CODE_COUNTRY.get(code)
    if expected_country is not None:
        if country != expected_country:
            raise RoutingError(f"{code} is audited only for country_catalog={expected_country}")
        return YearRoute(target_year, target_year - 1, code, expected_country,
                         "candidate-calendar-year-provider-offset-minus-one; request only; runtime title/date evidence required")
    return YearRoute(target_year, target_year, code, country,
                     "split-season-or-unreviewed-noncalendar-source-id-equals-target")


def cache_key(*, kind: str, target_year: int, provider_year: int, code: str,
              club_id: int | None = None) -> str:
    tail = f"/{club_id}" if club_id is not None else ""
    if target_year == provider_year:
        if kind == "competition":
            return f"competition-v2/{provider_year}/{code}.html"
        if kind == "schedule":
            return f"schedule/{provider_year}/{club_id}.html"
        if kind == "report":
            return f"report/{club_id}.html"
        if kind == "squad":
            return f"squad/{provider_year}/{code}/{club_id}.html"
        raise ValueError(f"unknown cache kind {kind}")
    if kind == "competition":
        return f"competition-calendar-route-v1/{target_year}/{provider_year}/{code}.html"
    if kind == "schedule":
        return f"schedule-calendar-route-v1/{target_year}/{provider_year}/{club_id}.html"
    if kind == "report":
        return f"report-calendar-route-v1/{target_year}/{provider_year}/{club_id}.html"
    if kind == "squad":
        return f"squad-calendar-route-v1/{target_year}/{provider_year}/{code}/{club_id}.html"
    raise ValueError(f"unknown cache kind {kind}")


def _title_text(payload: bytes) -> str:
    soup = BeautifulSoup(payload, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    headings = " ".join(node.get_text(" ", strip=True) for node in soup.select("h1"))
    return " ".join(f"{title} {headings}".split())


def title_matches_source_season(payload: bytes, *, provider_year: int, target_year: int) -> tuple[bool, str]:
    """Require an actual captured page title that names the selected source season.

    Titles are accepted as the provider season pair (YYYY/YY, YY/YY,
    YYYY-YYYY) or as the exact target calendar year (for example,
    "Detailed squad 2017"). No title is synthesized from the URL or request
    arguments.
    """
    title = _title_text(payload)
    if not title:
        return False, ""
    text = title.replace("–", "/").replace("—", "/")
    text = re.sub(r"\s*[-/]\s*", "/", text)
    short_start = provider_year % 100
    short_end = (provider_year + 1) % 100
    patterns = [
        rf"(?<!\d){provider_year}/{provider_year + 1}(?!\d)",
        rf"(?<!\d){provider_year}/{short_end:02d}(?!\d)",
        rf"(?<!\d){short_start:02d}/{short_end:02d}(?!\d)",
    ]
    matched = any(re.search(pattern, text) for pattern in patterns)
    if re.search(rf"(?<![\d/\-]){target_year}(?![\d/\-])", text):
        matched = True
    return matched, title


def require_source_title(payload: bytes, *, provider_year: int, target_year: int, label: str) -> str:
    matches, title = title_matches_source_season(payload, provider_year=provider_year, target_year=target_year)
    if not matches:
        raise RoutingError(
            f"{label} title does not identify provider season {provider_year}/{provider_year + 1} "
            f"for target year {target_year}: {title!r}"
        )
    return title
