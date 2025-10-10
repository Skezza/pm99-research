# Architecture Overview — Premier Manager 99 Database Editor

## Goals and scope
The project provides safe tooling for inspecting and editing Premier Manager 99 database archives (`*.FDI`) without relying on the original game executable. The codebase is split between a reusable library (`app`), command line tooling, and a Tk GUI. Tests and reverse-engineering notes live alongside these layers so newcomers can trace behaviour from documentation to implementation.

## High-level component map
| Component | Location | Responsibilities |
| --- | --- | --- |
| Core models & I/O | [`app/models.py`](../app/models.py), [`app/io.py`](../app/io.py) | Decode headers, directory entries, and player/coach/team records. Provide `FDIFile` for loading and exposing parsed records.
| Persistence helpers | [`app/file_writer.py`](../app/file_writer.py) | Backup input files, encode modified records, and repair directory offsets/max offsets when payload lengths change.
| XOR & scanners | [`app/xor.py`](../app/xor.py), [`app/scanner.py`](../app/scanner.py) | Implement single/double-XOR routines and heuristics that discover embedded player payloads when directory entries are incomplete.
| Domain loaders | [`app/loaders.py`](../app/loaders.py), [`app/coach_models.py`](../app/coach_models.py), [`app/player_models.py`](../app/player_models.py) | Secondary parsers used by the GUI to decode teams, coaches, and correlated lookup data.
| League metadata | [`app/league_definitions.py`](../app/league_definitions.py), [`app/correlate.py`](../app/correlate.py) | Provide country/league hierarchies and cross-file lookups powering the Leagues tab and roster overlays.
| Command line | [`app/cli.py`](../app/cli.py) | Provides `list`, `search`, `rename`, and `info` commands that wrap the core library.
| Desktop GUI | [`app/gui.py`](../app/gui.py) | Tkinter application with tabs for players, coaches, teams, and leagues, in-record editing widgets, a PKF archive viewer, and persistence via `save_modified_records()`.
| Data helpers | [`app/datastore.py`](../app/datastore.py), [`app/pkf.py`](../app/pkf.py) | Shared caches plus PKF archive reader used by the PKF viewer dialog.
| Tests & regression fixtures | [`tests/`](../tests/), [`scripts/`](../scripts/) | Encode unit, regression, and exploratory coverage around the decoding/writing pipeline and GUI smoke behaviour.

## Runtime data flow
1. **Load** — `FDIFile.load()` validates the file signature, instantiates `FDIHeader`, and parses directory entries via `DirectoryEntry.from_bytes()`. It stores the raw file image on the instance for later writes.
2. **Discover records** — Player payloads are sourced from two places:
   - `find_player_records()` scans the decoded file image for embedded records when directory offsets are incomplete.
   - Directory entries tagged with `'P'` are decoded through `xor.decode_entry()` and normalised into `PlayerRecord` instances.
   Duplicate names are filtered by a case-insensitive key, producing both `records_with_offsets` (offset + model) and a flat `records` list for callers.
3. **Augment** — The GUI lazily loads coaches (`ENT98030.FDI`) and teams (`EQ98030.FDI`) on demand via `load_coaches()` / `CoachRecord` and `load_teams()` / `TeamRecord`. League definitions are hydrated separately so the Leagues tab can group teams by country. The CLI only works with the player file requested by the user.
4. **Surface** —
   - CLI commands (`app/cli.py`) instantiate `FDIFile`, then project the parsed records into table-style console output.
   - The GUI populates search/filter state across notebook tabs, renders attribute fields, includes the Leagues hierarchy browser, and provides tooling such as the PKF viewer that reuses `_format_hex_preview()` to show raw bytes when needed.
5. **Modify** — Edits made in the GUI set `PlayerRecord.modified` and cache the mutated instance keyed by original offset. Team and coach editors work similarly via `modified_team_records` / `modified_coach_records` mappings.
6. **Persist** — `save_modified_records()` (GUI bulk writes) and `FDIFile.save()` (used by CLI helpers) re-encode the decoded payloads, update length prefixes, patch directory offsets when sizes shift, recompute `header.max_offset`, and create timestamped backups through `create_backup()` before rewriting the file.

## Key workflows
### Command-line usage
* `app/cli.py` registers subcommands under `python -m app`.
* Each command (`cmd_list`, `cmd_search`, `cmd_rename`, `cmd_info`) loads an `FDIFile`, applies filtering, and prints tabular output. `cmd_rename` saves through `FDIFile.save()`, which wraps `save_modified_records()` to keep directory metadata consistent.

### GUI lifecycle
1. `PM99DatabaseEditor` bootstraps the Tk window, sets default file paths (`DBDAT/JUG98030.FDI`, etc.), and immediately calls `load_database()`.
2. `load_database()` hydrates player records and populates the Players tab (search entry, treeview of names, and attribute editors).
3. Switching to Coaches or Teams triggers lazy loaders that parse the corresponding `.FDI` via `load_coaches()` / `load_teams()` and populate treeviews, search boxes, and detail editors.
4. The Leagues tab uses shared country/league metadata plus loaded team data to show a hierarchical Country → League → Team view with stadium overlays.
5. Save actions collect modified entities, call `save_modified_records()` for batch writes, and refresh the UI state.
6. The **Tools → Open PKF Viewer…** menu spawns a PKF file picker, decodes the archive using `PKFFile`, and shows a modal window with entry metadata and decoded previews.

### Testing & validation
* Tests under `tests/` exercise record decoding (`test_core_io_decoding.py`, `test_serialization.py`), hex dump helpers, and regression behaviours for scanners, writers, and GUI loading.
* Script-style regression suites under `scripts/` consume real DBDAT fixtures to verify higher-level workflows (e.g., name fixing, save editors) while remaining opt-in through pytest markers and fixture skips when the proprietary data is unavailable.

## Extensibility guidelines
* Keep canonical format rules synchronised between the `PlayerRecord` parsing helpers and the documentation in [`docs/DATA_FORMATS.md`](./DATA_FORMATS.md).
* When introducing new record types or metadata, update serializers in `models.py` and persistence helpers in `file_writer.py`, then add regression coverage under `tests/`.
* GUI enhancements should maintain separation between the UI layer (widgets, events) and parsing logic. Reuse `app` helpers rather than duplicating decoding/encoding code inside the GUI.
* New tooling or scripts should live under `scripts/` and lean on the CLI/library APIs to stay consistent with automated tests.

