# Composing database and artwork corrections

`register_completed_delta(..., verified_ancestor_chain=[...])` requires an
explicit chain from the current preferred release to the completed candidate.
It never changes the preferred release to an intermediate parent.

Database edges retain the existing package/compiler/build-chain hash checks.
An artwork-only edge keeps its compiler receipt, so it uses separate authority:
the exact parent chain plus one new artwork stage, the immediate parent manifest
hash, unchanged recipe/compiler, and hash-bound plan, application and materialisation.
Both complete inventories must match their games, and every changed path must
be a permitted portrait or compact-kit asset. A stale inherited artwork stage
cannot authorise a later database change.

These checks prove ancestry and byte scope. They do not approve historical
identities, kit designs, portraits, or runtime appearance; those require their
own evidence before promotion. A refused promotion does not require rebuilding
an already verified candidate.

Regression commands:

```bash
PYTHONPATH=.:upstream/pm99-skezmod-db-editor .local/venvs/season-pipeline/bin/python -m pytest -q \
  scripts/test_visual_artwork_ancestry_edge_v1.py \
  scripts/test_completed_delta_verified_ancestry_v1.py \
  scripts/test_paired_kit_ancestry_descriptors_v1.py \
  scripts/test_season_visual_patch_v1.py \
  scripts/test_season_visual_patch_reconstruction_v1.py
```
