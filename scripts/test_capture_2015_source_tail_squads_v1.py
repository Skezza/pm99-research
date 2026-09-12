"""Tests for exact search identity in the 2015 source-tail squad capture."""

from scripts.capture_2015_source_tail_squads_v1 import (
    NATIONALITY_CODES,
    SourceTailSquadError,
    _accepted_search_identity,
    _restore_transfermarkt_nationalities,
    _search_request,
    _pinned_transfermarkt_identity,
    _source_saison_id,
    _squad_cache_key,
)


def test_search_accepts_one_exact_target_title() -> None:
    assert _accepted_search_identity(
        target_title="Example FC",
        links=[("Example FC", "/example-fc/startseite/verein/42"), ("Other", "/other/startseite/verein/2")],
    ) == ("Example FC", "/example-fc/startseite/verein/42", "exact-normalised-transfermarkt-search-display-name")


def test_search_rejects_an_ambiguous_exact_target_title() -> None:
    try:
        _accepted_search_identity(
            target_title="Example FC",
            links=[("Example FC", "/one/startseite/verein/1"), ("Example FC", "/two/startseite/verein/2")],
        )
    except SourceTailSquadError as error:
        assert "no-unique" in str(error)
    else:
        raise AssertionError("an ambiguous target must remain a source gap")


def test_search_accepts_only_a_documented_historic_display_alias() -> None:
    assert _accepted_search_identity(
        target_title="Club Bolívar",
        links=[
            ("Bolívar La Paz", "/bolivar-la-paz/startseite/verein/123"),
            ("Bolívar U20", "/bolivar-u20/startseite/verein/456"),
        ],
    ) == (
        "Bolívar La Paz",
        "/bolivar-la-paz/startseite/verein/123",
        "documented-historical-transfermarkt-search-alias",
    )


def test_reviewed_query_uses_a_distinct_immutable_cache_key() -> None:
    url, cache_key, query = _search_request(
        carrier_id=1403, target_title="FC Astra Giurgiu",
    )
    assert query == "Astra Giurgiu"
    assert "query=Astra+Giurgiu" in url
    assert cache_key.startswith("search/2015/1403-query-")


def test_pinned_historic_identity_is_a_specific_club_not_a_name_search() -> None:
    assert _pinned_transfermarkt_identity("NK Inter Zaprešić") == {
        "club_id": 918,
        "display_name": "NK Inker",
        "evidence_url": "https://www.transfermarkt.com/nk-inker/spielplan/verein/918/saison_id/2015/plus/1",
        "slug": "nk-inker",
    }


def test_published_transfermarkt_country_label_repairs_a_parser_map_gap() -> None:
    payload = b'''<table class="items"><tr><td>-</td><td><a href="/uros/profil/spieler/1">Uros Djeric</a>
    Centre-Forward</td><td></td><td><img title="Bosnia-Herzegovina"/></td></tr></table>'''
    players = [{
        "name": "Uros Djeric", "nationality": "UNK", "position": "F",
        "unresolved_fields": ["birth_date", "nationality_code"],
    }]
    assert _restore_transfermarkt_nationalities(payload, players) == [{
        "name": "Uros Djeric", "nationality": "BIH", "position": "F",
        "unresolved_fields": ["birth_date"],
    }]


def test_opening_profile_country_labels_use_the_same_declared_source_map() -> None:
    assert {label: NATIONALITY_CODES[label] for label in ("Cape Verde", "Chad", "Curacao", "Djibouti")} == {
        "Cape Verde": "CPV", "Chad": "CHA", "Curacao": "CUR", "Djibouti": "DJI",
    }


def test_calendar_league_uses_the_source_selector_that_is_labelled_2015() -> None:
    assert _source_saison_id({"family": "bolivia"}) == 2014
    assert _source_saison_id({"family": "finland"}) == 2014
    assert _source_saison_id({"family": "croatia"}) == 2015
    assert _squad_cache_key(carrier_id=2601, club_id=6878, source_saison_id=2014) == (
        "squad/2015/2601-6878-selector-2014.html"
    )


def test_new_dom_parser_uses_published_long_tail_nationality_labels() -> None:
    assert {label: NATIONALITY_CODES[label] for label in (
        "Antigua and Barbuda", "Barbados", "Equatorial Guinea", "Gibraltar",
        "Montserrat", "St. Kitts & Nevis", "Trinidad and Tobago", "Vietnam",
    )} == {
        "Antigua and Barbuda": "ATG", "Barbados": "BRB", "Equatorial Guinea": "EQG",
        "Gibraltar": "GIB", "Montserrat": "MSR", "St. Kitts & Nevis": "SKN",
        "Trinidad and Tobago": "TRI", "Vietnam": "VIE",
    }
