# 2019/20 all-country world intake

**Status: blocked — not a delivered PM99 database.** This directory records
the source and fixed-carrier intake for the 2019/20 all-country workstream.
It contains no strict V2 package, built game database, release hash, runtime
qualification, or Stoke City lineup screenshot. A six-row candidate-only
foreign-identity overlay is recorded below; it is not an approval or PM99
content change.

## Verified inputs

The canonical squad capture is
[`sources/footballsquads-2019-20.json`](sources/footballsquads-2019-20.json)
(`sha256:9962457c6ef192eb6dc3ef513614b4f919a5cc906aa2cc40d52d200b3e307624`).
It is derived from `footballcsv/cache.footballsquads`, revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` (CC0-1.0).

- 559 usable club sources, 17,098 player rows, 22 country catalogues, and 32
  competition catalogues were captured.
- 905 player rows retain one or more source gaps: 130 birth dates, 853
  heights, 881 weights, 23 shirt numbers, two nationalities, and two primary
  positions. They require source-backed reconciliation; these values must not
  be inferred.
- `eng/2019-2020/flone/bury.txt`
  (`sha256:d6c15913ba2da29dcc51ddcbd1e1f3b67a2e4e05ca6bebbe6bf62ce477992394`)
  was deliberately blocked: its dated content has only a `Past Players`
  section, not a current squad. The capture retains this receipt.
- The capture includes Stoke City's dated squad source
  `eng/2019-2020/flcham/stoke.txt`
  (`sha256:130291c3869d58e41f3669117a3dd59afd3927860fbe9b29dff7683f66b40469`),
  but a squad source is not opening-lineup evidence.

The base topology registry is
[`fixed-carrier-registry.json`](fixed-carrier-registry.json)
(`sha256:7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375`).
It is locked to verified base `pm99-gog-en-1998-clean`, inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.
It describes 451 existing foreign carriers / 9,390 player slots; it is a
binary capacity contract, never evidence of historical club membership.

## Ledger and gate state

[`fixed-carrier-ledger.json`](fixed-carrier-ledger.json)
(`sha256:33dd155e3219457744f4dfeb88cddfd7bbe5c2e175cbe52aeb4a83f6af245e66`)
is structurally valid but deliberately contains no historical assignments.
Its audit is
[`fixed-carrier-intake-audit.json`](fixed-carrier-intake-audit.json)
(`sha256:532318347a629baa65447071feca391b4359a2cdb38c08099a0e806d6974942e`).

The audit reports all 451 carriers unassigned, zero complete player slots,
and no kit or portrait decisions. It blocks a world release on
`world-content-incomplete` and on 36 shared baseline player carriers that
need one consistent evidenced identity. This is intentional: no source club
has been guessed onto a carrier and no country, division, draw-pool, or
competition topology has been changed.

## Candidate-only foreign-identity milestone

The reviewed empty base assignment is
[`foreign-carrier-assignment.json`](foreign-carrier-assignment.json)
(`sha256:44fc8f0c451e0a39e49a8bf70ccf3f9a248279b673fab42c42c34733c6ec03be`).
Its six-row review queue is
[`foreign-carrier-candidate-queue.json`](foreign-carrier-candidate-queue.json)
(`sha256:79245d40328fbcc28bb0d6bd399f53dcb2a8e8fa24ef3fb7b5c4a40f46a061af`).
Each queue row has reviewed Spanish host evidence, one dated source-name lead,
and a roster that meets the fixed carrier capacity. A name-token match remains
an editorial lead, never historical carrier-identity proof.

The candidate-only coordinator generated these separate, canonical artefacts:

| File | SHA-256 | Meaning |
| --- | --- | --- |
| [`foreign-carrier-candidate-proposal.json`](foreign-carrier-candidate-proposal.json) | `0da15ea0a4b410dc5e24b505bcbfd6f25d5d039e4a3b7f8769c6414f9b41ca45` | Deterministic proposal overlay. |
| [`foreign-carrier-assignment-candidates.json`](foreign-carrier-assignment-candidates.json) | `0f87c7519eed8ce838301f8eb15e0c0ddfe6344c908c37eb68d0c51e2d6b3e42` | Derived candidate ledger; the base assignment remains unchanged. |
| [`foreign-carrier-assignment-candidates-audit.json`](foreign-carrier-assignment-candidates-audit.json) | `e4de27c46176ca18f510015d908f07f91d49d7d6edc931b87f1ef3c8c4f3d01f` | Candidate-only identity audit. |

| Carrier | Baseline display | Dated source lead | Status |
| ---: | --- | --- | --- |
| 1 | F.C. Barcelona | Barcelona | `candidate` |
| 2 | R.C. Deportivo | Deportivo La Coruña | `candidate` |
| 3 | R. Zaragoza | Zaragoza | `candidate` |
| 4 | Real Madrid C.F. | Real Madrid | `candidate` |
| 5 | Athletic Club | Athletic Bilbao | `candidate` |
| 7 | Valencia C.F. | Valencia | `candidate` |

The audit reports six candidate identities, six host-country evidence rows,
and 445 unassigned foreign carriers. Every candidate retains these blockers:
independent carrier-identity review, lack of editorial approval, and the
complete club/player/manager/kit/portrait/runtime transaction. The candidate
ledger has not written PM99 and cannot be used as a release or lineup claim.

The calendar-only experiment is local and non-release material:
`.local/builds/2019-20-calendar/calendar-receipt.json` describes a 2019 to
2020 patch of the verified base `MANAGPRE.EXE`
(`sha256:840913d4a62fa975f6c399bb5ca1ae951a286d4878dfd03dec8802e80cfdd95b`).
It has 853 patches and yields
`MANAGPRE.EXE` SHA-256
`1bbc918c9479eb79c9780999cdb19c2549fa3a8d9f20f9de91e14dc10b1f853f` from
base SHA-256
`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158`.
It does not establish a complete game build or runtime qualification.

## Required work before delivery

1. Reconcile every in-scope club, manager, and player to stable IDs and dated
   facts, resolving all source gaps and Bury's missing current-squad evidence.
2. Assign only proven identities to existing fixed carriers, resolving all
   shared carrier conflicts. Do not derive topology from the registry.
3. Add canonical evidence for ratings, kits, portrait/no-photo outcomes, and
   opening lineups/formations.
4. Emit and strictly validate a `pm99-season-package-v2`, then make two clean,
   byte-identical builds from the verified base.
5. Qualify the final inventory at runtime and capture the Stoke City lineup
   screenshot with its safe local path and SHA-256. Until then, no screenshot
   is claimed or supplied.

## Candidate milestone validation

```bash
python3 scripts/season_candidate_identity_milestone_v1.py \
  --season-dir seasons/2019-20
python3 scripts/foreign_carrier_candidate_proposal_v1.py \
  --registry seasons/2019-20/fixed-carrier-registry.json \
  --source-capture seasons/2019-20/sources/footballsquads-2019-20.json \
  --assignment seasons/2019-20/foreign-carrier-assignment.json \
  --queue seasons/2019-20/foreign-carrier-candidate-queue.json \
  --proposal seasons/2019-20/foreign-carrier-candidate-proposal.json
python3 scripts/foreign_carrier_assignment_v1.py \
  --registry seasons/2019-20/fixed-carrier-registry.json \
  --source-capture seasons/2019-20/sources/footballsquads-2019-20.json \
  --assignment seasons/2019-20/foreign-carrier-assignment-candidates.json \
  --output .local/builds/2019-20-candidate-identity-revalidation/audit.json
cmp -s seasons/2019-20/foreign-carrier-assignment-candidates-audit.json \
  .local/builds/2019-20-candidate-identity-revalidation/audit.json
```

The proposal validator accepted the generated six-row proposal. The final
comparison confirms the independently regenerated audit is byte-identical to
the coordinator's audit.

## Reproduction

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2019-2020 \
  --output seasons/2019-20/sources/footballsquads-2019-20.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-base-clean-fixed-carriers \
  --output seasons/2019-20/fixed-carrier-registry.json
python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2019-20/fixed-carrier-registry.json \
  --ledger-id pm99-2019-20-fixed-carrier-intake --start-year 2019 \
  --output seasons/2019-20/fixed-carrier-ledger.json
python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2019-20/fixed-carrier-registry.json \
  --ledger seasons/2019-20/fixed-carrier-ledger.json
python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2019-20/fixed-carrier-registry.json \
  --ledger seasons/2019-20/fixed-carrier-ledger.json \
  --output seasons/2019-20/fixed-carrier-intake-audit.json
```
