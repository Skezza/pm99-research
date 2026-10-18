# Clean-static post-ingress operations

## Scope and status

This is the operations path from a `clean-static-ingress-complete-not-playable`
candidate to a release candidate.  It applies to the nine currently clean-static
seasons: 2000/01--2007/08 and 2020/21.

It does **not** make a playable claim.  A clean static audit proves only the
three database containers were written from a verified base without changing
the fixed mode-1 roster tail.  It does not prove the target season's managers,
opening squads, kits, portraits, calendar executable, or PM99 runtime.

The static receipts enumerate the following remaining gates:

1. calendar runtime validation;
2. target-season manager source review;
3. target-season kit materialisation;
4. portrait/no-photo materialisation;
5. ratings reconciliation;
6. opening XI and formation review;
7. PM99 runtime validation; and
8. a target-season screenshot.

The batch receipt for 2003/04, 2004/05, 2006/07, and 2020/21 is at
`.local/season-static-ingress-batch-v1/mechanical-tranche-20260904-r1/static-ingress-batch-receipt.json`.
The individual receipts for 2000/01--2002/03 are below
`.local/season-static-ingress-v1/`.  The original nine-season summary and
hashes are in [STATIC_INGRESS_MILESTONE_2026-09-04.md](STATIC_INGRESS_MILESTONE_2026-09-04.md).

## What is already reusable

| Gate | Existing reusable input / command | What it proves |
| --- | --- | --- |
| Calendar evidence | `.local/calendar-v1/YYYY-YY/{calendar-receipt.json,MANAGPRE.EXE}`; `season_calendar_package_overlay_v1.py` and `season_calendar_batch_bind_v1.py` | A 853-byte-contract calendar patch is hash-bound to the source package. All 25 non-2015 seasons have this receipt. It is not yet installed into a target final tree or run. |
| Calendar materialisation | `materialise_season_calendar_v1.py` | Installs only the strict package's hash-bound `MANAGPRE.EXE` into a fresh tree whose existing executable matches the verified base. Its receipt binds the target package, source calendar audit/receipt, base descriptor and before/after whole-tree inventories, and proves this stage changed exactly `MANAGPRE.EXE`. Runtime validation remains explicitly pending. |
| Opening manager evidence | `.local/season-overlays-v1/YYYY-YY/manager-v1/` (`manager-v2` for 2007/08) | A write-once, package-bound provisional manager ledger. It does not author a correct manager for a missing club. |
| Opening XI evidence | `.local/season-overlays-v1/YYYY-YY/opening-xi-v1/` | A write-once, package-bound reconciled opening-XI receipt. The integrator permits deterministic formation bands only after a real XI is reconciled. |
| Ratings | `season_editorial_rating_input_builder_v1.py`, then `season_editorial_ratings_v1.py` | Deterministic ratings for source-authored allocated players; this is not a source-discovery tool. |
| Kit source/render | `season_kit_source_capture_v1.py`, `season_kit_catalogue_v1.py`, `season_kit_render_bindings_v1.py` | Captures source evidence and produces hash-bound rendered artifacts; it does not install a complete kit archive set into a final game tree. |
| Portraits | `materialise_native_no_photo_v2.py` | Disables inherited recycled-carrier photos for `native-no-photo` / `unresolved` rows. This is the required fail-open route and has a test. |
| Database compile | `season_package_compiler_v2.py`, `audit_season_clean_base_v1.py` | The narrow JUG/EQ/ENT write surface and clean-base comparison. The compiler deliberately does not write calendar, kits, or portraits. |
| Reproducibility / release metadata | `season_pipeline_v2.py`, `season_pipeline_buildplan_v2.py` | Two independent clean builds, complete output inventories, release manifest, then a separate runtime attestation. |
| Runtime capture | `upstream/pm99-runner/scripts/pm99_runner/run_stoke_route_capture.sh` | A disposable remote run can hash-copy an arbitrary DBDAT set plus `MANAGPRE.EXE` using `--dbdat-dir` and `--exe-file`. The existing guided driver still contains 2015 Stoke roster assumptions, so this must first be given a target-season-neutral validation/capture profile. |

`season_playtest_commands_v1.py` is intentionally excluded from this path: it
creates calendar-only 2015-content presets and explicitly is not a historical
target-season database builder.

## Measured authoring gaps

The following figures use the final-shard carrier allocation and the existing
manager/XI overlays.  They count only allocated carrier clubs; they do not
mistake source coverage of an unallocated club for an authorable fixed carrier.

| Season | Allocated clubs | Unmapped non-system carriers (of 446) | Manager gaps in allocation | XI gaps in allocation | Rendered kit bindings in allocation |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2000/01 | 85 | 361 | 3 | 46 | 30 |
| 2001/02 | 120 | 326 | 10 | 63 | 23 |
| 2002/03 | 120 | 326 | 19 | 61 | 2 |
| 2003/04 | 120 | 326 | 16 | 75 | 1 |
| 2004/05 | 159 | 287 | 25 | 108 | 1 |
| 2005/06 | 241 | 205 | 68 | 189 | 2 |
| 2006/07 | 239 | 207 | 75 | 192 | 1 |
| 2007/08 | 239 | 207 | 69 | 186 | 1 |
| 2020/21 | 228 | 218 | 59 | 168 | 1 |

The current kit catalogues have no authorised native fallback in this scope:
every listed allocated carrier is either source-ready, blocked, or missing a
catalogue row.  The lowest-level current rating pass is also not complete:
the existing 2000/01 rating-input audit records 62 allocated carriers / 1,109
players outside the reviewed country-strength policy plus one missing primary
position.  The other eight seasons have no equivalent current rating result.

Therefore the immediate bottleneck is data selection and source coverage, not
the JUG/EQ/ENT file mechanics.  A package that only preserves the native
mode-1 opening state cannot meet the worldwide historical-release gate.

There is one additional known gameplay guardrail: the world compiler preserves
mode-1 handling because that field has no proven writer in that lane.  A
release QA check must flag goalkeeper-like handling values on an outfield
player rather than treating the deterministic nine-skill rating output as a
complete solution.

## Deterministic staging order

Run stages only against a new revision directory.  Never add later assets or
runtime state to an existing clean-static game tree; it is evidence for the
old source package, not a mutable release workspace.

1. **Freeze the exact selected source package and allocation.** Start from
   the hash-named clean-static reconciled package for the selected season,
   not a previous game tree.  Re-run `season_package_v2.py validate --strict`
   and record its SHA-256 alongside the allocation SHA-256.
2. **Close allocation, manager and XI queues.** Extend the raw source
   captures, then create new immutable manager/XI overlays.  A manager remains
   a hard blocker: native manager fallback is not permitted.  An XI permits
   the documented formation inference only where exactly eleven source people
   are reconciled.
3. **Produce a complete ratings revision.** Add missing country-strength
   decisions and any missing primary-position fact as source/editorial inputs;
   generate the rating input and output afresh.  Preserve an explicit
   no-handling-write audit for mode-1 outfield players.
4. **Close kits and bind artifacts.** Capture only targeted season sources;
   render against the verified base palette.  For each continuing target club,
   require a source-backed rendered kit.  Native kit fallback is allowed only
   for a proven exited carrier.
5. **Join the evidence in one fresh strict package.**
   `season_authoring_layer_integrator_v1.py` is the fail-closed join.  Its
   audit must have no hard blockers before promotion.  It deliberately creates
   `native-no-photo` declarations for target players without image evidence.
6. **Materialise every separate write lane in two clean trees.** Use the
   generic database compiler, a new generic calendar materialiser, a new
   generic kit-archive materialiser, and `materialise_native_no_photo_v2.py`.
   Then audit the full declared output inventory and compare clean A with
   clean B.
7. **Runtime and evidence.** Inject only the exact final DBDAT set and
   calendar executable into a disposable runner lane, use a target-neutral
   selector/squad capture route, and retain the successful route summary and
   screenshot hash.  Attach those receipts to the final inventory using
   `season_pipeline_v2.py attest`.

Stages 2--4 can run independently for different seasons.  Stage 5 is the
only convergence point.  Stages 6--7 must be serial per runtime worker lane,
but are independent per final immutable build.

## Exact command skeleton for one new revision

Set these variables to a **new** ignored revision directory and the selected
season's frozen inputs.  Do not substitute a provisional calendar-only preset.

```bash
SEASON=2000-01
REV=.local/release-candidates/${SEASON}-r1
PACKAGE=.local/season-static-ingress-v1/${SEASON}-20260904-r2/season-package.reconciled.json
ALLOCATION=.local/season-authoring-final-shards-v1/a/${SEASON}/carrier-allocation.json
MANAGERS=.local/season-overlays-v1/${SEASON}/manager-v1/opening-manager-ledger.json
OPENING=.local/season-overlays-v1/${SEASON}/opening-xi-v1/opening-lineup-reconciliation.json
KITS=.local/season-kit-sources-historical-backfill-v1/${SEASON}/kit-catalogue-v1.json
KIT_BINDINGS=.local/season-kit-renders-historical-backfill-v1/${SEASON}/kit-render-bindings-v1.json
BASE=.local/season-static-qualification-v1/2005-06-carrier-10-reconciled-20260904
VERIFIED_BASE=.local/season-pipeline-v2/verified-base.json
```

First validate and create *only* authoring receipts.  This will report the
known hard blockers today; it must not be described as an integration pass
until their count is zero.

```bash
python3 scripts/season_package_v2.py validate --package "$PACKAGE" --strict

python3 scripts/season_editorial_rating_input_builder_v1.py \
  --draft-package "$PACKAGE" \
  --carrier-allocation "$ALLOCATION" \
  --opening "$OPENING" \
  --output-input "$REV/editorial-rating-input.json" \
  --output-ratings "$REV/editorial-ratings.json" \
  --output-audit "$REV/editorial-rating-audit.json"

python3 scripts/season_authoring_layer_integrator_v1.py \
  --draft-package "$PACKAGE" \
  --carrier-allocation "$ALLOCATION" \
  --manager-ledger "$MANAGERS" \
  --opening-reconciliation "$OPENING" \
  --kit-catalogue "$KITS" \
  --kit-render-bindings "$KIT_BINDINGS" \
  --rating-output "$REV/editorial-ratings.json" \
  --output-draft "$REV/season-package.authoring.json" \
  --output-audit "$REV/authoring-integration-audit.json"
```

After the authoring audit reaches zero hard blockers, use a new clean tree
for the no-photo lane, never the static-ingress tree:

```bash
python3 scripts/materialise_native_no_photo_v2.py \
  --package "$REV/season-package.authoring.json" \
  --game-tree "$REV/build-a/game" \
  --receipt "$REV/build-a/native-no-photo-receipt.json"
```

The calendar materialiser is now available for the separate executable lane.
It accepts the final strict package, its matching source calendar-binding
audit, the hash-verified calendar receipt/executable and the verified-base
descriptor. It refuses to overwrite a non-base `MANAGPRE.EXE`, and its receipt
still marks runtime validation pending. Run it once for each fresh build tree,
for example:

```bash
python3 scripts/materialise_season_calendar_v1.py \
  --package "$REV/season-package.authoring.json" \
  --calendar-audit ".local/season-calendar-bound-batch-v2/$SEASON/calendar-binding-audit.json" \
  --calendar-receipt ".local/calendar-v1/$SEASON/calendar-receipt.json" \
  --calendar-executable ".local/calendar-v1/$SEASON/MANAGPRE.EXE" \
  --verified-base "$VERIFIED_BASE" \
  --game-tree "$REV/build-a/game" \
  --output "$REV/build-a/calendar-materialisation-receipt.json"
```

The kit-archive materialiser is still missing. It must consume only the
selected render bindings, write the complete declared archive set, and emit a
package/base/output-bound receipt before this command sequence can produce a
historical release.

Once they exist, the final stage must use a reviewed V2 build plan for both
clean trees, then the existing primitives are:

```bash
python3 scripts/season_pipeline_v2.py double-build \
  --first-tree "$REV/build-a/game" \
  --second-tree "$REV/build-b/game"

# This is only valid after the target-neutral runner profile and final
# build inventory exist.
./scripts/run_pm99_experiment.sh route-capture --worker <worker> \
  --run-tag "${SEASON}-r1" -- \
  --dbdat-dir "$REV/build-a/game/DBDAT" \
  --exe-file "$REV/build-a/game/MANAGPRE.EXE" \
  --team-name "Stoke C." --capture-route squad
```

The last command demonstrates the runner's transport capability, not a
qualified final evidence command: its target-specific selector coordinates,
expected roster names, completion predicate, and screenshot manifest must be
made season-neutral and bound to the final output inventory first.

## Validation performed for this note

- Read the nine static ingress receipts and the nine matching source package,
  allocation, manager-overlay, opening-XI-overlay, kit-catalogue, and kit
  render-binding inputs.
- Confirmed all 25 calendar receipt/executable pairs exist under
  `.local/calendar-v1/`.
- Ran `--help` for the named reusable scripts and inspected their declared
  write boundaries.
- Confirmed the no-photo stage has
  `scripts/test_materialise_native_no_photo_v2.py`; the generic integration,
  calendar-overlay, and release-metadata primitives have their corresponding
  tests.

No PM99 binary, source package, static receipt, 2015 legacy file, or
editorial workbench file was changed while preparing this note.
