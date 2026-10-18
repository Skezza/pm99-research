# 2010/11 all-country world intake

## Status

**Intake only — not a package, build, runtime-qualified database, or
delivered season.**  This directory records reproducible dated source facts
and the fixed-carrier authoring boundary for the 2010/11 workstream.  It does
not assert that the available source cache covers every PM99 world carrier.

The delivery gate is deliberately unsatisfied: all 451 foreign fixed carriers
remain explicitly unassigned, so no historical club identity, player,
manager, kit, portrait, rating, opening lineup, country, division, draw-pool,
or competition membership has been inferred from the 1998 baseline.

## Evidence captured

| Receipt | SHA-256 | Evidence |
| --- | --- | --- |
| `sources/footballsquads-2010-11-world.json` | `ce0c9c0571107eb030013246c1cc31e957902172917578ecb7d87a003a093a06` | 554 club-squad receipts / 16,873 player rows from 21 catalog countries and 31 competition catalogs. |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | 451 existing mode-1 foreign carriers and 9,390 immutable roster slots, read from the verified clean base. |
| `fixed-carrier-ledger.json` | `cc91339c7a50eb6bf7d8206f94693b640b7bf58120e2c44bdfcce2d7146bb49e` | Empty, hash-locked 2010/11 authoring ledger. |
| `fixed-carrier-intake-audit.json` | `39486e336a18b9c6e3d4888f5682632ce6141c431fb6d8030f1049a51a3d3201` | Audit showing 451 unassigned carriers and zero completed slots, kits, or portraits. |

The squad capture comes from `footballcsv/cache.footballsquads`, revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` (CC0-1.0).  All 554 available
2010/11 source files were safely admitted; none was rejected.  The capture
retains individual source-file hashes and reports 637 rows with one or more
unresolved source facts: 59 birth dates, 524 heights, 622 weights, and 14
shirt numbers.  These are editorial blockers, not default values.

The 2010/11 calendar profile was also calculated from the verified base as a
local-only artifact:

- output: `.local/builds/2010-11-calendar/MANAGPRE.EXE`
- SHA-256: `f84bd2a265484cbacca27a0e08d830dd6c18e99aee53024fc857ae2bd671c8e1`
- receipt: `.local/builds/2010-11-calendar/calendar-receipt.json`
- receipt SHA-256: `2428cc5e0c9d14672543bfc77f004548d0ab96258fa815c8735a4d7d02014aab`
- 853 version-checked operands, 2010 start / 2011 rollover.

Calendar eligibility alone does not make a database build valid.

## Candidate-only foreign-carrier identity bridge

The reviewed Spanish host-country queue yields five single,
capacity-compatible, name-token leads.  They are recorded only in a separate
derived candidate ledger; the base `foreign-carrier-assignment.json` remains
empty and no row is `approved`.

| Carrier | PM99 baseline display | Dated source club | Status |
| ---: | --- | --- | --- |
| 2 | R.C. Deportivo | Deportivo La Coruña | `candidate` |
| 3 | R. Zaragoza | Zaragoza | `candidate` |
| 4 | Real Madrid C.F. | Real Madrid | `candidate` |
| 5 | Athletic Club | Athletic Bilbao | `candidate` |
| 7 | Valencia C.F. | Valencia | `candidate` |

Carrier 1 (`F.C. Barcelona`) remains unassigned.  Its source-name token has
two dated, capacity-compatible leads—Barcelona and Barcelona B—so it has the
queue state `multiple-name-token-candidates` and is deliberately omitted from
the proposal.  This is an unresolved ambiguity, not a Barcelona assignment.

| Candidate-only artefact | SHA-256 | Result |
| --- | --- | --- |
| `foreign-carrier-candidate-proposal.json` | `f08a364041ee212f43c75e0dea67d6059a2ba15c4230617eb89856cd0dea286e` | Deterministic five-row candidate overlay from single-lead queue rows only. |
| `foreign-carrier-assignment-candidates.json` | `dafda589af20d6db5475343169ee6cbea5528cd91f44764097534259761e86af` | Separate derived ledger; 446 of 451 carriers remain unassigned. |
| `foreign-carrier-assignment-candidates-audit.json` | `8efabd0b62a047034abbd374ee878562d48d47a51e90eec464241834f4eee3df` | `identity-assignment-incomplete`: five candidate identities and six host-evidence rows. |

Each candidate retains explicit blockers: its name-token link is not
editorially approved; independent club-identity review remains required; and
the player, manager, kit, portrait/no-photo, opening-state, package,
clean-build, and runtime transaction is incomplete.  The source catalogue is
provenance only, never a PM99 country, division, membership, or draw-pool
claim.  The candidate bridge writes neither PM99 nor the base assignment.

## Stoke City status

The dated capture includes the 28-player Stoke City Premier League squad at
`eng/2010-2011/faprem/stoke.txt` (source SHA-256
`809fca453e0eda390b92a407f59159944d93ec3a1664818c7cbda289ffb186c8`).
It is a squad receipt, **not** opening-XI or formation evidence.  No Stoke
carrier has been reconciled or written, no playable 2010/11 build exists, and
there is therefore no valid Stoke lineup screenshot to provide.  A screenshot
from the 1998 base or an unqualified patch would be misleading and is
intentionally absent.

## Reproduction and validation

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2010-2011 \
  --output seasons/2010-11/sources/footballsquads-2010-11-world.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-base-clean-fixed-carriers \
  --output seasons/2010-11/fixed-carrier-registry.json
python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2010-11/fixed-carrier-registry.json \
  --ledger-id pm99-2010-11-fixed-carrier-intake \
  --start-year 2010 \
  --output seasons/2010-11/fixed-carrier-ledger.json
python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2010-11/fixed-carrier-registry.json \
  --ledger seasons/2010-11/fixed-carrier-ledger.json
python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2010-11/fixed-carrier-registry.json \
  --ledger seasons/2010-11/fixed-carrier-ledger.json \
  --output seasons/2010-11/fixed-carrier-intake-audit.json

python3 scripts/season_candidate_identity_milestone_v1.py \
  --season-dir seasons/2010-11

python3 scripts/foreign_carrier_candidate_proposal_v1.py \
  --registry seasons/2010-11/fixed-carrier-registry.json \
  --source-capture seasons/2010-11/sources/footballsquads-2010-11-world.json \
  --assignment seasons/2010-11/foreign-carrier-assignment.json \
  --queue seasons/2010-11/foreign-carrier-candidate-queue.json \
  --proposal seasons/2010-11/foreign-carrier-candidate-proposal.json

python3 scripts/foreign_carrier_assignment_v1.py \
  --registry seasons/2010-11/fixed-carrier-registry.json \
  --source-capture seasons/2010-11/sources/footballsquads-2010-11-world.json \
  --assignment seasons/2010-11/foreign-carrier-assignment-candidates.json \
  --output seasons/2010-11/foreign-carrier-assignment-candidates-audit.json
```

## Remaining delivery gates

1. Reconcile every in-scope club and person to stable identifiers and source
   every missing player fact.
2. Complete every fixed-carrier/slot update without changing carrier topology;
   resolve the 36 shared baseline player carriers consistently or leave them
   blocked.
3. Source and review managers, ratings, kits, portrait/no-photo dispositions,
   and opening-lineup evidence for the declared world scope.
4. Create and strictly validate a `pm99-season-package-v2`; then produce two
   clean byte-identical builds and release hashes.
5. Qualify the finished inventory at runtime and capture a Stoke lineup
   screenshot only from that qualified build.
