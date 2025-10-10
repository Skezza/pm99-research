# PM99 Documentation Index

Purpose
Central, concise entry point for engineers. Canonical docs live here under docs/. Legacy investigation artifacts remain under out/ for traceability.

Start here (canonical)
- Quick start: [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)
- Architecture overview: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Data formats and record rules: [docs/DATA_FORMATS.md](docs/DATA_FORMATS.md)
- Editor user guide (GUI/usage status): [docs/EDITOR_README.md](docs/EDITOR_README.md)
- Deliverable impact walkthrough: [docs/DELIVERABLE_IMPACT.md](docs/DELIVERABLE_IMPACT.md)

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
  - Archive (legacy): [out/schema_players.md](../out/schema_players.md) (superseded by DATA_FORMATS and code)
- Usage and editor roadmaps
  - Keep/canonical: [docs/EDITOR_README.md](docs/EDITOR_README.md), [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md), [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) (to be added)
  - Archive (legacy): [out/USAGE.md](../out/USAGE.md), [out/FULL_EDITOR_ROADMAP.md](../out/FULL_EDITOR_ROADMAP.md), [out/editor_roadmap.md](../out/editor_roadmap.md), [out/ENHANCEMENT_PLAN.md](../out/ENHANCEMENT_PLAN.md)
- Handover/final findings/status
  - Keep/canonical: [docs/REVERSE_ENGINEERING_REPORT.md](docs/REVERSE_ENGINEERING_REPORT.md) (to be added)
  - Archive (legacy bundles): [out/COMPREHENSIVE_HANDOVER.md](../out/COMPREHENSIVE_HANDOVER.md), [out/FINAL_HANDOVER.md](../out/FINAL_HANDOVER.md), [out/FINAL_FINDINGS.md](../out/FINAL_FINDINGS.md), [out/FINAL_STATUS.md](../out/FINAL_STATUS.md), [out/HANDOVER_FINAL.md](../out/HANDOVER_FINAL.md), [out/handover.md](../out/handover.md), [out/PROJECT_SUMMARY.md](../out/PROJECT_SUMMARY.md), [docs/SESSION_PROGRESS_REPORT.md](docs/SESSION_PROGRESS_REPORT.md), [docs/SESSION_COMPLETE_SUMMARY.md](docs/SESSION_COMPLETE_SUMMARY.md), [docs/SESSION_HANDOVER_FINAL.md](docs/SESSION_HANDOVER_FINAL.md), [docs/SESSION_HANDOVER_RECORD_REWRITE.md](docs/SESSION_HANDOVER_RECORD_REWRITE.md)
- Loader/structure triangulation (useful research artifacts)
  - Keep as archived references: [out/README.md](../out/README.md), [out/struct_notes.md](../out/struct_notes.md), [out/triangulation.md](../out/triangulation.md), [out/verify.txt](../out/verify.txt), [out/breadcrumbs.csv](../out/breadcrumbs.csv)
- Success notes
  - Archive: [out/SUCCESS_COMPLETE_COACH_EDITOR.md](../out/SUCCESS_COMPLETE_COACH_EDITOR.md), [out/PLAYER_EDITOR_SUCCESS.md](../out/PLAYER_EDITOR_SUCCESS.md)

Maintenance policy
- Canonical docs are updated here under docs/. Legacy files under out/ and session logs in docs/ will not be extended; they remain for provenance.
- When adding a new field/offset:
  - Update [docs/DATA_FORMATS.md](docs/DATA_FORMATS.md) with precise byte rules and double‑XOR notes
  - Add or extend a minimal test near [tests/test_core_io_decoding.py](../tests/test_core_io_decoding.py) and [tests/test_integration_roundtrip.py](../tests/test_integration_roundtrip.py)
  - Cross‑link relevant code anchors (e.g., [PlayerRecord.from_bytes()](../pm99_editor/models.py:63))

Directory guide
- Canonical docs: this directory
- Legacy/archived artifacts: [out/](../out/)
- Code: [pm99_editor/](../pm99_editor/), GUI: [pm99_database_editor.py](../pm99_database_editor.py)

Next actions (planned)
- Create [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) with test/CLI/script playbook
- Create [docs/REVERSE_ENGINEERING_REPORT.md](docs/REVERSE_ENGINEERING_REPORT.md) (condensed single narrative with references)
- Create [docs/CHANGELOG.md](docs/CHANGELOG.md) with this re‑structure and future deltas
- Add [docs/ARCHIVE/README.md](docs/ARCHIVE/README.md) to index archived items (both docs/ session logs and out/ artifacts)

Notes on status drift and correctness
Some earlier documents claim broader completion or different algorithmic details than the current code confirms. Treat [docs/DATA_FORMATS.md](docs/DATA_FORMATS.md) and the code anchors ([FDIFile._iter_records()](../pm99_editor/io.py:63), [PlayerRecord.from_bytes()](../pm99_editor/models.py:63), [file_writer.write_fdi_record()](../pm99_editor/file_writer.py:102)) as the source of truth when discrepancies arise.