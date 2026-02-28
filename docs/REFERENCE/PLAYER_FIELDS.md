# Player Fields Reference

This is the authoritative player-record field reference for the current codebase.

For container-level rules, use [../DATA_FORMATS.md](../DATA_FORMATS.md). For implementation details, cross-check [../../app/models.py](../../app/models.py), [../../app/io.py](../../app/io.py), and [../../app/file_writer.py](../../app/file_writer.py).

## Scope

This document describes the player data that the project can currently parse or write conservatively from `JUG98030.FDI`.

## Record Anchors

- Player data lives inside `.FDI` entry payloads and is parsed by `PlayerRecord.from_bytes()`.
- `team_id` is stored at bytes `0-1` (little-endian).
- `squad_number` is stored at byte `2`.
- The name region starts after byte `4`.

The current parser supports two complementary ideas:
- It first attempts a structured name read from the payload at offset `5` using two sequential length-prefixed strings (given name, then surname).
- Each structured string is stored as `uint16 length` followed by `length` bytes of `0x61`-XOR'd text.
- When structured parsing is incomplete or suspicious, it falls back to conservative name heuristics.

Reverse-engineering notes and Ghidra validation indicate that the original game reads player records sequentially after the two strings. The `0x61 0x61 0x61 0x61` (`aaaa`) marker is therefore a conservative implementation anchor in the current write path, not a proven format boundary.

## Confirmed Parser-Backed Fields

## Identity

- `team_id`
  - Bytes `0-1`
  - Type: `uint16` little-endian
- `squad_number`
  - Byte `2`
  - Type: `uint8`
- `given_name`, `surname`, `name`
  - Extracted from the name region beginning at byte `5`
  - Backed by the raw payload so unknown surrounding bytes can be preserved

## Metadata (current conservative write anchor)

The current codebase rewrites these fields relative to the `aaaa` anchor when it can be found safely. This is a write-safety rule, not a claim that the underlying format is marker-based:

- `position_primary`
  - `marker + 7`
  - Stored XOR’d (`value ^ 0x61`)
- `nationality`
  - `marker + 8`
  - Stored XOR’d
- `birth_day`
  - `marker + 9`
  - Stored XOR’d
- `birth_month`
  - `marker + 10`
  - Stored XOR’d
- `birth_year`
  - `marker + 11` and `marker + 12`
  - Little-endian, XOR’d bytewise
- `height`
  - `marker + 13`
  - Stored XOR’d

## Attributes

- The current parser reads up to 12 skill bytes from the trailing attribute window.
- The effective window is `len(payload) - 19` through `len(payload) - 7`.
- Each byte is XOR’d with `0x61` after outer payload decoding.
- Missing values are padded conservatively in memory for compatibility.

## Write Rules and Constraints

- Preserve `raw_data` whenever possible; unknown bytes should survive unchanged.
- Do not assume arbitrary player-name expansion is safe.
- Metadata writes must not happen if the `aaaa` anchor cannot be located.
- Attribute writes must remain within the trailing attribute window.
- If a write would change record size, directory offsets and header state must be updated through the existing safe writers.

## Known / Partial / Unknown

## Known

- `team_id`
- `squad_number`
- name region handling
- `position_primary`
- `nationality`
- `birth_day`
- `birth_month`
- `birth_year`
- `height`
- trailing attribute window

## Partial

- The exact internal name encoding varies across records; the parser handles multiple shapes conservatively.
- The meaning of all 12 trailing skill bytes is not fully stabilized as a user-facing field contract.

## Unknown or Not Yet Safe

- Weight
- Contract-related fields
- Any unknown metadata bytes outside the confirmed offsets
- Structural rewrites that rely on undocumented player-record variants

## Safety Notes

- Historical investigations showed that player-name storage is structurally sensitive. Incorrect assumptions about string layout can corrupt the file.
- The original game appears to read the record sequentially, so name edits and metadata edits should be treated as whole-record structural work, not arbitrary byte pokes around a presumed delimiter.
- Current write paths should therefore be treated as conservative overlays, not as permission to freely synthesize or reflow record internals.
