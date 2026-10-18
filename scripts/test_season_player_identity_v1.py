"""Fixture-only tests for provider-scoped source player identity.

No game files, .local baselines, network, DuckDB data or runner are used.
"""

from __future__ import annotations

import copy
import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "upstream/pm99-skezmod-db-editor"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts import capture_transfermarkt_historical_squads_v1 as capture_v1  # noqa: E402
from scripts import compose_season_source_captures_v1 as compose_v1  # noqa: E402
from scripts import pm99_season_qa_v1 as qa  # noqa: E402
from scripts import pm99_simple_season_v1 as simple_v1  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_player_identity_v1 as identity_lib  # noqa: E402
from scripts import season_source_intake_from_allocation_v1 as allocation_intake_v1  # noqa: E402
from scripts import season_source_intake_v1 as intake_v1  # noqa: E402
from scripts import season_source_package_builder_v1 as builder  # noqa: E402
from scripts import supplement_2015_ntf_with_transfermarkt as supplement  # noqa: E402
from scripts.capture_transfermarkt_opening_lineups_v1 import CaptureError, TeamRef  # noqa: E402
from scripts.merge_footballsquads_captures import MergeError  # noqa: E402
from scripts.test_season_package_v2 import _valid_package  # noqa: E402
from scripts.test_season_source_intake_v1 import _registry as intake_registry  # noqa: E402

TM = "transfermarkt"


def ident(player_id: str, provider: str = TM) -> dict[str, str]:
    return {"provider": provider, "player_id": player_id}


# --------------------------------------------------------------------------
# HTML fixtures: standard (streaming) parser and DOM fallback
# --------------------------------------------------------------------------

def tm_row(number: int, href: str, name: str, position: str = "Centre-Back", nation: str = "England") -> str:
    return (
        f'<tr><td class="zentriert">{number}</td><td><table class="inline-table"><tr>'
        f'<td><a href="{href}"><img src="x.png"></a></td><td><a href="{href}">{name}</a></td></tr>'
        f'<tr><td>{position}</td></tr></table></td><td>24</td>'
        f'<td><img class="flaggenrahmen" title="{nation}"></td></tr>'
    )


def tm_page(*rows: str) -> bytes:
    return ('<table class="items"><tbody>' + "".join(rows) + "</tbody></table>").encode()


def dom_row(number: int, href: str, name: str, title: str = "Defender") -> str:
    return (
        f'<tr><td class="zentriert rueckennummer" title="{title}"><div class="rn_nummer">{number}</div></td>'
        f'<td><table><tr><td><a href="{href}">{name}</a></td></tr><tr><td>Centre-Back</td></tr></table></td>'
        f'<td>24</td><td><img class="flaggenrahmen" title="Romania"></td></tr>'
    )


def by_name(rows: list[dict], name: str) -> list[dict]:
    return [row for row in rows if row["name"] == name]


def test_standard_parser_keeps_literal_ids_for_namesakes_and_provider_scope() -> None:
    rows = supplement.parse_squad(tm_page(
        tm_row(1, "/alex-smith/profil/spieler/111", "Alex Smith", "Goalkeeper"),
        tm_row(2, "/alex-smith-2/profil/spieler/222", "Alex Smith"),
        tm_row(3, "/bo/profil/spieler/333/saison/2000", "Bo", "Left-Back", "Wales"),
    ))
    assert [(row["name"], row["source_identity"]) for row in rows] == [
        ("Alex Smith", ident("222")), ("Bo", ident("333")), ("Alex Smith", ident("111")),
    ]
    assert all(isinstance(row["source_identity"]["player_id"], str) for row in rows)
    # Identity is not an unresolved *fact* and is not placed in that list.
    assert "source_identity" not in rows[0]["unresolved_fields"]


def test_standard_parser_collapses_identical_markup_and_rejects_conflicts() -> None:
    one = tm_row(2, "/a/profil/spieler/222", "Alex Smith")
    assert len(supplement.parse_squad(tm_page(one, one))) == 1
    with pytest.raises(identity_lib.IdentityError, match="conflicting"):
        supplement.parse_squad(tm_page(one, tm_row(9, "/a/profil/spieler/222", "Alex Smith")))
    two_ids = tm_row(5, "/a/profil/spieler/1", "Cy").replace('<td><a href="/a/profil/spieler/1"><img', '<td><a href="/a/profil/spieler/2"><img', 1)
    with pytest.raises(identity_lib.IdentityError, match="several Transfermarkt"):
        supplement.parse_squad(tm_page(two_ids))


def test_standard_parser_leaves_missing_or_noncanonical_ids_unknown_and_legacy_shaped() -> None:
    rows = supplement.parse_squad(tm_page(
        tm_row(4, "/d/profil/spieler/abc", "Dee"),
        tm_row(4, "/d/profil/spieler/abc", "Dee"),
        tm_row(6, "/e/profil/spieler/007", "Eve"),
    ))
    assert sorted(row["name"] for row in rows) == ["Dee", "Eve"]  # legacy name-keyed collapse
    assert all("source_identity" not in row for row in rows)
    assert set(rows[0]) == {
        "shirt_number", "name", "nationality", "position", "height_cm", "weight_kg",
        "birth_date", "unresolved_fields",
    }


def test_dom_fallback_retains_ids_namesakes_and_rejects_conflicts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture_v1, "parse_squad", lambda _payload: [])
    page = tm_page(
        dom_row(4, "/a/profil/spieler/11", "Ana Example"),
        dom_row(4, "/a/profil/spieler/11", "Ana Example"),
        dom_row(5, "/b/profil/spieler/12", "Ana Example"),
        dom_row(6, "/c/profil/spieler/zz", "Cora"),
    )
    rows = capture_v1.parse_squad_with_dom_fallback(page)
    assert [(row["name"], row.get("source_identity")) for row in rows] == [
        ("Ana Example", ident("11")), ("Ana Example", ident("12")), ("Cora", None),
    ]
    assert "source_identity" not in rows[2]
    with pytest.raises(CaptureError, match="conflicting"):
        capture_v1.parse_squad_with_dom_fallback(tm_page(
            dom_row(4, "/a/profil/spieler/11", "Ana Example"), dom_row(9, "/a/profil/spieler/11", "Ana Example"),
        ))
    with pytest.raises(CaptureError, match="several Transfermarkt"):
        capture_v1.parse_squad_with_dom_fallback(tm_page(
            dom_row(4, "/a/profil/spieler/11", "Ana Example").replace(
                "<td>24</td>", '<td><a href="/z/profil/spieler/99">x</a></td>', 1),
        ))


def test_standard_parser_conflict_is_not_masked_by_the_dom_fallback() -> None:
    one = tm_row(2, "/a/profil/spieler/222", "Alex Smith")
    with pytest.raises(CaptureError, match="conflicting"):
        capture_v1.parse_squad_with_dom_fallback(tm_page(one, tm_row(9, "/a/profil/spieler/222", "Alex Smith")))


def test_canonical_player_validates_and_preserves_identity_only_when_present() -> None:
    base = {"name": "P", "position": "D", "nationality": "ENG", "shirt_number": 3}
    legacy = capture_v1.canonical_player(base)
    assert "source_identity" not in legacy
    assert capture_v1.canonical_player({**base, "source_identity": ident("5")})["source_identity"] == ident("5")
    for bad in (ident("05"), ident("x"), {"provider": "other", "player_id": "5"}, {"provider": TM}, "5", ident(5)):  # type: ignore[arg-type]
        with pytest.raises(CaptureError):
            capture_v1.canonical_player({**base, "source_identity": bad})


# --------------------------------------------------------------------------
# Audit helper
# --------------------------------------------------------------------------

def entry(ref: str, name: str | None, *, club: str = "c1", dob: str | None = None,
          identity: object = None, shirt: int | None = None, native: bool = False) -> dict:
    return {"ref": ref, "club": club, "name": name, "birth_date": dob, "source_identity": identity,
            "shirt_number": shirt, "native_preserved": native}


def test_same_provider_id_is_a_strong_candidate_even_without_dob_club_or_number() -> None:
    audit = identity_lib.audit_entries([
        entry("a", "Alex Smith", club="c1", identity=ident("111"), shirt=9),
        entry("b", "Alex  SMITH", club="c2", identity=ident("111"), shirt=19),
    ])
    (candidate,) = audit["same_provider_id_candidates"]
    assert candidate["key"] == "provider-id:transfermarkt:111"
    assert candidate["classification"] == "strong-duplicate-candidate" and candidate["status"] == "unreviewed"
    assert candidate["distinct_clubs"] and candidate["distinct_shirt_numbers"]
    assert candidate["birth_date_known_for_all"] is False
    assert audit["metadata_conflicts"] == [] and candidate["metadata_conflict_fields"] == []
    assert audit["counts"]["same_provider_id_candidates"] == 1


def test_one_provider_id_with_conflicting_name_or_birth_date_is_a_conflict() -> None:
    audit = identity_lib.audit_entries([
        entry("a", "Alex Smith", dob="1980-01-01", identity=ident("111")),
        entry("b", "Bob Jones", dob="1981-02-02", identity=ident("111")),
    ])
    assert audit["metadata_conflicts"] == [
        {"key": "provider-id:transfermarkt:111", "provider": TM, "player_id": "111", "fields": ["name", "birth_date"]},
    ]
    # A missing date on one side is insufficient evidence, not a conflict.
    audit = identity_lib.audit_entries([
        entry("a", "Alex Smith", dob="1980-01-01", identity=ident("111")),
        entry("b", "Alex Smith", identity=ident("111")),
    ])
    assert audit["metadata_conflicts"] == []
    assert audit["same_provider_id_candidates"][0]["birth_date_known_for_all"] is False


def test_namesakes_with_different_ids_are_not_merged_by_name_and_birth_date() -> None:
    audit = identity_lib.audit_entries([
        entry("a", "Alex Smith", dob="1990-05-05", identity=ident("111")),
        entry("b", "Alex Smith", dob="1990-05-05", identity=ident("222"), club="c2"),
    ])
    assert audit["same_provider_id_candidates"] == [] and audit["name_birth_date_candidates"] == []
    (namesake,) = audit["distinct_provider_id_namesakes"]
    assert [member["player_id"] for member in namesake["members"]] == ["111", "222"]


def test_name_and_birth_date_fallback_is_retained_for_missing_or_cross_provider_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(identity_lib.PROVIDER_ID_PATTERNS, "example", r"[1-9][0-9]*")
    plain = identity_lib.audit_entries([
        entry("a", "José Núñez", dob="1990-05-05"), entry("b", "Jose Nunez", dob="1990-05-05", club="c2"),
    ])
    assert [row["classification"] for row in plain["name_birth_date_candidates"]] == ["name-birth-date-candidate"]
    one_id = identity_lib.audit_entries([
        entry("a", "Jose Nunez", dob="1990-05-05", identity=ident("7")), entry("b", "Jose Nunez", dob="1990-05-05"),
    ])
    assert len(one_id["name_birth_date_candidates"]) == 1
    # The same number in two provider namespaces is neither equal nor distinct.
    cross = identity_lib.audit_entries([
        entry("a", "Jose Nunez", dob="1990-05-05", identity=ident("7")),
        entry("b", "Jose Nunez", dob="1990-05-05", identity=ident("7", "example")),
    ])
    assert cross["same_provider_id_candidates"] == []
    assert len(cross["name_birth_date_candidates"]) == 1 and cross["distinct_provider_id_namesakes"] == []
    # Different names and dates never become candidates.
    assert identity_lib.audit_entries([
        entry("a", "A B", dob="1990-05-05"), entry("b", "A B", dob="1990-05-06"), entry("c", "A C", dob="1990-05-05"),
    ])["name_birth_date_candidates"] == []


def test_unknown_identity_and_birth_date_are_reported_not_treated_as_clean() -> None:
    audit = identity_lib.audit_entries([
        entry("a", "Same Name"), entry("b", "Same Name"),
        entry("c", "Dated", dob="1990-01-01", native=True), entry("d", "Known", identity=ident("1")),
        entry("e", "Bad", dob="1990-01-01", identity={"provider": TM}),
    ])
    coverage = audit["coverage"]
    assert coverage["entry_count"] == 5 and coverage["with_provider_identity"] == 1
    assert coverage["missing_provider_identity"] == 3 and coverage["malformed_provider_identity"] == 1
    assert coverage["missing_provider_identity_native_preserved"] == 1
    assert coverage["missing_identity_and_birth_date"] == 2
    assert [row["ref"] for row in audit["insufficient_identity_facts"]] == ["a", "b"]
    assert coverage["screening"] == "incomplete" and coverage["duplicate_free_verified"] is False
    assert audit["name_birth_date_candidates"] == []  # absence of a finding is not proof
    assert [row["ref"] for row in audit["malformed_identities"]] == ["e"]


def test_complete_id_coverage_still_never_claims_duplicate_free_verification() -> None:
    audit = identity_lib.audit_entries([entry("a", "A", identity=ident("1")), entry("b", "B", identity=ident("2"))])
    assert audit["coverage"]["screening"] == "complete-provider-identity"
    assert audit["coverage"]["duplicate_free_verified"] is False
    assert "not verified" in audit["verification"]
    assert identity_lib.audit_entries([])["coverage"]["screening"] == "incomplete"


def test_audit_is_deterministic_regardless_of_input_order() -> None:
    entries = [
        entry(f"r{index}", name, club=f"c{index % 3}", dob=dob, identity=identity)
        for index, (name, dob, identity) in enumerate([
            ("Alex Smith", None, ident("111")), ("Alex Smith", None, ident("111")),
            ("Bo Bo", "1990-01-01", None), ("Bo Bo", "1990-01-01", ident("5")),
            ("Cy", "1991-01-01", ident("8")), ("Cy", "1991-01-01", ident("9")), ("Di", None, None),
        ])
    ]
    expected = json.dumps(identity_lib.audit_entries(entries), sort_keys=True)
    for seed in range(5):
        shuffled = list(entries)
        random.Random(seed).shuffle(shuffled)
        assert json.dumps(identity_lib.audit_entries(shuffled), sort_keys=True) == expected


def test_name_key_matches_the_existing_strict_package_guard() -> None:
    for name in ("José Núñez", "O'Neil-Smith", "Łukasz  Fabiański", "Ünal"):
        player = {"name": name, "facts": {"birth_date": "1990-01-01"}}
        assert package_v2._person_candidate_key(player) == (identity_lib.normalise_person_name(name), "1990-01-01")


def test_schema_and_helper_agree_on_providers_and_id_syntax() -> None:
    schema = json.loads(package_v2.SCHEMA_PATH.read_text())["$defs"]["source-identity"]
    assert [schema["properties"]["provider"]["const"]] == sorted(identity_lib.PROVIDER_ID_PATTERNS)
    assert schema["properties"]["player_id"]["pattern"] == "^" + identity_lib.PROVIDER_ID_PATTERNS[TM] + "$"
    assert set(package_v2.SOURCE_IDENTITY_PATTERNS) == set(identity_lib.PROVIDER_ID_PATTERNS)


# --------------------------------------------------------------------------
# Actual public chain: capture -> compose -> normalise -> intake -> builder
# --------------------------------------------------------------------------

SQUAD_PAGE = tm_page(
    tm_row(1, "/k/profil/spieler/101", "Keeper One", "Goalkeeper"),
    tm_row(2, "/s/profil/spieler/111", "Alex Smith"),
    tm_row(3, "/s2/profil/spieler/222", "Alex Smith"),
    tm_row(4, "/n/profil/spieler/nope", "No Identity"),
)
OTHER_PAGE = tm_page(tm_row(7, "/s/profil/spieler/111", "Alex Smith"), tm_row(8, "/o/profil/spieler/303", "Other"))


class _Cache:
    used: dict = {}

    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def get(self, url: str, key: str) -> bytes:
        return self.payload


def _capture(monkeypatch: pytest.MonkeyPatch, payload: bytes, *, club: str, country: str, club_id: int) -> dict:
    monkeypatch.setattr(
        capture_v1, "_competition_teams",
        lambda **_kw: [TeamRef(club, club, club_id, f"/{club.lower()}/startseite/verein/{club_id}", "source")],
    )
    scope = [{"country_catalog": country, "competition_catalog": "laliga", "competition_name": "League", "source_competition_code": "ES1"}]
    capture, gaps = capture_v1.build_capture(
        season_start_year=2000, scope=scope, scope_sha256="a" * 64, cache=_Cache(payload),  # type: ignore[arg-type]
    )
    assert gaps["gaps"] == []
    return capture


@pytest.fixture()
def captures(monkeypatch: pytest.MonkeyPatch) -> tuple[dict, dict]:
    return (
        _capture(monkeypatch, SQUAD_PAGE, club="Real Sociedad", country="spain", club_id=1),
        _capture(monkeypatch, OTHER_PAGE, club="Baseline 2", country="spain", club_id=2),
    )


def test_capture_emits_identity_only_for_literal_ids_and_counts_them(captures: tuple[dict, dict]) -> None:
    first, _second = captures
    players = first["clubs"][0]["players"]
    # Same position and name: the provider ID is the deterministic tie-breaker.
    assert [p.get("source_identity") for p in by_name(players, "Alex Smith")] == [ident("111"), ident("222")]
    assert "source_identity" not in by_name(players, "No Identity")[0]
    assert first["summary"]["player_rows_with_provider_identity"] == 3
    assert first["clubs"][0]["players"][0]["unresolved_fields"]  # unrelated unknown facts stay explicit


def test_capture_without_any_ids_keeps_its_legacy_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = _capture(monkeypatch, tm_page(tm_row(1, "/k/profil/spieler/x", "Keeper", "Goalkeeper")),
                      club="Real Sociedad", country="spain", club_id=1)
    assert "player_rows_with_provider_identity" not in legacy["summary"]
    assert all("source_identity" not in p for p in legacy["clubs"][0]["players"])


def _compose(captures: tuple[dict, dict]) -> dict:
    inputs = [(f"c{index}.json", capture, f"{index}" * 64) for index, capture in enumerate(captures, 1)]
    return compose_v1.compose(inputs=inputs, catalog="2000-2001", label="2000/01")


def test_compose_preserves_identity_and_rejects_malformed_or_inconsistent_ids(captures: tuple[dict, dict]) -> None:
    composed = _compose(captures)
    assert composed["summary"]["player_rows_with_provider_identity"] == 5
    assert composed == _compose(captures)  # deterministic
    # The same ID in two clubs is retained (dated reconciliation, not a compositor decision).
    ids = [p["source_identity"]["player_id"] for c in composed["clubs"] for p in c["players"] if "source_identity" in p]
    assert ids.count("111") == 2
    bad = copy.deepcopy(captures)
    bad[1]["clubs"][0]["players"][0]["source_identity"] = ident("012")
    with pytest.raises(MergeError, match="malformed"):
        _compose(bad)
    conflict = copy.deepcopy(captures)
    for player in conflict[1]["clubs"][0]["players"]:
        if player.get("source_identity") == ident("111"):
            player["name"] = "Somebody Else"
    with pytest.raises(MergeError, match="inconsistently"):
        _compose(conflict)


def test_legacy_compose_output_has_no_identity_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    page = tm_page(tm_row(1, "/k/profil/spieler/x", "Keeper", "Goalkeeper"))
    composed = _compose((
        _capture(monkeypatch, page, club="Real Sociedad", country="spain", club_id=1),
        _capture(monkeypatch, page, club="Baseline 2", country="spain", club_id=2),
    ))
    assert "player_rows_with_provider_identity" not in composed["summary"]


def _normalised(captures: tuple[dict, dict]) -> tuple[dict, dict]:
    return simple_v1._normalise_capture(_compose(captures))


def test_normalisation_keeps_identity_reports_cross_club_claims_and_strips_nothing_else(captures: tuple[dict, dict]) -> None:
    normalised, receipt = _normalised(captures)
    assert receipt["source_identity_cross_club_claims"] == [
        {"provider": TM, "player_id": "111", "clubs": ["Baseline 2", "Real Sociedad"]},
    ]
    assert receipt["source_identity_cross_club_claim_count"] == 1
    # The canonical club contract has no competition-code field; it is receipted instead.
    assert all("source_competition_code" not in club for club in normalised["clubs"])
    assert {row["source_competition_code"] for row in receipt["club_source_competition_codes"]} == {"ES1"}
    players = [p for club in normalised["clubs"] for p in club["players"]]
    assert sum("source_identity" in p for p in players) == 5


def test_normalisation_of_legacy_capture_adds_no_identity_receipt_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    page = tm_page(tm_row(1, "/k/profil/spieler/x", "Keeper", "Goalkeeper"))
    _normalised_cap, receipt = _normalised((
        _capture(monkeypatch, page, club="Real Sociedad", country="spain", club_id=1),
        _capture(monkeypatch, page, club="Baseline 2", country="spain", club_id=2),
    ))
    assert not any(key.startswith("source_identity") for key in receipt)


def _registry_for_chain() -> dict:
    registry = intake_registry()
    registry["carriers"][0]["baseline_club"].update(name="Real Sociedad", full_name="Real Sociedad")
    return registry


def _allocation_for(normalised: dict, registry: dict) -> dict:
    clubs = {club["club_name"]: club for club in normalised["clubs"]}
    rows = []
    for carrier_id, name in ((1, "Real Sociedad"), (2, "Baseline 2")):
        club = clubs[name]
        rows.append({
            "carrier_id": carrier_id, "club_name": name, "roster_capacity": 3,
            "source_selector": {key: club[key] for key in (
                "country_catalog", "competition_catalog", "source_path", "source_sha256")},
        })
    return {
        "schema_version": allocation_intake_v1.ALLOCATION_SCHEMA, "assignments": rows,
        "source_sha256": builder._sha256_document(normalised), "registry_sha256": builder._sha256_document(registry),
    }


def _intake_chain(captures: tuple[dict, dict]) -> tuple[dict, dict, dict]:
    normalised, _receipt = _normalised(captures)
    registry = _registry_for_chain()
    assignment = allocation_intake_v1.adapt(
        allocation=_allocation_for(normalised, registry), registry=registry, source=normalised,
        assignment_id="world-2000-01",
    )
    intake = intake_v1.build_intake(
        registry=registry, source_capture=normalised, assignment=assignment, intake_id="world-2000-01-intake",
    )
    return normalised, registry, intake


def test_allocation_intake_and_intake_retain_identity_and_validate(captures: tuple[dict, dict]) -> None:
    normalised, registry, intake = _intake_chain(captures)
    facts = [row["facts"] for club in intake["source_clubs"] for row in club["players"]]
    assert sum("source_identity" in row for row in facts) == 5
    assert all("source_identity" not in row for row in by_name(facts, "No Identity"))
    # row hashes are bound to the identity: changing the ID changes the hash.
    assert intake == _intake_chain(captures)[2]
    changed = copy.deepcopy(normalised)
    changed["clubs"][0]["players"][0]["source_identity"] = ident("999")
    assert intake_v1._normalise_source_clubs(changed)[0]["players"][0]["source_row_sha256"] != (
        intake["source_clubs"][0]["players"][0]["source_row_sha256"])
    assert intake_v1.audit_intake(
        intake=intake, registry=registry, source_capture=normalised,
        assignment=allocation_intake_v1.adapt(
            allocation=_allocation_for(normalised, registry), registry=registry, source=normalised,
            assignment_id="world-2000-01"),
    )["coverage"]["source_player_rows_with_provider_identity"] == 5


def test_intake_rejects_malformed_identity_and_same_id_twice_in_one_club(captures: tuple[dict, dict]) -> None:
    normalised, _receipt = _normalised(captures)
    for bad in (ident("0"), {"provider": TM, "player_id": "1", "extra": 1}, {"provider": "x", "player_id": "1"}, None):
        broken = copy.deepcopy(normalised)
        broken["clubs"][0]["players"][0]["source_identity"] = bad
        with pytest.raises(intake_v1.SourceIntakeError):
            intake_v1._normalise_source_clubs(broken)
    repeated = copy.deepcopy(normalised)
    club = repeated["clubs"][0]
    first = next(p for p in club["players"] if p.get("source_identity") == ident("111"))
    club["players"].append({**first, "shirt_number": 30})
    with pytest.raises(intake_v1.SourceIntakeError, match="repeats"):
        intake_v1._normalise_source_clubs(repeated)
    extra = copy.deepcopy(normalised)
    extra["clubs"][0]["players"][0]["provider_player_id"] = "5"
    with pytest.raises(intake_v1.SourceIntakeError, match="unsupported player fields"):
        intake_v1._normalise_source_clubs(extra)


def test_legacy_intake_players_without_identity_are_unchanged() -> None:
    player = {
        "shirt_number": 1, "name": "Legacy", "nationality": None, "position": "G", "height_cm": None,
        "weight_kg": None, "birth_date": None,
        "unresolved_fields": ["nationality", "height_cm", "weight_kg", "birth_date"],
    }
    assert intake_v1._validate_player(player, label="legacy") == player


def _template(registry: dict) -> dict:
    players, clubs = [], []
    for carrier_id in (1, 2):
        ids = [f"player-{carrier_id}-{slot}" for slot in range(3)]
        clubs.append({
            "id": f"club-{carrier_id}", "carrier_id": carrier_id, "name": f"Baseline {carrier_id}",
            "full_name": f"Baseline {carrier_id}", "roster_player_ids": ids, "proof": {},
        })
        players.extend({
            "id": player_id, "carrier_id": carrier_id * 1000 + slot, "carrier_family": "dd6360",
            "club_id": f"club-{carrier_id}", "name": f"Native {player_id}", "person_id": f"person-native-{player_id}",
            "facts": {}, "ratings": {"sentinel": 1}, "proof": {},
            # A stale identity from a replayed earlier draft must never survive a rewrite.
            "source_identity": ident("424242"),
        } for slot, player_id in enumerate(ids))
    clubs[0].update(name="Real Sociedad", full_name="Real Sociedad")
    return {
        "schema_version": "pm99-season-package-v2", "package_id": "template-package",
        "season": {"start_year": 2000, "end_year": 2001, "label": "2000/01"}, "scope": {},
        "artifacts": [], "sources": [], "clubs": clubs, "players": players, "managers": [],
        "assets": {"kits": [], "portraits": []}, "calendar": {"target_year": 2000, "target_rollover_year": 2001},
        "proofs": [], "migration": {"known_gaps": []},
    }


def _build_draft(monkeypatch: pytest.MonkeyPatch, captures: tuple[dict, dict]) -> tuple[dict, dict, dict]:
    monkeypatch.setattr(builder.package_v2, "validate_package", lambda *_a, **_k: None)
    _normalised_cap, registry, intake = _intake_chain(captures)
    draft, audit = builder.build_draft(template=_template(registry), source_intake=intake, registry=registry)
    return draft, audit, intake


def test_builder_writes_identity_onto_recipe_players_and_drops_stale_template_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _capture(monkeypatch, tm_page(
        tm_row(1, "/k/profil/spieler/101", "Keeper One", "Goalkeeper"),
        tm_row(2, "/s/profil/spieler/111", "Alex Smith"),
        tm_row(3, "/s2/profil/spieler/222", "Alex Smith"),
    ), club="Real Sociedad", country="spain", club_id=1)
    second = _capture(monkeypatch, tm_page(
        tm_row(1, "/p/profil/spieler/303", "Pat Three"), tm_row(2, "/q/profil/spieler/304", "Quinn Four"),
        tm_row(3, "/r/profil/spieler/305", "Rae Five"),
    ), club="Baseline 2", country="spain", club_id=2)
    draft, audit, _intake = _build_draft(monkeypatch, (first, second))
    sociedad = [p for p in draft["players"] if p["club_id"] == "club-1"]
    assert sorted(p["source_name"] for p in sociedad) == ["Alex Smith", "Alex Smith", "Keeper One"]
    # Both namesakes (distinct IDs) survive as separate people with their own provider IDs;
    # a name-keyed join would have merged or excluded them.
    assert sorted(p["source_identity"]["player_id"] for p in sociedad) == ["101", "111", "222"]
    assert len({p["person_id"] for p in sociedad}) == 3
    assert audit["source_person_identity_conflicts"] == []
    assert sorted(p["source_identity"]["player_id"] for p in draft["players"] if p["club_id"] == "club-2") == [
        "303", "304", "305"]
    assert ident("424242") not in [p.get("source_identity") for p in draft["players"]]
    assert audit["coverage"]["updated_player_slots_with_provider_identity"] == 6
    # The identity reaches a strictly valid package player and the ordinary QA screen.
    package = _valid_package()
    package["players"][0]["source_identity"] = sociedad[0]["source_identity"]
    package_v2.validate_package(package, strict=True)
    assert qa.audit_player_identities(draft)["coverage"]["with_provider_identity"] == 6


def test_builder_clears_a_stale_identity_when_the_new_source_row_is_unidentified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builder.package_v2, "validate_package", lambda *_a, **_k: None)
    legacy = tuple(
        _capture(monkeypatch, tm_page(tm_row(1, "/k/profil/spieler/x", f"Keeper {name[-1]}", "Goalkeeper")),
                 club=name, country="spain", club_id=index)
        for index, name in ((1, "Real Sociedad"), (2, "Baseline 2"))
    )
    _cap, registry, intake = _intake_chain(legacy)  # type: ignore[arg-type]
    draft, audit = builder.build_draft(template=_template(registry), source_intake=intake, registry=registry)
    written = [p for p in draft["players"] if str(p.get("source_name", "")).startswith("Keeper")]
    assert len(written) == 2 and all("source_identity" not in p for p in written)
    assert "updated_player_slots_with_provider_identity" not in audit["coverage"]


def test_builder_candidate_key_scopes_by_provider_id_and_keeps_name_birth_date_for_unidentified_rows() -> None:
    base = {"facts": {"name": "Alex Smith", "birth_date": "1990-01-01"}}
    with_id = lambda pid: {"facts": {**base["facts"], "source_identity": ident(pid)}}  # noqa: E731
    assert builder._person_candidate(with_id("1")) == ("source-identity", "transfermarkt:1")
    assert builder._person_candidate(with_id("1")) != builder._person_candidate(with_id("2"))
    assert builder._person_candidate(base) == ("alexsmith", "1990-01-01")


def test_builder_same_provider_id_in_two_clubs_is_an_unresolved_conflict_not_a_silent_pick(
    monkeypatch: pytest.MonkeyPatch, captures: tuple[dict, dict],
) -> None:
    draft, audit, _intake = _build_draft(monkeypatch, captures)
    conflicts = audit["source_person_identity_conflicts"]
    assert [row["normalised_name"] for row in conflicts] == ["source-identity"]
    assert conflicts[0]["birth_date"] == "transfermarkt:111"
    written_ids = [p["source_identity"]["player_id"] for p in draft["players"] if "source_identity" in p]
    assert "111" not in written_ids  # excluded from both clubs rather than assigned to one arbitrarily


# --------------------------------------------------------------------------
# Strict package + schema
# --------------------------------------------------------------------------

def test_schema_accepts_valid_identity_and_rejects_malformed_ones() -> None:
    package = _valid_package()
    package["players"][0]["source_identity"] = ident("123")
    package_v2.validate_package(package, strict=True)
    for bad in (ident("0123"), {"provider": TM, "player_id": 123}, {"provider": "other", "player_id": "1"},
                {"provider": TM}, {"provider": TM, "player_id": "1", "extra": True}, "x", None):
        broken = copy.deepcopy(package)
        broken["players"][0]["source_identity"] = bad
        assert package_v2._schema_errors(broken), bad
        with pytest.raises(package_v2.PackageValidationError):
            package_v2.validate_package(broken)


def test_package_validator_rejects_malformed_identity_even_without_the_json_schema_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(package_v2, "_schema_errors", lambda _package: [])
    package = _valid_package()
    package["players"][0]["source_identity"] = {"provider": TM, "player_id": "01"}
    with pytest.raises(package_v2.PackageValidationError, match="malformed provider player identity"):
        package_v2.validate_package(package)


def test_strict_package_rejects_a_repeated_provider_id_but_not_distinct_ids_or_non_strict_drafts() -> None:
    package = _valid_package()
    package["players"][0]["source_identity"] = ident("123")
    package["players"][1]["source_identity"] = ident("123")
    package_v2.validate_package(package)  # builder drafts keep collisions as audit data
    with pytest.raises(package_v2.PackageValidationError, match="repeated provider player identity"):
        package_v2.validate_package(package, strict=True)
    package["players"][1]["source_identity"] = ident("124")
    package_v2.validate_package(package, strict=True)


def test_strict_name_birth_date_guard_still_applies_to_players_with_distinct_ids() -> None:
    package = _valid_package()
    first, second = package["players"][0], package["players"][1]
    second["name"], second["facts"] = first["name"], dict(first["facts"])
    first["source_identity"], second["source_identity"] = ident("1"), ident("2")
    with pytest.raises(package_v2.PackageValidationError, match="ambiguous same-person"):
        package_v2.validate_package(package, strict=True)


def test_legacy_package_without_identity_still_validates_strictly() -> None:
    package_v2.validate_package(_valid_package(), strict=True)


# --------------------------------------------------------------------------
# Ordinary QA integration
# --------------------------------------------------------------------------

def test_package_entries_prefer_source_name_and_mark_native_preserved_rows() -> None:
    package = _valid_package()
    package["players"][0].update(source_name="Exact Source Name", policy="preserve-existing-mode1")
    rows = identity_lib.entries_from_package(package["players"])
    assert rows[0]["name"] == "Exact Source Name" and rows[0]["native_preserved"] is True
    audit = qa.audit_player_identities(package)
    assert audit["coverage"]["missing_provider_identity_native_preserved"] == 1


def test_qa_issue_mapping_separates_blockers_from_warnings() -> None:
    package = _valid_package()
    first, second, third = package["players"][:3]
    first["source_identity"], second["source_identity"] = ident("5"), ident("5")
    second["source_name"] = "Totally Different"
    third["source_identity"] = {"provider": TM}
    blockers, warnings = qa.player_identity_issues(qa.audit_player_identities(package))
    assert {row["code"] for row in blockers} == {
        "player-identity-metadata-malformed", "player-provider-id-repeated", "player-provider-id-metadata-conflict",
    }
    assert {row["code"] for row in warnings} == {"player-provider-identity-missing"}
    repeated = next(row for row in blockers if row["code"] == "player-provider-id-repeated")
    assert repeated["details"]["count"] == 1
    assert repeated["details"]["samples"][0]["key"] == "provider-id:transfermarkt:5"
    assert "not a resolved historical finding" in repeated["message"]


def test_qa_without_ids_only_warns_and_reports_incomplete_coverage() -> None:
    package = _valid_package()
    for player in package["players"]:
        player["facts"]["birth_date"] = None
    audit = qa.audit_player_identities(package)
    blockers, warnings = qa.player_identity_issues(audit)
    assert blockers == []
    by_code = {row["code"]: row for row in warnings}
    assert by_code["player-provider-identity-missing"]["details"]["count"] == 11
    assert by_code["player-duplicate-screening-insufficient-facts"]["details"]["count"] == 11
    assert audit["coverage"]["screening"] == "incomplete" and audit["coverage"]["duplicate_free_verified"] is False


def test_qa_report_lists_are_bounded_but_counts_are_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qa, "QA_IDENTITY_LIST_LIMIT", 2)
    package = _valid_package()
    for player in package["players"]:
        player["facts"]["birth_date"] = None
    audit = qa.audit_player_identities(package)
    assert len(audit["insufficient_identity_facts"]) == 2 and audit["counts"]["insufficient_identity_facts"] == 11
    _blockers, warnings = qa.player_identity_issues(audit)
    assert next(row for row in warnings if row["code"] == "player-duplicate-screening-insufficient-facts")["details"]["count"] == 11


def _stub_season_audit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, package: dict) -> None:
    """Replace only game/runner/binary-bound checks; identity and package checks run for real."""
    from scripts import audit_compiled_player_birth_dates_v1 as birth_dates
    from scripts import season_contextual_tactics_rollout_v1 as tactics
    from scripts import season_opening_order_repair_v1 as opening_order

    package_path = tmp_path / "package.json"
    package_path.write_bytes(package_v2.canonical_json_bytes(package))
    game = tmp_path / "game"
    (game / "DBDAT").mkdir(parents=True)
    (game / "DBDAT/JUG98030.FDI").write_bytes(b"")
    monkeypatch.setattr(qa, "ROOT", tmp_path)
    monkeypatch.setattr(qa, "validate_candidate", lambda season: {"valid": True, "missing": []})
    monkeypatch.setattr(qa, "game_path", lambda season: game)
    monkeypatch.setattr(qa, "resolve_package", lambda season: package_path)
    monkeypatch.setattr(qa, "audit_compiled_roles", lambda *a, **k: {"failure_count": 0, "unresolved_role_count": 0})
    monkeypatch.setattr(birth_dates, "inspect", lambda *a, **k: {"failure_count": 0})
    monkeypatch.setattr(qa, "audit_manager_sources", lambda *a, **k: {
        "mismatch_count": 0, "missing_reference_count": 0, "provisional_foreign_manager_count": 0})
    monkeypatch.setattr(qa.release_registry, "load_preferred_release", lambda season: SimpleNamespace())
    monkeypatch.setattr(tactics, "load_english", lambda *a, **k: None)
    monkeypatch.setattr(opening_order, "deployment_review", lambda *a, **k: {"warning_count": 0})
    monkeypatch.setattr(qa, "audit_compiled_player_identities", lambda **k: {"failure_count": 0})
    monkeypatch.setattr(qa, "audit_compiled_managers", lambda *a, **k: {"failure_count": 0})
    monkeypatch.setattr(qa, "audit_compiled_handling", lambda *a, **k: {"failure_count": 0})
    monkeypatch.setattr(qa, "audit_compiled_nationalities", lambda *a, **k: {
        "failure_count": 0, "unrepresentable_nationality_count": 0})
    monkeypatch.setattr(qa, "audit_binary_receipt", lambda *a, **k: {"mismatch_count": 0})
    monkeypatch.setattr(qa, "audit_calendar", lambda *a, **k: {"passed": True})
    monkeypatch.setattr(qa, "audit_runtime", lambda *a, **k: {"passed": True})
    monkeypatch.setattr(qa, "audit_kit_outputs", lambda *a, **k: {
        "byte_or_format_failure_count": 0, "visual_review_missing": False})


def test_ordinary_season_qa_reports_identity_coverage_without_blocking_legacy_recipes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    package = _valid_package()
    _stub_season_audit(monkeypatch, tmp_path, package)
    for season in ("2015-16", "2016-17"):  # non-strict and strict package validation
        report = qa.audit_season(season)
        identity = report["checks"]["player_identity"]
        assert report["checks"]["package_validation"]["passed"] is True
        assert identity["coverage"]["missing_provider_identity"] == 11
        assert identity["coverage"]["screening"] == "incomplete"
        codes = [row["code"] for row in report["warnings"]]
        assert "player-provider-identity-missing" in codes
        identity_blockers = {
            "player-identity-metadata-malformed", "player-provider-id-repeated", "player-provider-id-metadata-conflict",
        }
        assert not identity_blockers & {row["code"] for row in report["blockers"]}
        assert report["summary"] == {"blocker_count": len(report["blockers"]), "warning_count": len(report["warnings"])}


def test_ordinary_season_qa_blocks_repeated_or_conflicting_provider_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    package = _valid_package()
    package["players"][0]["source_identity"] = ident("5")
    package["players"][1]["source_identity"] = ident("5")
    package["players"][1]["source_name"] = "Totally Different"
    _stub_season_audit(monkeypatch, tmp_path, package)
    report = qa.audit_season("2015-16")  # non-strict: the QA check itself must block
    codes = {row["code"] for row in report["blockers"]}
    assert {"player-provider-id-repeated", "player-provider-id-metadata-conflict"} <= codes
    assert report["result"] == "fail"
    assert report["checks"]["player_identity"]["coverage"]["with_provider_identity"] == 2
    strict = qa.audit_season("2016-17")
    assert "package-validation-failed" in {row["code"] for row in strict["blockers"]}


def test_ordinary_season_qa_report_is_deterministic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    package = _valid_package()
    package["players"][0]["source_identity"] = ident("5")
    _stub_season_audit(monkeypatch, tmp_path, package)
    first = json.dumps(qa.audit_season("2015-16")["checks"]["player_identity"], sort_keys=True)
    assert first == json.dumps(qa.audit_season("2015-16")["checks"]["player_identity"], sort_keys=True)
