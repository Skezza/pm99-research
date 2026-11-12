# Reusable season recipe generator — reviewed planning proposal

UTC: 2026-11-12T21:09:25.235150+00:00. Machine: joe-Vostro-3350. Source Codex session: 01a0592d-fcd5-7262-a637-743a8253d9b4.

Requested actual Claude Sonnet 5.5 planning session: `69280f98-ad91-48e3-8b7c-3796459cfd70`. Three read-only passes; permission mode `plan`, tools only Read/Glob/Grep. The lead challenged the first two plans and reviewed the final one. This is a proposal, not implementation authority, a working generate command, measured source coverage or release certification. Existing games, recipes and registrations were not changed.

The text below is Claude's final plan with explicit lead corrections to unsupported scope-count inference, a blanket compact-record write restriction, the global cutoff rule and the baseline-gap allowance. The raw, unedited final response and the two superseded plans remain under `.local/claude-generator-plan-20261112/`.

## Lead acceptance requirements

- Use all **543 Native club slots** for club coverage. The older preview's 211 authored foreign clubs does not establish why the other 240 were unauthored.
- Use **one database-wide playing-owner cutoff** per season. Country-specific source calendars and reference fixtures remain distinct. Existing authorised exceptions are data overrides. The proposed 31 August default is not a previously approved exact day, and existing unusual-season decisions must be imported.
- Use date precision as intervals: an entry known only to year/month may still certainly precede the cutoff, and an exit may certainly follow it. Exact day dates are not mandatory when all possible dates establish the same result. A window straddling the cutoff remains uncertain. Missing records do not prove no move.
- Managers must be evaluated at that same roster cutoff (or an explicit authorised exception), not blindly at a different anchor-match date.
- No whole Native family is declared unwritable from a template policy. Reuse current per-field writers and guards; this is not another binary-format investigation.
- Non-historical Native baseline clubs count within the same small mandatory-gap ceiling. They cannot provide an extra 27-club exemption.
- The build proof must account for unused as well as assigned Native player slots, prevent inherited wrong-person identities/photos from appearing as newly sourced facts, and exercise historical division counts that exceed fixed engine capacity. Such constraints need explicit dispositions and policy; a roster cannot simply shrink its denominator. This is an acceptance check, not a claim that a new engine defect has been found.
- Proposed targets of at most 20 affected people and 10 affected clubs are product goals to test, not an accuracy guarantee. Include omitted uncertain people and roster holes, not only successfully placed people. Optional fact/photo omissions do not become thousands of owner tasks.
- No new per-player/club/season modules. No claim of success until full recipe, locked replay, workbook corrections and Native/runtime proof pass. Preflight failure retains useful output but leaves the milestone incomplete.

---

# Final season recipe generator plan (supersedes my first and second plans)

This is read-only planning. I ran nothing, wrote nothing and used no ExitPlanMode. Every command below is **proposed and not currently available**.

**What this version corrects:**
- The coverage denominator is the full **543 club slots** (451 foreign + 92 English). It is no longer "clubs with a scoped source".
- "Minor" now means small absolute ceilings across all 543 slots. The earlier allowance of about 690 weak owners is withdrawn, and window-level and annual-list ownership are no longer hidden inside an "A+W" grade.
- An entry with no recorded exit is never upgraded to proven.
- A match nearest the cutoff is never an ownership tie-break, even for starters.
- Unknown managers stay unresolved fields.
- New people inherit no fine roles, portraits or prior-occupant nationality.
- Override preimage and refresh semantics are stated precisely.
- The cutoff date and the game clock are separate. 31 August is a proposed data default, not an agreed day.

---

## 0. Plain-English core

**The problem.** Today the pipeline treats "which club's squad page lists this player" as "who owned him in August". It has one dated-ownership rule, and that rule compares first-match dates between different clubs, which is not a snapshot. The front door doesn't even supply opening lineups. Wrong owners are therefore found later, one at a time.

**The fix.** Decide ownership once, up front, from dated evidence, for the full set of 543 Native club slots. The new pieces:
1. An explicit, data-driven snapshot date per season.
2. Bulk collection of squad lists, club arrivals/departures/loans, anchor-match lineups and manager histories.
3. An ownership state for **every placed person**, where "derived under a stated continuity rule" is kept apart from "unresolved".
4. A recipe that stays in the existing format, plus ledgers so that editing one thing never reshuffles other people, slots or ratings.

**What "minor gaps" means.** Across all 543 slots, I propose at most 20 people and 10 clubs needing manual action, and strict English coverage. Missing heights, weights, dates of birth and portraits can be numerous and are never manual blockers. These are proposed product targets, not facts. Nobody should promise they are achievable until the source preflight measures what exists.

**How it is judged.** The run prints achieved numbers against the limits. If any limit is missed, the output says "provisional, minor-gap claim not met" and names the blocker. A partial recipe is still useful but is not the requested generator. The milestone passes only when the limits are met **and** the offline replay, workbook corrections and Native build proof all succeed.

**Three deliverables (section 9).** D1: source and denominator preflight. D2: reusable dated-ownership assembly. D3: the full 1990/91 recipe with English and foreign clubs, a portable locked replay, workbook corrections and a Native proof. None of this rebuilds the existing 26 or blocks playing them.

---

## 1. Verified facts and their status

**Verification status.** Everything below was read in code or files. **None was replayed or run.** Exact operand counts and file claims are from reading code. The registry count was verified by the lead with read-only Python.

- **Denominator.** The fixed-carrier registry `seasons/2000-01/fixed-carrier-registry.json` has **451** carriers, all `record_mode` 1. The English fixed leagues are separate: **92** slots (20 + 24 + 24 + 24, `NATIVE_DIVISION_CARRIERS` in `season_english_fixed_carrier_authoring_v1.py`). The full Native denominator is **543 club slots**, before explicit historical replacement decisions.
- **Collector scope.** The two scope files give 29 competitions in 26 country catalogues: the core-six file (four English tiers plus France, Germany, Italy, Scotland and Spain top divisions) and the 20-country top-division file. Foreign countries each have one competition. Top-flight-only discovery misses target clubs outside those competitions; that count must be measured. The older 1990 preview left 240 foreign slots unauthored, but the split between missing scope, failed fetches and failed mapping has not been established.
- **The 1990 closeout** reports 17 catalogues, 306 clubs, 7,234 rows, and 211 foreign clubs authored. The 211 is at most 47% of 451, and it is **not** a worldwide figure. The preview report cited in that closeout was not found at its path.
- **Collection** (`capture_transfermarkt_historical_squads_v1.build_capture`) keeps name, nationality, position, shirt, height, weight, DOB, `unresolved_fields` and optional `source_identity`. It keeps no join date, loan marker, as-of date or transfer. Year routing is audited only for Brazil, Ireland, Norway and Sweden (`transfermarkt_calendar_year_policy_v1.py`).
- **Front door** (`pm99_simple_season_v1.build`) calls `build_draft` with no opening lineup or selection input. It reports `opening_lineup_count: 0`, kits 0, English not authored, `release_eligible: False`. It defaults to a hidden `.local` template.
- **`build_draft` ownership rule** (`season_source_package_builder_v1.py:850-948`): for a person claimed by two squads, the claim with the *uniquely earliest first-league-fixture date among XI-bearing rows* wins; others are excluded. Problems:
  - It compares fixture dates of different clubs, which is not a common snapshot.
  - It treats an appearance as ownership.
  - It uses no transfer evidence.
  - A person with no DOB gets the key `(name, "unknown-date")` (`:239-242`), so namesakes can merge.
  - Capacity is taken by source page order (`players[:len(slots)]`, `:987`) unless opening preallocation reorders XI first.
  - `person_id` is a hash of the raw row (`_source_person_id`, `:161-178`), so a corrected row changes identity.
- **Sourced people** have the record-level preserve policy removed (`:1084`). Unresolved secondary facts (birth, nationality, height, weight, position) get a per-field `preserve` marker and appear in `fact_fallbacks` (`_updated_facts`, `:367-391`). Shirt is always preserved. Non-goalkeeper `fine_roles` are preserved. The *preserved* value is the previous slot occupant's, which the new rules below no longer allow to stand as source-derived.
- **Ratings** (`season_editorial_ratings_v1.py`, input builder) depend on club strength (per-country table), squad status, age on `snapshot_date`, height, position and a person-ID separator. They do not depend on name, nationality or manager. `snapshot_date` is the earliest first-league-fixture date or `Y-08-01` (`season_editorial_rating_input_builder_v1.py:95`).
- **Calendar patcher** rebases 1998/1999 year operands to the target year and next. The only runtime date proven is "August of the target year" on the dashboard. **The actual day is unverified.** It does not model per-country delayed starts.
- **Managers**: `manager_at_date` (`capture_opening_manager_history_supplements_v1.py:69`) requires exactly one manager covering the fixture date and has no native fallback. English authoring needs four layers (openings, managers, kits, ratings) and emits named blockers such as `opening-xi-not-eleven-unique-players`.
- **Existing English snapshot policy names** in authoring: `at-club-on-first-league-fixture-date-exclude-later-arrivals`, `opening-window-through-august-31-exclude-september-and-later-arrivals`, `...exited-club-prior-season-squad-fallback`.
- **`transfer_interval`** (`season_historical_transfer_review_v1.py:88`) returns statuses including `recorded-entry-and-exit-bracket-fixture`, `entry-only-unverified-continuity`, `same-day-transfer-order-unresolved` and `recorded-transfer-chain-disagrees`. It takes a fixture date; it needs a version that takes the cutoff.
- **Still unread:** `season_english_mode0_package_adapter_v1.py`, `compose_season_source_captures_v1`, `season_carrier_allocation_v1` internals, the role-plan modules, the pinned DuckDB receipt, the existing 2020 handling, and any 1990 cache.

---

## 2. Denominator, expected clubs and capture

**One denominator for every percentage and gap:** the 543 expected slots, or a **fully accounted, declared, base-derived variant** that lists every difference from 543. Slots are never dropped because the collector has no source for them.

**Expected-club data (no per-club code).** A data file per season, `seasons/<season>/expected-clubs.json`, generated from the registry and the English slot lists. Each of the 543 slots carries exactly one disposition:

| Disposition | Meaning |
|---|---|
| `represented` | a real club of that season occupies the slot, sourced |
| `declared-replacement` | a data row (with evidence) says the slot represents a different real club that season |
| `declared-not-represented` | evidence (a competition membership list) says no real club fits the slot that season; the slot keeps its native baseline, labelled `native-baseline-not-historical` |
| `gap-no-source` / `gap-source-failed` / `gap-header-mismatch` / `gap-unmapped-club` | coverage gaps, counted against 543 |

An unsupported country or group is a **coverage gap against 543**, not "outside scope".

**Clubs below the top flight.** The scope files cover top flights only. For native clubs in lower divisions the plan adds **capture by stable provider club ID**:
- Direct club-season pages: squad (`kader/verein/{id}/saison_id/{y}`) and schedule (`spielplan/...`). The schedule page lists the competitions the club actually played that season, so the source competition is **derived from that season**, not fixed in a scope file.
- Competition lists, where available, **verify** season membership. They are not the only entry point.
- Season-title verification applies to every page kind (extend `require_source_title`).

**One-time provider-club crosswalk** (`club-crosswalk.json`, data):
- Native slot ↔ provider club ID, built by exact normalised match against the registry names, plus a small reviewed alias file using the existing alias mechanism in the lineup capture (`load_club_identity_aliases`).
- Each row has season ranges, so renames, mergers, successors and clubs not yet founded are expressed as data. A club absent in a season either has a declared replacement row or is a gap.
- The preflight reports how many of the 543 match automatically and how many remain. That count is a bounded one-time table, not a recurring queue.

**Replacement and unused slots.** The share of slots that stay `native-baseline-not-historical` for any reason is reported prominently and has its own ceiling (section 8). A declaration cannot become a loophole.

**D1 prints** the split of 543 into: slots whose group has a scoped top flight, slots below the top flight, and slots whose country has no scope at all. I have not inspected the per-carrier division data, so I do not state those counts here.

---

## 3. Dates (policy and game clock are separate)

1. **(a) Source-season mapping** per country and competition (existing `route_provider_year`). Unreviewed countries are assumed split-season and are labelled so.
2. **(b) Game clock.** PM99 shows August of the target year. The day is unverified. This is the game's clock, not a historical claim.
3. **(c) Roster snapshot cutoff G\*.** A **proposed data-policy default of 31 August of the start year**, in `seasons/<season>/snapshot-policy.json`, inherited from a repository default and overridable per season. Country rules choose source-season and reference-fixture mapping; they do not create two simultaneous playing owners at different cutoffs. It follows the wording of the existing "opening window through August 31" policy name, but I do not treat 31 August as an agreed exact day.
4. **(d) Observation dates.** Each match, transfer or appointment keeps its own date and a precision (`day`, `window`, `season`).

**Anchor fixture (proposed default):** each club's first league fixture dated on or after 1 August of the start year. For calendar-year countries this is a mid-season match; it **differs from the current `_first_fixture`** (earliest in the target year). The change is a declared per-country policy choice and is switchable back. **Unavoidable choice:** for calendar-year leagues, PM99 2000/01 could mean January or August squads. The default picks August because of the game clock; the preflight counts how many players moved between January and the cutoff.

**2020/21 and any delayed or unusual season:** the existing 2020 decision is **imported as data, not invented**. D2's first task is to locate it (the 2020 calendar/canonical-owner work and the registered r708 evidence) and encode it. If no machine-readable decision exists, the policy is marked `unimported` and any 2020 run is flagged. Players who joined between the cutoff and the anchor fixture and then started it are labelled `arrived-after-snapshot`, and the club's XI is incomplete with that starter named.

**What a match proves:** presence at that club on that matchday. Nothing else.

---

## 4. Ownership evidence and states

**Coverage and absence of data.**

| Situation | Meaning |
|---|---|
| Arrivals/departures list for a club-season parsed, season header verified, and the **coverage-hole test** passes | "no recorded move" is weak negative evidence. It may *extend* a dated entry or earlier presence, under the stated continuity rule only. |
| List missing, unparsed or header mismatch | **absence of data.** No inference at all. |
| List parses but the coverage-hole rate is high | the source is declared incomplete for that country-year. Dependent ownership is uncertain. |

**Coverage-hole test:** for a club-season, players seen in anchor lineups at club X who are neither on X's prior-season squad nor have an arrival row at X. A high rate means the arrivals list is incomplete. The preflight records the rate; the limit is set from it before the 1990 run.

**Ownership states** for each placed person:

| State | Required evidence | Counts as |
|---|---|---|
| `proven` | A recorded chain: dated entry at or before G\* **and** a dated exit or next move after G\*, chain consistent (existing `recorded-entry-and-exit-bracket-fixture`) | owner known |
| `derived-continuity-v1` | **Positive** presence at the same club on **both sides** of G\* (or dated entry ≤ G\* plus later presence), a verified season header, a passing coverage-hole test, and a source list showing no departure in between. Reported and audited separately. | owner derived under a named rule |
| `uncertain-entry-only` | Dated entry ≤ G\* but no recorded exit **and** no later presence. This stays the existing `entry-only-unverified-continuity`. **Missing exit data is not proof of continuity.** | **ownership uncertainty** |
| `uncertain-window` | Only a window label (e.g. "summer") for a window that straddles G\*. No day-level owner is claimed. | **ownership uncertainty** |
| `uncertain-annual` | Only an annual list entry | **ownership uncertainty** |
| `contested` | Two clubs claim, or conflicting evidence, or same-day order unresolved | **ownership uncertainty** |

Every `W`, `B` and entry-only case where the playing owner at the cutoff is uncertain counts as ownership uncertainty. No pooled "A+W" grade hides it.

**Contested starters.** A match nearest G\* is not a resolver, and a starter is not auto-assigned to the nearest-fixture claimant. The owner is left unresolved and the person is omitted from the resolved historical roster of every claimant. For each claimant whose published XI included him, the XI is marked incomplete with the starter named. The published XI is kept as a reference in `xi-reference` (club, match, date, IDs), and an explicit `assign-owner` override is offered.

**Identity rules:**
- Key by (provider, ID). Never merge across clubs by name.
- Missing DOB is not an identity failure when a strong ID and dated ownership exist.
- A source surname plus shirt is not identity proof. Link only via source IDs (lineup links carry them) or the existing reconcile path. Otherwise the claim is unresolved.
- Two provider IDs that look like one person are `possible-same-person`, a review flag, not a defect.
- Implausible age is a soft `age-outlier` flag, never a hard failure.

**Harmless versus defect.** The same (provider, ID) seen on several pages is one person observed several times. A defect is two active owners for one person at G\* in the recipe, or two persons on one carrier.

---

## 5. Squad, XI, managers, roles, portraits, nationality

**Capacity ranking:** ownership state, then XI, then bench, then dated reserves. No donors. Capacity is not taken by page order. The existing mapping rows already report `truncated_source_player_count` and `xi_capacity_satisfied` (`:1041-1051`) and are reused. Do not equate a whole-record preserve policy with an unwritable Native family. Sourced people have that policy removed. Existing guarded APIs support compact dd6360 ratings/nationality and roles; other fields have their own format limits. D2 must use a per-field capability table and report actual writable capacity, not exclude all compact carriers.

**Managers.** `manager_at_date` stays the dated source. An unknown manager is a **visible unresolved field** (`manager: unresolved` plus the source gap). A native manager record may remain in the compiled *preview* because a record must physically exist, labelled `provisional-native-preview-fallback`. It is never counted as success and never an RC default.

**Roles, portraits, nationality for newly assigned people.**
- **Fine roles are not inherited from the previous occupant, even if broadly compatible** (a new striker with an old winger's roles, a new centre-back with an old left-back's, are both "compatible" and wrong). Derive roles before Native allocation from the person's source position and lineup position text, through a data table with provenance. Precedent for default roles by broad position exists in the amendment route (D `[4,5]`, M `[9]`, F `[12]`, G `[0]`). Compatibility is necessary, not sufficient.
- Where a carrier family cannot take roles, the person gets a `role-not-writable` gap, not a silent inherited value.
- **Portrait:** a wrong old portrait must be cleared (no-image state). I have not verified the portrait link field or a writer. D2 identifies it. If no clearing writer exists, that is a named blocker.
- **Unknown nationality** uses the declared unknown representation (the proven-unsupported code `XXX` policy), never the old occupant's value presented as source. I do **not** claim the existing guards permit an unknown value in a new Native format. D2 tests what the compiler accepts. If it cannot, the field is labelled `inherited-slot-value-unsourced` and counted as an optional-fact gap.
- Keep the tested optional-unknown representations. Do not invent source facts.

---

## 6. Architecture, reuse and commands

```
S0 plan/expected clubs → S1 fetch/cache → S2 parse to observations → S3 identity
→ S4 ownership states → S5 composition (XI/bench/capacity, carrier map)
→ S6 facts/roles/ratings ledger → S7 recipe emit → S8 class checks → (separate) build
```

| Stage | Reuse | Change |
|---|---|---|
| S1 | `SnapshotCache`, calendar policy, per-file hashes | backoff, request ledger, breaker, gzip, cache outside the repo, header check on all page kinds |
| S2 | squad, lineup and manager parsers | one observation per row; add arrivals/departures/loans parser; schedule-derived competition |
| S3 | `season_player_identity_v1` | person ID from (provider, ID); row-hash ID stays for the existing 26 |
| S4 | `transfer_interval` vocabulary, `unique_person` | new pure function taking G\*, implementing section 4 |
| S5 | `build_draft` (`opening_squad_preallocation`, identity-retained slots), English authoring | `ownership_resolved` mode: pre-resolved input, any residual conflict is a hard error, not earliest-wins |
| S6 | ratings model and input builder | rating ledger; role-defaults table |
| S7 | `package_v2.validate_package`; English adapter (unread) | template derived from base plus registry |
| S8 | `audit_entries` | class checks |

No per-person, per-club or per-season code. File count is not a quality gate. The existing builder's default behaviour for the 26 stays byte-identical and its tests pass unchanged.

**Proposed commands:**
```
./pm99-season generate 1990-91 --base <owned base>               # acquisition
./pm99-season generate 1990-91 --offline --lock <lock>           # replay only
./pm99-season generate 1990-91 --refresh fetch:schedule:<id>     # explicit refresh
./pm99-season build-generated 1990-91 --base <owned base>        # separate Native build
```

The report prints counts against **543**, every disposition, the ownership states, the XI and manager lines, and "MINOR-GAP CLAIM: MET / NOT MET (limits missed: …)". A foreign-only or partial result says so in its first line.

---

## 7. Data contract, overrides, carrier map, ratings

Sidecars next to the existing recipe (`pm99-season-package-v2`): `expected-clubs.json`, `club-crosswalk.json`, `observations.jsonl`, `ownership.json`, `xi-reference.json`, `carrier-map.json`, `ratings.ledger.json`, `overrides.json`, `season.lock.json`. Raw observations are append-only.

```json
{"obs":"o-91c0","kind":"arrival","provider":"transfermarkt","player_id":"12345","to_club":"418","from_club":"1049",
 "as_of":{"date":"1990-08-20","precision":"day"},"page_sha256":"…"}
{"person":"tm:12345","snapshot":"1990-08-31","state":"derived-continuity-v1","owner":"tm:418",
 "evidence":["o-91c0","o-91d2"],"disposition":"placed","carrier":{"club":412,"slot":9031}}
```

**Stable carrier map.** A person keeps the same slot across refreshes. New people take free slots in a deterministic order. Departed people free their slot without moving anyone else. This extends the builder's identity-retained path, which today only works when a prior draft is replayed.

**Overrides** key on stable identity, never on an array index:

```json
{"id":"ov-1","target":{"person":"tm:12345","field":"owner"},"expected":"unresolved","set":"tm:418",
 "reason":"owner correction"}
```

- **First edit:** verifies the expected *current* value and hash (preimage). A stale expectation is rejected.
- **On source refresh:** the pinned manual choice is preserved. A conflict row shows the new source value beside it. The run never claims the result is consistent or correct, and never replaces a current preferred game.
- **Authorised exceptions** (such as Michael Owen→Stoke) stay as intentional override rows.
- If the target no longer exists, the override is `orphaned`: not applied, listed.
- Workbook pointers are only a UI locator verified by expected value and hash. The staged record stores the stable key, so a changed array order never retargets an edit or attaches an edit to a new person.

**Ratings contract.** Ratings are generated once per person into the ledger with an input-context hash. **Every one-field edit preserves existing ratings by default.** Name, nationality, manager, shirt and portrait changes affect no rating. A change to a rating input (DOB, height, position, club, XI membership, snapshot date) produces a preview ("would change X to Y") and is applied only on an explicit scoped `--rerate`. A model-version change is a deliberate, previewed recomputation. Manual and sourced ratings persist across refresh. A test must show a one-person change touches only that person's ledger row and slot.

---

## 8. Targets and QA

**Proposed product targets (not empirical facts).** The preflight reports what the sources allow first. Targets are fixed before the 1990 run and not lowered afterwards. All percentages use the **543** denominator.

**Mandatory action-required items** are: ownership uncertainty (`uncertain-*` or `contested`), an XI incomplete with a named starter, an unresolved identity ambiguity for a selected person, an unresolved role, an unknown manager, and any club-level gap (no squad evidence, header failure, unmapped club, no source).

| Measure | Proposed limit across the whole 543 |
|---|---|
| Action-required **people** (all kinds above) | ≤ 20 |
| Action-required **clubs** (unique clubs, any kind) | ≤ 10 (about 1.8% of 543) |
| English (92 slots) | all 92 with complete linked 11 and a dated manager; any English exception fails the claim |
| Foreign managers dated and XI complete | together within the 10-club ceiling |
| Slots left `native-baseline-not-historical` for any reason | Count within the same 10-club uncertainty ceiling, not an additional allowance. An inherited wrong historical roster or manager is not an accepted RC fallback. |
| Duplicate active owners; two persons on one carrier | 0 |
| Prior-occupant role, portrait or nationality presented as source | 0 (tested) |
| Source-header failure for a whole country or group | counts as club gaps against 543 and **cannot be reframed as minor** |

**Not limited and never manual release blockers:** missing height, weight, DOB, portraits, shirt numbers, unsupported nationality codes. They are reported counts only. `derived-continuity-v1` is not uncertainty but is reported and audited separately.

**Audit.** A frozen, versioned, seeded sample file, stratified by tier, country, calendar-year versus split season, and loan/window cases. Each check records its evidence origin. A site that copies the generating provider does not count as independent. Report counts per stratum. **No confidence interval and no statistical guarantee** (errors cluster by club, league and provider). After a fix, reuse unaffected club evidence by recipe-slice hash and re-audit only touched strata.

**Fixing a systematic bug once.** Fix the resolver or parser rule, add a regression test, replay offline for the affected stages, and re-check affected strata. No case queue for the owner.

---

## 9. Three deliverables and the binary acceptance

**D1: source and denominator preflight.**
- Produces `expected-clubs.json` for 1990/91 (all 543 slots with dispositions), `club-crosswalk.json` with its automatic-match rate, and the split described in section 2.
- Bounded request sample reporting: squad page versus first XI (late arrivals or departures present?); detailed-view join dates; club transfer pages (day dates, window labels only, or neither); DuckDB 1989–91 transfer rows (local read-only query); lineup parse rate; manager uniqueness at the anchor date; the coverage-hole rate; header coverage by country; completeness of DOB, height, nationality; an independent origin per audit country; the January–cutoff move count in calendar-year countries.
- Imports the existing 2020 decision as data.
- **Preflight exit:** all measures and the 543 accounting produced, with an evidence-based decision to proceed or a named blocker. A small sample does not prove that the full season meets the limits. **If not achievable, the result is a named blocker with the missing source, not a completed generator.**

**D2: reusable dated-ownership assembly.**
- Observation layer; the S4 resolver implementing section 4; `snapshot-policy` loader; the `ownership_resolved` mode in `build_draft`; carrier map; ratings ledger; role-defaults table; portrait and nationality reset; override loader with preimage semantics.
- Tests: synthetic chronology cases (before and after G\*, same-day, cross-country openings with different dates, calendar-year mid-season, a delayed-start season); entry-only not upgraded; missing exit data not treated as negative evidence; contested starter left unresolved with the XI reference kept; the no-DOB namesake; byte-identical rerun; a one-person change touching only that person's rows, slot and ledger entry; the existing builder tests unchanged.
- Backtest on cached 2020/21 and 2022/23 against the confirmed fixes (Casemiro, Tuanzebe, Sarkic, Kilkenny, McGrandles, Janneh and the 2013 Stoke case, where cached sources exist). **Pass:** each known case yields the corrected owner or an explicit unresolved state, with no silent wrong owner.

**D3: the full 1990/91 recipe and proof.** **Binary acceptance. Every item must be true:**
1. All 543 slots have exactly one disposition, printed. English (92) and foreign (451) are both processed. Unsupported groups are listed as gaps.
2. A cold run, then an offline replay from the lock on a **clean checkout** with only the declared base and cache bundle, produce a byte-identical recipe and sidecars. The run manifest of files read is a subset of the declared inputs.
3. The section 8 ceilings are met (≤20 people, ≤10 clubs, English strict, with every non-historical baseline slot counted within the same club ceiling). Otherwise the claim is not met.
4. No silent owners: every uncertain or contested person is listed, with zero duplicate active owners and zero prior-occupant leaks.
5. **Workbook corrections, through overrides → regenerate → build:** an owner move, a manager name and manager link correction, a name edit and an XI swap all round-trip. Only the target rows change; all other persons' ratings and slots are unchanged (diff). The corrections survive a source refresh with the conflict shown, and a stale preimage is rejected. If the compiler cannot write a manager link or a name within native capacity, that is a named blocker.
6. **Native proof:** a separate build from the base; readback of sampled fields agrees with the recipe; each correction appears in Native readback; the runner checks a few clubs (one English, one foreign, one corrected); the build is registered unpreferred; the 26 catalogue hash and the original 2015 backup are unchanged.
7. The frozen audit sample is run. Defects are reported as counts, and any confirmed wrong-owner class is fixed once and re-checked.

**If any item is false, the result is a partial recipe plus a named blocker, and the milestone is not complete.** Honest reporting is required either way; honesty does not turn a missed limit into a pass.

**Workbook scope.** The current amendment bridge covers ratings, scalars, outfield positions and written-manager names on a registered exact parent. It does not cover names, ownership, lineups or the 2015 English sidecar. For generated seasons the owner corrects through the new override kinds (`assign-owner`, `release`, `set-manager`, `set-name`, `set-xi`) in the same workbook, which regenerate and rebuild. Whether generated English clubs live in the editable recipe or a separate artifact is checked first in D3 (the adapter is unread).

---

## 10. Open-source and clean-machine proof

- Ship code, policy and scope data, expected-club and crosswalk data, recipes, locks, overrides and small synthetic parser fixtures. Do not ship site pages, base files or game binaries.
- The lock lists URLs, per-file sha256, parser/model/resolver versions, scope, policy and base hashes, and the calendar receipt hash. Another machine can refetch and compare; a mismatch is shown, not blessed.
- Source acquisition licensing, permitted automated access and redistribution are **not assessed** for any site or dataset.
- New generated seasons compile from the base (Route B). The existing 26 stay on exact-parent amendment (Route A), with every guard kept and no flattening.

---

## 11. The existing 26

- **Small benefit now:** the resolver can run read-only over a season's cached sources and list disagreements against the registered recipe by ownership state. That replaces raw candidate counts with graded ones, on demand and per season, without reopening completed cases.
- **Not regenerated:** the 26 are Native byte-deltas over inherited chains. Preserve completed typed transactions for replay. New corrections must use or extend generic amendment operations once per operation type, then supply correction data; do not add another per-person module. `ownership_resolved` is opt-in for generated seasons only.
- **No blocking:** generator failure does not touch the preferred catalogue, the 26 playable alphas or the original 2015 backup. Separate output root; no registry writes except an unpreferred candidate.
- **RC decisions** use a per-season evidence card (denominator, graded disagreements where IDs exist, a bounded audit, known issues). The generator does not certify the 26.

---

## 12. Risks, falsifiers, adversarial pass

**Biggest risks:**
1. The sources may lack day-dated arrivals, loans or complete coverage for early seasons. Then most persons stay uncertain, the ceilings fail, and the right result is "claim not met, here is the blocker".
2. The older preview left 240 foreign slots unauthored; the reasons and actual collector-scope shortfall must be measured. The crosswalk for lower-division clubs is new work whose automatic-match rate is unmeasured.
3. The anchor-fixture default and the 2020 handling are policy data that must follow existing decisions.
4. English recipe editability, portrait clearing, unknown-nationality and manager-link writers are unverified in the compiler.
5. Licensing is unassessed.

**What falsifies the design:** wrong owners in the audit sample, nondeterministic output, hidden inputs, coverage below the ceilings, or collateral changes on a one-fact edit.

**Adversarial:**
- *"20 people and 10 clubs is unreachable."* Possibly. D1 measures first. If so, the claim is not met and the blocker is named; the targets are not quietly widened.
- *"The continuity rule is a guess."* It is explicit, requires positive presence on both sides and a passing coverage-hole test, is counted separately and audited. Without those, the state is uncertain.
- *"Baseline exceptions hide missing clubs."* Every slot lacking a valid historical roster or manager counts within the same mandatory-gap ceiling; there is no extra exempt allowance.
- *"You duplicate the dated-ownership modules."* The resolver reuses their vocabulary. If the D2 backtest does not match them on the confirmed cases, it is rejected.
- *"Overrides pile up."* Repeated override types point to a resolver rule fixed once.

**Evidence that would convince us:** a cold 1990/91 run with English and foreign clubs and all 543 slots accounted for, achieved numbers printed against the ceilings, a byte-identical portable replay, owner corrections through the workbook with no collateral change, and a Native proof. Until then, "repeatable with minor gaps" is a hypothesis.