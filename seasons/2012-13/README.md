# 2012/13 all-country world-season intake

## Status

**Not delivered.** This directory is a reproducible source-and-capacity intake
for the 2012/13 world-season workstream. It is deliberately not a
`pm99-season-package-v2`, game database, release receipt, or runtime-qualified
build. The available evidence does not support making any of those claims.

The FootballSquads capture is dated source material for its 569 listed clubs;
it does not establish the historical PM99 carrier mapping, manager identities,
ratings, kits, portraits, opening fixtures, or opening lineups. The fixed
carrier registry is a baseline binary-layout contract, not evidence of club or
competition membership.

## Captured inputs

| File | SHA-256 | Evidence |
| --- | --- | --- |
| `sources/footballsquads-2012-13.json` | `9fab654584153be82fa09d61d006ec354469b5626c076cf04539c33dbb6f5bc7` | 569 dated squad sources, 17,223 player rows, 21 source-country catalogs and 32 competition catalogs |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | immutable 1998-clean-base foreign carrier capacity: 451 carriers / 9,390 roster slots |
| `fixed-carrier-ledger.json` | `612e890421e92f71aefb495cd01681f49a1dea53ec4be0e26117aa127791d38f` | empty 2012/13 authoring ledger locked to the registry |
| `fixed-carrier-intake-audit.json` | `cd7f267449927a0b27a09cb8d7a677f1e79b4cf07959c7ec1e88950393fc86f9` | deterministic coverage audit and release blockers |

The source capture is from `footballcsv/cache.footballsquads` revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` (CC0-1.0). All 569 matching
source files were captured; none was rejected as malformed. It contains 509
rows with an explicitly unresolved input fact: 68 birth dates, 439 heights,
485 weights, and 24 shirt numbers. These counts are not inferred or silently
filled.

## Candidate-only foreign identity milestone

The following three files are a guarded editorial proposal derived from the
reviewed host-country and source-name queue. They are **not approved identity
assignments**, do not alter `foreign-carrier-assignment.json`, and do not write
PM99 data or assets.

| File | SHA-256 | Result |
| --- | --- | --- |
| `foreign-carrier-candidate-proposal.json` | `752625c1054e1d118cd9c36f9a32094ed01f05d00e51de07b974ed376ec0285c` | four candidate-only, capacity-compatible single-name leads |
| `foreign-carrier-assignment-candidates.json` | `965bb5e880db8aa35ec10862636652d0099ec20ff2d951b236c6fb673df0ebd5` | derived candidate ledger; 4 candidates and 447 unassigned foreign carriers |
| `foreign-carrier-assignment-candidates-audit.json` | `e262a7343652715af4e3c74a3b6ce42348241f262281d4272aaaa266d578b35a` | deterministic candidate-ledger audit |

The four leads are carrier 2 / Deportivo La Coruña, carrier 3 / Zaragoza,
carrier 5 / Athletic Bilbao, and carrier 7 / Valencia. Each retains the
required editorial, complete-content, and runtime blockers.

Two name-token collisions are deliberately preserved as unresolved: carrier 1
has both Barcelona and Barcelona B candidates, and carrier 4 has both Real
Madrid and Real Madrid Castilla candidates. Neither carrier appears in the
derived candidate ledger. No reserve-team inference has been made.

## Stoke City evidence and screenshot status

The source capture includes the 28-player Stoke City Premier League squad in
`eng/2012-2013/faprem/stoke.txt`, whose recorded source SHA-256 is
`bda07d81bee57eb1d2cb5b977fc77e27be85bc05e9313abd81dcbe3100a7d0f0`.

There is no sourced 2012/13 opening-XI record in this intake, no carrier
assignment for the English database, and no runtime-qualified 2012/13 build.
Consequently, **no Stoke lineup screenshot exists or is claimed**. A screenshot
would be required only after a completed, hash-locked release has passed the
runtime gate; producing one from the baseline or a partial build would be
misleading.

## Calendar prerequisite

The version-checked local calendar patch was successfully calculated from the
known clean `MANAGPRE.EXE` profile. Its private executable and receipt remain
under `.local/builds/2012-13-calendar/` and are not repository artifacts.

| Field | Value |
| --- | --- |
| Profile | `managpre-calendar-1998-99-to-target-v1` |
| Input SHA-256 | `01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158` |
| Output SHA-256 | `71c96627d7e6b75a015282fa29d7106bd6d80273eae7acc1726efc485681b4ea` |
| Target years | 2012 / 2013 |
| Verified patch count | 853 |

This patch has not been combined with a database build and does not qualify
the season for runtime use.

## Current delivery gate

The ledger audit reports `world-content-incomplete`: all **451 of 451** foreign
fixed carriers are unassigned, with zero completed player slots and no kit or
portrait decisions. It also identifies 36 shared baseline player carriers that
require a single evidence-backed identity or an explicit unresolved decision.
These are release blockers, not data to be guessed.

The source cache covers only the enumerated 21 catalog countries. It is not a
claim of full historical world coverage and cannot be treated as a substitute
for the missing carrier identity, manager, rating, kit, portrait, lineup and
fixture evidence.

## Reproduce and continue

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2012-2013 \
  --output seasons/2012-13/sources/footballsquads-2012-13.json

python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2012-13/fixed-carrier-registry.json \
  --ledger seasons/2012-13/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2012-13/fixed-carrier-registry.json \
  --ledger seasons/2012-13/fixed-carrier-ledger.json \
  --output seasons/2012-13/fixed-carrier-intake-audit.json

python3 scripts/season_candidate_identity_milestone_v1.py \
  --season-dir seasons/2012-13
```

The next worker must first reconcile stable club, manager and player identities
to the existing fixed carriers, then supply dated evidence for every declared
fact and asset decision. Only after zero world-scope blockers may it author a
strict package, make two clean byte-identical builds, and run the Stoke route
to record a screenshot and its hash.
