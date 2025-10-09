# Reverse Engineering Report — Condensed Narrative

Purpose
A single, high-signal account of what is known, why it is believed, and how it is implemented in code. This is the canonical summary; verbose session logs remain in out/ as artifacts.

Scope
- Container format (FDI header, directory)
- Decode algorithm and section iteration
- Player record detection and decoded layout
- Validated fields vs heuristics
- Practical reliability and limitations
- Next actions

Executive summary
- FDI container is little‑endian with a fixed 0x20‑byte header and variable directory of 8‑byte entries (offset, tag, index).
- Sections store XOR‑0x61 encoded payloads prefixed by length (uint16 LE). Decoded section buffers contain multiple “clean” player records split by dd 63 60.
- Per‑record parsing relies on a name‑end marker “aaaa” (0x61 ×4) to compute dynamic offsets for metadata (position, nationality, DOB, height).
- Attributes live in a fixed tail window of the decoded record and are double‑XOR bytes in 0..100. Unknown bytes are preserved bit‑exact during write.
- Implementation is conservative: only write within verified bounds; preserve unknowns; adjust directory and header on disk writes.

Source of truth in code
- Section scanning and record enumeration: [FDIFile._iter_records()](../pm99_editor/io.py:63)
- Record parse/serialize overlay: [PlayerRecord.from_bytes()](../pm99_editor/models.py:63), [PlayerRecord.to_bytes()](../pm99_editor/models.py:281)
- Header and directory models: [FDIHeader.from_bytes()](../pm99_editor/models.py:389), [DirectoryEntry.from_bytes()](../pm99_editor/models.py:434)
- Safe write path: [file_writer.write_fdi_record()](../pm99_editor/file_writer.py:102) with backups via [file_writer.create_backup()](../pm99_editor/file_writer.py:17)
- CLI entry: [cli.main()](../pm99_editor/cli.py:89); GUI app entry: [main()](../pm99_database_editor.py:1189)

Container format (observed)
- Signature: "DMFIv1.0" at 0x00..0x07
- record_count (uint32 LE) at 0x10; version (uint32 LE) at 0x14; max_offset (uint32 LE) at 0x18; dir_size (uint32 LE) at 0x1C
- Directory table at 0x20, dir_size bytes long; entries are 8 bytes <offset:uint32, tag:uint16, index:uint16>
- Sections at entry.offset, each: <len:uint16> + <payload_len XOR‑0x61>
- On write, directory offsets after a changed record are shifted; max_offset recomputed. See [file_writer.write_fdi_record()](../pm99_editor/file_writer.py:102).

Decode algorithm and enumeration
- Section payload decode: decoded[i] = encoded[i] ^ 0x61
- FDI iteration (simplified):
  - Scan from 0x400
  - Read uint16 len, filter plausible size, decode payload
  - Split on separator dd 63 60 to yield candidate “clean” player records
  - For each candidate 50..200 bytes, attempt [PlayerRecord.from_bytes()](../pm99_editor/models.py:63)
- Heuristic second pass searches large sections for embedded players (name fragments + marker alignment) and accepts only plausible records (attributes within 0..100, position 0..3).

Decoded player record layout (canonical)
- Leading fixed fields:
  - +0..1 team_id (uint16 LE)
  - +2 squad_number (uint8)
  - +5..~45 name region (Latin‑1); “Given SURNAME” reconstructed by robust pattern matching
- Name‑end anchor:
  - Marker “aaaa” (0x61 ×4) found by [PlayerRecord._find_name_end()](../pm99_editor/models.py:261)
- Anchor‑relative, double‑XOR metadata:
  - name_end + 7 → position_primary in {0,1,2,3}
  - name_end + 8 → nationality (0..255 code)
  - name_end + 9/10/11..12 → birth_day, birth_month, birth_year (uint16 LE across 11..12)
  - name_end + 13 → height (cm)
- Tail‑relative attributes (double‑XOR):
  - Window len-19 .. len-7 (12 bytes); first 10 interpreted as skills; values 0..100
- Unknown bytes:
  - Preserved verbatim via [PlayerRecord.raw_data](../pm99_editor/models.py:59) and overlay write in [PlayerRecord.to_bytes()](../pm99_editor/models.py:281)

Validation and invariants
- Write only if anchor is found and offsets fall before attribute window
- Attributes written only within tail window; values clamped by accepting 0..100
- team_id is uint16 LE; listing may normalize implausible values to 0 for display
- Directory and header integrity enforced on writes (offset shifts and max_offset recompute)

What is confirmed vs heuristic
Confirmed
- XOR‑0x61 section decode and separator dd 63 60 within decoded buffers
- team_id, squad_number at +0..2
- Name parsing window and name‑end marker used as anchor
- Attributes window at tail, double‑XOR 0..100 values

Heuristic but robust
- Name reconstruction patterns in [PlayerRecord._extract_name()](../pm99_editor/models.py:192)
- Embedded record detection in large sections (accepted only when attributes and position validate)
- Nationality code range (0..255) without a complete mapping table yet

Limitations and cautions
- Not all records in all sections are “clean”; embedded/edge‑case records need heuristic alignment
- If the anchor cannot be found, metadata is left at defaults and not written
- Some historical documents claim different algorithms (e.g., conflicting “single vs double XOR” narratives). Treat this report and code anchors as canonical.

Practical usage
- Programmatic access via [FDIFile](../pm99_editor/io.py:15) and [PlayerRecord](../pm99_editor/models.py:13)
- CLI for inspection and name edits by id in [cli.main()](../pm99_editor/cli.py:89)
- GUI application entry [main()](../pm99_database_editor.py:1189) for interactive workflows
- Safe persistence via [file_writer.write_fdi_record()](../pm99_editor/file_writer.py:102)

Next actions (ordered)
- Add a nationality mapping table; keep writing numeric codes until mapped
- Harden attribute labeling (order names) with sampled in‑game validation
- Extend tests to cover embedded record alignment and failure modes
- Document any newly confirmed offsets in [docs/DATA_FORMATS.md](./DATA_FORMATS.md) and add unit tests

References (legacy artifacts)
- Loader and decode summary: [../out/README.md](../out/README.md)
- Cross‑binary triangulation: [../out/triangulation.md](../out/triangulation.md)
- Verify snapshots: [../out/verify.txt](../out/verify.txt)
- Historical Ghidra schema notes: [../out/schema_players.md](../out/schema_players.md) — superseded by code + this report

Relationship to other canonical docs
- Formats and byte rules: [docs/DATA_FORMATS.md](./DATA_FORMATS.md)
- Detailed mapping supplement: [docs/PLAYER_FIELD_MAP.md](./PLAYER_FIELD_MAP.md)
- Getting started and workflows: [docs/GETTING_STARTED.md](./GETTING_STARTED.md)
- Architecture overview: [docs/ARCHITECTURE.md](./ARCHITECTURE.md)

Status and ownership
- This document is maintained alongside code changes affecting parsing or writing
- When code anchors change, update the line references above in the same commit

Versioning
- Track user‑visible documentation changes in [docs/CHANGELOG.md](./CHANGELOG.md)
- Keep legacy narratives unchanged in out/ for provenance