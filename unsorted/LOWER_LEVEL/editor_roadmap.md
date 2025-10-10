# PM99 Database Editor Roadmap

## Current Reverse-Engineering Evidence

- **Decode parity confirmed:** `out/decode_one.py` reproduces MANAGPRE.EXE’s `decode_data_xor61` logic. Running `python out/decode_one.py DBDAT/TEXTOS.PKF 0x0 --out textos_0000.bin` emits the Portuguese name roster visible in CP1252, proving we can round-trip TEXTOS entries.
- **Structural groundwork:** [`out/struct_notes.md`](out/struct_notes.md:1-127) documents the FDI header, directory entries, and sample decoded payload (offset `0x000410`), while [`out/verify.txt`](out/verify.txt:1-53) records before/after hexdumps for both FDI and TEXTOS resources.
- **Cross-binary agreement:** [`out/triangulation.md`](out/triangulation.md:1-30) shows DBASEPRE importing the same XOR helper, validating that the decoded buffers we produce match the game’s own consumer.
- These assets confirm we can read and interpret real game data; the remaining effort is to formalize record layouts, provide encode/write paths, and wrap them in editing tooling.


In-progress items (latest session):
- Player record byte mapping underway; raw observations captured in [`out/struct_notes.md`](out/struct_notes.md:110-136).
- Awaiting field-label confirmation before generating dataclasses and writer logic.

This document outlines the steps required to evolve the current reverse-engineering assets into a functional database editor that can read, modify, and write `.FDI` and `TEXTOS.PKF` content—starting with renaming a player and gradually expanding toward broader attribute editing.

---

## 1. Formalise Record Structures

1. **Capture record schemas**  
   - Use `FUN_004a0370` / `FUN_004afd80` decompilation to map field offsets, their conditional inclusion (build/version checks), and data types (byte vs string vs numeric).
   - Document each field with:
     - Offset relative to decoded buffer.
     - Length / type.
     - Inter-field dependencies (e.g., optional sub-block lengths).
     - Encoding (e.g., CP1252, custom charmap IDs).

2. **Create Python dataclasses**  
   - Represent players, teams, coaches as structured types (e.g., `PlayerRecord`).  
   - Provide `from_bytes` / `to_bytes` helpers aligned with the struct definitions.

3. **Charset handling**  
   - Leverage `HW-Charmap.map` to ensure non-ASCII glyphs round-trip correctly.  
   - Abstract encoding/decoding (e.g., `encode_text(raw: str) -> bytes`, `decode_text(buf: bytes) -> str`).

---

## 2. File I/O Abstractions

1. **Directory reader/writer**  
   - Expand `decode_one.py` into a module (e.g., `pm99/io.py`) that:
     - Parses the FDI header, validates offsets, and yields typed records.
     - Maintains metadata (record count, directory offsets) so changes can be saved.

2. **Writer support**  
   - Implement `encode_data_xor61` (inverse of the current decode) to regenerate XOR’d payloads.  
   - Rebuild directory offset table after modifications; ensure alignment/padding matches original layout.

3. **Integrity checks**  
   - After write-back, re-run the decode pipeline on the output file and confirm:
     - Record count matches.
     - Checksums (if any) or sentinel values remain valid.
     - Loading the modified file in MANAGPRE/DBASEPRE succeeds (smoke test).

---

## 3. Editing Workflow (Command-line)

1. **CLI entry point**  
   - Create `app.py` with subcommands:
     - `list players` → display player IDs/names.
     - `rename --id <idx> --name "New Name"` → modify name field.
     - Future: `set-attr --id <idx> --field speed --value 87`.

2. **Transaction handling**  
   - Load once, apply changes to in-memory dataclasses, then call `write_fdi(path, records, metadata)`.

3. **Backups & logging**  
   - Automatically copy original file to `<file>.bak`.
   - Emit a change log summarising modifications.

---

## 4. GUI Considerations (Optional Future Phase)

1. **Lightweight UI stack**  
   - Consider Python + Tkinter/PySimpleGUI for cross-platform editing.  
   - Provide tabbed views for players, teams, coaches, and text resources.

2. **Validation & Constraints**  
   - Enforce field length limits (name length, numeric ranges).
   - Prompt user when edits might violate engine expectations (e.g., reserved codes).

---

## 5. Testing Strategy

1. **Unit tests**  
   - Round-trip encode/decode tests for sample records (fixtures derived from `verify.txt`).  
   - Regression tests comparing raw binary slices before/after modifications (excluding edited segments).

2. **In-game validation**  
   - After renaming a player, launch MANAGPRE and verify UI shows the updated name without crashes.  
   - For attribute edits, verify the change reflects in match simulations or scouting screens.

---

## 6. Implementation Sequencing

1. **Phase A – Reader**  
   - Finish struct documentation (`out/struct_notes.md` expansion).  
   - Build reader that enumerates records and prints friendly summaries.

2. **Phase B – Writer + Rename**  
   - Implement encoder and directory rebuild.  
   - Expose `rename-player` CLI that updates the name field only.

3. **Phase C – Attribute Editing**  
   - Extend dataclasses and CLI/UI to modify core stats.  
   - Add validation & value constraints.

4. **Phase D – TEXTOS integration**  
   - Apply the same framework to `TEXTOS.PKF` inner files (e.g., names, countries).  
   - Provide editing for text resources referencing player names/nationalities.

---

## 7. Tooling & Reuse

- Reuse existing modules:
  - `out/decode_one.py` → convert into a package (`pm99/xor.py`).
  - Verification artefacts → become fixtures for tests.

- Build documentation (markdown) showing CLI usage and mapping between in-game fields and struct offsets.

---

## 8. Risk Mitigation

- Unknown fields: keep raw bytes for unparsed segments and copy them through.  
- Large directory counts: ensure memory usage stays manageable by streaming entries if necessary.  
- Localization: text assets might vary by language; maintain per-region backups and note file naming conventions (`%03u` suffix).

---

## 9. Deliverables for Initial Editor Release

1. Python package `app/` with modules:
   - `io.py`, `models.py`, `cli.py`, `xor.py`
2. CLI script `python -m app rename --id 123 --name "New Name"`
3. Updated documentation in `/out`:
   - `editor_usage.md`
   - `schema_players.md`
4. Automated tests verifying round-trip integrity.

---

This roadmap leverages the reverse-engineered knowledge base to deliver a practical editing tool, starting with player renaming and extending to full attribute manipulation.
