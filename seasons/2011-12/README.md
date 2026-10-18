# PM99 2011/12 all-country world intake

Status: **canonical source/fixed-carrier intake plus a candidate-only identity
milestone; not a strict V2 package, build, runtime-qualified database, or
delivered season.** These records preserve the dated evidence available for
the workstream without claiming an approved club identity, rating, manager,
kit, portrait, opening lineup, or competition-topology fact.

## Durable evidence

| File | SHA-256 | Purpose |
| --- | --- | --- |
| `sources/footballsquads-2011-12.json` | `e3f291d557b6411176d6ebbd6d71c55472184113e389bf5c2182daec2c8bf991` | Canonical dated squad capture. |
| `fixed-carrier-registry.json` | `e2671c63245f71953bb15eb00f0595c1d11c3abf14fcab3538f4047b77cd0157` | Native-base inventory of 451 foreign fixed carriers and 9,390 roster slots. |
| `fixed-carrier-ledger.json` | `f13b90983af256dc601ea7ff10645d4482816e7a748c486644805d35628a3f37` | Empty, base-locked 2011/12 authoring ledger. |
| `fixed-carrier-intake-audit.json` | `5ce4881c6d966a0cc94d45fb2b495b880d1ba0d87ee81661e1dca4d648f2478f` | Deterministic initial coverage audit and explicit blockers. |
| `foreign-carrier-candidate-proposal.json` | `02794c616ec4ba86766c06ffe2dbe048ea041a505bab28e07774313c9e1c07b1` | Five deterministic, candidate-only identity leads. |
| `foreign-carrier-assignment-candidates.json` | `0211f94d5e803a9974c78d2afd051ad286b74f0f65eee0b56f27d7f68f22f164` | Derived candidate ledger; the base assignment is unchanged. |
| `foreign-carrier-assignment-candidates-audit.json` | `e8b1783c6a1594456c1020ed7a40d2b57101c975c740f8b8a4093b1639d7ee41` | Candidate coverage audit: 5 leads and 446 unassigned carriers. |

The source capture is pinned to `footballcsv/cache.footballsquads` revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` under CC0-1.0. It records 569
usable club squads and 17,203 player rows in 32 competition catalogues across
22 country catalogues. This broad source inventory is not evidence that these
clubs belong to existing PM99 carriers or that it is safe to change country,
division, draw-pool, or membership topology.

## Source boundaries

The cache contains 570 candidate 2011/12 club files. One is intentionally
excluded from the usable capture and retained in `blocked_sources` with its
source hash: `switz/2011-2012/superl/neuxamax.txt` contains no current-squad
CSV section. No substitute roster has been inferred.

The capture records 619 player rows with unresolved supplied facts: 68 birth
dates, 532 heights, 594 weights, and 27 shirt numbers. Nationality and
primary position are present for the captured rows, but every remaining gap
requires an identity-safe contemporary source before it can enter a package.
Managers, ratings, kits, portraits/no-photo decisions, and opening lineups
are not supplied by this capture and have not been invented.

## Fixed-carrier and executable constraints

The registry is a capacity and binary-layout record for
`pm99-gog-en-1998-clean`, not historical evidence of 2011/12 club identity.
Its audit records 451 unassigned foreign carriers, zero complete foreign
roster slots, no kit decisions, no portrait/no-photo decisions, and 36 shared
baseline JUG carriers. The audit therefore reports
`world-content-incomplete` and `baseline-shared-player-carriers`; no approved
carrier mapping has been made.

## Candidate-only foreign identity milestone

The reviewed Spanish host queue has six unassigned carriers: five have one
capacity-compatible source-name lead, while F.C. Barcelona has two. The
guarded candidate milestone derives only the five unambiguous leads, all with
`status: candidate`:

| Carrier | Baseline label | Candidate source club |
| --- | --- | --- |
| 2 | R.C. Deportivo | Deportivo La Coruña |
| 3 | R. Zaragoza | Zaragoza |
| 4 | Real Madrid C.F. | Real Madrid |
| 5 | Athletic Club | Athletic Bilbao |
| 7 | Valencia C.F. | Valencia |

Carrier 1 remains unassigned. Its F.C. Barcelona name-token lead is ambiguous
between `Barcelona` and `Barcelona B`; both dated squad rows meet the existing
26-slot capacity. The proposal deliberately does not choose either one.

The derived ledger records five candidate, not approved, identities and 446
unassigned foreign carriers. Every candidate retains the blockers for an
editorial carrier-identity approval and a complete club/player/manager/kit/
portrait/runtime transaction. It writes neither PM99 content nor topology, and
does not satisfy a release gate.

The local-only calendar receipt at
`.local/season-2011-12/calendar/calendar-receipt.json` records the safe
2011-to-2012 calendar patch of the verified base `MANAGPRE.EXE`: 853 approved
operand patches, input SHA-256
`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158`, and
output SHA-256
`79ca52e83a7973bc4da7bbd1b095a414bf82db7b53bf22749fe19c55c8a17d8e`.
This is calendar eligibility only, not a database build or runtime proof.

## Stoke City

The capture contains a 31-player Stoke City squad in the English Premier
League source file `eng/2011-2012/faprem/stoke.txt` (source SHA-256
`afd7ba7c9d9a125e795ad0824046bf85f3ff7df0bf6fb5c347d3e186d40602aa`). It
does not establish an opening starting XI. There is no reliable runtime lineup
screenshot: no complete, validated 2011/12 build exists, and a screenshot
from the baseline or an incomplete build would not be evidence for this
season.

## Reproduce the recorded intake

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2011-2012 \
  --output seasons/2011-12/sources/footballsquads-2011-12.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-2011-12-fixed-carriers \
  --output seasons/2011-12/fixed-carrier-registry.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2011-12/fixed-carrier-registry.json \
  --ledger-id pm99-2011-12-world-ledger --start-year 2011 \
  --output seasons/2011-12/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2011-12/fixed-carrier-registry.json \
  --ledger seasons/2011-12/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2011-12/fixed-carrier-registry.json \
  --ledger seasons/2011-12/fixed-carrier-ledger.json \
  --output seasons/2011-12/fixed-carrier-intake-audit.json

python3 tools/pm99_calendar_patcher.py \
  .local/season-pipeline-v2/pm99-base-clean/MANAGPRE.EXE --year 2011 \
  --output .local/season-2011-12/calendar/MANAGPRE.EXE \
  --receipt .local/season-2011-12/calendar/calendar-receipt.json

python3 scripts/season_candidate_identity_milestone_v1.py \
  --season-dir seasons/2011-12

python3 scripts/foreign_carrier_candidate_proposal_v1.py \
  --registry seasons/2011-12/fixed-carrier-registry.json \
  --source-capture seasons/2011-12/sources/footballsquads-2011-12.json \
  --assignment seasons/2011-12/foreign-carrier-assignment.json \
  --queue seasons/2011-12/foreign-carrier-candidate-queue.json \
  --proposal seasons/2011-12/foreign-carrier-candidate-proposal.json
```

## Delivery blockers

1. Reconcile every source club, manager, and player to stable historical
   identities and existing fixed PM99 carriers, resolving all shared-carrier
   conflicts, the Barcelona/Barcelona B ambiguity, and the unavailable Swiss
   squad without inference.
2. Evidence every required player fact and rating, kit, portrait/no-photo
   decision, manager, and opening lineup.
3. Complete a strict V2 package; create two clean byte-identical builds;
   validate release hashes; and qualify the exact inventory at runtime.
4. Capture a Stoke City runtime starting-XI screenshot from that exact
   qualified release and record its safe local path and SHA-256.

Until every gate passes, this directory is an auditable intake, **not a
delivered database**.
