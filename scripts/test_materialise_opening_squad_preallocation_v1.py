from __future__ import annotations

import copy

import pytest

from scripts import materialise_opening_squad_preallocation_v1 as join
from scripts import season_source_club_selection_v1 as selection_v1


def test_join_orders_reconciled_and_profiled_starters_before_squad_tail() -> None:
    selector = {"country_catalog": "eng", "competition_catalog": "d2", "club_name": "Example", "source_path": "x", "source_sha256": "a" * 64}
    intake = {"schema_version": join.INTAKE_SCHEMA, "season": {"label": "2001/02"}, "source_capture_sha256": "b" * 64, "source_clubs": [{
        "selector": selector, "competition_name": "Division", "players": [
            {"source_row_index": 0, "source_row_sha256": "c" * 64, "facts": {"name": "Squad Starter"}},
            {"source_row_index": 1, "source_row_sha256": "d" * 64, "facts": {"name": "Tail"}},
        ],
    }]}
    lineup_xi = [{"source_player_id": "1", "display_name": "Squad Starter"}] + [
        {"source_player_id": str(i), "display_name": f"Added {i}"} for i in range(2, 12)
    ]
    lineup = {"schema_version": join.LINEUP_SCHEMA, "clubs": [{"source_selector": selector, "first_league_fixture_date": "2001-08-01", "source_match_id": "9", "starting_xi": lineup_xi}]}
    reconciliation = {"schema_version": join.RECONCILIATION_SCHEMA, "sources": {"source_capture_sha256": "b" * 64, "lineup_capture_sha256": "LINEUP"}, "clubs": [{"source_selector": selector, "starting_xi": [{"source_player_id": "1", "source_name": "Squad Starter"}]}]}
    additions = {"schema_version": join.ADDITIONS_SCHEMA, "sources": {"lineup_capture_sha256": "LINEUP", "reconciliation_sha256": "RECON"}, "rows": [{
        "source_selector": selector, "source_player_id": str(i), "display_name": f"Added {i}", "profile_status": "opening-fixture-person-profiled",
        "published_full_name": f"Added {i}", "published_birth_date": "1980-01-01", "published_profile_position": "Midfielder",
        "published_height_cm": None, "published_nationality_label": None, "profile_url": f"https://example/{i}",
    } for i in range(2, 12)]}

    result = join.materialise(
        source_intake=intake, source_intake_sha256="INTAKE", lineup=lineup, lineup_sha256="LINEUP",
        reconciliation=reconciliation, reconciliation_sha256="RECON", additions=additions, additions_sha256="ADDITIONS",
    )

    club = result["source_clubs"][0]
    assert club["opening_xi_complete"] is True
    assert [row["facts"]["name"] for row in club["players"][:11]] == ["Squad Starter"] + [f"Added {i}" for i in range(2, 12)]
    assert club["players"][11]["facts"]["name"] == "Tail"
    assert result["summary"]["opening-xi-complete-club-count"] == 1
    assert "source_club_selection_sha256" not in result["sources"]


def test_join_keeps_unprofiled_addition_as_gap() -> None:
    selector = {"country_catalog": "eng", "competition_catalog": "d2", "club_name": "Example", "source_path": "x", "source_sha256": "a" * 64}
    intake = {"schema_version": join.INTAKE_SCHEMA, "season": {"label": "2001/02"}, "source_capture_sha256": "b" * 64, "source_clubs": [{"selector": selector, "competition_name": "Division", "players": []}]}
    lineup = {"schema_version": join.LINEUP_SCHEMA, "clubs": [{"source_selector": selector, "starting_xi": [{"source_player_id": "1"}]}]}
    reconciliation = {"schema_version": join.RECONCILIATION_SCHEMA, "sources": {"source_capture_sha256": "b" * 64, "lineup_capture_sha256": "LINEUP"}, "clubs": [{"source_selector": selector, "starting_xi": []}]}
    additions = {"schema_version": join.ADDITIONS_SCHEMA, "sources": {"lineup_capture_sha256": "LINEUP", "reconciliation_sha256": "RECON"}, "rows": [{"source_selector": selector, "source_player_id": "1", "profile_status": "profile-facts-pending"}]}

    result = join.materialise(source_intake=intake, source_intake_sha256="INTAKE", lineup=lineup, lineup_sha256="LINEUP", reconciliation=reconciliation, reconciliation_sha256="RECON", additions=additions, additions_sha256="ADDITIONS")

    assert result["source_clubs"][0]["opening_xi_complete"] is False
    assert result["summary"]["profile-facts-pending-count"] == 1
    assert result["gaps"][0]["source_player_id"] == "1"


def test_profile_role_outside_pm99_groups_uses_published_lineup_group() -> None:
    row = {
        "profile_status": "opening-fixture-person-profiled", "source_player_id": "7",
        "published_full_name": "Example Winger", "published_profile_position": "Right Winger",
        "source_position_group": "Forwards", "profile_url": "https://example.test/7",
    }
    player = join._addition_player(row, 0)
    assert player["facts"]["position"] == "F"


def test_join_uses_sourced_birth_date_to_select_one_same_name_intake_row() -> None:
    selector = {"country_catalog": "eng", "competition_catalog": "flone", "club_name": "Rochdale", "source_path": "x", "source_sha256": "a" * 64}
    players = [
        {"source_row_index": 0, "source_row_sha256": "c" * 64, "facts": {"name": "Jordan Williams", "birth_date": "1995-11-06"}},
        {"source_row_index": 1, "source_row_sha256": "d" * 64, "facts": {"name": "Jordan Williams", "birth_date": "1992-12-13"}},
    ] + [
        {"source_row_index": i, "source_row_sha256": f"{i:064x}", "facts": {"name": f"Player {i}"}}
        for i in range(2, 12)
    ]
    intake = {"schema_version": join.INTAKE_SCHEMA, "season": {"label": "2018/19"}, "source_capture_sha256": "b" * 64, "source_clubs": [{"selector": selector, "competition_name": "League One", "players": players}]}
    lineup_xi = [{"source_player_id": "1"}] + [{"source_player_id": str(i)} for i in range(2, 12)]
    lineup = {"schema_version": join.LINEUP_SCHEMA, "clubs": [{"source_selector": selector, "first_league_fixture_date": "2018-08-04", "source_match_id": "9", "starting_xi": lineup_xi}]}
    resolved = [{"source_player_id": "1", "source_name": "Jordan Williams", "source_birth_date": "1995-11-06"}] + [
        {"source_player_id": str(i), "source_name": f"Player {i}"} for i in range(2, 12)
    ]
    reconciliation = {"schema_version": join.RECONCILIATION_SCHEMA, "sources": {"source_capture_sha256": "b" * 64, "lineup_capture_sha256": "LINEUP"}, "clubs": [{"source_selector": selector, "starting_xi": resolved}]}
    additions = {"schema_version": join.ADDITIONS_SCHEMA, "sources": {"lineup_capture_sha256": "LINEUP", "reconciliation_sha256": "RECON"}, "rows": []}

    result = join.materialise(source_intake=intake, source_intake_sha256="INTAKE", lineup=lineup, lineup_sha256="LINEUP", reconciliation=reconciliation, reconciliation_sha256="RECON", additions=additions, additions_sha256="ADDITIONS")

    assert result["source_clubs"][0]["opening_xi_complete"] is True
    assert result["source_clubs"][0]["players"][0]["facts"]["birth_date"] == "1995-11-06"


def _selection_fixture() -> tuple[dict, dict, dict, dict, dict]:
    """Return a minimal all-season/selected-August evidence chain."""

    canonical = {
        "country_catalog": "eng", "competition_catalog": "national", "club_name": "Example Town",
        "source_path": "eng/example.txt", "source_sha256": "a" * 64,
    }
    selected = {
        "country_catalog": "english-non-league", "competition_catalog": "soccerbase-august",
        "club_name": "Example", "source_path": "soccerbase/example/august", "source_sha256": "b" * 64,
    }
    all_season_player = {
        "source_row_index": 0, "source_row_sha256": "c" * 64,
        "facts": {"name": "All-season Player"},
    }
    selected_player = {
        "source_row_index": 0, "source_row_sha256": "d" * 64,
        "facts": {"name": "Opening Player"},
    }
    intake = {
        "schema_version": join.INTAKE_SCHEMA,
        "intake_id": "world-2016-17-source-intake",
        "season": {"catalog": "2016-2017", "label": "2016/17"},
        "source": {"title": "credited capture"},
        "source_capture_sha256": "e" * 64,
        "source_clubs": [
            {"selector": canonical, "competition_name": "National League", "players": [all_season_player]},
            {"selector": selected, "competition_name": "National League", "players": [selected_player]},
        ],
    }
    manifest = {
        "schema_version": selection_v1.MANIFEST_SCHEMA,
        "selection_id": "world-2016-17-opening-source-selection",
        "season": copy.deepcopy(intake["season"]),
        "inputs": {
            "source_intake_sha256": selection_v1._sha256_document(intake),
            "source_capture_sha256": intake["source_capture_sha256"],
        },
        "selections": [{
            "id": "example-opening-source",
            "canonical_selector": canonical,
            "selected_selector": selected,
            "basis": selection_v1.SELECTION_BASIS,
        }],
    }
    selection, _audit = selection_v1.build_selection(source_intake=intake, manifest=manifest)
    lineup = {
        "schema_version": join.LINEUP_SCHEMA,
        "clubs": [{
            "source_selector": canonical,
            "first_league_fixture_date": "2016-08-06",
            "source_match_id": "fixture-1",
            "starting_xi": [{"source_player_id": "opening-player"}],
        }],
    }
    reconciliation = {
        "schema_version": join.RECONCILIATION_SCHEMA,
        "sources": {
            "source_capture_sha256": intake["source_capture_sha256"],
            "lineup_capture_sha256": "lineup",
        },
        "clubs": [{
            "source_selector": canonical,
            "starting_xi": [{"source_player_id": "opening-player", "source_name": "Opening Player"}],
        }],
    }
    additions = {
        "schema_version": join.ADDITIONS_SCHEMA,
        "sources": {"lineup_capture_sha256": "lineup", "reconciliation_sha256": "reconciliation"},
        "rows": [],
    }
    return intake, selection, lineup, reconciliation, additions


def test_selection_bound_join_uses_effective_rows_and_suppresses_alias() -> None:
    intake, selection, lineup, reconciliation, additions = _selection_fixture()
    result = join.materialise(
        source_intake=intake,
        source_intake_sha256=join._sha(intake),
        lineup=lineup,
        lineup_sha256="lineup",
        reconciliation=reconciliation,
        reconciliation_sha256="reconciliation",
        additions=additions,
        additions_sha256="additions",
        source_club_selection=selection,
        source_club_selection_sha256=join._sha(selection),
    )

    assert result["sources"]["source_club_selection_sha256"] == join._sha(selection)
    assert [row["selector"]["club_name"] for row in result["source_clubs"]] == ["Example Town"]
    assert result["source_clubs"][0]["players"][0]["facts"]["name"] == "Opening Player"
    join.validate_selection_bound_preallocation(
        preallocation=result, source_intake=intake, source_club_selection=selection,
    )


def test_selection_bound_join_rejects_stale_selection_hash_and_tampered_selected_player() -> None:
    intake, selection, lineup, reconciliation, additions = _selection_fixture()
    with pytest.raises(join.PreallocationError, match="does not bind"):
        join.materialise(
            source_intake=intake, source_intake_sha256=join._sha(intake),
            lineup=lineup, lineup_sha256="lineup",
            reconciliation=reconciliation, reconciliation_sha256="reconciliation",
            additions=additions, additions_sha256="additions",
            source_club_selection=selection, source_club_selection_sha256="f" * 64,
        )

    result = join.materialise(
        source_intake=intake, source_intake_sha256=join._sha(intake),
        lineup=lineup, lineup_sha256="lineup",
        reconciliation=reconciliation, reconciliation_sha256="reconciliation",
        additions=additions, additions_sha256="additions",
        source_club_selection=selection, source_club_selection_sha256=join._sha(selection),
    )
    result["source_clubs"][0]["players"][0]["facts"]["name"] = "Unsourced edit"
    with pytest.raises(join.PreallocationError, match="does not exactly match"):
        join.validate_selection_bound_preallocation(
            preallocation=result, source_intake=intake, source_club_selection=selection,
        )


def _provider_id_join_inputs():
    selector = {'country_catalog': 'brazil', 'competition_catalog': 'seriea', 'club_name': 'Example', 'source_path': 'x', 'source_sha256': 'a'*64}
    ids = ['11','12'] + [str(i) for i in range(20,30)]
    players = [{'source_row_index': n, 'source_row_sha256': f'{n+1:064x}', 'facts': {
        'name': 'Emerson' if pid in ('11','12') else 'Player '+pid,
        'birth_date': None, 'source_identity': {'provider':'transfermarkt','player_id':pid}}}
        for n,pid in enumerate(ids)]
    starters = [{'source_player_id':pid, 'source_url':f'https://www.transfermarkt.com/person/profil/spieler/{pid}'}
                for pid in ['12']+ids[2:]]
    intake = {'schema_version':join.INTAKE_SCHEMA,'season':{'label':'2017/18'},'source_capture_sha256':'b'*64,
              'source_clubs':[{'selector':selector,'competition_name':'League','players':players}]}
    lineup = {'schema_version':join.LINEUP_SCHEMA,'clubs':[{'source_selector':selector,'first_league_fixture_date':'2017-05-14','source_match_id':'9','starting_xi':starters}]}
    reconciliation = {'schema_version':join.RECONCILIATION_SCHEMA,'sources':{'source_capture_sha256':'b'*64,'lineup_capture_sha256':'LINEUP'},
                      'clubs':[{'source_selector':selector,'starting_xi':[{'source_player_id':'12','source_name':'Emerson','source_birth_date':None}]}]}
    additions = {'schema_version':join.ADDITIONS_SCHEMA,'sources':{'lineup_capture_sha256':'LINEUP','reconciliation_sha256':'RECON'},'rows':[]}
    return intake,lineup,reconciliation,additions


def _provider_join(values):
    intake,lineup,reconciliation,additions=values
    return join.materialise(source_intake=intake,source_intake_sha256='INTAKE',lineup=lineup,lineup_sha256='LINEUP',
        reconciliation=reconciliation,reconciliation_sha256='RECON',additions=additions,additions_sha256='ADDITIONS')


def test_original_profile_id_selects_the_right_same_name_without_a_birthday():
    result=_provider_join(_provider_id_join_inputs())
    club=result['source_clubs'][0]
    assert club['opening_xi_complete']
    assert club['players'][0]['facts']['source_identity']['player_id']=='12'
    assert club['players'][-1]['facts']['source_identity']['player_id']=='11'


def test_same_name_cannot_override_a_conflicting_literal_provider_id():
    values=_provider_id_join_inputs()
    values[0]['source_clubs'][0]['players']=values[0]['source_clubs'][0]['players'][1:]
    values[1]['clubs'][0]['starting_xi'][0].update(source_player_id='99',source_url='https://www.transfermarkt.com/person/profil/spieler/99')
    values[2]['clubs'][0]['starting_xi'][0]['source_player_id']='99'
    result=_provider_join(values)
    assert not result['source_clubs'][0]['opening_xi_complete']
    assert result['source_clubs'][0]['opening_xi_blockers'][0]['source_player_id']=='99'


def test_unqualified_number_is_not_a_provider_identity_bridge():
    values=_provider_id_join_inputs()
    values[1]['clubs'][0]['starting_xi'][0].pop('source_url')
    result=_provider_join(values)
    assert not result['source_clubs'][0]['opening_xi_complete']


def test_original_profile_url_and_id_must_agree():
    values=_provider_id_join_inputs()
    values[1]['clubs'][0]['starting_xi'][0]['source_url']='https://www.transfermarkt.com/person/profil/spieler/99'
    with pytest.raises(join.PreallocationError,match='URL and player ID disagree'):
        _provider_join(values)


def test_exact_profile_id_cannot_be_inferred_from_unidentified_namesake():
    values = _provider_id_join_inputs()
    players = values[0]['source_clubs'][0]['players']
    players[:] = players[1:]
    players[0]['facts'].pop('source_identity')
    values[1]['clubs'][0]['starting_xi'][0].update(
        source_player_id='99', source_url='https://www.transfermarkt.com/person/profil/spieler/99')
    values[2]['clubs'][0]['starting_xi'][0]['source_player_id'] = '99'
    result = _provider_join(values)
    assert not result['source_clubs'][0]['opening_xi_complete']
    assert result['source_clubs'][0]['opening_xi_blockers'][0]['source_player_id'] == '99'
