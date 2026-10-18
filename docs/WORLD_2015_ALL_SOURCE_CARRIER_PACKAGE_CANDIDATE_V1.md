# World 2015 all-source-carrier package candidate V1

`scripts/build_2015_world_all_source_carrier_package_candidate.py` expands
the dated FootballSquads source pool from the 77 opening-fixture links to all
302 `source-squad-ready` carriers and their 6,539 immutable slots. It is one
hash-locked source/package candidate—not a PM99 writer.

```bash
python3 scripts/build_2015_world_all_source_carrier_package_candidate.py \
  --source-draft .local/season-pipeline-v2/world-2015-source-carrier-drafts-20260830.json \
  --player-reconciliation .local/season-pipeline-v2/world-2015-source-player-reconciliation-20260830.json \
  --opening-fixture-source-join .local/season-pipeline-v2/world-2015-opening-fixture-source-join-20260831.json \
  --asset-dispositions .local/season-pipeline-v2/world-2015-asset-dispositions.json \
  --recycle-role-audit .local/season-pipeline-v2/world-2015-recycle-role-demand-20260831.json \
  --output .local/season-pipeline-v2/world-2015-all-302-source-carrier-package-candidate-20260831.json
```

The 77 exact opening-fixture links retain their dated manager/stadium and
formation facts. The remaining 225 carriers still receive full dated club and
player drafts, with `opening-fixture-manager-stadium-formation-metadata-
unavailable` as an explicit metadata blocker. No manager, stadium, formation
or capacity is inferred.

The candidate retains 3,762 complete FIFA16 ratings, applies the deterministic
editorial policy to 2,760 fallback rows, and leaves 17 genuinely ambiguous
FIFA identities unresolved (across 14 carriers). It has no blanket “mode-1
unproven” blocker: the allocation-specific recycle audit qualifies all 29
selected recycle demands (roles 0×9, 4×11, 9×9), while the seven absent dated
duplicate slots remain a content-coverage issue outside this 302-carrier
candidate.

All 302 carrier rows remain blocked by actual external gates: reviewed kit and
portrait decisions, ground/capacity evidence, 225 missing fixture-metadata
sources, 3 incomplete Dutch fixture receipts, 41 carriers with incomplete
FootballSquads facts, and 17 identity-resolution rows. No binary write occurs.
