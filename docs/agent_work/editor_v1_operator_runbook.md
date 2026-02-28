# PM99 Editor v1 Operator Runbook (Safe Core)

This runbook describes the recommended safe workflow for using the PM99 editor v1 features (CLI/GUI) while preserving recoverability.

## Safety Defaults

- Treat `PM99_SAVE_NAME_ONLY=True` as the baseline for player edits.
- Always work on a copy of `DBDAT/`.
- Never commit `.FDI`, `.backup*`, or generated rename mapping CSVs.

## Recommended Workflow (Single Record Edits)

1. Copy the target `DBDAT/` directory to a disposable working folder.
2. Open the GUI (`python3 -m app.gui`) or use CLI commands from `app/cli.py`.
3. Make a single player/team/coach rename and stage it.
4. Save changes and confirm a backup file is created.
5. Re-open the file(s) and verify the new name is visible.

## Recommended Workflow (Bulk Player Rename M1)

1. Run a dry run first:
   - `python3 scripts/bulk_rename_players.py --data-dir DBDAT --map-output rename_map.csv --dry-run`
2. Review `rename_map.csv` (schema includes `offset` and `offset_hex`).
3. Run the actual rename:
   - `python3 scripts/bulk_rename_players.py --data-dir DBDAT --map-output rename_map.csv`
4. Validate the game/editor can load the updated files.
5. Keep the mapping CSV with the modified copy until sign-off is complete.

## Bulk Revert Workflow

1. Dry-run validation first:
   - `python3 scripts/bulk_rename_revert.py --data-dir DBDAT --map-input rename_map.csv --dry-run`
2. Run the revert:
   - `python3 scripts/bulk_rename_revert.py --data-dir DBDAT --map-input rename_map.csv`
3. Re-open in editor and verify original names are restored.

## GUI Bulk Tools (M1)

- `Tools -> Bulk Rename Players (M1)...`
- `Tools -> Revert Bulk Player Rename (M1)...`

Use dry-run in the dialog first, then run the write operation.

## Roster PDF Reconciliation (CLI Validation / Tuning)

Use this workflow to reconcile PM99 roster-listing PDFs against `JUG98030.FDI` and generate validation/review datasets.

1. Run reconciliation for a league PDF:
   - `python3 -m app.cli roster-reconcile-pdf --pdf "/home/joe/Documents/Division 1.pdf" --player-file DBDAT/JUG98030.FDI --json-output /tmp/div1_reconcile.json --csv-output /tmp/div1_reconcile_rows.csv --team-summary-csv /tmp/div1_reconcile_teams.csv`
2. Optional: constrain to one team while iterating on heuristics/hints:
   - `python3 -m app.cli roster-reconcile-pdf --pdf "/home/joe/Documents/2nd div.pdf" --player-file DBDAT/JUG98030.FDI --team "Stoke City" --json-output /tmp/stoke_reconcile.json --csv-output /tmp/stoke_reconcile_rows.csv`
3. Optional: apply name hints (CSV/JSON) for ambiguous/low-confidence surnames:
   - `python3 -m app.cli roster-reconcile-pdf --pdf "/home/joe/Documents/2nd div.pdf" --player-file DBDAT/JUG98030.FDI --team "Stoke City" --name-hints /tmp/stoke_name_hints.csv --json-output /tmp/stoke_reconcile_hints.json --csv-output /tmp/stoke_reconcile_hints_rows.csv`
4. Review the detailed CSV:
   - Use `status` for backward-compatible classification.
   - Use `status_detail` to separate high/low-confidence isolates and review buckets.
   - Use review columns (`review_decision`, `review_notes`, `expected_full_name`, `accepted_candidate_name`) for manual curation.
5. Keep outputs in `/tmp` or another local export folder and do not commit generated JSON/CSV files.

Notes:
- JSON exports include `schema_version: \"v1\"` for schema stability tracking.
- Name hints are additive disambiguation signals and do not create club evidence when none exists.

## Team Roster Extraction (Parser-First Default)

Use this command to inspect team roster extraction from `EQ98030.FDI` with `JUG98030.FDI` player-id name mapping.

Default mode is **authoritative-only**:

- `python3 -m app.cli team-roster-extract --team "Stoke C"`
- `python3 -m app.cli team-roster-extract --team "AC Milan"`
- `python3 -m app.cli team-roster-extract --team "Inter Milan"`

Authoritative-only mode reports:

- same-entry strong/perfect matches only (`provenance=same_entry_authoritative`)
- coverage and unresolved-club summaries suitable for parser-first milestone tracking
- canonical club-name aliases are accepted for common variants (`AC Milan`, `Inter Milan`, `Atletico Madrid`, `Real Madrid`) and resolve to the parser-backed internal team records

Investigation fallback mode is explicit and opt-in:

- `python3 -m app.cli team-roster-extract --include-fallbacks --team "Manchester Utd" --team "Middlesbrough"`

Fallback mode additionally shows:

- known lineup anchor-assisted split-entry windows
- provisional candidate classes (circular-shift, pseudo-adjacent, anchor-interval)
- heuristic warnings and guardrails (e.g. known-anchor collisions)

Guideline:

- Use default authoritative mode for editor-facing workflows and milestone health.
- Use `--include-fallbacks` only when investigating unresolved teams.

GUI note:

- The Team overlay's `Show squad lineup` panel uses the same authoritative extraction path.
- It only displays parser-backed roster rows by default and falls back to `PID <id>` placeholders when a player name is still unresolved in the current `dd6361` corpus.
- When a `dd6361` row resolves cleanly, the overlay also fills `SP`, `ST`, `AG`, and `QU` from the verified visible stat mapping.

## Troubleshooting

- If a player rename fails in safe mode, check for length changes or unsupported expansion.
- If revert fails on a row mismatch, verify you are reverting against the same file set used to generate the mapping.
- If a team/coach rename looks wrong, revert from the backup and retry with a single targeted offset.
- If roster reconciliation over-matches a surname, add a small name-hints CSV (first name / initial) and re-run on a single-team filter first.

## Current v1 Limitations

- Player bulk rename is length-preserving only (Milestone 1).
- Variable-length player bulk rename is not part of v1.
- Player attribute editing is not part of the v1 safety guarantee.
- PDF reconciliation is a validation/tuning pipeline, not a canonical parser or authoritative roster import.
