# Superseded kit experiment cleanup — 2026-10-03

## Superseded ingress games moved to Pi, 2026-10-04

Additional user-approved cleanup is recorded in
`.local/cleanup-20261004/superseded-ingress-games`. The exact plan selects 94
old `game` children only, from `season-static-ingress-v1`,
`season-static-ingress-batch-v1` and `season-quality-ingress-v1`. Recipes,
source caches, neighbouring build receipts, current games, artwork rollback
files and required clean/recovery bases remain local. No regeneration or
database/artwork edit is performed during this cleanup.

Completed: all 94 game copies (25,850 files) are on the Pi and their local
game trees were removed. Source logical bytes: 33,623,986,623; summed source
file allocation: 33,898,323,968 (31.6 GiB). Laptop availability is approximately
49.6 GiB / 53.2 GB, up from about 19.4 GiB before the pass. File allocation
sums can differ from net filesystem reclaim due to hardlinks and concurrent
activity. A fresh post-batch check matched all 94 completed remote receipt
SHA-256s; each actual game file had already passed SHA-256 before deletion.

All 26 current seasons passed **full release validation after the batch**;
the preferred catalogue is byte-identical, and boundary/diff checks passed.
The durable report is `post-cleanup-current-release-validation.json` in the
cleanup receipt root. No databases/artwork were rebuilt or edited. Completed
receipts, plan, summary, validation and selected source/documentation snapshots
are also copied to the Pi's `receipts/superseded-ingress-games-20261004` folder.

Each retired game is copied to the mounted Pi archive under
`packages/superseded-ingress-games/20261004/<original path below .local>`.
All-file SHA-256, empty checksum-rsync and fresh local inventory checks gate
each local removal. Exact original inventories (including modes/timestamps),
verification state, actual removed allocation and remote paths are in the
individual receipts; completed totals are in `summary.json`. The neighbouring
`game.pi-archive.json` also identifies the recovery copy. Historical registry
locators are marked archived, not left looking like current playable releases.
Current `./pm99-season play YYYY-YY` launch paths remain unchanged.

Helper: `scripts/archive_superseded_ingress_games_20261004.py`. Safety suite:
`scripts/test_archive_superseded_ingress_games_20261004.py` (13 passing tests;
24 with the preceding test-install helper's regression suite).
The helper is a narrow, dated migration, not a general recursive cleaner.
Run without options to list remaining candidates; `--apply` resumes the exact
existing plan after checking the preferred catalogue has not changed. Restore
remote games to a **fresh local directory** and verify the receipt hashes;
do not edit the immutable Pi archive, where common files can share hardlinks.
Original file modes/timestamps are retained in receipts, not necessarily on
shared remote files; reapply them on restoration if metadata fidelity matters.
The [Pi ledger](PI_ARCHIVE_LEDGER_2026-09-11.md) records this archive separately
from earlier test-install and software-cache removals.

## Additional workstation cache removal, 2026-10-04

With further cleanup approval, 17 unused standalone executable distributions
were removed from `/home/joe/.codex/packages/standalone/releases`. Their exact
names and package metadata are recorded individually in
`.local/cleanup-20261004/additional-caches`. The current `0.160.0`, rollback
`0.159.3`, and live-session `0.157.1` and `0.154.0` versions were retained.
Executable paths, mapped resources and open-file paths were checked, the
installer lock was held, and protection was checked again before each removal.
All four retained executable SHA-256s matched before/after; `codex --version`
still reports `codex-cli 0.160.0`. No conversations, credentials, settings,
plugins or session databases were removed. These were software distributions,
not user data; no exact-byte backup of the obsolete executables was made.

The [official OpenAI documentation](https://learn.chatgpt.com/docs/codex/cli)
confirms the standalone installation/update route. It does not prescribe this
manual pruning policy: that policy is based on this workstation's package
metadata and live-process checks. Reusing a removed older version would require
obtaining that distribution again; no exact-version availability guarantee is
made by this cleanup.

Two expanded Gradle distributions (`4.3.1` and `4.4`) were also removed, while
both original ZIPs remain **locally** under `/home/joe/.gradle/wrapper/dists`.
Every one of their 20,955 extracted files was SHA-256 compared against its ZIP
member before removal; no extra or modified files were found. No Java/Gradle
process was running. Empty wrapper completion markers were removed so the
retained ZIPs can be extracted again. Each ZIP hash and recovery path is in the
individual receipt. No remote access or new download is needed to recover them.

Total additional file allocation reclaimed: **6,756,438,016 bytes (6.3 GiB)**,
comprising 6,169,272,320 bytes of old executables and 587,165,696 bytes of
expanded Gradle copies. Approximately 19.4 GiB / 20.8 GB remained free afterwards.
The current season catalogue remains unchanged, with SHA-256
`7eb60b810497f96339510440b9982b8142e88ca2942e1bf60eb02ad5ef4e7800`.
All PM99 game/source data, frontend dependencies, browsers and personal Trash
were retained. No further PM99 intermediate-build deletion was performed.

## Additional retired season tests, 2026-10-04

The exact allowlist in `scripts/archive_retired_season_tests_20261004.py`
covers 15 superseded 2000/01 Calle/Elkin carrier/alias test installations and
the separate 2015/16 runtime-palette V4 test. This does **not** include the
protected V4 hem-contour recovery base, the clean native base, current seasons,
recipes, source caches, photographs or screenshots.

Copies are retained at
`smb://pi-ur.local/HDD/pm99-archive/packages/retired-season-tests/20261004`.
Each local copy is removed only after the correct mounted Pi UUID is checked,
every destination file passes SHA-256 verification, checksum rsync reports no
differences, and the entire local source is rehashed immediately before removal.
Registered historical games and running/current games are rejected. Individual
receipts record original hashes, sizes, modes, timestamps and actual removal
status under `.local/cleanup-20261004/retired-season-tests` and the Pi's
`receipts/retired-season-tests-20261004` folder.

Common archive files may share hardlinks **only on the Pi**, never with a
writable local game. Rsync replaces changed files, rather than editing shared
bytes in place; every resulting game tree is verified separately. Restore to a
new local directory; do not edit the immutable archive files in place.

Read-only eligibility and archive verification:

```bash
python3 scripts/archive_retired_season_tests_20261004.py
python3 scripts/archive_retired_season_tests_20261004.py --verify-archives
```

The second command requires all 16 completed archive receipts. The exact
completed count and reclaimed file allocation are in `summary.json`; interrupted
transfers retain the local source until verification succeeds. No old data needs
to be regenerated to recover these tests.

Completed: all 16 copies were verified and removed locally, retaining 8,717
file hashes and full remote copies. Reclaimed local file allocation was
5,807,910,912 bytes (about 5.4 GiB). Both the clean native base and the V4
hem-contour reconstruction base remain local. All 26 current seasons passed
playable-file and full release checks; their preferred catalogue is unchanged.
The archive helper's safety tests passed 11 cases.

The re-downloadable npm cache at `/home/joe/.npm` was additionally cleared using
`npm cache clean --force --cache /home/joe/.npm`, reclaiming approximately
227 MiB. Installed dependencies were not removed. All installed Playwright
browser revisions were found referenced by existing projects and were retained.
Personal Trash contents were inspected but not deleted or archived.

## Approved crash-control compaction, 2026-10-04

31 unique obsolete EQ/JUG FDI copies were removed only after exact byte
reconstruction was verified. This released 104,759,296 allocated bytes
(about 100 MiB). All diagnostic JSON recipes, logs, screenshots, executables,
art archives and the successful `identity-repair` control remain retained.
No preferred season release was removed or changed by this cleanup.

The initial reconstruction blobs occupied 32,016,616 bytes locally. Following
the successful Pi remount, they were copied to
`smb://pi-ur.local/HDD/pm99-archive/evidence/crash-controls/20261004/database-deltas`,
checked with checksum rsync and independent SMB SHA-256 readback, and every
one of the 31 original files was reconstructed from the remote bytes. Only
then were the locally generated blobs removed. Local receipts and the archive
reference remain at `.local/cleanup-20261004/crash04-database-deltas`.

Read-only recovery validation (requires the Pi SMB share mounted):

```bash
python3 scripts/compact_crash04_database_copies_v1.py
```

Exact single-file restoration to a fresh disposable path:

```bash
python3 scripts/compact_crash04_database_copies_v1.py \
  --restore-file .local/crash04-diagnostics-v1/players03/DBDAT/JUG98030.FDI \
  --destination .local/recovered-crash-control/JUG98030.FDI
```

The immutable clean base `.local/season-pipeline-v2/pm99-base-clean/DBDAT`
must remain available and match the base hashes in the receipt. Do not remove
that base. The Pi archive location and current availability are recorded in
`docs/PI_ARCHIVE_LEDGER_2026-09-11.md`.

## Additional superseded visual-build compaction

### Archived Barcelona V4 selector test, 2026-10-04

With user approval, the local duplicate
`.local/season-workspace-v1/2015-16-kit-factory-template-v4-native-hem-contour-barcelona-selector-probe-game`
was removed after rechecking all 4,592 SHA-256 hashes and obtaining an empty,
successful checksum-rsync comparison with the complete Pi backup at
`HDD/pm99-archive/packages/retired-kit-probes/20261004/barcelona-v4-selector-probe`.
This released approximately 395 MiB. Current releases do not reference this
test installation; the separate V4 recovery base remains untouched.

The immutable backup inventory and subsequent removal receipt are retained
in `.local/cleanup-20261004/barcelona-probe-archive/{receipt,local-removal}.json`.
The removal receipt was also copied to the Pi's `receipts/pi-recovery-20261004`.
The full experiment can be restored from the Pi into a new local directory;
it is not necessary to regenerate it.

### Previously compacted visual releases

Three older, non-preferred game copies were compacted on 2026-10-03. Every
unique file was copied and every reconstruction hash verified before removing
the duplicate game tree. Recipes, current preferred games, source caches,
runner screenshots and the old release metadata remain retained.

| Recovery variant | Removed duplicate game | Original bytes | Unique bytes retained |
| --- | --- | ---: | ---: |
| 1 | `.local/season-visual-patches-v2/2014-15/playable/game` | 358,369,667 | 14,045,209 |
| 2 | `.local/season-visual-patches-v3/2014-15/playable/game` | 362,583,317 | 18,258,859 |
| 3 | `.local/season-visual-patches-v2/2015-16/playable/game` | 360,983,086 | 21,740,544 |

Recovery receipts, directory lists, sizes, permissions, mtimes and SHA-256s:
`.local/cleanup-20261003/superseded-visual-game-deltas/variant-{1,2,3}`.
Old locators are explicitly marked archived rather than advertised as available
full game trees. There is no Pi copy. Actual storage savings are slightly below
the roughly 980 MiB logical-byte saving because small retained files occupy
filesystem allocation blocks.

**Required recovery base: `.local/season-pipeline-v2/pm99-base-clean`. Do not
delete or modify it without independently preserving these reconstruction
inputs.** The restoration script copies only the original inventory's files,
not all files from the base, then checks their hashes:

```bash
PYTHONPATH=. python3 scripts/compact_superseded_visual_games_v1.py \
  --restore-variant 1 --destination .local/recovered-visual-variant-1
```

The destination must be new. Restore variants 2 or 3 by changing the variant
number and destination. This does not automatically change the preferred
season or resurrect an old runtime attestation.

Eight obsolete full-game trees were removed from `.local/season-workspace-v1`.
Only their three changed kit archives were unique. Those bytes were copied and
SHA-256 verified locally before deleting the duplicate game copies. No registered
release, recipe, source cache, portrait pilot, or experiment receipt was removed.

## Retained evidence and recovery

- Reconstruction base: `.local/season-workspace-v1/2015-16-kit-factory-template-v4-native-hem-contour-game`.
- Differences and complete per-file inventories:
  `.local/cleanup-20261003/kit-experiment-deltas` (about 27 MiB).
- Removed full-game names are explicitly listed in
  `scripts/compact_superseded_kit_experiments_v1.py` and its `summary.json`.
- Removed variants: V1, its two Barcelona selector probes, V2 and its probe,
  V3 and its probe, and the older shading V1 experiment.
- Every original file is recoverable from the base plus its recorded delta;
  36,736 file-hash comparisons passed after removal.
- The retained base is now a recovery dependency. Do not delete or modify it
  before independently archiving the base and these deltas.

For these eight variants the original file sets equal the retained base's file
set; only `DBDAT/MINIESC.PKF`, `DBDAT/NANOESC.PKF` and `DBDAT/RIDIESC.PKF` differ.
To recover a variant, copy the retained base to a **new disposable directory**,
overlay that variant's `files/` delta, then check every file hash against its
`receipt.json`. The inventory also records original sizes, modes and mtimes.

Read-only recoverability check:

```bash
python3 scripts/compact_superseded_kit_experiments_v1.py --verify-retained
```

Free space increased from approximately 3 GiB to 6 GiB. The old Pi archive
could not be used safely: `/srv/hdd/pm99-archive` returned I/O errors. These
local deltas are **not** Pi backups. Transfer and checksum verification remain
pending until the remote disk is healthy. No filesystem repair was attempted.

## Foreign portrait accuracy check

`scripts/verify_foreign_portrait_sources_v1.py` reuses the complete 26-season
roster/photo audit and checks each installed 2015/16 foreign portrait against
the original conversion materialisation, cached source bytes, ID-derived image
URL, dated FIFA16 CSV identity and birth date, and single-face framing.

Reports live under
`.local/visual-qa-20261003/foreign-source-verification/`. This verifies source
and installed-image consistency; it does **not** certify every face independently
or treat a source database as infallible. Aliases, missing original references
and conflicting birth dates are review queues, not automatic replacement rules.

All 3,350 installed 2015/16 foreign portraits were checked: 2,908 passed these
source/framing checks, while 442 need further review. The issue counts overlap:
181 recipe/CSV birth-date disagreements or omissions, 124 identities absent
from the dated CSV, 103 name/alias checks, and 35 missing original conversion
joins. None of the available matched source images failed the source hash or
single-face detection checks. Passing these checks is not visual certification.

At the time of this initial audit, the other 25 registered seasons had no newly sourced world portraits:
9,352 no-photo entries plus two inherited portraits per season. The report
records the original native identities for all 50 inherited occurrences.
For example, 2014/15 Federico Barba retains the native Kanu portrait. The audit's
`foreign-club` group means mode-1/non-managed carriers and includes some English
non-league clubs; it should not be read as a nationality classification.

An independently corroborated wrong assignment is Deportivo's `Lucas`
(carrier 186, recipe birth date 1988-09-10): the installed portrait is bound to
FIFA ID 200949, identified by the dated CSV as Lucas Rodrigues Moura da Silva
(1992-08-13). Arsenal's contemporary
[Lucas Pérez interview](https://www.arsenal.com/feature/lucas-perez-a3RjP9K96fRa)
identifies the Deportivo striker and his September birthday; the
[Premier League profile](https://www.premierleague.com/players/5762/player/overview)
records Lucas Moura's different identity and birth date.

Conversely, Jonathan dos Santos demonstrates why CSV conflicts cannot be
auto-applied: the recipe's 1990-04-26 is supported by his
[LA Galaxy profile](https://www.lagalaxy.com/players/jonathan-dos-santos/), while
the FIFA CSV says 1990-04-04. A failed comparison does not alone establish
which side is incorrect.

No playable portrait or kit was changed by that initial accuracy check.
Subsequent changes are recorded below and in the historical-photo pilot document.

## Bayern runner proof and verification

A fresh 2022/23 runner route explicitly selected Germany and then Bayern
Munich. The selected-club caption reads `Bayern Munich` alongside the
yellow/black kit. Evidence:
`.local/runlogs/pm99_runner/visual_qa_2022_23_bayern_20261003_r3/screens/19_select_bayern.png`.
All ten runtime visual-input hashes (DAT palette, four database/photo inputs,
and five kit archives) match the registered release. The source bitmap in
slot 401 remains byte-identical to the original Borussia Dortmund artwork.
This is an actual opponent-selection screenshot, not an archive preview or
evidence of managing Bayern. The dashboard's Community Shield opponent is
not Bayern and must not be used as Bayern match evidence.

The expected home shirt is red/white, independently supported by the
[official FC Bayern 22/23 shirt listing](https://www.fcbayern.com/store/en-zz/p/home-shirt-22-23-2744).
The earlier R1 capture selected Denmark; R2 selected Bayer Leverkusen. They
are diagnostic attempts, not Bayern proof. R3 resolves the country and tile
coordinates from the visible captions. No other kit is certified accurate
merely because its bitmap parses or matches its generation receipt.

Verification: 37 targeted tests passed; the research repository boundary check
and Markdown diff check passed. The stricter `--check-local` lane also reports
the pre-existing undeclared `upstream/.local` directory; it was not removed as
part of this narrowly scoped cleanup.

## Local-only implementation and storage checkpoint

No additional deletion or Pi transfer took place during the follow-up
implementation. Source caches, recipes, old releases and recovery deltas remain
local. Approximately 2.1 GiB is free at the final checkpoint after four reviewed releases were published;
further full-game batch copies have stopped.

New full game copies use reflinks where supported, otherwise independent copies
(never writable hardlinks). The copier checks the complete source/destination
inventory and reserves at least 1 GiB after estimated copy cost. Art publication
permits only declared portrait/compact-kit changes and separately preserves a
pre-existing user `manager.ini` setting change. Database/executable bytes remain
unchanged. No successful historical source capture was repeated.

Cleanup candidates at the implementation checkpoint (the two dependency folders
were subsequently deleted with user approval; see the receipt below):

| Exact path | Approximate size | Condition |
| --- | ---: | --- |
| `tools/season-preset-viewer/node_modules.incomplete-20260831` | 481 MiB | Abandoned dependency install; active `node_modules` is separate. |
| `tools/season-preset-viewer/node_modules.incomplete-20260831b` | 362 MiB | Same; rebuildable from the dependency lockfile. |
| `.local/season-visual-patches-v1/2015-16/playable/game` | 395 MiB | Superseded release; first preserve/verify exact reconstruction and adjust its recovery references. |
| `.local/season-visual-patches-v2/2014-15/playable/game` | 345 MiB | Same; current release is V3. |

The two dependency folders together offer about 843 MiB with no game/source
loss. Do not remove historical releases merely because they are superseded:
their registered inventories and recovery references must remain meaningful.
The retained V4 kit reconstruction base and `.local/cleanup-20261003` deltas
remain protected recovery dependencies.

Two small diagnostic failures were retained rather than overwritten:
`.local/season-visual-patches-v2/2015-16/failed-release-metadata` (a duplicate-ID
publication attempt, before the atomic/unique-stage fix) and
`.local/season-visual-patches-v4/failed-2022-23-extend` (a combined-patch receipt
copy failure). Neither is a preferred release or lost source data.

## Proven Bayern kit correction, not an all-kit closeout

The shared Wikipedia renderer now composites transparency onto sourced fabric,
removes edge-connected diagram background/outline, unwraps garment bounds and
projects the pattern onto an original PM99 factory silhouette with its shading,
seams, highlights and native DAT palette. This prevents tiny Commons diagrams
from leaving large flat/white fabric regions. The first asymmetric-white probe
was rejected after inspection; the revised probe was checked in the runner.

Only Bayern's 2022/23 carrier 401 was changed in the three compact kit archives.
The current release is `visual-kit-bayern-20261003-r4`; the genuine opponent
selection proof is
`.local/runlogs/pm99_runner/visual_factory_bayern_2022_23_20261003_r2/screens/19_select_bayern.png`.
It shows Bayern selected with red/white rather than inherited Dortmund yellow/black.
Those three archive hashes exactly match the published release; its fresh
registered Stoke launch proof is
`.local/runlogs/pm99_runner/visual_kit_bayern_2022_23_20261003_r4/screens/022_line_up_inspect.png`.
This is not proof that Bayern is a playable managed team or that other kits
are correct. Broader sourced-kit rollout and visual checking remain open.

The original kit receipt is unchanged. QA accepts the correction only when the
old archive hash matches the patch's recorded input, the application receipt is
bound to the registered manifest/build stage, and the current archive matches
the stage's output. The initial QA failure against the original receipt is
retained; the corrected QA report has zero blockers and five declared warnings.

## Follow-up quality pass storage

The Bayern correction is applied once per published release. Its retained
compact patch is replay/recovery evidence, not residual game data or a patch
reapplied on every launch. The larger minimal runner input is a separate test
fixture. Old full playable copies, unlike the patch itself, are the significant
storage cost and must not be multiplied for an unattended 26-season batch.

The follow-up created exactly two full local game copies: 2014/15 kit corrections
under `.local/season-visual-patches-v5/2014-15/playable/game` and 2015/16 English
portrait quarantine under `.local/season-visual-patches-v6/2015-16/playable/game`.
All rejected kit renders are small BMP candidates/three-archive patches under
`.local/visual-quality-v1`, not full installations. Prior releases, source caches,
the V4 reconstruction base and recovery deltas were retained. No additional
deletion or Pi transfer was performed. Approximately **1.7 GiB** remains free;
the next iteration should prepare compact art patches before allocating another
full game copy.

Source recovery exposed a duplicate-URL cache write race. Per-URL process/thread
locks now prevent duplicate immutable receipt writes. A missing payload is
restored only if its downloaded hash matches the retained receipt. Conflicting
or corrupt cached bytes are not silently replaced. This is unrelated to kit
patch residuals or a lost game database.

The remote runner also reported its retained-run budget was exceeded (24 roots,
about 30 GiB, against a configured 20-root/24-GiB cap). This is on the independent
runner, not the unavailable Pi or a new laptop game-copy batch. No leases were
broken and no remote maintenance/deletion was attempted.

Final full `./pm99-season validate all` passed for all 26 current preferred
releases, including their existing/fresh inventory-bound runtime attestations.
The four changed releases have fresh passing QA (four or five declared editorial
warnings each). This is technical/source-consistency evidence, not a claim that
every historical face or kit across 26 seasons has been visually certified.
Boundary and `git diff --check` passed; the pre-existing dirty worktree and
submodule pointer differences were preserved. Regression tests cover unbound
kit receipts, unrecorded kit-byte changes, resurrected stock portraits,
successive narrow publications and replacing a formerly blank portrait.
The final targeted pipeline/visual regression run passed all 78 tests.

## Approved dependency cleanup

The user approved deletion of the two abandoned dependency installations. Exact
paths were resolved and confirmed as ordinary directories inside the viewer;
the separate active `node_modules` was not removed.

- Deleted `tools/season-preset-viewer/node_modules.incomplete-20260831`: 491,716 KiB.
- Deleted `tools/season-preset-viewer/node_modules.incomplete-20260831b`: 370,548 KiB.
- Total allocated space removed: 862,264 KiB (about 842 MiB).
- Free space increased from approximately 1.9 GiB to 2.7 GiB.
- Both paths are absent. Source code, current game releases, recipes, caches,
  recovery bases/deltas and the active dependency install were left untouched.

Before/after SHA-256 checks were identical for:

| Retained file | SHA-256 |
| --- | --- |
| `tools/season-preset-viewer/package.json` | `81dc856b66a0e15e3c73639c3079cb0838148c0c1cba614a6c8ca6cd090826cc` |
| `tools/season-preset-viewer/package-lock.json` | `5bd1c98c89378d76ebdb4afd99ed13da7f9b881f8eb77223461802576ac4c07d` |
| `tools/season-preset-viewer/node_modules/.package-lock.json` | `8fd3644b2d2acfe190c7d7dd9861039028a839e7366db202682ff1737a03b0d9` |

These were incomplete dependency installs, not unique project data. A usable
dependency installation can be recreated from the retained manifests with
`npm ci` in the viewer directory, given compatible Node/npm and registry/cache
availability. There is no reason to recreate the abandoned incomplete states.
Do not run `npm ci` merely to verify this cleanup: it replaces the active install.

The earlier eight deleted kit-experiment game trees were also rechecked without
recreating full copies: `--verify-retained` passed 36,736 file-hash comparisons.
Their exact file bytes remain reconstructable from the retained V4 base and
saved deltas. This depends on keeping those local recovery inputs safe; it is
not a claim that unavailable Pi backups or deletions by other workers have been
independently verified.
