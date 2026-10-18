# 2018/19 world-season intake

**Status: blocked intake; not a delivered PM99 database.**

This directory contains the first reproducible evidence boundary for the
2018/19 all-country programme.  It deliberately does not contain a season
package, compiled game tree, release hash, or runtime screenshot.  Those
artifacts would be misleading while the immutable PM99 carrier slots have no
historic assignments.

## Captured source corpus

`sources/footballsquads-2018-19.json` is a canonical capture of the local
CC0-1.0 `footballcsv/cache.footballsquads` revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555`.

- SHA-256: `2a759bb49263fda7351a0429e394aa92794094507586bf20c7e27aa866fc383`
- 560 usable club captures, 16,891 player rows, across 22 country catalogs
  and 32 source competition catalogs.
- 815 player rows contain at least one explicitly unresolved captured fact:
  110 birth dates, 789 heights, 812 weights, and 2 shirt numbers.  The field
  counts overlap because one player row can have several gaps.
- `spain/2018-2019/laliga2/reus.txt` is retained as a blocked source with
  SHA-256 `e5c826b61e481735ea17e38f9abba40bf873f392d2f3a8cfbe256c38c2ed55d8`:
  it contains no current-squad section and has contributed no inferred data.

This is source coverage, not proof that a source club corresponds to a PM99
club/carrier, division, country slot, or competition membership.

## Fixed-carrier intake

The registry is bound to verified base `pm99-gog-en-1998-clean`, inventory
fingerprint `310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

| File | SHA-256 | Result |
| --- | --- | --- |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | 451 foreign fixed carriers; 9,390 immutable roster slots. |
| `fixed-carrier-ledger.json` | `ec4c594e95198ed1829afc2eb482a00a31aa066f4cb0ae59048612a23c17b090` | Empty, hash-locked 2018/19 authoring ledger. |
| `fixed-carrier-intake-audit.json` | `fbe1752673905b4684309031594dfd83ff532b99446983dc9fabd0edc58fa3bb` | 451 unassigned carriers; zero complete slots, kits, or portrait decisions. |

The audit's `world-content-incomplete` blocker and its 36 baseline shared-JUG
carrier constraint are expected and remain release-blocking.  The registry is
a binary-layout contract only; no carrier identity was guessed from record
order or a source-club name.

## Candidate-only carrier-identity bridge

The coordinator has produced a separate, deterministic candidate overlay from
six reviewed Spanish host-carrier facts and six single, dated,
capacity-compatible FootballSquads leads.  The **base**
`foreign-carrier-assignment.json` remains empty and unchanged.

| File | SHA-256 | Result |
| --- | --- | --- |
| `foreign-carrier-candidate-proposal.json` | `1c83fe53e9bf4567963dea427ef6fa66714ba8fc8772f4af8ef851de4cbd58ad` | Six deterministic candidate-only proposal rows. |
| `foreign-carrier-assignment-candidates.json` | `8616890a682f2178b9c517e0ec7fc437f0a0f590781ed60481f809a9d49ecf2c` | Separate derived ledger: 6 `candidate`, 445 unassigned. |
| `foreign-carrier-assignment-candidates-audit.json` | `616a661bcdbeba3b242294466458d9a2bf0b15dfdd5f50366b8a5bac052470d1` | Hash-locked audit of the derived candidate ledger. |

| Carrier | Baseline display | Dated source club | Slots / source rows |
| ---: | --- | --- | ---: |
| 1 | F.C. Barcelona | Barcelona | 26 / 37 |
| 2 | R.C. Deportivo | Deportivo La Coruña | 25 / 31 |
| 3 | R. Zaragoza | Zaragoza | 27 / 35 |
| 4 | Real Madrid C.F. | Real Madrid | 25 / 38 |
| 5 | Athletic Club | Athletic Bilbao | 25 / 33 |
| 7 | Valencia C.F. | Valencia | 26 / 30 |

Every row is `candidate`, not `approved`, and has three explicit blockers:
independent club-identity review, editorial approval of the name-token lead,
and a complete club/player/manager/kit/portrait/runtime transaction.  Meeting
the immutable roster capacity proves only that the dated source is large
enough to review; it does not prove historical carrier identity.  No PM99
file, carrier topology, shared base assignment, or release state was changed.

## Stoke City evidence and runtime status

The source capture includes Stoke City at
`eng/2018-2019/flcham/stoke.txt` (SHA-256
`ade8ff5d857df6924d3e0cf222d879f414574922d75f1b3520e4744e4f1a8248`): 43
current-squad rows, of which 11 have captured physical-fact gaps.  It is a
squad source, not an opening-lineup claim.

There is **no Stoke screenshot**.  The worker contract permits a runtime
lineup screenshot only from a finished, inventory-qualified release.  No
such build exists while the world ledger is entirely unassigned; creating a
screenshot from the baseline or a partial build would falsely attest to this
season.

## Independent calendar component

The verified base `MANAGPRE.EXE` was copied and patched only into the local,
untracked path `.local/season-2018-19/calendar/`.

- input SHA-256: `01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158`
- output SHA-256: `132581c31596afca6e60c737fdc27b08d7289364c777e955c2dece00fc7f1332`
- receipt: `.local/season-2018-19/calendar/calendar-receipt.json`
- target years: 2018 / 2019; checked patch count: 853.

This verifies the independently version-locked clock component.  It is not a
release build and is not combined with a database tree.

## Reproduce and validate

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2018-2019 \
  --output seasons/2018-19/sources/footballsquads-2018-19.json

python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2018-19/fixed-carrier-registry.json \
  --ledger seasons/2018-19/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2018-19/fixed-carrier-registry.json \
  --ledger seasons/2018-19/fixed-carrier-ledger.json \
  --output seasons/2018-19/fixed-carrier-intake-audit.json

python3 scripts/season_candidate_identity_milestone_v1.py \
  --season-dir seasons/2018-19 --replace

python3 scripts/foreign_carrier_candidate_proposal_v1.py \
  --registry seasons/2018-19/fixed-carrier-registry.json \
  --source-capture seasons/2018-19/sources/footballsquads-2018-19.json \
  --assignment seasons/2018-19/foreign-carrier-assignment.json \
  --queue seasons/2018-19/foreign-carrier-candidate-queue.json \
  --proposal seasons/2018-19/foreign-carrier-candidate-proposal.json

python3 tools/pm99_calendar_patcher.py \
  .local/season-pipeline-v2/pm99-base-clean/MANAGPRE.EXE \
  --year 2018 \
  --output .local/season-2018-19/calendar/MANAGPRE.EXE \
  --receipt .local/season-2018-19/calendar/calendar-receipt.json
```

## Required work before delivery

1. Reconcile every claimed club and person to dated, identity-safe sources;
   resolve or preserve the captured source gaps.
2. Obtain reviewed, one-tile runtime picker evidence and bind historical clubs
   to the appropriate immutable carriers without changing topology.
3. Complete every assigned carrier's manager, player facts and ratings, kit,
   portrait/no-photo decision, and opening-lineup evidence; resolve shared
   JUG carrier conflicts consistently.
4. Derive and validate a strict `pm99-season-package-v2`, then make two
   independent clean, byte-identical builds and qualify the finished inventory
   in the runner.  Only then capture the Stoke City lineup screenshot.
