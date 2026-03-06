# Premier Manager 99 Editor

This guide describes the current desktop editor experience exposed through
`python -m app.gui`.

The runtime GUI is the refreshed club-first shell implemented in
`app/gui_refresh.py`. Older notebook-style screenshots or notes should be
treated as historical only.

## Launching the editor

From the repository root:

```bash
python -m app.gui
```

The app opens into the editor shell and waits for a PM99 database set. Use:

- `File -> Open Database Set...`
- or the landing-screen `Load Database Set` button

You can select any one of the three `.FDI` files (`JUG*.FDI`, `EQ*.FDI`, or
`ENT*.FDI`) from a folder that contains the full set. The GUI resolves the
companion player, club, and coach databases automatically.

## Startup behavior

The GUI now uses staged loading.

- Clubs and coaches load first so the shell becomes usable quickly.
- The player catalog is deferred at startup, then warmed in the background.
- If you reach a player-dependent surface before that warmup finishes, the GUI
  can still load the player catalog on demand.
- The player load still uses the full parser-backed discovery path with the
  existing scanner fallback; deferred loading is a responsiveness optimization,
  not a reduced-capability mode.

This means startup is faster, but the first player-heavy action can still incur
one full player parse if the background warmup has not finished yet.

## Window layout

The editor is split into four persistent regions:

- Top toolbar: current route, save action, and live status.
- Left rail: global search, primary navigation, and database/validation summary.
- Center workspace: club browser, player browser, coach browser, or leagues view.
- Right editor pane: the active record card (player, club, coach, or empty state).
  It now scrolls, so tall player/team cards remain usable on smaller window heights.

The main product flow is club-first:

1. Load a database set.
2. Browse clubs.
3. Select a club.
4. Open a squad row.
5. Edit the player in the right-hand pane.
6. Save staged changes with `Save All`.

## Main workspaces

### Clubs

This is the default editor surface and the primary workflow.

- Browse the club list with search / country grouping.
- Select a club to view its summary and roster state.
- If player data is still deferred, the club card stays usable and explains that
  the roster will appear once player data is loaded.
- When roster data is available, single-clicking a squad row loads that player
  into the editor pane.
- Linked roster rows now expose a first-class `Promote Slot Player` flow in the
  team editor card. This applies a safe indexed-name alias sync for the selected
  JUG record and can optionally apply an elite visible-skill preset in one step.
  The current safe writer is fixed-width only: if the requested name token is
  longer than the source token at that slot, the promotion is rejected instead
  of risking an unsafe payload expansion.
- `Batch Import CSV` is now migrated into the refreshed team editor card and
  runs the same shared roster-batch parser-backed validation path as CLI.
- `Batch Import CSV` now includes a row-level plan preview pane before staging.
  The preview uses the shared backend payload (`plan_preview`) and shows
  `change` / `no_change` / `warning` per CSV row before you commit anything.
- Roster tools are now staged-first in the refreshed shell:
  `Edit Selected Slot`, `Promote Slot Player`, and `Batch Import CSV` all stage
  operations and rely on `Save All` for the actual write.

### Players

This is the cross-database player browser.

- It is available immediately as a shell surface.
- If the player catalog is not ready yet, the view shows a clear deferred state
  and offers `Load Player Data`.
- Once loaded, it behaves as a searchable player browser rather than the main
  landing page.

### Coaches

Coach editing is intentionally narrower than player editing.

- Browse coach records across the database.
- Open a coach in the right-hand editor card.
- Current write support is limited; the UI reflects the confirmed writable
  surface instead of implying fields that are not parser-backed yet.

### Leagues

The leagues view is primarily a browse-and-route surface.

- Use it to navigate country -> league -> club.
- Selecting a club routes you back into the club-first workflow.
- For noisy team records where `team_id` parsing is unreliable, the editor now
  promotes strong competition-signal probe matches into a read-only
  `competition_probe_contract` source. Remaining unresolved teams still fall
  back to best-effort file-order placement so league browsing remains usable.
- The Leagues grid now exposes assignment provenance columns (`source`,
  `confidence`, `status`) and supports search + assignment-bucket filtering
  (`Promoted`, `Confirmed`, `Supported`, `Fallback`, `Review`, `Unresolved`).

### Advanced Workspace

Reverse-engineering and investigation tools live behind:

```text
Tools -> Advanced Workspace
```

These tools are intentionally separated from the normal editor workflow. They
remain useful for:

- player metadata inspection
- indexed byte profile analysis
- current-club roster source inspection
- selected-club competition-field candidate inspection
- selected-club primary-code family inspection
- linked-roster promotion skip diagnostics (`Profile Roster Promotion Safety`)
- cross-league competition signature profiling, including the secondary
  `+0x08/+0x0A` family-split view and the current best tested tertiary byte
- dominant-country subgroup profiling for country-like primary families
- bitmap / asset reference string probing

The team editor provenance panel also now shows the current `+0x00`
competition-byte candidate, the current `+0x08/+0x0A` secondary signature, and
the inferred split strength for the selected club, plus the current best tested
third-byte probe for that family, plus the current best non-text family-byte
candidate.

They should be treated as research tools, not the main editing surface.

### CLI parity for Advanced team competition probes

The same competition-family reports exposed in the Advanced workspace are also
available from the CLI against `EQ98030.FDI`:

```bash
python -m app.cli team-competition-profile DBDAT/EQ98030.FDI
python -m app.cli team-primary-family DBDAT/EQ98030.FDI --team "Manchester Utd"
python -m app.cli team-country-subgroup-profile DBDAT/EQ98030.FDI
python -m app.cli team-league-audit DBDAT/EQ98030.FDI
python -m app.cli player-name-capacity DBDAT/JUG98030.FDI --name "Bryan SMALL" --proposed-name "Joe Skerratt"
python -m app.cli team-roster-promote-player DBDAT/EQ98030.FDI --team "Stoke C." --slot 13 --new-name "Joe SKERRATT" --elite-skills --fixed-name-bytes
python -m app.cli team-roster-promote-bulk-name DBDAT/EQ98030.FDI --team "Stoke C." --new-name "Joe Skerratt" --slot-limit 25 --fixed-name-bytes --dry-run
python -m app.cli team-roster-promotion-safety DBDAT/EQ98030.FDI --team "Stoke C." --new-name "Joe Skerratt" --slot-limit 25 --json
python -m app.cli team-roster-export-template DBDAT/EQ98030.FDI --team "Stoke C." --csv stoke_template.csv
python -m app.cli team-roster-clone-linked DBDAT/EQ98030.FDI --source-team "Manchester Utd" --target-team "Stoke C." --slot-limit 25 --dry-run
python -m app.cli team-roster-batch-edit DBDAT/EQ98030.FDI --player-file DBDAT/JUG98030.FDI --csv roster_plan.csv
python -m app.cli team-roster-batch-edit DBDAT/EQ98030.FDI --player-file DBDAT/JUG98030.FDI --csv roster_plan.csv --dry-run --json
python -m app.cli bitmap-reference-probe --json
```

Use these commands when you want scriptable output that stays aligned with the
GUI investigation surfaces.

The `player-name-capacity` probe is read-only and meant for API/import
preflight. It reports current byte capacity per matched player and whether a
proposed name is likely to fit, truncate, or overflow under the current writer
contract.

## Saving

All record edits are staged first.

- Field edits mark the record dirty.
- No write happens during typing.
- Team roster tools also stage changes now (slot edits, promotions, batch CSV).
- Club export now writes an import-ready roster batch template CSV so full-squad edits can round-trip directly through `Batch Import CSV`.
- Roster promotions now support `--fixed-name-bytes` (and GUI staged promotions default to this mode) to keep writes in-place by truncating/padding to existing name slot capacity.
- Fixed-byte promotions now use conservative safety gates; slots that cannot be patched safely are skipped with explicit diagnostics (slot, pid, reason code, and candidate summary) instead of forcing risky writes.
- The Team editor now exposes **Bulk Promote Linked Slots**, which stages all safe linked-slot promotions and shows skip diagnostics before Save All.
- Save All confirmation now includes staged promotion skip diagnostics so blocked slots are visible in the write plan review.
- `Save All` now shows a structured write plan (players/clubs/coaches/skills/
  roster ops) before commit.
- `Save All` writes staged player / club / coach / roster edits together.
- The save path now runs preflight safety checks first (missing file paths,
  malformed staged roster ops, and safe-mode non-name player edits) and blocks
  unsafe writes in one dialog before touching disk.
- After writing, the GUI runs the shared reopen validation path and reports
  whether the write succeeded cleanly, succeeded with validation warnings, or
  failed.
- If a save step fails mid-run, the GUI now attempts rollback using the backups
  created in that same save transaction and reports a rollback summary in one
  error dialog.

This separation is intentional: “bytes written” and “database healthy after
reopen” are distinct checks.

## Current limitations

- Some club rosters still depend on unresolved legacy inline roster families and
  may show as unavailable until those mappings are decoded.
- Coach linkage is still partial, so club-to-coach routing is deliberately
  conservative.
- Some league labels are still best-effort fallbacks driven by the recovered EQ
  team stream order rather than a fully decoded dedicated competition field.
  Strong probe matches are now promoted into a read-only
  `competition_probe_contract`, but unresolved clubs still remain fallback.
- The new secondary `+0x08/+0x0A` signature helps split many smaller shared
  competition families, but the dominant `0x7F` England-heavy family is still a
  weak split. League placement should still be treated as best-effort until the
  dedicated field is decoded cleanly.
- A first tertiary probe is also available now, but the current best candidate
  (`+0x01`) is still `no-gain` for the dominant `0x7F` family. It is useful as
  negative evidence, not as a stable inferred field.
- The newer non-text family-byte scan is the better follow-on for the hardest
  remaining family. On the current real corpus, the dominant `0x7F` group now
  points to `+0x16` as its best current non-text candidate, but it is still an
  exploratory read-only signal rather than a decoded dedicated field.
- The next narrower step for that same family is the dominant-country subgroup
  scan. For the England-heavy `0x7F` bucket, the current subgroup lead is now
  `+0x19`, and the `Inspect Primary-Code Family` plus
  `Profile Country Subgroups` views now expose that lead directly.
- Indexed JUG full-name edits now flow through the shared staged writer used by
  both CLI and GUI `Save All`, including variable-length payload rewrites that
  repoint indexed offsets/lengths safely.
- Bitmap / image assets are part of the broader PM99 data story, but they are
  not yet a first-class editor surface. They are tracked as a roadmap item and
  should be treated as a future read-first reverse-engineering milestone.

## Troubleshooting

| Symptom | Resolution |
| --- | --- |
| `Player file not found` or `Load failed` | Select any one of the PM99 `.FDI` files from a folder that contains the full set. |
| Clubs load but players say `on demand` | This is expected during staged startup. Wait for background warmup or use `Load Player Data`. |
| First club/player action pauses briefly | The player catalog may still be warming or may be loading on demand for the first time. |
| Save fails | Check file permissions and review the validation/report dialog for the failing stage. |

## Related documentation

- [Current Roadmap](./CURRENT_ROADMAP.md)
- [Architecture](./ARCHITECTURE.md)
- [Data Formats](./DATA_FORMATS.md)
- [Developer Guide](./DEVELOPER_GUIDE.md)
