# Independent adversarial audit: PM99 season generation and the 26-season programme

**Reviewer model:** `claude-sonnet-5-5`. **Date:** 2026-10-17.

**Method:** read-only, using Read, Glob and Grep. I executed nothing: no tests, no hashing, no builds, no runner, no screenshots viewed. "Direct" means I read the code or data myself. "Claimed" means I read a statement in a handoff document and did not check it. Line numbers refer to files as I read them.

---

## 1. Executive verdict: **Simplify first. Stop the current completion strategy. Don't rewrite.**

- **The product you described does not exist yet.** There is no rerunnable generator for an unseen season, and the only one-command path is an explicitly provisional, foreign-clubs-only preview. The 26 games are real artefacts, reproducible from recipe at least by their own receipts. They have not been shown to be "agreed releasable".
- **The programme is not converging, and its progress meter can't show whether it is.** Candidate groups fell from 2,809 on 2026-10-07 to 2,761 at v116 on 2026-10-17, which is 48, or 1.7%. Meanwhile about 20 or more release IDs were tagged 20261017 alone. The 2,761 are *candidates*. Nobody has measured how many are defects.
- **The cause is architectural, not effort.** I found four causes:
  - duplicates are created at capture and repaired last;
  - the captured data has no provider ID or DOB;
  - allocation is bound to string-fit in fixed slots;
  - "done" is defined as exhaustive closure of an unbounded queue.
- **Keep the binary layer and the guards.** They are the best work in the repo. Replace the front door, the duplicate key, the progress meter and the state storage.
- **Further investment is justified only in this order:**
  1. Run a bounded experiment on 1990/91 (§8).
  2. Run a stratified-sample defect-rate measurement on the existing 26 (§7).
  3. Fix the single biggest operational risk (finding F1) before anything else.
- **What would change this verdict:**
  - If the sample shows few real defects among the candidates, the right move is to declare the 26 done with a gap report.
  - If the 1990/91 experiment fails two or more of its pre-registered criteria, stop the generator ambition and ship the 26 plus a gap report.

---

## 2. Ranked findings

| # | Sev | Finding | Evidence | Consequence |
|---|---|---|---|---|
| F1 | **Critical** | **The season toolchain is not in version control.** The git index contains no `scripts/season_*`, `pm99_season_*`, `pm99_simple_season_v1.py`, `build_registered_quality_release_v1.py`, `schemas/` or `seasons/`. Under `data/` only `data/README.md` is tracked. `CURRENT_WORK.md` and `data/preferred-season-releases-v1.json` are untracked. The last commit was ≈2026-09-12 (`.git/logs/HEAD:19`, epoch 1789231764). | I grepped `.git/index` with positive controls: tracked scripts such as `check_repo_boundary.py` were found, and none of the named files were. Direct. | The only copy of the code that produced the 26 games is one working tree on one machine, plus gitignored `.local/` and a personal archive host. Disk loss means the programme is unrecoverable. I can't see other branches, remotes or backups. |
| F2 | **Critical** | **Not delivered: a rerunnable unseen-season generator.** `preview` is a foreign-fixed-carrier preview. Its own docstring says English authoring "remains a reported gap" (`scripts/pm99_simple_season_v1.py:6-8`). Its report hardcodes `release_eligible: False`, `opening_lineup_count: 0`, `target_season_kit_count: 0` and native-manager fallback (`:307-326`). `build` composes from *registered preferred releases*, not from a new season (`scripts/build_registered_quality_release_v1.py:2,98-126`). Grep finds no import of the English-authoring, manager, lineup or kit layers in `preview`, `play`, `status`, `qa` or `build`. | Direct. | Nothing here handles a new season end to end. The 2001/02 "reproduction chain" is 8 hand-run steps through revision-numbered `.local` directories (`docs/2001_02_PLAYABLE_PROVISIONAL_CLOSEOUT_2026-09-07.md:81-98`). |
| F3 | **High** | **Duplicates are created at the source by design, and repaired downstream per club.** `_normalise_capture` keeps cross-club claims "for dated reconciliation" (`pm99_simple_season_v1.py:121`). It keys duplicates on a SHA-256 of the whole player row, which includes shirt number and club-specific fields (`:99-111`), so a person at two clubs usually hashes differently and goes uncounted. No build or QA entry point imports the ownership, duplicate or collision modules. | Direct (grep of imports). | Every season starts with unresolved duplicates, and fixing them is bespoke work. |
| F4 | **High** | **The generic capture has no stable identity.** `canonical_player` (`capture_transfermarkt_historical_squads_v1.py:95-117`) keeps no provider ID. `parse_squad` sets `birth_date`, `height_cm` and `weight_kg` to `None` for every row and dedupes by normalised name (`supplement_2015_ntf_with_transfermarkt.py:226,233-236`). The DOM fallback collapses same-name players by `casefold(name)` (`capture_transfermarkt_historical_squads_v1.py:156-159`). The raw cached 1990/91 Arsenal page contains 23 `/profil/spieler/<id>` links and no birth dates. | Direct, one cached page. | The IDs exist in the source and the adapter discards them. For 1990/91 there are no DOBs anywhere in the generic path. |
| F5 | **High** | **The duplicate gate is blind where it matters.** The strict gate keys on `(normalised source name, birth_date)` and returns `None` unless `birth_date` is a string (`season_package_v2.py:255-276,479-485`). Players with missing or `{"policy":"preserve-existing-mode1"}` DOBs are invisible. `./pm99-season qa` (`pm99_season_qa_v1.py`) contains no same-person duplicate check at all. | Direct. | "All 26 release checks pass" and "25 of 26 fail strict duplicates" are both true at once (`docs/ALL_26_INDEPENDENT_ROSTER_REVIEW_2026-10-05.md`). The headline pass count says almost nothing about roster quality. |
| F6 | **High** | **The progress meter doesn't measure delivered value.** `remaining_cross_club_cases: 2761` and `all_required_work_complete: false` in v116. The denominator is frozen at 2,809, and newly found Stoke 2013 late arrivals are tracked "outside the denominator" (`CURRENT_WORK.md:119`). Nineteen source-player corrections closed one case (`:123-126`). A closure script closes one case and opens two new known-wrong-fact follow-ups (`deliver_haladas2000_opening_keeper_20261017.py:72-89`). | Direct. | The number can fall while quality rises, falls or stays flat, and new findings never show as regression. |
| F7 | **High** | **The closed cases are not predominantly defects.** Counting status strings in v116, I found 34 `confirmed-fault-repaired-current-game` and 42 non-fault closures (`proved-factory-identical-system-selection-scope-exception` or `legitimate-…namesakes`). The total (76) doesn't reconcile with the headline "48 dispositions". I couldn't parse the structure. | Direct (string counts), unreconciled. | If the early, easiest closures are roughly 45% real faults, then 2,761 is neither "2,761 defects" nor "mostly noise". It is unknown. |
| F8 | **High** | **Allocation subordinates historical correctness to string-fit and slot count.** The reserve pool is "capacity-fitting" (`CURRENT_WORK.md:30-33`). A real squad member can be "capacity-trimmed" (`:58-59`). Compact displays are lossy: "Adam M.", "Jacob B." (the request and proof files). Capacity recovery is pinned to one factory JUG hash and **one** runtime pilot with one name and one screenshot (`season_same_carrier_name_capacity_v1.py:16-17,31-37,58-63`). | Direct. | Each real player must also fit a previous occupant's byte window. This is the engine of the "endless repair" pattern. |
| F9 | **High** | **Fallback policy inherits another person's facts.** New occupants get the previous occupant's height, weight, shirt number and fine roles via `preserve-existing-mode1`. The Orient proof shows this on the rows I read. A live follow-up records a retained keeper with "inherited Germany and forward fine roles 12/8" (`deliver_haladas2000_opening_keeper_20261017.py:81-84`). | Direct. | This is a standing source of visible wrongness that screenshots then find one case at a time. It is a root cause of the follow-up churn. |
| F10 | **Med-High** | **The runtime gate proves launch plus a club label.** The registry attestation requires a runner receipt "at Line-Up" and an OCR'd managed-club label (`season_release_registry_v1.py:265-313`). The managed club is always Stoke City (`data/README.md:44-48`; `deliver_haladas2000_opening_keeper_20261017.py:51`). Per-fix proof adds 1–3 player profiles. | Direct. | Runtime coverage is roughly one club plus a handful of players per delivery. |
| F11 | **Med-High** | **Several validations share the writer's parser.** The retained-transfer verification re-reads with the same `read` used to read the source (`season_retained_native_transfer_v1.py:79-81`). SOURCE replays use the same compiler primitives. The independent checks are runtime OCR of digits and age on sampled profiles. Cache integrity is "immutable-by-convention": the hash is recomputed and recorded, not checked against a pin (`capture_transfermarkt_opening_lineups_v1.py:114-144`). | Direct. | A systematic offset or parsing error would round-trip. An online run with a populated cache is silently an offline run. |
| F12 | **Medium** | **CI and tests don't protect any of this.** CI runs a boundary check and `git submodule status` only (`.github/workflows/ci.yml`). Submodules use SSH URLs (`.gitmodules`). 545 test files exist. 40 skip statements across 30 test files, and 101 `.local/` references across 46 test files, mean the tests need local data or skip. The retained-transfer tests skip when the `.local` baseline is missing (`test_season_retained_native_transfer_v1.py:6-16`). | Direct. | A clean checkout can't tell you whether anything works. |
| F13 | **Medium** | **The new composition module is not integration-ready.** `season_owned_club_composition_v1.py` has no test file and no importer. The August-signing "evidence" check is a substring test for the date string and the person's name anywhere in the article (`:129-130`). The window is hardcoded to July 1 – August 31 (`:126`). It accepts only Soccerbase hosts and paths (`:233-236`). The expected team ID is parsed by path index `[2]` (`:232`). It writes nationality at raw offset `name_end + 8` with `^0x61` (`:201`). | Direct. | It is a bespoke-input transaction engine with weak anchors, not yet a generic replacement. |
| F14 | **Medium** | **Maintainability and open-source readiness are poor.** `scripts/` has 1,664 Python files, 412 of them date-stamped, and 171 carry 20261017. The product lives in the research repo's `scripts/` despite `AGENTS.md` assigning product code to `upstream/`. There is no `LICENSE` at the root. Personal and archive-host paths are hardcoded (`season_delivery_status_v1.py:124-126`). The same-carrier capacity code hardcodes `.local/season-pipeline-v2/pm99-base-clean`. Docs reference `/home/joe/ductor/.venv`. Delivery scripts hardcode season, carrier IDs and "Stoke City". | Direct. | A second person can't run this. |
| F15 | **Medium** | **Status reporting is hard for the owner to audit.** `CURRENT_WORK.md` is 575 KB and `WORK_HANDOFF.md` is 279 KB. The first 3 hours of 10-17 take about 190 lines, and the prose is compressed, with spaces dropped ("Haladas2000followup now delivered"). The checklist is 116 copied ~450k-token JSON files. | Direct. | The headline "goal ACTIVE / PROGRESS" is not decision-grade. |

**What the lead is doing honestly, to be fair:**
- Every recent entry says "no global RC", "mechanical proof, not an approved squad", and "no game changed".
- The composition's own output says `native_files_written: false`, `publication_approved: false`.
- The 1990 closeout is candid about its gaps.
- The packaging guard `preserve_other_records` and the upstream order writers are carefully built.

My criticism is of the strategy and the instruments, not of candour.

---

## 3. Direct answers to the eight questions

**Q1. What genuinely runs from one command for an unseen season?**
- **Genuinely runs:** acquisition from Transfermarkt through a hash-recording cache, normalisation, carrier allocation, source package, deterministic editorial ratings, calendar, static compile and a clean-static audit (`pm99_simple_season_v1.py:243-301`). It is one season, once, for foreign clubs only.
- **Missing from the chain:** English authorship, target-season managers, opening XIs, kits, runtime launch, registry entry and publication.
- **Hidden prerequisites:**
  - `.local/season-pipeline-v2/pm99-base-clean` (a proprietary base tree) and `verified-base.json`.
  - A prior-season template at `.local/season-static-ingress-v1/2000-01-20260904-r2/season-package.reconciled.json` (`:51-53`).
  - A 2000-01 carrier registry and two scope files (`:47-50`). The 17-country scope is the same for every season, so a 1990 world is forced into 1998 country slots.
- **Online vs offline:** an existing cache file is trusted and never refreshed. An "online" run with a populated cache is offline for those keys, and the hash is recomputed rather than verified (F11).
- **Recipe vs binary reproducibility:** deliveries carry "complete game inventory identical" and "complete recipe identical" SOURCE replay checks (`deliver_haladas2000_opening_keeper_20261017.py:42-45`). That's strong in design, and I didn't run any of it. The standard `build` path *inherits* non-database assets by hardlinking the previous preferred game and swapping only the three DB files from the factory base (`build_registered_quality_release_v1.py:45-54`). So current games are layered children, and reconstruction from scratch is shown by SOURCE receipts rather than by the normal build.
- **1990/91 context:** the preview output itself was archived to remote storage by `archive_cold_1990_preview_20261017.py`, so I couldn't inspect the one demonstrated unseen run. The raw 1990 cache is still on disk (167+ files).

**Q2. Why do duplicates, ownership and late signings enter?**
- **Source of the problem:** annual squad capture lists players per club. Capture applies no global one-club-per-person rule. Cross-club claims are retained (F3).
- **Where the fix happens:** per club, per existing release. The repair lane is a set of separate modules (`season_common_date_ownership_v1`, `season_duplicate_ownership_plan_v1` and others) not wired into `build` or `qa`.
- **Identity joins:** name plus exact DOB, fail-closed. `unique_person` requires a unique `(normalised name, DOB)` match, "never expand initials, drop arbitrary digits or choose a homonym" (`season_historical_transfer_review_v1.py:70-85`). Provider IDs (Soccerbase, Transfermarkt `spieler/<id>`) appear only in the opening-lineup layer, with cross-provider bridging by name and DOB. Cross-provider DOB conflicts are settled by free-text reasons per person (`discard-conflicting-annual-biography` for Lawless, Widdowson and Brill in the Orient proof).
- **Loans and ownership gaps:** the ownership model has explicit undecidable statuses (`same-day-transfer-order-unresolved`, `entry-only-unverified-continuity`, `:88-107`). Loans are not a first-class concept. The code's own note is that recorded continuity is "not proof that the source contains every loan or move".
- **Is the queue a defect list or an inflated count?** Unknown, and likely a mix. The first-pass numbers (2026-10-05 review): 1,806 name-and-DOB duplicate candidates; 920 independently matched duplicate-person cases; 7,260 ownership-conflict candidates "not automatic removal instructions". Closed cases so far include many namesakes and exceptions (F7). Treat 2,761 as an unmeasured upper bound.

**Q3. The fixed-carrier premise.**
- **Proven or well-supported:**
  - Membership, country, division and draw are not in the decoded EQ/JUG/ENT payloads for one tested carrier. Valletta, EQ 2151, had zero references (`PM99_FOREIGN_TOPOLOGY_WRITER_CLOSEOUT_2026-08-30.md:68-87`).
  - Compact name windows were tested empirically, including a decompilation-derived cursor contract.
- **A negative result presented as policy:** the closeout itself says the finding "does **not** prove that the executable has no candidate-pool algorithm". The "Forbidden" rows (add or remove carriers, change league size) are a chosen conservatism (`:98-108`). No Ghidra call chain was found.
- **Counter-evidence in the repo:** 2001/02 shipped with 166 declared appended player carriers, and 2004/05 with 161. The latter needed a native-ID repair, and Stoke Line-Up passed afterwards (`2004_05_SETUP_CRASH_REPAIR_2026-10-03.md:26-28`). So appending JUG players is not impossible. I found no experiment growing a mode-1 club roster beyond its fixed row count, and I can't prove none exists.
- **Is the strategy an endless programme?** The scale of work is set by the slot-fit policy plus the inherit-from-previous-occupant fallback (F8, F9). Foreign coverage is also lost to fixed capacity. By my arithmetic from the closeout's numbers, 1990/91 placed 211 of about 258 foreign clubs (306 captured minus 48 English), roughly 82%. Only 4,608 of 7,234 captured player rows (64%) were authored.
- **Would a different policy reduce work without reopening binary research?** Probably, but I haven't tested it:
  - Choose people by sporting prominence and dated ownership.
  - Always use a deterministic display-name policy that fits.
  - Make unknown facts neutral rather than inherited (e.g. unassigned roles, code 98, if the engine tolerates it, which is unverified).
  - Score "complete" as XI + bench + a stated reserve policy.

  Caveat: removing a duplicate leaves a slot to refill. The refill candidates are a same-club annual-list member who fits, or a declared filler. So this isn't free, and it may be less accurate per case than the current per-case sourcing.

**Q4. Can one correction apply without drift?**
- **Within a season:** reasonably guarded.
  - `preserve_other_records` compares decoded payloads of all non-permitted records and the directory (`prepare_duplicate_whole_club_native_v1.py:119-125`).
  - Order writers do preimage checks, idempotent replay and a "patch escaped its selected bytes" assertion (`player_initial_order.py:62-104`).
  - SOURCE replays plus whole-tree inventory checks run per delivery.
  - Delivery scripts verify the other 25 seasons' bindings are unchanged (`deliver_haladas2000_opening_keeper_20261017.py:69-70`).
- **Weak spots:**
  - Writer and reader share a parser (F11).
  - The permitted record set is wide, and field-level drift inside it is checked only semantically.
  - Runtime spot checks are tiny (F10).
  - Evidence lives in mutable gitignored `.local/` (F1), with outside hashes recorded only inside the same tree.
  - No `test_season_owned_club_composition*` exists, and 8 retained-transfer tests cover one baseline.
  - The strict duplicate gate is bypassed by missing DOBs (F5).
- **Recoverable evidence gaps are acknowledged.** For example, Haladas controller exits are recorded as UNKNOWN and not invented (`CURRENT_WORK.md:91-95`). That is honest, and it shows the evidence pipeline depends on fragile process state.

**Q5. Is the 1990 single-run claim misleading?**
- The closeout is candid ("exploratory partial build, not a playable or historically complete release"). The risk is in the framing. Its headline says an "arbitrary pre-1999 season can be collected, normalised, rated and statically compiled in one invocation", and its last paragraph says 2001/02 "supplied the missing English opening squad, manager, formation, rating and kit layers".
- Those layers have not been generalised and wired into the same command (F2). They run from per-season hand-curated override manifests (`data/season-*-overrides-v1/`, untracked) and per-season revision directories.
- A 1990/91 preview also has no DOBs at all (F4), so the duplicate gate would be vacuous there.
- Whether English 1990/91 opening lineups and dated managers are obtainable generically is **untested**. I found no documented year floor in the adapters, and the closeout acquired none.

**Q6. Scope and stopping rules.**
- **Not bounded as defined.** The same review that gives 187,640 independently name-and-DOB-matched records also reports 127,323 records (≈42% of 301,333) with no exact same-club identity proof. It lists 57,773 broad-position contradictions, 3,108 height conflicts and 2,648 weight conflicts. All of these are "review queues, not permission to guess". Exhaustive verification isn't closable with available sources.
- **Separate these four classes explicitly:**
  - **Confirmed release blockers:** crash, wrong club or manager in a user-visible playable club, same person in two playable clubs, missing kit in a playable club.
  - **Suspected candidates:** the 2,761.
  - **Optional:** portraits (1 present / 1,085 missing among corrected slots at one point), secondary facts, small icons.
  - **Exhaustive historical verification:** not a release criterion.
- **Is progress counting measuring delivery or paperwork?** Both. Many releases, 116 checklists and about 10 evidence files per closure don't measure fixed defects. 1,430 "corrected slots" (cumulative, 2026-10-07) is a delivered-corrections measure but is not tied to a defect rate.
- **Architecture or scope creep?** Both. Each closure surfaces more (F6). That points to architecture (F3, F4, F8, F9). The unbounded definition of "done" is scope.

**Q7. Maintainability and open-source readiness.** See F1, F12 and F14. Additions:
- **Implementation-hash coupling:** `implementations={…Path(__file__)}` appears at `prepare_duplicate_whole_club_native_v1.py:130`, and similar bindings occur in about 20 files. This couples receipts to the exact source text of generic scripts, which is why the docs refer to an "implementation freeze". I didn't read each mismatch path.
- **Licensing, without inventing prohibitions:** the README repeatedly says source credit is not a redistribution licence, which is correct. The capture's `source.license` string ("public factual pages…") is a self-description rather than a grant (`capture_transfermarkt_historical_squads_v1.py:228`). Unresolved questions, none of which I assessed legally:
  - the Transfermarkt and Soccerbase terms for automated retrieval;
  - the scope of the Historical Football Kits "kind permission";
  - Wikipedia CC BY-SA text if embedded;
  - EA/SoFIFA portraits ("local use is not permission to redistribute", `data/README.md:38-42`);
  - database-right status of extracted rosters inside recipes.
- **Practical open-source shape:** publish generator code and recipes, and let users supply their own game and re-acquire sources. That means offline replay can't be shared except as recipe-level data.

**Q8. Combined composition and the existing guards.**
- **Does it replace repeated club-specific work?** It replaces club-specific *code* with club-specific *data*. The Aldershot/Orient request still hand-specifies the carrier IDs, provider team 92, `recover_move_destinations: [11043, 11054]`, a one-off Mannion `additional_moves` entry, and a declared Fowler birthday conflict (`retained-composition-request.json:3-27`). The decisions that cost the time (who goes where, which August arrivals count, DOB conflicts) are unchanged.
- **Capability demonstrated:** one in-memory preflight on one club. `native_files_written: false`, `publication_approved: false`, and "Ground/kit application, final source/identity audit, runtime and publication not performed" (`combined-native-context-preflight-proof.json`; code `:270-276`). Not delivered.
- **Is it safe to integrate now?** No, for the reasons in F13. A smaller critical path: finish that single Orient/Aldershot transaction through the *existing* publication gates if the owner wants that fix, and do not add more generic machinery until the sample (§7) shows how many clubs need whole-club composition at all. Back then, 165 repeated non-playable English clubs were cited (2026-10-06 review).

---

## 4. Claimed vs demonstrated capability

| Claim | Where | Demonstrated | Strength |
|---|---|---|---|
| Any pre-1999 season collected, normalised, rated and compiled in one command | `1990_91…CLOSEOUT` | One run for one season; foreign clubs only; 211 of ~258 foreign clubs placed; not launched; output archived, not re-inspected | Claimed + code read |
| Offline deterministic replay | `capture_transfermarkt…:12`, closeout | Replay depends on a mutable cache, with no pinned manifest check | Code read, not run |
| Recipe reproduces the binary | delivery scripts, receipts | Per-delivery SOURCE equality (full inventory and recipe) in code; standard `build` inherits assets | Code read, not run |
| 26 playable games | registry | Each reaches Line-Up in Stoke's team with an attestation, plus 1–3 profile spot checks | Code read; receipts not viewed |
| "All 26 checks pass" | review docs | The `qa` command has no duplicate-person check; strict duplicate gate fails 25 of 26 as of 10-05/07 | Direct |
| Duplicates closing | review/checklist | 1,430 corrected slots (10-07); candidates 2,809 → 2,761 (10-17); defect rate unmeasured | Direct, partial |
| Generic composition replaces club work | CURRENT_WORK 10-17 | In-memory, one club, hand-authored request, no tests, no callers | Direct |
| Single-fix isolation | handoffs | Strong at file and season level; shared-parser and thin runtime proof | Direct, partial |
| Unseen-season quality (English layers) | 2001/02 closeout | Hand-driven for one season; "playable-provisional" with 31 ambiguous ownership choices and 59 duplicate groups | Claimed |

---

## 5. Root causes vs symptoms

**Root causes**
1. Capture grain is wrong for the need. Annual squads feed ownership decisions that need dated lineups, and the capture drops IDs and DOBs.
2. Allocation is bound to byte-window fit and a fixed 18-slot shape, mixing a historical decision with a binary constraint.
3. Missing facts are filled by inheritance from the previous occupant instead of a neutral value.
4. "Done" is defined as exhaustive closure of an unbounded, unclassified queue.
5. State and code live outside version control and outside any runnable test lane.

**Symptoms**
412 dated scripts; 116 checklist copies; about 22 releases in a day; "fix one, find two"; duplicate counts; screenshot-by-screenshot discovery; status documents the owner can't audit.

---

## 6. KEEP / STOP / REPLACE

**KEEP**
- The strict recipe schema and package validator (with the duplicate-key fix below).
- Upstream native readers and writers with preimage and idempotence guards (`app/player_initial_order.py` and its tests).
- `preserve_other_records`, the fixed-carrier ledger `audit-eq`, and the registry with inventory-bound attestation.
- Fail-closed identity and ownership statuses, including the explicit "unresolved" states.
- Raw-source caching with recorded hashes, and the portrait fail-open policy.
- The honest "provisional / not release eligible" labelling in the preview report.

**STOP**
- One script per club or case (`deliver_*_2026MMDD.py`, `checkpoint_*`) as the unit of work.
- The frozen-denominator candidate checklist as the progress meter.
- Publishing a full release for one-case closures through a serial runner.
- Adding generic abstractions ahead of an acceptance test.
- Treating tests, evidence files or release counts as progress, and treating "26 checks pass" as quality.

**REPLACE**
- **Front door:** one `generate` that composes existing stages for foreign and English clubs and emits recipe, game and gap report.
- **Capture adapter:** keep provider player IDs (`/profil/spieler/<id>` is already in the page).
- **Duplicate detection and gate:** detect by same-provider ID first, then name+DOB, with an explicit "unknown DOB" bucket reported rather than skipped. Put it into `qa`.
- **Progress meter:** confirmed visible defects by class, unresolved items in a bounded gap report, and a sampled defect rate with a confidence interval.
- **State:** one tracked ledger in place of 116 copied JSON files.
- **Test lane:** a clean-checkout CI lane with small fixtures that runs without `.local` data.

---

## 7. Smallest realistic recovery plan for the existing 26 games

1. **Protect the work first (F1).** Commit and tag the toolchain, schemas, season data and the registry catalogue. Never commit proprietary binaries (per `AGENTS.md`). Record the hash of the Pi archive contents.
2. **Define the release bar with the owner**, as three tiers: blockers, gap-report items, and out of scope. Suggested default: blockers are user-visible problems in the four playable divisions (crashes, wrong club or manager, same person in two playable clubs, missing kits). Non-playable foreign duplicates go to the gap report.
3. **Measure before repairing.** Draw a *random* stratified sample from the 2,761 candidates, at least a few per season, and classify each as defect, namesake, exception or unresolvable. Closed cases so far are the easiest ones, so they can't be extrapolated. Report the rate with an interval. Do the same for a random sample of visible player facts (nationality, position, DOB) in a few playable clubs.
4. **Fix the identity key once, generically** (provider ID where present; unknown DOB reported). Re-run the duplicate audit across all 26 and compare it to the 2,761, so the new count is on a consistent basis.
5. **Apply one documented, deterministic rule** to groups that remain undecidable (for example, keep the person at the club of the first-fixture lineup or bench, otherwise leave and list). Record each decision in the gap report. Accept that this is a documented approximation for non-blocker leagues.
6. **Freeze micro-deliveries** (country, kit, position batches) except confirmed blockers.
7. **Check reproducibility across the whole set:** rebuild all 26 from recipes in one run and compare inventories. Pass or fail per season.
8. **Publish the gap report**, so "done" means "blockers closed and the remainder listed".

**Challenge to this plan:** step 5 may reduce accuracy per case compared with current per-case sourcing, and refilling vacated slots reintroduces the capacity problem. Step 3 could show a high real defect rate, which would argue for the architecture changes in §6 before more repair. I have not tested either.

---

## 8. Separate acceptance experiment: unseen season 1990/91

Pre-register all thresholds with the owner *before* running. The numbers below marked "suggested" are mine and are not derived from evidence.

**Setup:** a committed tag on a second machine or clean container, the owner-supplied base game, a declared cache tarball for the offline leg, and network access for the online leg. No 2000-01 template other than the declared carrier registry.

**Pass criteria (all must hold):**
1. **One command, zero manual edits.** A single `generate 1990-91` produces a strict-validated recipe, a game tree, a gap report and a hash manifest. No per-club script or hand-written JSON is required.
2. **Determinism.** Two offline runs in separate directories give byte-identical recipe, `JUG98030.FDI`, `EQ98030.FDI`, `ENT98030.FDI`, `MINIFOTO.PKF` and executable. An online-vs-offline diff is limited to a whitelist of timestamp fields.
3. **Accounting.** Captured = placed + dropped + removed duplicates, with a reason for every dropped club and player. Zero unexplained.
4. **Identity.** Every player row carries a provider ID. After the documented rule, zero provider-ID duplicates among placed players. The rows with unknown DOB are counted in the report.
5. **English layer.** 92 English clubs authored, each with a dated target-season manager and an opening XI/bench, or an explicit "source unavailable" entry. Suggested bar: dated manager for ≥90% and XI for ≥75%, with the rest listed. This also answers whether 1990/91 sources exist generically.
6. **Runtime.** The runner reaches Line-Up for at least three different managed clubs (not only Stoke), and at least 10 sampled player profiles match the recipe on DOB or age, nationality, position and skills via the existing OCR tooling.
7. **Blind audit.** Sample 50 English and 50 foreign players and check them against a second source not used in generation. Report the error rate with an interval. Suggested fail line: the owner picks it in advance.
8. **Clean machine.** The documented setup works from the tag, and the CI test lane passes without `.local` data.

**Fail criteria:** any manual per-club intervention; any non-determinism; unexplained loss; provider-ID duplicates remaining; runtime failure; need for club-specific code.

**Decision rule:** if two or more criteria fail after one bounded iteration, stop the generator ambition. Ship the 26 games and the gap report.

**Challenge to my own design:** provider IDs reduce within-provider duplicates but don't remove cross-provider bridging, which still needs name+DOB. The experiment may also fail simply because 1990 sources don't exist, which would be a finding about data, not about the pipeline.

---

## 9. Uncertainty and checks I couldn't perform read-only

- **Not run:** any test, hash, build, replay or runner. I verified none of the SOURCE-exactness, native-proof or attestation claims; I read the code that checks them.
- **Not viewed:** any screenshot or game binary. The Arnautovic, Kurucsai and Moore evidence is therefore "claimed".
- **Partially read:** `CURRENT_WORK.md` (lines 1–200 of a 575 KB file), `WORK_HANDOFF.md` (lines 1–120 of 279 KB), and the review doc to line 448. Compiler, `season_pipeline_v2` and most delivery scripts are unread.
- **Checklist:** v116 is the newest file (no `v117+`, `final`, `latest` or `current` variants), with UTC 2026-10-17T14:32:22 and `all_required_work_complete: false`. I extracted values by string patterns and didn't parse the structure, so the 34/42/48 status mismatch (F7) is unreconciled.
- **1990 evidence:** the preview directory is archived, so the closeout's counts (7,234 rows, 211 clubs, hashes) are unverified by me. I inspected one cached 1990 squad page only, so "no DOBs on 1990 pages" and "IDs present" generalise from that one page.
- **Git:** my "untracked" conclusion rests on the index. I can't see other branches, remotes, the ThinkPad mirror or the Pi archive.
- **Not assessed:** legal terms of any source; whether growing a mode-1 EQ roster beyond its fixed rows works; whether the engine tolerates all-unassigned fine roles; the schema's room for provider IDs; how every implementation-hash mismatch is handled; the Transfermarkt/Soccerbase availability of 1990 lineups and managers.
- **My own bias risk:** I sampled the evidence I could reach by search. The strongest quantitative claims (1.7%, 211 of ~258, 82%, 64%, the 42% unproved-same-club share) come from the lead's own documents and my arithmetic on them, not from independent measurement.
