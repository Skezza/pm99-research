# Premier Manager 99 Editor — User Guide

This guide explains how to operate the bundled tooling to inspect and edit Premier Manager 99 database files. It focuses on the Tk desktop editor (`app/gui.py`) and highlights companion CLI helpers for automation.

## Launching the GUI
1. Ensure the `DBDAT` folder containing `JUG98030.FDI`, `ENT98030.FDI`, and `EQ98030.FDI` is present alongside the repository.
2. From the repository root run:
   ```bash
   python -m app.gui
   ```
3. The window opens with a default size capped to your screen resolution and immediately loads `DBDAT/JUG98030.FDI`. Status updates appear in the bottom status bar (initially `Ready`).

### Command-line alternative
The same library powers a CLI that can inspect and edit records without the GUI:
```bash
python -m app info DBDAT/JUG98030.FDI   # header + counts
python -m app list DBDAT/JUG98030.FDI   # tabular roster output
python -m app search DBDAT/JUG98030.FDI "Ronaldo"
python -m app rename DBDAT/JUG98030.FDI --id 123 --name "New Name"
```
The GUI uses these same parsers; if the CLI works, the GUI will too.

## Window layout
The application hosts a left-hand navigation tree and a right-hand editor that changes with the active tab. Four notebook tabs are available: Players, Coaches, Teams, and ⚽ Leagues.

### Players tab
* **Search box** — typing filters the tree in real time using `filter_records()` logic; the search matches names and IDs.
* **Player list** — shows the deduplicated set of players detected by `FDIFile.load()`. Double-click a row to focus the record.
* **Detail editor** — lets you adjust:
  - Given name / surname (12 character guidance per field)
  - Team ID and squad number (`ttk.Spinbox` widgets with numeric ranges)
  - Position (`Goalkeeper`, `Defender`, `Midfielder`, `Forward`)
  - Nationality ID, date of birth (day/month/year spinboxes), and height
* **Attributes panel** — scrollable form containing twelve candidate attribute fields. Labels reflect current best guesses (e.g., "Attr 0 (Speed?)"). Values are stored even if the final semantics change.
* **Action buttons** —
  - `💾 Apply Changes` copies widget values into the active `PlayerRecord`, marks it as modified, and reports success in the status bar.
  - `🔄 Reset` restores the current record to its original values from the file.
* **Keyboard shortcut** — `Ctrl+S` triggers `save_database()` for the whole file.

### Coaches tab
* Loaded on demand when you first select the tab. The background thread updates the status bar (`"✓ Loaded … coaches"`).
* Search operates like the Players tab.
* The detail form exposes given name and surname fields. Applying changes rebuilds the encoded string blocks inside the `CoachRecord` payload and caches the edit.

### Teams tab
* Also lazy-loaded; the application keeps player search responsive while team data loads on a background thread.
* The roster tree displays leagues/countries pulled from `app/loaders.py`; selecting a team shows stadium and metadata fields in the right-hand overlay.
* Editable fields include team name, ID, stadium, capacity, car park size, and pitch quality (combo box of known constants).
* `Show squad lineup` toggles a roster sub-panel listing correlated player names when available.

### ⚽ Leagues tab
* Presents a hierarchical Country → League → Team tree built from `app/league_definitions.py` combined with parsed team data.
* Country and free-text filters help narrow large datasets; double-clicking a team row jumps to the Team overlay.
* Stadium name, capacity, and pitch details display alongside the tree so you can audit metadata without leaving the tab.

### Tools → Open PKF Viewer…
The Tools menu launches a file picker for PKF archives. After choosing a file the modal viewer uses [`PKFFile`](../app/pkf.py) to list entries and previews decoded bytes with the same `_format_hex_preview()` helper. Errors encountered while opening the archive are surfaced in the status bar.

## Saving and backups
* `Apply Changes` queues edits in memory; `Save Database` (menu item or `Ctrl+S`) writes them back to disk.
* `app/file_writer.py` creates a `.backup` copy before rewriting `JUG98030.FDI` so you can revert quickly.
* Directory offsets and the header `max_offset` are recomputed automatically; you do not need to adjust them manually even if record sizes change.

## Safety checklist
- Work on copies of the original `DBDAT` directory. Each save creates a backup, but keeping an untouched source is recommended.
- Keep names the same length when possible. If you extend them, reload the player in the GUI or via `python -m app info` to confirm offsets still line up.
- After major edits run `pytest -q` to ensure regression suites that depend on fixture files still pass.

## Troubleshooting
| Symptom | Resolution |
| --- | --- |
| `File not found` in status bar | Confirm the `.FDI` paths under `DBDAT/` match the defaults or use **File → Open Database…** to browse to a copy. |
| Players missing from list | Records without canonical names may be skipped by the deduplication heuristic. Confirm the entry with the CLI `list` command and, if necessary, locate it directly via the directory offsets shown in the console output. |
| Save fails | The status bar will show the exception message. Check file permissions and ensure the backup file can be created in the same directory. |
| GUI freezes during load | Large files are processed in background threads, but slow disks can still delay UI updates. Wait for the status bar confirmation before editing. |

Automated tests under `pytest` skip integration cases if the proprietary `DBDAT` assets are missing, so a clean checkout without the data will still report success (with skips). To exercise the full suite, supply the game databases before running the command.

For deeper technical detail see [`docs/ARCHITECTURE.md`](./ARCHITECTURE.md) and [`docs/DATA_FORMATS.md`](./DATA_FORMATS.md).

