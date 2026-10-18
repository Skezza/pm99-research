# Premier Manager 99 Game Data

## Overview
This directory contains the original game data files that are being analyzed and modified.

## File Types
- `.FDI` files: Player database files
- `.PKF` files: Package files containing various game assets
- `.FDI.backup` files: Backup copies of database files

## Usage
These files are used as input for the reverse engineering tools and can be modified using the database editor.

## Important Notes
- Do not modify the original game files directly
- Always work with copies of the data files
- Use the backup files to restore the original state if needed

## Reviewable season overrides

The JSON manifests under `season-kit-overrides-v1/` and
`season-opening-overrides-v1/` are small, source-cited exceptions to the
deterministic season pipeline. They contain no proprietary PM99 data. Keeping
them here makes a later editorial correction change one declared fact without
regenerating unrelated source decisions.

## Release catalogues

`preferred-season-releases-v1.json` selects exactly one immutable preferred
release for each supported season. It contains identifiers and hashes only;
local paths and proprietary game files remain under ignored `.local/` storage.

Narrow artwork transactions may reuse the physical game directory while saving
the changed original bytes. Superseded releases are then explicitly archived
as recoverable deltas, not advertised as unchanged full copies. See
[`FOREIGN_ARTWORK_ROLLOUT_2026-10-03.md`](../docs/FOREIGN_ARTWORK_ROLLOUT_2026-10-03.md).

Artwork credits: individual Wikimedia Commons photographers (per-file artist,
licence and attribution retained in the photo receipts); EA Sports/SoFIFA for
the FIFA portrait lane; FIFAIndex for retained shirt references; original PM99
artwork for factory silhouettes and shading. Local use is not permission to
redistribute proprietary artwork; Commons licence obligations also remain.

`season-runtime-selectors-v1.json` records the per-release Stoke selector
coordinates used by inventory-bound runtime captures. Coordinates are inputs,
not proof: the runner must independently OCR the managed-club label on the
Line-Up screen before an attestation can pass. Keeping both controls prevents a
generic or stale coordinate from silently proving the wrong club.

`season-portrait-overrides-v1/football-photo-sources-v2.json` pins the approved
Ronaldo/Yamal source titles and dated credits. The accompanying
`football-photo-review-20261004.json` records the narrowly accepted football
photographs and explicit rejections from the next batch. Generated reviews
bind those decisions to source/BMP hashes before a compact artwork-only
transaction; they do not change ratings, player facts, club ownership or kits.
