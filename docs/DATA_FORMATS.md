# Premier Manager 99 Data Formats

This document captures the canonical format rules that the codebase implements today. When new structures are reverse engineered, update this file alongside the parsers in [`pm99_editor/models.py`](../pm99_editor/models.py), [`pm99_editor/io.py`](../pm99_editor/io.py), and [`pm99_editor/file_writer.py`](../pm99_editor/file_writer.py).

## FDI container files
Premier Manager 99 ships multiple `.FDI` databases. The editor currently focuses on:
- `JUG98030.FDI` — player data (default file opened by the GUI and CLI)
- `ENT98030.FDI` — coaches/managers (lazy-loaded in the GUI)
- `EQ98030.FDI` — teams and stadium metadata

Each file has the following structure:

1. **Header (`0x20` bytes)** — parsed by [`FDIHeader.from_bytes()`](../pm99_editor/models.py#L1286):
   | Offset | Size | Field | Notes |
   | --- | --- | --- | --- |
   | `0x00` | 8 | Signature | Always `b'DMFIv1.0'`; mismatches abort loading. |
   | `0x10` | 4 | `record_count` | Total directory entries seen in the original game. Some dumps use `0`. |
   | `0x14` | 4 | `version` | Typically `2` for these assets. |
   | `0x18` | 4 | `max_offset` | Highest byte offset touched by any entry; recomputed on save. |
   | `0x1C` | 4 | `dir_size` | Size of the directory table in bytes. |

2. **Directory table** — `dir_size` bytes starting at `0x20`, consisting of 8-byte records decoded by [`DirectoryEntry.from_bytes()`](../pm99_editor/models.py#L1318):
   | Offset | Size | Field |
   | --- | --- | --- |
   | `+0` | 4 | `offset` (little endian) — points to the encoded payload (length prefix).
   | `+4` | 2 | `tag` — ASCII code identifying the entry type (`'P'` for player, `'T'` for team, `'C'` for coach, `'N'`, `'G'`, etc. appear in raw dumps).
   | `+6` | 2 | `index` — ordinal value the original game expected.

3. **Entry payloads** — each directory entry references a length-prefixed XOR blob:
   - `[uint16 length]` followed by `length` bytes encoded with `byte ^ 0x61` (`decode_entry()` / `encode_entry()`).
   - The editor stores both the decoded payload and the original encoded bytes so writes can preserve unknown regions.

The directory is often incomplete; `FDIFile.load()` augments player records by scanning the entire decoded file through [`find_player_records()`](../pm99_editor/scanner.py) so hidden or duplicate payloads become visible in the UI.

## Player records (`JUG98030.FDI`)
Player payloads are variable-length and contain a mix of plain and XOR-obfuscated fields. [`PlayerRecord.from_bytes()`](../pm99_editor/models.py#L560) implements the canonical parser. Key layout details:

| Region | Description |
| --- | --- |
| Bytes `0-1` | `team_id` (little-endian uint16). Values >5000 are treated as corrupt and normalised to `0`.
| Byte `2` | `squad_number`.
| Byte `3` | Record flags (often `0x61`). Preserved but not currently decoded.
| Byte `4` | Separator / alignment byte (usually `0x61`).
| Bytes `5..` | Player name in CP1252. Parsing stops when a sentinel `0x61 0x61 0x61 0x61` sequence ("aaaa") is found.
| Sentinel + 7 | Primary position code. Stored XOR'd (`value ^ 0x61`) even after the outer decode; the parser reverses this dynamically.
| Sentinel + 8 | Nationality code (`value ^ 0x61`).
| Sentinel + 9/10 | Birth day/month (`value ^ 0x61`).
| Sentinel + 11/12 | Birth year (two bytes interpreted as little-endian and XOR'd with `0x61`).
| Sentinel + 13 | Height in cm (`value ^ 0x61`).
| Final 12 bytes before tail | Skill attributes. The parser walks from `len(payload) - 19` to `len(payload) - 7`, XORing each byte to yield up to 12 attributes. Missing attributes are padded with default `50` values for backwards compatibility.

Additional observations:
- The parser splits the decoded name into `given_name` and `surname` but preserves the raw payload to avoid losing unknown bytes on write.
- `PlayerRecord` stores a `raw_data` copy; editing flows mark `name_dirty` when textual regions are changed so the serializer can rebuild the encoded byte window.
- `save_modified_records()` and `write_fdi_record()` re-encode the entire payload and adjust directory offsets if the encoded length changes.

## Team records (`EQ98030.FDI`)
[`TeamRecord`](../pm99_editor/models.py#L13) represents the partially-understood structure:
- Records often start with a 3-byte separator `0x61 0xDD 0x63` followed by padding before the uppercase team name.
- The parser scans for the first uppercase ASCII run to locate the name, stopping when it encounters lowercase `a` separators or non-printable characters.
- Stadium names follow the team name and are extracted from printable spans containing keywords like "stadium", "ground", "park", etc.
- Team IDs are heuristically detected by scanning for 16-bit integers in the `3000-5000` range.
- Stadium metadata (capacity, parking, pitch quality) is parsed from substrings inside the stadium description when available.

Edits replace text slices inside the `raw_data` buffer; the GUI keeps offsets so stadium and team names can be updated without corrupting other bytes.

## Coach records (`ENT98030.FDI`)
[`CoachRecord`](../pm99_editor/models.py#L434) decodes a simpler structure:
- After an initial flag byte, two length-prefixed strings are stored back-to-back.
- Each string is encoded as `[uint16 length]` followed by bytes XOR'd with `0x61` in 32-bit chunks. `_decode_string_32bit()` reverses this and trims trailing nulls.
- The GUI exposes fields for given name and surname and writes changes through `set_name()`, which rebuilds the encoded string blocks in-place.

The current implementation leaves `coach_id` as `0` because the source material has not revealed a stable identifier yet.

## PKF archives
Some GUI tooling surfaces PKF container files. [`PKFFile`](../pm99_editor/pkf.py) uses the same XOR helpers to decode entries and presents:
- Archive header with entry count and offsets.
- Individual entries that can be previewed with `_format_hex_preview()` inside the GUI's PKF viewer.

## Encoding rules recap
- XOR key is always `0x61`. Container payloads use one layer; certain in-record fields (positions, nationality, DOB, attributes) are XOR'd a second time relative to the sentinel.
- Strings are CP1252. Null terminators are commonly present after XOR decoding and should be stripped before display.
- Length fields are little-endian.
- When increasing payload sizes, directory offsets and `header.max_offset` must be updated (handled automatically by `file_writer.write_fdi_record()` and `save_modified_records()`).

Keep tests such as [`tests/test_core_io_decoding.py`](../tests/test_core_io_decoding.py) and [`tests/test_serialization.py`](../tests/test_serialization.py) updated whenever new insights refine these rules.
