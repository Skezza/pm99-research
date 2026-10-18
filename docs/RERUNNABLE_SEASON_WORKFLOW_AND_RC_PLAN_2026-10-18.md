# Rerunnable seasons and the remaining 26-season release work

Date: 2026-10-18. Source session: 01a0592d-fcd5-7262-a637-743a8253d9b4.
Machine: joe-Vostro-3350. This is the proposed next implementation, not a claim
that a new generation command or 26 release candidates already exist.

## Outcome we actually want

Give the tool a season and an owner-supplied verified PM99 base. It acquires or
reuses historical sources, writes an editable recipe and gap report, and builds
the game where the required inputs are available. A repeated offline run uses
the same pinned inputs and produces the same recipe and native output. Editing
one fact does not recalculate unrelated facts, ratings, kits or portraits.

Keep the existing binary readers/writers, carrier constraints and safety gates.
Connect and simplify the existing stages; do not introduce another binary-format
investigation, editor redesign or club-specific executable pipeline.

## Implementation order

1. **Protect the implementation and prove the fixture lane from saved source.**
   Publish source-only snapshot branches in the research and upstream repos;
   pin the upstream commits. Keep games, caches, downloaded photographs and
   backups out of Git. Clearly distinguish the recovery snapshot from a tested
   release. A clean source tree must run the identity fixture tests without
   borrowing .local data from this working copy.
2. **Join collection and recipe authoring before compiling.** Add one proposed
   `pm99-season generate` orchestration path with explicit season, verified
   base, source scope and output directory. Reuse the present collectors,
   English/foreign authoring, manager, opening-lineup, rating and kit stages;
   there must not be a separate hidden hand-run chain after preview. Make the
   recipe-only mode useful even when some required historical input is absent.
3. **Resolve ownership before assigning native slots.** Annual squad lists
   are discovery, not evidence of August ownership. Keep provider IDs, original
   names, dated claims and evidence hashes. Use the agreed first league XI and
   bench, August cup/friendly evidence where needed, and dated August reserves.
   Later arrivals are not August squad members. Distinguish player loans from
   parent-club registration. Ambiguous ownership stays an explicit candidate;
   never silently remove a namesake or invent a replacement.
4. **Make every decision visible in the recipe.** Keep source facts, display
   aliases, deterministic editorial ratings and deliberate overrides separate.
   Attribute missing or conflicting facts. No wrong-person fine roles or
   nationality should be inherited as if they were historically sourced. Keep
   the existing tested unknown/fallback representation until an alternative is
   proven safe in the engine. Preserve continuing club names under the agreed
   policy; missing portraits are allowed. Managers still require dated evidence.
5. **Pin inputs and make stages resumable.** Record source URLs/provider IDs,
   raw snapshot hashes, source scope, base hash and implementation/rating-model
   versions in a small lock manifest. Offline mode must refuse missing/changed
   inputs, not silently fetch or bless new hashes. Each stage consumes declared
   inputs and emits deterministic outputs; restart only failed or changed stages.
6. **Compile and report, without quietly claiming release quality.** Reuse the
   native compiler and readback checks. Account for every captured club/player:
   placed, outside native scope, capacity-trimmed, duplicate claim or unresolved.
   Keep sourced XI/bench ahead of reserves. Display aliases are explicit and
   retain full source identity. A gap in a required historical input makes the
   result provisional; a successful compile alone never makes it an RC.
7. **Apply a surgical edit without collateral change.** Feed an override keyed
   to the season and stable player/club identity into the same recipe path.
   Require an expected preimage and field mask. Do not refresh source snapshots
   or rerun ratings/artwork just because a manager, DOB or nationality changed.
   Independently compare the unaffected recipe fields and native payloads.

## Bounded acceptance experiment: 1990/91

The following are proposed behaviors, not commands already implemented:

```text
pm99-season generate 1990-91 --base <owned-base> --output <new-directory>
pm99-season generate 1990-91 --offline --lock <saved-lock> --output <another-directory>
```

First prove the complete source-to-recipe path, then use one native candidate
and the serial runner when disk headroom permits. Do not overwrite the original
archived 1990 preview or any of the current 26 games.

Pass criteria:

- One invocation reaches every required authoring stage, including the English
  leagues, rather than stopping after the foreign preview. No per-club Python
  script or hand-edited intermediate JSON is needed to make it proceed.
- The report declares the full native worldwide scope, source coverage and all
  gaps. Missing English XI/manager/foreign squad evidence cannot be hidden by
  naming the foreign-only output a completed world database.
- The same pinned snapshots replay to an identical canonical recipe; two
  isolated compilations give identical native database/asset inventories.
  Runtime save files and diagnostic timestamps are outside that comparison.
- Provider identities survive, duplicate candidates and insufficient identities
  are reported, and every omitted player/club has a deterministic reason.
- A single explicit manager or nationality edit changes only its allowed recipe
  and native fields, with ratings, other actors and artwork preserved.
- Genuine runner evidence checks more than Stoke: choose representative playable
  clubs and a foreign player/kit view. Source-to-native-to-screen readback must
  agree for sampled identity, nationality, age, role and rating fields.
- Failures distinguish missing source coverage from a broken mechanism. Do not
  promise perfect historical accuracy or abandon the generator after an arbitrary
  number of failed tests. Fix the demonstrated mechanism, report the data gaps.

What is already demonstrated: the new identity path has fixture coverage, and
154 cached 1990 squad pages replay to 3718 rows with IDs intact. This is NOT yet
the above full recipe/native/runtime experiment.

## Where the existing 26 actually stand

Authoritative baseline is the local v116 release checklist, dated
2026-10-17T14:32:22Z. The cleanup/source snapshot does not change its counters.

| Area | Demonstrated state | Remaining work |
| --- | --- | --- |
| Playability | 26 preferred playable registrations, 2000/01–2025/26, existing runner evidence | Not equivalent to 26 historically approved RCs |
| Within-club duplicate queue | All 82 disposed: 34 repaired faults, 26 scope exceptions, 22 namesakes | Preserve decisions; do not reopen them |
| Cross-club duplicate queue | 48 of 2809 original candidate groups disposed | 2761 unclassified/unclosed candidates; NOT 2761 proven defects |
| Recipe/native birthday disagreements | 246 of 247 repaired | One unresolved discrepancy/source conflict; do not invent a date |
| Rating calibration | Delivered in games with SOURCE/runtime evidence | Preserve it; fix only new demonstrated faults |
| 2018 Aldershot/Orient ownership | Source-backed coupled composition proven in memory | Actual game delivery, independent readback/replay and targeted runtime proof |
| 2013 Stoke opening ownership | Three late-arrival concerns source-confirmed | Coupled owners/replacements and actual-game delivery |
| Managers/positions/squads | Many specific fixes delivered | Independent evidence gaps and detected candidates remain open; no current trustworthy confirmed-bug total |
| Kits | Named corrections delivered; native format checks and some genuine profiles exist | Global visual evidence incomplete; required selection/TEAM RATING views still missing for named cases |
| Existing photos and secondary facts | Missing portraits/unavailable facts allowed | Correct/remove confirmed wrong-person photos and source-backed wrong facts; no exhaustive enrichment |
| Final regression | Prior bound sweeps and targeted captures available | Consolidated final validation after the remaining approved changes |

The frozen manager baseline contains 5720 foreign club-season source-proof gaps;
the positions baseline includes 69 English tactical fact warnings and much
larger inherited-role candidate counts. These are OLD screening baselines,
not a current count of wrong managers or positions. Repeating those figures as
confirmed bugs or subtracting them from a completion percentage would mislead.

## How to reach RCs without another unbounded repair programme

Keep the 2809-case baseline for comparison, but create one compact current ledger
that separates: confirmed outstanding defects, reviewed legitimate cases,
unreviewed candidates, unresolved evidence and permitted gaps. Reconcile existing
delivered proof before counting anything as new. Do not silently discard foreign
teams or change the owner's worldwide scope.

Backfill source IDs from the saved source evidence only where the bridge is
proven. Apply the upstream dated-ownership/identity check to all recipes without
re-scraping completed research or regenerating unaffected games. Review genuine
remaining candidates in batches; publish corrections by affected season rather
than one full release per person. Keep the prepared 2018 and 2013 corrections
as explicit confirmed work, not lost in the candidate count.

Use native readback, exact unrelated-data comparisons and reconstruction checks
for changed seasons; use the runner for visual/runtime questions. Reuse existing
valid evidence for unchanged seasons. Finish with one consolidated all-season
regression and a per-season command/evidence/gap handoff.

There is no defensible overall percentage or completion date yet. We have
26 playable games, not 26 certified RCs, and historical ownership coverage is
still substantial work. Measuring the confirmed remainder is part of making
the next commitment honest; neither another test count nor another release
number substitutes for that measurement.
