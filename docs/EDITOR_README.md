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
- bitmap / asset reference string probing

They should be treated as research tools, not the main editing surface.

## Saving

All record edits are staged first.

- Field edits mark the record dirty.
- No write happens during typing.
- `Save All` writes staged player / club / coach edits together.
- After writing, the GUI runs the shared reopen validation path and reports
  whether the write succeeded cleanly, succeeded with validation warnings, or
  failed.

This separation is intentional: “bytes written” and “database healthy after
reopen” are distinct checks.

## Current limitations

- Some club rosters still depend on unresolved legacy inline roster families and
  may show as unavailable until those mappings are decoded.
- Coach linkage is still partial, so club-to-coach routing is deliberately
  conservative.
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
