from argparse import Namespace
from types import SimpleNamespace

import pytest

import app.cli as cli
from app.main_dat import PM99MainDatFile, PM99MainDatPrefix, PM99PackedDate, load_main_dat


class FakeFDIFile:
    instances = []

    def __init__(self, file_path):
        self.file_path = file_path
        self.modified_records = {}
        self._records = [
            (0x10, SimpleNamespace(team_id=123, name="Old Name", set_name=self._set_name, name_dirty=False)),
        ]
        self.saved = False
        self.__class__.instances.append(self)

    def _set_name(self, new_name):
        self._records[0][1].name = new_name
        self._records[0][1].name_dirty = True

    def load(self):
        return None

    def list_players(self, limit=None):
        return self._records[:limit] if limit else self._records

    def save(self):
        self.saved = True


def test_cmd_search_uses_offset_aware_entries(monkeypatch, capsys):
    entries = [
        SimpleNamespace(offset=0x10, source="scanner", record=SimpleNamespace(name="Alex Smith", team_id=7, squad_number=1)),
        SimpleNamespace(offset=0x20, source="scanner", record=SimpleNamespace(name="Brian Jones", team_id=8, squad_number=2)),
    ]
    monkeypatch.setattr(cli, "gather_player_records", lambda _: (entries, []))

    cli.cmd_search(Namespace(file="dummy.fdi", name="alex", include_uncertain=False, json=False))
    out = capsys.readouterr().out
    assert "0x00000010" in out
    assert "Alex Smith" in out


def test_cmd_search_strict_uses_strict_gatherer(monkeypatch, capsys):
    entries = [
        SimpleNamespace(offset=0x44, source="entry (strict)", record=SimpleNamespace(name="Peter THORNE", team_id=12, squad_number=9)),
    ]
    monkeypatch.setattr(cli, "gather_player_records", lambda _: ([], []))
    monkeypatch.setattr(cli, "gather_player_records_strict", lambda *_args, **_kwargs: (entries, []))

    cli.cmd_search(
        Namespace(
            file="dummy.fdi",
            name="thorne",
            include_uncertain=False,
            json=False,
            strict=True,
            require_team_id=False,
        )
    )
    out = capsys.readouterr().out
    assert "0x00000044" in out
    assert "entry (strict)" in out


def test_cmd_team_search_matches_canonical_alias(monkeypatch, capsys):
    team_entries = [
        SimpleNamespace(
            offset=0x10,
            source="loader",
            record=SimpleNamespace(
                team_id=3937,
                name="Milan",
                full_club_name="Associazione Calcio Milan",
            ),
        ),
        SimpleNamespace(
            offset=0x20,
            source="loader",
            record=SimpleNamespace(
                team_id=1111,
                name="Inter Cardiff",
                full_club_name="Inter Cardiff",
            ),
        ),
    ]
    monkeypatch.setattr(cli, "gather_team_records", lambda _path: (team_entries, []))

    cli.cmd_team_search(
        Namespace(
            file="EQ98030.FDI",
            name="AC Milan",
            include_uncertain=False,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "Milan" in out
    assert "Inter Cardiff" not in out


def test_cmd_rename_stages_by_offset_not_id(monkeypatch, capsys):
    FakeFDIFile.instances = []
    monkeypatch.setattr(cli, "FDIFile", FakeFDIFile)

    cli.cmd_rename(Namespace(file="dummy.fdi", id=123, name="New Name", offset=None))
    out = capsys.readouterr().out
    inst = FakeFDIFile.instances[0]
    assert inst.saved is True
    assert 0x10 in inst.modified_records
    assert 123 not in inst.modified_records
    assert "0x00000010" in out


def test_build_club_index_rows_aggregates_and_ranks():
    strict_hits = [
        {
            "name": "Peter THORNE",
            "offset": 0x100,
            "team_id": 0,
            "target_mentions": ["Stoke City (97)", "Stoke City"],
            "association_type": "strict_subrecord_context",
            "confidence_score": 0.88,
            "confidence_band": "high",
        },
    ]
    heuristic_hits = [
        {
            "name": "Peter THORNE",
            "offset": 0x200,
            "team_id": 0,
            "target_mentions": ["Stoke City"],
            "association_type": "heuristic_blob_context",
            "confidence_score": 0.41,
            "confidence_band": "low",
        },
        {
            "name": "Someone Else",
            "offset": 0x300,
            "team_id": 12,
            "target_mentions": ["Stoke City"],
            "association_type": "heuristic_blob_context",
            "confidence_score": 0.65,
            "confidence_band": "medium",
        },
    ]

    rows = cli._build_club_index_rows("Stoke City", strict_hits, heuristic_hits)

    assert [row["player_name"] for row in rows] == ["Peter THORNE", "Someone Else"]
    peter = rows[0]
    assert peter["club_normalized"] == "Stoke City"
    assert peter["evidence_count"] == 2
    assert peter["strict_evidence_count"] == 1
    assert peter["heuristic_evidence_count"] == 1
    assert peter["best_confidence_band"] == "high"
    assert peter["mentions"] == ["Stoke City"]
    assert peter["offsets"] == [0x100, 0x200]


def test_resolve_club_query_to_teams_matches_exact(monkeypatch):
    team_entries = [
        SimpleNamespace(
            offset=0x10,
            source="loader",
            record=SimpleNamespace(team_id=77, name="Stoke City"),
        ),
        SimpleNamespace(
            offset=0x20,
            source="loader",
            record=SimpleNamespace(team_id=88, name="Swindon Town"),
        ),
    ]
    monkeypatch.setattr(cli, "gather_team_records", lambda _path: (team_entries, []))

    rows = cli._resolve_club_query_to_teams("Stoke City (97)", "EQ98030.FDI")

    assert len(rows) == 1
    assert rows[0]["team_id"] == 77
    assert rows[0]["match_kind"] == "exact"
    assert rows[0]["match_score"] == 1.0


def test_export_club_investigate_csv_and_json(tmp_path):
    payload = {
        "club_index": [
            {
                "club_query": "Stoke City",
                "club_normalized": "Stoke City",
                "player_name": "Peter THORNE",
                "best_confidence_score": 0.42,
                "best_confidence_band": "low",
                "best_association_type": "heuristic_blob_context",
                "best_offset": 0x1C1DBC,
                "evidence_count": 1,
                "strict_evidence_count": 0,
                "heuristic_evidence_count": 1,
                "team_ids": [],
                "mentions": ["Stoke City"],
            }
        ]
    }

    csv_path = tmp_path / "stoke.csv"
    json_path = tmp_path / "stoke.json"

    written_csv = cli._export_club_investigate(payload, str(csv_path))
    written_json = cli._export_club_investigate(payload, str(json_path))

    assert written_csv == csv_path
    assert written_json == json_path
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "player_name" in csv_text
    assert "Peter THORNE" in csv_text
    assert "0x001C1DBC" in csv_text
    json_text = json_path.read_text(encoding="utf-8")
    assert "Peter THORNE" in json_text


def test_cmd_main_dat_inspect_emits_json(tmp_path, capsys):
    file_path = tmp_path / "main.dat"
    payload = PM99MainDatFile(
        prefix=PM99MainDatPrefix(
            header_version=0x1E,
            format_version=0x0C,
            primary_label="Slot A",
            secondary_label="Profile A",
            save_date=PM99PackedDate(day=27, month=2, year=2026),
            hour=18,
            minute=5,
            flag_bytes=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
            scalar_byte=11,
        ),
        opaque_tail=b"\xAA\xBB",
    )
    file_path.write_bytes(payload.to_bytes())

    cli.cmd_main_dat_inspect(Namespace(file=str(file_path), json=True))

    out = capsys.readouterr().out
    assert '"header_version": 30' in out
    assert '"header_matches_expected": true' in out
    assert '"opaque_tail_size": 2' in out


def test_cmd_main_dat_edit_writes_copy_and_preserves_tail(tmp_path, capsys):
    file_path = tmp_path / "main.dat"
    payload = PM99MainDatFile(
        prefix=PM99MainDatPrefix(
            header_version=0x1E,
            format_version=0x0C,
            primary_label="Slot A",
            secondary_label="Profile A",
            save_date=PM99PackedDate(day=27, month=2, year=2026),
            hour=18,
            minute=5,
            flag_bytes=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
            scalar_byte=11,
        ),
        opaque_tail=b"\xAA\xBB\xCC\xDD",
    )
    file_path.write_bytes(payload.to_bytes())

    cli.cmd_main_dat_edit(
        Namespace(
            file=str(file_path),
            primary_label="Edited Slot",
            secondary_label=None,
            day=None,
            month=None,
            year=None,
            hour=21,
            minute=9,
            scalar_byte=12,
            flag_byte=["0=7", "9=0xEE"],
            output_file=None,
            in_place=False,
            no_backup=False,
            json=False,
        )
    )

    out = capsys.readouterr().out
    edited_path = tmp_path / "main.edited.dat"
    assert "Changed fields:" in out
    assert edited_path.exists()

    edited = load_main_dat(edited_path)
    original = load_main_dat(file_path)
    assert edited.prefix.primary_label == "Edited Slot"
    assert edited.prefix.hour == 21
    assert edited.prefix.minute == 9
    assert edited.prefix.scalar_byte == 12
    assert edited.prefix.flag_bytes[0] == 7
    assert edited.prefix.flag_bytes[9] == 0xEE
    assert edited.opaque_tail == original.opaque_tail


def test_club_query_aliases_include_root_and_abbrev():
    aliases = cli._club_query_aliases("Stoke City")
    assert "Stoke City" in aliases
    assert "Stoke" in aliases
    assert any(a in aliases for a in ("Stoke C.", "Stoke C"))

    qpr_aliases = cli._club_query_aliases("Queens Park Rangers")
    assert "QPR" in qpr_aliases
    assert "Q.P.R." in qpr_aliases

    wba_aliases = cli._club_query_aliases("West Bromwich Albion")
    assert "WBA" in wba_aliases


def test_extract_query_mentions_finds_abbrev_and_root():
    text = "Some text ... Stoke C. (98) ... later Stoke ... end"
    center = text.index("later")
    aliases = cli._club_query_aliases("Stoke City")
    mentions = cli._extract_query_mentions(text, center, aliases, window=200, limit=10)
    matched_texts = [m["text"] for m in mentions]
    assert any("Stoke C" in t for t in matched_texts)
    assert any(t.lower() == "stoke" for t in matched_texts)


def test_cmd_roster_reconcile_pdf_delegates_to_shared_module(monkeypatch):
    import app.roster_reconcile as roster_reconcile

    calls = {}
    fake_result = SimpleNamespace(pdf_rows=2, teams=1, summary_counts={"isolated_default": 1}, team_summaries=[])

    def fake_reconcile_pdf_rosters(**kwargs):
        calls["reconcile"] = kwargs
        return fake_result

    def fake_write_reconcile_outputs(result, **kwargs):
        calls["write"] = {"result": result, **kwargs}

    def fake_print_reconcile_run_summary(result, top_n=10):
        calls["print"] = {"result": result, "top_n": top_n}

    monkeypatch.setattr(roster_reconcile, "reconcile_pdf_rosters", fake_reconcile_pdf_rosters)
    monkeypatch.setattr(roster_reconcile, "write_reconcile_outputs", fake_write_reconcile_outputs)
    monkeypatch.setattr(roster_reconcile, "print_reconcile_run_summary", fake_print_reconcile_run_summary)

    cli.cmd_roster_reconcile_pdf(
        Namespace(
            pdf="/tmp/test.pdf",
            player_file="DBDAT/JUG98030.FDI",
            default_window=800,
            wide_window=10000,
            json_output="/tmp/out.json",
            csv_output="/tmp/out.csv",
            team_summary_csv="/tmp/teams.csv",
            team="Stoke City",
            name_hints=None,
        )
    )

    assert calls["reconcile"] == {
        "pdf_path": "/tmp/test.pdf",
        "player_file": "DBDAT/JUG98030.FDI",
        "default_window": 800,
        "wide_window": 10000,
        "team_filter": "Stoke City",
        "name_hints_path": None,
    }
    assert calls["write"]["result"] is fake_result
    assert calls["write"]["json_output"] == "/tmp/out.json"
    assert calls["write"]["csv_output"] == "/tmp/out.csv"
    assert calls["write"]["team_summary_csv"] == "/tmp/teams.csv"
    assert calls["print"]["result"] is fake_result


def test_cmd_player_skill_patch_delegates_to_dd6361_probe(monkeypatch, capsys, tmp_path):
    calls = {}

    def fake_parse_assignments(items):
        calls["parse"] = list(items)
        return {"speed": 91, "passing": 91}

    def fake_patch_action(**kwargs):
        calls["patch"] = kwargs
        return SimpleNamespace(
            resolved_bio_name="David Robert BECKHAM",
            output_file=kwargs["output_file"],
            backup_path=None,
            updates_requested={"speed": 91, "passing": 91},
            mapped10_order=["speed", "stamina", "passing"],
            mapped10_before={"speed": 90, "stamina": 85, "passing": 90},
            mapped10_after={"speed": 91, "stamina": 85, "passing": 91},
            verification_all_requested_fields_match=True,
            touched_entry_offsets=[0x1234, 0x5678],
            raw_payload={"ok": True},
        )

    monkeypatch.setattr(cli, "parse_player_skill_patch_assignments", fake_parse_assignments)
    monkeypatch.setattr(cli, "patch_player_visible_skills_dd6361", fake_patch_action)

    output_file = tmp_path / "beckham_patched.fdi"
    report_file = tmp_path / "beckham_patched.json"
    cli.cmd_player_skill_patch(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            name="Beckham",
            set_args=["speed=91", "passing=91"],
            output_file=str(output_file),
            in_place=False,
            no_backup=False,
            json_output=str(report_file),
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert calls["parse"] == ["speed=91", "passing=91"]
    assert calls["patch"] == {
        "file_path": "DBDAT/JUG98030.FDI",
        "player_name": "Beckham",
        "updates": {"speed": 91, "passing": 91},
        "output_file": str(output_file),
        "in_place": False,
        "create_backup_before_write": False,
        "json_output": str(report_file),
    }
    assert "David Robert BECKHAM" in out
    assert "speed: 90 -> 91" in out
    assert "passing: 90 -> 91" in out
    assert "Verification: ok" in out


def test_cmd_player_skill_patch_in_place_enables_backup(monkeypatch, capsys):
    calls = {}

    monkeypatch.setattr(cli, "parse_player_skill_patch_assignments", lambda items: {"speed": 91})

    def fake_patch_action(**kwargs):
        calls["patch"] = kwargs
        return SimpleNamespace(
            resolved_bio_name="David Robert BECKHAM",
            output_file=kwargs["file_path"],
            backup_path=str(kwargs["file_path"]) + ".backup",
            updates_requested={"speed": 91},
            mapped10_order=["speed"],
            mapped10_before={"speed": 90},
            mapped10_after={"speed": 91},
            verification_all_requested_fields_match=True,
            touched_entry_offsets=[0x1234],
            raw_payload={"ok": True},
        )

    monkeypatch.setattr(cli, "patch_player_visible_skills_dd6361", fake_patch_action)

    cli.cmd_player_skill_patch(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            name="Beckham",
            set_args=["speed=91"],
            output_file=None,
            in_place=True,
            no_backup=False,
            json_output=None,
            json=False,
        )
    )

    assert calls["patch"]["output_file"] is None
    assert calls["patch"]["in_place"] is True
    assert calls["patch"]["create_backup_before_write"] is True
    out = capsys.readouterr().out
    assert "Backup:" in out


def test_cmd_player_skill_patch_rejects_no_backup_without_in_place(capsys):
    with pytest.raises(SystemExit):
        cli.cmd_player_skill_patch(
            Namespace(
                file="DBDAT/JUG98030.FDI",
                name="Beckham",
                set_args=["speed=91"],
                output_file=None,
                in_place=False,
                no_backup=True,
                json_output=None,
                json=False,
            )
        )
    err = capsys.readouterr().err
    assert "--no-backup only applies with --in-place" in err


def test_cmd_team_roster_extract_delegates_to_shared_action(monkeypatch, capsys, tmp_path):
    calls = {}

    fake_payload = {"ok": True, "requested_team_results": [{"team_name": "Stoke C"}]}
    fake_result = SimpleNamespace(
        team_count=532,
        dd6361_pid_name_count=2009,
        same_entry_overlap_coverage={
            "status_counts": {
                "perfect_same_entry_run_overlap": 487,
                "moderate_same_entry_overlap": 8,
            },
            "strong_or_better_count": 487,
            "strong_or_better_ratio": 0.9154,
        },
        requested_team_results=[
            {
                "team_name": "Stoke C",
                "full_club_name": "Stoke City",
                "team_id": 3425,
                "team_offset": 0x29802,
                "status": "perfect_same_entry_run_overlap",
                "containing_entry": {"entry_offset": 0x2694D, "length": 34048},
                "top_run_match": {
                    "run_index": 6,
                    "overlap_hits_in_team_raw": 19,
                    "non_empty_row_count": 19,
                    "second_best_overlap_hits": 1,
                    "rows": [
                        {
                            "pid_candidate": 15578,
                            "dd6361_name": "Graham KAVANAGH",
                            "is_empty_slot": False,
                            "xor_pid_found_in_team_raw": True,
                        },
                        {
                            "pid_candidate": 32960,
                            "dd6361_name": "Scott James TAYLOR",
                            "is_empty_slot": False,
                            "xor_pid_found_in_team_raw": True,
                        },
                    ],
                },
            }
        ],
        raw_payload=fake_payload,
    )

    def fake_extract(**kwargs):
        calls["extract"] = kwargs
        return fake_result

    monkeypatch.setattr(cli, "extract_team_rosters_eq_same_entry_overlap", fake_extract)

    report_file = tmp_path / "team_roster_report.json"
    cli.cmd_team_roster_extract(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=["Stoke"],
            top_examples=10,
            row_limit=10,
            include_fallbacks=False,
            json_output=str(report_file),
            json=False,
        )
    )

    assert calls["extract"] == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "team_queries": ["Stoke"],
        "top_examples": 10,
        "include_fallbacks": False,
        "json_output": str(report_file),
    }
    out = capsys.readouterr().out
    assert "Same-entry EQ roster overlap coverage" in out
    assert "Stoke C (Stoke City)" in out
    assert "status=perfect_same_entry_run_overlap" in out
    assert "Graham KAVANAGH" in out
    assert "Report:" in out


def test_cmd_team_roster_extract_json_passthrough(monkeypatch, capsys):
    fake_result = SimpleNamespace(
        team_count=532,
        dd6361_pid_name_count=2009,
        same_entry_overlap_coverage={},
        requested_team_results=[],
        raw_payload={"hello": "world"},
    )
    monkeypatch.setattr(cli, "extract_team_rosters_eq_same_entry_overlap", lambda **kwargs: fake_result)

    cli.cmd_team_roster_extract(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=[],
            top_examples=15,
            row_limit=25,
            include_fallbacks=False,
            json_output=None,
            json=True,
        )
    )

    out = capsys.readouterr().out
    assert '"hello": "world"' in out


def test_team_query_matches_canonical_alias_without_broad_false_positive():
    from app.editor_helpers import team_query_matches

    assert team_query_matches(
        "Inter Milan",
        team_name="Inter",
        full_club_name="Internazionale Milano Football Club",
    )
    assert not team_query_matches(
        "Inter Milan",
        team_name="Inter Cardiff",
        full_club_name="Inter Cardiff",
    )


def test_cmd_team_roster_extract_prints_heuristic_candidate_warning(monkeypatch, capsys):
    fake_result = SimpleNamespace(
        team_count=532,
        dd6361_pid_name_count=2009,
        same_entry_overlap_coverage={
            "status_counts": {"perfect_same_entry_run_overlap": 487, "weak_same_entry_overlap": 23},
            "strong_or_better_count": 487,
            "strong_or_better_ratio": 0.9154,
        },
        final_extraction_coverage={
            "covered_count": 508,
            "covered_ratio": 0.955,
            "circular_shift_fallback_count": 21,
            "guarded_covered_count": 507,
            "guarded_covered_ratio": 0.953,
            "circular_shift_flagged_anchor_collision_count": 1,
        },
        requested_team_results=[
            {
                "team_name": "Middlesbrough",
                "full_club_name": "Middlesbrough Football Club",
                "team_id": 4449,
                "team_offset": 0x1AD03,
                "status": "weak_same_entry_overlap",
                "circular_shift_candidate_status": "order_fallback_circular_shift_same_entry_run",
                "heuristic_warnings": [
                    {
                        "type": "known_lineup_anchor_collision",
                        "dataset_key": "manutd",
                        "message": "Candidate run overlaps known lineup anchor 'manutd' (18/18 anchor PIDs)",
                    }
                ],
                "containing_entry": {"entry_offset": 0x15B3C, "length": 21504},
                "top_run_match": {
                    "run_index": 2,
                    "overlap_hits_in_team_raw": 1,
                    "non_empty_row_count": 27,
                    "second_best_overlap_hits": 1,
                    "rows": [],
                },
                "circular_shift_candidate_match": {
                    "run_index": 0,
                    "non_empty_row_count": 23,
                    "selection_method": "circular_shift_same_entry",
                    "rows": [],
                },
            }
        ],
        raw_payload={"ok": True},
    )
    monkeypatch.setattr(cli, "extract_team_rosters_eq_same_entry_overlap", lambda **kwargs: fake_result)

    cli.cmd_team_roster_extract(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=["Middlesbrough"],
            top_examples=15,
            row_limit=10,
            include_fallbacks=True,
            json_output=None,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "Heuristic candidate coverage" in out
    assert "Guarded heuristic coverage" in out
    assert "WARNING Candidate run overlaps known lineup anchor 'manutd'" in out
    assert "candidate_run index=0" in out


def test_cmd_team_roster_extract_default_authoritative_hides_fallback_sections(monkeypatch, capsys):
    fake_result = SimpleNamespace(
        team_count=532,
        dd6361_pid_name_count=2009,
        same_entry_overlap_coverage={
            "status_counts": {"perfect_same_entry_run_overlap": 487, "weak_same_entry_overlap": 23},
            "strong_or_better_count": 487,
            "strong_or_better_ratio": 0.9154,
        },
        final_extraction_coverage={
            "covered_count": 508,
            "covered_ratio": 0.955,
            "circular_shift_fallback_count": 21,
        },
        requested_team_results=[
            {
                "team_name": "Middlesbrough",
                "full_club_name": "Middlesbrough Football Club",
                "team_id": 4449,
                "team_offset": 0x1AD03,
                "status": "weak_same_entry_overlap",
                "circular_shift_candidate_status": "order_fallback_circular_shift_same_entry_run",
                "heuristic_warnings": [{"type": "known_lineup_anchor_collision", "message": "x"}],
                "containing_entry": {"entry_offset": 0x15B3C, "length": 21504},
                "top_run_match": {"run_index": 2, "overlap_hits_in_team_raw": 1, "non_empty_row_count": 27, "second_best_overlap_hits": 1, "rows": []},
                "circular_shift_candidate_match": {"run_index": 0, "non_empty_row_count": 23, "selection_method": "circular_shift_same_entry", "rows": []},
            }
        ],
        raw_payload={"ok": True},
    )
    monkeypatch.setattr(cli, "extract_team_rosters_eq_same_entry_overlap", lambda **kwargs: fake_result)

    cli.cmd_team_roster_extract(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=["Middlesbrough"],
            top_examples=15,
            row_limit=10,
            include_fallbacks=False,
            json_output=None,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "Selection mode: authoritative_only" in out
    assert "Heuristic candidate coverage" not in out
    assert "heuristic_candidate_status" not in out
    assert "candidate_run index=0" not in out


def test_cmd_team_roster_extract_prints_anchor_assisted_window(monkeypatch, capsys):
    fake_result = SimpleNamespace(
        team_count=532,
        dd6361_pid_name_count=2009,
        same_entry_overlap_coverage={},
        final_extraction_coverage={},
        requested_team_results=[
            {
                "team_name": "Manchester Utd",
                "full_club_name": "Manchester United F. C",
                "team_id": 0,
                "team_offset": 0x1580B,
                "status": "moderate_same_entry_overlap",
                "containing_entry": {"entry_offset": 0x6D03, "length": 60928},
                "top_run_match": {
                    "run_index": 7,
                    "overlap_hits_in_team_raw": 6,
                    "non_empty_row_count": 11,
                    "second_best_overlap_hits": 5,
                    "rows": [],
                },
                "known_lineup_anchor_assisted_match": {
                    "dataset_key": "manutd",
                    "entry_offset": 0x15B3C,
                    "hit_count": 18,
                    "exact_anchor_count": 18,
                    "stride5_window": {
                        "delta_positions": [5, 5, 5, 5],
                        "rows": [
                            {
                                "pid_candidate": 3385,
                                "dd6361_name": "David Robert BECKHAM",
                                "is_empty_slot": False,
                                "is_anchor_pid": True,
                            },
                            {
                                "pid_candidate": 8434,
                                "dd6361_name": "Philip John NEVILLE",
                                "is_empty_slot": False,
                                "is_anchor_pid": False,
                            },
                        ],
                    },
                },
            }
        ],
        raw_payload={"ok": True},
    )
    monkeypatch.setattr(cli, "extract_team_rosters_eq_same_entry_overlap", lambda **kwargs: fake_result)

    cli.cmd_team_roster_extract(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=["Manchester Utd"],
            top_examples=15,
            row_limit=10,
            include_fallbacks=True,
            json_output=None,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "anchor_assisted dataset=manutd" in out
    assert "anchor_run_window rows=2" in out
    assert "A pid= 3385  David Robert BECKHAM" in out


def test_cmd_team_roster_extract_prints_pseudo_adjacent_candidate(monkeypatch, capsys):
    fake_result = SimpleNamespace(
        team_count=532,
        dd6361_pid_name_count=2009,
        same_entry_overlap_coverage={},
        final_extraction_coverage={},
        requested_team_results=[
            {
                "team_name": "Wimbledonl",
                "full_club_name": "Wimbledon Football Club",
                "team_id": 0,
                "team_offset": 0x1B578,
                "status": "no_same_entry_overlap_hits",
                "containing_entry": {"entry_offset": 0x1B04B, "length": 47360},
                "heuristic_warnings": [
                    {
                        "type": "adjacent_pseudo_team_record_reassignment",
                        "message": "Adjacent pseudo-team record 'ELONEX' has a strong roster match; candidate run copied for review",
                    }
                ],
                "preferred_roster_match": {
                    "provenance": "adjacent_pseudo_team_record_reassignment",
                    "row_count": 27,
                    "provisional": True,
                    "rows": [],
                },
                "top_run_match": {
                    "run_index": 0,
                    "overlap_hits_in_team_raw": 0,
                    "non_empty_row_count": 27,
                    "second_best_overlap_hits": 0,
                    "rows": [],
                },
                "adjacent_pseudo_team_reassignment_candidate": {
                    "run_index": 1,
                    "non_empty_row_count": 27,
                    "source_pseudo_team_name": "ELONEX",
                    "rows": [
                        {
                            "pid_candidate": 9238,
                            "dd6361_name": "Neil SULLIVAN",
                            "is_empty_slot": False,
                            "xor_pid_found_in_team_raw": True,
                        }
                    ],
                },
            }
        ],
        raw_payload={"ok": True},
    )
    monkeypatch.setattr(cli, "extract_team_rosters_eq_same_entry_overlap", lambda **kwargs: fake_result)

    cli.cmd_team_roster_extract(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=["Wimbledon"],
            top_examples=15,
            row_limit=10,
            include_fallbacks=True,
            json_output=None,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "preferred_roster provenance=adjacent_pseudo_team_record_reassignment" in out
    assert "WARNING Adjacent pseudo-team record 'ELONEX'" in out
    assert "pseudo_adjacent_candidate run=1" in out
    assert "pid= 9238  Neil SULLIVAN" in out


def test_cmd_team_roster_extract_anchor_interval_duplicate_hidden_but_warning_shown(monkeypatch, capsys):
    fake_result = SimpleNamespace(
        team_count=532,
        dd6361_pid_name_count=2009,
        same_entry_overlap_coverage={},
        final_extraction_coverage={},
        preferred_roster_coverage={"covered_count": 514, "club_like_team_count": 530, "club_like_covered_count": 514},
        requested_team_results=[
            {
                "team_name": "R.C.D. Mallorca",
                "full_club_name": "Real Club Deportivo Mallorca",
                "team_id": 0,
                "team_offset": 0x7000,
                "status": "moderate_same_entry_overlap",
                "containing_entry": {"entry_offset": 0x6D03, "length": 60928},
                "heuristic_warnings": [
                    {
                        "type": "anchor_interval_contested_run",
                        "message": "Assigned run 7 is also the current best same-entry run for 1 other team(s)",
                        "run_index": 7,
                        "contested_team_names_preview": ["Manchester Utd"],
                    }
                ],
                "top_run_match": {
                    "run_index": 7,
                    "overlap_hits_in_team_raw": 5,
                    "non_empty_row_count": 20,
                    "second_best_overlap_hits": 4,
                    "rows": [
                        {
                            "pid_candidate": 3385,
                            "dd6361_name": "David Robert BECKHAM",
                            "is_empty_slot": False,
                            "xor_pid_found_in_team_raw": False,
                        }
                    ],
                },
                "anchor_interval_monotonic_candidate": {
                    "run_index": 7,
                    "non_empty_row_count": 20,
                    "anchor_interval": {"left_run_index": 6, "right_run_index": 9},
                    "rows": [
                        {
                            "pid_candidate": 3385,
                            "dd6361_name": "David Robert BECKHAM",
                            "is_empty_slot": False,
                            "xor_pid_found_in_team_raw": False,
                        }
                    ],
                },
                "preferred_roster_match": {
                    "provenance": "anchor_interval_monotonic_same_entry",
                    "row_count": 20,
                    "provisional": True,
                    "rows": [],
                },
            }
        ],
        raw_payload={"ok": True},
    )
    monkeypatch.setattr(cli, "extract_team_rosters_eq_same_entry_overlap", lambda **kwargs: fake_result)

    cli.cmd_team_roster_extract(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=["Mallorca"],
            top_examples=15,
            row_limit=10,
            include_fallbacks=True,
            json_output=None,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "preferred_roster provenance=anchor_interval_monotonic_same_entry" in out
    assert "WARNING Assigned run 7 is also the current best same-entry run" in out
    assert "contested_with=Manchester Utd" in out
    assert "best_run index=7" in out
    assert "anchor_interval_candidate run=7" not in out
