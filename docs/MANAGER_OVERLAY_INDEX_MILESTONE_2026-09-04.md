# Explicit manager-overlay index milestone — 2026-09-04

The source-completeness reader now accepts a per-season manager-overlay index
instead of one global overlay version.  It is a read-only authoring and source
measurement milestone, not a package, release, runtime, or playable-game
claim.

## Explicit selection

The local selection manifest names one overlay version for every one of the
25 calendar-bound baseline seasons:

- 2000/01–2006/07 and 2008/09–2014/15 use their explicit `manager-v1`;
- 2007/08 explicitly retains `manager-v2`;
- 2016/17–2019/20 use their completed `manager-v2` repairs;
- 2020/21 explicitly selects its completed `manager-v3` repair; and
- 2021/22–2025/26 use their completed `manager-v2` repairs.

No reader selects a directory merely because its version number or timestamp
is newest.  A future manager repair requires a new manifest and a new index
path, preserving earlier receipts.

The generated local artifacts are:

| Artifact | SHA-256 |
| --- | --- |
| explicit selection manifest | `8dc2540d66f37e765e718ad7ce999a24823fb8bd8122eecdea1e845da1c2a099` |
| frozen per-season index | `7d1b875ddda2d91998f6a6890de85fa8b69c901aa98d762a13de7c8beeb94195` |
| 25-season JSON completeness receipt | `42af30da0f1d55c9036450817c6a172d6fd0a12bcadfee4d0b8b09f370a18fca` |
| Markdown companion | `e026babda0bd22d18c3c8cc6fa75017c5b1f4af0de5208501eb22bb2e26c826d` |

The index binds the frozen calendar baseline, selection manifest, and each
selected overlay audit and manager ledger by SHA-256.  The completeness reader
then checks every selected overlay against the current source capture and
current opening-lineup receipt.  A missing or stale binding stops the run.

## Fixed-carrier manager result

The indexed receipt counts only assigned fixed carriers:

| Measure | Earlier unindexed 25-season queue | Explicit-index receipt | Change |
| --- | ---: | ---: | ---: |
| Assigned fixed carriers | 10,351 | 10,351 | 0 |
| Exact dated, hash-backed manager identities | 6,491 | 8,917 | +2,426 |
| Manager work items | 3,860 | 1,434 | -2,426 |

For the completed 2016/17–2025/26 repair tranche alone, the same comparison is
2,710 to 3,802 resolved fixed-carrier managers: **+1,092**, reducing its queue
from 1,439 to 347.  These numbers demonstrate selection and source coverage
only; manager evidence must still travel through the remaining package,
ratings, kit, XI, static-ingress and runtime gates before any release claim.

## Reproduce

```bash
python3 scripts/season_manager_overlay_index_v1.py \
  --selection-manifest \
    .local/season-overlay-selection-manifests-v1/calendar-bound-v2-manager-overlays-explicit-v1.json \
  --output \
    .local/season-overlay-index-v1/calendar-bound-v2-manager-overlays-explicit-v1.json

python3 scripts/season_source_completeness_queue_v1.py \
  --manager-overlay-index \
    .local/season-overlay-index-v1/calendar-bound-v2-manager-overlays-explicit-v1.json \
  --output-json .local/operations/season-source-completeness-explicit-manager-index-v1.json \
  --output-markdown .local/operations/season-source-completeness-explicit-manager-index-v1.md
```

Both commands refuse to reinterpret a newer overlay directory as a selected
input.  Choose it explicitly in a new manifest instead.
