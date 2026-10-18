# PM99 2001/02 world-ledger intake

Status: **source and fixed-carrier intake only; not a strict V2 package,
build, runtime-qualified database, or delivered season.**  This directory
records the evidence available at the start of the 2001/02 all-world workstream
without inferring missing historical facts or changing PM99's fixed carrier
topology.

## Durable inputs

| Input | SHA-256 | Purpose |
| --- | --- | --- |
| `sources/footballsquads-2001-02.json` | `0ff65dcaaa42a0a821df91f128cd0ff77af5b500f8b9bc8335f0d26b0757cfeb` | Hash-retained dated squad facts from the local FootballSquads cache. |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | Base PM99 foreign carrier inventory: 451 clubs and 9,390 roster slots. |
| `fixed-carrier-ledger.json` | `3d39d1ff0ca4284ca008819619721a01c276c7140d60fa847c8d746c9541fc04` | Empty 2001/02 authoring ledger locked to that inventory. |
| `fixed-carrier-intake-audit.json` | `1bb39beb74357140f11e11d0f6186ec074ec30f0ade53c2e14daef2e030868c4` | Deterministic coverage audit and release blockers. |

The squad capture is pinned to `footballcsv/cache.footballsquads` revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` under CC0-1.0.  It contains 245
clubs and 7,310 player rows from nine catalogue countries:

| Catalogue | Clubs | Players |
| --- | ---: | ---: |
| Australia | 13 | 291 |
| England | 92 | 2,957 |
| France | 18 | 538 |
| Germany | 36 | 1,041 |
| Holland | 18 | 455 |
| Italy | 18 | 561 |
| Portugal | 18 | 500 |
| Scotland | 12 | 439 |
| Spain | 20 | 528 |

This is **not all-country coverage**: it is exactly the nine catalogues the
dated cache contains.  It must not be used to silently preserve or overwrite
the remaining global PM99 carriers.

## Measured blockers

FootballSquads does not provide a usable nationality field for this era, so all
7,310 captured player rows record `nationality` as unresolved.  Other captured
gaps are 56 birth dates, 528 heights, 541 weights, 20 primary positions, and
288 shirt numbers.  These facts need dated, identity-safe corroboration before
they can enter a strict package.

The ledger audit reports all 451 fixed foreign carriers as `unassigned`, zero
complete player slots, and no kit or portrait outcomes.  It also records 36
shared baseline JUG carriers.  No club-to-carrier assignments, player identity
mappings, manager decisions, ratings, kits, portraits, opening lineups, or
formation coordinates have been authored.  The registry is a base-file
capacity inventory, not evidence of 2001/02 membership, country, division, or
competition topology.

Stoke City is retained as a dated 35-player roster capture at
`eng/2001-2002/d2/stoke.txt` (source SHA-256
`da0b3e7373eb03bd36cbb7fea881403d238dc2ac1e7de3bc57628ca3a7189a76`).
That source does not identify a particular fixture's starting XI, substitutes,
formation, or tactics coordinates.  Consequently this workstream has **no
reliable Stoke City lineup screenshot**; producing one before those facts and
a release build are proven would be misleading.

## Candidate-only foreign-carrier bridge

The reviewed Spanish host-country queue has six single, capacity-compatible
name-token leads.  They are reproduced in a **separate derived ledger** and
all remain `candidate`, never `approved`: carriers 1 Barcelona, 2 Deportivo
La Coruña, 3 Zaragoza, 4 Real Madrid, 5 Athletic Bilbao, and 7 Valencia.  The
base `foreign-carrier-assignment.json` remains unchanged with zero assignments.
No identity approval, player mapping, PM99 write, membership claim, or release
claim follows from these rows.

| Candidate-only artefact | SHA-256 | Result |
| --- | --- | --- |
| `foreign-carrier-candidate-proposal.json` | `8f0a27a1707ecf9d8cbb2c6073fbfcb9e6a47911746020d5d255358b91b939a5` | Deterministic six-row candidate overlay from the verified queue. |
| `foreign-carrier-assignment-candidates.json` | `dace8b49f3ca5deb15a0697d0c1685988091c2ca3a94ece4b8883ce1e04baa6c` | Separate candidate ledger; 445 of 451 carriers remain unassigned. |
| `foreign-carrier-assignment-candidates-audit.json` | `ec72b71cf5b8624fe447d2bd83f635386a4c3ce680be2d27c1e145f77747ceef` | `identity-assignment-incomplete`: six candidate rows and six host-evidence rows. |

Every candidate retains the blockers that its name-token match is not
editorially approved, independent club-identity review is required, and the
complete club/player/manager/kit/portrait/runtime transaction remains open.
The Spanish source catalogue is provenance only; it has not been converted
into a PM99 country, division, membership, or draw-pool assertion.

## Calendar eligibility only

The clean-base calendar tool has produced a local-only 2001 -> 2002 executable
receipt at `.local/builds/2001-02-calendar/calendar-receipt.json`.  It applies
853 verified operands and has output SHA-256
`88b3a727b0bb2bcebd9fcb655a445412edc2d72e10fff7b11796dee3dfc5b7d7`.
This is an executable-layer eligibility check, not a season build or runtime
claim; the executable and receipt remain untracked local artifacts.

## Reproduce the intake

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2001-2002 \
  --output seasons/2001-02/sources/footballsquads-2001-02.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-base-clean-fixed-carriers \
  --output seasons/2001-02/fixed-carrier-registry.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2001-02/fixed-carrier-registry.json \
  --ledger-id pm99-2001-02-fixed-carrier-intake --start-year 2001 \
  --output seasons/2001-02/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2001-02/fixed-carrier-registry.json \
  --ledger seasons/2001-02/fixed-carrier-ledger.json \
  --output seasons/2001-02/fixed-carrier-intake-audit.json

python3 scripts/foreign_carrier_candidate_proposal_v1.py \
  --registry seasons/2001-02/fixed-carrier-registry.json \
  --source-capture seasons/2001-02/sources/footballsquads-2001-02.json \
  --assignment seasons/2001-02/foreign-carrier-assignment.json \
  --queue seasons/2001-02/foreign-carrier-candidate-queue.json \
  --proposal seasons/2001-02/foreign-carrier-candidate-proposal.json

python3 scripts/foreign_carrier_assignment_v1.py \
  --registry seasons/2001-02/fixed-carrier-registry.json \
  --source-capture seasons/2001-02/sources/footballsquads-2001-02.json \
  --assignment seasons/2001-02/foreign-carrier-assignment-candidates.json \
  --output seasons/2001-02/foreign-carrier-assignment-candidates-audit.json
```

## Required work before delivery

1. Add all-country dated sources, reconcile real-world club/person identities,
   and resolve source gaps without changing PM99's carrier topology.
2. Map each world carrier and its roster safely, including an explicit decision
   for every shared baseline player carrier.
3. Add source-backed managers, ratings, kit evidence, and portrait or
   native-no-photo decisions.
4. Evidence every playable club's opening XI, substitutes, formation and PM99
   tactics coordinates; Stoke City needs a fixture-specific source before a
   reliable lineup screenshot is possible.
5. Create a complete strict V2 package, make two matching clean builds, pass
   static audits, and attach runtime evidence tied to the final release hashes.

Until all five gates pass, this folder is a measured research starting point,
not a 2001/02 database delivery.
