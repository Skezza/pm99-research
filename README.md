# Premier Manager 99 — Database Editor & Reverse Engineering Notes

This repository contains a Python toolchain for inspecting and editing the *Premier Manager 99* database files (`*.FDI`). The code focuses on safe, conservative reads and writes so that original data can be restored if something goes wrong. This README consolidates the previously scattered markdown notes into a single reference covering workflow, binary-format discoveries, filter heuristics, performance tuning, and outstanding GUI work.

## Quick start
- **Python**: 3.8 or later.
- **Sample data**: copy the game files into [`DBDAT/`](DBDAT/).
- Run commands from the repository root.

### Common CLI tasks
The command line interface lives in [`pm99_editor/cli.py`](pm99_editor/cli.py) and exposes the following entry points:

```bash
# Inspect file header and record counts
python -m pm99_editor info DBDAT/JUG98030.FDI

# List the first N player records
python -m pm99_editor list DBDAT/JUG98030.FDI --limit 20

# Search players by a case-insensitive substring
python -m pm99_editor search DBDAT/JUG98030.FDI "Ronaldo"

# Rename a player by record id (prefer same-length names)
python -m pm99_editor rename DBDAT/JUG98030.FDI --id 123 --name "Cristiano Ronaldo"
```

### Test & toolchain essentials
- Install dependencies (the core modules rely on the standard library).
- Run the full test suite with `pytest -q`; regression tests cover decoding, writer fixups, filtering, and round-trips under [`tests/`](tests/).
- Explore the data programmatically:
  ```python
  python -q
  >>> from pm99_editor.io import FDIFile
  >>> f = FDIFile("DBDAT/JUG98030.FDI"); f.load()
  >>> f.records[0]
  ```
- Useful diagnostics: `debug_missing_players.py` and `debug_bartram_jones.py` inspect scanner coverage; `test_performance_improvements.py` benchmarks loader speed; `test_garbage_filters.py` exercises the filter heuristics.

## Binary format & reverse‑engineering findings
Authoritative notes pulled from the Ghidra sessions and validation scripts.

### Ghidra cross-reference

| Function | Address | Purpose | Highlights |
| --- | --- | --- | --- |
| `FUN_004afd80` | `0x004afd80` | Player (and coach) record parser | Sequentially walks the decoded payload: `team_id` → `squad` → given/surname via `FUN_00677e30`, then six-byte initials (each byte decremented, `0`→`'b'`), followed by metadata bytes (flag, nationality, DOB, height, weight) and the 10-byte attribute block. Confirms no `name_end + N` math. |
| `FUN_00677e30` | `0x00677e30` | Length-prefixed XOR string decoder | Reads a uint16 length, XORs data with `0x61` in 4/2/1-byte batches, and appends a null terminator. Returns `length + 1`, matching [`pm99_editor/xor.py`](pm99_editor/xor.py). |
| `FUN_004a0a30` | `0x004a0a30` | Loader entry point | Uses the FDI header at offsets `0x24`/`0x26` for directory lookup, falls back to sequential scan when counts/offsets fail, and feeds each buffer to `FUN_004afd80`. Mirrors our `FDIFile._iter_records()` walker. |

Additional Ghidra breadcrumbs worth keeping close:

- **FDI path strings** (validated addresses): `dbdat\jug98%03u.fdi` at `0x00735260`, `dbdat\eq98%03u.fdi` at `0x0073524c`, and `dbdat\ent98%03u.fdi` at `0x00734d10`.
- **Header fields**: the loader reads a 2-byte directory offset from `file_base + 0x24` and entry counts from `file_base + 0x26`. These offsets remain in the shipped binaries even though retail data requires the sequential fallback.
- **Attribute tail**: `FUN_004afd80` copies ten bytes straight into the in-memory struct (order: Passing, Shooting, Tackling, Speed, Stamina, Heading, Dribbling, Aggression, Positioning, Form). Keep unknown trailing bytes intact; the executable simply memcpys them after the attribute array.
- **Section framing**: every chunk starts with a 2-byte little-endian length prefix followed by bytes XOR’d with `0x61`. [`pm99_editor/xor.py`](pm99_editor/xor.py) mirrors the in-game routine that decodes in 4/2/1 byte chunks and appends a null terminator.
- **FDI container layout**: `FDIFile.load()` reads the header/directory (offsets `0x24`/`0x26`) but treats them as hints. Real data is discovered by sequentially scanning from `0x400` with `_iter_records()`, matching the retail executable’s loop.
### Player record field map

The executable walks each player payload sequentially. Treat the following structure as authoritative when reading or writing:

| Step | Bytes | Description | Notes |
| --- | --- | --- | --- |
| 1 | 2 | Team id | `<H` little-endian. Observed range `0x0e80`–`0x0edf` (3712–3807). |
| 2 | 1 | Squad number | Stored verbatim; `0x60` still appears for “unassigned”. |
| 3 | 2 + *n* | Given name | Length-prefixed (little-endian) then XOR’d with `0x61`. |
| 4 | 2 + *m* | Surname | Same decoder as the given name. |
| 5 | 6 | Initials block | Game subtracts `1` from each byte; `0` decodes to `'b'`. |
| 6 | 1 | Metadata flag | Byte preserved from legacy format; meaning unknown. |
| 7 | 1 | Nationality id | Table index, stored post-XOR. |
| 8 | 1 | Birth day | Range 1–31. |
| 9 | 1 | Birth month | Range 1–12. |
| 10 | 2 | Birth year | `<H`, typically 1960–1985 for shipped data. |
| 11 | 1 | Height | Centimetres; matches broadcast data after XOR. |
| 12 | 1 | Weight | Kilograms; still under review, preserve exact byte. |
| 13 | variable | Contract / extras | Unknown metadata carried forward untouched. |
| 14 | 10 | Attribute block | `[Passing, Shooting, Tackling, Speed, Stamina, Heading, Dribbling, Aggression, Positioning, Form]`. |

The six-byte metadata core (steps 7–12) was verified against CAÑIZARES and ZAMORANO: the day/month/year/height fields round-trip perfectly and nationality differs between Spain/Chile. Keep capturing examples to confirm the weight byte and to build a nationality lookup table for the CLI and GUI.

#### Hex walkthrough (Santiago CAÑIZARES, Real Madrid)

The snippet below shows the sequential bytes immediately after the `aaaa` name terminator in a decoded record. Each value is the on-disk byte after the outer XOR has been removed; applying another `^ 0x61` yields the in-game value.

```
... 61 61 61 61  60 00 12 0c b1 07 b5  4f ...
                ↑   ↑  ↑  ↑  ↑↑   ↑   ↑
                │   │  │  │  ││   │   └─ first attribute byte (Passing)
                │   │  │  │  ││   └──── height byte
                │   │  │  │  └┴──────── birth year (0x07b1 → 1969)
                │   │  │  └──────────── birth month (0x0c → 12)
                │   │  └─────────────── birth day (0x12 → 18)
                │   └────────────────── nationality code candidate (0x00)
                └────────────────────── position byte (0x60 → Defender)
```

Decoding each field with the second XOR produces `(position=1, nationality=0, day=18, month=12, year=1969, height=181)`, matching the known metadata for CAÑIZARES. The attribute window begins immediately after this metadata block; the first byte (`0x4f ^ 0x61 = 0x2e = 46`) demonstrates why attributes must be interpreted with the same sequential cursor rather than legacy `name_end + N` guesses.

### Team record markers

Team sections in `EQ98030.FDI` are longer but follow a consistent frame:

- Separator bytes decode to `0x61 0xdd 0x63`.
- A short header precedes the human-readable team name (≤60 characters, ASCII dominant).
- Stadium name and additional metadata trail after the first separator; expect stadium text once long runs of padding `0x61` appear.
- 543 distinct teams span 88 XOR chunks in the retail database, with ids aligning to the `0x0e80`–`0x0edf` player range.

Field-mapping utilities worth keeping handy:

- [`scripts/binary_field_mapper.py`](scripts/binary_field_mapper.py) — statistical byte-by-byte diffing for player payloads.
- [`scripts/scan_entire_team_file.py`](scripts/scan_entire_team_file.py) — enumerates all XOR sections, teams, and stadium strings.
- [`scripts/map_team_ids.py`](scripts/map_team_ids.py) — correlates player team ids against the decoded team sections.
- **Writing safeguards**: always go through [`file_writer.write_fdi_record()`](pm99_editor/file_writer.py). It recalculates the length prefix, rewrites following directory entries, and emits `.backup` files before touching disk.
- **Preserve unknown bytes**: `PlayerRecord.raw_data` keeps everything beyond the sequential cursor. Extend the parser cautiously and document new discoveries here once verified against the executable.

### Avoid outdated heuristics
Legacy notes referenced `name_end + 7/8/...` offsets and “double-XOR” terminology. The executable never consults a `0x61 0x61 0x61 0x61` marker for positioning—those bytes are padding emitted by the encoder. Any implementation that relies on `name_end` math will corrupt metadata. Treat marker-based helper scripts in `scripts/old_*` as historical context only.

## Player editing & renaming
- `PlayerRecord.set_given_name()`, `.set_surname()`, and `.set_name()` validate Latin-1, enforce the 12-character soft limit observed in-game, rebuild the sequential string payload, and update `self.name`. Unknown bytes and the attributes tail are copied through untouched.
- GUI wiring (`pm99_editor/gui.py`) should replace the read-only name label with paired `ttk.Entry` widgets (`given_name_var`, `surname_var`). Present validation errors before writing so partially edited records never hit disk.
- Add coverage before enabling saves:
  - Unit tests (`tests/test_player_renaming.py`) that mutate both name parts and assert a byte-for-byte round-trip.
  - An integration test that renames, saves via `file_writer`, reloads, and compares parsed models.
- `PlayerRecord.from_bytes()` still contains fallback marker searches for legacy data. The long-term goal is a single sequential parser/serializer pair that never peeks at padding yet preserves unknown bytes verbatim.

## Loader performance & scanning heuristics
- [`pm99_editor/scanner.py`](pm99_editor/scanner.py) merges the historical GUI scanner and the rewritten CLI pass into a single iterator. It performs hash-based dedupe of decoded blocks, uses a compiled regex to locate embedded records, and feeds candidates into `PlayerRecord.from_bytes()`.
- The *Emergency Handover* report captured a regression where an `elif`→`if` change forced every section to run both separated and embedded scans, ballooning load time to ~30s. Guard against this by skipping the embedded scan when the primary path already yielded canonical players or by tracking a `found_separated` flag.
- Confidence scoring favours aligned given/surname tokens, realistic team ids (<5000), complete attribute arrays, and plausible positions. Duplicates collide on uppercase names so higher scores replace noisy variants instead of appending.
- Regression safety net:
  - `python test_performance_improvements.py` — expect <5s on `JUG98030.FDI`.
  - `python -m pytest tests/test_regression_players.py::test_canonical_players_present` — ensures Vince Bartram, Lee Jones, and the other canonical fixtures remain discoverable while tuning heuristics.

## Filtering rules for teams & coaches
`pm99_editor/loaders.py` centralises parsing for both datasets so the CLI, GUI, and tests stay aligned. The heuristics stabilised after multiple rounds documented in the filtering markdowns:

### Team filters (balanced pass)
- Enforce 5–60 characters, uppercase first letter, ≥90% ASCII, and ≤40% lowercase `'a'` characters.
- Allow numeric prefixes only when followed by a space (`1860 München`); reject glued-on digits (`1FC`).
- Prefix guard blocks gibberish like `Tva`, `Uxa`, `Rva`, `Twa`, `Uza` unless the remainder contains club indicators (`FC`, `AC`, `CF`, `United`, `Town`, `Football`, `Club`, etc.).
- Embedded garbage detector only fires on long lowercase→uppercase→lowercase runs (`wHva`) or uppercase bursts in the middle of words (`NGva`). Earlier iterations rejected legitimate clubs; keep the relaxed form.
- Trailing garbage trimming drops endings such as `/aaaa`, `Aaaaa`, or long `'a'` tails once stadium text starts appearing.
- Token sanity check flags entries where most words are ≤2 characters unless we detect known abbreviations.
- **Expected result**: GUI Teams tab should list roughly 50–70 legitimate clubs rather than the 2–3 items we saw during over-filtered iterations.

### Coach filters (strict pass)
- Require 6–40 characters, two tokens minimum, uppercase initials per token, ≥85% ASCII, and ≤60% `'a'` characters overall.
- Apply the ~120 item blocklist built from the “Enhanced Filtering” docs: league/division names, cup names, stadiums, slogans, job titles, biographies, and ~50 known player names (Boa Morte, Stan Collymore, Jamie Redknapp, etc.).
- Reject tokens containing digits or punctuation beyond hyphen/apostrophe; these were common in stadium lines.
- **Expected result**: GUI Coaches tab should settle between 80–120 human names with no stadiums or marketing phrases.

### Validation commands
- `python test_garbage_filters.py` — 19/19 garbage samples rejected.
- `python -m pytest tests/test_loaders.py -v` — regression coverage for team/coach parsing plus guardrails for heuristics.

## GUI status & outstanding work
- **Coaches/Teams tabs**: sequential scans locate thousands of entries but the Tk tree can still show `Unknown Coach/Team`. Follow the debugging workflow from `HANDOVER_GUI_LOADING_ISSUES`: instrument `load_coaches()` / `populate_coach_tree()` in `pm99_editor/gui.py`, confirm the loader returns populated models, and verify the `ttk.Treeview` insertion logic uses a stable key (record offset or id) instead of occasionally empty name strings.
- **Team name extraction**: `TeamRecord._extract_name()` must follow the refined parsing routine — skip separator bytes, locate the first uppercase sequence after the `0x61 0xdd 0x63` separator, read ≤60 characters, strip trailing separators, and stop when stadium text starts. This is the main reason only ~24 teams show up in current builds.
- **Leagues tab**: `pm99_editor/league_definitions.py` maps team id ranges per country (England: 3712–3791 split across four divisions; other countries have single top flights). The planned UI adds a notebook tab with:
  - Country combobox to pick league groupings.
  - Search entry that filters by club name, id, or stadium substring.
  - `Treeview` with bold league parent rows and child rows showing team id, stadium, and capacity columns.
  - Double-click handler launching the existing editor with the selected team record.
  Complete this after the team-name parser is reliable so hierarchy counts stay meaningful.

## Historical investigations & guardrails
- **Legacy name parsing heuristics**: the Tkinter editor (`pm99_database_editor.py`) recovers full names from buffers that look like `HierrouaFernando Ruiz HIERROeagdenaaw`. It splits on `[a-z~@\x7f]{1,2}a(?=[A-Z])`, scores candidates (all-caps surnames + multi-word given names get priority), trims garbage suffixes (`POPESCUe` → `POPESCU`), and runs Latin-1 decoding with `errors="ignore"` so accents survive.
- **Critical parser fix retrospective**: synthetic tests once masked a broken CLI parser. Keep integration tests pointed at real FDI samples and prefer the sequential offsets validated by Ghidra rather than reviving `name_end` calculations.
- **Team database breakthrough**: investigations on `EQ98030.FDI` confirmed 543 teams split across 88 XOR sections. Scripts such as `map_team_record_structure.py` and `team_file_deep_analysis.py` map the stadium text trailing each club. Pin the team-id field so GUI lookups can eventually join players and teams.
- **Open questions**: the contract block after height/weight and several trailing bytes remain unmapped. Preserve them in `raw_data` until Ghidra or live instrumentation clarifies their purpose. Nationality code tables and weight semantics still need correlation against in-game data.

## Repository layout & maintenance
- [`pm99_editor/`](pm99_editor/) — core library, CLI, loaders, and models.
- [`pm99_database_editor.py`](pm99_database_editor.py) — legacy GUI prototype (still functional; contains heuristic parsing and dedup logic).
- [`scripts/`](scripts/) — exploratory tools from reverse engineering sessions. Treat results as hypotheses until migrated into the library.
- [`tests/`](tests/) — pytest suite; extend it whenever rules or encodings change.
- [`DBDAT/`](DBDAT/) & [`data/`](data/) — game assets and fixtures. Work on copies, keep `.backup` files generated by the writer, and never ship original game files.

### Maintenance checklist
- Always work on duplicate `.FDI` files and rely on the automatic `.backup` created by `file_writer.create_backup()`.
- Update or add tests (`pytest -q`) when adjusting parsing/writing logic or heuristics.
- Document additional byte rules, heuristics, or GUI workflows by extending the appropriate section of this README instead of creating new markdown files.
- Open pull requests with clear descriptions of binary changes and reference the relevant sections above so reviewers understand the guardrails that informed the change.
