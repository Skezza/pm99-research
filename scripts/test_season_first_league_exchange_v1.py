"""Source-bound tests for the narrow first-league-fixture bench exception.

Production implementation is owned by the lead in
season_opening_identity_exchange_v1.verify_first_league_fixture(). These tests
pin the exception to the retained 2000/01 Celtic league opener, rather than a
generic non-August friendly.
"""
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import season_opening_identity_exchange_v1 as subject


ROOT = Path(__file__).resolve().parents[1]
BASE = {
    "membership_mode": "original-published-first-league-fixture-bench",
    "first_league_capture": {
        "path": ".local/transfermarkt-opening-plans-current-v1/2000-01/opening-lineups-transfermarkt.json",
        "sha256": "6d31885239632a200a81638f788c83ffecd48dbdbbec595a56399d4a3706414a",
    },
    "schedule_source": {
        "path": ".local/transfermarkt-opening-plans-current-v1/2000-01/cache/schedule/2000/371.html",
        "sha256": "42d50389f3b1e2a0841a59be7a60626fdb79ef2fc8399607387a62f6a1dff705",
        "url": "https://www.transfermarkt.co.uk/celtic-glasgow/spielplan/verein/371/saison_id/2000",
    },
    "competition": "SC1",
    "season_start_year": 2000,
    "provider_club_id": 371,
    "date": "2000-07-30",
    "url": "https://www.transfermarkt.co.uk/spielbericht/index/spielbericht/3838377",
    "path": ".local/transfermarkt-opening-plans-current-v1/2000-01/cache/report/3838377.html",
    "sha256": "72bce1b59b64b0cd988581d3b9169c06ac440fcdaa69b5fbd053ab8818598354",
}


@pytest.fixture
def fixture():
    for value in (BASE["first_league_capture"], BASE["schedule_source"], BASE):
        assert (ROOT / value["path"]).is_file(), f"retained source missing: {value['path']}"
    return deepcopy(BASE)


def test_real_celtic_first_league_fixture_is_valid(fixture):
    # The retained lineup capture binds Celtic to match 3838377 on July 30;
    # schedule round 1 binds it as the first league match, and the report
    # supplies the actual published bench used by new_person().
    subject.verify_first_league_fixture(fixture)


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider_club_id", 1519),
        ("date", "2000-08-06"),
        ("url", "https://www.transfermarkt.co.uk/spielbericht/index/spielbericht/3838376"),
        ("competition", "SC2"),
        ("season_start_year", 2001),
        ("membership_mode", None),
    ],
)
def test_first_league_fixture_rejects_mismatched_claims(fixture, field, value):
    if value is None:
        fixture.pop(field)
    else:
        fixture[field] = value
    with pytest.raises(ValueError):
        subject.verify_first_league_fixture(fixture)


@pytest.mark.parametrize("source_key", ["first_league_capture", "schedule_source", "report"])
def test_first_league_fixture_rejects_changed_source_hash(fixture, source_key):
    item = fixture[source_key] if source_key != "report" else fixture
    item["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source changed"):
        subject.verify_first_league_fixture(fixture)


def test_first_league_fixture_does_not_accept_an_unmarked_non_august_fixture(fixture):
    fixture["membership_mode"] = "published-bench"
    with pytest.raises(ValueError):
        subject.verify_first_league_fixture(fixture)


LENNON_TRANSFER = {
    "path": ".local/external-sources/historical-detailed-roles-v1/2000-01/squad/2000/scots/371.html",
    "sha256": "9dabe8b244a5a866ca2a95287b2214d716bdd392216117276630d57068b007f1",
    "url": "https://www.transfermarkt.com/club/kader/verein/371/saison_id/2000/plus/1",
    "anchors": ["Neil Lennon", "08/12/2000"],
    "date_anchor": "08/12/2000",
    "event_date": "2000-12-08",
    "person_row": {
        "provider_player_id": 9498,
        "date_column": "Joined",
        "date_literal": "08/12/2000",
        "from_club_id": 1003,
    },
}


def test_dated_joined_claim_binds_lennon_and_leicester_in_same_source_row():
    subject.dated_source(deepcopy(LENNON_TRANSFER))


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider_player_id", 9499),
        ("date_column", "Date of birth/Age"),
        ("date_literal", "09/12/2000"),
        ("from_club_id", 1004),
    ],
)
def test_dated_joined_claim_rejects_wrong_same_row_facts(field, value):
    source = deepcopy(LENNON_TRANSFER)
    source["person_row"][field] = value
    with pytest.raises(ValueError):
        subject.dated_source(source)


@pytest.mark.parametrize("wrong_club", [123])
def test_dated_joined_claim_does_not_confuse_current_club_with_signed_from(wrong_club):
    source = deepcopy(LENNON_TRANSFER)
    # Lennon's row has a current-club link to Retired (123), but Leicester
    # (1003) is the club linked in the Signed from column.
    source["person_row"]["from_club_id"] = wrong_club
    with pytest.raises(ValueError, match="Joined/from-club"):
        subject.dated_source(source)


@pytest.fixture
def celtic_club_report(tmp_path, monkeypatch):
    path = tmp_path / "clubs.html"
    path.write_text('''<a href="/celtic-fc/startseite/verein/371" title="Celtic FC">Celtic</a>
        <a href="/rangers-fc/startseite/verein/273" title="Rangers FC">Rangers</a>''')
    monkeypatch.setattr(subject, "original", lambda _value: path)
    return path


def test_match_club_accepts_structural_fc_alias_for_exact_celtic_id(celtic_club_report):
    subject.verify_match_club({"provider_club_id": 371}, "Celtic")


def test_match_club_rejects_celtic_united_as_substring_false_positive(celtic_club_report):
    with pytest.raises(ValueError, match="destination native club"):
        subject.verify_match_club({"provider_club_id": 371}, "Celtic United")


def test_opponent_id_273_is_not_accepted_as_celtic(celtic_club_report):
    with pytest.raises(ValueError, match="destination native club"):
        subject.verify_match_club({"provider_club_id": 273}, "Celtic")


BURCHILL_PROFILE = {
    "path": ".local/consolidated-audit-20261009/Celtic2000-opening-review-v1/source/burchill-profile-25204.html",
    "sha256": "9ce92ea84fe4d9fe7e0be48ca3c3aeaa7b859b810f8c05706bca94f2860dede3",
    "url": "https://www.transfermarkt.co.uk/mark-burchill/profil/spieler/25204",
}


def test_published_family_display_accepts_exact_burchill_profile_heading():
    selection = {"profile": "profile", "provider_player_id": 25204, "name": "Mark Burchill",
                 "birth_date": "1980-08-18", "native_display_name": "Burchill"}
    assert subject.published_profile_family_display(selection, {"profile": BURCHILL_PROFILE}) == "Burchill"


@pytest.mark.parametrize("family", ["Burch", "Burchill Jr"])
def test_published_family_display_rejects_wrong_or_truncated_family(family):
    selection = {"profile": "profile", "provider_player_id": 25204, "name": "Mark Burchill",
                 "birth_date": "1980-08-18", "native_display_name": family}
    with pytest.raises(ValueError, match="exact published complete"):
        subject.published_profile_family_display(selection, {"profile": BURCHILL_PROFILE})


def test_published_family_display_refuses_multiword_family_even_when_explicit(tmp_path, monkeypatch):
    source = ROOT / BURCHILL_PROFILE["path"]
    raw = source.read_bytes().replace(b"<strong>Burchill</strong>", b"<strong>Van Burchill</strong>")
    changed = tmp_path / "synthetic-profile.html"
    changed.write_bytes(raw)
    monkeypatch.setattr(subject, "original", lambda _value: changed)
    selection = {"profile": "profile", "provider_player_id": 25204, "name": "Mark Van Burchill",
                 "birth_date": "1980-08-18", "native_display_name": "Van Burchill"}
    evidence = {"profile": {**BURCHILL_PROFILE, "path": "synthetic-profile.html", "sha256": "synthetic"}}
    with pytest.raises(ValueError, match="exact published complete"):
        subject.published_profile_family_display(selection, evidence)


def test_published_family_display_refuses_heading_without_explicit_strong_component(tmp_path, monkeypatch):
    source = ROOT / BURCHILL_PROFILE["path"]
    raw = source.read_bytes().replace(b"<strong>Burchill</strong>", b"Burchill")
    changed = tmp_path / "synthetic-profile.html"
    changed.write_bytes(raw)
    monkeypatch.setattr(subject, "original", lambda _value: changed)
    selection = {"profile": "profile", "provider_player_id": 25204, "name": "Mark Burchill",
                 "birth_date": "1980-08-18", "native_display_name": "Burchill"}
    evidence = {"profile": {**BURCHILL_PROFILE, "path": "synthetic-profile.html", "sha256": "synthetic"}}
    with pytest.raises(ValueError, match="exact published complete"):
        subject.published_profile_family_display(selection, evidence)


MONACO_REQUEST = ROOT / ".local/consolidated-audit-20261009/Monaco2000-opening-review-v1/panucci-bonnal-request-v1.json"


@pytest.fixture
def monaco_request():
    if not MONACO_REQUEST.is_file():
        pytest.skip("retained Monaco exchange request unavailable")
    return subject.pipeline.read_json_file(MONACO_REQUEST)


def test_monaco_classic_used_substitute_is_exact_first_league_fixture(monaco_request):
    opener = monaco_request["evidence"]["opener"]
    assert opener["membership_mode"] == "classic-played-substitutes"
    assert opener["fixture_basis"] == "recorded-first-league-fixture"
    subject.verify_first_league_fixture(opener)
    _, used_substitutes = subject.match_people(opener)
    assert "5642" in [person["source_player_id"] for person in used_substitutes]


def test_monaco_classic_played_substitutes_without_explicit_first_fixture_basis_is_rejected(monaco_request):
    opener = deepcopy(monaco_request["evidence"]["opener"])
    opener.pop("fixture_basis")
    with pytest.raises(ValueError, match="explicit first league fixture"):
        subject.verify_first_league_fixture(opener)


def test_dfb_monaco_panucci_registration_row_is_exact_person_dob_and_period(monaco_request):
    # This records DFB's 1 January 2001 registration start; it is not an exact
    # transfer-announcement day claim.
    subject.dated_source(monaco_request["evidence"]["retirement"])


@pytest.mark.parametrize(
    "path,value",
    [
        (("dfb_registration_row", "full_name"), "Christian Panuccy"),
        (("dfb_registration_row", "birthday_literal"), "12.04.1974"),
        (("dfb_registration_row", "club_heading"), "Chelsea FC"),
        (("dfb_registration_row", "season_start_year"), 2001),
        (("event_date",), "2001-01-02"),
    ],
)
def test_dfb_monaco_registration_rejects_wrong_identity_club_season_or_date(monaco_request, path, value):
    evidence = deepcopy(monaco_request["evidence"]["retirement"])
    target = evidence
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        subject.dated_source(evidence)
