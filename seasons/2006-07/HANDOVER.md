# PM99 2006/07 all-country intake

Status: **source and fixed-carrier intake complete; not a strict V2 package,
build, runtime-qualified database, or delivered season.**  The all-country
source capture establishes a reproducible research baseline.  It does not
claim that every source catalogue belongs in PM99, nor that a PM99 carrier is
the corresponding historical club.

## Durable evidence

| File | SHA-256 | Purpose |
| --- | --- | --- |
| `sources/footballsquads-2006-07.json` | `0e0324156a57763e4196b702d6b12ebcaa5c64c200a37079a0ed3b4a26cab566` | CC0 historical squad capture. |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | Read-only native-base foreign carrier inventory. |
| `fixed-carrier-ledger.json` | `a128f78fe68c840231bcd87ff9f8a4ff13d3f234f650f79df9ecedd0a74a0b5a` | Empty, hash-locked 2006/07 authoring ledger. |
| `fixed-carrier-intake-audit.json` | `8d7c55a8121b2b70998224077f85762132b8f0ca49a0ce155748b5add90ef7da` | Initial coverage audit and explicit blockers. |

The capture is pinned to `footballcsv/cache.footballsquads` revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` under CC0-1.0.  It records 554
club squads, 16,212 player rows, 31 competition catalogues, and 21 country
catalogues.  This is a broad dated source inventory, not an inferred PM99
competition topology.

## Source gaps and release blockers

Every captured row lacks a nationality field in this source revision.  The
capture retains this gap instead of guessing: 16,212 nationality facts remain
unresolved.  Other recorded fact gaps are 152 birth dates, 1,086 heights,
1,184 weights, 45 primary positions, and 124 shirt numbers.

The native carrier ledger deliberately assigns no historical content before
reconciliation.  Its audit reports all 451 foreign carriers unassigned, zero
complete player slots, and 36 shared baseline player carriers.  It reports
the `world-content-incomplete` and `baseline-shared-player-carriers` blockers.
The registry is capacity and binary-layout evidence only; it proves neither
club identity nor country, division, draw-pool, or competition membership.

No ratings, managers, kits, portraits/no-photo decisions, opening-lineup
evidence, person reconciliation, or carrier mappings have been fabricated.
Consequently, strict package validation, two clean database builds, and
runtime qualification have not been attempted.

## Stoke City

The dated source includes a 35-player Stoke City squad at
`eng/2006-2007/flcham/stoke.txt`.  It is roster evidence only and contains no
starting-XI claim.  There is no runtime Stoke lineup screenshot because no
verified build exists; a screenshot from the base or an incomplete build would
not be evidence for 2006/07.

## Calendar proof

The verified clean `MANAGPRE.EXE` was copied and patched locally from 1998/99
to 2006/07.  The local-only receipt is
`.local/season-2006-07/calendar/calendar-receipt.json`; it records 853
recognised patches, source SHA-256
`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158`, and
output SHA-256
`fc12957329cea88955112eabe71aec2c2b2e1cb2effeee49b4b975e2c7782657`.
This demonstrates calendar eligibility, not a database release.

## Reproduce the intake

Materialise the exact `2006-2007` tree from the declared FootballSquads
revision into a dedicated local cache, then run:

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/season-2006-07/cache.footballsquads \
  --season 2006-2007 \
  --output seasons/2006-07/sources/footballsquads-2006-07.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-base-clean-fixed-carriers \
  --output seasons/2006-07/fixed-carrier-registry.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2006-07/fixed-carrier-registry.json \
  --ledger-id pm99-2006-07-fixed-carrier-intake --start-year 2006 \
  --output seasons/2006-07/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2006-07/fixed-carrier-registry.json \
  --ledger seasons/2006-07/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2006-07/fixed-carrier-registry.json \
  --ledger seasons/2006-07/fixed-carrier-ledger.json \
  --output seasons/2006-07/fixed-carrier-intake-audit.json
```

## Required work before delivery

1. Reconcile dated, identity-safe club, player, and manager sources; decide
   the provable PM99 world scope without changing unsupported topology.
2. Assign every fixed carrier and every shared player carrier consistently;
   preserve unresolved cases as blockers.
3. Evidence ratings, kits, portraits or native-no-photo, and opening lineups.
4. Create and pass a complete strict V2 package; make two byte-identical clean
   builds, validate their inventories, and qualify the finished build at
   runtime.
5. Capture the Stoke City runtime lineup from that exact qualified inventory.

Until every gate passes, this is an auditable intake only, not a delivered
database.
