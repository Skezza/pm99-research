# Data Formats — FDI Containers and Player Records

Scope
Canonical reference for the Premier Manager 99 database formats used by this project:
- FDI container header and directory
- Section decode (XOR-0x61)
- Player record detection and decoded record layout
- Stable byte-level rules and invariants for safe parsing and writing

FDI container (header and directory)
- Header model and parsing:
  - Class: [FDIHeader](../pm99_editor/models.py:377)
  - Parser: [FDIHeader.from_bytes()](../pm99_editor/models.py:389)
  - Serializer: [FDIHeader.to_bytes()](../pm99_editor/models.py:412)
- Directory entries:
  - Model: [DirectoryEntry](../pm99_editor/models.py:423)
  - Parser: [DirectoryEntry.from_bytes()](../pm99_editor/models.py:434)
  - Serializer: [DirectoryEntry.to_bytes()](../pm99_editor/models.py:442)

Header layout (observed)
- Signature: ASCII "DMFIv1.0"
- record_count: uint32 LE at 0x10 (informational)
- version: uint32 LE at 0x14
- max_offset: uint32 LE at 0x18 (end-of-last-record marker; updated when writing)
- dir_size: uint32 LE at 0x1C (size in bytes, 8 bytes per directory entry)
- Directory table starts at 0x20; each entry packs:
  - offset: uint32 LE (absolute file position of section/record)
  - tag: uint16 LE
  - index: uint16 LE

Decode and section scanning
- Top-level I/O wrapper: [FDIFile](../pm99_editor/io.py:15)
  - Load header and directory: [FDIFile.load()](../pm99_editor/io.py:31), [FDIFile._parse_directory()](../pm99_editor/io.py:47)
  - Iterate sections, decode and enumerate records: [FDIFile._iter_records()](../pm99_editor/io.py:63)
- Section format (raw on disk):
  - [length_le: uint16] + [payload_len bytes XOR-0x61]
  - Decode rule: decoded_byte = encoded_byte ^ 0x61
- Player separator (inside decoded section buffers):
  - Bytes: dd 63 60 (3 bytes), used to split “clean” player records prior to per-record parsing

Player record — decoded layout (canonical)
The decoded (per-record) bytes parsed by the model [PlayerRecord.from_bytes()](../pm99_editor/models.py:63) use a dynamic anchor around the name. Stable invariants:

- Leading fields (fixed offsets from start of decoded record):
  - +0..1: team_id (uint16 LE)
  - +2: squad_number (uint8)
  - +3..4: implementation-defined (ignored/preserved)
  - +5..~45: name region (Latin-1 text; given name + SURNAME extracted by heuristics)

- Name-end anchor:
  - Marker: 0x61 0x61 0x61 0x61 (“aaaa”)
  - Found by [PlayerRecord._find_name_end()](../pm99_editor/models.py:261)
  - All following metadata offsets are relative to this anchor

- Double-XOR encoded metadata (anchor-relative; value = byte ^ 0x61):
  - name_end + 7: position_primary (0=GK, 1=DEF, 2=MID, 3=FWD) — extracted in [PlayerRecord._extract_position()](../pm99_editor/models.py:269)
  - name_end + 8: nationality (0..255)
  - name_end + 9: birth_day (1..31)
  - name_end + 10: birth_month (1..12)
  - name_end + 11..12: birth_year (uint16 LE across two bytes, both double-XOR)
  - name_end + 13: height (cm; typical 150..210). Weight not yet a stable single-byte field in the decoded clean-record layout; default preserved.

- Attributes window (tail-relative; double-XOR):
  - Start: len(decoded) - 19
  - End (exclusive): len(decoded) - 7
  - Count: 12 bytes window; first 10 bytes interpreted as skills by [PlayerRecord.from_bytes()](../pm99_editor/models.py:129), and written by [PlayerRecord.to_bytes()](../pm99_editor/models.py:351)
  - Range: 0..100 per attribute
  - Invariants: Writer only sets bytes within the window and within valid numeric range

- Unknown/preserved data:
  - All unrecognized bytes are retained via [PlayerRecord.raw_data](../pm99_editor/models.py:59) and overlaid during [PlayerRecord.to_bytes()](../pm99_editor/models.py:281)

Extraction semantics and name parsing
- The name region (roughly +5..~45) is parsed with robust heuristics to reconstruct "Given SURNAME" while tolerating noise and abbreviations. See [PlayerRecord._extract_name()](../pm99_editor/models.py:192).
- The four-‘a’ marker (“aaaa”) serves as the stable pivot for all metadata offsets and is searched in a bounded early window. See [PlayerRecord._find_name_end()](../pm99_editor/models.py:261).

Writer, backups and directory integrity
- In-memory serialization overlays only known fields into the preserved raw bytes: [PlayerRecord.to_bytes()](../pm99_editor/models.py:281)
- File write:
  - Backups: [file_writer.create_backup()](../pm99_editor/file_writer.py:17)
  - Replace a record and adjust directory offsets + header.max_offset: [file_writer.write_fdi_record()](../pm99_editor/file_writer.py:102)
- Safety:
  - Header and directory re-encoded with updated offsets; header bytes overwritten with [FDIHeader.to_bytes()](../pm99_editor/models.py:412)

CLI and practical usage
- Commands:
  - [cli.cmd_info()](../pm99_editor/cli.py:74): header, counts
  - [cli.cmd_list()](../pm99_editor/cli.py:10): formatted list of players
  - [cli.cmd_search()](../pm99_editor/cli.py:22): substring match with de-dup heuristics
  - [cli.cmd_rename()](../pm99_editor/cli.py:38): modifies record and persists via [FDIFile.save()](../pm99_editor/io.py:269) or low-level writer
- Entry point: [cli.main()](../pm99_editor/cli.py:89)

Field ranges and invariants (write-time validation)
- team_id: uint16 LE (typical 3712..3807; impl may normalize implausible values to 0 when enumerating)
- squad_number: uint8 (96..119 observed in clean data)
- position_primary: 0..3 (GK/DEF/MID/FWD)
- nationality: 0..255 (code system TBD)
- birth_day: 1..31; birth_month: 1..12; birth_year: 1900..1999 preferred, default fallback used if out-of-range
- height: 50..250 cm (further validation recommended)
- attributes: 0..100; writer clamps by only writing valid-range values in the tail window

Heuristics and edge cases
- Section filtering in [FDIFile._iter_records()](../pm99_editor/io.py:63) uses plausible section length ranges before attempting XOR decode to avoid false positives
- “Clean” records are prioritized using length and structure checks; embedded/edge-case records are discovered via additional heuristics with conservative acceptance
- If the name-end anchor cannot be found, metadata fields fall back to safe defaults and are not written

References and further reading
- Detailed player field mapping (narrative): [docs/PLAYER_FIELD_MAP.md](./PLAYER_FIELD_MAP.md)
- Reverse engineering handover (binary-level story): [docs/REVERSE_ENGINEERING_HANDOVER.md](./REVERSE_ENGINEERING_HANDOVER.md)
- Final report (historical narrative): [docs/REVERSE_ENGINEERING_FINAL_REPORT.md](./REVERSE_ENGINEERING_FINAL_REPORT.md)
- Legacy schema notes (Ghidra-centric, historical): [out/schema_players.md](../out/schema_players.md) — superseded by this document and the code references above

Related code index
- Models
  - [PlayerRecord](../pm99_editor/models.py:13), [PlayerRecord.from_bytes()](../pm99_editor/models.py:63), [PlayerRecord.to_bytes()](../pm99_editor/models.py:281)
  - [FDIHeader](../pm99_editor/models.py:377), [FDIHeader.from_bytes()](../pm99_editor/models.py:389), [FDIHeader.to_bytes()](../pm99_editor/models.py:412)
  - [DirectoryEntry](../pm99_editor/models.py:423), [DirectoryEntry.from_bytes()](../pm99_editor/models.py:434)
- I/O
  - [FDIFile](../pm99_editor/io.py:15), [FDIFile.load()](../pm99_editor/io.py:31), [FDIFile._iter_records()](../pm99_editor/io.py:63), [FDIFile.save()](../pm99_editor/io.py:269)
- Writer
  - [file_writer.create_backup()](../pm99_editor/file_writer.py:17), [file_writer.replace_text_in_decoded()](../pm99_editor/file_writer.py:32), [file_writer.write_fdi_record()](../pm99_editor/file_writer.py:102)