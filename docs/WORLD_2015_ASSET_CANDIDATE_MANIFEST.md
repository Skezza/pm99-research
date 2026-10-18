# 2015/16 world asset candidate manifest

`scripts/audit_2015_world_assets.py` creates a deterministic, source-only join
of the 302 source-ready carrier drafts (6,539 fixed slots), the player
reconciliation, the local compact kit archives and explicitly named portrait
receipts. It does not modify an EXE, FDI, PKF or release database.

Run it against the current local evidence with:

```bash
python3 scripts/audit_2015_world_assets.py \
  --draft .local/season-pipeline-v2/world-2015-source-carrier-drafts-20260830.json \
  --reconciliation .local/season-pipeline-v2/world-2015-source-player-reconciliation-20260830.json \
  --kit-dbdat .local/season-pipeline-v2/english92-clean-release-2015-16-20260830/DBDAT \
  --portrait-receipt .local/season-pipeline-v2/world2015-foreign-core-with-assets-20260830/face-stage-receipt.json \
  --output .local/season-pipeline-v2/world-2015-asset-candidate-manifest.json
```

The output is canonical JSON and hashes its source files. It includes all 451
foreign carriers; carriers without a dated squad source have an empty player
list. Each selected player is retained with its fixed carrier/slot, source
name, FIFA16 identity match status and portrait disposition.

## Current local audit

The 2026-08-31 local run found:

| Measure | Count |
| --- | ---: |
| Foreign carriers in manifest | 451 |
| Dated source-squad-ready carriers | 302 |
| Fixed slots in source-ready carriers | 6,539 |
| Compact archives with base art | 451 / 451 (all three archives) |
| Era-approved kit dispositions | 0 |
| FIFA16 URL portrait candidates | 3,761 |
| Cached identity-matched approved portraits | 1 |
| Explicit native-no-photo receipts | 0 |
| Players needing an identity-safe era source/decision | 2,777 |

Compact `MINIESC.PKF`, `NANOESC.PKF` and `RIDIESC.PKF` records are complete
for the carrier IDs, but this is only base-art presence. The manifest marks
each as `needs-era-source`; a carrier cannot become complete by inheriting a
base image belonging to its former club. Likewise a FIFA16 URL is a download
candidate, not an approved output. Only an explicitly supplied face-stage
receipt with the same FIFA player ID is counted as `cached-approved-era`.
Players with no identity-safe URL remain unresolved until editorial review
either supplies an era-correct source or records an explicit native-no-photo
decision.

`audit_kit_archive_coverage.py` is also usable independently for archive-wide
presence counts. Its import path is self-contained, so it can be invoked
directly from the repository root.
