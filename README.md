# Premier Manager 99 — Database Editor and Reverse Engineering

Purpose
One‑stop entrypoint for working with Premier Manager 99 database files: inspect, search and make safe edits. Canonical docs now live in [docs/](docs/) and the legacy investigation trail remains in [docs/archive/](docs/archive/) as artifacts.

Quick start
Requirements: Python 3.8+; run from repo root. Database files are under [DBDAT/](DBDAT/).

GUI tips
- Launch the desktop editor via `python -m pm99_editor.gui`; the **Tools → Open PKF Viewer…** menu opens the new container inspector for `.PKF` archives with a built-in string searcher that accepts single needles or lists.
- For offline investigation, `ArchiveStringSearcher` in [pm99_editor/pkf.py](pm99_editor/pkf.py) accepts a folder of `.PKF`/`.FDI` assets and a list of needles to report cross-file matches.

CLI examples
The command line uses [pm99_editor/cli.py](pm99_editor/cli.py) via module entry. Core commands are implemented in [cli.cmd_list()](pm99_editor/cli.py:10), [cli.cmd_search()](pm99_editor/cli.py:22), [cli.cmd_rename()](pm99_editor/cli.py:38) and [cli.cmd_info()](pm99_editor/cli.py:74); the entry point is [cli.main()](pm99_editor/cli.py:89).

Inspect file header and counts
Example reference: [DBDAT/JUG98030.FDI](DBDAT/JUG98030.FDI)
```
python -m pm99_editor info DBDAT/JUG98030.FDI
```

List first 20 players
```
python -m pm99_editor list DBDAT/JUG98030.FDI --limit 20
```

Search by name
```
python -m pm99_editor search DBDAT/JUG98030.FDI "Ronaldo"
```

Rename by record id (same-length recommended)
```
python -m pm99_editor rename DBDAT/JUG98030.FDI --id 123 --name "Cristiano Ronaldo"
```

Safety
- Always work on copies of [DBDAT/JUG98030.FDI](DBDAT/JUG98030.FDI) and keep backups.
- Writer creates backups via [file_writer.create_backup()](pm99_editor/file_writer.py:17) and adjusts directory offsets with [file_writer.write_fdi_record()](pm99_editor/file_writer.py:102).

Project layout
- Core library: [pm99_editor/](pm99_editor/)
  - File I/O wrapper [FDIFile](pm99_editor/io.py:15) with helpers: [FDIFile.load()](pm99_editor/io.py:31), [FDIFile.list_players()](pm99_editor/io.py:338), [FDIFile.find_by_name()](pm99_editor/io.py:229), [FDIFile.save()](pm99_editor/io.py:269)
  - Models: [PlayerRecord](pm99_editor/models.py:13) with parser [PlayerRecord.from_bytes()](pm99_editor/models.py:63) and serializer [PlayerRecord.to_bytes()](pm99_editor/models.py:281)
  - Header & directory: [FDIHeader.from_bytes()](pm99_editor/models.py:389), [DirectoryEntry.from_bytes()](pm99_editor/models.py:434)
  - XOR helpers: [pm99_editor/xor.py](pm99_editor/xor.py)
  - PKF containers: [pm99_editor/pkf.py](pm99_editor/pkf.py)
- CLI: [pm99_editor/cli.py](pm99_editor/cli.py)
- Tests: [tests/](tests/)
- Analysis scripts: [scripts/](scripts/)
- Game data used for development: [DBDAT/](DBDAT/)

Canonical documentation (start here)
- User guide: [docs/EDITOR_README.md](docs/EDITOR_README.md) — how to use the editor today
- Data formats and field mapping: [docs/PLAYER_FIELD_MAP.md](docs/PLAYER_FIELD_MAP.md)
- Reverse‑engineering summary: [docs/REVERSE_ENGINEERING_HANDOVER.md](docs/REVERSE_ENGINEERING_HANDOVER.md) and [docs/REVERSE_ENGINEERING_FINAL_REPORT.md](docs/REVERSE_ENGINEERING_FINAL_REPORT.md)
- Project docs index: [docs/README.md](docs/README.md)

Legacy investigation artifacts (kept for reference)
The following remain for traceability and will be gradually folded into concise canonical docs:
- Loader and decode summary: [docs/archive/README.md](docs/archive/README.md)
- Binary triangulation and struct notes: [docs/archive/triangulation.md](docs/archive/triangulation.md), [docs/archive/struct_notes.md](docs/archive/struct_notes.md), [docs/archive/verify.txt](docs/archive/verify.txt)
- Handover bundles and status reports: [docs/archive/COMPREHENSIVE_HANDOVER.md](docs/archive/COMPREHENSIVE_HANDOVER.md), [docs/archive/FINAL_HANDOVER.md](docs/archive/FINAL_HANDOVER.md), [docs/archive/FINAL_FINDINGS.md](docs/archive/FINAL_FINDINGS.md), [docs/archive/FINAL_STATUS.md](docs/archive/FINAL_STATUS.md), [docs/archive/COMPLETION_NOTES.md](docs/archive/COMPLETION_NOTES.md), [docs/archive/PROJECT_SUMMARY.md](docs/archive/PROJECT_SUMMARY.md), [docs/archive/HANDOVER_FINAL.md](docs/archive/HANDOVER_FINAL.md), [docs/archive/handover.md](docs/archive/handover.md)
- Editor success notes: [docs/archive/SUCCESS_COMPLETE_COACH_EDITOR.md](docs/archive/SUCCESS_COMPLETE_COACH_EDITOR.md), [docs/archive/PLAYER_EDITOR_SUCCESS.md](docs/archive/PLAYER_EDITOR_SUCCESS.md)
- Field schemas and roadmap: [docs/archive/schema_players.md](docs/archive/schema_players.md), [docs/archive/FULL_EDITOR_ROADMAP.md](docs/archive/FULL_EDITOR_ROADMAP.md), [docs/archive/USAGE.md](docs/archive/USAGE.md), [docs/archive/editor_roadmap.md](docs/archive/editor_roadmap.md), [docs/archive/ENHANCEMENT_PLAN.md](docs/archive/ENHANCEMENT_PLAN.md)

Status at a glance
Parsing and writing are intentionally conservative. Known‑good reading/writing paths are encapsulated in:
- Parser: [PlayerRecord.from_bytes()](pm99_editor/models.py:63) with dynamic offsets (name end marker and attribute tail)
- Safe writer: [file_writer.write_fdi_record()](pm99_editor/file_writer.py:102)
- Header parsing: [FDIHeader.from_bytes()](pm99_editor/models.py:389)

Development workflow
- Run tests: from repo root execute
```
pytest -q
```
- Explore records in a REPL
```
python -q
>>> from pm99_editor.io import FDIFile
>>> f = FDIFile("DBDAT/JUG98030.FDI"); f.load()
>>> f.records[0]
```
See the [FDIFile](pm99_editor/io.py:15) implementation for available helpers.

Contributing and documentation cleanup
This repository previously contained overlapping handovers and AI‑generated notes. The new structure adopts:
- Canonical docs under [docs/](docs/) with concise, maintained topics
- Artifact trail kept under [docs/archive/](docs/archive/)
- Future consolidation target: migrate field/schema specifics from [docs/archive/schema_players.md](docs/archive/schema_players.md) into a single developer‑facing spec

Where to go next
- Getting started guide: [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)
- Architecture overview: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Developer guide (tests, scripts, CLI): [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md)

License and usage
Educational/research use only. The original game and its assets are copyright their owners.