# 2002/03 all-country world intake

Status: **source and fixed-carrier intake complete; not a strict V2 package,
build, runtime-qualified database, or delivered season.** This folder records
the available dated facts and exact release blockers. It must not be used to
infer unsupported club topology, player identity, ratings, kits, portraits,
managers, or starting line-ups.

## Durable inputs

| Input | SHA-256 | Purpose |
| --- | --- | --- |
| `sources/footballsquads-2002-03.json` | `92a86b14bddedf59fb39cd3150bc87852fd6609d9e67fa4c544b1d8839055da1` | Canonical dated squad-fact capture. |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | Clean-base foreign carrier inventory. |
| `fixed-carrier-ledger.json` | `ed3844752e6b17aa4a76efd4f39e5749ad6ef36c90fb979c8af93a3540d8ee6c` | Empty, registry-locked 2002/03 authoring ledger. |
| `fixed-carrier-intake-audit.json` | `81d540479fc9cbcd7889809f683f9500cf386b762735d5c9b0f1db1e04f8e912` | Deterministic coverage and blocker report. |

The capture is pinned to `footballcsv/cache.footballsquads` revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` (CC0-1.0). It contains 331 club
pages and 9,652 player rows in nine country catalogues and 17 competition
catalogues:

| Catalogue | Clubs | Player rows |
| --- | ---: | ---: |
| Australia | 13 | 332 |
| England | 114 | 3,358 |
| France | 40 | 1,125 |
| Germany | 36 | 1,023 |
| Holland | 18 | 455 |
| Italy | 38 | 1,203 |
| Portugal | 18 | 528 |
| Scotland | 12 | 447 |
| Spain | 42 | 1,181 |

This is not evidence of complete world coverage: no dated source has yet been
captured for every country and competition represented by PM99's foreign
carriers. The raw pages contain no `Nat` column, so nationality is unresolved
for all 9,652 player rows. The capture also records 119 missing birth dates,
793 missing heights, 827 missing weights, 18 missing primary positions, and
175 missing shirt numbers. Those facts must be reconciled from dated,
identity-safe evidence before strict package validation.

## Fixed-carrier constraint

The carrier registry is derived from `pm99-gog-en-1998-clean` and locks these
base database files:

| File | SHA-256 |
| --- | --- |
| `DBDAT/ENT98030.FDI` | `729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238` |
| `DBDAT/EQ98030.FDI` | `e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c` |
| `DBDAT/JUG98030.FDI` | `95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844` |

It exposes 451 foreign mode-1 club carriers and 9,390 fixed roster slots. The
audit reports all 451 carriers as `unassigned`, zero complete player slots, and
36 shared baseline player carriers. It is therefore correct for this ledger to
remain empty: no historical club has been mapped to a carrier and no country,
division, draw-pool, or competition membership has been inferred from carrier
order or a baseline club name.

## Candidate-only Spanish identity leads

Six single, capacity-compatible source-name leads have been mechanically
derived from the reviewed Spanish host-country queue: carriers 1, 2, 3, 4, 5,
and 7 respectively name Barcelona, Deportivo La Coruña, Zaragoza, Real Madrid,
Athletic Bilbao, and Valencia. They are all `candidate`, not approved, and the
source competition catalogue remains provenance only--not a PM99 division,
membership, country, or draw-pool claim.

| File | SHA-256 | Role |
| --- | --- | --- |
| `foreign-carrier-candidate-proposal.json` | `6da201b0fae38026b2aded096e9184ae2413ff0040944a4db6cb0fe4ff4bb9bf` | Deterministic candidate-only overlay. |
| `foreign-carrier-assignment-candidates.json` | `5839a69500a94eab00b36c286395777dbaf127dca60141a924beea085f470846` | Separate derived candidate ledger. |
| `foreign-carrier-assignment-candidates-audit.json` | `1f3070ca970ea5dd2c5542438b8b066d46c6662144a3099b99cac030f2f231f3` | Audit: six candidates and 445 unassigned carriers. |

The base `foreign-carrier-assignment.json` remains empty. Each lead has the
same three blockers: its name-token match is not editorially approved,
independent club-identity review is required, and full club/player/manager/
kit/portrait/runtime work remains mandatory. No identity has been approved,
no PM99 file has been written, and this does not change the release status.

## Stoke City evidence and screenshot status

`eng/2002-2003/d1/stoke.txt` is captured with SHA-256
`77a4d1dd5366f61293aab329e530526106e9b4d05249c3569e91c3900922c06c`.
It supplies a season squad list for Stoke City in English Division One, but it
does **not** identify an opening fixture, the starting XI, substitutes,
formation, tactics positions, manager, or a PM99 carrier mapping. Consequently
there is no reliable Stoke City starting-lineup screenshot. A screenshot from
the clean base would be historically false, and no runtime was attempted.

## Calendar compatibility proof

The known clean `MANAGPRE.EXE` was patched locally for target year 2002 and
rollover year 2003. The receipt at
`.local/builds/2002-03-calendar/calendar-receipt.json` records 853 verified
patches and output SHA-256
`af87a516e39d05742acd7f63db19fa7c78b0a394b33968a54767244e611f1787`.
This local proprietary executable is calendar compatibility evidence only; it
is not a database build or release.

## Reproduce the intake

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2002-2003 \
  --output seasons/2002-03/sources/footballsquads-2002-03.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-base-clean-fixed-carriers \
  --output seasons/2002-03/fixed-carrier-registry.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2002-03/fixed-carrier-registry.json \
  --ledger-id pm99-2002-03-fixed-carrier-intake --start-year 2002 \
  --output seasons/2002-03/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2002-03/fixed-carrier-registry.json \
  --ledger seasons/2002-03/fixed-carrier-ledger.json \
  --output seasons/2002-03/fixed-carrier-intake-audit.json
```

## Required work before delivery

1. Capture and reconcile dated all-country facts, including all missing player
   facts and stable person identities.
2. Evidence each fixed foreign carrier's historical club, manager, roster,
   and any preserved shared player carrier without altering PM99 topology.
3. Add source-backed ratings, kits, portraits or deliberate native-no-photo
   outcomes, and opening fixture/line-up/formation evidence for every club.
4. Generate a complete strict V2 package; build twice from the verified clean
   base; pass static audits; and add exact-release runtime evidence, including
   a Stoke City lineup screenshot tied to its opening-lineup source.
