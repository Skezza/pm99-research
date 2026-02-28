# PM99 Seed PDF Reverse-Engineering Notes (2026-02-26)

Date: 2026-02-26

## Scope

Iterated over the 12 seed PDFs in `.local/PM99RE-demo-pdfs/` and fed the findings back into the reverse-engineering workflow for the milestone sequence:

1. player renames
2. club renames
3. stadium renames
4. skill attributes (next target)

## Seed Corpus (Local)

Path: `.local/PM99RE-demo-pdfs/`

Documents detected and parsed:

- `Premier League Players.pdf` (player listing)
- `Division 1 Players.pdf` (player listing)
- `Division 2 Players.pdf` (player listing)
- `Division 3 Players.pdf` (player listing)
- `Premier League Managers.pdf` (manager listing)
- `Division 1 Managers.pdf` (manager listing)
- `Division 2 Managers.pdf` (manager listing)
- `Division 3 Managers.pdf` (manager listing)
- `Man Utd Bio.pdf` (club bio)
- `Stoke City Bio.pdf` (club bio)
- `Stoke City Players.pdf` (squad card)
- `Roy Keane Bio.pdf` (player bio)

## Tooling Added / Updated

### New script: `scripts/probe_seed_pdfs.py`

Purpose:

- classifies PM99 PDF types
- parses known layouts (player/manager listings, club bio, squad card, player bio)
- cross-checks managers/teams against local `DBDAT/`
- cross-correlates squad card vs player/manager listing PDFs
- optional strict player probe for metadata/attribute inspection (`--probe-player`)
- optional raw decoded-text probe (`--probe-text-query`) for parser-independent name matching
- optional `dd6361` biography-subrecord probe (`--probe-bio-marker`)
- optional auto player-bio linkage runner (`--probe-seed-player-bios`)

Example runs used:

```bash
python3 scripts/probe_seed_pdfs.py --json-output /tmp/pm99_seed_pdf_probe.json
python3 scripts/probe_seed_pdfs.py \
  --probe-player "Roy Keane" \
  --probe-player "Roy Maurice Keane" \
  --json-output /tmp/pm99_seed_pdf_probe_roy.json

python3 scripts/probe_seed_pdfs.py \
  --probe-text-query "Roy Maurice KEANE" \
  --probe-text-query "Roy Keane" \
  --json-output /tmp/pm99_text_probe_roy_keane.json

python3 scripts/probe_seed_pdfs.py \
  --probe-bio-marker "Roy Keane" \
  --probe-bio-marker "David Beckham" \
  --json-output /tmp/pm99_bio_marker_probe_keane_beckham.json

python3 scripts/probe_seed_pdfs.py \
  --probe-seed-player-bios \
  --json-output /tmp/pm99_seed_player_bio_linkage.json
```

### Compatibility fix for stadium milestone work: `app/models.py`

`TeamRecord` now syncs parsed stadium details to legacy attribute names used by GUI/export code paths:

- `capacity` <- `stadium_capacity`
- `pitch_quality` <- `pitch`

This removes a display/inspection mismatch when validating club/stadium edits.

### JSON CLI hygiene fix: `app/loaders.py`

Team/coach loader diagnostic prints now go to `stderr` (not `stdout`), so CLI commands like `team-search --json` remain valid machine-readable JSON on `stdout`.

## Findings By Milestone

### 1) Player Renames (Strong PDF Coverage)

All 4 league player-list PDFs parse cleanly with the existing player-list parser (`parse_listing_pdf` in `app/roster_reconcile.py`).

Player listing row counts:

- Premier League: `530` rows across `20` teams
- Division 1: `559` rows across `24` teams
- Division 2: `541` rows across `24` teams
- Division 3: `496` rows across `24` teams

Implication:

- These are excellent external validation sources for player rename workflows and reconciliation tuning.
- They are immediately usable with `roster-reconcile-pdf`.

### 2) Manager / Coach Renames (Good Coverage, Some Gaps)

All 4 manager-list PDFs parse cleanly with the new probe parser.

Local coach DB count (`DBDAT/ENT98030.FDI`): `95` coach records.

Manager listing -> coach DB surname cross-check (raw surname matching first, then normalized last-token):

- `Division 1 Managers.pdf`: `24` rows, normalized hits `22`, misses `2`
- `Division 2 Managers.pdf`: `25` rows, normalized hits `20`, misses `5`
- `Division 3 Managers.pdf`: `24` rows, normalized hits `20`, misses `4`
- `Premier League Managers.pdf`: `20` rows, normalized hits `16`, misses `4`

Observed miss examples include names like:

- `Buckley`, `Todd`
- `Evans`, `Mountfield`, `Reames`, `Sánchez`, `Ternent`
- `Joyce`, `O´Regan`, `Wood`
- `O'Leary`, `O'Neill`, `Robson`, `Vialli`

Implication:

- Manager PDFs are immediately useful for coach rename validation.
- Remaining misses are likely a mix of parser coverage gaps, data coverage differences, and normalization/alias issues.

### 3) Club Renames + Stadium Renames (PDF Fields Parse Cleanly; Team DB Coverage Still Limiting)

Club bio PDFs parse cleanly and provide structured club/stadium metadata.

`Man Utd Bio.pdf` extracted:

- Team label: `Manchester Utd.`
- Club name: `Manchester United F. C.`
- Ground: `Old Trafford`
- Capacity: `55,300`
- Size: `116x76m.`
- Foundation values shown twice in layout: `1897`, `1897`

`Stoke City Bio.pdf` extracted:

- Team label: `Stoke C.`
- Club name: `Stoke City`
- Ground: `Britannia Stadium`
- Capacity: `24,054`
- Size: `105x68m.`
- Foundation values shown twice in layout: `1868`, `1868`

Current limitation (confirmed again):

- `team-search DBDAT/EQ98030.FDI "Stoke" --json` returns `[]`
- local team parser/loader still yields only `24` valid teams, so these English club bios do not resolve in current team DB coverage

Implication:

- The PDFs give reliable external stadium/name targets for validation.
- The blocker is `EQ98030.FDI` parsing coverage, not a lack of reference data.

### 4) Squad Card (High-Value Cross-Document Validation)

`Stoke City Players.pdf` (squad card) now parses correctly, including the layout quirk where one goalkeeper line appears after `MANAGER`.

Extracted Stoke squad card summary:

- Manager: `Brian LITTLE`
- Group counts:
  - Goalkeepers: `2`
  - Defenders: `7`
  - Midfielders: `7`
  - Forwards: `4`
- Squad total: `20`

Cross-document validation against `Division 2 Players.pdf` (`Stoke C.` rows):

- Same-team player listing count: `20`
- Squad card vs listing surname overlap: `20/20`
- Missing from listing: none
- Extra in listing: none

Manager cross-check for Stoke:

- Squad card manager `Brian LITTLE` matches Division 2 manager listing surname (`Little`) for `Stoke C.`
- `coach-search DBDAT/ENT98030.FDI "Brian Little" --json` returns a matching coach record
- Last-name-only matching is ambiguous in coach DB (`Brian Little` and `Alan Little`), so first-name-aware matching is important

Implication:

- The Stoke squad card is a strong validation bridge between player listings, manager listings, and coach DB records.
- This is a good pattern to reuse for future club-specific validation packs.

### 5) Skill Attributes / Player Bio Linkage (Important Limitation Found)

`Roy Keane Bio.pdf` parses cleanly as a 5-page player bio with useful metadata:

- Name: `Roy Maurice KEANE`
- Birth date: `10/8/1971`
- Citizenship: `IRELAND`
- Previous team: `Nottingham Forest (93)`
- Position label: `MIDFIELDER`
- Sections present: personal data, technical characteristics, honours, international, anecdotes, last season, career, notes

Important observation (date-sensitive):

- The PDF shows `AGE 54 years` on `2026-02-26`, which suggests the exported age field may be dynamically generated at export time rather than fixed to the original 1998/99 season state.

Strict player probe results (`scripts/probe_seed_pdfs.py --probe-player ...`):

- Scanned strict entries/subrecords: `486`
- No strict hit for Roy Keane
- Only surname collision found: `Mark KEANE` (strict subrecord)

Implication:

- Roy Keane is not currently reachable via the strict subrecord path used by the probe (at least in this file/parser coverage).
- Skill-attribute reverse engineering from player bios will require a faster targeted heuristic/scanner path (or a cached player index) to reliably map bio documents to actual DB records.

### 6) Player Bio Linkage Breakthrough (Parser-Independent) — `dd6361` Bio Subrecords

Follow-up probing found a second subrecord family inside `DBDAT/JUG98030.FDI`:

- marker bytes: `dd 63 61` (hex)
- distinct from the existing strict player subrecord separator (`dd 63 60`)

This `dd6361` marker appears to delimit biography mini-records (or biography-oriented subrecords) containing star-player names and narrative text.

#### Roy Keane case (confirmed)

Raw decoded-text probe (`--probe-text-query`) finds:

- `Roy Maurice KEANE` in decoded entry `0x0005456B`
- nearby club mentions in the same decoded entry include:
  - `Manchester U`
  - `Manchester United`
  - `Nottingham Forest`

`dd6361` bio-marker probe (`--probe-bio-marker`) finds:

- `Roy Maurice KEANE` at entry `0x0005456B` (bio marker offset `13143` within entry)
- nearby club mentions again include `Manchester U` / `Manchester United` / `Nottingham Forest`

This provides a repeatable parser-independent linkage path for player bios even when no parseable player record object is produced by current strict/scanner pipelines.

#### Additional confirmation (same bio-marker path)

The bio-marker probe also finds:

- `David Robert BECKHAM` (Manchester United context)
- `Robbie KEANE` (Wolverhampton/Bury/Shrewsbury/Hull context)

This confirms the `dd6361` path is not a one-off and likely indexes a broad set of player biography records.

#### Auto seed-player-bio linkage (`--probe-seed-player-bios`)

For `Roy Keane Bio.pdf`, the automated linkage report now shows:

- inferred team from PDF career rows: `Manchester United`
- inferred team present in seed team packets: `true`
- inferred team mention hit in DB probes: `true`
- strict parser path exact-like hit: `false`
- strict hits are surname-only collisions (`Mark KEANE`)
- bio-marker full-name hit: `true` (`Roy Maurice KEANE`)

Implication:

- The current blocker is not absence of Roy Keane in `JUG98030.FDI`.
- The blocker is which record family the current parser pipeline can materialize.
- `dd6361` bio-subrecord parsing is now a concrete next path for player-bio linkage and later attribute-correlation workflows.

### 7) Club-Investigate Calibration: Stoke (Good) vs Manchester United (Noisy)

Using `club-investigate --include-heuristic` and comparing against seed team packets:

#### Stoke City (good calibration case)

- `target_entry_count`: `76`
- strict matches: `16`
- heuristic matches: `132`
- combined unique names: `142`
- seed roster size (verified from listing/squad card): `20`
- top-50 `club_index` surname overlap with seed roster: `9`

Notes:

- Stoke has a strong multi-source seed packet (player list + manager list + club bio + squad card).
- `club-investigate` surfaces useful Stoke-associated names, but many strict hits are not the first-team 20 (likely other squad/youth/background records).
- Existing roster reconciliation remains better for direct PDF->DB player matching on Stoke.

#### Manchester United (current failure mode)

- `target_entry_count`: `190`
- strict matches: `12`
- heuristic matches: `569`
- combined unique names: `570`
- seed roster size (Premier League listing): `24`
- top-50 `club_index` surname overlap with seed roster: `0`
- no `KEANE` names surfaced in `combined_unique_names`

Interpretation:

- Generic `Manchester`/`Manchester U` mentions cause broad overmatching in biography/news blobs.
- `club-investigate` is currently much less useful for high-visibility clubs with many incidental mentions.
- This is a precision problem (query alias overreach / context model), not necessarily a data absence problem.

#### Manchester United seed listing reconcile (team-scoped) — current mislink examples

Running `roster-reconcile-pdf` on `Premier League Players.pdf` with `--team "Manchester United"` (24 rows) shows the current listing-driven pipeline still struggles on key star names:

- `Keane` -> `isolated_wide_only` (provisional) with best candidate `Robbie KEANE`
- `Beckham` -> `no_db_candidate`
- `Giggs` -> `no_db_candidate`

At the same time, the new `dd6361` bio-marker probe can recover:

- `Roy Maurice KEANE`
- `David Robert BECKHAM`

This is direct evidence that the missing signal exists in `JUG98030.FDI`, but the current reconciliation candidate sources do not yet include the biography-subrecord family.

Practical takeaway:

- For clubs like Manchester United, use:
  1. seed team packets (player list + manager list + club bio + player bio)
  2. raw decoded-text probe / `dd6361` bio-marker probe for specific player names
  3. roster reconciliation for listing-driven matching

before relying on `club-investigate` for player-level linkage.

## CLI Validation (Current Toolchain)

Confirmed:

- `python3 -m app.cli roster-reconcile-pdf --help` shows `--name-hints`
- `coach-search` finds `Brian Little`
- `team-search "Stoke"` currently fails (known team parser coverage gap)
- `team-search --json` stdout is now clean JSON (`[]`), with loader diagnostics moved to `stderr`

Stoke team-scoped player reconciliation (using seed PDF):

```bash
python3 -m app.cli roster-reconcile-pdf \
  --pdf '.local/PM99RE-demo-pdfs/Division 2 Players.pdf' \
  --player-file DBDAT/JUG98030.FDI \
  --team 'Stoke City' \
  --json-output /tmp/stoke_seed_reconcile.json \
  --csv-output /tmp/stoke_seed_reconcile.csv
```

Observed summary (completed successfully):

- Schema: `v1`
- Rows: `20` across `1` team
- Status counts:
  - `isolated_default`: `10`
  - `ambiguous_default`: `1`
  - `ambiguous_wide_only`: `3`
  - `db_candidate_no_club_evidence`: `3`
  - `no_db_candidate`: `3`

Selected isolated defaults include:

- `Forsyth`
- `Keen`
- `Lightbourne`
- `Muggleton`
- `Petty`
- `Robinson`
- `Sigurdsson`
- `Sturridge`
- `Thorne`
- `Wallace`

Note:

- This team-filtered reconcile completed successfully but was slower than expected on this machine/session (roughly around a minute), so it is not yet “fast” enough for tight iteration loops.

Manchester United team-scoped player reconciliation (using seed PDF) was also run:

- `24` rows across `1` team
- status counts:
  - `isolated_default`: `7`
  - `isolated_wide_only`: `4`
  - `ambiguous_wide_only`: `2`
  - `db_candidate_no_club_evidence`: `2`
  - `no_db_candidate`: `9`

Key rows (current behavior):

- `Keane` -> `Robbie KEANE` (`isolated_wide_only`, provisional)
- `Beckham` -> `no_db_candidate`
- `Giggs` -> `no_db_candidate`

## Artifacts Generated (Local, Ephemeral)

- `/tmp/pm99_seed_pdf_probe.json`
- `/tmp/pm99_seed_pdf_probe_roy.json`
- `/tmp/pm99_seed_pdf_probe_team_packets.json`
- `/tmp/pm99_text_probe_roy_keane.json`
- `/tmp/pm99_bio_marker_probe_keane_beckham.json`
- `/tmp/pm99_seed_player_bio_linkage.json`
- `/tmp/stoke_seed_reconcile.json`
- `/tmp/stoke_seed_reconcile.csv`
- `/tmp/mu_seed_reconcile.json`
- `/tmp/mu_seed_reconcile.csv`

These are local analysis artifacts and should remain uncommitted.

## Skill Attribute Breakthrough (Seed Player Screenshots + `dd6361` Bio Trailers)

Using the user-provided screenshots in `.local/PlayerStills/` plus `ExamplePlayerData.txt`, the `dd6361` biography path now yields a direct stat mapping for the visible player skill/quality values.

### New finding: `dd6361` bio continuation trailer (`18` bytes)

For star-player biography records, the biography text ends with an `18`-byte trailer immediately before:

- the next `dd6361` biography marker, or
- a `dd6360` player subrecord marker (for some multi-player entries)

Important implementation detail:

- For multi-entry biographies (e.g. `Scholes`, `Beckham`, `Schmeichel`, `Giggs`), the trailer may sit in the **next decoded FDI entry** before the next `dd6361` marker, so a same-entry slice is insufficient.
- For some same-entry chains (e.g. `Stam`, `Yorke`, `Kavanagh`), the trailer is followed by a `dd6360` block; extraction must cut at the **first `dd6360` after the `dd6361` marker**.

### Trailer decode (`^ 0x61`) — verified field mapping (bytes `0..9`)

After XOR-decoding the trailer with `0x61`, bytes `0..9` map directly to visible screenshot values in this order:

1. `speed`
2. `stamina`
3. `aggression`
4. `quality`
5. `heading`
6. `dribbling`
7. `passing`
8. `shooting`
9. `tackling`
10. `handling`

This order is **not** the on-screen UI order for the six skill rows (which starts with `Handling`), but the values match exactly once reordered.

### Trailer bytes `11..16` (working interpretation)

Working structure hypothesis for the decoded `18`-byte trailer:

- bytes `0..9`: visible static stat values (solved)
- byte `10`: separator / reserved (almost always `0`)
- bytes `11..15`: **five role/suitability ratings** (working hypothesis; strongly supported)
- byte `16`: unresolved single value (likely dynamic state such as energy, or a role/state code)
- byte `17`: separator / reserved (`0` in all extracted cases)

Why `role/suitability ratings` is the leading hypothesis for bytes `11..15`:

- There are exactly **5** values.
- They correlate strongly with the solved skill bytes across the full `dd6361` corpus (`n=2113`), especially with outfield skill aggregates.
- In the seed screenshots:
  - `Paul SCHOLES` (`ROL.: Central Striker`) has `78,78,78,78,78`
  - `Graham KAVANAGH` (`ROL.: Central Mid.`) has `73,73,73,73,73`
  - wide/side roles (e.g. Beckham, Giggs) show non-uniform vectors

This pattern is consistent with a precomputed multi-role suitability vector rather than raw skills or padding.

### Verification status (8 seed players)

The mapping was verified against all 8 screenshot players:

- `Peter Boleslaw SCHMEICHEL`
- `David Robert BECKHAM`
- `Paul SCHOLES`
- `Jaap STAM`
- `Andrew Alexander COLE`
- `Ryan Joseph GIGGS`
- `Dwight YORKE`
- `Graham KAVANAGH`

Result:

- `7/8` OCR text blocks in `ExamplePlayerData.txt` match the decoded `mapped10` values exactly.
- `Paul SCHOLES` OCR text has a likely scrape error:
  - OCR text says `Speed 65`
  - screenshot image and decoded trailer both show `Speed 85`

### What is still unresolved in the trailer

Trailer decoded bytes `10..17` remain unresolved.

Observed pattern in this sample:

- byte `10` is `0` for all 8
- byte `17` is `0` for all 8
- bytes `11..16` vary and may encode additional derived/role ratings or another compact stat block

Broader corpus profiling (all extractable `dd6361` trailers, `n=2113`) shows these bytes are structured, not random padding:

- byte `17` is always `0`
- byte `10` is almost always `0` (`1968/2113`; small number of non-zero outliers)
- bytes `11..15` often form a repeated block (`1515/2113` rows have all five equal)
- bytes `11..15` distributions shift by decoded position class from the `dd6361` header token (especially clear for position class `0` vs `1/2/3`)

This strongly suggests bytes `11..16` encode a secondary rating/suitability family (or runtime-facing derived values), not freeform text/padding.

Byte `16` profile note:

- byte `16` has weak correlation with the solved stat bytes (near-zero to low correlations in broad profiling)
- distributions are discrete and broad by position class
- this makes it a better candidate for a **state/code field** than a direct derived stat

Possible candidates for byte `16` (still unresolved):

- hidden `EN`/energy-like state (roster list field)
- selected role code / tactical slot code
- other save-state or UI-facing per-player code

### On-screen `RATING` formula (seed screenshot verification)

For the seed screenshot set, the displayed `RATING` matches:

`floor((Speed + Stamina + Aggression + Quality + Fitness + Moral) / 6)`

Verification status:

- `7/8` OCR text blocks match directly
- `Paul SCHOLES` only fails because the OCR text scraped `Speed 65`
- using the decoded trailer speed (`85`) + screenshot `Fitness/Moral` gives the correct displayed rating (`82`)

Implication:

- `RATING` appears to be a runtime/display aggregate of the 6 core values, not an independently stored visible stat in the solved `dd6361` trailer bytes `0..9`.

The trailer does **not** (yet) explain:

- `Fitness`
- `Moral`
- `Rating`

These may be:

- stored elsewhere (another record family / save-state structure), or
- derived at runtime from multiple fields

### Tooling added for repeatable extraction

New local probe script:

- `scripts/probe_bio_trailer_stats.py`

Capabilities:

- extracts ordered `dd6361` biography markers
- stitches cross-entry biography continuations
- isolates the trailer before `dd6360` / next `dd6361`
- decodes `^0x61` trailer bytes
- emits `mapped10` stat values
- optionally compares against `.local/PlayerStills/ExamplePlayerData.txt`

Command used (seed 8 verification):

```bash
python3 scripts/probe_bio_trailer_stats.py \
  --name 'Peter Boleslaw SCHMEICHEL' \
  --name 'David Robert BECKHAM' \
  --name 'Paul SCHOLES' \
  --name 'Jaap STAM' \
  --name 'Andrew Alexander COLE' \
  --name 'Ryan Joseph GIGGS' \
  --name 'Dwight YORKE' \
  --name 'Graham KAVANAGH' \
  --json-output /tmp/pm99_bio_trailer_stats_seed8.json
```

Local artifact (ephemeral):

- `/tmp/pm99_bio_trailer_stats_seed8.json`

### Additional iteration findings (GUI roster columns, `dd6360` tail split, byte16 evidence)

#### GUI `EN / AV / ROL.` columns are not yet wired to player data

I traced the current GUI team overlay roster table in `app/gui.py`:

- headers exist for `EN`, `SP`, `ST`, `AG`, `QU`, `FI`, `MO`, `AV`, `ROL.`, `POS`
- but there is **no current row population implementation** for `self.team_roster_tree`

Implication:

- the GUI does not currently provide an implementation source-of-truth for `EN`, `AV`, or numeric `ROL.`
- those fields must be reverse engineered from the binary structures directly (not inferred from current GUI code)

#### `dd6360` strict subrecord tail-12 != screenshot-visible `dd6361` trailer stats

I compared known strict `dd6360` subrecords (e.g. `Ciaran KAVANAGH`) against the solved `dd6361` trailer mapping:

- strict `PlayerRecord` parsing still reads a fixed tail-12 block (`len-19 .. len-7`)
- this tail often yields values such as:
  - `attrs12 [1, 72, 67, 64, 70, 61, 59, 64, 60, 67, 17, 0]` (example: `Ciaran KAVANAGH`)
- these do **not** match the screenshot-visible values recovered from the `dd6361` biography trailer
  - `Graham KAVANAGH` screenshot/bio-trailer `mapped10`: `72, 65, 67, 69, 71, 69, 74, 76, 73, 26`

Implication:

- the strict `dd6360` tail-12 block is a **different attribute family** (or a different view/encoding), not the same stat set as the on-screen player page values solved in `dd6361`
- we should avoid conflating the current `PlayerRecord.attributes` heuristic with the screenshot stat mapping

#### Stronger evidence that trailer byte `16` is not a deterministic skill-derived field

New corpus-level summary mode was added to `scripts/probe_bio_trailer_stats.py`:

- `--include-corpus-summary`

Full-corpus run (`n=2009` extractable `dd6361` trailers in the current extraction path) shows:

- `role_ratings5` are all-equal in `1432/2009` rows (`~71.3%`)
- `byte16` distribution is broad (`min=10`, `max=97`, many clustered values in the `40s-50s`)

Most important new evidence:

- there are **multiple cases** where players share the same `decoded18[0:16]` (same solved stat bytes + same role vector bytes) but have **different** `byte16` values

Examples (same static+role trailer fields, different `byte16`):

- `Wayne Lawrence BROWN` vs `John Neil KENNEDY` (`byte16`: `51` vs `56`)
- `Darel RUSSELL` vs `Che WILSON` (`byte16`: `37` vs `46`)
- `Julian DARBY` vs `Jamie William HOYLAND` (`byte16`: `38` vs `55`)

This is strong negative evidence against:

- `byte16` being a deterministic function of the solved `mapped10` stats
- `byte16` being a deterministic function of the `role_ratings5` vector

It remains consistent with:

- dynamic/player-state field (energy/condition-style)
- another code/index used by UI/tactics/selection logic

Local artifact (ephemeral):

- `/tmp/pm99_bio_trailer_all_summary.json`

#### Seed screenshot `ROL.` numeric box extraction (new evidence)

I extracted the tiny on-screen numeric `ROL.` selector box from the 8 provided screenshots (manual crop calibration for the 640x480 images) and manually read the displayed values.

Seed-8 `ROL.` numeric readings (from screenshots):

- `Peter Boleslaw SCHMEICHEL` -> `2`
- `David Robert BECKHAM` -> `8`
- `Paul SCHOLES` -> `1`
- `Jaap STAM` -> `4`
- `Andrew Alexander COLE` -> `8`
- `Ryan Joseph GIGGS` -> `1`
- `Dwight YORKE` -> `3`
- `Graham KAVANAGH` -> `0`

I then joined these readings against the solved `dd6361` trailer fields (`role_ratings5`, `byte16`) for the same 8 players.

Validated negative findings (seed-8):

- `ROL.` numeric value does **not** directly equal any of the 5 `role_ratings5` values (`0/8` matches)
- `ROL.` numeric value does **not** equal trailer byte `16` (`0/8` matches)
- `ROL.` numeric value is **not** simply:
  - `argmax(role_ratings5)` index (`1/8` accidental match)
  - `argmin(role_ratings5)` index (`2/8` accidental matches)

Implication:

- the displayed `ROL.` numeric box is likely a **separate tactical role code/index space** (0..8 in this sample), not a direct display of the `dd6361` role suitability values or byte `16`
- the `role_ratings5` vector still looks like suitability/derived ratings, but the UI role selector code appears to be sourced elsewhere

Additional validated clue (seed-8):

- the `ROL.` numeric code is **not a unique global role enum** in this sample
- duplicate code -> multiple displayed role labels:
  - code `1` -> `Central Striker`, `Left Forward`
  - code `8` -> `Centre Forward`, `Right Mid.`

Implication:

- the displayed numeric `ROL.` code likely indexes a **position/context-dependent tactical role table** (or another higher-level role code space), not a one-to-one role label ID

Additional negative check:

- no simple aligned raw/XOR byte around the `dd6361` trailer boundary (±128 bytes in the extracted biography payload) matched the seed `ROL.` numeric values across all 8 anchors

This does **not** rule out:

- the role code living in another linked subrecord (possibly `dd6360` or another container segment)
- a per-player code stored outside the biography payload and only surfaced on the player UI page

Tooling added for repeatable screenshot `ROL.` evidence capture:

- `scripts/probe_screenshot_rol_boxes.py`

Capabilities:

- deterministic crop of the tiny `ROL.` numeric box from the provided screenshots
- joins each screenshot to `dd6361` bio trailer values
- records manual readings and validates common direct-match hypotheses (`role_ratings5`, `byte16`, argmax/argmin)

Validation artifact (ephemeral):

- `/tmp/pm99_rol_box_probe_seed8.json`
- `/tmp/pm99_rol_box_probe_seed8_v2.json`

Observed summary from the artifact:

- `rol_num_matches_any_role_ratings5_value_count = 0`
- `rol_num_equals_byte16_count = 0`
- `rol_num_matches_argmax_index0_count = 1`
- `rol_num_matches_argmin_index0_count = 2`
- `rol_num_non_unique_role_label_codes = {1, 8}` (both map to multiple role labels in the seed set)

#### `dd6361` header-prefix bytes checked (no direct Fitness/Moral/ROL hit yet)

I also checked the early `dd6361` biography bytes (header/prefix area before the readable biography text) across the same 8 screenshot anchors:

- no direct aligned raw/XOR byte matched the screenshot `Fitness` values (`70` for all 8)
- no direct aligned raw/XOR byte matched the screenshot `Moral` values (`99/99/..../93/97` mix)
- no simple raw/XOR/nibble transform in the early prefix bytes matched the screenshot `ROL.` numeric readings

Implication:

- `Fitness`, `Moral`, and the displayed `ROL.` selector code are still not located in the currently solved `dd6361` header/trailer bytes
- the next likely search area is linked/non-bio payloads (adjacent container structures, `dd6360`, or another player-state record family)

#### Marker-neighborhood validation: seed biographies are not locally adjacent to matching `dd6360` player subrecords

I built a combined marker stream probe across decoded `JUG98030.FDI` entries:

- `dd6360` (player-like separator/subrecords)
- `dd6361` (biography separator/subrecords)

and inspected neighborhoods around the 8 seed biography anchors.

New local probe:

- `scripts/probe_marker_neighborhoods.py`

Seed-8 validation result (`--same-surname-window 200`):

- `8/8` seed `dd6361` biographies had **no** `dd6360` marker within ±200 markers whose parsed surname matched the biography surname

Examples (nearest `dd6360` parsed neighbors are unrelated):

- `David Robert BECKHAM` bio neighbors -> `Daniel ANDERSSON` / `Fabien BARTHEZ`
- `Paul SCHOLES` bio neighbors -> `Daniel ANDERSSON` / `Fabien BARTHEZ`
- `Ryan Joseph GIGGS` bio neighbors -> `Daniel ANDERSSON` / `Fabien BARTHEZ`
- `Graham KAVANAGH` bio neighbors -> `Alessandro MAZZOLA` / `Darren FERGUSON`
- `Dwight YORKE` bio neighbors -> `Savo MILOSEVIC` / `Simon JENTZSCH`

This does **not** prove there is no linked player record elsewhere, but it does invalidate a simple local-neighborhood assumption for the seed set:

- the matching player record is not generally the immediately previous/next `dd6360` marker near a `dd6361` biography
- for several high-profile Man Utd bios (e.g. Beckham/Scholes/Cole/Giggs), the stream shows long `dd6361`-only stretches before the next `dd6360`

Practical implication for the next search:

- searching for `Fitness` / `Moral` / `ROL.` code should not rely on “nearest `dd6360` to biography” heuristics alone
- we likely need a broader container/linkage strategy (cross-record indexing, hidden IDs, or another state record family)

Validation artifact (ephemeral):

- `/tmp/pm99_marker_neighborhood_seed8.json`

#### Corpus-wide check: local `dd6361`↔`dd6360` matches are uncommon (not just a seed-star quirk)

Using `scripts/probe_marker_neighborhoods.py --corpus-surname-summary`, I measured how often a named `dd6361` biography has a nearby parsable `dd6360` with the same surname / exact name.

Current extraction counts:

- named `dd6361` biographies: `2018`

At ±200 markers:

- same-surname nearby `dd6360`: `73 / 2018` (`~3.62%`)
- exact-name nearby `dd6360`: `29 / 2018` (`~1.44%`)
- any same-entry parsable `dd6360` present: `1122 / 2018` (`~55.6%`)

Interpretation:

- many biographies do share entry containers with `dd6360` segments, but a **matching** player record by local marker-neighborhood heuristics is rare
- this supports the seed-8 conclusion that local proximity is not a reliable linkage strategy

Validation artifact (ephemeral):

- `/tmp/pm99_marker_neighborhood_corpus_summary.json`

#### Preliminary cross-record prefix-byte linkage clue (`dd6361` vs exact nearby `dd6360`)

I used the `29` rare exact-name local matches (within ±200 markers) as a small training set to compare `dd6361` and `dd6360` subrecord prefixes.

Observed prefix-byte agreement in these exact pairs:

- `dd6361[4] == dd6360[4]` in `28/29` pairs
- `dd6361[5] == dd6360[5]` in `24/29` pairs
- `dd6361[6]` vs `dd6360[6]` shows a small-delta distribution (often `0`, `±1`, `±2`, `±5`) rather than a stable equality
- `dd6361[3]` vs `dd6360[3]` does **not** match directly (varied deltas)

What this likely means:

- `dd6361` and `dd6360` appear to share part of a common subrecord-header family (bytes `4` and often `5`)
- but the prefix is **not** unique enough on its own to link biographies to player subrecords in the seed-star cases

Seed-star prefix-signature test (`dd6361` prefix bytes `4,5` and `4,5,6` against all `dd6360` prefixes):

- `David Robert BECKHAM`: `0` `dd6360` candidates with exact `(4,5)` or `(4,5,6)` prefix match
- `Andrew Alexander COLE`: `1` `(4,5)` candidate, `0` `(4,5,6)` candidates (not a matching name)
- `Ryan Joseph GIGGS`: `1` `(4,5)` candidate, `0` `(4,5,6)` candidates
- `Dwight YORKE`: `3` `(4,5)` candidates, `0` `(4,5,6)` candidates
- `Graham KAVANAGH`: `4` `(4,5)` candidates, `1` `(4,5,6)` candidate (`Darren FERGUSON`, not a matching name)

Interpretation:

- shared prefix bytes are a real clue, but the current prefix signature is still too weak/noisy for reliable identity linkage
- next linkage work should combine:
  - prefix bytes
  - container/entry provenance
  - name decoding confidence
  - possibly another hidden field outside the currently compared prefix bytes

Validation artifact (ephemeral, one-off exploratory run):

- `/tmp/pm99_dd60_dd61_prefix_linkage_probe.json`

#### Stoke lineup screenshot (team roster table) validation — `AV`, `EN`, `FI`, `ROL.` behavior

The provided `.local/StokeCityLineup.png` is exactly the kind of evidence needed for the roster-table columns (`EN / SP / ST / AG / QU / FI / MO / AV / ROL. / POS`).

I manually transcribed the visible `20` rows (starters + substitutes + visible reserves) into a reproducible artifact and validated formulas against the table values.

New local probe:

- `scripts/probe_lineup_screenshot.py`

Validation artifact (ephemeral):

- `/tmp/pm99_stoke_lineup_probe.json`

##### `AV` formula confirmed on roster table (20/20 rows)

For all 20 visible Stoke rows, lineup `AV` matches:

`floor((SP + ST + AG + QU + FI + MO) / 6)`

This matches the same formula already validated on the player-page `RATING`/average-style calculation path from the screenshots.

##### `EN` and `FI` behavior in this screenshot

Observed in the Stoke opening-day lineup screenshot (all 20 visible rows):

- `EN = 99` for every row (`20/20`)
- `FI = 70` for every row (`20/20`)

Interpretation (still provisional, but strongly suggested):

- `EN` and `FI` are likely dynamic/state-like values that can be globally uniform at season start (or at least in this scenario)
- they should not be assumed to be part of the same static attribute family as `SP/ST/AG/QU`

##### `ROL.` code in lineup table is position-context dependent (Stoke sample)

Visible Stoke lineup `ROL.` codes present:

- `{0, 2, 3, 4, 6, 8}`

By position in this screenshot:

- `FOR` -> `{8}` (all visible forwards)
- `MID` -> `{4, 6}`
- `DEF` -> `{0, 4}`
- `GOAL` -> `{2, 3}`

This is strong evidence that lineup `ROL.` is a **contextual tactical role code**, not a simple single stat or global label ID.

##### Cross-check with player-page screenshot: Graham KAVANAGH

Comparing the Stoke lineup row (`Kavanagh`) to the previously provided player-page screenshot (`Graham KAVANAGH`):

Same values:

- `SP=72`, `ST=65`, `AG=67`, `QU=69`, `FI=70`, `AV=73`, `POS=MID`

Different values:

- `MO`: lineup `99` vs player-page `97`
- `ROL.` numeric code: lineup `6` vs player-page `0`

Interpretation:

- `MO` (morale) is likely dynamic/time/context-dependent
- the displayed `ROL.` numeric code is also context-dependent (player page vs lineup view may show different role-code semantics or different selected-role states)

This is one of the strongest pieces of evidence so far that both `MO` and `ROL.` are not fixed static values tied only to the solved `dd6361` trailer skill block.

#### Manchester Utd opening-day lineup screenshot validation (cross-team confirmation)

The provided `.local/ManUtd.png` (opening-day lineup table) gives a second high-signal roster-table sample with many overlaps to the player-page screenshot seed set (`Schmeichel`, `Stam`, `Beckham`, `Cole`, `Yorke`, `Scholes`, `Giggs`, and reserve `Keane`).

I manually transcribed the visible `20` rows (starters + substitutes + visible reserves) into `scripts/probe_lineup_screenshot.py` and re-ran the same validations used for Stoke.

Validation artifact (ephemeral):

- `/tmp/pm99_manutd_lineup_probe.json`

Results (Man Utd lineup, 20 visible rows):

- `AV` formula holds for all rows (`20/20`):
  - `floor((SP + ST + AG + QU + FI + MO) / 6)`
- `EN = 99` for all visible rows (`20/20`)
- `FI = 70` for all visible rows (`20/20`)
- `MO` range across visible rows: `94..99`
- lineup `ROL.` codes present: `{0, 2, 3, 4, 6, 8}`

By position in the Man Utd lineup screenshot:

- `DEF` -> `{0}`
- `MID` -> `{4, 6}`
- `FOR` -> `{8}`
- `GOAL` -> `{2, 3}`

Cross-team implication (Stoke + Man Utd together):

- the same `ROL.` code family (`{0,2,3,4,6,8}`) appears in both opening-day lineup tables
- `MID/FOR/GOAL` positional buckets align across both samples
- `DEF` appears broader in Stoke (`{0,4}`) than in this Man Utd snapshot (`{0}`), which supports lineup-role selection/tactic dependence rather than a single immutable defender code

#### Cross-check probe: lineup table vs player-page screenshots vs `dd6361` (`Stoke + Man Utd`)

To make the comparisons reproducible, I added:

- `scripts/probe_lineup_playerpage_crosscheck.py`

This joins:

- lineup-table screenshot transcriptions (`scripts/probe_lineup_screenshot.py`)
- player-page screenshot text scrape (`.local/PlayerStills/ExamplePlayerData.txt`)
- manual player-page `ROL.` number readings (`scripts/probe_screenshot_rol_boxes.py`)
- `dd6361` biography trailer extraction (`scripts/probe_bio_trailer_stats.py`)

Validation artifact (ephemeral):

- `/tmp/pm99_lineup_playerpage_crosscheck.json`

##### Stoke overlap (1 player-page anchor)

Overlap found in current screenshot set:

- `Kavanagh` (`Graham KAVANAGH`)

Results:

- lineup vs player-page `core6` exact match: `0/1`
- lineup `AV` equals player-page `RATING`: `1/1`
- lineup `ROL.` equals player-page `ROL.` numeric: `0/1`
- exact `dd6361` core4 (`SP/ST/AG/QU`) match for overlap: `1/1`

Observed mismatch details:

- `MO` differs: lineup `99` vs player-page `97`
- `ROL.` numeric differs: lineup `6` vs player-page `0`

This confirms, again, that `MO` and displayed `ROL.` are context/time/state dependent.

##### Man Utd overlaps (7 player-page anchors)

Overlaps found:

- `Schmeichel`
- `Stam`
- `Beckham`
- `Yorke`
- `Scholes`
- `Giggs`
- `Cole`

Summary (Man Utd, `7` overlaps):

- lineup vs player-page `core6` exact match: `5/7`
- lineup `AV` equals player-page `RATING`: `6/7`
- lineup `ROL.` equals player-page `ROL.` numeric: `1/7`
- exact `dd6361` core4 (`SP/ST/AG/QU`) match for overlaps: `7/7`

Key mismatch details:

- `Schmeichel`: lineup `ROL=3` vs player-page `ROL=2` (core6 match otherwise)
- `Stam`: lineup `ROL=0` vs player-page `ROL=4` (core6 match otherwise)
- `Beckham`: lineup `ROL=4` vs player-page `ROL=8` (core6 match otherwise)
- `Giggs`: lineup `ROL=6` vs player-page `ROL=1` (core6 match otherwise)
- `Yorke`: lineup `MO=99` vs player-page `MO=93`; lineup `AV=84` vs player-page `RATING=83`; lineup `ROL=8` vs player-page `ROL=3`
- `Scholes`: lineup `SP=85` vs `ExamplePlayerData.txt` `SP=65`; flagged as likely OCR scrape error because:
  - lineup value matches the actual screenshot
  - exact `dd6361` core4 also matches lineup (`SP=85`, `ST=81`, `AG=80`, `QU=81`)

Important consequence:

- the lineup tables and `dd6361` trailer mapping now mutually reinforce each other for the overlapping stars (`7/7` exact core4 matches in Man Utd overlaps)
- `MO` and `ROL.` remain the main context-sensitive fields in these cross-view comparisons

#### `Keane` disambiguation resolved in the lineup context (`Roy` vs `Robbie`)

The Man Utd lineup screenshot includes reserve row:

- `Keane` (`MID`) with lineup core4:
  - `SP=88`, `ST=93`, `AG=99`, `QU=87`

Using `scripts/probe_lineup_playerpage_crosscheck.py`, I compared this lineup row against all `dd6361` surname=`KEANE` candidates:

- `Roy Maurice KEANE` -> exact core4 match (`L1 distance = 0`)
- `Robbie KEANE` -> non-match (`L1 distance = 59`)

This provides a clean, data-backed disambiguation for the lineup `Keane` row:

- it is `Roy Maurice KEANE`, not `Robbie KEANE`

This also directly addresses the earlier roster-reconciliation misassignment risk where a surname-only path could drift toward `Robbie KEANE`.

#### Team-player extraction readiness (data-backed answer: hybrid path is close, direct path is not)

To answer "how close are we to extracting all players for a team programmatically?", I added a readiness probe that benchmarks the current parser/linkage paths against the two known lineup datasets (`Stoke` + `Man Utd`, `40` visible rows total).

New probe:

- `scripts/probe_team_extraction_readiness.py`

Validation artifact (ephemeral):

- `/tmp/pm99_team_extraction_readiness.json`

This probe measures two paths:

1. **Direct strict parser path** (`gather_player_records_strict`, `dd6360`-oriented)
2. **Hybrid identity path** (`dd6361` biographies + lineup `SP/ST/AG/QU` core4 disambiguation)

##### Direct strict parser path (current state: not close for team extraction)

Strict parser scan counts on `DBDAT/JUG98030.FDI`:

- valid: `5751`
- uncertain: `2452`
- total candidate player-like rows: `8203`

Against the `40` known lineup rows:

- rows with any strict name match: `14/40`
- unique strict matches: `7/40`
- ambiguous strict matches: `7/40`
- rows with any matched candidate carrying non-zero `team_id`: `0/40`
- matched rows with only `team_id=0` candidates: `14/40`

Interpretation:

- the current strict parser path is **not** yet usable for authoritative team roster extraction
- even when it finds same-surname players, they are often the wrong identity and `team_id` is still unusable (`0`)

##### `dd6361` hybrid identity path (current state: getting close for identity extraction, but not team membership)

Against the same `40` lineup rows:

- rows with a `dd6361` biography name match (name heuristic): `35/40`
- `dd6361` name-unique matches: `27/40`
- ambiguous `dd6361` name matches: `8/40`
- ambiguous rows resolved by exact core4 (`SP/ST/AG/QU`) match: `7/40`
- **core4-validated resolved identities** (`name_unique_core4_exact + resolved_by_core4_exact`): `31/40`

Important nuance:

- `3` "name-unique" matches were false positives when checked against core4 stats (surname-only uniqueness is not enough)
  - `Stoke`: `Fraser`, `Petty`
  - `Man Utd`: `Neville P.` (picked `Philip John NEVILLE` via surname+initial but core4 mismatch indicates this is not yet safe)

Unresolved / not-yet-safe rows in this benchmark:

- `Stoke`: `Clarke` (name match exists but no exact core4 match), `Wallace`, `Crowe`, `McKenzie`, `Heath`, `Fraser`, `Petty`
- `Man Utd`: `Neville G.`

Interpretation:

- if we already know the team roster names from another source (PDF/listing/screenshot), the `dd6361` path is **close** to robust player identity resolution
- but this is still **not** the same as programmatic team extraction from raw game data, because the missing step is authoritative team membership linkage (and dynamic/state data linkage for lineup-context values)

##### Practical answer ("Are we close?")

Short answer:

- **For a hybrid pipeline** (team roster names from PDF/list + game data for identity/stat linkage): **yes, fairly close**
- **For direct extraction from `DBDAT/*.FDI` alone** (authoritative team roster by team, no external list): **not yet**

#### `EQ98030.FDI` team loader coverage breakthrough (sequential scan across all XOR entries)

I identified that `load_teams()` was only scanning two hardcoded `EQ98030.FDI` sections, which is why `team-search` previously returned only `24` teams and missed `Stoke` / `Manchester`.

I updated `app/loaders.py` so `load_teams()` now:

- sequentially scans all length-prefixed XOR entries in `EQ98030.FDI` (starting at `0x400`)
- decodes each entry
- searches each decoded entry for the team-record separator (`61 dd 63`)
- parses/deduplicates `TeamRecord` candidates across all entries

Validation (local CLI):

- `python3 -m app.cli team-search DBDAT/EQ98030.FDI "Stoke" --json`
  - loads `532` teams
  - returns `Stoke C` (`Britannia Stadium`)
- `python3 -m app.cli team-search DBDAT/EQ98030.FDI "Manchester" --json`
  - loads `532` teams
  - returns `Manchester Utd` and `Manchester C`

Follow-up cleanup (post-breakthrough):

- tightened loader validation to reject short garbage names (e.g. `Mar`)
- `TeamRecord` extracted-text cleanup now strips the leading delimiter artifact (`a`) before capitalized team/stadium strings
  - `aOld Trafford` -> `Old Trafford`
  - `aBritannia Stadium` -> `Britannia Stadium`

What this changes:

- team coverage is now dramatically better and no longer the immediate blocker for finding target clubs
- direct team extraction is still **not** comfortable yet, because player-team linkage remains unresolved (strict player benchmark still `0/40` rows with non-zero `team_id` candidates)
- there is now a clearer path:
  - team-side lookup via `EQ98030.FDI` is available
  - player-side identity via `dd6361` is strong for many cases
  - the main remaining join problem is authoritative team membership / player-state linkage

What must land before I would call direct team extraction "comfortable":

1. A reliable player-team linkage path (strict `dd6360` parser currently yields `0/40` matched rows with non-zero `team_id` in this benchmark)
2. Team parser cleanup/normalization pass for remaining noisy strings and suspicious values (notably some `team_id=0` real clubs and noisy global-club aliases)
3. Optional but valuable: dynamic-state linkage (`MO`, lineup `ROL.`, likely `EN`) for in-situ roster/lineup extraction parity

What makes me optimistic:

- the `dd6361` bio path is now a strong identity/stat anchor for many players
- lineup tables and player pages both validate the same core stat semantics and `AV` formula
- name-collision risks (e.g. `Keane`) can be solved cleanly once we use core4 evidence instead of surname-only matching

#### Full install / binary reconnaissance (pre-Ghidra, using `.local/premier-manager-ninety-nine/`)

With the full game install now available locally, I added a lightweight binary/install probe so the executables and file layout can be used immediately (before Ghidra setup is complete).

New probe:

- `scripts/probe_pm99_install_binaries.py`

Validation artifact (ephemeral):

- `/tmp/pm99_install_binaries_probe.json`

Probe output includes:

- executable/DLL inventory + SHA256
- relevant ASCII strings (FDI/DBDAT paths, save paths, tactics paths, lineup/training labels)
- marker-byte presence checks (`dd6360`, `dd6361`, `61dd63`) in binaries
- save-directory inventory heuristics
- `TACTICS/` inventory (`TACTIC.*`, `predef.*`, `partido.dat`)

##### Confirmed installed binaries/modules

- `PM99.EXE`
- `MANAGPRE.EXE`
- `DBASEPRE.EXE`
- `MIDAS11.DLL`
- `RegSetUp.exe`

##### High-value findings from `MANAGPRE.EXE` strings

`MANAGPRE.EXE` contains direct references to the core data files and editor-relevant UI concepts:

- FDI templates:
  - `dbdat\\jug98%03u.fdi`
  - `dbdat\\eq98%03u.fdi`
  - `dbdat\\ent98%03u.fdi`
- lineup/tactics/attributes labels:
  - `LINE-UP`, `TACTICS`, `ROL.`, `FITNESS`, `STAMINA`, `AGGRESSION`, `QUALITY`, `MORAL`
- save system paths:
  - `save\\manager\\%03u-%u`
  - `save\\promanag\\%03u-%u`
  - `%s\\main.dat`
  - `save\\actual`
- tactics files:
  - `tactics\\partido.dat`
  - `tactics\\predef.%.3u`
  - `%c:tactics\\TACTIC.*`

Why this matters:

- it confirms the main game executable directly uses the same FDI files we are editing (`JUG`, `EQ`, `ENT`)
- it gives a concrete save-file target (`main.dat`) for future diff-based dynamic-state reverse engineering (`MO`, lineup `ROL.`, likely `EN`)
- it ties lineup/tactics UI behavior to the `TACTICS/` directory for future tactics editor support

##### `DBASEPRE.EXE` confirms official DB-editor scope on the same files

`DBASEPRE.EXE` string references include:

- `dbdat\\jug98030.fdi`
- `dbdat\\eq98030.fdi`
- `dbdat\\ent98030.fdi`

This is strong support for the overall project direction (full-scope external editor) because the original tooling path also operates on these database files directly.

##### Save-file status in the provided install snapshot

The provided install currently has no standard `save/` directory populated, so there are no normal save snapshots to diff yet.

The probe found only two root-level extension-based candidates:

- `ELAD8738.R0X`
- `aviso030.030`

At least `ELAD8738.R0X` contains obvious unrelated scene/BBS text when inspected with `strings`, so it is likely not a normal PM99 save-state container.

##### Tactics directory inventory (future editor scope)

The install includes a populated `TACTICS/` directory:

- `TACTIC.000` .. `TACTIC.00A` (`11` files)
- `predef.001` .. `predef.010` (`10` files)
- `partido.dat`

This is a useful future target for tactics/lineup editing once core player/team linkage is stabilized.

#### `dd6361` skill/stat write path validated on a copy (major milestone for player skill editing)

I converted the solved `dd6361` trailer mapping into a write-capable patch probe for `JUG98030.FDI`:

- `scripts/probe_dd6361_skill_patch.py`

What it does:

- resolves a player by `dd6361` biography name
- locates the fixed-size trailer (`18` bytes) at the end of the biography continuation
- patches selected `mapped10` fields (the verified visible stat/skill block)
- rewrites only the touched FDI entry/entries with same-size `encode_entry()` output
- verifies the patched values by re-reading the output file

Validation run (copy only, local):

- patched `David Robert BECKHAM` on a copy of `JUG98030.FDI`
- requested updates:
  - `speed: 90 -> 91`
  - `passing: 90 -> 91`
- output file: `/tmp/JUG98030.beckham_patch.FDI`
- report artifact: `/tmp/pm99_dd6361_beckham_patch.json`

Verification results:

- patched copy re-parses successfully via `scripts/probe_bio_trailer_stats.py`
- `Beckham` values read back as:
  - `speed=91`
  - `passing=91`
- unrelated check (`Paul SCHOLES`) remained unchanged in the patched copy

Byte-level diff check (input vs patched copy):

- file length unchanged
- exactly `2` bytes changed
- differing offsets (on-disk file bytes):
  - `0x5cdf5`
  - `0x5cdfb`

Interpretation / milestone impact:

- we now have a validated, write-safe path (on a copy) for **player skill updates** covering the solved `dd6361` `mapped10` fields:
  - `speed`, `stamina`, `aggression`, `quality`
  - `heading`, `dribbling`, `passing`, `shooting`, `tackling`, `handling`
- this is a major step toward a full editor, even before the player-team linkage problem is solved
- remaining blockers for a polished player editor are mainly:
  - authoritative player-team linkage
  - location/derivation of `Fitness`, `Moral`, and lineup `ROL.` state
  - a user-facing integration path (CLI/GUI) with validation/backup UX

#### Important clarification: `dd6361` markers in `EQ98030.FDI` are team subrecords (not player bios)

While investigating player-team linkage, I found that the decoded `EQ98030.FDI` team containers also contain many `dd6361` markers.

Examples:

- `Stoke C` container (`0x2694d`) contains `16` `dd6361` markers
- `Manchester Utd` container (`0x6d03`) contains `30` `dd6361` markers

These are **not** player biography subrecords like the `JUG98030.FDI` `dd6361` records.

Evidence:

- marker-local ASCII text in `EQ` containers clearly decodes to team metadata records, e.g.:
  - short team name
  - stadium
  - full club name
  - chairman/president-style names
  - sponsor / kit supplier strings
- no player-name hits (`Beckham`, `Giggs`, `Keane`, etc.) appear in the `Manchester Utd` team subrecord raw data

Examples from decoded `EQ` team record chunks:

- `Stoke C`:
  - `Stoke C`
  - `Britannia Stadium`
  - `Stoke City`
  - `Sir Stanley Matthews`
  - `Asics UK`
  - `Asics`
- `Manchester Utd`:
  - `Manchester Utd`
  - `Old Trafford`
  - `Manchester United F. C.`
  - `C M Edwards`
  - `SHARP`
  - `UMBRO`

Implication:

- `dd6361` is a separator/subrecord marker family reused across files/record types
- `JUG98030.FDI dd6361` and `EQ98030.FDI dd6361` cannot be treated as the same semantic schema
- this does **not** solve player-team linkage directly, but it significantly improves what we can extract/edit on the team side

#### Team metadata extraction milestone (additive `TeamRecord` fields + CLI JSON exposure)

Using the `EQ` team-subrecord insight, I extended `TeamRecord` heuristic parsing to extract additional metadata fields from team records (additive only):

- `full_club_name`
- `chairman`
- `shirt_sponsor`
- `kit_supplier`

These fields are now exposed in `team-list --json` and `team-search --json`.

Validation examples (local CLI):

- `Stoke C`
  - `stadium = Britannia Stadium`
  - `full_club_name = Stoke City`
  - `chairman = Sir Stanley Matthews`
  - `shirt_sponsor = Asics UK`
  - `kit_supplier = Asics`
- `Manchester Utd`
  - `stadium = Old Trafford`
  - `full_club_name = Manchester United F. C`
  - `chairman = C M Edwards`
  - `shirt_sponsor = SHARP`
  - `kit_supplier = UMBRO`
- `Arsenal`
  - `stadium = Highbury`
  - `full_club_name = Arsenal Football Club`
  - `chairman = P D Hill-Wood`
  - `shirt_sponsor = JVC`
  - `kit_supplier = NIKE`
- `Liverpoolf`
  - `stadium = Anfield`
  - `full_club_name = Liverpool Football Club`
  - `chairman = D.R. Moores`
  - `shirt_sponsor = CARLSBERG`
  - `kit_supplier = REEBOK`

Coverage snapshot across current parsed teams (`532`):

- `full_club_name`: `532 / 532` (heuristic quality varies by club/locale)
- `chairman`: `99 / 532`
- `shirt_sponsor`: `43 / 532`
- `kit_supplier`: `43 / 532`

Interpretation:

- this is a meaningful step toward the full-scope editor goal on the **team / metadata** side
- coverage is intentionally conservative for chairman/sponsor/kit fields (to avoid obvious garbage)
- quality is best on many English clubs; broader international cleanup remains future work

#### Player visible-skill editing milestone (CLI productization of `dd6361` patch path)

The validated `dd6361` trailer patch workflow is now exposed through the main CLI as a copy-safe command:

- `python3 -m app.cli player-skill-patch`

Scope (intentional, current):

- patches only the verified `mapped10` visible stat block in `JUG98030.FDI` biographies (`dd6361` path):
  - `speed`, `stamina`, `aggression`, `quality`
  - `handling`, `passing`, `dribbling`, `heading`, `tackling`, `shooting`
- writes to an output copy by default (does **not** patch in-place)
- verifies requested changes by re-reading the patched output

This is the first direct player-skill editing path promoted from probe-only tooling into the maintained CLI surface.

Backend integration milestone (follow-up):

- the `dd6361` player visible-skill patch workflow is now wrapped in `app.editor_actions` as a shared backend action (CLI no longer imports `scripts/*` directly for this path)
- this makes GUI integration cleaner/safer: GUI can call the same action layer used by CLI

GUI integration milestone (follow-up):

- added a GUI Tools-menu workflow for visible stat patching:
  - `Patch Player Visible Skills (dd6361)...`
- the GUI path calls the shared `app.editor_actions` backend wrapper (same code path as CLI)
- workflow is explicit and now partially structured:
  - select `JUG*.FDI`
  - enter player name query
  - GUI inspects the player's current `dd6361` mapped10 values
  - GUI presents a dedicated modal editor with prefilled spinboxes for the verified mapped10 fields
  - only changed fields are emitted/patched (change-only patch requests)
  - choose copy-safe output (default recommended) or in-place patch with backup
- headless/test fallback still uses the text prompt path (so unit tests remain lightweight)
- this does **not** replace the legacy generic attribute editor yet; it is a separate verified-path tool for the mapped10 visible stat block
- follow-up GUI integration milestone (direct player-editor binding, partial):
  - added a `Verified Visible Skills (dd6361)` panel directly in the main player editor
  - panel auto-refreshes from live `dd6361` reads on player selection (best-effort)
  - panel exposes editable mapped10 spinboxes, a direct in-place patch action with automatic backup, and a `Stage for Save Database` path
  - panel also links to the advanced patch dialog flow
  - staged dd6361 panel changes are now included in `Save Database` (player-file backup is created and staged patches are applied via the shared backend)
  - this is a partial save-flow integration; dd6361 patches are still applied immediately during save rather than merged into the generic `FDIFile.modified_records` path

Validation (local):

- `python3 -m pytest -q -o addopts='' tests/test_cli_v1.py -k player_skill_patch`
  - pass (CLI delegates to the `dd6361` patcher with expected args/output)
- real smoke command on `DBDAT/JUG98030.FDI` (copy-safe) for `David Robert BECKHAM`
  - requested: `speed=91`, `passing=91`
  - output copy written to `/tmp/...`
  - verification succeeded (`all_requested_fields_match = true`)
- in-place smoke command on a temp copy (`/tmp/JUG98030.inplace_test.FDI`) for `David Robert BECKHAM`
  - requested: `speed=92`
  - `--in-place` created `/tmp/JUG98030.inplace_test.FDI.backup`
  - patched file and backup remained same size
  - byte diff vs backup = `1` byte changed (expected single-field patch)
  - independent `probe_bio_trailer_stats.py` re-read confirmed `speed=92`
- post-refactor copy-safe smoke via shared `editor_actions` backend path
  - requested: `speed=93`
  - output copy written to `/tmp/JUG98030.beckham_shared_action_patch.FDI`
  - same size as source; byte diff = `1` byte changed
  - CLI `--json` payload schema preserved (compatibility)
- GUI/headless validation after adding the Tools-menu visible-skill patch workflow
  - `python3 -m pytest -q -o addopts='' tests/test_gui_v1.py` → `6 passed`
  - includes copy-safe and in-place GUI dialog flow tests (backend action mocked)
  - `import app.gui` smoke still succeeds (`gui_import_ok`)
- follow-up validation after adding shared inspect action + GUI prefill
  - real backend inspect smoke via `app.editor_actions.inspect_player_visible_skills_dd6361(...)` on Beckham returns expected mapped10/role vector values
  - `python3 -m pytest -q -o addopts='' tests/test_gui_v1.py tests/test_cli_v1.py tests/test_editor_actions_unit.py` → `24 passed`
- follow-up validation after replacing the text assignment prompt with a structured modal editor (plus headless fallback)
  - `python3 -m pytest -q -o addopts='' tests/test_gui_v1.py` → `6 passed`
  - combined GUI/CLI/editor-actions regression remains `24 passed`
- follow-up validation after adding the direct player-editor `dd6361` visible-skill panel
  - `python3 -m pytest -q -o addopts='' tests/test_gui_v1.py` → `8 passed`
  - combined GUI/CLI/editor-actions regression remains green at `26 passed`
- follow-up validation after adding staged dd6361 panel changes + Save Database integration
  - `python3 -m pytest -q -o addopts='' tests/test_gui_v1.py` → `11 passed`
  - combined GUI/CLI/editor-actions regression remains green at `29 passed`
- follow-up validation after tightening staged dd6361 queue review/discard UX + regression coverage
  - staged review dialog now shows total queued patch count and marks the current player entry (`[current]`) for safer multi-player sessions
  - added headless GUI tests for:
    - current-player staged patch discard (queue removal + panel reset to baseline)
    - staged queue review summary rendering
    - visible-skill panel status text staged-count/pending wording
  - `python3 -m pytest -q -o addopts='' tests/test_gui_v1.py` → `14 passed`
  - combined GUI/CLI/editor-actions regression remains green at `32 passed`

Implication:

- we now have a practical milestone path for **player skill updates** (visible stat block) while player-team linkage and dynamic state fields remain under investigation
- backup/in-place CLI UX is now present
- shared `editor_actions` backend wrapper is now present
- GUI Tools-menu wrapper is now present for visible stat patching (prefilled from live `dd6361` mapped10 reads; structured spinbox dialog in GUI mode)
- direct player-editor `dd6361` panel is now present (auto-refresh + in-place patch)
- staged dd6361 panel patches now participate in `Save Database` (partial unified save UX milestone)
- staged dd6361 queue now has basic review/discard controls with regression coverage (including current-entry highlighting in review summary)
- next productization step is deeper unification/visibility of staged dd6361 changes beyond the current messagebox-based review/discard controls, plus continued player-team linkage work

#### Major player-team linkage breakthrough: `EQ98030.FDI` roster ID tables (via `dd6361` player IDs)

A new probe (`scripts/probe_eq_roster_playerid_linkage.py`) validated a strong linkage path between:

- `JUG98030.FDI` `dd6361` biographies (player identity + visible skills)
- lineup screenshot anchors (team membership ground truth for Stoke / Man Utd)
- `EQ98030.FDI` decoded entries

Key finding:

- the first two bytes after the `dd6361` marker (XOR with `0x61`, little-endian) act as a **stable player ID** candidate
- `EQ98030.FDI` contains **5-byte XOR-coded roster slots** of the form:
  - `[player_id_lo ^ 0x61, player_id_hi ^ 0x61, 0x61, 0x61, 0x61]`
- these roster slots occur in contiguous stride-5 tables inside decoded `EQ` entries and can be mapped back to unique `dd6361` player names

Validated (local, data-backed):

- `dd6361` player-ID candidates are unique across the extracted biography corpus in this run:
  - `2009 / 2009` unique (`duplicate_pid_count = 0`)
- `Stoke` lineup anchors (exact `dd6361` core4 matches): `13`
  - top `EQ` decoded entry hit count: `13 / 13`
  - entry: `0x2694d`
  - every hit row matches the 5-byte roster-slot shape ending in `61 61 61`
  - the parsed `Stoke C` team subrecord (`0x29802`) lives inside the same decoded `EQ` entry and its raw subrecord bytes contain all `13` anchor XOR-encoded IDs
- `Man Utd` lineup anchors (exact `dd6361` core4 matches): `18`
  - top `EQ` decoded entry hit count: `18 / 18`
  - entry: `0x15b3c`
  - every hit row matches the same 5-byte roster-slot shape ending in `61 61 61`
  - **important structural difference**: the parsed `Manchester Utd` team subrecord (`0x1580b`) is in a different decoded `EQ` entry (`0x6d03`) and its raw subrecord bytes contain `0` of the `18` anchor IDs

This means:

- player-team linkage is no longer blocked by "no signal"
- we now have a validated **player ID -> EQ roster table row** path
- the remaining hard part is now **generic team -> roster-block mapping** (especially when roster tables live in separate entries from the parsed team metadata subrecord, as with Man Utd)

Additional high-value evidence from the same probe:

- the roster-slot windows are clean stride-5 tables (`delta_positions == [5]`)
- extra non-anchor rows in the discovered windows map back to real `dd6361` players, e.g.:
  - Man Utd window includes `Philip John NEVILLE` and `Michael CLEGG` in addition to the anchor set
  - Stoke window includes duplicate `Phil BARNES` IDs and `Ray WALLACE` (one unresolved extra row still lacks a `dd6361` bio name in this run)
- global roster-run scan (`global_roster_run_entry_summary_top20`) shows many decoded `EQ` entries contain multiple stride-5 roster tables
  - the Stoke hit entry (`0x2694d`) has `16` roster runs and `16` parsed team subrecords in the same decoded entry
  - this strongly suggests an order-based or near-order-based team<->roster pairing inside at least some league blocks
  - the Man Utd hit entry (`0x15b3c`) is not one of the highest run-count entries and appears to be a split/companion roster block (its `Manchester Utd` team metadata subrecord remains in a different decoded entry)

Validation / artifacts (local):

- `python3 -m py_compile scripts/probe_eq_roster_playerid_linkage.py`
- `python3 scripts/probe_eq_roster_playerid_linkage.py --json-output /tmp/pm99_eq_roster_playerid_linkage.json`
- artifact:
  - `/tmp/pm99_eq_roster_playerid_linkage.json`

#### Follow-up milestone: same-entry team roster extraction (programmatic, broad coverage)

A second probe (`scripts/probe_eq_team_roster_overlap_extract.py`) now uses the discovered EQ roster-slot format to extract team rosters programmatically for a large subset of teams without lineup anchors.

Method (current):

- decode `EQ98030.FDI` entries and detect stride-5 roster-table runs (`.. .. 61 61 61`)
- for each parsed team subrecord, inspect only roster runs in the **same decoded EQ entry**
- score each run by how many XOR-encoded player IDs (from that run) appear in the team subrecord raw bytes
- select the best-overlap run and map player IDs back to `dd6361` names (when available)

Coverage (local, current run):

- `team_count = 532`
- same-entry overlap extraction status counts:
  - `perfect_same_entry_run_overlap: 487`
  - `moderate_same_entry_overlap: 8`
  - `weak_same_entry_overlap: 23`
  - `no_same_entry_overlap_hits: 13`
  - `entry_has_no_roster_runs: 1`
- strong-or-better coverage (currently perfect-only in this run): `487 / 532` (`~91.5%`)

Interpretation:

- we now have a **broad programmatic roster extraction path** for most teams (same-entry cases)
- the remaining hard cases are concentrated in split-entry / weak-overlap teams (e.g. `Manchester Utd`) and teams with poor/no `dd6361` name coverage for some roster IDs

Targeted validation (local):

- `Stoke C`
  - status: `perfect_same_entry_run_overlap`
  - containing entry: `0x2694d`
  - matched run: index `6`
  - overlap: `19 / 19` roster IDs (second-best overlap `1`)
  - extracted rows: `19`, with `17` mapped to `dd6361` names in this run
- `Manchester Utd`
  - status: `moderate_same_entry_overlap`
  - containing team-metadata entry: `0x6d03`
  - best same-entry run only `6 / 11` hits (second-best `5`)
  - extracted row IDs are low/unmapped and do **not** represent the lineup-anchored Man Utd roster block from `0x15b3c`
  - this cleanly confirms the split-entry issue remains the main blocker for the uncovered subset

Validation / artifacts (local):

- `python3 -m py_compile scripts/probe_eq_team_roster_overlap_extract.py`
- `python3 scripts/probe_eq_team_roster_overlap_extract.py --team "Stoke" --team "Manchester Utd" --json-output /tmp/pm99_eq_team_roster_overlap_extract.json`
- artifact:
  - `/tmp/pm99_eq_team_roster_overlap_extract.json`

#### Productized milestone follow-up: CLI `team-roster-extract` + circular-shift heuristic candidates (investigation aid)

The same-entry extractor was promoted into the shared backend + CLI as:

- `app.editor_actions.extract_team_rosters_eq_same_entry_overlap(...)`
- `python3 -m app.cli team-roster-extract ...`

This now gives a repeatable read-only roster extraction command for milestone demos and manual investigation.

Additional improvement (heuristic, not authoritative):

- `scripts/probe_eq_team_roster_overlap_extract.py` now computes a **circular-shift same-entry fallback candidate**
  for weak/no-hit teams in entries where anchor teams strongly fit a single team-index -> run-index circular shift.
- This is surfaced in the CLI as:
  - `heuristic_candidate_status=order_fallback_circular_shift_same_entry_run`
  - `candidate_run ...`
- Coverage is reported separately as a heuristic candidate metric:
  - same-entry strong/perfect coverage: `487 / 532` (`91.5%`)
  - heuristic candidate coverage (same-entry + circular-shift): `508 / 532` (`95.5%`)
  - circular-shift candidates added: `21`

New discriminator/guard (data-backed, still partial):

- circular-shift candidates are now checked against known transcribed lineup anchor PID sets (currently the seed lineup datasets, e.g. `stoke`, `manutd`)
- if a candidate strongly overlaps a known lineup anchor for a **different** team, it is flagged with:
  - `known_lineup_anchor_collision`
  - surfaced in CLI as a warning line
- a guarded heuristic coverage metric excludes these flagged candidates:
  - guarded heuristic coverage: `507 / 532` (`95.3%`)
  - flagged known-anchor collisions in this run: `1`

Anchor-assisted split-entry extraction (known lineup datasets; practical milestone step):

- requested teams that match a known transcribed lineup dataset (currently `stoke`, `manutd`) now include a
  `known_lineup_anchor_assisted_match` block in the extractor payload / CLI output
- this uses exact lineup-anchor PID hits to localize the correct EQ roster block even when the parsed team metadata
  record is in a different decoded `EQ` entry
- for `Manchester Utd` this recovers the correct split-entry roster window from `0x15B3C` directly in the CLI

Validated (`Manchester Utd`, local):

- `team-roster-extract --team "Manchester Utd"` now shows:
  - same-entry result remains `moderate_same_entry_overlap` in metadata entry `0x6D03`
  - `anchor_assisted dataset=manutd, entry=0x00015B3C, hit_count=18, exact_anchors=18`
  - stride window rows include expected players (e.g. Beckham, Schmeichel, Keane, Giggs, Stam, etc.)

This is not generic yet, but it proves a clean product path for user-supplied lineup anchors while generic split-entry mapping is still being decoded.

Pseudo-team parser-artifact breakthrough (`ELONEX` / `SANDERSON ELECTRONICS` class):

- `EQ98030.FDI` team parsing includes at least two obvious sponsor/brand pseudo-records that are not real clubs:
  - `ELONEX`
  - `SANDERSON ELECTRONICS`
- these pseudo-records can take strong same-entry roster matches, leaving the adjacent real clubs (`Wimbledon`, `Sheffield W`) as no-hit/weak cases

Validated characteristics of these pseudo-records (local):

- all-uppercase brand-like `name`
- brand-like value in the parsed `stadium` field (`LOTTO`, `PUMA`)
- `capacity = 0`
- no `chairman`, `shirt_sponsor`, or `kit_supplier`
- gibberish/non-club-like `full_club_name`

Extractor mitigation added (provisional, explicit provenance):

- `adjacent_pseudo_team_record_reassignment_candidate`
  - if a conservatively-classified pseudo-team record has a strong roster match, copy that run as a provisional candidate to the immediately preceding real club in the same entry
- `preferred_roster_match` can now use:
  - `provenance=adjacent_pseudo_team_record_reassignment` (provisional)

Unified preferred-roster selection (editor-facing extraction view):

- extractor payload now attaches `preferred_roster_match` with explicit provenance ordering:
  - `same_entry_authoritative`
  - `known_lineup_anchor_assisted`
  - `adjacent_pseudo_team_record_reassignment` (provisional)
  - `heuristic_circular_shift_candidate` (provisional; only when no warnings)
- this gives a single best-available roster view per parsed record while preserving provenance and warning data

Current preferred-roster coverage (local run):

- all parsed records: `510 / 532` (`95.9%`)
- club-like records only (excluding conservatively-classified pseudo-team records): `508 / 530` (`95.8%`)

Validated recovery (local):

- `Wimbledonl`
  - receives provisional preferred roster from adjacent pseudo-team `ELONEX` (`run=1`)
- `Sheffield W`
  - receives provisional preferred roster from adjacent pseudo-team `SANDERSON ELECTRONICS` (`run=2`)
- extractor summary fields in current run:
  - `suspected_pseudo_team_record_count = 2`
  - `adjacent_pseudo_team_reassignment_candidate_count = 2`

This does not solve generic split-entry mapping, but it removes a concrete parser-artifact blocker and improves practical roster extraction for affected real clubs.

Important caveat (validated false positive):

- The circular-shift candidate logic can recover useful hidden runs, but it is **not yet authoritative**.
- Example:
  - `Middlesbrough` (weak same-entry match in `0x15b3c`) gets a circular-shift candidate `run 0`
  - that candidate run decodes to a clear **Manchester Utd** roster (Schmeichel, Beckham, Keane, Giggs, etc.)
  - the new anchor-collision discriminator correctly flags this candidate:
    - `WARNING Candidate run overlaps known lineup anchor 'manutd' (18/18 anchor PIDs)`
  - therefore the fallback is currently best treated as an **investigation hint**, not a final mapping

Why this still matters:

- It materially reduces search space for unresolved teams.
- It exposes hidden/split-entry roster blocks quickly in the CLI.
- It gives a concrete next target: add a robust discriminator to tell "true shifted team" from "hidden foreign roster in same block".

Validation (local):

- `python3 -m py_compile scripts/probe_eq_team_roster_overlap_extract.py app/editor_actions.py app/cli.py`
- `python3 -m pytest -q -o addopts='' tests/test_cli_v1.py tests/test_editor_actions_unit.py`
  - `24 passed`
- `python3 -m app.cli team-roster-extract --team "Middlesbrough" --team "Heart of M" --team "Manchester Utd"`
  - confirms:
    - same-entry coverage summary (`487/532`)
    - heuristic candidate coverage summary (`508/532`)
    - guarded heuristic coverage summary (`507/532`) with `1` flagged anchor collision
    - `Middlesbrough` candidate run visibly resolves to Man Utd players (known false-positive class), and is now flagged
- `python3 -m app.cli team-roster-extract --team "Manchester Utd" --row-limit 15`
  - confirms `anchor_assisted dataset=manutd` and a correct split-entry roster window from `0x15B3C`
- `python3 -m app.cli team-roster-extract --team "Wimbledon" --team "Sheffield W" --row-limit 12`
  - confirms provisional `adjacent_pseudo_team_record_reassignment` preferred rosters sourced from `ELONEX` / `SANDERSON ELECTRONICS`
- `python3 -m app.cli team-roster-extract --team "Manchester Utd" --team "Wimbledon" --team "Sheffield W" --row-limit 6`
  - confirms CLI preferred-roster summary lines and mixed provenance:
    - `Manchester Utd` -> `known_lineup_anchor_assisted`
    - `Wimbledon` / `Sheffield W` -> `adjacent_pseudo_team_record_reassignment` (provisional)
    - preferred-roster coverage totals: `510/532`, club-like `508/530`

## Recommended Next Reverse-Engineering Iteration (Priority Order)

1. Generalize **team -> roster-block mapping** for the uncovered split-entry cases (highest-value blocker after same-entry productization):
   - identify how roster tables are associated with team records when they are in the same entry (Stoke-like) vs separate entries (Man Utd-like)
   - extract roster-block boundaries and ordering without lineup anchors
2. Add a discriminator/guard for circular-shift heuristic candidates:
   - extend beyond the current seed lineup anchor datasets (`stoke`, `manutd`) so the guard works across more leagues/teams
   - distinguish "true shifted same-entry team" from "hidden split-entry foreign roster block" (Middlesbrough -> Man Utd false-positive class)
   - only then consider promoting heuristic candidates into authoritative extraction output
3. Expand anchor-assisted split-entry extraction using more lineup screenshots (high-value interim path):
   - each new lineup screenshot can immediately seed a reliable split-entry roster extraction for that club
   - expose anchor-assisted matches distinctly in CLI/GUI as "user-anchored" extraction
4. Improve parser-artifact handling in team extraction (new blocker class now identified):
   - detect/tag pseudo-team sponsor records beyond the current conservative `ELONEX` / `SANDERSON ELECTRONICS` pattern
   - prevent pseudo-team records from stealing authoritative roster ownership in generic extraction flows
5. Promote `preferred_roster_match` into shared backend/editor workflows (new practical milestone path):
   - use `preferred_roster_match` (with provenance/warnings) as the default read path for team roster views
   - preserve raw same-entry / heuristic / anchor-assisted diagnostics for investigation mode
6. Productize roster extraction further into editor workflows (same-entry authoritative + heuristic candidate / pseudo-adjacent / anchor-assisted views):
   - expose roster rows as `{player_id, dd6361_name, unresolved_pid}` for CLI/GUI read workflows
   - keep same-entry vs heuristic-candidate vs anchor-assisted vs pseudo-adjacent labeling explicit in the UI
7. Productize the discovered EQ roster-slot format in a maintained probe/helper:
   - parse contiguous stride-5 roster tables
   - map XOR-coded player IDs back to `dd6361` names (unique PID path)
   - expose team roster extraction for anchor teams first
8. Decode trailer bytes `10..17` from the `dd6361` bio trailer (hidden/derived ratings or additional player-state fields).
9. Locate `Fitness` / `Moral` storage (or runtime derivation inputs), using the 8 screenshot players as anchors.
10. Improve `EQ98030.FDI` team parsing quality (team_id accuracy + noisy alias cleanup) now that broad coverage is unlocked.
11. Build a manager-list reconciliation path (manager PDF -> `ENT98030.FDI`) similar to `roster-reconcile-pdf`, then merge it with team packets.
12. Re-run club/stadium GUI manual smoke after the `TeamRecord` alias fix to confirm capacity/pitch fields now display as expected.

## Follow-up Hardening Pass: Anchor-Interval Candidate Transparency + Shared Coverage Field

Targeted hardening completed on the new `anchor_interval_monotonic_same_entry` provisional path:

- CLI now suppresses duplicate `anchor_interval_candidate` row dumps when the candidate resolves to the same run as `top_run_match`
  - this avoids noisy duplicate output in moderate-overlap cases where the provisional candidate is only adding provenance/warning context
- CLI now prints richer contested-run warnings for `anchor_interval_contested_run`, including a short preview of the conflicting team names
  - example output suffix: `[contested_with=Manchester Utd]`
- shared backend result (`TeamRosterSameEntryOverlapRunResult`) now exposes `preferred_roster_coverage` directly
  - CLI no longer needs to rely on `raw_payload` to read that summary (it still falls back for compatibility)

Why this matters:

- The provisional anchor-interval path is useful, but it needs explicit operator-facing caution.
- The contested-run warning improves reviewability for the remaining split-entry / clustered-same-entry ambiguity cases.
- The shared `preferred_roster_coverage` field is a small but useful productization step for future GUI/editor roster views.

Validated behavior (local):

- `R.C.D. Mallorca` now shows:
  - provisional anchor-interval warning
  - contested-run warning with preview (`Manchester Utd`)
  - `preferred_roster provenance=anchor_interval_monotonic_same_entry`
- duplicate anchor-interval row dumps are suppressed when the candidate run equals `top_run_match.run_index`
  - observed in clustered moderate-overlap cases (e.g. `R.C. Deportivo`-class output)

Coverage sanity after hardening (unchanged from prior anchor-interval pass):

- preferred-roster coverage (all parsed records): `516 / 532` (`97.0%`)
- preferred-roster coverage (club-like records): `514 / 530` (`97.0%`)
- guarded heuristic coverage (circular-shift candidates excluding known anchor collisions): `507 / 532` (`95.3%`)

Validation (local):

- `python3 -m py_compile app/cli.py app/editor_actions.py tests/test_cli_v1.py`
- `python3 -m pytest -q -o addopts='' tests/test_cli_v1.py tests/test_editor_actions_unit.py`
  - `25 passed`
- `python3 -m app.cli team-roster-extract --team "Manchester Utd" --row-limit 8`
  - confirms preferred split-entry path still resolves via `known_lineup_anchor_assisted`
- `python3 -m app.cli team-roster-extract --team "Middlesbrough" --team "Wimbledon" --team "Sheffield W" --row-limit 10`
  - confirms guarded heuristic warninging still works and pseudo-adjacent preferred paths remain intact
- `python3 -m app.cli team-roster-extract --team "Espanyol" --team "Mallorca" --team "Extremadura" --team "D. Ala" --team "Deportivo" --team "Zaragoza" --team "C. At. Madrid" --row-limit 6`
  - confirms anchor-interval provisional outputs, contested-run warning formatting, and unchanged preferred-coverage totals (`516/532`, club-like `514/530`)

Next targeted milestone step (still highest value):

1. Generalize split-entry `team -> roster-block` mapping beyond lineup-anchored clubs (remove dependency on `stoke` / `manutd` seed anchors).
2. Quantify the remaining uncovered club-like teams after the current `preferred_roster_match` pipeline and cluster them by EQ entry to identify the next heuristic family.

## Follow-up Refinement: Uncovered-Club Summary Instrumentation + Non-Club Utility Record Filter

Implemented additional instrumentation in the EQ roster-overlap extractor payload:

- `uncovered_club_like_summary` now includes:
  - `uncovered_count`
  - `entry_cluster_count`
  - `entry_clusters_top`
  - `teams` (full list of unresolved club-like records with status + top-run hints)
- CLI now prints a compact summary line for unresolved club-like records and a short top-entry cluster preview when running `team-roster-extract` in text mode

Also refined the non-club classifier:

- `Free players` is now treated as a non-club utility record (excluded from the club-like coverage denominator)
- this improves the milestone coverage metric to reflect actual club targets more accurately

Updated coverage after `Free players` exclusion (local):

- preferred-roster coverage (all parsed records): `516 / 532` (`97.0%`) (unchanged)
- preferred-roster coverage (club-like records): `514 / 529` (`97.2%`) (improved denominator)
- remaining uncovered club-like records: `15`

Current unresolved club-like records (local, from `uncovered_club_like_summary.teams`):

- `0x00000401` `C. At. Madrid` (`moderate_same_entry_overlap`, top run `17`, `7/12`, second `6`)
- `0x00015B3C` `Middlesbrough` (`weak_same_entry_overlap`, top run `2`, `1/27`, second `1`)
- `0x0001B04B` `Oldham Ath` (`weak_same_entry_overlap`, top run `0`, `1/27`, second `1`)
- `0x0004A7B9` `Sochauxl` (`weak_same_entry_overlap`, top run `3`, `1/20`, second `1`)
- `0x00055ABB` `Obilic` (`weak_same_entry_overlap`, top run `4`, `1/26`, second `0`)
- `0x00070CB8` `Samsunsporka19 de mayoVa` (`weak_same_entry_overlap`, top run `24`, `1/19`, second `1`)
- `0x000837AE` `St. Gallen` (`weak_same_entry_overlap`, top run `11`, `1/17`, second `0`)
- `0x000DAB3C` `Dinamo Tbilisi` (`no_same_entry_overlap_hits`)
- `0x000DB33E` `Vasco da Gama` (`weak_same_entry_overlap`, top run `5`, `1/17`, second `0`)
- `0x000E2340` `A. de Cali` (`weak_same_entry_overlap`, top run `2`, `1/16`, second `1`)
- `0x000EA742` `Northwich V` (`no_same_entry_overlap_hits`)
- `0x000FEA01` `Hurac` (`no_same_entry_overlap_hits`)
- `0x00106A03` `Gimnasia (J)i` (`no_same_entry_overlap_hits`)
- `0x00107985` `Ferro` (`no_same_entry_overlap_hits`)
- `0x00108930` `Talleres (Cba)r` (`no_same_entry_overlap_hits`)

Interpretation:

- The remaining unresolved set is now mostly **singletons**, not large same-entry clusters.
- That weakens the value of broad cluster interpolation heuristics and strengthens the case for:
  - generic split-entry mapping
  - parser-quality cleanup for noisy international club names / metadata fragments
  - additional anchor datasets for specific stubborn clubs (as an interim path)

Validation (local):

- `python3 -m py_compile scripts/probe_eq_team_roster_overlap_extract.py app/cli.py app/editor_actions.py`
- `python3 -m pytest -q -o addopts='' tests/test_cli_v1.py tests/test_editor_actions_unit.py`
  - `25 passed`
- `python3 -m app.cli team-roster-extract`
  - confirms new text summary lines:
    - `Remaining uncovered club-like records: 15`
    - `Top uncovered clusters by EQ entry: ...`

## Parser-First Pivot: Authoritative-Only Default for `team-roster-extract`

Implemented a parser-first behavior shift in the extraction path:

- `team-roster-extract` now defaults to `authoritative_only`
  - preferred roster selection only uses `same_entry_authoritative` (strong/perfect same-entry overlaps)
- fallback/investigation mappings are now explicit opt-in:
  - `--include-fallbacks`
  - this enables prior investigation classes (anchor-assisted, circular-shift, pseudo-adjacent, anchor-interval)

Implementation notes:

- backend wrapper now accepts/forwards `include_fallbacks`:
  - `app/editor_actions.extract_team_rosters_eq_same_entry_overlap(..., include_fallbacks=...)`
- CLI forwards `--include-fallbacks` and prints selection mode:
  - `Selection mode: authoritative_only` (default)
  - `Selection mode: investigation_fallbacks_enabled` (when enabled)

Validated behavior split (local):

- default mode:
  - `python3 -m app.cli team-roster-extract --team "Manchester Utd" --team "Middlesbrough" --row-limit 6`
  - output confirms:
    - `Selection mode: authoritative_only`
    - no heuristic coverage/candidate sections
    - authoritative preferred coverage:
      - all records: `487/532` (`91.5%`)
      - club-like: `485/529` (`91.7%`)
- fallback mode:
  - `python3 -m app.cli team-roster-extract --include-fallbacks --team "Manchester Utd" --team "Middlesbrough" --row-limit 6`
  - output confirms:
    - `Selection mode: investigation_fallbacks_enabled`
    - heuristic coverage and warnings visible
    - `Manchester Utd` anchor-assisted preferred mapping shown
    - `Middlesbrough` known-anchor collision warning + circular candidate shown
    - preferred coverage:
      - all records: `516/532` (`97.0%`)
      - club-like: `514/529` (`97.2%`)

Regression coverage updates:

- `tests/test_cli_v1.py`
  - added authoritative-default test to ensure fallback sections are hidden by default
  - existing fallback display tests now pass `include_fallbacks=True`
- `tests/test_editor_actions_unit.py`
  - wrapper delegation assertion now includes `include_fallbacks`
- local targeted suite:
  - `python3 -m pytest -q -o addopts='' tests/test_cli_v1.py tests/test_editor_actions_unit.py`
  - `26 passed`

## Canonical Team Query Matching (CLI + GUI)

Added a shared canonical team-query matcher (`app.editor_helpers.team_query_matches`) and moved both CLI team lookup and EQ roster extraction request filtering onto it.

What it does:

- normalizes punctuation/spacing consistently
- applies a conservative alias map for common club-name variants
- keeps matching parser-backed and narrow enough to avoid obvious false positives

Current verified aliases include:

- `AC Milan` -> `Milan`
- `Inter Milan` / `Internazionale Milan(o)` -> `Inter`
- `Barcelona` / `FC Barcelona` -> `F.C. Barcelona`
- `Real Madrid` / `Real Madrid CF` -> `Real Madrid C.F`
- `Atletico Madrid` / `Atl Madrid` -> `C. At. Madrid`
- `Manchester United` / `Man Utd` -> `Manchester Utd`
- `Manchester City` -> `Manchester C`
- `Stoke City` -> `Stoke C`

Validated locally:

- `python3 -m app.cli team-search DBDAT/EQ98030.FDI "AC Milan"`
  - resolves to `Milan`
- `python3 -m app.cli team-search DBDAT/EQ98030.FDI "Inter Milan"`
  - resolves to `Inter` (does **not** return `Inter Cardiff`)
- `python3 -m app.cli team-search DBDAT/EQ98030.FDI "Atletico Madrid"`
  - resolves to `C. At. Madrid`
- `python3 -m app.cli team-search DBDAT/EQ98030.FDI "Real Madrid"`
  - resolves to `Real Madrid C.F`
- `python3 -m app.cli team-roster-extract --team "Inter Milan" --row-limit 5`
  - authoritative extraction returns `Inter`, `provenance=same_entry_authoritative`, `rows=26`
- `python3 -m app.cli team-roster-extract --team "AC Milan" --row-limit 5`
  - authoritative extraction returns `Milan`, `provenance=same_entry_authoritative`, `rows=28`
- `python3 -m app.cli team-roster-extract --team "Atletico Madrid" --row-limit 5`
  - resolves to `C. At. Madrid`; still uncovered in authoritative mode (`moderate_same_entry_overlap`)

Follow-up:

- the GUI team search box now uses the same matcher, so editor search behavior is consistent with CLI/query tooling.

## GUI Team Overlay: Authoritative Roster Pane Now Live

The existing Team overlay already had a PM99-style squad tree (`EN/SP/ST/AG/QU/FI/MO/AV/ROL./POS`) but it was effectively inert.

It now loads parser-backed roster rows using the same authoritative extraction path as `team-roster-extract`:

- source action:
  - `app.editor_actions.extract_team_rosters_eq_same_entry_overlap(..., include_fallbacks=False)`
- selection rule:
  - only `preferred_roster_match.provenance == same_entry_authoritative`
- trigger points:
  - opening `Show squad lineup`
  - changing team selection while the roster pane is already visible

Current behavior:

- roster rows are loaded from authoritative EQ same-entry matches only
- `name` column shows:
  - resolved `dd6361` name with `[pid N]` suffix, or
  - `PID N (name unresolved)` when the current `dd6361` corpus has no extracted bio-name row for that player ID
- static visible fields (`SP`, `ST`, `AG`, `QU`) are filled from a shared single-pass `dd6361` PID->stats index
- dynamic/unresolved fields (`EN`, `FI`, `MO`, `AV`, `ROL.`, `POS`) remain blank for now in the team overlay

Validated locally:

- targeted regression:
  - `python3 -m pytest -q -o addopts='' tests/test_gui_v1.py tests/test_cli_v1.py tests/test_editor_actions_unit.py`
  - `46 passed`
- live GUI-backend smoke with a fake editor object:
  - `PM99DatabaseEditor.load_current_team_roster(...)` for `Milan`
  - result:
    - `ROWS 28`
    - `STATUS Loaded authoritative roster rows for Milan: 28`

Performance note:

- repeated per-player `dd6361` re-inspection has been removed
- the current remaining cost is the first full build of:
  - the authoritative EQ roster extraction result for the requested team
  - the one-pass `dd6361` PID->stats index for the current player file
- next optimization target:
  - cache the authoritative `team -> preferred_roster_match` extraction result inside the GUI session, not just the `dd6361` PID stats

## Update (2026-02-27): Ghidra Anchors + GUI Honesty

### Stable MANAGPRE.EXE Anchors (Persisted In Ghidra)

Confirmed again via GhidraMCP:

- `MANAGPRE.EXE` remains open
- image base remains `00400000`
- `.text` = `00401000-006E51FF`
- `.rdata` = `006E6000-0072BBFF`
- `.data` = `0072C000-007BDE67`

User-defined function names now persisted:

- `0x004B6A50` -> `load_jug98030_player_catalog`
- `0x0049BC20` -> `write_main_dat_save`
- `0x0049C070` -> `read_main_dat_save`

Bookmarks added under `Analysis / RE Anchors`:

- `0x00735240` -> `save\\actual`
- `0x0073524C` -> `eq98%03u.fdi`
- `0x00735260` -> `jug98%03u.fdi`
- `0x00734AE0` -> `main.dat`

### `load_jug98030_player_catalog` (Concrete Loader Facts)

Decompiled result now confirms:

- it builds `jug98%03u.fdi` with index `0x1E` (`JUG98030.FDI`)
- the opened file object exposes:
  - record count at `file_obj + 0x10`
  - source record table at `file_obj + 0x0C`
- the source table is iterated with an exact `0x10` byte stride
- the exported destination table is resized to `count * 8` bytes (`u32 key + pointer`)
- inclusion is gated by two explicit filters:
  - `FUN_00678120(record[2], record[3])`
  - `FUN_004afc90(...)`
- the value copied into the exported row key is `record[0]`

Important current negative finding:

- this function does **not** read an authoritative team link while populating the exported catalog row
- `record[1]` is not consumed here
- based on this function alone, there is no direct replacement yet for the current EQ-driven roster linkage

### `main.dat` Read/Write Layout (Concrete First Pass)

The save reader/writer pair is now aligned enough to state the block order concretely.

Fixed prefix:

- `u32` header/version guard = `0x1E`
- `u32` secondary version/format value = `0x0C` in the current writer
- two XOR-obfuscated length-prefixed strings via `FUN_00678350` / `FUN_00677ef0`
  - format: `u16 length`, then `length` encoded bytes
- one packed date block via `FUN_005ae790` / `FUN_005ae860`
  - serialized as `day (u8), month (u8), year (u16 LE)`
- `hour (u8)`
- `minute (u8)`
- ten flag bytes copied from object offsets `+0x2A..+0x33`
- one scalar byte copied from the low byte of object offset `+0x34`

Full-save-only blocks (`param_2 == 0` in the writer):

- two additional global bytes (`DAT_00753974`, `DAT_00753970`)
- a second packed date block (`day, month, year`)
- composite block `FUN_004B5C90`
- 13 serialized buckets from `FUN_004B53C0`
- variable-count array at `DAT_00754C98`
  - count is stored as a single byte
  - each element allocates `0x30` bytes and is serialized by `FUN_004BD910`
  - each `0x30` element contains:
    - one encoded string
    - 2 single-byte fields
    - 5 dwords
    - 1 bool byte
    - `u16` nested-count
    - nested records loaded by `FUN_004BDBE0` / saved by `FUN_004BDD70`
  - nested records allocate `0x90` bytes each
- optional block at `DAT_00754C94`
  - presence byte
  - if present, up to `0x80` entries backed by a `0x1004` allocation
  - per-entry serializer/deserializer pair: `FUN_004B9260` / `FUN_004B9310`
- optional block at `DAT_00754C90`
  - same outer shape as `DAT_00754C94`
- 14 virtual-method-backed objects in the range `DAT_00753928..DAT_0075395C`
  - saved through vtable `+0x24`
  - loaded through vtable `+0x2C`
- final trailing timestamp `DAT_00754BBC` (`u32`)

Current save-guard conclusion:

- the reader explicitly validates `header == 0x1E`
- the reader also requires the second dword to be greater than `8`
- no checksum logic is visible inside `write_main_dat_save`

### Authoritative Dynamic-State Source (Now Confirmed)

`main.dat` is now confirmed as an authoritative dynamic-state container, not just a thin header wrapper.

At minimum, these blocks are persisted there and reconstructed only on load:

- the `DAT_00754C98` variable-count `0x30` object array
- the optional `DAT_00754C94` table
- the optional `DAT_00754C90` table

That gives a concrete binary-backed target for future extraction of:

- energy / fitness / morale-like runtime values
- availability-like flags
- lineup-role-related state

Exact field semantics inside those dynamic blocks still need the next decompilation pass, but the source-of-truth file is no longer speculative.

### GUI Honesty Update

The Team overlay has been tightened to match actual parser coverage:

- `Capacity`, `Car Park`, and `Pitch quality` are now explicitly display-only in the GUI and disabled for editing
- the Team panel now states which fields are authoritative saves:
  - Team name
  - Team ID
  - Stadium
- the roster frame is now labeled as partial/authoritative instead of looking like a full lineup editor
- unresolved columns now use explicit `?` placeholders instead of blank PM99-style empty cells:
  - `EN?`
  - `FI?`
  - `MO?`
  - `AV?`
  - `ROL.?`
  - `POS?`
- the `dd6361` panel is labeled as authoritative/parser-backed

Validated locally after the GUI honesty pass:

- `python3 -m pytest -q -o addopts='' tests/test_gui_v1.py tests/test_cli_v1.py tests/test_editor_actions_unit.py`
- result: `47 passed`

### `main.dat` Parser Groundwork (2026-02-27)

A new parser-first backend module now exists:

- `app/main_dat.py`

Current scope:

- parses the confirmed `main.dat` prefix structurally:
  - header/version dword
  - format/version dword
  - two `FUN_00678350`/`FUN_00677EF0` XOR `u16` strings
  - packed date
  - hour / minute
  - 10 flag bytes
  - scalar byte
- parses the confirmed full-save prelude when present:
  - two global bytes
  - second packed date
- preserves the unresolved remainder byte-for-byte as `opaque_tail`
- supports exact roundtrip serialization so unknown blocks are not rewritten heuristically

This is intentionally partial but safe:

- it does **not** claim semantic names for unresolved tail blocks yet
- it is designed to become the editor-safe insertion point for future dynamic-state decoding

Additional codec support now implemented in that module:

- PM99 XOR `u16` string codec (`FUN_00678350` / `FUN_00677EF0`)
- PM99 XOR `u8` short-string codec (`FUN_00678270` / `FUN_00677E90`)

CLI command added:

- `python3 -m app.cli main-dat-inspect /path/to/main.dat`
- `--json` emits machine-readable structured output

Parser-backed edit command added:

- `python3 -m app.cli main-dat-edit /path/to/main.dat --primary-label "..." ...`
- edits only the confirmed prefix fields
- preserves the unresolved tail byte-for-byte
- defaults to writing a copy (`<input>.edited.dat`)
- supports `--in-place` with an automatic `.backup` unless `--no-backup` is used

Current output is honest:

- confirmed prefix fields are decoded
- `header_matches_expected` and `format_passes_guard` are reported explicitly
- unresolved payload size is reported as `opaque_tail_size`

Current edit scope is intentionally narrow:

- first confirmed XOR `u16` string
- second confirmed XOR `u16` string
- save date
- hour / minute
- 10 confirmed flag bytes
- confirmed scalar byte

This is the first real `main.dat` editor path in the repo that is parser-backed and preserves unknown blocks instead of hard-coding a blind byte patch deeper into unresolved structures.

It has now been promoted into shared backend actions as well:

- `app.editor_actions.inspect_main_dat_prefix(...)`
- `app.editor_actions.patch_main_dat_prefix(...)`

That means the CLI is no longer the source of truth for `main.dat`; it is now a consumer of the same backend action layer the GUI can use later.

Validated locally after adding the parser module:

- `python3 -m pytest -q -o addopts='' tests/test_main_dat.py tests/test_cli_v1.py tests/test_gui_v1.py tests/test_editor_actions_unit.py`
- result: `58 passed`

## 2026-02-27 - DBASEPRE.EXE Indexed FDI Container Findings

`DBASEPRE.EXE` is the strongest current static-database anchor.

Confirmed binary-backed container model:

- `FUN_0043ac50` validates `DMFIv1.0`
- it reads two dwords at `0x08` and `0x0C` as header fields, then reads the record count at `0x10`
- the inline index starts immediately at `0x14`
- `FUN_0043aab0` parses each index entry as:
  - `u32 record_id`
  - `u8 key_length`
  - `key_length` raw bytes (uppercased in-memory)
  - `u32 payload_offset`
  - `u32 payload_length`
- top-level payloads are not length-prefixed on disk
- top-level payload bytes are XOR-encoded directly, and the index carries the payload length

This means the old assumption that `EQ98030.FDI` team sections are best treated as generic length-prefixed XOR entries is not authoritative for the indexed static database path.

Parser changes made from this:

- added `app.fdi_indexed.IndexedFDIFile`
- `app.loaders.load_teams(...)` now prefers the indexed DMFI parser and falls back to the older sequential scan only if indexed parsing fails
- indexed team records now carry:
  - `container_offset`
  - `container_relative_offset`
  - `container_length`
  - `container_encoding="indexed_xor"`
- `app.editor_actions._write_modified_team_subrecords(...)` now supports same-size rewrites for indexed XOR containers as well as legacy length-prefixed containers

Practical effect:

- team parsing is now closer to the game's real static DB model
- team edits staged from indexed `EQ98030.FDI` payloads remain writable when the patched subrecord does not change the enclosing payload size

Validated locally for this milestone:

- `python3 -m pytest -q -o addopts='' tests/test_fdi_indexed.py`
- `python3 -m pytest -q -o addopts='' tests/test_editor_actions_unit.py`
- `python3 -m pytest -q -o addopts='' tests/test_cli_v1.py`

Results:

- `3 passed`
- `10 passed`
- `23 passed`

Known unchanged baseline issue:

- `tests/test_loaders.py::test_coaches_reject_garbage` still fails locally because the current coach loader returns `95` records, below the test's lower bound of `100`
- this change did not modify `load_coaches(...)`

## 2026-02-27 - ENT98030.FDI Indexed Coach Loader And Writer

`ENT98030.FDI` is also a DMFI indexed container, and the existing coach loader was still using the older sequential length-prefixed scan.

That is no longer true.

Parser-backed change:

- `app.loaders.load_coaches(...)` now prefers `IndexedFDIFile` for `ENT98030.FDI`
- each indexed payload is XOR-decoded directly and passed to `parse_coaches_from_record(...)`
- the existing conservative coach-name validation and deduplication are preserved
- sequential length-prefixed scanning remains only as a fallback path when indexed parsing fails

Write-path change:

- indexed coach records now carry:
  - `container_offset`
  - `container_length`
  - `container_encoding="indexed_xor"`
- `app.editor_actions._write_modified_entries(...)` now detects indexed XOR records and rewrites them by direct same-size payload overwrite
- variable-length indexed rewrites are still refused
- `app.editor_actions.write_coach_staged_records(...)` now provides the GUI/backend-safe save path for staged coach edits
- the GUI save flow now uses `write_coach_staged_records(...)` instead of blindly routing coach changes through the old generic length-prefixed writer

Practical effect:

- coach loading is now closer to the real `DBASEPRE.EXE` static DB path
- coach editing is safer for indexed `ENT98030.FDI` records, as long as the edited decoded payload does not change size
- this removes another major parser-vs-heuristic mismatch from the editor

## 2026-02-27 - Parser-Backed EQ -> JUG Static Roster Links

`FUN_00439f50` in `DBASEPRE.EXE` is now partially reproduced in Python for the large-record external-link path.

Confirmed parser-backed layout used now:

- team payloads are parsed from the raw indexed `EQ98030.FDI` slice, not the fully XOR-decoded blob
- at `0x26` the payload carries the game-side record-size discriminator
- at `0x29` the payload carries the mode byte
- large records (`>= 600`) with non-zero mode use the external-link path
- after the fixed scalar block, the external linked tables start at:
  - `cursor_after_fixed_fields + 0x6e7`
- that block contains:
  - `u8 ent_count`
  - `ent_count * u32` external `ENT` ids
  - `u8 player_count`
  - `player_count` rows of:
    - `u8 flag`
    - `u32 jug_record_id`

New parser module:

- `app.eq_jug_linked`
- `parse_eq_external_team_roster_payload(...)`
- `load_eq_linked_team_rosters(...)`

New shared backend wrapper:

- `app.editor_actions.extract_team_rosters_eq_jug_linked(...)`

Current product usage:

- the GUI team roster pane now prefers this parser-backed `EQ -> JUG` path first
- it falls back to the older same-entry overlap extractor only when no parser-backed linked roster is available
- the CLI now exposes the parser-backed view directly via:
  - `python3 -m app.cli team-roster-linked`

Real-data smoke check against current `DBDAT` files:

- parser-backed linked team records: `451`
- total linked player rows: `9390`
- player rows with currently resolved names: `8534`

Current remaining gap:

- `92` `EQ` entries still fall into the unresolved legacy mode-0 branch
- that branch is not yet decoded, so the parser-backed path is substantial but not yet full static roster coverage

## 2026-02-27 - Legacy Mode-0 EQ Roster Prelude Decoded

The remaining `mode_byte == 0` branch in `FUN_00439f50` is now decoded far enough to reach the same external `ENT` and `JUG` link tables.

Confirmed mode-0 cursor rules now implemented:

- after the shared fixed scalar block, mode-0 consumes:
  - optional `u16` when `record_size > 0x207`
  - one `u32`
  - one XOR `u16` string
  - two `u32`
  - two more XOR `u16` strings
  - `3` raw bytes
  - `20` bytes when `record_size >= 0x1f9` (else `10`)
  - `15` more fixed bytes
  - `46` bytes when `record_size >= 0x1f9` (else `42`)
  - then either:
    - fixed `2-byte` pairs for smaller legacy records, or
    - a sparse `count + count * 3` table for `record_size >= 700`
- the shared external link tables then begin at:
  - `cursor_after_mode0_prelude + 0x6e7`

Practical result:

- `app.eq_jug_linked.parse_eq_external_team_roster_payload(...)` now supports both:
  - non-zero external mode
  - legacy `mode_byte == 0`
- `app.eq_jug_linked.load_eq_linked_team_rosters(...)` now covers the full current `EQ98030.FDI` set

Updated real-data smoke check:

- parser-backed linked team records: `543`
- `mode_byte == 0` records: `92`
- non-zero mode records: `451`
- total linked player rows: `11520`
- player rows with currently resolved names: `10492`

This closes the main static team-to-player linkage milestone:

- the editor now has parser-backed static roster coverage across the current `EQ98030.FDI` dataset
- remaining work is now about quality and completeness of decoded player data, not whether the roster linkage exists

## 2026-02-28 - Legacy JUG Prefix Name Recovery

The `EQ -> JUG` roster linkage was already parser-backed, but `1028` linked player rows still rendered with blank names because the existing `PlayerRecord` parser did not understand every `JUG98030.FDI` payload variant.

To reduce that gap without changing roster provenance, `app.eq_jug_linked._build_jug_player_name_index(...)` now has a conservative fallback:

- it only runs when `PlayerRecord.from_bytes(...)` yields no usable name
- it scans the first decoded `JUG` payload prefix (`10`-byte header skipped, then up to `192` bytes)
- it truncates at the first `aaaa` marker when present
- it splits on the legacy `a + uppercase` separator pattern that often divides an abbreviated alias from the fuller display name
- it accepts only name-shaped suffixes that still contain a clear uppercase surname-style token

This is intentionally narrower than the old broad regex experiments:

- static roster linkage remains parser-backed and authoritative
- only the displayed player name gets a best-effort recovery path when the primary player parser fails
- malformed names are still left unresolved rather than forced into obviously bad output

Updated real-data smoke check against current `DBDAT` files:

- parser-backed linked team records: `543`
- total linked player rows: `11520`
- player rows with currently resolved names: `11209`
- remaining blank linked player names: `311`

This lifts parser-backed linked roster name coverage by `717` rows while keeping the fallback bounded to the known legacy `JUG` prefix region.
