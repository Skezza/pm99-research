# Cached-output replay for legacy PM99 seasons

`scripts/season_pipeline_cached_replay_v2.py` is the honest transition path
for a historical release that already has reviewed PM99 output files but did
not capture sufficient source inputs to regenerate them from scratch.

It is not a compiler and does not reinterpret database data. It writes exact
hash-checked bytes into a new clean game tree only when both of these locks
match:

- the verified original PM99 base tree;
- the canonical season package named by the bundle.

The retained bundle contains only explicitly selected release output files as
content-addressed blobs. It never copies a prior playable directory wholesale,
so it cannot carry a Wine prefix, saves, screenshots, logs or machine state
into a release.

## Portrait policy: fail open

Portraits are deliberately **not** a release blocker. A player without an
approved era-appropriate portrait must be marked `native-no-photo` or
`unresolved` in the season package and must have no active PM99 minifoto
record/loose bitmap. The cached-output stage does not substitute a 1998 carrier
face, a random photo or a placeholder. A later release can add an approved
portrait as an ordinary, independently hash-checked asset change.

Each no-photo decision or failed portrait attempt must also appear in the
machine-readable review queue described in [SEASON_REVIEW_V2.md](SEASON_REVIEW_V2.md).
The queue names the player and club, explains the decision, and confirms the
resulting PM99 native no-photo state.

This is the required policy for the 2000/01--2025/26 programme: historical
data and gameplay must still ship when image research is incomplete.

## Creating a clean replay of the existing 2015 English release

All paths below are local-only examples; the resulting base, bundle and
materialisations stay under ignored `.local/` roots and are not committed.

```bash
# 1. Strip only the old SAVE directory from the known installation and lock
#    every retained base byte.
python3 scripts/season_pipeline_cached_replay_v2.py prepare-clean-base \
  --source-tree .local/pm99-upscale-poc/game \
  --output-tree .local/season-pipeline-v2/pm99-base-clean \
  --base-id pm99-gog-en-1998-clean \
  --exclude-directory SAVE \
  --verified-base-output .local/season-pipeline-v2/pm99-base-clean.json

# 2. Migrate metadata. This remains legacy-migrated; it is not falsely
#    promoted to strict source-provenance status.
python3 scripts/season_package_v2.py migrate-2015 \
  --input-dir .local/season-2015-16/english92-2015-16-editorial-v1-r2 \
  --output .local/season-pipeline-v2/2015-english92-legacy.json

# 3. Retain only gameplay outputs from the already-reviewed reference. The
#    loose-photo directory is optional: missing portraits remain no-photo.
python3 scripts/season_pipeline_cached_replay_v2.py create-bundle \
  --base-tree .local/season-pipeline-v2/pm99-base-clean \
  --reference-tree .local/season-2015-16/english92-2015-16-editorial-v1-r2/game \
  --season-package .local/season-pipeline-v2/2015-english92-legacy.json \
  --bundle-root .local/asset-store/2015-english92-cached-release-v1 \
  --include DBDAT/JUG98030.FDI --include DBDAT/EQ98030.FDI \
  --include DBDAT/ENT98030.FDI --include DBDAT/MINIFOTO.PKF \
  --include DBDAT/MINIESC.PKF --include DBDAT/BIGESC.PKF \
  --include DBDAT/BIGENTR.PKF --include DBDAT/MINIENTR.PKF \
  --include DBDAT/NANOESC.PKF --include MANAGPRE.EXE \
  --include-directory DBDAT/MINIFOTO

# 4. Produce the canonical V2 build plan and then materialise it twice.
python3 scripts/season_pipeline_cached_replay_v2.py write-plan \
  --base-id pm99-gog-en-1998-clean \
  --base-tree .local/season-pipeline-v2/pm99-base-clean \
  --season-package .local/season-pipeline-v2/2015-english92-legacy.json \
  --bundle-index .local/asset-store/2015-english92-cached-release-v1/index.json \
  --adapter scripts/season_pipeline_cached_replay_v2.py \
  --output .local/season-pipeline-v2/2015-english92-replay-plan.json
```

The final materialisations use `season_pipeline_buildplan_v2.py` with the
plan, verified base, bundle index and adapter. Its normal output inventories
and receipts become the release proof. A failed hash, a changed base, an extra
file, a symlink or runtime state stops the build.

## What this closes, and what it does not

It closes repeatable **cached-output** builds for the already qualified 2015
English release: no prior game folder is an input and two new materialisations
must match byte-for-byte.

It does not close strict original-source provenance for 2015 artwork, nor the
foreign competition membership research required for the world edition. New
season packages must capture crop recipes and source content hashes before
their portrait stage is run; then their normal compiler stages can replace
this bridge.
