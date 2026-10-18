# PM99 2005/06 world-season intake

Status: **source and fixed-carrier intake with a guarded candidate-identity
milestone only; not a strict V2 package, build, runtime-qualified database, or
delivered season.**  The files in this directory record the evidence safely
available for the 2005/06 workstream without inventing any approved historical
identity, rating, kit, portrait, manager, lineup, or topology fact.

## Durable records

| Record | SHA-256 | Result |
| --- | --- | --- |
| `sources/footballsquads-2005-06-world.json` | `b2fe1c02187c3a6d2c714771537e8440486169280b7ed1291e094b0f94638eac` | Canonical dated source capture for every 2005/06 cache catalogue. |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | Native-base inventory: 451 foreign carriers and 9,390 roster slots. |
| `fixed-carrier-ledger.json` | `b2b6a04d6a0c018f16c393408500c5c43eef0de4e14a550bcaf28693de169d0d` | Empty, base-locked 2005/06 authoring ledger. |
| `fixed-carrier-intake-audit.json` | `8ff5af7dfa42ed487fd348bf0faf25813220ecb381d152c60d0d11cc08b6a8f4` | Initial audit that declares the incomplete world state. |
| `foreign-carrier-candidate-proposal.json` | `57edec934a100ccb0817c31ac68cb84df3e892c969be5e7d5be10b9a4e161eae` | Deterministic, candidate-only overlay for four unambiguous capacity-compatible Spanish leads. |
| `foreign-carrier-assignment-candidates.json` | `866dce294f9029aa1495a37f406224fc04a0aea27e118daa0aa455f182a0f1bf` | Derived candidate assignment; it does not mutate the empty base assignment. |
| `foreign-carrier-assignment-candidates-audit.json` | `72f43de128bd1f16e7fa14eb4fdb18561ecc64f2b41bd79eeee051dcd32fe8e0` | Candidate-only assignment audit. |

The capture is pinned to `footballcsv/cache.footballsquads` revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` (CC0-1.0).  It preserves all 554
club squads and 15,742 player rows available in the 2005/06 cache, across 21
country catalogues.  It has not been reconciled to PM99 carrier or stable
person identities.

## Known source boundaries

The 21 captured catalogues are Argentina, Australia, Austria, Belgium, Czech
Republic, Denmark, England, France, Germany, Greece, Holland, Hungary, Italy,
Mexico, Poland, Portugal, Scotland, Spain, Switzerland, Turkey, and Ukraine.
The source capture preserves the 76 calendar-year Argentine and Mexican
Apertura/Clausura files (40 and 36 respectively) from their `2005-2006`
folder.  Their own dated source titles remain `2005` or `2006`; this is source
provenance only and must never be coerced into a PM99 competition-membership
claim.

Raw all-country cache coverage is not playable-world coverage.  The cache
does not establish that each historical club belongs to an existing PM99
carrier, nor does it establish carrier country, division, draw pools, or
membership.

All 15,742 captured player rows have `nationality` as an explicit source gap:
these older FootballSquads source files do not have a `Nat` column.  Other
retained gaps are 154 birth dates, 918 heights, 1,046 weights, 86 primary
positions, and 233 shirt numbers.  These counts are an editorial queue, not
values to infer from a later release or from baseline PM99 records.

## Candidate identity milestone

The candidate overlay contains exactly four **unapproved** leads: carrier 1
to Barcelona, carrier 2 to Deportivo La Coruña, carrier 5 to Athletic Bilbao,
and carrier 7 to Valencia.  Each is bound to one dated Spanish source capture,
is explicitly `status: candidate`, and carries blockers for independent club
identity review and the complete club/player/manager/kit/portrait/runtime
transaction.

The candidate audit counts four candidate identities and 447 unassigned
foreign carriers.  It does not alter the base assignment, which remains empty.
Carrier 3 (Zaragoza) remains unassigned because its source squad is below the
fixed carrier capacity.  Carrier 4 remains unassigned because both Real
Madrid and Real Madrid Castilla are distinct, capacity-compatible dated leads;
neither is approved or guessed.

## Fixed-carrier and executable constraints

The registry is an inventory of `pm99-gog-en-1998-clean`, not evidence of
2005/06 club identity, country, division, draw pools, or membership.  Its
audited starting state is 451 unassigned foreign carriers, zero complete
foreign roster slots, no kit decisions, no portrait/no-photo decisions, and
36 shared baseline JUG carriers.  No carrier mapping has been made.

The local-only calendar proof at
`.local/builds/2005-06-calendar/calendar-receipt.json` records a successful
2005-to-2006 patch of the known clean `MANAGPRE.EXE`: 853 approved operand
patches (50 start-year, 803 rollover-year), source hash
`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158`, and
output hash `d3dbda72bd26db7f4cd68f568ca0e22919ecacbe21b065fd1e31b63fe1d644ae`.
The executable and its receipt are local proprietary artifacts and do not
constitute a game build or runtime proof.

## Reproduce the recorded intake

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2005-2006 \
  --output seasons/2005-06/sources/footballsquads-2005-06-world.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-base-clean-fixed-carriers \
  --output seasons/2005-06/fixed-carrier-registry.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2005-06/fixed-carrier-registry.json \
  --ledger-id pm99-2005-06-fixed-carrier-intake --start-year 2005 \
  --output seasons/2005-06/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2005-06/fixed-carrier-registry.json \
  --ledger seasons/2005-06/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2005-06/fixed-carrier-registry.json \
  --ledger seasons/2005-06/fixed-carrier-ledger.json \
  --output seasons/2005-06/fixed-carrier-intake-audit.json

python3 scripts/season_candidate_identity_milestone_v1.py \
  --season-dir seasons/2005-06

python3 tools/pm99_calendar_patcher.py \
  .local/season-pipeline-v2/pm99-base-clean/MANAGPRE.EXE --year 2005 \
  --output .local/builds/2005-06-calendar/MANAGPRE.EXE \
  --receipt .local/builds/2005-06-calendar/calendar-receipt.json
```

## Blocking work before delivery

1. Independently review or explicitly reject every candidate lead.  In
   particular, resolve the Real Madrid / Real Madrid Castilla ambiguity from
   historical evidence before any carrier-4 proposal is possible.
2. Reconcile every source club, manager, and player to stable historical
   identities and fixed PM99 carriers, resolving all shared-carrier conflicts.
3. Source every required fact, rating, kit, portrait/no-photo decision, and
   opening lineup.  Stoke City is in scope, but no opening-XI evidence or
   runtime screenshot exists yet.
4. Produce a complete strict V2 package, create two independently clean,
   byte-identical builds, and qualify the exact inventory at runtime.

Until all four gates pass, this workstream has no deliverable database and no
Stoke lineup screenshot to provide.
