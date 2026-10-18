# 2015/16 world V1 playtest defects — 2026-09-04

The local `pm99-2015-16-world` V1 release starts and is mechanically
reproducible, but it is not acceptable as a historically accurate playable
release. Live playtest evidence supersedes the earlier release wording for
these semantic lanes. The V1 artefacts remain immutable evidence; corrections
must produce a new versioned release rather than patching that tree in place.

## Confirmed defects

| Lane | Confirmed defect | Scope | V2 release rule |
| --- | --- | ---: | --- |
| Managers | A written ENT manager can remain the active link for another live club. Diego Simeone (ENT 27) is linked to Atlético Madrid and Newcastle United; Jackie McNamara (ENT 43) is linked to Dundee United and Southampton. | 40 written-manager gate failures | A written manager entity must have exactly one active EQ owner, which must be its declared club. |
| Handling | The legacy English rating transform populated the game’s goalkeeper-only `HANDLING` field from outfield ball-control data. Ibrahim Afellay and Marko Arnautović are direct examples. | 1,938 English outfield ledger rows exceed 20; maximum 91 | Every outfielder must have runtime Handling in 1–20. Ball control is never an input to this field. |
| Player ownership | English and world compiler inputs claim some of the same JUG carriers for different people. | 42 collisions | One compiled carrier has one declared person/club owner across the complete integrated package. |
| Foreign kits | The 268 patched foreign carriers had only archive/header/range readback. No visual acceptance proved the rendered kit was appropriate in the game. The initial renderer stretched a shirt-only image across arbitrary PM99 carrier art, and its palette lookup used a simulator palette rather than the runtime `DAT.PKF` palette. V1–V4 replacements are rejected: V4 corrected the palette but replaced detailed original game art with an overly simple icon. | 268 unreviewed patched carriers | Each patched carrier requires exact archive readback and an explicit in-game visual-review receipt before release. The native-art comparison and rejected candidate history are documented in `2015_16_WORLD_KIT_RENDERER_REMEDIATION_2026-09-08.md`. |

The foreign kit issue is not currently proven to be a malformed BMP container:
the release records retain their original container shape and read back at the
expected hashes. It is a renderer/output-quality failure until a visual review
identifies the precise rasterisation or palette defect.

## Semantic release gate

`scripts/audit_2015_world_release_semantics_v1.py` is a post-compile,
read-only hard gate. It joins the actual final EQ, ENT and JUG files with the
declared English/world inputs and foreign-kit receipt. A non-zero exit is a
release block.

```bash
python3 scripts/audit_2015_world_release_semantics_v1.py \
  --game-tree .local/releases/pm99-2015-16-world \
  --world-package .local/season-workspace-v1/2015-16-final-build/season-package.effective.json \
  --english-player-ledger .local/season-2015-16/english92-2015-16-release-2015-16/player-ledger.json \
  --foreign-kit-receipt .local/season-workspace-v1/2015-16-final-build/foreign-kit-application-receipt.json \
  --kit-review-receipt <approved-kit-review.json> \
  --output .local/operations/2015-16/world-semantic-qa-v1.json
```

Without the explicit kit review receipt the kit lane deliberately fails. This
prevents another byte-valid but visibly poor kit set from being called
release-ready.

## Correction order

1. Build a single integrated V2 package from a known good English base, with
   global manager and player-carrier ownership allocation before any writes.
2. Regenerate English outfield Handling using the bounded goalkeeper-technique
   policy, then verify the actual runtime values by player name.
3. Re-render foreign kits from a proven original-game visual template using
   the runtime `DAT.PKF` palette, generate side-by-side native-art review
   images, and attach explicit approvals. V4 is rejected and must not be
   promoted merely because its byte/readback checks passed.
4. Compile V2 into a new workspace, run this semantic gate, then capture
   in-game proof for representative English and foreign clubs before restoring
   a playable/release label.

The current 2000–2025 source-capture work is unaffected: it is source-only
and cannot promote a new season to playable status without these gates.
