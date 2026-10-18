# PM99 initial team tactics research — updated 5 October 2026

The October stored-layout contract and implementation section below supersede
the old August byte-layout interpretation. Later August sections are retained
as dated research history, not current rollout or release status.

## August compiler correction and runtime proof (historical)

The first English-92 compiler wrote structurally valid tactic grids but used
the wide-axis range for PM99's short, vertical lane. PM99 clips that word at
the lower edge of the pitch, so the goalkeeper could be at the correct goal
end while full-backs and wide players were visibly crushed against one side.
That invalidates build 27's opening-tactics presentation only; it does not
affect the roster, player, manager, kit, or calendar data.

The August recipe exposed each static state as `(vertical lane, depth, vertical lane,
depth)`, not the actual native word order corrected below. Transfermarkt's upright pitch uses `left` across the pitch and `top`
towards the goalkeeper. PM99's vertical lane is the short 228-unit axis; depth
is the wide axis and the own goal is at low depth. The production transform is:

```
vertical = clamp(208 - left * 2.0, 20, 208)
depth    = clamp(430 - top * 4.875, 55, 440)
```

The fresh-save calibration for Stoke's 9 August 2015 4-1-4-1 is
`upstream/pm99-runner/docs/artifacts/pm99_runner/english92_2015_build30_stoke_centred_tactics_20260828/screens/023_tactics_advanced_view_attack.png`.
It visibly places Butland in the left goal area; Cameron, Muniesa, Pieters
and Johnson across the defensive line; Whelan ahead; the four midfielders
spread across their line; and Diouf at the far end. The production grid has
the SHA-256 `45f509bd69ad82d53f69afac51a2948895126c523770803fd52ced3eaa77c094`.
The compiler regression test and release audit reject an out-of-range vertical
lane as well as a goalkeeper at the wrong depth.

## Result

The opening formation is a team-specific part of the EQ database. It can be written before a new game and PM99 will show it in Advanced Tactics without loading a `TACTIC.*` file or making an in-game change.

The August captures proved that an opening shape could be changed, but did not
prove the byte boundary or both phases independently. The October investigation
below supersedes the earlier layout interpretation. A visible opening shape is
not proof that all twenty contextual states survive loading and saving.

## Stored layout and guardrails

Large mode-0 English EQ records contain a `0x6E7` (1,767-byte) region immediately before the existing manager/player-link tail. `DBASEPRE.EXE` skips this same region while reading the known club fields.

| Part | Size | Contract |
| --- | ---: | --- |
| Prefix | 0 bytes | The former supposed prefix was the first attack-depth word. |
| Eleven player slots | 1,760 bytes | `11 x 20 x 8`: one 160-byte slot per ordered XI player, with 20 four-word tactical states. |
| Controls | 7 bytes | Preserve exactly except an explicitly evidenced repair of previous corruption. |

The actual raw word order is attack depth, attack lane, defend depth, defend
lane. MANAGPRE's reader at `0x5c2380` subtracts respectively 14, 12, 8 and 9,
then clamps depths to 0..398 and lanes to 0..228. Its caller at `0x4a0dc7`
does not skip a two-byte prefix. The eleven-slot reader at `0x5c2730` consumes
1,760 bytes, after which the club reader consumes seven controls. The inverse
writer at `0x5c22b0` adds the same biases. Public recipe coordinates remain
defend lane/depth followed by attack lane/depth, in actual pitch coordinates;
the native API translates the order and biases at the binary boundary.

The previous writer started two bytes late and overwrote the first two controls.
The corrected writer preserves all seven controls, unknown EQ bytes and existing
XI/manager links. It must never paste an unparsed user-library `TACTIC.*` file
into EQ: the earlier direct-copy probe made PM99 reject new-game setup.
Mode 1 remains preserve-only; this correction is not permission to write it.

### October implementation and proof limits

`app/eq_initial_tactics.py` in the upstream editor is the canonical bounded
mode-0 reader/writer. Its deterministic tests cover the first and last state,
all seven controls, other records, invalid ranges and byte-identical reapply.
The season schema/compiler now retain eleven named slots, twenty states per
slot and explicit deployment roles. A conflicting static summary or different
native opening XI is rejected before database files are written.

The first corrected candidate changes only Stoke carrier 307 in the current
2015/16 release. It retains the first-league-fixture XI and 4-1-4-1, with
editorially inferred role-specific attack/defence anchors and small factory
movement offsets. The movements are not presented as historically sourced
manager instructions. The current playable release and the original favourite
2015 backup are not modified by candidate preparation.

The genuine runner capture `tactics_phase_verified_2015_16_20261005_i`
independently reads all 880 coordinate values and 44 phase averages from the
running game before opening Advanced Tactics. Two matching native objects
contain the exact expected 3,696-byte XI state. The visual verifier then checks
all eleven attack and eleven defence markers against the recipe averages,
within six pixels. The combined screenshot is
`.local/runlogs/pm99_runner/tactics_phase_verified_2015_16_20261005_i/screens/024_tactics_matrix_general_all_players.png`.
The attack/defend frames are `026` and `028` in the same directory. Evidence is
under `.local/contextual-tactics-v1/2015-16/stoke-candidate-v2/`.

The first attack-depth value for the goalkeeper must be zero, matching the
factory convention and measured runtime. The first pilot with 20 in that one
field failed exact live readback and was superseded, not counted as a pass.
Opening Advanced Tactics changes the display copy; exact before-display
readback is retained separately from the later diagnostic observation.

Earlier player-selection clicks at x=152 opened profile popups, rather than
selecting a player. Those follow-ball captures are not twenty-state proof.
Phase buttons also leave the pitch paint one input event behind; the runner
now uses an inert border click before each phase screenshot. No gameplay
coordinates are changed by these visual checks.

The first Save Tactics attempts did not save a file. A bounded Wine file trace
(`tactics_save_filetrace_2015_16_20261005_m`) proves `STATUS_ACCESS_DENIED`
when overwriting `Z:tactics\\TACTIC.000`: the isolated library retained the
immutable source's read-only modes. The runner now copies the complete library
into its disposable upper directory, makes only that copy writable, then
remounts it before launch. The shared install remains untouched.

Save/reload and match proof are required before registration or wider rollout.
The publisher rejects a merely unchanged library file, a reload into the
already-patched database, and a route capture without a completed match.
Mode-1 clubs and the other 25 preferred seasons remain unchanged by this pilot.

### Completed Stoke pilot: preferred release r20a

`historical-contextual-tactics-20261005-r20a` is registered for 2015/16.
Its inventory-bound lineup run `tactics_registered_lineup_2015_16_20261005_s`
attests the exact published manifest and visible Stoke team. The release is
marked technically verified, not historically complete for every club.
It changes only Stoke's grid and the two evidenced damaged control bytes:
932 changed bytes in EQ, with all players, ratings, coaches and artwork exact.
The previous release and original favourite backup are preserved. The new
playable tree is an independent copy, not writable hardlinks into either.

Proof runs:

- Initial full-state and 22-marker proof: `tactics_phase_verified_2015_16_20261005_i`.
- Native save: `tactics_save_permission_fixed_2015_16_20261005_o`.
  `TACTIC.000` changed and its final 1,760 bytes exactly match the candidate grid;
  file SHA-256 is `713f8d491b2a2b581ad352119c48d50a266c28fc95e7c68287448c21e40ddd50`.
- Old-baseline reload: `tactics_reload_correct_row_2015_16_20261005_r`.
  It starts with the unpatched database, loads the game's own saved file,
  and passes exact state/average readback and all 22 on-screen markers.
  The remote driver completed successfully; a locally interrupted wrapper's
  artifacts were recovered through the normal read-only mirror helper.
- Untouched-tactics match: `tactics_match_smoke_2015_16_20261005_p`.
  Stoke completes a 3–3 match at Everton, with no crash and one genuine
  full-time screen. This is a compatibility smoke test, not an optimisation
  or a claim of historically accurate match results.

The wrong-row negative control `tactics_reload_negative_control_2015_16_20261005_q`
loaded `ii`, not the saved `REGEV`. Its memory scan found the candidate in the
library cache, but the on-screen verifier correctly rejected the actual team
positions. A matching memory object alone must therefore never count as team
proof. Save reserves an initial row; Load lists `REGEV` in row one. The accepted
reload uses Load row one, not Save row two.

Release workspace:
`.local/contextual-tactics-v1/2015-16/historical-contextual-tactics-20261005-r20a/`.
Its compiler and completion receipts bind the candidate, source release, native
save, reload and match evidence. The current EQ SHA-256 is
`accce1d665ffb4564f48d3f8b5f7257946b90154a9e61bf422e144800eecc862`.
Run it with `./pm99-season play 2015-16`; use `--original` for the retained
original. New games use the revised opening tactics; old saves are not migrated.

Three inherited JSON evidence descriptors use compact semantic hashes while
their local files use the established pretty JSON encoding. Both encodings were
checked; their semantic content matches exactly. The publisher preserves the
files unchanged and records each hash contract explicitly rather than treating
the formatting difference as changed or lost source data.

Remaining rollout work: validate other formation topologies, author named
contextual slots from each club's own opening XI, then cascade with equivalent
byte/identity/geometry checks. No claim is made that all 26 seasons or mode-1
foreign teams have received this tactics correction.

Implementation checks: 60 focused recipe/compiler/publisher tests; 475 editor
deterministic tests passed with the Tk-dependent GUI test excluded (Tkinter is
unavailable); runner wrapper tests passed (192, one skip). The full runner suite
has seven existing failures involving stale navigation expectations, test
namespaces and missing screen-atlas fixtures. The default repository boundary
check passes; its local-extra check flags the pre-existing `upstream/.local/`.
Those unrelated worktree items were not changed or removed for this milestone.

### English formation rollout candidates

The reusable authoring step now covers all 17 formation shapes declared across
the 26 preferred seasons. It keeps players attached to their existing recipe
deployments, including midfielders deployed at fullback, and writes twenty
distinct ball states for both phases. Phase movement is editorially inferred,
not presented as historical manager instructions. Native XI order takes
precedence over recipe list order only when both contain exactly the same
eleven players. The tested Stoke pilot is retained without changing its grid.

All 26 offline candidates exist under
`.local/contextual-tactics-v1/<season>/english-rollout-candidate-v1/`.
Independent readback passed for 2,320 of the 2,392 English club-season entries,
checking 2,041,600 coordinate values. Only selected 1,760-byte EQ grids change;
all other EQ bytes, seven controls, JUG players, managers and artwork remain
unchanged. Reapplying the frozen layer produces identical bytes. The audit is
`.local/contextual-tactics-v1/rollout-offline-audit-v1.json`.

These are **candidates, not newly registered playable releases**. The existing
play commands still select their previous preferred releases, including the
completed Stoke-only r20a for 2015/16. No original backup has been overwritten.
Mode-1 foreign teams remain unchanged because their named-slot contract has
not been proved. Immutable candidate DBDAT hardlinks are upload inputs only;
never launch or edit them as a writable game installation.

There are exactly 72 blocked club-season entries, recorded in
`.local/contextual-tactics-v1/rollout-opening-slot-queue-v1.json`:

- 36 have an outfield player in native slot one and their goalkeeper later in
  the XI. For example, Stoke 2001/02 has Jurgen Van Deurzen before Gavin Ward.
  Both the recipe and compiled order carry this problem; it is not a missing
  historical squad source. Repair the lineup-order metadata and move the
  corresponding named tactical slot together, preserving player facts.
- 36 clubs in 2015/16 have reserves retaining duplicate starting-slot numbers.
  Stevenage, for example, has eleven declared starters plus four reserve
  records still numbered within 1..11. Repair reserve startup metadata after
  checking ownership, rather than guessing which duplicate the loader selects.

Next work is to close those order repairs, prove each formation family in the
runner, and publish bounded deltas with explicit sampled runtime coverage. The
Stoke-only publisher refuses a multi-club layer: one club's proof must not
silently qualify an entire batch. Do not regenerate ratings, artwork or squads
to resolve these startup-order issues.

### Opening order repair and deployment review

The subsequent repair lives in `scripts/season_opening_order_repair_v1.py`,
with final candidates named `english-rollout-candidate-v3`. It extends the
frozen v1 grids rather than regenerating squads, ratings, managers or artwork.
The compiler bug was deriving startup order from roster storage order instead
of the recipe's selected XI and substitutes. The compiler now uses XI,
substitutes, then remaining squad, and writes compact mode-0 startup order too.
A separate hash-bound `opening-order-<season>` input makes the bounded repair
replayable for the separately declared English 2015/16 recipe.

An initial hypothesis that compact reserves used a different semantic byte
was rejected. Native loader inspection and the compact field fixture agree
on the leading startup byte. Stevenage's baseline fresh game nonetheless shows
the intended eleven starters despite its reserve duplicates; the warnings do
not establish that those reserves displaced the XI in that run. The repair
gives the declared reserves unambiguous unique orders without changing facts.
Its actual runtime proof is `tactics_order_repaired_stevenage_2015_16_20261005_b`.

Moving the goalkeeper alone is insufficient where the old generated deployment
also placed players on the wrong line. The v2 Stoke 2001/02 run exposed Van
Deurzen in defence. Final v3 assigns deployments deterministically using the
existing fine-role facts and declared shape, records that inference explicitly,
and leaves the facts themselves unchanged. Its fresh-game run
`tactics_deployment_repaired_stoke_2001_02_20261005_c` passes the full native
grid and all 22 visible phase markers, with Ward first, Clarke at left-back and
Van Deurzen in midfield. V2 candidates are unpublished diagnostics, not final
releases. The earlier run with the 2015 executable is not 2001 calendar proof.

Oldham 2015/16 is the sole currently identified migrated flat `4-4-2` label
whose named coordinates encode a midfield diamond. The final recipe records
`4-1-2-1-2`, inferred from those coordinates, not a newly dated historical
formation source. This adds an eighteenth template, with its own runtime gate.

The repaired offline audit is complete for all 26 seasons and all 2,392 English
club-season entries: 72 formerly queued clubs repaired, 403 startup-order bytes
changed, and 2,104,960 coordinate values read back. Every other player byte and
every EQ byte outside the allowed grids is preserved. The immutable aggregate
is `rollout-repaired-offline-audit-v3.json` under the tactics workspace.

A separate deployment review flags 69 player-fact/deployment disagreements.
These are not 69 proven historical errors: either a dated player role or the
old inferred deployment could be wrong, particularly for players who changed
position. The complete names and recipe hashes are in
`rollout-deployment-review-queue-v1.json`. Regular season QA now reports these
as visible warnings rather than silently rewriting the facts. The startup
order queue is closed; the editorial disagreement queue is not.

All 18 formation families now have passing runtime samples, each checking
880 native coordinate values, 44 means and all 22 visible phase markers. The
coverage report is `formation-runtime-coverage-v2.json`. These samples are
bound to final candidate grids and named XIs; they are not full-match tests of
every club. The final rollout match completed successfully with the shipped
tactics preserved, no crash and no debugger activation. All 26 releases are
registered as `historical-contextual-tactics-20261005-r21a`; all 26 fresh
inventory-bound Stoke captures completed successfully, and
`./pm99-season validate all` passed for those exact releases. Run the repair with
`scripts/season_opening_order_repair_v1.py all --allow-compact-mode0` using the
season-pipeline interpreter and editor PYTHONPATH above. Passed captures can
be resumed with `scripts/season_tactics_formation_runtime_v1.py`; one sample
per shape is not gameplay coverage of every club or season. The rollout
publisher refuses missing formation or startup-repair runtime gates and
preserves at least 8 GiB free before making an independent playable copy.

The Charlton 2000/01 capture has an explicit image review because OCR returned
`Chariton Athletic` while the original screenshot visibly says
`Charlton Athletic`. Its original OCR result remains unchanged. The separate
review is bound to that exact screenshot; native-grid and 22-marker checks
remain mandatory. It is not described as an automatic OCR pass.

Visual-proof schema v2 also fixes a reporting bug: the final connected-component
index had overwritten the returned team-identity object. Verification had
checked the original header before that collision, but the old JSON summary
field was wrong. Existing screenshots and raw OCR/native evidence are retained;
new `formation-runtime-proofs-v2` reports reverify them without replaying games.
The frozen v1 reports remain diagnostic history.

The Everton 2016/17 formation capture A stopped on `TEAMS IN CHAMPIONSHIPS`.
Its full-state memory matches belong to cached team objects, not proof that
the displayed tactics screen was reached. Its failed header/pixel verification
is retained. Capture B also failed because single-line OCR included the
two-line Manager League logo. Bootstrap now uses a tighter title crop plus
the existing narrow-distance setup-page image references. It uses each page's
own Continue button, with an eight-step limit and no setup clicks on a dashboard.
Capture C reached the opening objectives page and then the Shield-result
popup, but did not reach the dashboard; it is also failed evidence. The next
capture D adds the existing positively classified Shield-modal OK action.
Some setup transitions need a second identical click before the game repaints;
each retry still requires the corresponding page or modal to be observed.
Image references assist navigation only; independent club, native-grid and
marker verification still decides whether a tactics capture passes.

Tottenham 2018/19 capture A reached Board Room after its preseason header was
missed. Its club-name and cached native-state matches did not qualify: the
mandatory attacking-marker check rejected the wrong page. The title crop now
includes the entire setup heading without the logo, and the existing full
classifier recognises the known preseason/setup pages as a fallback. Capture
B is a new run; the failed A evidence is unchanged.

User review of that failed capture also exposed a separate manager-name
presentation defect. The hash-verified factory ENT has surname `Wenger` and
display name `Arsene Wenger`, and surname `Ferguson` with display name
`Alex FERGUSON`. The old `_patch_ent_name` wrote the recipe's full name into
both fields, or into the sole compact field. The later isolated runtime probe
below proves that the championships screen reads the short/surname field.
Explicit aliases now fix that writer difference. No manager bytes were changed
by the tactics milestone itself.

The rollout resumes through the maintained commands below. The publisher
reuses an already registered exact release rather than rebuilding it; the
capture command reuses valid inventory-bound attestations. The expected
release option refuses an old preferred version instead of treating it as
evidence for the new rollout.

```bash
PYTHONPATH=upstream/pm99-skezmod-db-editor:. \
  .local/venvs/season-pipeline/bin/python \
  scripts/publish_contextual_tactics_rollout_v1.py all --register
PYTHONPATH=upstream/pm99-skezmod-db-editor:. \
  .local/venvs/season-pipeline/bin/python \
  scripts/capture_registered_season_runtime_v1.py all --execute --attest \
  --compact-evidence --expect-release-id historical-contextual-tactics-20261005-r21a
```

Regular season QA ran under `.local/contextual-tactics-v1/registered-qa-r21`.
The 25 non-legacy seasons retain their inherited duplicate-person blocker. The
2015 audit exposed a false manager-graph hash failure: unrelated tactics changed
the EQ hash although its manager edges were unchanged. QA now independently
checks every dated target's native name and exclusive owner instead of equating
whole EQ equality with manager equality. Original dated input hashes remain
mandatory. Failed reports were not registered as passes.
The original 2015 backup remains available through `--original`.

Strict historical QA is not expected to pass merely because tactics load.
The pilot reports the same inherited duplicate-person blocker already recorded
in [the independent roster review](ALL_26_INDEPENDENT_ROSTER_REVIEW_2026-10-05.md).
All 26 tactics revisions preserve the preceding recipe's player records exactly.
The duplicate guard remains enabled; failed QA reports must not be registered
as passes. Foreign preserve-only slots account for many but not all candidates,
so a blanket fallback exception would hide authored roster problems too.

The 15-example review pack is generated by
`scripts/export_tactics_spotcheck_v1.py` under
`.local/contextual-tactics-v1/spotcheck-15-20261005`. It contains 30 original,
hash-checked attacking/defending frames, three contact sheets, a clickable local
gallery and a ZIP. The existing full coverage verifier binds each sample's exact
named XI/grid to the final candidate; the pack does not pretend these are newly
launched published games or one example for each season.

Manager display candidates are separate inputs under `.local/manager-display-v2`;
the original isolated field probe remains under `.local/manager-display-v1`.
Canonical full names remain in `manager.name`;
explicit `native_names` declare the game's short/display segments. The guarded
upstream ENT name writer rejects changed preimages, wrong IDs, unknown name-block
lengths and invalid text, and preserves the biography tail. The compiler and
semantic name audit understand these explicit fields without changing historical
name-source validation. Unknown compound aliases remain queued. The actual
championships-screen field is now proved by the disposable SHORTQA/FULLQA probe:
Chelsea's trophy rows show `SHORTQA` although its full profile also contains
`FULLQA`. The original frame was inspected directly; its explicit assistant
visual review is hash-bound in `championships-field-proof-v1.json`, not relabelled
as OCR. That run later exceeded the old six-step setup retry budget; it remains
failed complete-game evidence. The budget now allows eight positively observed
steps (four stages with one paint-lag retry each), with regression coverage for
seven/eight successful steps and refusal of a ninth.

The normal 2016/17 candidate subsequently completed setup and reached Everton's
Line-Up successfully. Its unmodified trophy screenshot shows Wenger, Conte,
Klopp, Guardiola and Zidane fitting their cells. This is a new run, not a
rewritten success report from the field probe. Across all 26 candidates, 8,877
short-name changes are prepared with zero canonical-name changes; 221 foreign
alias cases remain queued, and no English alias is unresolved. Canonical name
edits that retain an unrelated old alias are rejected. The known-good delta
publisher changes only ENT name spans/lengths, preserves IDs, formats and full
biography tails, and does not regenerate tactics, players or artwork. New
manager-display releases need their own attestations; the preceding tactics
screenshots are not renamed as evidence for a different whole-game inventory.

Final readback caught an equal-row alias bug between the main recipe and the
separately hash-bound English recipe: collecting targets had retained only the
last of two equal manager dictionaries. Every affected layer now receives its
explicit alias, with a regression test and both-field binary readback. The
2015 English recipe's old carrier IDs are reconciled with all 92 already-proved
exclusive native owners; canonical names and club links are not guessed or
changed in the game. Its candidate changes 514 short labels rather than the
earlier 422, which had omitted those 92 English managers.

Publication explicitly recovers only unregistered, unattested manager-display
copies after confirming their entire game inventory differs from the source
only at the exact earlier ENT candidate. Metadata is archived with a ledger at
`.local/manager-display-v1/unpublished-recipe-binding-recovery/<season>/` before
replacement. The independent game copies are reused to avoid another large disk
allocation; this recovery never mutates a preferred release or the original
2015 backup. All 26 manager-display revisions are now preferred as
`historical-manager-display-20261005-r22a`. Normal `./pm99-season play YYYY-YY`
commands select them. There are 8,877 short-label repairs and zero canonical
manager-name changes. All published main/English recipe layers pass 17,412
short/full field checks with zero manager readback failures. The complete game
inventories, recipes, build chains and required artwork hashes also passed;
the separate full-inventory runtime attestations are not implied by those checks.

The genuine normal 2015/16 setup run
`manager_display_corrected_2015_16_20261005_b` reaches Stoke's Line-Up without
crash or debugger activation. It uses the exact shipped ENT and executable but
is a candidate-input smoke test, not a relabelled final-inventory attestation.
All 26 final r22a inventories now have their own successful Stoke Line-Up
attestations. The already valid 2000/01 and 2025/26 final-inventory proofs were
reused; the remaining 24 received fresh captures, not relabelled r21a screenshots.
Every proof binds the final manifest, complete game inventory, visible Stoke
identity and original screenshot hash. The missing-attestation rollout gap is
closed. The maintained capture command above now reuses valid proofs rather
than rebuilding games or replaying already qualified inventories. Capture used
three separately leased runner lanes and compact local evidence; complete
remote captures and failed attempts remain available. This proves fresh-game
startup and Line-Up for Stoke in every season, not full-season simulation or
live gameplay of every club.

Final `./pm99-season validate all` passes all 26 preferred r22a releases, with
zero issues. The saved result is
`.local/manager-display-v1/release-validation-r22-final-20261005.json`.
The frozen closeout is
`.local/manager-display-v1/manager-display-all26-runtime-closeout-20261005.json`;
it binds every final manifest/inventory, attestation, original Line-Up screenshot,
QA report and the three retained failed attempts to their hashes. The technical
rollout/runtime milestone is closed, while the historical QA queues below remain
open. Normal `./pm99-season play YYYY-YY` commands select these checked versions;
`./pm99-season play 2015-16 --original` retains the original fun backup.

All 26 r21a tactics versions retain their own successful fresh-game attestations.
The frozen closeout is `tactics-all26-runtime-closeout-20261005.json` under the
tactics workspace. Every r22a EQ/JUG hash is identical to its r21a predecessor,
verified in `.local/manager-display-v1/tactics-proof-transfer-all26-20261005.json`.
This transfers the exact tactics/XI proof, not whole-game gameplay coverage.
The component qualification report is `manager-display-all26-qualified-20261005.json`.

The isolated manager field screenshot validates labels only. Its bottom-right
foreign club label still overlaps its manager column, and trophy participants
are not historical qualification proof. Club-label sizing is separate work;
this ENT-only repair does not silently rename clubs or change cup entrants.
The 221 ambiguous foreign surname aliases remain unchanged and queued.
Inherited duplicate-person and the 69 deployment/fact review queues remain
open; no failed historical QA was promoted to a pass. Fresh QA of all 26 final
r22a games is retained under `.local/manager-display-v1/registered-qa-r22/`.
2015/16 passes with five explicit warnings and is the only report registered
as a historical QA pass. The other 25 fail the existing strict same-person
duplicate gate; every package-validation error is a duplicate-person candidate,
not a new manager-alias validation error. There are 171 warning entries across
the batch. All 26 calendar/runtime checks pass, with zero compiled manager,
Handling, nationality, fine-role or kit-format readback failures. Those binary
checks prove agreement with the declared recipe, not historical correctness of
every declaration or visual approval of every kit.

Three first-attempt captures (2005/06, 2009/10 and 2010/11) reached Stoke's
Line-Up without crashing but failed screen recognition after OCR probe
timeouts. Failed summaries and screenshots are retained, not edited or promoted
to passes. Each affected season subsequently passed a fresh capture against
the same final game inventory. The canonical runner now defaults each
Tesseract process to one OpenMP thread, respecting an explicit existing limit;
recognition rules and the OCR timeout remain unchanged. The failed 2009/10 run
recorded 12 probe timeouts; the new 2013/14 run recorded none. Fourteen focused
runner/OCR/setup tests pass, including preservation of timeout failure and the
parent process environment.

The latest manager, recipe/compiler, QA, reconciliation, capture and review-pack
lane passes 114 focused tests. The canonical ENT writer passes 11 deterministic
tests; the eight-step setup retry lane passes six focused runner tests. Boundary
and whitespace checks pass. Earlier tactics implementation checks include
91 focused recipe/compiler/QA/runtime
tests, 17 deterministic native order/grid tests, and eight focused setup and
tactics-identity runner tests, all passing. The wider three-file runner lane
has 259 passes, one skip and the same seven pre-existing stale-navigation or
missing-fixture failures. The root runtime-preflight lane also has a pre-existing
shell-quoting assertion failure; its release-registry checks pass. These are
recorded separately from the new gates, not presented as a clean full suite.
Repository boundaries and diff whitespace checks pass; existing dirty worktrees
and missing tracked screen-atlas fixtures remain untouched.

Runner verification now searches the complete 3,696-byte XI state. The previous
32-byte goalkeeper search reached its 16-hit cap on other clubs because the
rollout uses a shared goalkeeper envelope. The exact full-state read remains
mandatory; the search change does not weaken it. A separate hash-bound OCR
record reads both fixture-header rows and requires the requested club to occur
once, independent of generic screen classification. Header presence alone is
not proof of the displayed XI; full-grid and 22-marker checks are also required.

The first common-formation runner milestone is complete: Bournemouth 4-4-2
(`tactics_rollout_bournemouth_2015_16_20261005_h`), Sunderland 4-3-3
(`tactics_rollout_sunderland_2015_16_20261005_i`) and Liverpool 4-2-3-1
(`tactics_rollout_liverpool_2015_16_20261005_e`) each pass exact live readback
of 880 coordinates and 44 averages, visible club identification, and all 22
phase-marker checks. Each combined screenshot is
`screens/024_tactics_matrix_general_all_players.png` in its local run directory.
The hash-bound aggregate is `common-formations-runtime-proof.json` in the
2015/16 rollout candidate. This proves three sampled clubs, not all 56 candidate
clubs, all seasons, save/reload for every shape, or optimised match behaviour.

Implementation checks for this rollout: 84 focused recipe/compiler/rollout/
verifier tests, eight native writer tests, and 196 runner-wrapper tests passed
(one runner skip). Repository boundary and Markdown diff checks pass. The
repository-state check correctly reports the existing dirty worktrees and
submodule differences; this is not a clean reproducible Git handoff. The
registered 2015/16 r20a still passes `./pm99-season validate 2015-16`.

The first Bournemouth selector mistakenly chose Arsenal; its cached memory
match was correctly rejected by the pixel check. Later Bournemouth navigation
stayed on the preseason page for one extra Continue event and reached Board
instead of Tactics. Those runs are failures, not formation evidence. The runner
now retries Continue once only when the actual `Preseason for` header remains
visible; it never blindly advances a real dashboard.

To prepare or resume without rebuilding existing candidates:

```bash
PYTHONPATH=upstream/pm99-skezmod-db-editor:. \
  .local/venvs/season-pipeline/bin/python \
  scripts/season_contextual_tactics_rollout_v1.py all .local/contextual-tactics-v1
```

Existing candidate/source hashes must still match. Per-season progress snapshots
are immutable; no previous evidence is replaced. The independent audit command
uses the same arguments plus `--audit`, and deliberately refuses to replace an
existing aggregate audit report. Runtime verification selects the carrier
explicitly with `verify_contextual_tactics_runtime_v1.py --carrier-id <id>`.

## Stoke 2015 proof

The current native-92 release uses Stoke's Premier League carrier, EQ record
`307`, and the historical first-league-fixture 4-1-4-1: Butland; Johnson,
Cameron, Muniesa, Pieters; Whelan; Adam, van Ginkel, Afellay, Walters; Biram
Diouf. The static EQ grid is written before a new game and is not a loaded
`TACTIC.*` file.

The fresh new-save proof is the build-30 screenshot cited above. The fully
staged build-31 candidate carries the byte-identical EQ file, verified by
SHA-256. It also has the calendar patch (2015/16), historical kit stage, and
portrait stage applied; the tactical correction changes only the 1,760-byte
tactic interiors of the 92 EQ carriers. It remains a candidate until the 17
unresolved portraits are supplied.

Older record-314 and record-341 screenshots are retained as format-research
history only. They are not evidence for the current 2015/16 release.

### Local distributed sample: opening order and numbers

`pm99-stoke-2015-full25-lineup-v2` has a separately verified first-game
line-up write for its EQ `341` carrier.  It changes only the per-player
initial-order/shirt-number bytes and that carrier's 1,760-byte EQ grid.  The
released order is:

Butland; Johnson, Cameron, Muniesa, Pieters; van Ginkel, Whelan; Walters,
Adam, Afellay; Biram Diouf.  Given is the first substitute, so the bench has
a reserve goalkeeper.  The checked output is `opening-xi-proof.json`; it
contains all 25 record IDs, orders and shirts, plus the before/after tactical
grid hashes.  A fresh local game captured the resulting Line-Up screen as
`runtime-opening-lineup.png`.

The ordering is not derived from number, alphabetic name, raw record number,
or UI sorting.  It is an explicit initial-state field.  A season compiler must
therefore validate, for every club: carrier ownership, ordered XI, substitute
goalkeeper, shirts, primary/secondary roles, and the corresponding tactical
slot layout.

## Implementation boundary

`scripts/probe_eq_initial_tactics.py` is the disposable, structurally checked research writer used for this proof. It refuses in-place writes and asserts that a mutation cannot escape the 1,760-byte interior. The production season compiler can promote the same narrow operation after it owns a template manifest and validates every carrier/competition assignment.

The editor/season contract can now expose:

- An opening formation template for the ordered starting XI.
- A four-value defensive/attacking position for each player slot.
- A conservative option to apply that template across all 20 ball locations.

Do not expose individual ball-location editing or raw coordinates as a normal editor control yet. That needs a proper pitch editor, named ball zones, and save/reload proof for each change. It is not required to create historically credible first-game formations.

## 29 August correction: use formation bands, not literal source-dot depth

The centred build fixed PM99's axis order but still translated a source
diagram's `top` percentage directly into PM99 depth.  That is not a safe
semantic conversion.  The Stoke first-fixture source calls the shape `4-1-4-1`,
but its compact diagram places Adam, van Ginkel, Afellay and Walters near
Diouf.  The old transform therefore rendered five players in PM99's attacking
band.  It was a real, visible formation defect, not a player-position or
rating issue.

A disposable A/B run isolated only Stoke's 1,760-byte EQ tactic interior:

| Candidate | Placement rule | Result |
| --- | --- | --- |
| A — previous release | Literal source `top` to PM99 depth | Five high attacking markers. |
| B — `pm99-formation-band-v1` | Source `left` retains the named player's lateral position; source `top` orders players into the declared `4-1-4-1` lines; PM99-calibrated band depths are `130 / 210 / 280 / 400` | One striker, four distinct midfield markers, real fresh-game Advanced Tactics capture. |

The proof run is
`tactics_ab_stoke_formation_banded_20260829`, screenshot
`023_tactics_advanced_view_attack.png`.  It reaches the game Tactics screen;
the runner's route summary is marked non-success only because its generic OCR
classifier mistakes the graphics-heavy tactics page for a player profile.

`TACTICS/predef.*` files may help a human judge a visually sensible shape, but
they are not an EQ format.  They must never be copied into a team record: a
previous direct-copy probe made PM99 reject a fresh game.  The compiler now
uses a documented native-coordinate template, rather than unknown preset
bytes.

The compiler rejects ambiguous formations, requires exactly one goalkeeper and
ten declared outfield places, and records `pm99-formation-band-v1` in each
team's build manifest.  Its release audit must retain the existing byte and
pitch-range checks.  Before a new season is distributed, sample each distinct
formation shape in a fresh game; no future mass release may infer tactical
depth solely from a website diagram.
