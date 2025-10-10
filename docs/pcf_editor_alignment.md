# PC Fútbol Alignment Review

## Current Decoder Characteristics

* The player scanner still leans on regex heuristics, windowed byte slices, and broad `except Exception` blocks to keep parsing going whenever `PlayerRecord.from_bytes` raises, so failures are silently skipped instead of surfaced. 【F:pm99_editor/scanner.py†L51-L181】
* The PKF helper intentionally stops at extracting raw entry payloads and falls back to a single-entry view whenever the header layout is unfamiliar, which keeps exploration safe but never asserts table integrity. 【F:pm99_editor/pkf.py†L1-L131】

## Gaps Versus Community Editors

Community PC Fútbol tooling described in the linked sources treats PKF archives as fully specified TOC-driven containers and FDI blobs as structured record arrays. In contrast, the current pipeline:

1. Never validates that a PKF entry table accounts for every byte or that offsets are monotonically increasing, so malformed archives could go unnoticed. 【F:pm99_editor/pkf.py†L84-L131】
2. Accepts any `PlayerRecord` chunk whose attributes merely fit heuristic ranges, which risks drifting from the fixed-width PC Fútbol schemas the community relies on. 【F:pm99_editor/scanner.py†L107-L176】
3. Suppresses decoder errors broadly, meaning tooling can return partial player lists without any warning, unlike editor-grade workflows that abort or quarantine unknown structures. 【F:pm99_editor/scanner.py†L89-L181】

## Progress Toward “Editor Grade”

* Deterministic PKF parsing is now implemented via `PKFFile.from_bytes(strict=True)`
  which raises `PKFTableValidationError` whenever the table-of-contents fails
  monotonic or coverage checks, eliminating the silent single-entry fallback. 【F:pm99_editor/pkf.py†L24-L154】
* `find_player_records` surfaces structured `PlayerScanError` issues and accepts a
  quarantine buffer so ingest pipelines can fail loudly (or opt-in to best effort)
  while preserving forensic data. 【F:pm99_editor/scanner.py†L18-L210】

## Remaining Recommendations to Reach “Editor Grade”

1. **Deterministic PKF Parsing**
   * ✅ Replace the fallback path with explicit validation of entry counts, offsets, and cumulative coverage, raising a dedicated error when the TOC is inconsistent. 【F:pm99_editor/pkf.py†L84-L154】
   * Expose typed entry descriptors (team roster block, string tables, indices) instead of opaque `raw_bytes`, mirroring the PKF→DBC flow community editors implement.

2. **FDI Schema Definition**
   * Document record size, field ordering, and encoding for representative files such as `jug00022.fdi`, then assert exact record counts during decode to eliminate silent drops. 【F:pm99_editor/scanner.py†L51-L181】
   * Add round-trip fixtures (decode → modify → encode) so CI can guarantee byte-level fidelity for key archives.

3. **Fail Loudly on Unknown Data**
   * ✅ Narrow `except Exception` handlers to specific decoding failures and surface structured errors that include offsets and offending bytes. 【F:pm99_editor/scanner.py†L18-L210】
   * ✅ Introduce quarantine logging for unparsed chunks so reverse-engineering efforts can iterate safely without corrupting output. 【F:pm99_editor/scanner.py†L102-L210】

4. **Version-Specific Coverage**
   * Split PKF/FDI handling paths by PC Fútbol release family (5/6 vs 7/2000+) and pin fixtures per version to prevent assumptions from leaking across formats.

These changes will move the codebase from an exploratory decoder toward the deterministic, schema-driven workflows that existing PC Fútbol editors use, providing confidence that edits will persist in-game and across saves.

## Why this matters when you are modding

* **Reliable PKF imports.** If you point the tool at a community package such as `EQPCPLUS.PKF` and the table of contents has gaps, the parser now throws a validation error and writes the offending offsets to `diagnostics/pkf_table_validation.log`, instead of quietly returning a roster that is missing teams.【F:pm99_editor/pkf.py†L69-L119】【F:pm99_editor/diagnostics.py†L1-L64】 That tells you immediately that the archive needs more reverse engineering before you ship an update.
* **Deterministic player extraction.** When an FDI file contains a malformed player blob, the scanner records a structured issue—including the byte offset and a hex preview—so you know exactly which youth or senior record needs hand fixing rather than discovering missing players in game.【F:pm99_editor/scanner.py†L57-L229】
* **Repeatable guardrails.** Focused tests pin these behaviours: the PKF suite refuses non-contiguous payloads and the scanner tests prove that strict/quarantine modes keep working.【F:tests/test_pkf_parser.py†L1-L136】【F:tests/test_scanner.py†L1-L208】 That gives CI a concrete signal that the safety nets are still protecting production assets.
