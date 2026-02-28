from types import SimpleNamespace

import app.editor_actions as editor_actions
from app.main_dat import PM99MainDatFile, PM99MainDatPrefix, PM99PackedDate
from app.editor_sources import RecordEntry


class FakePlayer:
    def __init__(self, name="Old Name", team_id=1, raw_data=b"abcdef"):
        self.name = name
        self.team_id = team_id
        self.raw_data = raw_data
        self.name_dirty = False

    def set_name(self, full_name):
        self.name = full_name
        self.name_dirty = True


class FakeCoach:
    def __init__(self, full_name="Old Coach"):
        self.given_name = full_name.split()[0]
        self.surname = full_name.split(maxsplit=1)[1]
        self.full_name = full_name
        self.decoded = bytearray(full_name.encode("latin-1"))

    def set_name(self, given, surname):
        self.given_name = given
        self.surname = surname
        self.full_name = f"{given} {surname}".strip()
        self.decoded = bytearray(self.full_name.encode("latin-1"))

    def to_bytes(self):
        return bytes(self.decoded)


class FakeTeam:
    def __init__(self, name="Old Team", stadium="Old Ground", team_id=10):
        self.name = name
        self.stadium = stadium
        self.team_id = team_id
        self.raw_data = bytearray(b"raw-team-data")

    def set_name(self, new_name):
        self.name = new_name
        self.raw_data = bytearray((new_name + "|" + self.stadium).encode("latin-1"))

    def set_stadium_name(self, new_stadium):
        self.stadium = new_stadium
        self.raw_data = bytearray((self.name + "|" + new_stadium).encode("latin-1"))


class FakeFDIFile:
    instances = []

    def __init__(self, file_path):
        self.file_path = file_path
        self.modified_records = {}
        self.last_backup_path = None
        self.saved = False
        self.__class__.instances.append(self)

    def load(self):
        return None

    def save(self):
        self.saved = True
        self.last_backup_path = self.file_path + ".backup"


def test_rename_player_records_staged_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(
        editor_actions,
        "gather_player_records",
        lambda _: ([RecordEntry(offset=0x10, record=FakePlayer(), source="scanner")], []),
    )
    fpath = tmp_path / "JUGTEST.FDI"
    fpath.write_bytes(b"")
    result = editor_actions.rename_player_records(
        str(fpath),
        target_old="Old Name",
        new_name="New Name",
        write_changes=False,
    )

    assert result.applied_to_disk is False
    assert result.backup_path is None
    assert result.matched_count == 1
    assert len(result.changes) == 1
    assert len(result.staged_records) == 1
    assert result.staged_records[0][0] == 0x10
    assert result.staged_records[0][1].name == "New Name"


def test_rename_player_records_immediate_write_uses_batch_writer(monkeypatch, tmp_path):
    monkeypatch.setattr(
        editor_actions,
        "gather_player_records",
        lambda _: ([RecordEntry(offset=0x20, record=FakePlayer(), source="scanner")], []),
    )
    monkeypatch.setattr(editor_actions, "save_modified_records", lambda file_path, file_data, modified_records: b"new-bytes")
    monkeypatch.setattr(editor_actions, "create_backup", lambda file_path: file_path + ".backup")

    fpath = tmp_path / "JUGTEST2.FDI"
    fpath.write_bytes(b"orig-bytes")
    result = editor_actions.rename_player_records(
        str(fpath),
        target_old="Old Name",
        new_name="New Name",
        write_changes=True,
    )

    assert result.applied_to_disk is True
    assert result.backup_path == str(fpath) + ".backup"
    assert fpath.read_bytes() == b"new-bytes"
    assert not result.staged_records


def test_rename_coach_records_staged_mode(monkeypatch, tmp_path):
    coach = FakeCoach("Alex Smith")
    monkeypatch.setattr(
        editor_actions,
        "gather_coach_records",
        lambda _: ([RecordEntry(offset=0x30, record=coach, source="loader")], []),
    )

    fpath = tmp_path / "ENTTEST.FDI"
    fpath.write_bytes(b"")
    result = editor_actions.rename_coach_records(
        str(fpath),
        old_name="Alex Smith",
        new_name="Alan Smith",
        write_changes=False,
    )

    assert result.applied_to_disk is False
    assert result.matched_count == 1
    assert len(result.changes) == 1
    assert result.changes[0].old_name == "Alex Smith"
    assert result.changes[0].new_name == "Alan Smith"
    assert result.staged_records[0][1].full_name == "Alan Smith"


def test_rename_team_records_staged_mode(monkeypatch, tmp_path):
    team = FakeTeam()
    monkeypatch.setattr(
        editor_actions,
        "gather_team_records",
        lambda _: ([RecordEntry(offset=0x44, record=team, source="loader")], []),
    )

    fpath = tmp_path / "EQTEST.FDI"
    fpath.write_bytes(b"\x00\x01dummy")
    result = editor_actions.rename_team_records(
        str(fpath),
        old_team="Old Team",
        new_team="New Team",
        old_stadium="Old Ground",
        new_stadium="New Ground",
        write_changes=False,
    )

    assert result.applied_to_disk is False
    assert result.matched_count == 1
    assert len(result.changes) == 1
    assert result.changes[0].name_change == ("Old Team", "New Team")
    assert result.changes[0].stadium_change == ("Old Ground", "New Ground")
    assert result.staged_records[0][0] == 0x44


def test_patch_player_visible_skills_dd6361_wraps_probe_payload(monkeypatch, tmp_path):
    import scripts.probe_dd6361_skill_patch as dd6361_patch

    calls = {}
    out_file = tmp_path / "patched.fdi"
    report_file = tmp_path / "patch.json"

    def fake_patch_dd6361_trailer_stats(**kwargs):
        calls["patch"] = kwargs
        return {
            "input_file": str(tmp_path / "JUG98030.FDI"),
            "output_file": str(out_file),
            "target_query": "Beckham",
            "resolved_bio_name": "David Robert BECKHAM",
            "in_place": False,
            "backup_path": None,
            "updates_requested": {"speed": 91},
            "mapped10_order": ["speed", "stamina"],
            "mapped10_before": {"speed": 90, "stamina": 85},
            "mapped10_after": {"speed": 91, "stamina": 85},
            "verification": {"all_requested_fields_match": True},
            "trailer_location": {"touched_entry_offsets": [0x1234, 0x5678]},
        }

    monkeypatch.setattr(dd6361_patch, "patch_dd6361_trailer_stats", fake_patch_dd6361_trailer_stats)

    result = editor_actions.patch_player_visible_skills_dd6361(
        file_path=str(tmp_path / "JUG98030.FDI"),
        player_name="Beckham",
        updates={"speed": 91},
        output_file=str(out_file),
        in_place=False,
        create_backup_before_write=False,
        json_output=str(report_file),
    )

    assert calls["patch"] == {
        "player_file": str(tmp_path / "JUG98030.FDI"),
        "name_query": "Beckham",
        "updates": {"speed": 91},
        "output_file": str(out_file),
        "in_place": False,
        "create_backup_before_write": False,
        "json_output": str(report_file),
    }
    assert result.file_path.name == "JUG98030.FDI"
    assert result.output_file == out_file
    assert result.resolved_bio_name == "David Robert BECKHAM"
    assert result.verification_all_requested_fields_match is True
    assert result.touched_entry_offsets == [0x1234, 0x5678]
    assert result.raw_payload["resolved_bio_name"] == "David Robert BECKHAM"


def test_inspect_player_visible_skills_dd6361_wraps_probe_payload(monkeypatch, tmp_path):
    import scripts.probe_dd6361_skill_patch as dd6361_patch

    calls = {}

    def fake_inspect_dd6361_trailer_stats(**kwargs):
        calls["inspect"] = kwargs
        return {
            "input_file": str(tmp_path / "JUG98030.FDI"),
            "target_query": "Beckham",
            "resolved_bio_name": "David Robert BECKHAM",
            "mapped10_order": ["speed", "stamina"],
            "mapped10": {"speed": 90, "stamina": 85},
            "decoded18": [90, 85, 0, 0],
            "role_ratings5": {"role_1": 87},
            "unknown_byte16_candidate": 57,
        }

    monkeypatch.setattr(dd6361_patch, "inspect_dd6361_trailer_stats", fake_inspect_dd6361_trailer_stats)

    result = editor_actions.inspect_player_visible_skills_dd6361(
        file_path=str(tmp_path / "JUG98030.FDI"),
        player_name="Beckham",
    )

    assert calls["inspect"] == {
        "player_file": str(tmp_path / "JUG98030.FDI"),
        "name_query": "Beckham",
    }
    assert result.file_path.name == "JUG98030.FDI"
    assert result.target_query == "Beckham"
    assert result.resolved_bio_name == "David Robert BECKHAM"
    assert result.mapped10 == {"speed": 90, "stamina": 85}
    assert result.unknown_byte16_candidate == 57
    assert result.raw_payload["resolved_bio_name"] == "David Robert BECKHAM"


def test_build_player_visible_skill_index_dd6361_wraps_probe_payload(monkeypatch, tmp_path):
    import scripts.probe_dd6361_skill_patch as dd6361_patch

    calls = {}

    def fake_build_dd6361_pid_stats_index(**kwargs):
        calls["build"] = kwargs
        return {
            7: {
                "pid": 7,
                "resolved_bio_name": "David Robert BECKHAM",
                "mapped10": {"speed": 90, "stamina": 85},
                "decoded18": [90, 85],
                "role_ratings5": {"role_1": 87},
                "unknown_byte16_candidate": 57,
            }
        }

    monkeypatch.setattr(dd6361_patch, "build_dd6361_pid_stats_index", fake_build_dd6361_pid_stats_index)

    result = editor_actions.build_player_visible_skill_index_dd6361(
        file_path=str(tmp_path / "JUG98030.FDI"),
    )

    assert calls["build"] == {"player_file": str(tmp_path / "JUG98030.FDI")}
    assert result == {
        7: {
            "pid": 7,
            "resolved_bio_name": "David Robert BECKHAM",
            "mapped10": {"speed": 90, "stamina": 85},
            "decoded18": [90, 85],
            "role_ratings5": {"role_1": 87},
            "unknown_byte16_candidate": 57,
        }
    }


def test_extract_team_rosters_eq_same_entry_overlap_wraps_probe_payload(monkeypatch, tmp_path):
    import scripts.probe_eq_team_roster_overlap_extract as roster_overlap_probe

    calls = {}
    payload = {
        "player_file": str(tmp_path / "JUG98030.FDI"),
        "team_file": str(tmp_path / "EQ98030.FDI"),
        "dd6361_pid_name_count": 2009,
        "eq_decoded_entry_count": 123,
        "team_count": 532,
        "same_entry_overlap_coverage": {
            "status_counts": {"perfect_same_entry_run_overlap": 487},
            "strong_or_better_count": 487,
            "strong_or_better_ratio": 0.9154,
        },
        "strong_match_examples_topN": [{"team_name": "Stoke C"}],
        "requested_team_results": [{"team_name": "Stoke C", "status": "perfect_same_entry_run_overlap"}],
    }

    def fake_extract_eq_team_rosters_same_entry_overlap(**kwargs):
        calls["extract"] = kwargs
        return payload

    monkeypatch.setattr(
        roster_overlap_probe,
        "extract_eq_team_rosters_same_entry_overlap",
        fake_extract_eq_team_rosters_same_entry_overlap,
    )

    result = editor_actions.extract_team_rosters_eq_same_entry_overlap(
        team_file=str(tmp_path / "EQ98030.FDI"),
        player_file=str(tmp_path / "JUG98030.FDI"),
        team_queries=["Stoke"],
        top_examples=10,
        include_fallbacks=False,
        json_output=str(tmp_path / "report.json"),
    )

    assert calls["extract"] == {
        "player_file": str(tmp_path / "JUG98030.FDI"),
        "team_file": str(tmp_path / "EQ98030.FDI"),
        "team_queries": ["Stoke"],
        "top_examples": 10,
        "include_fallbacks": False,
        "json_output": str(tmp_path / "report.json"),
    }
    assert result.player_file.name == "JUG98030.FDI"
    assert result.team_file.name == "EQ98030.FDI"
    assert result.team_count == 532
    assert result.same_entry_overlap_coverage["strong_or_better_count"] == 487
    assert result.requested_team_results[0]["team_name"] == "Stoke C"
    assert result.raw_payload["dd6361_pid_name_count"] == 2009


def test_extract_team_rosters_eq_jug_linked_filters_and_shapes_output(monkeypatch, tmp_path):
    calls = {}

    def fake_load_eq_linked_team_rosters(**kwargs):
        calls["load"] = kwargs
        return [
            SimpleNamespace(
                eq_record_id=12,
                short_name="Inter",
                full_club_name="Internazionale Milano Football Club",
                stadium_name="San Siro",
                record_size=700,
                mode_byte=1,
                ent_count=1,
                rows=[
                    SimpleNamespace(slot_index=0, flag=0, player_record_id=3937, player_name="Demo PLAYER"),
                    SimpleNamespace(slot_index=1, flag=1, player_record_id=4000, player_name=""),
                ],
            ),
            SimpleNamespace(
                eq_record_id=13,
                short_name="Inter Cardiff",
                full_club_name="Inter Cardiff",
                stadium_name="Leckwith",
                record_size=700,
                mode_byte=1,
                ent_count=1,
                rows=[],
            ),
        ]

    monkeypatch.setattr(editor_actions, "load_eq_linked_team_rosters", fake_load_eq_linked_team_rosters)

    result = editor_actions.extract_team_rosters_eq_jug_linked(
        team_file=str(tmp_path / "EQ98030.FDI"),
        player_file=str(tmp_path / "JUG98030.FDI"),
        team_queries=["Inter Milan"],
    )

    assert calls["load"] == {
        "team_file": str(tmp_path / "EQ98030.FDI"),
        "player_file": str(tmp_path / "JUG98030.FDI"),
    }
    assert len(result) == 1
    assert result[0]["provenance"] == "eq_jug_linked_parser"
    assert result[0]["team_name"] == "Inter"
    assert result[0]["rows"] == [
        {"slot_index": 0, "flag": 0, "pid": 3937, "player_name": "Demo PLAYER"},
        {"slot_index": 1, "flag": 1, "pid": 4000, "player_name": ""},
    ]


def test_inspect_main_dat_prefix_wraps_parser(tmp_path):
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

    result = editor_actions.inspect_main_dat_prefix(file_path=str(file_path))

    assert result.file_path == file_path
    assert result.header_matches_expected is True
    assert result.format_passes_guard is True
    assert result.primary_label == "Slot A"
    assert result.time_fields == {"hour": 18, "minute": 5}
    assert result.opaque_tail_size == 2
    assert result.raw_payload["format_version"] == 0x0C


def test_patch_main_dat_prefix_writes_copy_and_preserves_unresolved_tail(tmp_path):
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
        opaque_tail=b"\xAA\xBB\xCC",
    )
    file_path.write_bytes(payload.to_bytes())

    result = editor_actions.patch_main_dat_prefix(
        file_path=str(file_path),
        primary_label="Edited Slot",
        hour=21,
        minute=9,
        scalar_byte=12,
        flag_updates={0: 7, 9: 0xEE},
        in_place=False,
        create_backup_before_write=True,
    )

    reparsed = editor_actions.inspect_main_dat_prefix(file_path=str(result.output_file))
    original = editor_actions.inspect_main_dat_prefix(file_path=str(file_path))

    assert result.input_file == file_path
    assert result.output_file == tmp_path / "main.edited.dat"
    assert result.backup_path is None
    assert "primary_label" in result.changed_fields
    assert "flag_updates" in result.changed_fields
    assert reparsed.primary_label == "Edited Slot"
    assert reparsed.time_fields == {"hour": 21, "minute": 9}
    assert reparsed.scalar_byte == 12
    assert reparsed.flag_bytes[0] == 7
    assert reparsed.flag_bytes[9] == 0xEE
    assert reparsed.opaque_tail_size == original.opaque_tail_size
