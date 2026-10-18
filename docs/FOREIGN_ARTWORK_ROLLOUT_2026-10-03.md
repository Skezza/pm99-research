# Foreign artwork rollout — 2026-10-03

This is an artwork-only milestone. It does not certify every player's ratings,
club allocation, nationality or every unmodified historical kit.

## What changed

- 2015/16: 30 source-bound shirt projections installed in the three native
  compact-kit archives. The original factory silhouette, folds, native bitmap
  wrapper, transparent pixels and game palette are retained. Sources only show
  shirts: unchanged shorts colours are not independently certified.
- The old list of “29 confirmed defects” contained incorrect observations.
  Lazio is not Sampdoria; several white rectangles are sponsors, not shirt
  bands; Anderlecht really has hoops; Thun really has vertical stripes.
  The new receipt records corrections to those observations. Sampdoria carrier
  203's genuinely missing band is included. These are source comparisons,
  not an arbitrary colour change or a database-format experiment.
- 2,454 additional FIFA-edition portraits installed across 15 seasons,
  2009/10–2025/26 excluding the already expanded 2014/15 and 2015/16 releases.
  The bounded first pass tries 200 identity-matched players per season,
  round-robin across foreign clubs. It is **not complete squad coverage**.
- 88 visually reviewed real photographs installed across all 26 seasons.
  Sources are named Commons files with a recorded photographic date/year,
  artist, licence, source bytes, face crop and native bitmap. The window is
  two years before to one year after the opening year; not necessarily an
  exact opening-day photograph. Both Ronaldos are distinguished by DOB.
- All preferred releases are now `visual-real-photos-20261003-r9`. Database
  files and executables were not rebuilt or edited by these artwork patches.

The independently checked selection excludes a Ronaldo sculpture, Raúl Rojas
González (a different person), two blurred Raúl photographs and two Brazilian
election-candidate photographs incorrectly discovered for Roberto Carlos.
The raw candidates and explicit quarantine decisions remain retained.

## Evidence and receipts

- Kit source/before/after comparisons and 90 pixel-lane events:
  `.local/visual-quality-v1/2015-16/kit-source-projection-r7`.
- Initial kit release passed a fresh registered Stoke runner proof and QA
  with zero blockers before the later photograph-only update.
- All 26 real-photo selections, source attribution, crops and comparison sheets:
  `.local/foreign-photo-expansion-v1`.
- Authoritative selection review: `visual-review-r3.json` in that folder.
- New FIFA source/name/DOB/edition/framing checks and explicit rejected rows:
  `.local/foreign-portrait-rollout-r8/<season>/patch/receipt.json`.
- Small real-photo patches: `.local/reviewed-real-photo-rollout-r9`.
- Every new installed photo checked against its recipe identity, retained
  source bytes and native BMP: 2,538 final carrier images, zero failures in
  `.local/foreign-photo-expansion-v1/installed-verification-r9.json`. This count
  differs from 2,454 + 88 because four real photographs supersede new FIFA
  images on the same carrier.
- The stronger follow-up also checks active portrait archive entries. None
  conflicts with any of the 2,538 newly installed loose BMPs:
  `installed-verification-r9-effective.json` in the selection folder.
- Genuine 2015/16 Rayo selection (country and club visibly identified):
  `sourced_rayo_2015_16_20261003_r9_corrected/screens/19_select_rayo.png` under
  the runner artifact root. This shows the restored diagonal red sash.
  The earlier `sourced_rayo_kit_2015_16_20261003_r9` attempt clicked the wrong
  country and is retained as a failed attempt, never as Rayo evidence.
- Fresh current-release runtime qualification:
  `.local/foreign-photo-expansion-v1/runtime-qualification/qualification.json`.
  Final batch: 26 completed, 25 passed, 2004/05 failed. Its two subsequent
  current-release attempts also failed, including the original `tiny-m73`
  worker selection. A completed batch is not an all-season pass.
- Runner screenshots: `.local/runlogs/pm99_runner/real_photos_*_20261003_r9`.
  Individual foreign profiles are separate `real_photo_*` runs. Profile-only
  probes do not submit offers or alter the registered game.

Sample sheets:

- `requested-player-photo-showcase.png`: Zidane, Ronaldo Nazário, Cristiano
  Ronaldo, young Messi, Xavi, Iniesta, Arnautović and Yamal; original crop beside
  the actual converted bitmap, with photo year explicitly labelled.
- `all-26-seasons-real-photo-selection.png`: one selected player per season.
- `foreign-photo-selection-01.png` through `-05.png`: all 88 approved photos.

The targeted artwork, source-selection, geometry, publication and QA tests
pass **45 cases**. They include low-disk refusal, executable-write rejection,
interruption recovery, rollback, concurrent restore refusal, source framing
and receipt-bound kit ancestry after a portrait-only update. Tracked repository
boundary and Markdown diff checks pass. Existing unrelated dirty-worktree
changes and submodule states have not been reset or committed.

Final registration: **25 current releases have fresh valid runtime attestations
and passing registered QA reports**. Passing unchanged reports from
`.local/season-qa-v2/foreign-photo-rollout-20261003-r9-midway` were retained and
registered, not needlessly re-run. Updated late-season reports and the separate
2015/16 report are under `foreign-photo-rollout-20261003-r9-final`. The sole
unverified release is 2004/05; its QA failure remains explicit and unregistered.
These QA passes retain editorial warnings and do not overrule the factual
problems documented below.

The usual launch command resolves the installed artwork revision automatically:
`./pm99-season play 2025-26` (substitute any supported year). No raw manifest or
different executable command is required. Artwork rollback/source caches and
current games remain local; free space at closeout is approximately 1.2 GiB.

## Storage, rollback and repeatability

Artwork installation uses `scripts/season_art_transaction_v1.py`. It checks
the entire current game, saves overwritten/removed art, writes only allowlisted
bitmap assets, verifies every unrelated file, and publishes fresh metadata.
There is a season lock, an interrupted-transaction journal and explicit restore
command. Fresh QA and runtime evidence are not inherited from an older build.
The old release is marked archived with a recoverable art delta, not falsely
advertised as still being a separate unchanged full game.

Rollback receipts and original bytes:
`.local/season-art-transactions-v1/{kits-r7,foreign-r8,real-photos-r9}/<season>`.
Restore newer transactions before older ones; later changes are rejected.

```bash
python3 scripts/season_art_transaction_v1.py restore \
  --transaction-root .local/season-art-transactions-v1/real-photos-r9/2000-01
```

Three superseded full game copies were converted to verified local deltas.
See `docs/LOCAL_EXPERIMENT_CLEANUP_2026-10-03.md` for exact targets, retained
bytes, required clean recovery base and recovery command. There is **no Pi
backup**. Current games, recipes and source caches remain local.

The bounded source/installation commands are resumable and the original
downloads are hash-bound. The 200-player cap is an explicit storage-controlled
first pass, not a hidden declaration that everyone has a photograph. Increasing
it for a subsequent tranche requires a fresh output root/release revision;
do not rewrite old receipts or reapply the same release ID.

## Remaining factual issues revealed by the screenshots

The genuine 2000/01 Zidane profile shows the correct newly installed face but
also **Uruguay** as nationality and shooting **27**. Its unchanged recipe
explicitly preserves the carrier nationality and contains shooting 27 despite
claiming nearest-edition rating provenance. Artwork QA must not conceal this.
Evidence: `real_photo_zidane_2000_01_20261003_r9/screens/45_profile_only_zinedine_zidane_2000_01_done.png`.
This is an existing recipe/rating issue, not damage from the portrait patch.

The 2025/26 Yamal profile likewise renders the selected 2025 face, but shows
age 26 and an inconsistent secondary-role label. The visible player facts need
their own recipe-to-native-profile audit; a successful launch is not that audit.

Some selection cards also expose questionable club ownership (for example
Mbappé on Monaco carriers in later seasons and Messi on a Monaco carrier in
2022/23). The source selection verifies the person; it does not certify that
the registered recipe assigns him to the correct club. These require a dated
club-association audit before broader historical-accuracy claims.

## Runner failure investigation (superseded by identity repair)

The 2004/05 current-release Stoke route failed twice during new-game setup
with the native “Application cannot continue” modal. An Arsenal/profile route
also failed before entering the game. A separate control run restored the
**original pre-artwork MINIFOTO archive and omitted all added photographs**,
while keeping the exact same database, executable and kit bytes. That also
failed (`pre_photo_2004_05_failure_control_20261003b`). The failure is therefore
reproducible without this artwork patch on the current worker; its root cause
is not yet established. Earlier registered evidence on `tiny-m73` passed.
Selecting `tiny-m73` again with the current release also fails; changing only
the worker label does not resolve it.
Do not inherit that older attestation or call the present release verified
until a fresh exact-release capture succeeds.

The subsequent crash investigation isolated duplicate native self-IDs in
recipe-appended player records. An unchanged database with a pinned random
seed failed; changing only those two-byte IDs passed with the same executable
and seed. See [the setup-crash repair report](2004_05_SETUP_CRASH_REPAIR_2026-10-03.md)
for the exact controls, release correction and current runtime evidence.

The ordinary tracked-repository boundary check passes. Its optional local
cleanup check flags a pre-existing, 1.4 MiB `upstream/.local/season-2015-16`
directory dated August 27. It is untouched; this artwork milestone did not
create it and does not authorize discarding that old research data.

## Credits

Photographs: the individual Wikimedia Commons photographers and rights
holders, with attribution and licence URLs recorded per selected file.
For example the 2000 Zidane photograph is credited to José D. López-Palacios /
20 Minutos under CC BY-SA 2.1 Spain. Portrait conversion does not remove licence
obligations; attribution/share-alike must be reviewed before redistribution.

FIFA lane: EA Sports player portraits mirrored by SoFIFA; identity matches use
the retained legacy SoFIFA/EA catalogue and exact target-edition image URLs.
For years outside that catalogue, stable ID/name/DOB identity and the image's
edition URL are distinguished from target-edition roster evidence. These assets
are not represented as openly licensed for redistribution.

Kit photographs/renders: retained FIFAIndex FIFA16 shirt sources; original
PM99 factory artwork supplies the rendering silhouette and tonal structure.
Research/local-game use does not establish a redistribution licence.
