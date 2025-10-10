# Premier Manager 99 Reverse-Engineering — Handover Brief

## 1. Repository Inventory (re-verify all claims)

| Artifact | Purpose | Required Re-Verification |
| --- | --- | --- |
| [`out/breadcrumbs.csv`](out/breadcrumbs.csv) | String breadcrumbs per binary (filename, RVA, xref count). | Rerun Ghidra searches for each string to confirm RVAs/xrefs; update counts if mismatched. |
| [`out/struct_notes.md`](out/struct_notes.md:1-175) | Header details, decoded offsets, and **in-progress** player-struct mapping. | Reproduce every Python probe referenced, confirm offsets/interpretations, and extend/overwrite incomplete field notes. |
| [`out/verify.txt`](out/verify.txt:1-53) | Before/after hexdumps for one FDI record and TEXTOS entry. | Recreate both dumps from raw files; confirm XOR decode results match expectations (no skipped bytes). |
| [`out/decode_one.py`](out/decode_one.py:1-112) | Current XOR decoder stub. | Retest across multiple offsets (FDI + TEXTOS). Log any cases where output does not decode to readable data. Expand to encoder once schema is validated. |
| [`out/triangulation.md`](out/triangulation.md:1-30) | Cross-binary loader comparison summary. | Verify addresses/functions in Ghidra. Check import tables to confirm helper reuse. |
| [`out/README.md`](out/README.md:1-112) | Project summary, call graphs, decode algorithm overview. | Treat as a synopsis; update once verification tasks complete. |
| [`out/editor_roadmap.md`](out/editor_roadmap.md:1-145) | Implementation plan (now includes WIP status). | Use as task list; adjust as findings evolve. |
| [`app/__init__.py`](app/__init__.py:1-5) | Placeholder package for future code. | Populate as modules are created. |
| `textos_0000.bin` | Sample decoded output from TEXTOS.PKF `offset=0`. | Re-generate via decoder, inspect text with CP1252 to confirm readability. |
| [`out/handover.md`](out/handover.md:1-91) | This document. | Replace once new owner confirms status. |

## 2. Immediate Re-Verification Tasks

1. **Validate the XOR decoder**
   - Re-run `python out/decode_one.py DBDAT/JUG98030.FDI 0x410 --hexdump --preview`.
   - Re-run `python out/decode_one.py DBDAT/TEXTOS.PKF 0x0 --hexdump --preview`.
   - Repeat for 3+ additional offsets (pick diverse records). Note anomalies.

2. **Confirm header interpretation**
   - Rewrite the Python header-dump script to ensure offsets/lengths match `MANAGPRE.EXE.FUN_004a0a30()`.
   - Compare counts versus actual file size.

3. **Player record schema**
   - Disassemble `FUN_004afd80`, `FUN_004a0370`, and `FUN_004a0a30` in Ghidra.
   - Map each write to `param_1` to a struct field. Annotate with offsets and data types.
   - Use decoded sample(s) to confirm field semantics (name, birthdate, stats, etc.).
   - Document everything in `out/struct_notes.md` (or create `schema_players.md`).

4. **Text resources**
   - Inspect text decode output (`textos_0000.bin`) for encoding completeness (Windows-1252, fallback charmap).
   - Note any characters still mis-decoded; derive charmap adjustments if necessary.

## 3. Remaining Engineering Work (after schema is verified)

1. **Implement structured reader/writer**
   - A. Create dataclasses (e.g., `PlayerRecord`) with `from_bytes` / `to_bytes`.
   - B. Build module `app/fdi.py` to handle header parsing, directory handling, and record iteration.
   - C. Implement XOR encoder matching decode logic and rebuild the directory table.

2. **CLI workflow**
   - Provide commands to list players, rename by ID, and apply changes.
   - Auto-backup original files and produce change logs.
   - Validate that modified files load in MANAGPRE/DBASEPRE.

3. **Testing**
   - Unit tests for encode/decode symmetry.
  - Regression tests comparing original and rewritten files (isolating changed records).

4. **TEXTOS support**
   - Mirror the above pipeline for PKF/TEXTOS entries (names, countries) once the struct is fully understood.

## 4. Known Gaps / Risks

- Player schema is partially inferred; **do not rely on existing notes without re-checking**.
- TEXTOS decoding works for the sample but may require charmap adjustments; confirm across multiple files.
- Optional blocks (contracts, stats, etc.) include version-dependent paths (`param_5` threshold logic). Ensure the editor preserves unknown blocks unmodified if fields aren’t fully understood.

## 5. Suggested Workflow for the New Agent

1. **Set up tools**
   - Load `MANAGPRE.EXE`, `DBASEPRE.EXE` in Ghidra with symbols of interest.
   - Have Python environment ready (Python 3.11+ recommended) with `out/decode_one.py`.

2. **Verify existing work**
   - Re-run all scripts and confirmations listed in Sections 2 and 4.
   - Update documentation as discrepancies are found.

3. **Complete decoding schema**
   - Dive into `FUN_004afd80` and companion routines to finalize the player struct.

4. **Implement writer & editor CLI**
   - Follow `out/editor_roadmap.md` to convert findings into code.

5. **Test in-game**
   - After implementing rename/update functionality, verify by launching MANAGPRE with edited databases.

Remain cautious when making edits until every field is clearly documented; unknown segments should be preserved verbatim to prevent corruption.

Good luck!
