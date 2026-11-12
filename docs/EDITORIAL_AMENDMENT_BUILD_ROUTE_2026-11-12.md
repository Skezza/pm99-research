# Workbook edit -> playable candidate (generic amendment route)

Implemented on 2026-11-12 by an actual non-interactive Claude Sonnet 5.5 worker, then independently reviewed and corrected by the lead on joe-Vostro-3350. The spreadsheet now builds an edited playable game. Demonstration candidates remain separate from the 26 preferred releases; no historical correction or RC closure is claimed by these test edits.

Lead verification and remaining limits: `docs/EDITORIAL_AMENDMENT_LEAD_QA_2026-11-12.md`.

## The loop

1. `python3 tools/season_preset_browser.py` → pick a year → edit cells (existing workbook). Edits stage into
   `seasons/<season>/editorial-amendments/working.json`, hash-bound to the release recipe.
2. **Check edits** (dry run, builds nothing) then **Build playable candidate** in the page, or
   `./pm99-season apply-amendments YYYY-YY [--parent ID] [--dry-run] [--verify-reconstruction]`.
3. The result panel/CLI prints the candidate id, exactly which cells/bytes changed, validation, evidence path and
   `./pm99-season play YYYY-YY --release-id <candidate>`.
4. The candidate is registered but **never preferred**. Pick it in the page's *Edit base* list to stack the next edit on it
   (or pass `--parent`). Rebuilding the same staged edits returns the same candidate (`already-built`).

`./pm99-season report [--json]` writes `.local/season-status-report-v1/status.{md,json}` (see below).

## How it works (one generic plan type, no per-season/per-person code)

- `scripts/season_editorial_amendment_delta_v1.py` is a plan type `pm99-editorial-field-amendment-delta-v1` registered once in
  the existing publisher/SOURCE dispatch (`publish_historical_role_delta_v1.py`, `season_profile_assignment_pruning_layer_v1.py`,
  compiler `reject_factory_recipe`). The plan is pure data derived from (exact parent release, staged edits), so `verify`
  re-derives it and SOURCE reconstruction (`reconstruction()`) is exact and deterministic.
- It patches the parent's JUG/ENT bytes through the existing guarded writers (`quality.record_patch`,
  `rewrite_indexed_native_roles/birth_dates/shirt_numbers/profile_fields`, `replace_indexed_ent_manager_names`) and hardlinks everything else.
  Every changed byte is listed in the plan (`native_bytes`) and the whole-file diff is audited against it.
- Stale pointer/value, recipe/native disagreement, wrong hash, unsupported field, bad range, duplicate target, goalkeeper
  conversion, preserved foreign records and shirt clashes are refused with a reason. No guard was removed or weakened;
  `reject_factory_recipe` additionally refuses these recipes so they can never be factory-compiled from a clean base.
- Human edits are labelled `human-editorial-amendment` (recipe source `editorial-amendment-<tx>`, proof grade
  `reviewed-editorial`); source evidence and hash pins are never rewritten.

## Supported cells (everything else is read-only in the page and refused by the CLI with an actionable reason)

| Cell | Native effect |
|---|---|
| player ratings (10 incl. handling), 1-99 | ten skill bytes (both native families) |
| broad position D/M/F (dd6361 only) | position byte **and** explicit dependent fine roles: compatible existing roles kept, else fixed default D `[4,5]`, M `[9]`, F `[12]`; recorded in plan/recipe |
| nationality | country byte (must be representable) |
| DOB | four date bytes; year ≤1999 unless the release already carries the modern-birth-year guard |
| shirt number (dd6361 only) | header byte; refused if another player at the club wears it |
| height / weight | one byte each at the compiler's documented offsets |
| manager name (written managers only) | ENT short/display names via the existing grammar-checked writer; short name = surname with particles, ASCII-folded, shown in the plan |

**Gating is per edited field and record, not per person.** An unknown/preserved fact (e.g. Sparrow's weight, Casemiro's shirt)
blocks only edits of that fact; the same person's ratings and other facts remain editable and the preserved facts are carried
unchanged. A cell is read-only in the page (with the reason) when *that record* cannot take it: goalkeeper position changes,
preserved/foreign managers, compact dd6360 position/shirt, preserved fine roles, whole-record-preserved players. The server
refuses the same edits if posted directly. The native agreement check still runs at build time.

**Not supported (clear message):** player names (no proven generic native name-capacity writer), club name/full name/division/
ground, manager-to-club links, rosters, lineups, membership, fine-role edits as a cell (only as the explicit consequence of a
position edit), goalkeeper conversions, compact dd6360 position/shirt, preserved foreign (mode-1) players and managers.


## Outcomes are honest

- Playable validation failing, or a *requested* SOURCE-reconstruction verification failing, returns a non-success status
  (`validation-failed` / `verification-failed`, CLI exit 2, HTTP 409 with the full report). That operation does not add the candidate to the menu or return a play command; its evidence is kept.
- Each build writes `build-report.json`; an earlier different report is archived under `history/` by content hash, and every
  verification result is stored immutably under `verifications/`. A repeat without `--verify-reconstruction` carries the earlier
  exact proof and labels it `verified_in_this_run: false, carried_forward_from: ...`.
- Reports state `dry_run` and `built_this_run`; the page says "nothing was built" for checks and "already built — reused" for repeats.
- The in-memory plan cache is limited to 2 entries and is re-fingerprinted (recipe, JUG/EQ/ENT/TEXTOS hashes, birth-year guard) on every hit.
- Disk reserve: `--minimum-free-bytes N` on both `apply-amendments` and `tools/season_preset_browser.py` (or `$PM99_MINIMUM_FREE_BYTES` for the CLI);
  default 8 GiB; values under 6 GiB are refused by the shared `validate_reserve`.

## Evidence (all under ignored `.local/`)

`.local/amendment-demo-20261112/evidence-index.json` (written by `collect_evidence.py`): independent read-back for the three
built candidates, preferred catalogue hash unchanged, all 26 preferred bindings equal checklist v298, original 2015 backup
validates. `all-seasons-planning-scan.json`: the same code *planned* (not built) a position+rating+manager edit on 25/26 seasons.

| Season | Candidate (unpreferred) | Edits | Native bytes changed |
|---|---|---|---|
| 2022-23 (parent r701a) | `edited-2022-23-5be1905c4161` | Joe Ackroyd M→F (fine role 9→12), passing 58→77; Graham Potter→Graham Hudson | JUG 3 bytes, ENT 6 bytes, EQ 0 |
| 2005-06 | `edited-2005-06-2e46bb1850df` | Michael Symes F→M (fine role 12→9), passing; Colin Todd→Colin Ddot | JUG 3, ENT 8, EQ 0 |
| 2018-19 | `edited-2018-19-86192b20a18f` | Tyler Garrett D→M (4→9), passing; Neal Ardley→Neal Demoey | JUG 3, ENT 8, EQ 0 |

Each: SOURCE reconstruction (`-src` sibling) equals the candidate (complete game inventory + recipe), playable-level
validation passes, parent inventory intact. Stale-edit/hash/unsupported refusal, determinism, idempotent apply and
parent→child planning are covered by `scripts/test_editorial_amendment_delta_v1.py`.

## A second edit preserves the first

Lead Playwright QA built `edited-2022-23-3ab29fd9b8de` through the real browser, using `edited-2022-23-5be1905c4161` as its base. It changed Ackroyd's shooting from 31 to 41. Independent readback proves exactly one game byte changed; passing 77, forward position, roles, manager name, rosters, tactics and every other game file remain intact. A fresh SOURCE reconstruction matches the complete recipe and game inventory.

These are deliberately artificial QA edits, not historical corrections. None is preferred. The earlier worker's second-generation attempt was correctly blocked by its 6.5 GiB reserve; that attempt remains recorded. The lead used the supported explicit 6.25 GiB reserve after checking capacity. The shared 6 GiB hard minimum and 8 GiB default are unchanged.

To configure the workbook's reserve explicitly, use `python3 tools/season_preset_browser.py --minimum-free-bytes 6710886400`. A normal launch retains the 8 GiB default. The tool refuses values below 6 GiB.

## Status report

`./pm99-season report` discovers the preferred catalogue and the newest `release-delivery-checklist-v*.json` (no per-season files).
Each row separates **declared** (cached locator/checklist values), **actual** (playable validation and attestation structure checked now),
**known issues** (confirmed findings not closed, accepted exceptions, runtime-review candidates) and **unreviewed candidates**
(automatic scan groups, not bugs), plus how much of the recipe the workbook route can edit. No percentages.

## Known limits

- Candidates have not been registered as runtime-attested or preferred. The 2022/23 pilot has genuine player-profile and Stoke lineup captures; the two other eras have Native readback and exact SOURCE reconstruction. These are different levels of evidence.
- Playing a candidate launches Wine inside its release directory (same behaviour as preferred releases).
- English sidecar (`english-season-package.json`) is a historical projection that already differs from main; it is carried, not edited.
- 2015/16: a dry plan of a rating edit on the preferred r438a Varane (dd6360) agrees with native and changes one byte (`.local/amendment-demo-20261112/probes-round2.json`; nothing built, the original 2015 backup untouched).
- Pre-existing at HEAD (unrelated): 14 failures in `test_build_registered_{italian,manager}_reconstruction_v1.py` (dispatch-isolation).

A candidate is checked against its entire game inventory and registered recipe hash before being offered as usable, including on repeat requests. Launch-level validation alone is not substituted for this integrity check.

The four artificial QA candidates were archived out of the daily candidate menu after testing. Their registered games, recipes, exact play commands and evidence remain available; `demo-menu-retirement.json` records the reversible menu-only change. No real user candidate was removed.

The 2015/16 legacy main recipe does not contain its English squad. Its English sidecar is not yet editable through this bridge; see the lead QA report.
