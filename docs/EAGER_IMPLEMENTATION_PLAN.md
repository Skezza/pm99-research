Eager-loading Implementation Plan for PM99 Editor

Overview
This document specifies a line-by-line implementation plan to support "eager" loading — i.e. pull all FDI and PKF files into memory at startup — while keeping the codebase safe, testable and extensible.

Goals
- Resolve DB root via CLI/env/project-relative default.
- Discover `*.FDI` and `*.PKF` under the DB root.
- Load all discovered files fully into memory (payload + metadata).
- Expose an in-memory repository API for inspection, query, modification and commit.
- Reuse existing safe write logic for FDIs and add PKF writers.
- Provide safeguards (max-memory, warnings, dry-run).

New files & locations (implementation targets)
- [`app/datastore.py`](app/datastore.py:1) — core in-memory repository and loader.
- [`app/pkf.py`](app/pkf.py:1) — conservative PKF parser & serializer.
- Add helpers to [`app/io.py`](app/io.py:1): `FDIFile.from_bytes()` and `FDIFile.to_bytes()`.
- Reuse [`app/file_writer.py`](app/file_writer.py:1) for FDI in-memory writes; add a small wrapper if needed.
- Update CLI: [`app/cli.py`](app/cli.py:1) to accept `--db-root`, `--mode`, `--max-memory`, `--dry-run`.
- Tests: `tests/test_datastore.py` and `tests/test_pkf_parser.py`.

High-level architecture
- DataStore sits above the existing file readers/writers and provides an atomic view:
  - discovery -> bytes read -> FDIFile.from_bytes / PKFFile.from_bytes -> store in dictionaries
  - mutable in-memory objects; callers can inspect and modify.
  - commit/flush converts objects to bytes then writes atomically to disk (or returns bytes in dry-run).

DataStore API (detailed signatures)
- Class: [`DataStore`](app/datastore.py:1)
  - `def __init__(self, db_root: Path, mode: str = "eager", max_memory_bytes: Optional[int] = None, dry_run: bool = False):`
  - `def load_all(self) -> None:` Discover and eagerly load all FDI/PKF files into memory.
  - `def list_fdi(self) -> List[str]:` Return list of relative FDI paths (keys).
  - `def list_pkf(self) -> List[str]:`
  - `def get_fdi(self, path_or_name: str) -> FDIFile:`
  - `def get_pkf(self, path_or_name: str) -> PKFFile:`
  - `def query_players(self, name_substring: str) -> List[PlayerRecord]:` Shortcut across all FDIs.
  - `def save_fdi(self, fdi_path: str, write_to_disk: bool = True) -> bytes:` Return new bytes and optionally write.
  - `def save_pkf(self, pkf_path: str, write_to_disk: bool = True) -> bytes:`
  - `def stats(self) -> dict:` memory usage, file counts, total bytes.

FDI in-memory wrapper changes
- Add: [`FDIFile.from_bytes()`](app/io.py:1)
  - Signature: `@classmethod def from_bytes(cls, name: str, file_bytes: bytes, source_path: Optional[Path]=None) -> "FDIFile":`
  - Behaviour: parse header and directory, decode records into PlayerRecord instances (reuse existing parsing code).
- Add: [`FDIFile.to_bytes()`](app/io.py:1)
  - Signature: `def to_bytes(self) -> bytes:` Create updated file bytes by calling `save_modified_records()` semantics.
- Add: `def inspect_record(self, offset: int) -> dict:` Return raw_bytes, decoded_bytes, model and helpful previews.
- Keep `FDIFile.load()` for on-disk convenience.

PKF parser & wrapper
- New module: [`app/pkf.py`](app/pkf.py:1)
- Conservative parser goals:
  - Parse container header and TOC; do not attempt brittle decodes by default.
  - Store raw payload bytes for each entry and the entry metadata (name/index/offset/length).
- Class: `PKFFile`
  - `@classmethod def from_bytes(cls, name: str, file_bytes: bytes) -> "PKFFile"`
  - `def list_entries(self) -> List[PKFEntry]`
  - `def get_entry(self, name_or_index) -> PKFEntry`
  - `def replace_entry(self, name_or_index, new_bytes: bytes) -> None`
  - `def to_bytes(self) -> bytes` — rebuild TOC, adjust offsets, recompute checksums if present (conservative: preserve unknown fields if possible).
- Model: `PKFEntry` fields: index, name (optional), offset, length, raw_bytes, meta.

Discovery & eager load flow (line-by-line plan for [`DataStore.load_all()`](app/datastore.py:1))
1. Resolve `db_root` via helper `resolve_db_root(cli_arg, env="PM99_DB_ROOT", default=Path("DBDAT"))`.
2. Build lists: fdi_paths = sorted(db_root.rglob("*.FDI")), pkf_paths = sorted(db_root.rglob("*.PKF")).
3. For each path in combined list:
   - Read bytes: b = path.read_bytes()
   - If path.suffix.upper() == ".FDI": obj = FDIFile.from_bytes(path.name, b, source_path=path)
   - If path.suffix.upper() == ".PKF": obj = PKFFile.from_bytes(path.name, b)
   - Store objects in dictionaries keyed by relative path string; track original file size.
4. Maintain cumulative memory counter `self._total_bytes_loaded` and raise or warn if > `max_memory_bytes`.
5. Populate quick indices: player name -> (fdi_key, offset) for fast query.

Memory & safety guards
- Default `max_memory_bytes`: 512 * 1024 * 1024 (512MB). Environment override via `PM99_MAX_MEMORY`.
- If cumulative file bytes > `max_memory_bytes`:
  - With `--force` or `dry_run`, continue but warn.
  - Otherwise abort load_with a clear message and return partial state.
- Keep option to load with `--scan-only` (TOC/headers only) for recovery.

Save / commit flow (FDI specifics)
- To save an FDI object:
 1. Call `bytes_out = fdi_obj.to_bytes()` (which applies `save_modified_records()` semantics).
 2. If dry_run: return `bytes_out` without writing.
 3. Create backup file using [`app/file_writer.create_backup()`](app/file_writer.py:17).
 4. Write to a temporary file in the same directory (use `tempfile.NamedTemporaryFile(delete=False, dir=target.parent)`).
 5. Use `os.replace(temp_path, target_path)` for atomic swap.
 6. On Windows, optionally acquire an exclusive lock during write using `msvcrt.locking()` or `portalocker`.
- For PKF writes, use `pkf_obj.to_bytes()` then the same atomic-write steps.

CLI changes & UX
- Global options added to [`app/cli.py`](app/cli.py:1):
  - `--db-root DBROOT` (string)
  - `--mode {eager,lazy,hybrid}` (default `eager` for this plan)
  - `--max-memory BYTES`
  - `--dry-run` (flag)
- New subcommands:
  - `load-all` — eagerly load and print stats: total files, bytes, top 10 largest.
  - `list-pkf` — list pkf files and entry counts
  - `inspect` — inspect an FDI or PKF entry by path + offset/index
  - `export-pkf-entry` — write a PKF entry to disk (images, etc.)
- Example:
  - `python -m app load-all --db-root DBDAT --mode eager`

Tests
- `tests/test_datastore.py`
  - test_discovery_loads_all_fdi_pkf: create tmpdir with sample FDI/PKF, run DataStore.load_all(), assert counts and total bytes.
  - test_memory_limit_enforced: set max_memory_bytes low and assert DataStore raises or returns partial behaviour.
  - test_query_players_across_files: ensure `query_players()` returns expected PlayerRecord objects.
- `tests/test_pkf_parser.py`
  - roundtrip: PKFFile.from_bytes() -> modify an entry -> to_bytes() -> from_bytes() and compare entries.
- Extend `tests/test_file_writer.py` with in-memory save smoke test calling `FDIFile.to_bytes()`.

Developer scripts
- Update [`scripts/debug_write_and_inspect.py`](scripts/debug_write_and_inspect.py:1) to demonstrate:
  - ds = DataStore(Path("DBDAT/"), mode="eager"); ds.load_all()
  - print(ds.stats()); f = ds.get_fdi("JUG98030.FDI"); print(f.list_records()[:10])
  - example of modifying a player name and performing a dry-run save to produce new bytes.

Performance & profiling
- Add optional tracing hooks in DataStore to log load time per file (ms) and memory.
- Provide a `--profile` flag to dump simple CSV of filename, bytes, load_time.
- If memory usage too high during eager load, suggest fallback to hybrid mode.

Extension & plugin hooks
- `PKFFile` should expose a registry for decoders: `register_decoder(magic_bytes: bytes, decoder_fn)`.
- DataStore can accept a plugin list on init that allows file-type specific post-processing.

Backwards compatibility & migration notes
- Existing code that constructs `FDIFile(args.file)` remains valid.
- Add convenience factory `DataStore.from_local_paths([...])` to build a store for tests / REPL.
- Tests and CLI should adopt DataStore gradually — start by exposing a `load-all` dev command.

Implementation milestones (order)
1. Add `resolve_db_root()` and CLI flags in [`app/cli.py`](app/cli.py:1).
2. Implement [`app/datastore.py`](app/datastore.py:1) skeleton with discovery and simple metadata store.
3. Add `FDIFile.from_bytes()` and `FDIFile.to_bytes()` to [`app/io.py`](app/io.py:1).
4. Implement [`app/pkf.py`](app/pkf.py:1) conservative parser.
5. Wire `DataStore.load_all()` to fully load files into memory; enforce `max_memory_bytes`.
6. Add `save_fdi()` and `save_pkf()` flows using atomic replace and backups.
7. Add tests and minimal docs.

Rough estimate of effort
- Developer-time: 2–3 days for a robust first pass (datastore + FDI in-memory + tests).
- Additional 1–2 days for PKF writer, CLI polish and locking/atomic write hardening.
- Extra time for large-PKF performance work if needed.

Example usage (eager mode)
```
from pathlib import Path
from app.datastore import DataStore
ds = DataStore(Path("DBDAT/"), mode="eager", max_memory_bytes=1024*1024*1024)
ds.load_all()
print(ds.stats())
f = ds.get_fdi("JUG98030.FDI")
players = f.list_players()[:20]
# Inspect the first player's raw/decoded bytes
offset, player = players[0]
rec = f.inspect_record(offset)
print(rec["decoded"][:120])
# Dry-run save
new_bytes = ds.save_fdi("JUG98030.FDI", write_to_disk=False)
```

Notes and rationale
- Eager mode is ideal for interactive reverse engineering: it lets you patch, experiment, and rebuild quickly.
- The primary trade-off is memory; the plan includes a conservative default `max_memory_bytes` and a dry-run mode so destructive operations are optional.
- Reuse of existing functions (notably [`save_modified_records()`](app/file_writer.py:180)) minimizes risk.

Next steps
- If you want, I can:
  - generate the initial skeleton for [`app/datastore.py`](app/datastore.py:1) and [`app/pkf.py`](app/pkf.py:1),
  - or implement `FDIFile.from_bytes()` in-place in [`app/io.py`](app/io.py:1).

Choose which file skeleton should be created first.
