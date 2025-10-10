# Getting Started — PM99 Database Editor

Audience
Engineers new to this repository who need a concise path to explore, inspect, and make safe edits to Premier Manager 99 database files.

What you can do in 10 minutes
- Inspect file metadata and counts with the CLI
- List and search players
- Understand the core architecture and where to look next
- Run tests to validate the pipeline works on your machine

Prerequisites
- Python 3.8+
- Run all commands from the repository root
- Sample data is in [DBDAT/](../DBDAT/)

1) Quick tour (60 seconds)
CLI entry point and commands are implemented in:
- Entry: [cli.main()](../app/cli.py:89)
- Commands: [cli.cmd_info()](../app/cli.py:74), [cli.cmd_list()](../app/cli.py:10), [cli.cmd_search()](../app/cli.py:22), [cli.cmd_rename()](../app/cli.py:38)

Show file info
```
python -m app info DBDAT/JUG98030.FDI
```

List players (limit results)
```
python -m app list DBDAT/JUG98030.FDI --limit 20
```

Search by name (case-insensitive substring)
```
python -m app search DBDAT/JUG98030.FDI "Ronaldo"
```

Rename by record id (same-length recommended)
```
python -m app rename DBDAT/JUG98030.FDI --id 123 --name "Cristiano Ronaldo"
```

2) Safety first (backups and integrity)
- The writer creates backups with [file_writer.create_backup()](../app/file_writer.py:17)
- In-place record writes adjust directory offsets via [file_writer.write_fdi_record()](../app/file_writer.py:102)
- Parsing and writing are conservative by design:
  - Parser: [PlayerRecord.from_bytes()](../app/models.py:63)
  - Serializer: [PlayerRecord.to_bytes()](../app/models.py:281)
  - I/O wrapper: [FDIFile.load()](../app/io.py:31), [FDIFile.save()](../app/io.py:269)

3) Core mental model (2 minutes)
- File format header and directory are represented by:
  - [FDIHeader.from_bytes()](../app/models.py:389) / [FDIHeader.to_bytes()](../app/models.py:412)
  - [DirectoryEntry.from_bytes()](../app/models.py:434) / [DirectoryEntry.to_bytes()](../app/models.py:442)
- Records are decoded from sections using XOR-0x61; see:
  - Section scanning and decoding: [FDIFile._iter_records()](../app/io.py:63)
- Player record parsing is dynamic:
  - Names parsed from early bytes, then a name-end marker 'aaaa' (0x61*4) is detected by [PlayerRecord._find_name_end()](../app/models.py:261)
  - Position, nationality, DOB and height are read relative to name-end
  - Attributes are taken from a fixed tail window (double-XOR)
- Most unknown bytes are preserved verbatim during writes by basing serialization on the original [PlayerRecord.raw_data](../app/models.py:59)

4) Typical workflows
Inspect file content from Python REPL
```
python -q
>>> from app.io import FDIFile
>>> f = FDIFile("DBDAT/JUG98030.FDI"); f.load()
>>> len(f.records), f.records[0]
```
Helpful helpers: [FDIFile.list_players()](../app/io.py:338), [FDIFile.find_by_name()](../app/io.py:229), [FDIFile.find_by_id()](../app/io.py:211)

Replace text in decoded payloads (advanced)
- Use [file_writer.replace_text_in_decoded()](../app/file_writer.py:32) to prepare a decoded buffer
- Then persist the new payload with [file_writer.write_fdi_record()](../app/file_writer.py:102)

5) Running tests
Execute from repository root:
```
pytest -q
```
Relevant tests/examples for exploration:
- IO/decoding: [tests/test_core_io_decoding.py](../tests/test_core_io_decoding.py)
- Writer behavior: [tests/test_file_writer.py](../tests/test_file_writer.py)
- Roundtrip and integration: [tests/test_integration_roundtrip.py](../tests/test_integration_roundtrip.py)
- Debug/inspection helpers: [tests/test_debug_inspect.py](../tests/test_debug_inspect.py), [tests/test_hex_dump.py](../tests/test_hex_dump.py)

6) Where to read next
- User guide (practical editing): [docs/EDITOR_README.md](./EDITOR_README.md)
- Architecture overview: [docs/ARCHITECTURE.md](./ARCHITECTURE.md)
- Data formats and field mapping: [docs/DATA_FORMATS.md](./DATA_FORMATS.md)
- Reverse engineering narrative (condensed): [docs/REVERSE_ENGINEERING_REPORT.md](./REVERSE_ENGINEERING_REPORT.md)
- Development playbook (tests, scripts, CLI): [docs/DEVELOPER_GUIDE.md](./DEVELOPER_GUIDE.md)

7) Troubleshooting
- “Player not found” — list first: `python -m app list DBDAT/JUG98030.FDI --limit 50` and copy exact casing
- “Length mismatch/corruption risk” — keep names same length or use padding strategies in [file_writer.replace_text_in_decoded()](../app/file_writer.py:32), then persist through [file_writer.write_fdi_record()](../app/file_writer.py:102)
- Restoring files — use the `.backup` created by [file_writer.create_backup()](../app/file_writer.py:17)

8) Scope and limitations (honest status)
- The parser focuses on “clean” records in decoded sections and uses conservative heuristics for edge cases
- Unknown bytes and structures are preserved round‑trip
- Advanced write paths should be driven through record‑level serialization [PlayerRecord.to_bytes()](../app/models.py:281) + safe write [file_writer.write_fdi_record()](../app/file_writer.py:102)

9) Contributing
- Keep canonical docs concise under [docs/](./)
- Archive verbose notes in [docs/archive/](archive/) and cross‑link as references
- When adding fields or offsets, document them briefly in [docs/DATA_FORMATS.md](./DATA_FORMATS.md) with precise byte rules and a minimal test
