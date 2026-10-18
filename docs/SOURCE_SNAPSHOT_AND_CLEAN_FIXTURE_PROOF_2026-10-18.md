# Source protection and clean fixture proof

Machine: joe-Vostro-3350. Session: 01a0592d-fcd5-7262-a637-743a8253d9b4.
Date: 2026-10-18. User explicitly authorized GitHub pushes.

## Published source, not a release approval

All repositories use the new `snapshot/season-toolchain-20261018` branch.
Existing release/default branches were not overwritten or force-pushed. Local
source changes were preserved; deleted historical artifacts were not staged.

- Research: initial source snapshot `f005fe0`, import-isolation fix `0660472`,
  original implementation-byte preservation `80b3fe5`.
- Editor: `707322c489f62a98c34f5df9350d5c1a62e9ffc8`.
- Runner: `b0f0174bdb9eb14288f2d5037e96eff64af1f0ec`.
- Patcher: `75bffb02fd3effd77203e71802d7bc52cfcc4509`.

The parent pins these already-pushed upstream commits. The source snapshot
tracks the launcher, schemas, 1738 script paths, 419 season-definition/data
paths, viewer source and handoffs. No proprietary FDI/PKF/EXE/DLL, downloaded
portraits, local game tree, dependency installation, backup or .local evidence
was newly staged. A pattern scan of the scoped source found no private-key or
recognized GitHub/Anthropic API token strings. This is not a guarantee that an
automated pattern scan proves every file safe or legally redistributable.

Seven otherwise untouched scripts/tests were restored byte-for-byte to the
pre-Sonnet archive after EOF whitespace normalization. This deliberately
preserves historical implementation hash bindings. Their pre-existing final
blank lines are retained rather than cosmetically changing research inputs.

## A hidden dependency found by testing the saved source

The first fresh extraction failed collection: importing normal QA imported
`pm99_season_play_v1`, whose legacy REVISIONS dictionary eagerly loaded all 26
local release locators. Thus the earlier tests passing on Vostro did NOT prove
that these fixtures were independent of the local installations.

Fixed in `0660472`: the backward-compatible revision Mapping loads one stable
snapshot only when explicitly used. Importing capture/QA needs no installed
release locators. Actual explicit revision/playback lookups still fail closed
for absent/invalid registrations. Three regression tests cover pure imports,
legacy Mapping operations and the fail-closed behavior.

Validation actually executed:

- Lead identity/registry/import targeted suite: 66 passed.
- After dependency cleanup restored the disk reserve, the broader related
  regression ran without the previous exclusion: **367 passed** (one marker
  warning). The previously disk-blocked synthetic visibility test now passes;
  no production guard was lowered or mocked away to achieve that.
- Fresh extraction of committed research source, schemas and tracked catalogue,
  plus committed upstream editor app/test source: **141 passed, 1 skipped**.
  No .local directory existed in that extracted source tree. The skipped case
  is the pre-existing generated-backfill integration test in
  test_season_source_intake_from_allocation_v1.py, not an ID-survival assertion.
  Tested at `/tmp/pm99-source-fixtures-fixed.xa66br`.
- This reused the existing Python environment. It did not perform a fresh
  dependency installation, full Git submodule clone, native game build or runner
  capture. Do not claim complete clean-machine season reproducibility.
- Editor deterministic lane with GUI collection excluded: 631 passed, 4 skipped,
  47 deselected. Including the GUI module fails collection because this Python
  environment lacks tkinter. No release-gate green claim for the excluded lane.
- Runner targeted lane: 220 passed, 1 skipped, **1 failure**:
  test_stoke_season_profile_capture_restores_scroll_after_each_return returns
  only one capture where its fixture expects two. This needs investigation;
  it is not evidence of a new database crash. The snapshot preserves the existing
  runner work and is not a validation approval.
- Repository boundary guard passed. No game database or current recipe was
  rebuilt as part of source protection.

## Remaining dependencies

Current registrations still point into local-only game/package/evidence storage.
Publishing the catalogue does not upload those binaries or make those paths
portable. Clean-machine acquisition, pinned-source replay, complete generation
orchestration and a maintained fixture CI lane remain work, as set out in
RERUNNABLE_SEASON_WORKFLOW_AND_RC_PLAN_2026-10-18.md.

The working copies intentionally retain unstaged artifact deletions and the
parked nested `tools/season-preset-viewer` site checkout, which already has its
own original remote. The active Python/HTML recipe-viewer source is tracked in
the parent; the parked site's hosting configuration was not imported. Do not
call the whole workstation clean merely because the source snapshot is pushed.
Upstream UI tests were not run; regenerable frontend dependencies were
subsequently retired with lockfiles retained.

The pre-Sonnet scripts/schema recovery archive was also copied to the verified
Pi volume at
`/srv/hdd/pm99-archive/research/source-snapshots/20261018/pre-sonnet-identity-source-20261017.tar.gz`.
Remote SHA256 matches the local archive:
`8b6396301e2dc97f6f7a226df8765aabd24d27c0c5efc5e00cf24c014cf431f2`.
The small local recovery archive remains; it was not deleted for negligible savings.
