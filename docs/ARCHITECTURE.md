# Architecture Overview

The active codebase has three layers:

1. `app/`
   - Core parsers and serializers (`models.py`, `io.py`, `xor.py`, `fdi_indexed.py`)
   - Editing and write helpers (`file_writer.py`, `editor_actions.py`)
   - Domain loaders and UI support (`loaders.py`, `coach_models.py`, `gui.py`, `pkf.py`)
2. `tests/`
   - Unit and regression coverage for parsing, writing, CLI behavior, and GUI smoke paths
3. `scripts/`
   - A small set of maintained probes and operational wrappers

The intended flow is:

1. Load raw bytes from an `.FDI` or `.PKF`.
2. Decode container structure and payloads.
3. Parse only the fields the project can currently prove.
4. Apply conservative edits while preserving unknown bytes where possible.
5. Write back through the guarded save helpers that create backups first.

The command line and GUI should both sit on top of the shared `app/` code. If behavior differs between docs and code, treat the implementation as authoritative.
