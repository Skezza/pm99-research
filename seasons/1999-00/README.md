# PM99 1999/00 intake milestone

Status: **source and fixed-carrier intake complete; not a strict V2 package,
build, or playable release.**  This is the earliest supported season boundary
for the reusable pipeline.  It deliberately records what is known and what
still needs editorial reconciliation instead of copying a later-season
database into 1999/00.

## Durable inputs

| Input | SHA-256 | Purpose |
| --- | --- | --- |
| `sources/footballsquads-1999-00.json` | `cf3e5759ee6ee36ebc7c7dc8016c8d00d2d555ccae50dd13f4f591fe6b662557` | Dated squad facts captured from 176 FootballSquads club pages. |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | Native-base foreign carrier inventory: 451 clubs and 9,390 roster slots. |
| `fixed-carrier-ledger.json` | `bed75c31e738bceeb9b674594b3356e07d7f898f6b550e8749c7515de777e500` | Empty, hash-locked 1999/00 authoring ledger. |
| `fixed-carrier-intake-audit.json` | `14a4ead7fa28ad81fd40a4102ddcfc7a8eb6ad1a3192aa70fa65804b88eea9c2` | Initial audit and explicit blockers. |

The source capture is pinned to `footballcsv/cache.footballsquads` revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` (CC0-1.0).  It covers 176 clubs,
5,424 player rows, and the English, French, German, Italian, Scottish, and
Spanish catalogues listed in its `summary`.

FootballSquads' 1999/00 pages do not supply nationality.  The capture therefore
leaves all 5,424 nationalities unresolved rather than guessing.  It also
records source gaps for 42 birth dates, 95 heights, 102 weights, 18 primary
positions, and 3 shirt numbers.  These are the editorial queue for this input,
not validation exceptions.

## Native-base constraint

The registry is taken from `pm99-gog-en-1998-clean`; it pins the native files
as follows:

| File | SHA-256 |
| --- | --- |
| `DBDAT/ENT98030.FDI` | `729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238` |
| `DBDAT/EQ98030.FDI` | `e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c` |
| `DBDAT/JUG98030.FDI` | `95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844` |

It is a **carrier inventory**, not evidence that those baseline club identities
or competition memberships were correct in 1999/00.  No carrier has been
assigned: the audit correctly reports 451 unassigned carriers and 36 shared
baseline player carriers.  Country, division, draw-pool, and competition
topology remain preserved unless separately evidenced.

## Calendar proof

The known clean `MANAGPRE.EXE` is eligible for the first post-base season.  A
local-only patch receipt at `.local/builds/1999-00-calendar/calendar-receipt.json`
records target year 1999, rollover 2000, 853 patches (50 source-1998 and 803
source-1999 operands), and output SHA-256
`554693e94e8ea68bbef7f952b8848230faa58abaa2454d354220a38b271a68a7`.
The executable and receipt remain local proprietary artifacts and are not a
release claim.

## Reproduce the intake

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 1999-2000 \
  --country eng --country france --country ger --country italy \
  --country scots --country spain \
  --output seasons/1999-00/sources/footballsquads-1999-00.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-base-clean-fixed-carriers \
  --output seasons/1999-00/fixed-carrier-registry.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/1999-00/fixed-carrier-registry.json \
  --ledger-id pm99-1999-00-fixed-carrier-intake --start-year 1999 \
  --output seasons/1999-00/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/1999-00/fixed-carrier-registry.json \
  --ledger seasons/1999-00/fixed-carrier-ledger.json \
  --output seasons/1999-00/fixed-carrier-intake-audit.json
```

## Required work before a 1999/00 release

1. Reconcile stable person IDs and every missing player fact from dated,
   identity-safe sources.
2. Evidence the clubs, managers, opening squads, and all foreign carrier
   assignments without changing unsupported topology.
3. Add reviewed ratings, kit evidence, and either era-correct portraits or an
   explicit native-no-photo decision for each player.
4. Produce a complete strict V2 season package, then make two clean builds,
   pass static validation, and attach runtime proof for the exact release
   inventory.

Until those gates pass, this folder is an auditable research starting point,
not a candidate database.
