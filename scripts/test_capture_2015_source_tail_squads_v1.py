"""Tests for exact search identity in the 2015 source-tail squad capture."""

from scripts.capture_2015_source_tail_squads_v1 import (
    SourceTailSquadError,
    _accepted_search_identity,
    _search_request,
    _pinned_transfermarkt_identity,
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
