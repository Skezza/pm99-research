"""Tests for strict 2015 Transfermarkt manager-search identity decisions."""

from scripts import capture_2015_world_manager_transfermarkt_exact_search_v6 as subject


def test_exact_search_identity_accepts_only_one_declared_name() -> None:
    name, href, method = subject._accepted_search_identity(
        "Example Town",
        [("Example Town", "/example-town/startseite/verein/42"), ("Other Town", "/other/startseite/verein/43")],
    )
    assert (name, href, method) == (
        "Example Town", "/example-town/startseite/verein/42",
        "exact-normalised-transfermarkt-search-display-name",
    )


def test_exact_search_identity_rejects_two_matching_clubs() -> None:
    try:
        subject._accepted_search_identity(
            "Example Town",
            [("Example Town", "/one/startseite/verein/42"), ("Example Town", "/two/startseite/verein/43")],
        )
    except subject.ExactSearchManagerError as error:
        assert "no-unique" in str(error)
    else:
        raise AssertionError("expected ambiguous exact search result to be rejected")


def test_exact_search_identity_accepts_a_documented_historical_alias() -> None:
    name, href, method = subject._accepted_search_identity(
        "Rosenborg", [("Rosenborg BK", "/rosenborg-bk/startseite/verein/195")],
    )
    assert (name, href, method) == (
        "Rosenborg BK", "/rosenborg-bk/startseite/verein/195",
        "documented-historical-transfermarkt-search-alias",
    )


def test_documented_latin_spelling_keeps_the_published_name_traceable() -> None:
    assert subject._pm99_manager_name(1704, "Balázs Bekő") == (
        "Balazs Beko", "documented-pm99-latin-spelling-for-published-transfermarkt-name",
    )
