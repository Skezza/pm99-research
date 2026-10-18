# Football-photo corrections — 4 October 2026

## Delivered artwork

Forty portrait updates in 16 preferred seasons: six replacements using the
user-approved Ronaldo/Yamal sources, followed by 34 additional reviewed
football-photo updates. They are artwork-only compact transactions, not new
database builds. Every transaction proves that unrelated game files are
unchanged and retains only the overwritten artwork for recovery.

- Ronaldo: Ray Booysen's Manchester United v Chelsea photograph, 29 April
  2006, CC BY 2.0. The Commons `cropped-3-4` derivative is used for 2005/06,
  2006/07, 2007/08 and 2008/09.
- Yamal: Biso/Biser Todorov's Spain photograph, 4 September 2025, CC BY 4.0.
  The user-approved `cropped2` derivative is used for 2024/25 and 2025/26.

Source pages:
[Ronaldo](https://commons.wikimedia.org/wiki/File:Ronaldo_-_Manchester_United_vs_Chelsea_(cropped-3-4).jpg),
[Yamal](https://commons.wikimedia.org/wiki/File:Lamine_Yamal_in_2025_(cropped2).jpg).
Every additional source's photographer, licence URL, date basis and source
page are retained in `.local/football-photo-closeout-20261004/photo-credits.csv`.
The permitted photograph window remains opening year minus two through plus
one; this is era matching, not a claim that every picture was taken in August.

## Real runner proof

Both profile checks passed the expected-name test and visibly render the new
portraits in the running game:

- Ronaldo: `.local/runlogs/pm99_runner/football_photo_ronaldo_2005_06_20261004_r12_row2/screens/48_profile_only_cristiano_ronaldo_2005_06_done.png`.
- Yamal: `.local/runlogs/pm99_runner/football_photo_yamal_2025_26_20261004_r12/screens/44_profile_only_lamine_yamal_2025_26_done.png`.

The first Ronaldo attempt opened Cristiano Doni. Its name check correctly
failed, so it is retained as a failed navigation attempt, not release proof.
The successful retry selected row two of the actual search results. These
profile captures prove the named portraits, not all player facts or an entire
later artwork revision. Fresh inventory-bound Stoke proofs qualify each
updated final release separately.

## Selection safeguards

`season_foreign_photo_selection_v1.py` now uses `football-face-v4`:

- Source-associated name plus a unique recipe name/date-of-birth binding.
- Dated, licensed raster photographs; never substitute an upload timestamp.
- Reject formalwear descriptions, ambiguous multi-player titles, a known
  Roberto Carlos Sosa homonym, and contradictory title/metadata dates.
- One prominent detected face of at least 40 pixels. Tiny spectators do not
  invalidate a single-player portrait; two prominent faces still do.
- Landmark framing checks reject strong profiles. These are framing checks,
  **not biometric identity recognition**.
- Complete tight crops without invented pixels; native PM99 BMP validation.
- Use the actual displayed `DAT.PKF` palette rather than the first readable
  RIFF palette. They differ at index 111; the profile pixel checks confirm
  the same active resource previously established by the kit research.
- A source/BMP-hash-bound assistant review must confirm football or training
  clothing. Detection and captions alone cannot establish this reliably.

The expansion trial produced 123 candidates across all 26 seasons. The full
source photographs and crop/native-preview sheets were inspected: 60 approved,
63 rejected. Of the approved candidates, 26 were already installed unchanged;
only the remaining 34 were patched. The six separately approved corrections
were preserved, including Yamal's specifically approved derivative.

The new default rules do not retroactively certify all older inherited photos
or every prior selection. In particular, a successfully decoded bitmap is not
proof of the pictured person's identity, club association or historical kit.

## Re-running without changing unrelated data

Use the season virtual environment for OpenCV-dependent scripts:

```sh
.local/venvs/season-pipeline/bin/python scripts/season_foreign_photo_selection_v1.py \
  --output-root .local/football-photo-next-selection \
  --cache-root .local/foreign-photo-expansion-v1 \
  --source-overrides data/season-portrait-overrides-v1/football-photo-sources-v2.json \
  --only-overrides --maximum-per-season 20
```

Selection caches bind policy, recipe and override/selection parameters. Reuse
the same root only with identical inputs; otherwise use a fresh root while
sharing the existing source cache. Omitting `--only-overrides` permits general
searches outside the pinned photos' era windows. No database build is involved.

After reviewing source/crop sheets and generating source/BMP-bound decisions:

```sh
.local/venvs/season-pipeline/bin/python scripts/install_reviewed_foreign_photo_selection_v1.py \
  --selection-root SELECTION_ROOT --review REVIEW_JSON \
  --output-root PATCH_ROOT --release-id FRESH_LOWERCASE_REVISION
```

Already-installed revisions and byte-identical portraits are skipped. A
complete prepared patch can resume only if every input/output binding still
matches. Historical receipts are not overwritten. Interrupted transactions
must be recovered through the existing transaction journal before proceeding.

## Coverage and honest gaps

The final read-only verification is
`.local/football-photo-closeout-20261004/verification.json`: all 26 seasons,
2,553 added portrait carriers checked against recipe identity, raw source
bytes, installed BMP hashes and conflicting active archive entries; zero
failures. This includes 103 real-photo and 2,450 FIFA-source player-season
entries overall. It does **not** certify all inherited assets.

Foreign-club coverage is explicitly restricted to the 451 declared foreign
membership carriers, not all fixed-capacity clubs. English clubs also preserve
fixed capacities, so that policy alone is not a country filter. A regression
test covers this distinction. The final CSVs under the closeout's `coverage/`
directory record 89 verified real-photo entries, 2,450 verified FIFA entries,
5,604 inherited/unverified entries and 234,884 missing player-season entries.
Repeated people across seasons count separately. These figures include
declared fallback roster rows; they are not a count of distinct people or
newly researched historically correct squads.

The preliminary expansion-root verification used the over-broad capacity
filter. Its source/BMP checks passed, but its foreign coverage counts are
superseded by the final closeout report. Do not use it as the coverage ledger.

The 12-player sheet is
`.local/football-photo-closeout-20261004/installed-photo-samples.png`.
Its right-hand images are decoded from the actual installed native BMP and
runtime palette; they are checked against the materialised previews.

The corrected runtime-palette sample is under the closeout's
`runtime-palette-samples/installed-photo-samples.png`; use that sheet. The first
sample used the conversion palette and is superseded. Existing portrait
conversions can use index 111 for a dark shadow that the active game renders
blue. The new selector prevents that palette choice in future conversions,
but this milestone does not silently recolour all earlier portrait files.
That small, measured legacy conversion issue remains a targeted artwork task.
Ronaldo's actual 1,024 screenshot pixels match the active-palette/RGB565 native
decode exactly; Yamal's maximum channel difference is four, at three pixels.
This proves the installed pictures are the ones displayed, not that the
legacy conversion palette was the best quantisation choice.

## Visible player-data defects remain separate

The Ronaldo screenshot still shows England rather than Portugal. Yamal's
screen shows age 25 and a SWEEPER secondary-role label. Earlier research already
recorded age/role inconsistencies and questionable foreign club associations.
The new sample also labels Arnautovic's 2012/13 recipe carrier as Hannover 96,
which requires a dated club-association check. None of these facts changed in
this photo-only milestone. The photo checks must not be presented as historical
accuracy approval of the recipes.

The next factual work item is a recipe-to-native profile audit of nationality,
age, position and club ownership, beginning with these named examples. It
should produce targeted corrections and repeatable assertions, not another
unrelated rebuild or a blanket claim that every season is historically correct.

## Validation and storage

Native transactions: `.local/season-art-transactions-v1/visual-football-photos-20261004-r{12,13}/`.
Final changed-season runner logs: `.local/football-photo-runtime-20261004-r13/`;
the 2005/06 and 2006/07 captures have their dedicated proof tags.
Final QA target: `.local/season-qa-v2/football-photos-20261004-r13-final/`.
Runtime and QA results must be inspected before declaring release closeout.

Final results: all 16 changed seasons passed fresh exact-release Stoke captures
and QA, with zero blockers and 77 retained editorial warnings. The other ten
preferred seasons were unchanged. Full release validation passed for all 26;
the catalogue still has 122 editorial warnings in total. This is technical
release/asset verification, not historical certification of the fallback data.
The final report is `.local/football-photo-closeout-20261004/release-validation.json`.
All 154 native-database/executable/kit file comparisons against the 22 compact
transaction baselines are unchanged. Focused regression tests: 34 passed.

`verify_foreign_photo_profile_v1.py` makes the native-to-runner pixel check
repeatable. It binds the named runner probe, unchanged target BMP and unique
recipe name/DOB, then compares the actual screenshot header to the active
palette/RGB565 decode. Reports: `ronaldo-runtime-pixels.json` and
`yamal-runtime-pixels.json` under the closeout. The initial first-palette pixel
report is diagnostic only; it exposed the slot-111 difference and is not the
final display comparison.

The V4 selector was exercised with both cached approved photographs under
`.local/football-photo-palette-v4-pilot/`: both source/framing/native-format
checks passed using the correct active palette. Those regenerated pilot BMPs
were **not installed**; current releases retain the 40 reviewed patch files
whose exact hashes and screenshots were verified above.

New patch/selection/coverage/recovery artifacts occupy tens of MiB, not full
game copies. The shared downloaded sources are reused. Approximately 49 GiB
of local disk remains free during this work. Existing approved kit hashes and
all three native databases are unchanged by both portrait revisions.
