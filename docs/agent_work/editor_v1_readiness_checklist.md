# PM99 Editor v1 Readiness Checklist

Use this checklist before calling the safe-core editor "v1 ready".

## Automated Checks

- [x] `python3 -m py_compile` succeeds for changed modules/scripts/tests
- [x] `pytest` is installed in the dev environment
- [x] bulk rename/revert unit tests pass
- [x] editor action unit tests pass
- [x] CLI command unit tests pass
- [x] existing `tests/test_editor_actions.py` passes when `DBDAT/` fixtures are available
- [x] roster reconciliation unit tests pass (`tests/test_roster_reconcile.py`)
- [x] GUI bulk workflow unit tests pass (`tests/test_gui_v1.py`)

## PDF Reconciliation Validation (Milestone 5 Artifact Support)

- [x] `roster-reconcile-pdf` CLI command is documented in the operator runbook
- [x] JSON export includes a schema version field (currently `schema_version: \"v1\"`)
- [x] 4 playable league PDFs processed end-to-end (Premier, Division 1, Division 2, Division 3)
- [x] aggregate metrics document generated (`docs/agent_work/pdf_reconciliation_metrics.md`)
- [x] known error categories documented (ambiguity, low-confidence isolates, no-db-candidate parser gaps)
- [x] optional name-hints workflow documented and validated on at least one known false-isolation case

## Manual Editor Smoke Tests (on copied `DBDAT/`)

- [ ] GUI loads players/coaches/teams without exceptions
- [ ] Player name rename can be staged and saved
- [ ] Team name rename can be staged and saved
- [ ] Coach name rename can be staged and saved
- [ ] GUI save creates backups
- [ ] Re-opening files shows the edited names

## CLI Smoke Tests (on copied `DBDAT/`)

- [ ] `player-list` works
- [ ] `player-search` works (offset-aware output)
- [ ] `player-rename --dry-run` works
- [ ] `player-rename` writes successfully
- [ ] `team-list`, `team-search`, `team-rename` work
- [ ] `coach-list`, `coach-search`, `coach-rename` work
- [x] `roster-reconcile-pdf --help` works
- [x] `roster-reconcile-pdf` writes JSON/CSV/team-summary outputs
- [x] `roster-reconcile-pdf --name-hints` changes at least one known ambiguous/false-isolated row classification as expected

## Bulk Rename M1 Smoke Tests (on copied `DBDAT/`)

- [ ] `bulk-player-rename --dry-run` succeeds
- [ ] `bulk-player-rename` succeeds and writes mapping CSV
- [ ] mapping CSV contains `offset` and `offset_hex`
- [ ] `bulk-player-revert --dry-run` succeeds
- [ ] `bulk-player-revert` succeeds and restores names

## In-Game Validation

- [ ] Game loads after single player/team/coach edits
- [ ] Game loads after bulk player rename
- [ ] Game loads after bulk player revert
- [ ] Lineup/search/transfer screens show expected names

## Release Hygiene

- [ ] No `.FDI`, backup files, or generated mapping CSVs are staged in git
- [x] Known limitations documented (safe-core, M1-only bulk player rename, reconciliation pipeline limits)

## Milestone Status Snapshot (Local Engineering Sign-Off)

- [x] M1 bulk rename/revert: implemented + local tests + local smoke evidence captured
- [x] M2 shared editor actions: local tests passing, docs/readiness updated
- [x] M3 CLI tooling: command coverage/tests/docs updated (including roster reconciliation)
- [x] M4 GUI stabilization: local GUI smoke/validation evidence captured
- [x] M5 hardening/validation: metrics + validation artifacts generated and documented

## Latest Local Evidence (2026-02-26)

- [x] `pytest -q -o addopts='' tests/test_gui_v1.py tests/test_bulk_rename_scripts.py tests/test_editor_actions_unit.py tests/test_editor_actions.py tests/test_cli_v1.py tests/test_roster_reconcile.py` -> `37 passed`
- [x] `python3 -m py_compile` over all changed Python files (19 files) -> success
- [x] `python3 -m app.cli roster-reconcile-pdf --help` -> command available with `--name-hints`
- [x] Reconciliation exports generated for all 4 playable leagues (Premier / Div1 / Div2 / Div3)
- [x] Stoke hint validation: `Robinson` no longer `isolated_default` when `Phil` hint is supplied (moved to review bucket)
- [x] `python3 - <<'PY' import app.gui` import smoke -> `gui_import_ok`
- [x] `python3 -m app.cli bulk-player-rename --data-dir DBDAT --map-output /tmp/pm99_bulk_rename_map.csv --dry-run --json` -> success (`rows_written=4917`)
- [x] `python3 -m app.cli bulk-player-revert --data-dir DBDAT --map-input /tmp/pm99_bulk_rename_map.csv --dry-run --json` -> success (`rows_processed=4917`)
