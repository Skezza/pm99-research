# Architecture Overview — Premier Manager 99 Database Editor

## Goals and scope
The project provides safe tooling for inspecting and editing Premier Manager 99 database archives (`*.FDI`) without relying on the original game executable. The codebase is split between a reusable library (`pm99_editor`), command line tooling, and a Tk GUI. Tests and reverse-engineering notes live alongside these layers so newcomers can trace behaviour from documentation to implementation.

## High-level component map
| Component | Location | Responsibilities |
| --- | --- | --- |
| Core models & I/O | [`pm99_editor/models.py`](../pm99_editor/models.py), [`pm99_editor/io.py`](../pm99_editor/io.py) | Decode headers, directory entries, and player/coach/team records. Provide `FDIFile` for loading and exposing parsed records.
| Persistence helpers | [`pm99_editor/file_writer.py`](../pm99_editor/file_writer.py) | Backup input files, encode modified records, and repair directory offsets/max offsets when payload lengths change.
| XOR & scanners | [`pm99_editor/xor.py`](../pm99_editor/xor.py), [`pm99_editor/scanner.py`](../pm99_editor/scanner.py) | Implement single/double-XOR routines and heuristics that discover embedded player payloads when directory entries are incomplete.
| Domain loaders | [`pm99_editor/loaders.py`](../pm99_editor/loaders.py), [`pm99_editor/coach_models.py`](../pm99_editor/coach_models.py), [`pm99_editor/player_models.py`](../pm99_editor/player_models.py) | Secondary parsers used by the GUI to decode teams, coaches, and correlated lookup data.
| Command line | [`pm99_editor/cli.py`](../pm99_editor/cli.py) | Provides `list`, `search`, `rename`, and `info` commands that wrap the core library.
| Desktop GUI | [`pm99_editor/gui.py`](../pm99_editor/gui.py) | Tkinter application with tabs for players, coaches, and teams, in-record editing widgets, a PKF archive viewer, and persistence via `save_modified_records()`.
| Data helpers | [`pm99_editor/datastore.py`](../pm99_editor/datastore.py), [`pm99_editor/pkf.py`](../pm99_editor/pkf.py) | Shared caches plus PKF archive reader used by the PKF viewer dialog.
| Tests & regression fixtures | [`tests/`](../tests/), [`scripts/`](../scripts/) | Encode unit, regression, and exploratory coverage around the decoding/writing pipeline and GUI smoke behaviour.

## Runtime data flow
1. **Load** — `FDIFile.load()` validates the file signature, reads the [`FDIHeader`](../pm99_editor/models.py#L1286) bytes, and parses directory entries via [`DirectoryEntry.from_bytes()`](../pm99_editor/models.py#L1318). It stores the raw file image on the instance for later writes.
2. **Discover records** — Player payloads are sourced from two places:
   - [`find_player_records()`](../pm99_editor/scanner.py) scans the decoded file image for embedded records when directory offsets are incomplete.
   - Directory entries tagged with `'P'` are decoded through [`decode_entry()`](../pm99_editor/xor.py) and normalised into [`PlayerRecord`](../pm99_editor/models.py#L560) instances.
   Duplicate names are filtered by a case-insensitive key, producing both `records_with_offsets` (offset + model) and a flat `records` list for callers.
3. **Augment** — The GUI lazily loads coaches (`ENT98030.FDI`) and teams (`EQ98030.FDI`) on demand via [`load_coaches()` / `CoachRecord`](../pm99_editor/models.py#L434) and [`load_teams()` / `TeamRecord`](../pm99_editor/models.py#L13). The CLI only works with the player file requested by the user.
4. **Surface** —
   - CLI commands (`pm99_editor/cli.py`) instantiate `FDIFile`, then project the parsed records into table-style console output.
   - The GUI populates search/filter state across notebook tabs, renders attribute fields, and provides tooling such as the PKF viewer that reuses [`_format_hex_preview()`](../pm99_editor/gui.py#L32) to show raw bytes when needed.
5. **Modify** — Edits made in the GUI set `PlayerRecord.modified` and cache the mutated instance keyed by original offset. Team and coach editors work similarly via `modified_team_records` / `modified_coach_records` mappings.
6. **Persist** — `save_modified_records()` (GUI bulk writes) and `write_fdi_record()` (single record CLI/script writes) re-encode the decoded payloads, update length prefixes, patch directory offsets when sizes shift, recompute `header.max_offset`, and create timestamped backups through `create_backup()` before rewriting the file.

## Key workflows
### Command-line usage
* `pm99_editor/cli.py` registers subcommands under `python -m pm99_editor`.
* Each command (`cmd_list`, `cmd_search`, `cmd_rename`, `cmd_info`) loads an `FDIFile`, applies filtering, and prints tabular output. `cmd_rename` delegates saving to `write_fdi_record()` so directory metadata remains consistent.

### GUI lifecycle
1. [`PM99DatabaseEditor`](../pm99_editor/gui.py#L46) bootstraps the Tk window, sets default file paths (`DBDAT/JUG98030.FDI`, etc.), and immediately calls `load_database()`.
2. `load_database()` hydrates player records and populates the Players tab (search entry, treeview of names, and attribute editors).
3. Switching to Coaches or Teams triggers lazy loaders that parse the corresponding `.FDI` via `load_coaches()` / `load_teams()` and populate treeviews, search boxes, and detail editors.
4. Save actions collect modified entities, call `save_modified_records()` / `write_fdi_record()` as needed, and refresh the UI state.
5. The **Tools → Open PKF Viewer…** menu spawns a PKF file picker, decodes the archive using [`PKFFile`](../pm99_editor/pkf.py), and shows a modal window with entry metadata and decoded previews.

### Testing & validation
* Tests under `tests/` exercise record decoding (`test_core_io_decoding.py`, `test_serialization.py`), hex dump helpers, and regression behaviours for scanners, writers, and GUI loading.
* Script-style regression suites under `scripts/` consume real DBDAT fixtures to verify higher-level workflows (e.g., name fixing, save editors) while remaining opt-in through pytest markers.

## Extensibility guidelines
* Keep canonical format rules synchronised between [`PlayerRecord`](../pm99_editor/models.py#L560) parsing helpers and the documentation in [`docs/DATA_FORMATS.md`](./DATA_FORMATS.md).
* When introducing new record types or metadata, update serializers in `models.py` and persistence helpers in `file_writer.py`, then add regression coverage under `tests/`.
* GUI enhancements should maintain separation between the UI layer (widgets, events) and parsing logic. Reuse `pm99_editor` helpers rather than duplicating decoding/encoding code inside the GUI.
* New tooling or scripts should live under `scripts/` and lean on the CLI/library APIs to stay consistent with automated tests.
