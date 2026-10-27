# RC delivery checkpoint — 27 October 2026

Machine: joe-Vostro-3350. Source session: 01a0592d-fcd5-7262-a637-743a8253d9b4.
Checkpoint recorded at 18:07 UTC; this is a historical checkpoint, not the live task list. Read CURRENT_WORK.md first.

## Delivered since v191

| Season | Installed release suffix | Checkpoint | Kit remaps |
| --- | --- | --- | ---: |
| 2003/04 | r411a | v192 | 23 |
| 2004/05 | r412a | v193 | 14 |
| 2005/06 | r413a | v194 | 18 |
| 2006/07 | r414a | v195 | 8 |
| 2007/08 | r415a | v196 | 6 |

Release IDs are `sourced-stock-kit-bulk-20261027-<suffix>`.
These are installed games, with completed release validation, not just proposed plans.
Each batch has an independent whole-archive byte comparison, exact factory BMP
readback in all three compact archives, unchanged native player/club/manager/photo
and recipe checks, complete SOURCE A/B recipe and game-inventory equality, genuine
Stoke startup and changed-club player-card captures, and original-frame lead review.
Other season bindings and the original 2015 backup were preserved at every promotion.
Factory fallback means the declared club's original game art; it does not certify a
season-authentic shirt design or the historical accuracy of unrelated player facts.

Evidence root, local only:
`.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/bulk-kit-declared-identity-20261027-v2/`.
Each season contains `completion-proof-vNNN.json`, the native/runtime scope proof,
original-frame review, and installed full-release validation. The serial executor's
`live-serial-state.json` identifies the exact active stage. Do not rerun completed
builds or captures. Review original PNGs when requested by that executor; the review
barrier is a lead task, not a request for the user's approval.

## Fixed counts at v196

Stock-kit baseline: **327 candidates = 134 installed corrections + 32 disproved
candidates + 161 untreated candidates**. Fifteen additional no-op dispositions were
proved against already-corrected club identities and all three original bitmaps;
these are not credited as kit deliveries. The prepared bulk batch admitted 222
native-ready mappings; 69 have now been installed. Eight known source-cohort
conflicts remain quarantined separately.

The original cross-club queue remains **2,809 candidates, 110 disposed, 2,699
unreviewed**. Original source-cohort cases remain **42, with 34 delivered and eight
pending**. Group counts remain 30 tracked groups, 26 closed and four open. These
denominators measure different scopes and must not be combined into an overall
completion percentage. The 26 RC milestone is **not closed**.

## Roster and nationality follow-up

A read-only current native club-name census found 165 same-country collision
groups across the games. These are review candidates, not 165 confirmed bugs.
Reusing original source bytes for their carriers found 39 source-supported label
mismatches; 26 have an exact crosswalk to the earlier v90 label candidate list.
Existing guarded plans admit 16 label changes; the others have destination/coach
conflicts or insufficient evidence. No changes from this review have been installed.
The retained manager plans include previous no-op paired entries and must not be
interpreted as hundreds of new manager corrections.

Evidence: sibling `current-club-duplicate-census-20261027-v1/`, including the
original-cohort review index, guarded-plan index and prior-v90 crosswalk. None of
these 39 positive source conflicts overlaps the 222 admitted bulk kit targets;
`new-positive-source-conflict-overlap-review-v1.json` records that check.

Swiss 2020 needs a coupled repair: carrier 1110 already contains the sourced Vaduz
opening XI, while the other Vaduz label (1109) carries St. Gallen's sourced XI.
The legacy St. Gallen carrier 1105 is a separate dependency. Blindly adding another
Vaduz squad at 1109 would introduce a duplicate and is not approved. Preserve the
completed 2019 repairs while adjudicating each year's complete club map.

Original player cards also show nationality review candidates for Duijnhoven 2003,
Balli 2004 and Wölfli 2007. The cached target-season squad text genuinely omits a
nationality column; this is not evidence of a newly discovered scraper bug.
Names and DOBs do not authorize retaining an unrelated carrier's flag. These
observations are recorded independently of kit approval. A DFB original profile
for Duijnhoven was retained; several other HTTP source requests were refused and
must not be described as saved originals or completed nationality corrections.

## Space and preservation

Only independently copied, completed runner game clones were retired after sealed
release and screenshot verification; the shared Wine prefix remains. Identical
old PNGs were hardlinked with SHA verification while keeping every original path
and byte; ledger: `.local/cleanup-20261027/identical-old-runner-pngs-v4/`.
Do not edit those original PNGs in place. No current release, SOURCE ancestry,
source cache, original screenshot or original 2015 backup was deleted. The attempted
old Go-cache sweep found no eligible files and freed nothing. Pi SSH was reachable,
but no new Pi archive was created during this checkpoint.

Next: finish the serial kit batches, deliver source-backed coupled club/roster
corrections, resolve calendar/Bath ownership blockers and confirmed nationality
observations, then run one consolidated all-season regression. Missing portraits
and genuinely unavailable secondary facts remain separately documented allowed gaps.
