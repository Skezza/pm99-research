# PKF/FDI change summary

This note collects the concrete code updates that shipped with the stricter PKF
and FDI safeguards so you can see, at a glance, what changed and where to dive
in when debugging or extending the pipeline.

## `pm99_editor/pkf.py`

- Replaced the permissive single-entry fallback with deterministic TOC parsing
  and structural validation that raises `PKFTableValidationError` when offsets
  or coverage drift.
- Added the `PKFEntryKind` classification helper and now preserve the detected
  kind when returning entry copies so downstream tooling can branch by payload
  type.
- Wired the parser into the diagnostics logger so every validation failure is
  recorded on disk for later investigation.
- Extended `PKFFile.to_bytes()` to round-trip the stricter `toc32` layout while
  keeping a gated `raw` fallback for explicit best-effort workflows.

## `pm99_editor/scanner.py`

- Introduced `PlayerScanIssue` and `PlayerScanError` so scans report the exact
  offsets and reasons when player blobs fail to decode.
- Added quarantine support: undecodable payloads are returned alongside issues
  so you can inspect them without silently discarding data.
- Tightened the heuristics that detect record terminators and attribute ranges
  and removed broad `except Exception` guards; strict mode now fails loudly.
- Hooked the new error path into `FDIFile.load(strict=True)` so broken files are
  surfaced immediately instead of yielding partial record lists.

## `pm99_editor/diagnostics.py`

- Added a small logging utility that appends structured JSON lines under
  `diagnostics/` and keeps one log file per pipeline concern.
- PKF validation errors now emit log entries with file names and rule failures
  so reverse-engineering sessions can resume exactly where validation stopped.

## `pm99_editor/io.py`

- Updated `FDIFile.load()` to accept the `strict` flag and bubble up
  `PlayerScanError` details to callers.
- Ensured the helper forwards quarantine buffers from the scanner for advanced
  debugging.

## Tests

- `tests/test_pkf_parser.py` now verifies that malformed tables raise
  `PKFTableValidationError`, log diagnostics, and refuse to round-trip when
  coverage is non-contiguous.
- `tests/test_scanner.py` exercises both strict success/failure cases and the
  quarantine pathway using deterministic synthetic fixtures so CI catches
  regressions.

## Documentation

- `docs/DELIVERABLE_IMPACT.md` explains how to run the new validation, scanning,
  and regression commands in day-to-day modding workflows.
- `docs/pcf_editor_alignment.md` tracks progress toward “editor-grade” support
  and calls out where the stricter behaviours land in the codebase.
- README and `docs/README.md` link to the new walkthrough so the safeguards are
  easy to discover.

Use this summary as the map for code reviews or onboarding discussions: each
bullet corresponds to a concrete change that was introduced to harden the PKF
and FDI pipeline.
