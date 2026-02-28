import json
import subprocess

import pytest

import app.roster_reconcile as roster_reconcile


def test_parse_listing_pdf_parses_standard_page(monkeypatch):
    sample_text = "\n".join(
        [
            "LISTING OF ALL PALYERS",
            "NAME",
            "TEAM",
            "Thorne",
            "Davis K.",
            "Stoke C.",
            "Blackpool",
            "Data Base - Premier Manager 99",
        ]
    )

    monkeypatch.setattr(
        subprocess,
        "check_output",
        lambda cmd: sample_text.encode("utf-8"),
    )

    rows = roster_reconcile.parse_listing_pdf("/tmp/fake.pdf")

    assert rows == [
        roster_reconcile.PdfRosterRow(page=1, name_label="Thorne", team_label="Stoke C."),
        roster_reconcile.PdfRosterRow(page=1, name_label="Davis K.", team_label="Blackpool"),
    ]


def test_parse_listing_pdf_raises_on_odd_data_lines(monkeypatch):
    sample_text = "\n".join(
        [
            "LISTING OF ALL PALYERS",
            "NAME",
            "TEAM",
            "Thorne",
            "Davis K.",
            "Stoke C.",
            "Data Base - Premier Manager 99",
        ]
    )

    monkeypatch.setattr(
        subprocess,
        "check_output",
        lambda cmd: sample_text.encode("utf-8"),
    )

    with pytest.raises(RuntimeError, match="odd data line count"):
        roster_reconcile.parse_listing_pdf("/tmp/fake.pdf")


def test_team_label_normalization_and_pdf_name_label_parsing():
    assert roster_reconcile._canonical_team_query("Stoke C.") == "Stoke City"
    assert roster_reconcile._canonical_team_query("Q.P.R.") == "Queens Park Rangers"
    assert roster_reconcile._canonical_team_query("WBA") == "West Bromwich Albion"
    assert roster_reconcile._canonical_team_query("Leeds Utd.") == "Leeds United"
    assert roster_reconcile._canonical_team_query("Manchester Utd.") == "Manchester United"
    assert roster_reconcile._canonical_team_query("Newcastle Utd.") == "Newcastle United"
    assert roster_reconcile._canonical_team_query("Tottenham H.") == "Tottenham Hotspur"
    assert roster_reconcile._canonical_team_query("Blackburn R.") == "Blackburn Rovers"
    assert roster_reconcile._canonical_team_query("Brighton & HA") == "Brighton and Hove Albion"
    assert roster_reconcile._canonical_team_query("Southend Utd.") == "Southend United"
    assert roster_reconcile._canonical_team_query("Rotherham U.") == "Rotherham United"
    assert roster_reconcile._canonical_team_query("Leyton O.") == "Leyton Orient"
    assert roster_reconcile._canonical_team_query("Plymouth Arg.") == "Plymouth Argyle"
    assert roster_reconcile._canonical_team_query("Unknown Team") == "Unknown Team"

    davis = roster_reconcile._parse_pdf_name_label("Davis K.")
    assert davis["base"] == "Davis"
    assert davis["last_token"] == "DAVIS"
    assert davis["initial_hint"] == "K"

    johnson = roster_reconcile._parse_pdf_name_label("Johnson M")
    assert johnson["base"] == "Johnson"
    assert johnson["last_token"] == "JOHNSON"
    assert johnson["initial_hint"] == "M"

    right = roster_reconcile._parse_pdf_name_label("D. Wright")
    assert right["base"] == "Wright"
    assert right["last_token"] == "WRIGHT"
    assert right["initial_hint"] == "D"

    multiword = roster_reconcile._parse_pdf_name_label("Van der Kwaak")
    assert multiword["base"] == "Van der Kwaak"
    assert multiword["last_token"] == "KWAAK"
    assert multiword["initial_hint"] is None


def test_match_pdf_label_to_candidate_normalizes_punctuation_variants():
    pdf_info = roster_reconcile._parse_pdf_name_label("D´Jaffo")
    candidate_meta = {
        "name_upper": "JEAN D'JAFFO",
        "name_match_upper": "JEAN D'JAFFO",
        "last_token": "D'JAFFO",
        "last_token_match": "D'JAFFO",
        "given_initial": "J",
    }
    assert roster_reconcile._match_pdf_label_to_candidate(pdf_info, candidate_meta) is True


def test_detail_status_flags_low_conf_isolated_default():
    low = roster_reconcile.CandidateScore(
        candidate_name="Les ROBINSON",
        candidate_offset=0x1234,
        candidate_source="scanner (marker)",
        default_score=0.24,
        default_band="low",
    )
    high = roster_reconcile.CandidateScore(
        candidate_name="Peter THORNE",
        candidate_offset=0x2000,
        candidate_source="entry (strict)",
        default_score=0.87,
        default_band="high",
    )
    assert roster_reconcile._detail_status("isolated_default", low) == "isolated_default_low_conf"
    assert roster_reconcile._detail_status("isolated_default", high) == "isolated_default_high_conf"
    assert roster_reconcile._detail_status("isolated_wide_only", None) == "isolated_wide_provisional"
    assert roster_reconcile._detail_status("ambiguous_default", None) == "ambiguous_review"


def test_load_name_hints_csv_and_json_and_row_lookup(tmp_path):
    csv_path = tmp_path / "hints.csv"
    csv_path.write_text(
        "team_label,surname,first_name,initial\n"
        "Stoke C.,Robinson,Phil,P\n",
        encoding="utf-8",
    )
    json_path = tmp_path / "hints.json"
    json_path.write_text(
        json.dumps(
            {
                "hints": [
                    {"team_query": "Queens Park Rangers", "surname": "Harper", "first_name": "Richard"},
                ]
            }
        ),
        encoding="utf-8",
    )

    csv_hints = roster_reconcile.load_name_hints(str(csv_path))
    json_hints = roster_reconcile.load_name_hints(str(json_path))
    assert len(csv_hints) == 1
    assert csv_hints[0].first_name == "Phil"
    assert csv_hints[0].initial == "P"
    assert len(json_hints) == 1
    assert json_hints[0].team_query == "Queens Park Rangers"

    idx = roster_reconcile._build_name_hint_index(csv_hints)
    row = roster_reconcile.PdfRosterRow(page=1, name_label="Robinson", team_label="Stoke C.")
    parsed = roster_reconcile._parse_pdf_name_label("Robinson")
    row_hints = roster_reconcile._name_hints_for_row(row, "Stoke City", parsed, idx)
    assert len(row_hints) == 1
    assert row_hints[0].first_name == "Phil"


def test_apply_name_hints_to_candidate_score_penalizes_mismatch_and_boosts_match():
    hint = roster_reconcile.NameHint(team_label="Stoke C.", team_query="Stoke City", surname="Robinson", first_name="Phil", initial="P")
    les = roster_reconcile.CandidateScore(
        candidate_name="Les ROBINSON",
        candidate_offset=0x1111,
        candidate_source="scanner (marker)",
        default_score=0.2461,
        default_band="low",
        wide_score=0.6177,
        wide_band="medium",
    )
    phil = roster_reconcile.CandidateScore(
        candidate_name="Phil ROBINSON",
        candidate_offset=0x2222,
        candidate_source="scanner (marker)",
        default_score=0.0,
        default_band="none",
        wide_score=0.4710,
        wide_band="low",
    )

    roster_reconcile._apply_name_hints_to_candidate_score(
        les,
        {"given_name_match": "LES", "given_initial": "L"},
        [hint],
    )
    roster_reconcile._apply_name_hints_to_candidate_score(
        phil,
        {"given_name_match": "PHILIP", "given_initial": "P"},
        [hint],
    )

    assert les.default_score == 0.0
    assert les.default_band == "none"
    assert les.name_hint_match.startswith("first_name_mismatch")
    assert phil.default_score == 0.0  # name hints do not create club evidence
    assert phil.wide_score > 0.47
    assert "first_name_prefix" in phil.name_hint_match


def test_write_reconcile_outputs_writes_json_and_csv(tmp_path):
    result = roster_reconcile.ReconcileRunSummary(
        schema_version="v1",
        pdf_path="/tmp/fake.pdf",
        player_file="DBDAT/JUG98030.FDI",
        name_hints_path=None,
        name_hints_loaded=0,
        pdf_rows=1,
        teams=1,
        team_counts={"Stoke C.": 1},
        player_scan_counts={"heuristic_valid": 1, "heuristic_uncertain": 0, "strict_valid": 1, "strict_uncertain": 0, "strict_offsets": 1},
        summary_counts={"isolated_default": 1},
        summary_counts_detail={"isolated_default_high_conf": 1},
        team_summaries=[
            roster_reconcile.TeamReconcileSummary(
                team_label="Stoke C.",
                team_query="Stoke City",
                roster_rows=1,
                isolated_default=1,
                any_default_match=1,
                any_wide_match=1,
                status_counts={"isolated_default": 1},
                status_detail_counts={"isolated_default_high_conf": 1},
                strict_group_bytes={"0x4B": 1},
            )
        ],
        group_byte_team_hints={"0x4B": {"Stoke C.": 1}},
        rows=[
            roster_reconcile.ReconcileRowResult(
                page=1,
                team_label="Stoke C.",
                team_query="Stoke City",
                pdf_name_label="Thorne",
                pdf_base_name="Thorne",
                pdf_initial_hint="",
                candidate_count=1,
                default_hit_count=1,
                wide_hit_count=1,
                name_hint_count=0,
                name_hint_preview="",
                status="isolated_default",
                status_detail="isolated_default_high_conf",
                best_candidate_name="Peter THORNE",
                best_candidate_offset_hex="0x00000100",
                best_candidate_source="entry (strict)",
                best_default_score=0.9,
                best_default_band="high",
                best_default_mentions="Stoke City",
                best_wide_score=0.9,
                best_wide_band="high",
                best_wide_mentions="Stoke City",
                best_strict_group_byte_hex="0x4B",
                best_name_hint_match="none",
                best_name_hint_bonus=0.0,
                candidate_preview="Peter THORNE[high 0.900/high 0.900]",
            )
        ],
    )

    json_path = tmp_path / "rows.json"
    csv_path = tmp_path / "rows.csv"
    team_csv_path = tmp_path / "teams.csv"

    roster_reconcile.write_reconcile_outputs(
        result,
        json_output=str(json_path),
        csv_output=str(csv_path),
        team_summary_csv=str(team_csv_path),
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "v1"
    assert payload["pdf_rows"] == 1
    assert payload["rows"][0]["best_candidate_name"] == "Peter THORNE"

    csv_text = csv_path.read_text(encoding="utf-8")
    assert "pdf_name_label" in csv_text
    assert "Peter THORNE" in csv_text

    team_csv_text = team_csv_path.read_text(encoding="utf-8")
    assert "isolated_default" in team_csv_text
    assert "Stoke City" in team_csv_text


def test_print_reconcile_run_summary_includes_schema_and_hint_info(capsys):
    result = roster_reconcile.ReconcileRunSummary(
        schema_version="v1",
        pdf_path="/tmp/fake.pdf",
        player_file="DBDAT/JUG98030.FDI",
        name_hints_path="/tmp/hints.csv",
        name_hints_loaded=1,
        pdf_rows=1,
        teams=1,
        team_counts={"Stoke C.": 1},
        player_scan_counts={},
        summary_counts={"isolated_default": 1},
        summary_counts_detail={"isolated_default_high_conf": 1},
        team_summaries=[
            roster_reconcile.TeamReconcileSummary(
                team_label="Stoke C.",
                team_query="Stoke City",
                roster_rows=1,
                isolated_default=1,
                any_default_match=1,
                any_wide_match=1,
                status_counts={"isolated_default": 1},
                status_detail_counts={"isolated_default_high_conf": 1},
                strict_group_bytes={},
            )
        ],
        group_byte_team_hints={},
        rows=[],
    )

    roster_reconcile.print_reconcile_run_summary(result, top_n=5)
    out = capsys.readouterr().out
    assert "Schema: v1" in out
    assert "Name hints: 1 loaded (/tmp/hints.csv)" in out
    assert "Rows: 1 across 1 teams" in out
