# Breakdown of commit 2f79f4c

## Documentation restored and expanded
- **docs/ARCHITECTURE.md** — Added an end-to-end overview of the editor stack, including component responsibilities, runtime data flow from loading through persistence, core CLI/GUI workflows, and extensibility guidance so future contributors understand how pieces fit together.【F:docs/ARCHITECTURE.md†L1-L83】
- **docs/DATA_FORMATS.md** — Documented canonical structure for Premier Manager 99 `.FDI` archives plus detailed player, team, coach, and PKF record parsing rules, ensuring the parsers and docs stay in sync.【F:docs/DATA_FORMATS.md†L1-L94】【F:docs/DATA_FORMATS.md†L96-L147】
- **docs/EDITOR_README.md** — Produced a user-facing guide describing how to launch the GUI/CLI, the layout of each tab (including the ⚽ Leagues view and PKF tools), save/backup behaviour, safety tips, and troubleshooting steps.【F:docs/EDITOR_README.md†L1-L108】【F:docs/EDITOR_README.md†L110-L152】
- **docs/Bugs/MISSING_DBDAT_FIXTURES.md** — Logged the missing proprietary fixtures issue, its impact on integration tests, reproduction steps, and remediation options.【F:docs/Bugs/MISSING_DBDAT_FIXTURES.md†L1-L32】
- **docs/QA_REPORT.md** — Captured the latest `pytest -q` run, noting the skip behaviour when fixtures are absent and highlighting which suites are affected.【F:docs/QA_REPORT.md†L1-L27】
- **docs/REQUIREMENTS_INFERRED.md** — Summarised the inferred product, technical, and quality requirements gleaned from the codebase and docs, plus outstanding needs around documentation and fixtures.【F:docs/REQUIREMENTS_INFERRED.md†L1-L33】
- **docs/SUGGESTIONS.md** — Listed follow-up improvements such as shipping safe fixtures, clarifying CLI rename limits, and adding processes to prevent documentation drift.【F:docs/SUGGESTIONS.md†L1-L14】

## Test configuration and shared fixtures
- **pytest.ini** — Registered an `integration` marker for data-heavy suites so contributors can select or skip them explicitly.【F:pytest.ini†L1-L4】
- **tests/conftest.py** — Ensured the repo root is on `sys.path` and introduced reusable fixtures (`players_fdi_path`, `teams_fdi_path`, `coaches_fdi_path`) that gracefully skip tests when the proprietary `DBDAT` files are missing.【F:tests/conftest.py†L1-L34】

## Script-style regression helpers
- **scripts/test_coach_parser.py** — Added a top-level skip guard for the coach database before decoding and printing parsed records, preventing `FileNotFoundError` during collection.【F:scripts/test_coach_parser.py†L10-L32】
- **scripts/test_name_fixes.py** — Inserted a skip guard for the player database, then retained the exploratory assertions/prints verifying canonical player names.【F:scripts/test_name_fixes.py†L17-L55】
- **scripts/test_save_editors.py** — Converted ad-hoc path handling into pytest-aware tests that skip when fixtures are missing, exercise coach/team save flows through `save_modified_records()`, and print diagnostics on success; retained a `__main__` shim for manual runs.【F:scripts/test_save_editors.py†L1-L95】【F:scripts/test_save_editors.py†L97-L146】

## Standalone regression tests
- **test_garbage_filters.py** — Parameterised the garbage name regression list and wrapped the helper so each entry asserts it is rejected, improving pytest output without altering the legacy debugging CLI harness.【F:test_garbage_filters.py†L1-L95】
- **test_gui_loading.py** — Added skip guards for missing coach/team files before running GUI-loading diagnostics, keeping the verbose inspection logic intact.【F:test_gui_loading.py†L14-L63】【F:test_gui_loading.py†L65-L97】
- **test_loader_directly.py** — Guarded the module-level load against missing coach data before running loader diagnostics and inline debugging.【F:test_loader_directly.py†L1-L41】
- **test_performance_improvements.py** — Fallback to either repo-root or packaged fixture locations and skip cleanly when the player database is absent, while leaving timing diagnostics unchanged.【F:test_performance_improvements.py†L1-L55】
- **test_strict_filtering.py** — Added skip guards to both coach and team filtering scans so the strict validation heuristics only run when fixtures exist.【F:test_strict_filtering.py†L12-L66】【F:test_strict_filtering.py†L68-L109】

## Unit and integration suites under `tests/`
- **tests/test_core_io_decoding.py** — Kept XOR/FDI encoding unit tests while appending helper builders and attribute decoding assertions, still runnable without fixtures; relies solely on in-memory records.【F:tests/test_core_io_decoding.py†L1-L97】【F:tests/test_core_io_decoding.py†L99-L141】
- **tests/test_debug_serialization.py**, **tests/test_hex_dump.py**, **tests/test_metadata_edit.py**, and **tests/test_serialization.py** — Swapped direct path handling for the shared `players_fdi_path` fixture so Hierro regression cases load safely, asserting metadata/serialization behaviour remains intact.【F:tests/test_debug_serialization.py†L1-L28】【F:tests/test_hex_dump.py†L1-L23】【F:tests/test_metadata_edit.py†L1-L33】【F:tests/test_serialization.py†L1-L28】
- **tests/test_regression_players.py** — Reused the player fixture for canonical player assertions and decoded payload provenance checks, ensuring the regression harness skips when data is unavailable.【F:tests/test_regression_players.py†L1-L61】
- **tests/test_scanner.py** — Updated the scanner smoke test to consume the shared fixture, asserting the discovery helper still finds named players.【F:tests/test_scanner.py†L1-L9】
- **tests/test_team_coach_save.py** — Leveraged the team/coach fixtures to validate parsing and save round-trips, skipping gracefully when no suitable records exist in the provided assets.【F:tests/test_team_coach_save.py†L1-L40】

## Miscellaneous
- **docs/QA_REPORT.md** & **docs/Bugs/MISSING_DBDAT_FIXTURES.md** cross-reference — Documented that certain suites now skip rather than fail, emphasising the need for distributable fixtures or documented acquisition steps.【F:docs/QA_REPORT.md†L9-L27】【F:docs/Bugs/MISSING_DBDAT_FIXTURES.md†L5-L23】
