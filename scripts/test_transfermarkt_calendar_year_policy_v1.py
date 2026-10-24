from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
for path in (ROOT / "scripts", HERE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts import capture_transfermarkt_opening_lineups_v1 as opening
from scripts import capture_transfermarkt_historical_squads_v1 as squads
from scripts import capture_allocated_opening_lineups_v1 as allocated
from scripts import plan_transfermarkt_opening_lineups_batch_v1 as planner
from scripts import transfermarkt_calendar_year_policy_v1 as policy


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def test_route_table_is_exact_and_split_season_is_unchanged() -> None:
    for code, country in policy.CALENDAR_CODE_COUNTRY.items():
        assert policy.route_provider_year(2017, code, country).provider_season_id == 2016
        assert policy.route_provider_year(2018, code, country).provider_season_id == 2017
    assert policy.route_provider_year(2017, "RU1", "russia").provider_season_id == 2017
    assert policy.route_provider_year(2017, "L1", "ger").provider_season_id == 2017
    # The audit informs candidate routing, but observed-year whitelist does
    # not gate a fresh request. Runtime title and fixture checks decide whether
    # the candidate source is accepted.
    for target_year in (1990, 2000, 2001, 2015, 2016, 2017, 2026, 2027):
        assert policy.route_provider_year(target_year, "BRA1", "brazil").provider_season_id == target_year - 1
    with pytest.raises(policy.RoutingError, match="country_catalog"):
        policy.route_provider_year(2017, "BRA1", "arg")
    with pytest.raises(policy.RoutingError, match="country_catalog"):
        policy.route_provider_year(2017, "BRA1")
    with pytest.raises(policy.RoutingError, match="quarantined"):
        policy.route_provider_year(2010, "RU1", "russia")


def test_route_cache_keys_are_versioned_without_replacing_legacy_keys() -> None:
    assert policy.cache_key(kind="schedule", target_year=2017, provider_year=2016,
                            code="NO1", club_id=2761) == "schedule-calendar-route-v1/2017/2016/2761.html"
    assert policy.cache_key(kind="squad", target_year=2017, provider_year=2016,
                            code="NO1", club_id=2761) == "squad-calendar-route-v1/2017/2016/NO1/2761.html"
    assert policy.cache_key(kind="schedule", target_year=2017, provider_year=2017,
                            code="RU1", club_id=123) == "schedule/2017/123.html"


def test_routed_fixture_uses_provider_url_but_actual_target_year_date() -> None:
    ref = opening.TeamRef("Haugesund", "Haugesund", 2761,
                          "/haugesund/startseite/verein/2761", "retained-paired-audit")
    html = b'''<html><head><title>Schedule 16/17 | Transfermarkt</title></head><body><table>
      <tr><td>11/03/2018</td><td><a href="/x/test/spieltag/wettbewerb/NO1">League</a></td>
        <td><a href="/x/spielbericht/index/spielbericht/2985000">Later</a></td></tr>
      <tr><td>11/03/2017</td><td><a href="/x/test/spieltag/wettbewerb/NO1">League</a></td>
        <td><a href="/x/spielbericht/index/spielbericht/2808982">Target</a></td></tr>
    </table></body></html>'''

    class Cache:
        url = ""
        key = ""

        def get(self, url: str, key: str) -> bytes:
            self.url, self.key = url, key
            return html

    cache = Cache()
    result = opening._first_fixture(ref, season_start_year=2017, competition_code="NO1",
                                    country_catalog="norway", cache=cache)
    assert "/saison_id/2016" in cache.url
    assert cache.key == "schedule-calendar-route-v1/2017/2016/2761.html"
    assert result["date"] == "2017-03-11"
    assert result["match_id"] == "2808982"
    assert result["provider_season_id"] == 2016
    assert result["target_calendar_year"] == 2017


def test_routed_fixture_fails_closed_for_wrong_title_or_no_target_year_match() -> None:
    ref = opening.TeamRef("Bohemians", "Bohemians", 9211,
                          "/bohemians/startseite/verein/9211", "retained-paired-audit")

    class Cache:
        payload = b""

        def get(self, _url: str, _key: str) -> bytes:
            return self.payload

    cache = Cache()
    row = (b'<table><tr><td>24/02/2018</td><td><a href="/test/spieltag/wettbewerb/IR1">L</a></td>'
           b'<td><a href="/x/spielbericht/index/spielbericht/2818095">R</a></td></tr></table>')
    cache.payload = b"<title>Schedule 16/17</title>" + row
    with pytest.raises(opening.CaptureError, match="no actual fixture in target calendar year"):
        opening._first_fixture(ref, season_start_year=2017, competition_code="IR1",
                               country_catalog="ireland", cache=cache)
    cache.payload = b"<title>Schedule 18/19</title>" + row.replace(b"24/02/2018", b"24/02/2017")
    with pytest.raises(opening.CaptureError, match="title does not identify provider season"):
        opening._first_fixture(ref, season_start_year=2017, competition_code="IR1",
                               country_catalog="ireland", cache=cache)


def test_fresh_candidate_route_cannot_accept_wrong_season_or_fixture_year() -> None:
    ref = opening.TeamRef("Molde", "Molde FK", 687, "/molde/startseite/verein/687", "candidate-request")

    class Cache:
        payload = b""

        def get(self, url: str, key: str) -> bytes:
            assert "/saison_id/2029" in url
            assert key == "schedule-calendar-route-v1/2030/2029/687.html"
            return self.payload

    row = (b'<table><tr><td>10/03/2031</td><td><a href="/test/spieltag/wettbewerb/NO1">L</a></td>'
           b'<td><a href="/x/spielbericht/index/spielbericht/9001">R</a></td></tr></table>')
    cache = Cache()
    cache.payload = b"<title>Molde FK - Schedule 29/30</title>" + row
    with pytest.raises(opening.CaptureError, match="no actual fixture in target calendar year"):
        opening._first_fixture(ref, season_start_year=2030, competition_code="NO1",
                               country_catalog="norway", cache=cache)
    cache.payload = (b"<title>Molde FK - Schedule 30/31</title>" +
                     row.replace(b"10/03/2031", b"10/03/2030"))
    with pytest.raises(opening.CaptureError, match="title does not identify provider season"):
        opening._first_fixture(ref, season_start_year=2030, competition_code="NO1",
                               country_catalog="norway", cache=cache)


def test_squad_title_guard_checks_real_page_heading() -> None:
    assert policy.require_source_title(b"<title>Squad 2016/17</title>", provider_year=2016,
                                       target_year=2017, label="squad") == "Squad 2016/17"
    with pytest.raises(policy.RoutingError, match="title does not identify"):
        policy.require_source_title(b"<title>Squad 2017/18</title>", provider_year=2016,
                                    target_year=2017, label="squad")
    with pytest.raises(policy.RoutingError, match="title does not identify"):
        policy.require_source_title(b"<html><body>players</body></html>", provider_year=2016,
                                    target_year=2017, label="squad")
    assert policy.require_source_title(
        b"<title>Molde FK - Detailed squad 2017 | Transfermarkt</title>",
        provider_year=2016, target_year=2017, label="squad",
    ) == "Molde FK - Detailed squad 2017 | Transfermarkt"
    with pytest.raises(policy.RoutingError, match="title does not identify"):
        policy.require_source_title(
            b"<title>Molde FK - Detailed squad 2018 | Transfermarkt</title>",
            provider_year=2016, target_year=2017, label="squad",
        )


def test_retained_2016_provider_schedule_body_proves_target_2017_fixture() -> None:
    path = ROOT / ".local/transfermarkt-opening-plans-current-v1/2016-17/cache/schedule/2016/537.html"
    payload = path.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == (
        "4b57067c089466ed3ed520881c335c92cf444407e8c38a17533b3f6d0ab96550"
    )
    ref = opening.TeamRef("Botafogo", "Botafogo de Futebol e Regatas", 537,
                          "/botafogo/startseite/verein/537", "retained-audit-v3-body")

    class Cache:
        def get(self, url: str, key: str) -> bytes:
            assert "/saison_id/2016" in url
            assert key == "schedule-calendar-route-v1/2017/2016/537.html"
            return payload

    fixture = opening._first_fixture(ref, season_start_year=2017, competition_code="BRA1",
                                    country_catalog="brazil", cache=Cache())
    assert fixture["date"] == "2017-05-14"
    assert fixture["match_id"] == "2846995"


def test_allocated_reader_accepts_only_exact_calendar_route_path_and_metadata() -> None:
    route = policy.route_provider_year(2017, "NO1", "norway").document()
    source = {
        "source_path": "squad-calendar-route-v1/2017/2016/NO1/2761.html",
        "country_catalog": "norway", "competition_catalog": "tippe", "club_name": "Haugesund",
        "calendar_year_routing": route,
    }
    code, ref = allocated._identity(source, season_start_year=2017)
    assert code == "NO1" and ref.club_id == 2761
    legacy = {**source, "source_path": "squad/2017/NO1/2761.html"}
    legacy.pop("calendar_year_routing")
    assert allocated._identity(legacy, season_start_year=2017)[0] == "NO1"
    wrong = {**source, "source_path": "squad-calendar-route-v1/2017/2015/NO1/2761.html"}
    with pytest.raises(allocated.AllocatedLineupError, match="do not match reviewed"):
        allocated._identity(wrong, season_start_year=2017)
    wrong_country = {**source, "country_catalog": "sweden"}
    with pytest.raises(allocated.AllocatedLineupError, match="no reviewed route"):
        allocated._identity(wrong_country, season_start_year=2017)


def test_historical_squad_capture_binds_provider_url_title_and_route_cache(monkeypatch) -> None:
    team = opening.TeamRef("Botafogo", "Botafogo", 537, "/botafogo/startseite/verein/537", "audit-pair")
    monkeypatch.setattr(squads, "_competition_teams", lambda **_kwargs: [team])

    class Cache:
        used = {}
        payload = b"<title>Botafogo - Detailed squad 2017</title>"
        requested = None

        def get(self, url: str, key: str) -> bytes:
            self.requested = (url, key)
            self.used[key] = {"cache_path": key, "sha256": "a" * 64, "url": url}
            return self.payload

    scope = [{"competition_catalog": "campeon", "competition_name": "Serie A",
              "country_catalog": "brazil", "source_competition_code": "BRA1"}]
    parsed = lambda _payload: [{"name": "Player One", "position": "G", "nationality": "ENG",
                                "shirt_number": 1, "height_cm": 180, "weight_kg": 75,
                                "birth_date": "1990-01-01"}]
    cache = Cache()
    capture, gaps = squads.build_capture(season_start_year=2017, scope=scope,
        scope_sha256="b" * 64, cache=cache, parse=parsed)
    assert not gaps["gaps"]
    club = capture["clubs"][0]
    assert "/saison_id/2016" in cache.requested[0]
    assert cache.requested[1] == "squad-calendar-route-v1/2017/2016/BRA1/537.html"
    assert club["source_path"] == cache.requested[1]
    assert club["calendar_year_routing"]["audit_sha256"] == policy.AUDIT_SHA256

    cache = Cache()
    cache.payload = b"<title>Botafogo - Detailed squad 2018</title>"
    capture, gaps = squads.build_capture(season_start_year=2017, scope=scope,
        scope_sha256="b" * 64, cache=cache, parse=parsed)
    assert not capture["clubs"]
    assert gaps["gaps"][0]["reason"] == "squad-source-season-title-mismatch"


def test_planner_routes_reviewed_pairs_and_quarantines_unsupported_years(tmp_path: Path) -> None:
    source = tmp_path / "2017-18" / "source-intake.json"
    source.parent.mkdir()
    source.write_bytes(_canonical({"source_clubs": [
        {"selector": {"club_name": "Botafogo", "competition_catalog": "campeon", "country_catalog": "brazil"}},
        {"selector": {"club_name": "Bohemians", "competition_catalog": "prem", "country_catalog": "ireland"}},
        {"selector": {"club_name": "Haugesund", "competition_catalog": "tippe", "country_catalog": "norway"}},
        {"selector": {"club_name": "Djurgarden", "competition_catalog": "allsven", "country_catalog": "sweden"}},
        {"selector": {"club_name": "Bayern", "competition_catalog": "bundes", "country_catalog": "ger"}},
        {"selector": {"club_name": "Zenit", "competition_catalog": "rfpl", "country_catalog": "russia"}},
    ]}))
    plan = planner.plan_season(source_intake=source, output_directory=tmp_path / "out",
                               repo_root=ROOT, season_id="2017-18")
    assert plan["summary"]["supported_club_count"] == 6
    assert plan["summary"]["calendar_quarantined_club_count"] == 0
    routes = plan["calendar_year_routing"]["routed_competitions"]
    assert len(routes) == 4 and {row["provider_season_id"] for row in routes} == {2016}
    assert {row["source_competition_code"] for row in routes} == {"BRA1", "IR1", "NO1", "SE1"}
    assert "scripts/capture_transfermarkt_opening_lineups_v1.py" in plan["capture"]["argv"]

    old = planner.plan_season(source_intake=source, output_directory=tmp_path / "old",
                              repo_root=ROOT, season_id="2010-11")
    assert old["summary"]["calendar_quarantined_club_count"] == 1
    assert old["summary"]["supported_club_count"] == 5
    assert {row["source_competition_code"] for row in old["supported_competitions"]} == {
        "BRA1", "IR1", "NO1", "SE1", "L1",
    }
    assert old["calendar_year_routing"]["quarantined_competitions"][0]["source_competition_code"] == "RU1"



def test_allocated_capture_propagates_routed_fixture_and_audit(monkeypatch) -> None:
    raw_path = ROOT / ".local/transfermarkt-opening-plans-current-v1/2016-17/cache/schedule/2016/537.html"
    if not raw_path.is_file():
        pytest.skip("Retained raw schedule is optional; synthetic route cases run without local caches")
    payload = raw_path.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == (
        "4b57067c089466ed3ed520881c335c92cf444407e8c38a17533b3f6d0ab96550"
    )
    route = policy.route_provider_year(2017, "BRA1", "brazil").document()
    selector = {"country_catalog": "brazil", "competition_catalog": "campeon",
                "club_name": "Botafogo de Futebol e Regatas"}
    source_capture = {"clubs": [{
        "source_selector": selector,
        "source_path": "squad-calendar-route-v1/2017/2016/BRA1/537.html",
        "calendar_year_routing": route,
    }]}

    class Cache:
        used = {}
        requested = []

        def get(self, url: str, key: str) -> bytes:
            self.requested.append((url, key))
            self.used[key] = {"cache_path": key, "sha256": hashlib.sha256(payload).hexdigest(), "url": url}
            if "/spielplan/" in url:
                return payload
            raise AssertionError(f"unexpected uncached resource requested: {url}")

    seen_fixture = {}

    def fake_lineup(ref, fixture, _cache):
        seen_fixture.update(fixture)
        return {"source_selector": {"club_name": ref.source_club_name,
                                    "transfermarkt_club_id": ref.club_id}}

    monkeypatch.setattr(opening, "_lineup_from_report", fake_lineup)
    result = allocated.capture(
        source_capture=source_capture, source_capture_sha256="bound-source-capture-sha",
        allocation={"schema_version": allocated.ALLOCATION_SCHEMA,
                    "season": {"start_year": 2017},
                    "assignments": [{"club_name": selector["club_name"],
                                     "source_selector": {"country_catalog": "brazil",
                                                         "competition_catalog": "campeon"},
                                     "carrier_id": 537}]},
        allocation_sha256="allocation-sha",
        known_reconciliation={"schema_version": "pm99-transfermarkt-opening-lineup-reconciliation-v1",
                              "sources": {"source_capture_sha256": "bound-source-capture-sha"},
                              "clubs": []},
        known_reconciliation_sha256="known-sha", cache=Cache(),
    )

    assert result["summary"]["captured_club_count"] == 1
    assert not result["failures"]
    assert seen_fixture["date"] == "2017-05-14"
    assert seen_fixture["match_id"] == "2846995"
    assert seen_fixture["provider_season_id"] == 2016
    assert "/saison_id/2016" in seen_fixture["schedule_url"]
    row = result["clubs"][0]
    assert row["calendar_year_routing"] == route
    assert row["provider_season_id"] == 2016
    assert row["target_calendar_year"] == 2017
    assert result["source"]["calendar_year_routing_audit"] == {
        "path": policy.AUDIT_RELATIVE_PATH.as_posix(), "sha256": policy.AUDIT_SHA256,
    }
