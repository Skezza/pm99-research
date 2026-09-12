from __future__ import annotations

import hashlib

from scripts import capture_2015_world_manager_history_v2 as capture


def _page(title: str, content: str, *, redirected_from: str | None = None) -> dict[str, object]:
    result = {
        "title": title,
        "pageid": 7,
        "revid": 11,
        "timestamp": "2015-08-29T08:00:00Z",
        "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "content": content,
    }
    if redirected_from is not None:
        result["redirected_from"] = redirected_from
    return result


def _package() -> dict[str, object]:
    return {
        "schema_version": "pm99-season-package-v2",
        "clubs": [
            {"carrier_id": 4, "name": "Example FC", "manager_id": "manager-4"},
            {"carrier_id": 9999, "name": "Stars", "manager_id": "manager-9999"},
        ],
        "managers": [
            {"id": "manager-4", "policy": "preserve-existing-mode1"},
            {"id": "manager-9999", "policy": "preserve-existing-mode1"},
        ],
    }


def test_captures_a_dated_manager_through_a_redirected_title() -> None:
    content = """{{Infobox football club
| clubname = Example FC
| manager = {{flagicon|ENG}} [[Jane Manager|Jane Manager]]
}}"""

    receipt = capture.build(
        _package(),
        fetch_page=lambda title, _as_of: _page("Example Football Club", content)
        if title == "Example FC" else None,
        search_titles=lambda _name: [],
        jobs=1,
    )

    row = receipt["rows"][0]
    assert row["status"] == "dated-historical-club-page-manager-match"
    assert row["identity_method"] == "exact-historical-infobox-club-label"
    assert row["facts"]["manager"] == "Jane Manager"
    assert receipt["rows"][1]["status"] == "out-of-scope-non-club-carrier"


def test_rejects_an_unrelated_search_result_even_when_it_names_a_manager() -> None:
    content = """{{Infobox football club
| clubname = Different Club
| manager = [[Wrong Manager]]
}}"""

    receipt = capture.build(
        _package(),
        fetch_page=lambda _title, _as_of: _page("Different Club", content),
        search_titles=lambda _name: ["Different Club"],
        jobs=1,
    )

    assert receipt["coverage"]["dated_manager_match_count"] == 0
    assert receipt["rows"][0]["status"] == "requires-review-no-dated-historical-manager-match"


def test_accepts_only_a_publisher_declared_redirect_for_a_renamed_club_page() -> None:
    content = """{{Infobox football club
| manager = [[Jane Manager]]
}}"""

    receipt = capture.build(
        _package(),
        fetch_page=lambda title, _as_of: _page(
            "Example Football Club", content, redirected_from="Example FC"
        ) if title == "Example FC" else None,
        search_titles=lambda _name: [],
        jobs=1,
    )

    assert receipt["rows"][0]["identity_method"] == "declared-title-wikipedia-redirect"
    assert receipt["rows"][0]["facts"]["manager"] == "Jane Manager"
