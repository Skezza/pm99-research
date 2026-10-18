# PM99 2007/08 world-season intake

Status: **source and fixed-carrier intake plus a candidate-only identity
milestone complete; not a strict V2 package, build, playable database, or
delivered season.**  This folder records available dated squad evidence and
the native PM99 capacity boundary without turning either into unsupported
historical claims.

## Durable inputs

| Input | SHA-256 | Purpose |
| --- | --- | --- |
| `sources/footballsquads-2007-08.json` | `d857d2279aa80a7bdb5a9444fdbeb9382fe644706bc0524a5baf1ace73b04a96` | Canonical capture of the available 2007/08 FootballSquads club/phase squad facts. |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | Native-base inventory of 451 foreign mode-1 carriers and 9,390 roster slots. |
| `fixed-carrier-ledger.json` | `0906aa8297f35a1fe831d66f79833f066a094fe00c1d7fd533389fe0cec15237` | Empty, hash-locked 2007/08 foreign authoring ledger. |
| `fixed-carrier-intake-audit.json` | `3b9071c9b4a51cc6230ba656c552e204574a5c6ac298265ebe8ede82f643a583` | Initial audit that names the world-release blockers. |

The squad capture is pinned to `footballcsv/cache.footballsquads` revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` (CC0-1.0).  It contains 554
dated club/phase captures across 31 competition catalogues in 21 country
catalogues, with 16,522 player rows.  `arg` and `mexico` legitimately include
separate dated Apertura and Clausura captures; this is source coverage, not a
claim that either phase is a PM99 competition mapping.

The source format for this season lacks a nationality column.  All 16,522
rows therefore retain `nationality` as unresolved rather than receiving a
guess.  Other recorded gaps are 260 birth dates, 1,540 heights, 1,730
weights, 40 primary positions, and 129 shirt numbers.  The capture contains
no manager, opening-lineup, rating, kit, portrait, person-reconciliation, or
carrier-assignment evidence.  Those queues block a world release.

## Fixed-carrier boundary

The registry is derived from the verified `pm99-gog-en-1998-clean` base.  It
is a binary-layout capacity inventory only: it makes no country, division,
club, draw-pool, or competition-membership assertion.  The initial audit has
zero completed foreign player slots and all 451 foreign carriers unassigned.
It also flags 36 shared baseline JUG player carriers, which cannot be given
conflicting historical identities.

## Candidate-only identity milestone

The reviewed six-carrier Spain host evidence and dated source-name queue were
used only to derive exact, single, capacity-compatible editorial leads.  The
result contains six `candidate` rows and **zero approved identities**:
Barcelona (carrier 1), Deportivo La Coruña (2), Zaragoza (3), Real Madrid
(4), Athletic Bilbao (5), and Valencia (7).  Every row retains its independent
identity-review and complete-content/runtime blockers.  The derived audit
therefore reports 445 carriers with no identity row; the six candidate rows
are not historical approvals or a PM99 write.

| Candidate-only output | SHA-256 |
| --- | --- |
| `foreign-carrier-candidate-proposal.json` | `ca9a80c8949299ec63f8e1fa0754375d9fa2810614e8d8f8dc9f9cac4f2be99c` |
| `foreign-carrier-assignment-candidates.json` | `9745d6dd324d761870206b8c27a4862309bb522dac89ae6433e0e0e1ff191513` |
| `foreign-carrier-assignment-candidates-audit.json` | `c51f3358673ad180481574e825fdf0a8c4fdd34a2a3d892918050a05a10889a1` |

Recreate these deterministic, candidate-only files with:

```bash
python3 scripts/season_candidate_identity_milestone_v1.py \
  --season-dir seasons/2007-08 --replace
```

Consequently this workstream has **not** created a strict package, database
build, release inventory, runtime proof, or Stoke City screenshot.  A runtime
screenshot from the untouched base or from an unverified build would be false
evidence and is prohibited by the worker contract.

## Calendar compatibility proof

The verified clean `MANAGPRE.EXE` was patched locally for target 2007 and
rollover 2008.  Its local receipt at
`.local/builds/2007-08-calendar/calendar-receipt.json` records 853 patches,
input SHA-256 `01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158`,
and output SHA-256
`8b6de10ebbcbdfdb27b598806971e0c4887a00f0eeebb3568dcfb0089374edf3`.
The patched executable and receipt are local proprietary artifacts, and
calendar compatibility alone is not a season-build claim.

## Reproduce the intake

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2007-2008 \
  --output seasons/2007-08/sources/footballsquads-2007-08.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-base-clean-fixed-carriers \
  --output seasons/2007-08/fixed-carrier-registry.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2007-08/fixed-carrier-registry.json \
  --ledger-id pm99-2007-08-fixed-carrier-intake --start-year 2007 \
  --output seasons/2007-08/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2007-08/fixed-carrier-registry.json \
  --ledger seasons/2007-08/fixed-carrier-ledger.json \
  --output seasons/2007-08/fixed-carrier-intake-audit.json
```

## Required work for delivery

1. Reconcile all players and managers to stable identities and fill each
   missing fact from dated, identity-safe sources.
2. Evidence every in-scope club, manager, roster, kit, portrait/no-photo
   decision, rating, and opening lineup; map them to fixed carriers without
   changing unproven topology.
3. Resolve every shared player carrier consistently, then produce a complete
   strict V2 package.
4. Make two independent clean, byte-identical builds, pass static validation,
   and qualify the finished inventory at runtime.
5. Capture the Stoke City lineup screenshot only from that finished,
   runtime-qualified release and record its safe local path and SHA-256 in the
   release attestation.
