# 2013/14 all-country world intake

## Status

**Intake only — not a package, build, runtime-qualified database, or
delivered season.** This directory records reproducible dated source facts and
the fixed-carrier authoring boundary for the 2013/14 workstream. It does not
assert that the available source cache covers every PM99 world carrier.

The delivery gate is deliberately unsatisfied: all 451 foreign fixed carriers
remain explicitly unassigned. No historical club identity, player, manager,
kit, portrait, rating, opening lineup, country, division, draw-pool, or
competition membership has been inferred from the 1998 baseline.

The separate candidate-identity milestone below does not alter that base
assignment. It supplies four guarded editorial leads only; it is neither an
approval nor a PM99 data change.

## Evidence captured

| Receipt | SHA-256 | Evidence |
| --- | --- | --- |
| `sources/footballsquads-2013-14-world.json` | `1cc50b53dce02014753ba548466b3473d4b3705612477a1bbb39259dfd7f710f` | 570 parsed club-squad receipts / 17,123 player rows from 22 catalog countries and 32 competition catalogs. |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | 451 existing mode-1 foreign carriers and 9,390 immutable roster slots, read from the verified clean base. |
| `fixed-carrier-ledger.json` | `881e921112f6615e9a25107b9d86876e28cef407b78cbb0d5eac9c1b2f01283e` | Empty, hash-locked 2013/14 authoring ledger. |
| `fixed-carrier-intake-audit.json` | `7222e63fa1e846e58802392f4d6bd1718687e4f9087341a44bc36b074d0f3c94` | Audit showing 451 unassigned carriers and zero completed slots, kits, or portraits. |
| `foreign-carrier-assignment.json` | `dfead64aa74cd9b154ecdb44d2932a998328af411fb37c25121faccfe242f41f` | Unchanged empty assignment ledger with six reviewed Spain host-country facts. |
| `foreign-carrier-candidate-queue.json` | `44c552d5ced351a429f477ed4a4bb0a31dd8b6b7be4b0d9619b5543b5e93dcd5` | Six deterministic name-token review rows: four single leads and two explicit ambiguities. |
| `foreign-carrier-candidate-proposal.json` | `759397780dca0ebbe763555e44b7a5a2606beebb6274d7d346018816659032c0` | Four candidate-only proposals derived from single, capacity-sufficient leads. |
| `foreign-carrier-assignment-candidates.json` | `0b27e2ed4c17599088948ab8ace0f415fc63fccddd93cb9ea50cbc0bc9573f69` | Derived candidate ledger; the base assignment remains unchanged. |
| `foreign-carrier-assignment-candidates-audit.json` | `53f271eccafc894395f7cbbb88d2d41485105b11db7cf34218d188fcdf48b987` | Candidate coverage audit: four unapproved leads and 447 still-unassigned carriers. |

The squad capture comes from `footballcsv/cache.footballsquads`, revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` (CC0-1.0). The capture safely
admits 570 source files. It preserves one unusable source receipt rather than
silently omitting it: `ukraine/2013-2014/upl/arskyiv.txt` (SHA-256
`e25484b2bc7d318f7b412237085750e2c7ce18ca0fa5e254463f44348d692131`) has
no current-squad CSV section. This is an unresolved source blocker, not an
assertion that a squad was absent.

The capture reports 423 player rows with one or more unresolved facts: 67
birth dates, 395 heights, 421 weights, and one shirt number. These are
editorial blockers, not default values.

The 2013/14 calendar profile was also calculated from the verified base as a
local-only artifact:

- output: `.local/builds/2013-14-calendar/MANAGPRE.EXE`
- SHA-256: `f10ee740d630545639387b888337d8888a8e013a7b2035b9f18125e18873eae8`
- receipt: `.local/builds/2013-14-calendar/calendar-receipt.json`
- receipt SHA-256: `a34720dd279206ce9a376f27bdfd18c1eb7833fdfb459a0b6efea0fc4d249cb9`
- 853 version-checked operands, 2013 start / 2014 rollover.

Calendar eligibility alone does not make a database build valid.

## Candidate-identity milestone

Six immutable foreign carriers have independently reviewed PM99
host-country evidence for Spain. The deterministic queue compares their
baseline visible names only against dated Spanish source-club display names.
It has made no competition, division, membership, draw-pool, player, manager,
kit, portrait, rating, or binary claim.

Only these four single, capacity-sufficient rows were emitted as **candidate**
proposals; each retains the blockers for independent identity review and a
complete content transaction:

| Carrier | Baseline visible name | Candidate source club | Source catalogue |
| ---: | --- | --- | --- |
| 2 | R.C. Deportivo | Deportivo La Coruña | `spain/2013-2014/segunda/lacoruna.txt` |
| 3 | R. Zaragoza | Zaragoza | `spain/2013-2014/segunda/zaragoza.txt` |
| 5 | Athletic Club | Athletic Bilbao | `spain/2013-2014/laliga/abilbao.txt` |
| 7 | Valencia C.F. | Valencia | `spain/2013-2014/laliga/valencia.txt` |

Carrier 1 remains unresolved between `Barcelona` and `Barcelona B`, and
carrier 4 remains unresolved between `Real Madrid` and `Real Madrid Castilla`.
Both source choices meet the fixed-carrier capacity check; capacity is not
identity proof. Neither ambiguous row is included in the proposal or derived
candidate ledger.

The derived audit reports four `candidate` statuses and 447 unassigned
carriers. Those statuses are unapproved editorial leads, not historical
assignments. The base `foreign-carrier-assignment.json` still has zero
assignments.

## Stoke City status

The dated capture includes the 28-player Stoke City Premier League squad at
`eng/2013-2014/faprem/stoke.txt` (source SHA-256
`e0c305fa18c266142a9a851e6d376dcdad895f7ab4698ed661ab4e4b24e33440`). It
is a squad receipt, **not** opening-XI or formation evidence. No Stoke
carrier has been reconciled or written, no playable 2013/14 build exists, and
there is therefore no valid Stoke lineup screenshot to provide. A screenshot
from the 1998 base or an unqualified patch would be misleading and is
intentionally absent.

## Reproduction and validation

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2013-2014 \
  --output seasons/2013-14/sources/footballsquads-2013-14-world.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-base-clean-fixed-carriers \
  --output seasons/2013-14/fixed-carrier-registry.json
python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2013-14/fixed-carrier-registry.json \
  --ledger-id pm99-2013-14-fixed-carrier-intake \
  --start-year 2013 \
  --output seasons/2013-14/fixed-carrier-ledger.json
python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2013-14/fixed-carrier-registry.json \
  --ledger seasons/2013-14/fixed-carrier-ledger.json
python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2013-14/fixed-carrier-registry.json \
  --ledger seasons/2013-14/fixed-carrier-ledger.json \
  --output seasons/2013-14/fixed-carrier-intake-audit.json

python3 scripts/season_candidate_identity_milestone_v1.py \
  --season-dir seasons/2013-14 \
  --replace

python3 tools/pm99_calendar_patcher.py \
  .local/season-pipeline-v2/pm99-base-clean/MANAGPRE.EXE \
  --year 2013 \
  --output .local/builds/2013-14-calendar/MANAGPRE.EXE \
  --receipt .local/builds/2013-14-calendar/calendar-receipt.json
```

## Remaining delivery gates

1. Reconcile every in-scope club and person to stable identifiers, replace the
   unusable Ukraine source, and source every missing player fact.
2. Complete every fixed-carrier/slot update without changing carrier topology;
   resolve the 36 shared baseline player carriers consistently or leave them
   blocked.
3. Source and review managers, ratings, kits, portrait/no-photo dispositions,
   and opening-lineup evidence for the declared world scope.
4. Create and strictly validate a `pm99-season-package-v2`; then produce two
   clean byte-identical builds and release hashes.
5. Qualify the finished inventory at runtime and capture a Stoke lineup
   screenshot only from that qualified build.
