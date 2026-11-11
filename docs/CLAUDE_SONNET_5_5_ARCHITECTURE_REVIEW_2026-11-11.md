# Revised report: PM99 season architecture and programme (supersedes the first report)

**Reviewer:** claude-sonnet-5-5, read-only (Read, Glob, Grep). I ran no tests, builds, runner or screenshots.

- **Verified** means I read the code or file myself.
- **Receipt-only** means I read a claim and did not check it.
- **Uncertain** means I could not settle it with reads.

The first report is superseded. Section 1 lists what I withdrew or changed.

---

## 1. Corrections to my first report

| # | First-report claim | Status | Correction |
|---|---|---|---|
| 1 | The viewer is a read-only annotator. | **Withdrawn.** I audited the wrong tool. | `tools/season-preset-viewer` is the parked old site (`docs/SOURCE_SNAPSHOT_AND_CLEAN_FIXTURE_PROOF_2026-10-18.md:79-83`). The real workbench is `tools/season_preset_browser.py`, `season_preset_spreadsheet.py` and `season_manifest_amendments.py`. It really can edit recipe cells (section 3). |
| 2 | The editable fields are those in `season_review_v2` (manager name only), and the owner cannot change a manager link. | **Changed.** | That limit belongs to `season_review_v2` (`:44-57`). The workbook offers a manager select on clubs (`season_preset_spreadsheet.py:255`, pointer `/clubs/i/manager_id`). Whether the compiler handles a manager swap is untested. |
| 3 | F3 and F4 (identity) are "not implemented". | **Withdrawn.** | Identity is partly implemented (section 4). My grep for a literal field name at one selector was inadequate. |
| 4 | F5, the duplicate gate is blind. | **Changed.** | `season_package_v2.py:501-507` rejects repeated provider IDs in strict mode. The name+DOB gate is as I described, and it is blind where DOB is missing. |
| 5 | "Skip `reject_factory_recipe` when a recipe is flagged canonical", or flatten the recipe to canonical. | **Withdrawn as unsafe.** | The reasons are in section 5. |
| 6 | The generic compiler "refuses most recipes". | **Overstated.** | The 50 guards fire only on recipes carrying a specific patch-artifact prefix (e.g. `season_quality_only_delta_v1.py:148-150`). I did not count how many of the 26 carry such artifacts. 2022/23 r701a certainly does. |
| 7 | Blockers are playable English clubs, and the rest is gap-report material. | **Withdrawn.** | The owner's scope is worldwide. Foreign rosters matter for transfers and identity. Wrong clubs, wrong managers and duplicate-owned players abroad are not pre-approved gaps. Missing portraits, genuinely unavailable secondary facts and unsupported nationality codes are approved gaps. |
| 8 | "RC: you decide." | **Withdrawn.** | It makes the owner the coordinator again. See section 8. |
| 9 | "I found no evidence blockers are open." | **Withdrawn.** | I had not looked at foreign clubs or the owner's screenshot. The statement carried no evidential weight. |
| 10 | Deliverable 1 was "flatten 2022/23 and match r701a's hashes with no per-case module". | **Withdrawn.** | See sections 5 and 6. |

**Kept from the first report (re-checked):**
- `build()` chains about 67 per-case reconstructors (`scripts/build_registered_quality_release_v1.py:338-617`).
- Edited ownership recipes cannot replay (`season_opening_ownership_reconstruction_v1.py:52-53`).
- Nothing in `pm99-season`, `scripts/` or `tools/` consumes the workbook output (section 3).

**Check on my own conclusions.** The reconstructor chain exists to protect Native bytes (preimage and A/B equality). That is a legitimate discipline, so "stop the chain" is the wrong advice. The right advice is to stop adding a new bespoke module per case. A generic field-edit delta that keeps the same byte-scope guards is the replacement. I inferred that the chain blocks owner edits from reading the code, and I have not run an edit.

---

## 2. Corrected executive verdict

**Does the architecture work?**
- The binary mechanics are sound.
- The workbook already gives a year-first spreadsheet over each season's current recipe, with hash-bound, stale-checked edits. That is real, and it is more than the first report credited.
- **The bridge is missing.** Edits end as "materialised-source-copies-not-promoted" (`tools/season_manifest_amendments.py:262`). Nothing turns them into a game.
- Because the 26 games are byte-deltas over their parents rather than factory compiles of their recipes, simply compiling the amended recipe cannot be assumed to work.

**Why the weeks of low visible progress:**
- Every confirmed fix became a bespoke typed transaction with full replay proof.
- There was no owner-facing edit loop.
- The queue had no class-level bound.

**What to do next:**
- Build one generic field-edit delta over the current known-good release. It consumes the workbook's amendment file and reuses the existing byte-scoped writers and guards.
- Pilot it on 2022/23, then run the same command on other seasons.
- Treat the 26 as launchable ALPHAs now, with an auto-generated status page.
- Run a fresh 1990 attempt only after the loop works. It is the only route for a new season, and the 1990 generator does not exist yet.

---

## 3. Current workbook path trace (verified by reading)

The paths below are from `tools/season_preset_browser.py` unless stated.

1. **Discovery.** `discover_preferred_release_recipe_presets(catalog_path)` (`:857-874`) loads each registered preferred release. It checks that the release manifest hash equals the catalog binding. It requires the package to be `pm99-season-package-v2`. It exposes that season's `season-package.json` as an editable preset, "Current preferred registered recipe (amendment sidecar)". It is wired at `:947-948` and `:1544` using `release_registry.CATALOG_PATH`.
2. **Spreadsheet tabs** (`tools/season_preset_spreadsheet.py:15`): players, managers, clubs and kits.
3. **Editable cells:**
   - Players: name, DOB, nationality, position (G/D/M/F), shirt number, height, weight, and every rating key (`:160-190`).
   - Managers: name only (`:219`).
   - Clubs: name, full name, division, ground, and the manager select (`:251-255`).
   - Not editable: a player's club, fine roles, lineups and club membership. The portrait and carrier columns are also locked.
4. **Stage.** `POST /api/amendments/stage` (`:1458-1475`) calls `stage_amendment` (`:1038-1065`). It reads the expected value from the immutable source, replaces any earlier staged change to the same cell, and writes `editorial-amendments/working.json` per season (`:1018`).
5. **Materialise.** `POST /api/amendments/materialise` (`:1485-1489`) calls `amendments.materialise` (`tools/season_manifest_amendments.py:210-265`):
   - It re-hashes the source.
   - It checks every `expected` value and refuses stale changes.
   - It writes amended JSON copies plus `amendment-receipt.json` under `.local/season-editorial-amendments-v1/<season>/<hash>/`.
   - It does no package validation. Pointers are replaced blindly, with no `validate_package` call.
6. **The gap.** I found no consumer of `season-editorial-amendments-v1`, the amendment schema or the receipt in `pm99-season`, `scripts/*.py` or `tools/*.py`. The only other importer is `scripts/stage_number_label_name_amendments_v1.py`, which stages amendments. `pm99-season` has no subcommand for them (`pm99-season:6-53`). The test asserts `state == "materialised-source-copies-not-promoted"` (`tools/test_season_preset_browser.py:187`). So the edit loop currently ends at a JSON file.

**What happens if an amended recipe is fed to the existing builders (code reading, not run):**
- The factory compiler `compile_package_to_tree` (`scripts/season_package_compiler_v2.py:2084`) calls `reject_factory_recipe` on 50 layers (`:2116-2211`). Any recipe carrying one of those artifacts raises an error.
- The SOURCE reconstructors compare the recipe byte-for-byte with their own re-derivation. The ownership one says "edited ownership recipe cannot use exact SOURCE replay" (`season_opening_ownership_reconstruction_v1.py:52-53`).
- Result: workbook output cannot reach `./pm99-season build` or `play` today.

---

## 4. Identity: corrected status

**Retained (verified):**
- `canonical_player` keeps an optional validated `source_identity` (`scripts/capture_transfermarkt_historical_squads_v1.py:133-141`).
- The DOM fallback reads outer-row `/profil/spieler/` links into the same field and never merges different IDs by name (`:153-203`).
- The strict parser path, `parse_squad`, carries it (`scripts/supplement_2015_ntf_with_transfermarkt.py:239-243`).
- Intake accepts and validates it (`scripts/season_source_intake_v1.py:76,163-166`).
- The package builder copies it onto the recipe player (`scripts/season_source_package_builder_v1.py:1070-1072`).
- The package schema validates it (`scripts/season_package_v2.py:459-475`).

**Stripped on purpose:** the builder removes it when a source-selection suppression quarantines a stale ID under a hold identity (`season_source_package_builder_v1.py:1117-1118`).

**Reported but not resolved:**
- `pm99_simple_season_v1.py:127-152` computes `source_identity_cross_club_claims` and writes the receipt. The comment says the claims are "reported, never resolved here".
- The same function still dedupes cross-club claims by whole-row hash (`:112,:119-124`). That is the old weakness.
- The strict package gate does reject a repeated provider ID within a recipe (`season_package_v2.py:501-507`).

**Old data:**
- The Oct 18 plan says the new identity path replays 154 cached 1990 pages to 3718 rows with IDs intact (receipt-only).
- The same plan lists backfilling source IDs into the existing recipes as future work, "only where the bridge is proven" (`docs/RERUNNABLE_SEASON_WORKFLOW_AND_RC_PLAN_2026-10-18.md:143-145`).
- I found no backfill script.
- My attempt to count `source_identity` in the 2022 r701a recipe gave inconsistent results. Whether the 26 recipes carry IDs at all is **uncertain**.
- So: the front door is partly fixed. The old 26 are probably unfixed. The identity screen can only help where IDs exist.

---

## 5. Why "skip the guards if canonical" is unsafe

I withdraw that recommendation. Evidence that a recipe is not the whole game:

- **The compiler only writes DB files.** `compile_package_to_tree` writes only `JUG98030.FDI`, `EQ98030.FDI` and `ENT98030.FDI` (`:2094-2097`, `:2338-2349`). It starts from a clean base (`_ensure_clean_database_inputs`, `:2215`).
- **The r701a build chain says what is inherited.** Its stages are `database`, `inherited-known-good-assets` and `inherited-calendar-executable` (`.local/season-release-registry-v1/releases/2022-23/…r701a/build-chain.json`).
- **Its locator binds assets outside the recipe:**
  - `native_identity_repair_path` (`…/native-player-identity-20261003-r10/identity-repair.json`).
  - `visual_patch_plan_path`, `kit_patch_application_path` and `portrait_patch_application_path`.
  - `required_file_hashes` covering `MANAGPRE.EXE`, `MINIESC`, `NANOESC`, `RIDIESC` and `MINIFOTO.PKF`.
  - Plus a long list of loose `J96*.BMP` files that must be absent.
- **Artwork stages leave the recipe untouched.** The ancestry check requires the child recipe bytes to equal the parent's and the compiler receipt to be identical (`scripts/season_visual_patch_reconstruction_v1.py:49-50`).
- **The calendar executable is an external input.** The generic build reads it from `.local/calendar-v1/{season}/MANAGPRE.EXE` (`build_registered_quality_release_v1.py:660`).
- **A nationality repair runs after compile** and changes the game outside the compile (`:641-644`).
- **Current games are byte-deltas.** For example, the ownership SOURCE path reports `compilation_mode='source-bound-opening-ownership-reconstruction-not-factory-compile'` (`season_opening_ownership_reconstruction_v1.py:68`). Delta modules patch the parent's native records so that unknown bytes survive. The quality-only delta checks "every unknown byte" (`season_quality_only_delta_v1.py:1-5,128-129`).

**Consequences:**
- A recipe does not provably carry fixed-carrier membership, unowned actors, biography bytes, unknown bytes, kits, portraits, calendar or executable patches. I did not verify English overlay precedence either.
- Matching hashes within the same chain prove nothing about a from-scratch compile.
- I did not run a factory compile of r701a, and I did not diff it against the delivered game. Whether flattening is feasible is **unknown**.
- Keep every guard until a pilot demonstrates byte-for-byte equivalence of a factory compile against a known-good game.

I did not inspect a mixed artwork and calendar release beyond the 2022 locator and build-chain.

---

## 6. Two routes compared

| | **A. Generic field-edit delta over the current known-good release** | **B. Canonical recipe compiled from a clean base** |
|---|---|---|
| Idea | Diff the amended recipe against the registered parent. Patch only the changed native fields on the parent's bytes. Inherit all assets. | Make the recipe the whole truth and compile it. |
| Reuses | `record_patch` (nationality and ten ratings, unknown bytes proven unchanged, `season_quality_only_delta_v1.py:112-130`). `preserve_other_records`. The registry and publisher (`publish_historical_role_delta_v1.py`). The role, DOB, manager and club-label plan machinery. | `compile_package_to_tree` and the base tree. |
| Evidence it works | Partly: each narrow delta works today, but as separate modules. A single generic one over arbitrary cells does not exist. | None for the current 26 (section 5). |
| Time to an owner loop | Soonest. | Unknown, and gated on an unproven equivalence. |
| Risk | Writers for fields beyond nationality and ratings (position, DOB, height, weight, shirt, names, manager link) exist only as separate bespoke modules. They need unifying behind one allowed-field table. `build()` also needs to recognise the new receipt mode, or the next bespoke delta may not accept the owner-edited release as its parent (**uncertain**). | Silent loss of bytes the recipe never held. |
| Best use | The existing 26. | New seasons such as 1990/91, where no legacy bytes exist. The front door already compiles this way. |

**Choice: Route A for the 26, Route B only for new seasons.**

**Baselines and open-source prerequisites:**
- The base tree `.local/season-pipeline-v2/pm99-base-clean` and `verified-base.json` are default inputs of the front door (`pm99_simple_season_v1.py:376-377`).
- The 26 games also depend on gitignored `.local` locators and inherited assets. The Oct 18 document says registrations "still point into local-only game/package/evidence storage" (`:73-74`).
- To open-source, ship the code, recipes, amendment files and the proof format. Users supply their own PM99 install. Source acquisition licences (Transfermarkt and others) remain unassessed.

---

## 7. Ranked, validated findings

1. **Missing bridge.** The workbook edits and stores recipe cells, but no code consumes the output (section 3). This is the main blocker to the owner finishing by hand. It is a design gap rather than a bug.
2. **The 26 are byte-delta products with a long inherited chain,** not recompilable recipes (section 5). Any bespoke fix adds a link.
3. **`build()` is a first-match chain of about 67 reconstructors** (`:338-617`). Adding a case means adding a branch. This reproduces the Oct 17 "script per case" pattern.
4. **Guard asymmetry.** The recipe-level guards correctly stop silent corruption. They also make every owner edit fail closed unless a typed module exists for it.
5. **Identity is partly fixed for new captures and unfixed for the old 26** (section 4).
6. **The Oct 18 plan is documentation, not code.** It specifies `pm99-season generate 1990-91 --base … --output …`. The dispatch has no `generate` (`pm99-season:6-53`). The front door remains foreign-fixed-carrier-only, with `release_eligible: False` and zero lineups and kits (`pm99_simple_season_v1.py:336,346`).
7. **Progress is reported through frozen denominators** (2809, 298/148, 70/81). They are accurate but do not tell the owner whether a season is worth playing. I am repeating a view I held earlier, from the same receipts.
8. **The runtime gate is thin.** It uses one managed club plus a few profiles, and I did not re-check it. This is receipt-only.
9. **Worldwide ownership and country-year errors are a real class.** Examples are wrong clubs, managers or duplicate-owned players in foreign leagues. They should be screened by class, not case by case. I do not know their rate. The 2642 unclassified candidates are neither confirmed bugs nor shown to be noise.

I did not verify the 701 delivery itself. It is receipt-only.

---

## 8. Corrected Oct 17 status table

| Oct 17 item | Status | Evidence |
|---|---|---|
| F1: toolchain untracked | **Implemented** | Per the launch context. I did not inspect the index or backups. |
| F2: no unseen-season generator | **Not implemented** | No `generate` in `pm99-season`. Front door unchanged. |
| F3: duplicates created at capture, repaired late | **Partly** | Cross-club claims are now reported by provider ID (`pm99_simple_season_v1.py:127-152`). Not resolved. Row-hash dedupe remains (`:112`). |
| F4: capture drops stable IDs | **Partly implemented** | Retained through capture, intake, builder and schema (section 4). The old 26 are not shown to be backfilled. |
| F5: duplicate gate blind | **Partly** | Provider-ID gate in strict mode. The name+DOB gate is unchanged. |
| F6: frozen-denominator meter | **Not implemented** | The Oct 18 plan proposes one compact ledger. I did not see it. |
| Stop per-case scripts | **Not implemented** | The `build()` chain grew. |
| Clean-machine test lane | **Partly** | Oct 18 reports lanes passing and one runner failure. It also says clean-machine reproducibility is not claimed (`docs/SOURCE_SNAPSHOT_…:57-59`). |
| "Simplify first" | **Partly honoured in documents, not in method** | The Oct 18 plan is sensible. Delivery continued as bespoke transactions. |

My first report said the identity fix was not done and the Oct 17 findings were largely ignored. The code shows more was done than I credited. The method of delivery, however, did not change.

---

## 9. Primary recommendation

**Build one generic "apply amendments" command on top of the existing byte-scoped writers, and use it as the owner's edit loop.**

- Input: the workbook's `working.json` or materialised receipt for a season.
- Process: diff against the preferred release's recipe. Accept only a fixed allowed-field table. Patch the parent's native records through the existing preimage-checked writers.
- Output: a new registered release candidate. It is not preferred until `--register`.
- Anything outside the table fails with a clear message. It does not become a new module.

**Preserve:** the compiler, writers, `preserve_other_records`, the registry and attestation, the workbook, the runner and every existing guard.

**Do not:** remove guards, flatten recipes, or add another bespoke module for a case this command can express.

**Smallest safe boundary:** player scalar cells (rating, position, nationality, DOB, height, weight, shirt, name) first. Then manager name and club-name cells. Defer the manager link, lineups, membership and fine roles. They have no generic writer yet.

---

## 10. Next three deliverables

**D1. Amendment-apply pilot on 2022/23 (one season, one command)**

- **Pass:**
  - A player position and rating edit, plus a manager name edit, made in the workbook produce a new release candidate.
  - The native diff against r701a contains only the declared fields. Every other byte, identity and asset is identical.
  - The release launches to Line-Up and the three edits are visible in game.
  - The same edits applied twice give identical output.
  - A stale or unsupported edit is refused with a clear reason.
- **Fail:** any other byte changes, any guard is weakened, or a new per-case module is needed.

**D2. Owner loop and rollout**

- **Pass:**
  - The owner plays 2022/23, edits up to ten cells in the workbook, and runs one command to see them in game, with no developer step.
  - The same command then works on two other seasons from different eras, with no new per-season code.
  - An auto-generated status page lists, for each of the 26: launch command, last attestation, accepted gaps, and results of automated class-level screens (provider-ID duplicates where IDs exist, country-year plausibility, manager-club mismatch).
- **Fail:** the owner has to ask for a module, or the status page needs hand-written content.

**D3. Fresh 1990/91 attempt (time-boxed, after D1)**

- **Pass:**
  - A clean checkout and the owner's base produce a compiled foreign-carrier preview.
  - Provider IDs are present, cross-club claims are listed, and every omitted club and player has a reason.
  - The run is deterministic from a saved lock.
  - The English gap is declared.
- **Fail:** it needs a per-club script or a hidden `.local` template, or output differs between runs.

**Stop-conditions:**
- If D1 needs a new bespoke module for a basic field edit, stop and re-plan the boundary.
- No new `season_*_v1.py` case modules except for a defect the generic command cannot express and the owner has seen in play.
- No classification queue longer than one pass of automated class screens.

---

## 11. Alpha, RC and acceptance

- **ALPHA:** it launches and reaches Line-Up with attestation, and its gap list is generated automatically. It is not an acceptance claim.
- **Proposed engineering acceptance for RC (testable by the toolchain):**
  1. Release and playable validation pass.
  2. No provider-ID duplicate owners in any recipe that carries IDs.
  3. No managed-club or manager-club mismatch in the automated screens.
  4. A sampled player-fact readback matches source for a fixed sample across leagues, including foreign.
  5. The sample defect rate is reported with its interval.
- **Owner's part:** a final gameplay spot check of a few clubs, not project management.
- **Not approved as gaps:** wrong foreign clubs, wrong managers and duplicate-owned players. Approved gaps are missing portraits, unavailable secondary facts and unsupported nationality codes.
- I do not give a completion percentage.

---

## 12. What would falsify this recommendation

- The pilot shows the existing writers cannot patch position, DOB, height or weight without a per-case module.
- Applying an owner-edited release as a parent breaks the existing bespoke deltas, or `build()` cannot accept the new receipt mode.
- A one-off factory compile of r701a, diffed against the delivered game, turns out to match byte-for-byte. In that case Route B becomes viable and simpler.
- The automated class screens show a high rate of systemic foreign errors. In that case identity and country-year repair move ahead of the editing loop.

## 13. Unexecuted checks and uncertainties

- I did not run any test, build, edit or replay. I did not execute the workbook.
- I did not open the browser HTML, so the UI behaviour is read from Python only.
- I did not verify whether the manager select produces a valid Native result.
- I did not count how many of the 26 recipes carry guarded patch artifacts, or provider IDs.
- I did not inspect a mixed kit, portrait and calendar release beyond the 2022 locator and build-chain.
- I did not check `build()`'s handling of an owner-edited parent.
- I did not check CI, the `pm99-season qa` duplicate checks, licences, or the owner's screenshot.


---

## Lead verification and handoff

Saved 2026-11-11T19:54:11.600683+00:00 on joe-Vostro-3350. Source Codex session: 01a0592d-fcd5-7262-a637-743a8253d9b4. Actual Claude Code session: 9b7bdc77-1c70-45e0-b21d-244d23554221. Both initialization and assistant messages identified `claude-sonnet-5-5`. Two read-only passes made98Read/Glob/Grep tool calls. No reviewer code execution, build, runner, repository edit or release publication occurred. The initial report is retained as superseded under `.local/claude-review-20261111/attempt-20261111T194106093467Z/review.md`; the body above is Claude's corrected final report, unchanged.

The lead checked the current workbench discovery, amendment staging/materialisation, CLI build dispatch and exact-replay guard paths directly. The central missing edit-to-game bridge is supported by those code reads. The initial review had audited a parked viewer and missed newly retained provider IDs; both errors were challenged and corrected, along with the unsafe suggestion to bypass factory-compile guards and the unjustified English-only release scope.

One uncertainty was settled after Claude finished: a read-only scan of all26preferred packages found562player records carrying `source_identity` out of299015total recipe-player records; the current2022/23 package has64such records out of11641. This is field-presence coverage, NOT a defect rate, and includes inherited Native/player records rather than only newly sourced people. Other internalpersonIDs exist; absence of a providerID does not establish a duplicate. Raw counts are retained in `.local/claude-review-20261111/preferred-provider-identity-coverage.json`. The precise statement is therefore **sparse backfill**, not 'the old26have noIDs'.

### Recommended next milestone

Keep every current playable release and the original2015backup. Do not restart the game/database implementation, remove safeguards or silently narrow worldwide scope. Connect the existing spreadsheet's hash-bound amendments to one reusable baseline-preserving apply/build route. Prove one position edit, one rating edit and one manager-name edit against2022/23, with declared Native field changes only, deterministic repeatability, stale-input rejection and genuine runner confirmation. Then demonstrate that exact same route on two other seasons without per-season code. Manager links, fine roles, lineups and membership need explicit supported-field handling before claiming the workbook can finish ALL editorial work; the initial pilot is not that claim.

Only after that demonstrated owner loop should the next generation milestone be an unseen1990season from locked source inputs, clearly reporting missing coverage. Existing raw capture and provider-ID work should be reused. Broad candidate queues remain evidence/backlog, not an assertion that every candidate is a release-blocking defect. Confirmed worldwide identity/ownership, manager and country-year errors still matter and require bounded class-level handling; this review does not sign off their correctness or declare the26RCscomplete.

No implementation was authorised or performed by the reviewer. No game, recipe, release binding or checklist count changed during this audit.
