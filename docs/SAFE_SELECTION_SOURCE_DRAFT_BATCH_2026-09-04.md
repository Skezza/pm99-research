# Safe selection source-draft batch

`scripts/season_safe_selection_source_draft_batch_v1.py` is the deterministic
authoring bridge from the 25 mechanically-safe source-club selection manifests
to a new source-draft revision per eligible season. It is not a release or a
database builder.

For each current season it verifies the hash-bound source intake, carrier
allocation, fixed registry, safe manifest, opening lineup/reconciliation/
additions, calendar-bound template and matching calendar audit. It then:

1. materialises the explicit source-club selection without changing the raw
   intake;
2. regenerates the opening-squad preallocation against that exact selection;
3. replays the source-package builder with the selection, preallocation,
   allocation and calendar binding; and
4. writes a new immutable revision containing the selection, selection audit,
   preallocation, source draft, build audit and source-draft receipt.

It never compiles a database, creates a release package, validates PM99 at
runtime or makes a playable claim. Every source-draft receipt sets
`release_eligible: false`, even if a downstream builder assessment is empty.

## Run the remaining 25-manifest pass

Use a new output root for every run. The command refuses an existing root or
an unfinished sibling staging root.

```bash
python3 scripts/season_safe_selection_source_draft_batch_v1.py \
  --expected-season-count 25 \
  --output-root .local/season-safe-selection-source-draft-batch-v1/selection-aware-25-20260904-r1
```

The result is `.local/season-safe-selection-source-draft-batch-v1/selection-aware-25-20260904-r1/batch-receipt.json`.
It has one row for every target season:

- `source-draft-blocked-no-release` — a complete new source-draft revision
  exists and its remaining build blockers are enumerated.
- `source-draft-unreleased` — a complete source draft exists but is still only
  an authoring output; it has not been promoted, compiled or run.
- `skipped-no-safe-selection-manifest` — no safe manifest existed for that
  target season.
- `skipped-unresolved-dependency` — a required input was absent, stale or did
  not hash-bind the current evidence chain. The receipt contains the exact
  reason; the tool never substitutes an older opening plan or another season.

For a bounded diagnostic run, use repeatable `--season` and an expected count:

```bash
python3 scripts/season_safe_selection_source_draft_batch_v1.py \
  --season 2016-17 \
  --expected-season-count 1 \
  --output-root .local/season-safe-selection-source-draft-batch-v1/selection-aware-check-2016-17-NEW
```

The 2016/17 safe selection itself applies, but its present opening-fixture
additions do not hash-bind the current lineup/reconciliation pair. The
diagnostic therefore records `skipped-unresolved-dependency`; it does not make
a selection-aware preallocation from stale additions.

## 2016/17 dependency repair — 2026-09-06

The additions-binding dependency above is now closed in a new, immutable local
evidence chain. `derive_transfermarkt_opening_player_additions_v1.py` replayed
the existing current squad capture, lineup, reconciliation and person evidence
into:

```text
.local/season-opening-evidence-rebind-v1/2016-17-20260906-r1/
```

The derived additions SHA-256 is
`2b1a6d5ca2ce2fa9df80bf4b35098fe6ef5a62c02ca1437f85e27ee7b8a5027e`;
all 591 additions have cached published person profiles. A one-season safe
selection replay then materialised revision
`safe-selection-source-draft-2016-17-249e448de4515e2cbd3b` with receipt SHA-256
`f065e04fd42a33f3a9e7094f31e26782468fdbdf256f2e30ffbc856350b56a30`.
Its state is `source-draft-blocked-no-release`, not playable or release-ready.
Ten authoring blocker categories remain, followed by the static compile,
runtime-route and bound-screenshot gates.

## Safe inspection

```bash
python3 -m json.tool \
  .local/season-safe-selection-source-draft-batch-v1/selection-aware-25-20260904-r1/batch-receipt.json
python3 scripts/check_repo_boundary.py
```

The batch output is local evidence only. It must still pass the later manager,
kit, ratings, release, compiler and runtime gates before it can be called a
playable season.
