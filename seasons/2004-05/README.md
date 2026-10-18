# PM99 2004/05 all-country world-season intake

Status: **not delivered.**  This folder contains the evidence-backed intake
that can be safely created from the locally pinned sources and PM99's native
fixed-carrier inventory.  It is not a strict V2 package, a build, a runtime
qualified database, or evidence of a Stoke City lineup.

## Source-bundle repair and reprocessed intake

The eleven complementary cache receipts are now composed only through the
hash-locked [`source-bundle.json`](source-bundle.json). It verifies every
input before reproducing `sources/footballsquads-2004-05-composed.json`
(`6f6365de637bd6a28e224783841f3a34655d9a381915cb5ece2c6a89160a00d4`) and
derives `foreign-carrier-assignment-composed.json`
(`4600e53be7312c2e9562b69949d7ed6e40588bcfeb5a5421914c1dcbcee969cc`) from
the former Portugal-bound empty assignment. The reprocessed raw source
intake is `source-intake.json`
(`74a687bbf396a64926eb23f8c24daa6aa74e7ec7f034af197fa6f7380b6dca52`) and
its audit is `source-intake-audit.json`
(`fd7ab6eb4df2f20f8b25bba495719d83d270d6af9e4ae3e939c73685268a2511`).

This closes the competing-source receipt problem only. The composed
assignment remains zero approved identities and 451 unassigned foreign
carriers; the rejected country catalogues and all editorial release gates
below remain explicit blockers.

## Captured source coverage

The captures are pinned to `footballcsv/cache.footballsquads` revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` (CC0-1.0).  They cover 362 club
pages and 10,534 player rows from the following cache catalogues:

| Catalogue | Clubs | Players | Capture SHA-256 |
| --- | ---: | ---: | --- |
| Austria | 10 | 275 | `ec6619671b7164d7b45631f4678321375c6a99f39b5755e5a87b746749d8293f` |
| Belgium | 18 | 449 | `f738f3b3a0d61380604dffbc862615dbc35332f2a43186dd3e01cb6d473c6795` |
| Denmark | 12 | 298 | `40cae020c036cb384b1e420e28795c0cf9038ac03bc72afe8583c26216f5fe4f` |
| England | 114 | 3,258 | `286f89c56f24d71621ec55bf2a2e8f99d47e3e14bda3e2286bf778be6b1e0c59` |
| France | 40 | 1,253 | `684ed7c49cffb943bae65c7a5737c376454f4d75db57ace42c0c1d21119c69d6` |
| Germany | 36 | 1,050 | `f748a77238f5e96fa5bb0275f70823cdc15894a49da0ff9823b43038f5ea271d` |
| Holland | 18 | 451 | `634e0100927dbf95c3297b7af31197e0e65b170494a1a7a6fe82ee0591281e8d` |
| Italy | 42 | 1,406 | `dba9acc014193f038050316a9e4b45f353dadae7c58d2f476b993e892c96407a` |
| Portugal | 18 | 498 | `ea909b05a1b077b91ce290b81349b0e458efc9a9116e4902d4aa7657ee8285bb` |
| Scotland | 12 | 423 | `da7991186955c1959b2c71661667f5e8ccdd40b7c4ee180a8601196787cfa3de` |
| Spain | 42 | 1,173 | `8b75e6c4850bd594e2a557603ea32b9c45e63725fe65c8ca70bd4340ee6d76ba` |

Every captured row has an unresolved nationality because this vintage cache
does not contain a `Nat` column.  Other recorded source gaps are 98 birth
dates, 548 heights, 575 weights, 312 shirt numbers, and five primary
positions.  These are explicit editorial queues, not values to infer.

Four further cache catalogues (66 club pages) are rejected by the strict
capture tool.  Their exact source evidence and failure modes are in
`source-capture-blockers.json`: Argentina and Mexico use valid calendar-year
Clausura titles inside split-year folders; the Swiss Servette page duplicates
shirt number 25; and the Turkish Ankaragücü page contains an unnamed numbered
row.  The blocker receipt SHA-256 is
`8ce31bf722998723cd5781fe9383ed688f2febfc4ee7683bd7d72f210b384ae1`.
They prevent a claim of all-country source coverage.

## Fixed-carrier intake

| Input | SHA-256 | Result |
| --- | --- | --- |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | Native-base inventory of 451 foreign fixed carriers and 9,390 roster slots. |
| `fixed-carrier-ledger.json` | `8e0558c31d04d5f19d42059b4ed2bcc7622d5a875cc78b5fda34e2f13e7d3650` | Hash-locked 2004/05 ledger; zero carriers assigned. |
| `fixed-carrier-intake-audit.json` | `145b305ec20f11be129a573e1bcfc9971ac827731873a2661e457ffbe3ce3be5` | Audit: all 451 carriers unassigned and 36 baseline shared-player carriers. |

The registry pins the verified clean base files:

| File | SHA-256 |
| --- | --- |
| `DBDAT/ENT98030.FDI` | `729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238` |
| `DBDAT/EQ98030.FDI` | `e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c` |
| `DBDAT/JUG98030.FDI` | `95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844` |

This is capacity and binary-layout evidence only.  It does not establish any
2004/05 club, competition, country, manager, player, kit, portrait, or lineup
identity.  No unsupported topology edit has been attempted.

## Calendar proof

The known clean `MANAGPRE.EXE` was version-checked and copied to the local-only
path `.local/builds/2004-05-calendar/MANAGPRE.EXE`.  Its receipt records target
year 2004, rollover year 2005, all 853 expected patches (50 original-1998 and
803 original-1999 operands), base SHA-256
`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158`, and
output SHA-256
`2dd6f213b27573871dcbe1c385dcf2ddde1e8ff96cafa6ae7e34180615905e6f`.
The executable and its receipt are local proprietary artifacts; this proves
calendar eligibility only and is not a build or release claim.

## Reproduce

Run one capture per accepted catalogue, for example:

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2004-2005 --country eng \
  --output seasons/2004-05/sources/footballsquads-2004-05-eng.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-base-clean-fixed-carriers \
  --output seasons/2004-05/fixed-carrier-registry.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2004-05/fixed-carrier-registry.json \
  --ledger-id pm99-2004-05-fixed-carrier-intake --start-year 2004 \
  --output seasons/2004-05/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2004-05/fixed-carrier-registry.json \
  --ledger seasons/2004-05/fixed-carrier-ledger.json
```

## Candidate-only identity milestone: blocked

The existing `foreign-carrier-assignment.json` (SHA-256
`b8547da0a650aa757ca2e0af04c5d4eb65e4a57ff1850c7069e36553687b0701`)
replays to the checked-in assignment audit exactly: it has six reviewed
Spanish host-carrier observations, zero historical identity assignments, and
451 unassigned carriers.  Its hash-locked source capture is the Portuguese
catalogue (`ea909b05a1b077b91ce290b81349b0e458efc9a9116e4902d4aa7657ee8285bb`),
not a Spanish catalogue.  It therefore has no Spanish source/name lead.

`foreign-carrier-candidate-queue.json` (SHA-256
`6bc95aaa692dae14f0bbeb8cd529e3e3f7798affdfd26b9ac816ec381690e79f`)
validates exactly against those inputs.  Its six explicit rows—carriers 1, 2,
3, 4, 5, and 7—are all `no-name-token-candidate`, each with an empty candidate
list.  The current proposal tool correctly refuses this queue: it permits an
output only for an unassigned, single, capacity-compatible name-token lead.
No candidate-only proposal is therefore permitted, and no carrier identity
has been proposed or approved.

The pre-composition candidate milestone remains a historical blocked receipt;
it is not promoted by the generic source composition. No proposal, candidate
ledger, PM99 write, or release claim was created.

## Delivery blockers

Before this can be called a 2004/05 all-country database, all countries and
clubs require dated, identity-safe source capture; every person needs stable
reconciliation and fact provenance; all 451 carrier assignments must be
complete without changing topology; managers, ratings, kits, portraits or
native-no-photo states, formations, and opening lineups need evidence; and a
strict package must produce two identical clean builds and runtime proof.

No build was made.  Consequently there is no trustworthy Stoke City starting
lineup screenshot to attach.  Capturing one from the baseline or a partial
intake would misrepresent the season as released.
