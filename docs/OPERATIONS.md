# PM99 Operations Guide

This is the canonical operator-facing workflow for using the current PM99 editor safely.

## Safety Defaults

- Always work on a copy of `DBDAT/`.
- Keep backups created by the editor until you have verified the result.
- Prefer dry-run modes before any bulk operation.
- Never commit `.FDI`, `.backup*`, generated CSVs, or ad hoc exports.

## Standard Single-Record Workflow

1. Copy the target `DBDAT/` directory to a disposable working folder.
2. Open the GUI with `python3 -m app.gui` or use the CLI from `app/cli.py`.
3. Make one player, team, or coach edit at a time.
4. Save changes and confirm a backup was created.
5. Re-open the edited files and verify the change before doing more work.

## Bulk Player Rename Workflow

1. Dry-run first:
   - `python3 scripts/bulk_rename_players.py --data-dir DBDAT --map-output rename_map.csv --dry-run`
2. Review the generated mapping CSV.
3. Run the write:
   - `python3 scripts/bulk_rename_players.py --data-dir DBDAT --map-output rename_map.csv`
4. Verify the editor and game can still load the modified files.

## Bulk Revert Workflow

1. Dry-run validation first:
   - `python3 scripts/bulk_rename_revert.py --data-dir DBDAT --map-input rename_map.csv --dry-run`
2. Run the revert:
   - `python3 scripts/bulk_rename_revert.py --data-dir DBDAT --map-input rename_map.csv`
3. Re-open the files and confirm the original names are restored.

## Parser-Backed Roster Inspection

Use the read-first roster tools before trusting any team-level data mutation:

- `python3 -m app.cli team-roster-linked --team "Stoke C"`
- `python3 -m app.cli team-roster-extract --team "Stoke C"`
- `python3 -m app.cli team-roster-extract --include-fallbacks --team "Manchester Utd"`

Guideline:
- Default authoritative output is for editor-facing work.
- Fallback or heuristic output is only for investigation.

## Smoke Checks Before Calling a Change “Safe”

## Automated

- `python3 -m py_compile` succeeds for changed Python files.
- `pytest` is installed and runnable.
- Relevant unit tests for the touched workflow pass.

## Manual

- GUI loads without exceptions.
- Target edit can be staged and saved.
- Save creates a backup.
- Re-opening the file shows the updated value.

## Release Hygiene

- No game data files or backups are staged in git.
- Limitations are documented before relying on a workflow operationally.
- If a write path is not parser-backed and tested, treat it as investigative only.
