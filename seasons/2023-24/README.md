# PM99 2023/24 all-country intake

Status: **canonical source and fixed-carrier intake complete; not a strict V2
package, build, or playable release.**  This directory records the available
all-country source coverage without inventing club-to-carrier assignments,
ratings, managers, opening lineups, kits, portraits, or game evidence.

## Durable inputs

| Input | SHA-256 | Purpose |
| --- | --- | --- |
| `sources/footballsquads-2023-24.json` | `a4ae4ca99a668f8a0407bd1d300751aec80df7ded63de70013d964cad6caca1b` | Dated squad facts captured from 564 FootballSquads club pages. |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | Native-base foreign carrier inventory: 451 clubs and 9,390 roster slots. |
| `fixed-carrier-ledger.json` | `7a47c7a4c85fccca6aede88b43ae512803b0bb23ba23d1ff78ff1b1fb7e22322` | Empty, hash-locked 2023/24 authoring ledger. |
| `fixed-carrier-intake-audit.json` | `cad0a779db1da8542803c43dcf7d3d925ae1b415fb74276cba52d554418e5414` | Initial coverage audit and explicit blockers. |

The source capture is pinned to `footballcsv/cache.footballsquads` revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` (CC0-1.0).  It contains 564
clubs, 17,550 player rows, 33 competition catalogues, and these 22 country
catalogues: Australia, Austria, Belgium, Croatia, Czech Republic, Denmark,
England, France, Germany, Greece, Hungary, Italy, Mexico, Netherlands, Poland,
Portugal, Russia, Scotland, Spain, Switzerland, Turkey, and Ukraine.

The capture has no blocked source files, but 2,735 player rows contain one or
more unresolved source facts: 466 birth dates, 2,634 heights, 2,707 weights,
29 shirt numbers, four primary positions, and three nationalities.  These are
source-backed gaps, not values to infer.

## Stoke City evidence

The capture contains the 37-player `eng/flcham` Stoke City squad from
`eng/2023-2024/flcham/stoke.txt`, SHA-256
`1c7516ddf9135d58da377f035798743153bb918ca5293c2926c8b3ff35b8c43e`.
It is roster evidence only; it does not establish an opening eleven or a PM99
carrier assignment.

**No Stoke lineup screenshot exists for this season.**  There is no released
or runtime-qualified 2023/24 build, so a screenshot would be misleading and
is deliberately not fabricated.

## Native-base and scope constraints

The registry is locked to `pm99-gog-en-1998-clean` (base inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`).  It
contains 451 foreign carriers; the native layout has 543 club carriers in all
(92 English plus 451 foreign).  The intake’s 564 captured clubs consequently
cannot be treated as an implicit one-to-one PM99 scope.  The documented policy
preserves existing carriers and makes no country, division, draw-pool, or
competition-membership claims.

No foreign carrier has been assigned.  The audit reports all 451 as
`unassigned`, zero complete player slots, zero kit decisions, zero portrait
decisions, and 36 shared baseline player carriers.  Its blockers are
`world-content-incomplete` and `baseline-shared-player-carriers`.

## Candidate-only identity bridge

The separate base assignment and candidate queue retain all 451 carriers as
unassigned.  A deterministic coordinator has derived a five-row **candidate
only** overlay from the single, capacity-compatible Spanish host-country leads.
It does not alter the base assignment, approve an identity, write PM99, or
change any shared carrier, competition, country, division, membership, or
draw-pool state.

| File | SHA-256 | Role |
| --- | --- | --- |
| `foreign-carrier-assignment.json` | `2468019fce9bff5b0b48ef792f512c8218da90dfef8b1a71403c77ac8830c3c2` | Unchanged 451-unassigned base assignment ledger. |
| `foreign-carrier-candidate-queue.json` | `a5a9a83b955e5eb73f2fbbcef47f8ae87d57989fe57ea07952abf791e2cacd4a` | Reviewed-host / source-name candidate queue. |
| `foreign-carrier-candidate-proposal.json` | `3e379caa060f73992013240c754ba03c7671ffa5a83b897db0dc2d4b51b4fc07` | Deterministic, unapproved five-row proposal. |
| `foreign-carrier-assignment-candidates.json` | `0436cca176402fe66e6128b37c8a4d8bec3745bc61af77915c915eb6a090b71e` | Separate derived candidate ledger; 446 carriers remain unassigned. |
| `foreign-carrier-assignment-candidates-audit.json` | `dcac7dc8cc1be769cae32f0f6c45e2071f969ff736c45041fdd99cf46376686d` | Candidate-only audit. |

| Carrier | Dated source-club lead | Source path |
| ---: | --- | --- |
| 1 | Barcelona | `spain/2023-2024/laliga/barce.txt` |
| 3 | Zaragoza | `spain/2023-2024/laliga2/zaragoza.txt` |
| 4 | Real Madrid | `spain/2023-2024/laliga/rmadrid.txt` |
| 5 | Athletic Bilbao | `spain/2023-2024/laliga/abilbao.txt` |
| 7 | Valencia | `spain/2023-2024/laliga/valencia.txt` |

Carrier 2 (`R.C. Deportivo`) has **no dated source-name lead** in this
capture.  It is deliberately absent from the proposal and remains unassigned;
the absence is not a historical claim about Deportivo.  All five candidate
rows remain blocked pending independent club-identity approval and a complete
club/player/manager/kit/portrait/opening-state/package/runtime transaction.

## Calendar proof

The clean `MANAGPRE.EXE` hash
`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158` patches
to the 2023/24 calendar with 853 substitutions.  The local-only receipt at
`.local/builds/2023-24-calendar/calendar-receipt.json` records target 2023,
rollover 2024, and output hash
`b737420a936bd91d70416c9090e700f636243d25da3cbfd1d3d7253d4b5532fc`.
This is a calendar component only, not a database release.

## Reproduce the intake

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2023-2024 \
  --output seasons/2023-24/sources/footballsquads-2023-24.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-base-clean-fixed-carriers \
  --output seasons/2023-24/fixed-carrier-registry.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2023-24/fixed-carrier-registry.json \
  --ledger-id pm99-2023-24-fixed-carrier-intake --start-year 2023 \
  --output seasons/2023-24/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2023-24/fixed-carrier-registry.json \
  --ledger seasons/2023-24/fixed-carrier-ledger.json \
  --output seasons/2023-24/fixed-carrier-intake-audit.json

python3 scripts/season_candidate_identity_milestone_v1.py \
  --season-dir seasons/2023-24
```

## Gates before delivery

1. Establish the exact in-scope clubs and source-backed bindings to existing
   carriers, without changing unsupported topology.
2. Reconcile stable player and manager identities and all source gaps from
   dated, identity-safe records, including opening-lineup evidence.
3. Add sourced ratings, kits, and portraits or explicit native-no-photo
   decisions for every assigned player.
4. Produce a complete strict V2 package, two independently clean matching
   builds, static validation, and runtime qualification tied to the final
   inventory.  Only then may a Stoke lineup screenshot be captured.

Until these gates pass, this folder is an auditable all-country research
intake—not a candidate database.
