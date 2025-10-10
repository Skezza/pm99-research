# PM99 Documentation Index

Purpose
Central, concise entry point for engineers. Canonical docs live here under docs/. Legacy investigation artifacts remain under docs/archive/ for traceability.

Start here (canonical)
- Quick start: [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)
- Architecture overview: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Data formats and record rules: [docs/DATA_FORMATS.md](docs/DATA_FORMATS.md)
- Editor user guide (GUI/usage status): [docs/EDITOR_README.md](docs/EDITOR_README.md)

Developer references
- Developer guide (tests, scripts, CLI usage): [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) (to be added)
- Changelog (notable doc/code shifts): [docs/CHANGELOG.md](docs/CHANGELOG.md) (to be added)

Reverse‑engineering narrative
- Condensed report (canonical): [docs/REVERSE_ENGINEERING_REPORT.md](docs/REVERSE_ENGINEERING_REPORT.md) (to be added)
- Deep sessions (legacy, kept for context): [docs/REVERSE_ENGINEERING_HANDOVER.md](docs/REVERSE_ENGINEERING_HANDOVER.md), [docs/REVERSE_ENGINEERING_FINAL_REPORT.md](docs/REVERSE_ENGINEERING_FINAL_REPORT.md)

Key code anchors (for quick navigation)
- CLI entrypoint: [cli.main()](../pm99_editor/cli.py:89)
  - Commands: [cli.cmd_list()](../pm99_editor/cli.py:10), [cli.cmd_search()](../pm99_editor/cli.py:22), [cli.cmd_rename()](../pm99_editor/cli.py:38), [cli.cmd_info()](../pm99_editor/cli.py:74)
- File I/O and record enumeration: [FDIFile](../pm99_editor/io.py:15)
  - Load: [FDIFile.load()](../pm99_editor/io.py:31), Directory parse: [FDIFile._parse_directory()](../pm99_editor/io.py:47), Iterate/scan: [FDIFile._iter_records()](../pm99_editor/io.py:63)
- Player model and serialization: [PlayerRecord](../pm99_editor/models.py:13)
  - Parse: [PlayerRecord.from_bytes()](../pm99_editor/models.py:63), Serialize overlay: [PlayerRecord.to_bytes()](../pm99_editor/models.py:281)
- Safe write with directory fixups: [file_writer.write_fdi_record()](../pm99_editor/file_writer.py:102), backups via [file_writer.create_backup()](../pm99_editor/file_writer.py:17)
- GUI application entry: [main()](../pm99_database_editor.py:1189)

Consolidation map (what to keep, merge, archive)
- Player format and fields
  - Keep/canonical: [docs/DATA_FORMATS.md](docs/DATA_FORMATS.md) (container + decoded record rules), [docs/PLAYER_FIELD_MAP.md](docs/PLAYER_FIELD_MAP.md) (detailed mapping supplement)
  - Archive (legacy): [docs/archive/schema_players.md](archive/schema_players.md) (superseded by DATA_FORMATS and code)
- Usage and editor roadmaps
  - Keep/canonical: [docs/EDITOR_README.md](docs/EDITOR_README.md), [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md), [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) (to be added)
  - Archive (legacy): [docs/archive/USAGE.md](archive/USAGE.md), [docs/archive/FULL_EDITOR_ROADMAP.md](archive/FULL_EDITOR_ROADMAP.md), [docs/archive/editor_roadmap.md](archive/editor_roadmap.md), [docs/archive/ENHANCEMENT_PLAN.md](archive/ENHANCEMENT_PLAN.md)
- Handover/final findings/status
  - Keep/canonical: [docs/REVERSE_ENGINEERING_REPORT.md](docs/REVERSE_ENGINEERING_REPORT.md) (to be added)
  - Archive (legacy bundles): [docs/archive/COMPREHENSIVE_HANDOVER.md](archive/COMPREHENSIVE_HANDOVER.md), [docs/archive/FINAL_HANDOVER.md](archive/FINAL_HANDOVER.md), [docs/archive/FINAL_FINDINGS.md](archive/FINAL_FINDINGS.md), [docs/archive/FINAL_STATUS.md](archive/FINAL_STATUS.md), [docs/archive/HANDOVER_FINAL.md](archive/HANDOVER_FINAL.md), [docs/archive/handover.md](archive/handover.md), [docs/archive/PROJECT_SUMMARY.md](archive/PROJECT_SUMMARY.md), [docs/SESSION_PROGRESS_REPORT.md](docs/SESSION_PROGRESS_REPORT.md), [docs/SESSION_COMPLETE_SUMMARY.md](docs/SESSION_COMPLETE_SUMMARY.md), [docs/SESSION_HANDOVER_FINAL.md](docs/SESSION_HANDOVER_FINAL.md), [docs/SESSION_HANDOVER_RECORD_REWRITE.md](docs/SESSION_HANDOVER_RECORD_REWRITE.md)
- Loader/structure triangulation (useful research artifacts)
  - Keep as archived references: [docs/archive/README.md](archive/README.md), [docs/archive/struct_notes.md](archive/struct_notes.md), [docs/archive/triangulation.md](archive/triangulation.md), [docs/archive/verify.txt](archive/verify.txt), [docs/archive/breadcrumbs.csv](archive/breadcrumbs.csv)
- Success notes
  - Archive: [docs/archive/SUCCESS_COMPLETE_COACH_EDITOR.md](archive/SUCCESS_COMPLETE_COACH_EDITOR.md), [docs/archive/PLAYER_EDITOR_SUCCESS.md](archive/PLAYER_EDITOR_SUCCESS.md)

Maintenance policy
- Canonical docs are updated here under docs/. Legacy files under docs/archive/ and session logs in docs/ will not be extended; they remain for provenance.
- When adding a new field/offset:
  - Update [docs/DATA_FORMATS.md](docs/DATA_FORMATS.md) with precise byte rules and double‑XOR notes
  - Add or extend a minimal test near [tests/test_core_io_decoding.py](../tests/test_core_io_decoding.py) and [tests/test_integration_roundtrip.py](../tests/test_integration_roundtrip.py)
  - Cross‑link relevant code anchors (e.g., [PlayerRecord.from_bytes()](../pm99_editor/models.py:63))

Directory guide
- Canonical docs: this directory
- Legacy/archived artifacts: [docs/archive/](archive/)
- Code: [pm99_editor/](../pm99_editor/), GUI: [pm99_database_editor.py](../pm99_database_editor.py)

Next actions (planned)
- Create [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) with test/CLI/script playbook
- Create [docs/REVERSE_ENGINEERING_REPORT.md](docs/REVERSE_ENGINEERING_REPORT.md) (condensed single narrative with references)
- Create [docs/CHANGELOG.md](docs/CHANGELOG.md) with this re‑structure and future deltas
- Add [docs/ARCHIVE/README.md](docs/ARCHIVE/README.md) to index archived items (both docs/ session logs and docs/archive/ artifacts)

Notes on status drift and correctness
Some earlier documents claim broader completion or different algorithmic details than the current code confirms. Treat [docs/DATA_FORMATS.md](docs/DATA_FORMATS.md) and the code anchors ([FDIFile._iter_records()](../pm99_editor/io.py:63), [PlayerRecord.from_bytes()](../pm99_editor/models.py:63), [file_writer.write_fdi_record()](../pm99_editor/file_writer.py:102)) as the source of truth when discrepancies arise.