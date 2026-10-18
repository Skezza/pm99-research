# Historical photograph portrait pilot V1

This is a separate alternative to the deterministic FIFA portrait pipeline.
It discovers real photographs from Wikimedia Commons, accepts only candidates
with a declared photograph date and reusable licence, checks that the player's
given name and surname occur in the file title, and prefers candidates with a
detectable face. It records the source page, original URL, date, author,
licence, hash and PM99 conversion paths.

The first pilot targets the 2014/15 Stoke City squad. It found 17 automatic
candidates from 25 players within a two-year window around 2014. Eight were
left unresolved; no FIFA or modern portrait was silently substituted.

Automatic acceptance means only that the identity, date, licence and face
checks passed. The sample sheet is a mandatory visual gate. The first run
correctly demonstrates why that gate remains necessary: most results are much
more photographic than FIFA artwork, while small-action-subject crops such as
Bojan Krkic and Charlie Adam must still be rejected or manually recropped.
At this initial discovery stage nothing was applied to a registered game.
The reviewed pilot was subsequently promoted on 2026-10-03; see below.

```bash
python3 scripts/season_historical_photo_pilot_v1.py \
  --portrait-manifest .local/season-portrait-pilots-v1/2014-15/portrait-materialisation.json \
  --club 'Stoke City' --target-year 2014 --year-window 2 \
  --minifoto .local/season-portrait-pilots-v1/2014-15/game/DBDAT/MINIFOTO.PKF \
  --cascade .local/season-historical-photo-pilots-v1/shared/haarcascade_frontalface_default.xml \
  --output-root .local/season-historical-photo-pilots-v1/2014-15/stoke-v3
```

The OpenCV face cascade used by the pilot is the upstream
`haarcascade_frontalface_default.xml`. The generated assets occupy about 9 MB,
including superseded pilot iterations. Source images remain separate from the
FIFA cache and registered releases.

## Automated identity and framing QA

Run `season_historical_photo_qa_v1.py` after discovery. It uses the cached
120-pixel FIFA portrait solely as an identity reference. OpenCV YuNet detects
all faces in a candidate and SFace compares each with that reference. It
rejects weak or ambiguous matches, faces smaller than 65 source pixels, crops
that would cross the photo edge, and photographs taken after 30 June 2015.
The accepted window begins on 1 July 2012, allowing a nearby earlier photo.
The selected face is cropped to 1.65 times its size before native PM99 bitmap
conversion. Every source and converted bitmap has a SHA-256 receipt.

The model files are obtained from the OpenCV Zoo repository:

```bash
mkdir -p .local/season-historical-photo-pilots-v1/shared
curl -L --fail -o .local/season-historical-photo-pilots-v1/shared/face_detection_yunet_2023mar.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
curl -L --fail -o .local/season-historical-photo-pilots-v1/shared/face_recognition_sface_2021dec.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
```

Use the project season test environment, which installs OpenCV 4.10:

```bash
.local/venvs/season-pipeline/bin/python scripts/season_historical_photo_qa_v1.py \
  --fifa-manifest .local/season-portrait-pilots-v1/2014-15/portrait-materialisation.json \
  --discovery-receipt .local/season-historical-photo-pilots-v1/2014-15/stoke-v3/historical-photo-receipt.json \
  --fifa-cache .local/season-portrait-cache-v1 \
  --photo-cache .local/season-historical-photo-pilots-v1/shared/photo-cache \
  --minifoto .local/season-portrait-pilots-v1/2014-15/game/DBDAT/MINIFOTO.PKF \
  --detector .local/season-historical-photo-pilots-v1/shared/face_detection_yunet_2023mar.onnx \
  --recognizer .local/season-historical-photo-pilots-v1/shared/face_recognition_sface_2021dec.onnx \
  --output-root .local/season-historical-photo-pilots-v1/2014-15/stoke-qa-v4
```

The complete 25-player sheet is `stoke-25-qa-sheet.png` in that output root.
In the first QA pass, nine photographs passed identity and framing checks,
fourteen players retained their FIFA portrait, and two had no available FIFA
reference. Glenn Whelan's group-photo face was rejected, while Bojan Krkic and
Charlie Adam were recovered from other dated photographs with face crops.
These were automatic candidates before the isolated runtime proof below.

## Isolated in-game proof

The QA receipt was combined with the existing FIFA materialisation by
`scripts/compose_historical_photo_materialisation_v1.py`. That produced an
isolated 2014/15 game with nine historical photos, 14 FIFA fallbacks and two
no-photo outcomes for Stoke. The full worldwide materialisation still covers
11,557 players; structural validation checked every operation with zero
issues. The runner successfully opened Stoke City and captured ten profiles.
Its Stephen Ireland profile displays the selected historical photo; Glenn
Whelan displays his FIFA fallback rather than the wrong face from the group
photograph. The evidence is under
`.local/runlogs/pm99_runner/historical_photo_qa_2014_15_stoke_20260926_r1`.

The registered release was not changed by that isolated proof. Face comparison scores are a useful
automated filter, but this 25-player visual review remains the benchmark for
deciding whether to promote a photographic build more widely.

## Source and squad binding added 2026-10-03

The composer now rejects a QA receipt unless its input-manifest SHA-256 matches
the FIFA materialisation being composed. It also rejects duplicate player
carriers and receipts that do not exactly cover the declared club's squad.
This prevents a previous successful face review being silently reused after
the input identities change. The existing nine-photo Stoke pilot passes these
stronger checks without regenerating or modifying its game.

The practical release-review target is representative user spot checks after
source-identity checks, framing checks and installed-game evidence have been
reviewed by the worker. Matching receipts or successful face detection alone
must not be described as complete visual or historical verification.

For the registered 2015/16 foreign portraits,
`scripts/reconcile_foreign_portrait_biographies_v1.py` retains revision-pinned
Wikipedia biographies and compares the target and source's labelled identities.
Both full names must identify one biography. A matching biography can resolve
an alias; if its birthday supports the recipe rather than the CSV, the upstream
date conflict is explicitly recorded rather than incorrectly replacing the
recipe. Mononyms, conflicting target birthdays and missing image evidence remain
worker-owned review cases.

The first full 579-title capture reconciled 70 of the original 442 portrait
review cases; 372 remain unresolved. Original findings remain intact in
`.local/visual-qa-20261003/foreign-source-verification/report.json`, with
hash-bound resolutions in `foreign-biography-review/report.json` alongside it.
This original capture was **not** visual certification or a playable correction.
The subsequent corrections and remaining uncertainty are recorded below.

An official source was also captured with Playwright and visually inspected:
`foreign-biography-review/villarreal-samus-official.png` shows Samuel García's
name and 1990-07-13 birthday on Villarreal's own 2015 signing announcement.
It proves the recipe's `Samu` identity, not the correctness of the currently
installed Samuel Delgado portrait. The source is
[Villarreal's signing announcement](https://villarrealcf.es/en/fichaje-samus/).

Verification: 47 targeted tests passed, including negative tests for stale QA
inputs, duplicate carriers, wrong-club receipts, conflicting birthdays and
source-only identity matches. Boundary and Markdown diff checks passed. New
biography cache and review evidence occupy approximately 13 MiB; no full-game
copies were made during that initial investigation.

## Reviewed local rollout — 2026-10-03

No Pi was used. Existing caches and completed photographs were reused rather
than scraped again; databases, managers, ratings and executables were not rebuilt.
The old releases remain intact. New art is published as a narrow, hash-bound
patch with fresh release-specific runner evidence and QA.

- **2014/15:** every one of the 11,557 pilot rows was checked against the current
  recipe, captured FIFA15 CSV, source image hash/edition, single-face framing and
  converted bitmap. Seventy-one weak/missing-birthday matches were quarantined.
  The published release has 4,013 portraits and 7,544 no-photo outcomes:
  1,463 English-club and 2,550 foreign-club portraits (club group, not nationality).
  Nine are the already reviewed real Stoke photographs; most remaining images
  are explicitly FIFA-era fallbacks, not a worldwide photographic pipeline.
  Stoke retains 14 FIFA fallbacks and two blanks alongside those nine photographs.
- **2015/16:** official EA FIFA16 ID/full-name evidence supplements the cached
  biography checks. Of 442 original review cases, 146 are reconciled; two
  confirmed wrong assignments are replaced and the remaining 294 are blanked,
  not declared editorially resolved. `Samu` now uses Samuel García Sánchez
  (201379), and Deportivo's `Lucas` uses Lucas Pérez Martínez (199354), not
  Samuel Delgado and Lucas Moura. Persistent source corrections live in
  `data/season-portrait-overrides-v1/2015-16.json`. Original recipe/CSV birth-date
  conflicts remain explicit; a conflicting CSV alone never changes the recipe.
- **All 26:** small source-bound portrait correction plans and materialisations
  exist under `.local/season-visual-patches-v2`. For the other seasons they remove
  inherited stock faces from unresolved/no-photo players, not populate missing
  portraits. Four releases (2013/14, 2014/15, 2015/16 and 2022/23) are applied;
  the other 22 apply their retained correction on first real `play`, with a
  1 GiB free-space reserve. Read-only validation and `--print-command` do not
  create game copies. Already applied or superseded plans are not repeated.

Current commands (no revision-file selection required):

```bash
./pm99-season play 2014-15
./pm99-season play 2015-16
./pm99-season play 2022-23
./pm99-season evidence all
```

The earlier 2014/15 release was `visual-world-photos-20261003-r3`; its reviewed
source/combined manifests are in
`.local/season-portrait-pilots-v1/2014-15/source-reviewed-20261003`.
Its fresh inventory-bound Line-Up proof is
`.local/runlogs/pm99_runner/visual_world_photos_2014_15_20261003_r3/screens/022_line_up_inspect.png`.
The earlier profile captures demonstrate the nine unchanged historical images;
a Line-Up screenshot itself does not prove every player's visible portrait.

The earlier 2015/16 release was `visual-reviewed-20261003-r2`; its runner proof is
`.local/runlogs/pm99_runner/visual_reviewed_2015_16_20261003_r2/screens/022_line_up_inspect.png`.
The enhanced reconciliation report is
`.local/visual-qa-20261003/foreign-biography-review/report.json`.

The composer now supports any explicitly declared club roster, requires exact
coverage, and carries photograph attribution, licence and date basis. Old Commons
records whose exact timestamp field was not captured are explicitly marked
`legacy-Commons-date-field-not-recorded`. A QA receipt can be rebound to a revised
world manifest **only** when every row of its reviewed club is byte-identical;
changed club identities require a new review. Neither source agreement nor face
detection is independent visual certification of every player.

## Two-season quality pass, 3 October 2026

The preferred 2014/15 release is now `visual-quality-kits-20261003-r5`.
Forty clubs have additional source-bound corrections in all three compact kit
archives. Player, club, manager, executable and portrait bytes are unchanged.
The captured catalogue produced 49 candidates: eight had no safe current-club
binding, and Atlético was excluded because its shorts overlay is unsupported.
Thirty-two other source-ready entries lack complete exact pattern layers.
These are explicit gaps, not guessed replacements or a claim that every kit
in the season is accurate.

Visual checking caught and fixed white fabric being flood-filled as background,
thin sleeve cuffs being expanded across the sleeve, and straight patterns being
bent by per-row/per-column scaling. All four final comparison sheets were
inspected before application. Sources were reused from the existing catalogue
and cache. The historical database was not recompiled.

The runner shows Bayern selected as a **friendly opponent**, not a managed club:
`.local/runlogs/pm99_runner/visual_quality_kits_2014_15_20261003_r5/screens/19_select_bayern.png`.
The country-selection screenshot shows the German kits together. Archive and
DAT palette hashes were checked against the runtime. A separate fresh Stoke
launch attests the registered release:
`.local/runlogs/pm99_runner/visual_quality_2014_15_20261003_r5/screens/022_line_up_inspect.png`.
Its QA report passes with zero blockers and five declared warnings.

The preferred 2015/16 release is `visual-quality-portraits-20261003-r6`.
All 2,300 original English portrait entries were checked against the actual
compiled English rosters. The legacy foreign-only recipe must **not** be used
as the English identity join. Original converted BMPs remain available; many
raw-source paths refer to old folders unavailable locally. That absence alone
is not evidence of a wrong player or permission to erase a working portrait.
Period-specific references were recovered from the shared cache or exact
edition/ID URLs. Newly measured hashes are labelled as new checkpoints, not
invented original download hashes. Some 177 raw references remain unavailable.

Official edition identities, transliteration/given-name checks and pinned
Wikipedia biographies leave 136 uncertain identity/provenance/era cases.
Twenty-one flagged cases were cleared through independent biographies. The
136 unresolved images are quarantined to native no-photo, not declared to be
136 proven wrong people. There are 2,158 retained English portraits and the six
original no-photo entries. The old release retains their recoverable artwork.
Source-face detection checks framing, not who the person is. Secondary date
conflicts remain recorded and do not automatically discard a strongly labelled
correct identity. No database or kit bytes changed in this portrait patch.

Current English evidence and the narrow replay plan:

- `.local/visual-quality-v1/2015-16/portraits-recovered-r5/english-source-review.json`
- `.local/visual-quality-v1/2015-16/english-biography-review.json`
- `.local/season-visual-patches-v6/2015-16/plan.json`
- `.local/runlogs/pm99_runner/visual_quality_2015_16_20261003_r6/screens/022_line_up_inspect.png`

The new 2015/16 runtime is attested and technical QA passes with zero blockers
and four declared warnings. All 26 preferred releases validate successfully.
The actual Marco Amelia profile confirms the quarantined face is absent while
his player and Chelsea assignment remain intact:
`.local/runlogs/pm99_runner/visual_quality_2015_16_amelia_20261003_r6/screens/44_inspect_marco_amelia_quarantined_profile.png`.
The probe stopped on the profile without submitting an offer. The targeted
portrait, kit-rendering, source, patch, factory-tone and QA regression lane
passed 68 tests; repository boundary and diff checks also passed. The workspace
is still intentionally dirty; no clean-repository or committed handoff is claimed.

### The kit quality work is not closed

Every one of the 268 source-backed foreign 2015/16 kits passed the source hash,
club binding and three-size bitmap readback checks. Six source-versus-installed
comparison sheets were then inspected. This exposed **29 concrete geometry
defects**, including Ajax's centre panel, Feyenoord's halves, Udinese's stripes
and Stuttgart's chest band. Hash agreement did not catch those artistic errors.
They are retained as the next correction queue at
`.local/visual-quality-v1/2015-16/kits-source-audit/visual-findings.json`.
The other 183 foreign clubs remain declared fallback/source gaps; neither those
clubs nor the unflagged source-backed kits are automatically certified perfect.
The source pictures generally show shirts, not independently verified shorts.

Next work: correct those 29 source-bound pattern recipes, compare all three
sizes, apply one narrow kit patch and obtain fresh opponent-selection proof.
Then use this same checked workflow for subsequent seasons. Do not regenerate
already successful squad/manager data or call a clean technical report a full
historical visual approval.
