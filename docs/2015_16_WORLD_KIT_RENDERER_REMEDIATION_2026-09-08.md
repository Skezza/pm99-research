# 2015/16 world kit renderer remediation — 2026-09-08

## Status

**The earlier V1, V2, V3 and V4 candidate renderers are rejected.** They are retained only as
evidence. None was promoted into the playable 2015/16 release.

The later **factory-template V1** is a new, isolated candidate. It replaces
neither the playable 2015/16 release nor its release receipt. The subsequent
**factory-template V2 pattern-structure** candidate retains V1 unchanged and
uses pattern-matched original PM99 artwork for richer folds and garment cuts.
Neither candidate is promoted; an authentic in-game foreign-club visual
capture remains the promotion gate.

## What was actually wrong

The original complaint was accurate: the kit source looked broadly right in
an external image but wrong or high-contrast inside PM99. This was not one
fault.

1. The old renderer projected a modern shirt PNG into an arbitrary compact
   PM99 carrier. Those carriers contain inconsistent legacy player artwork,
   not a stable rectangular shirt slot.
2. The first attempted correction painted a central band over that artwork.
   It visibly crossed heads, arms and unrelated details, making the result
   worse.
3. The foreign-kit lane selected `SIMULDAT/SIMULPCF6.PAL` when choosing
   indexed colours. PM99 displays compact kits through the `DAT.PKF` palette.
   The same byte indices therefore rendered as different colours in-game.

The third point explains the precise outside-versus-runtime discrepancy.

## V4 rendering contract

`scripts/pm99_kit_palette_v1.py` now requires the runtime `DAT.PKF` palette.
`scripts/pm99_compact_kit_template_v1.py` replaces only the compact BMP pixel
lane with a centred, front-facing PM99 shirt-and-shorts icon, retaining each
record's container/header/trailer unchanged. `scripts/pm99_kit_recipe_v1.py`
turns each dated FIFA 16 shirt source into an editable, low-detail recipe:

- dominant kit colours;
- solid, hoops, vertical stripes, halves, or contrasting sleeves; and
- a conservative shorts colour.

It does **not** paste, rescale, or redistribute the original shirt artwork.
The recipe is recorded per carrier in the materialisation JSON, so it is a
small, reviewable input for later bulk editing.

## Candidate lineage

| Candidate | State | Reason |
| --- | --- | --- |
| `sprite-safe-v1` | Rejected | Central-band projection visibly garbled the legacy carrier art. |
| `canonical-shirt-v2` | Rejected | A native carrier silhouette was still an inconsistent legacy pose. |
| `centred-shirt-v3` | Rejected | Centred geometry was correct, but source colours were mapped through the simulator palette. |
| `centred-shirt-runtime-palette-v4` | Rejected | Runtime palette was correct, but the replacement icon was visibly cruder than the original game kit artwork. |

The immutable original materialisation remains:

- `.local/season-pipeline-v2/world-2015-combined-kit-materialisation-final.json`
- SHA-256 `f9dcd0d447c1af26bb92200b6533ab69d312b279c37d2dc8a1cdb30a814602db`

The V4 materialisation and structural audit are:

- `.local/season-pipeline-v2/world-2015-combined-kit-materialisation-centred-shirt-runtime-palette-v4/materialisation.json`
- `.local/season-pipeline-v2/world-2015-combined-kit-materialisation-centred-shirt-runtime-palette-v4/qa.json`

They cover 268 approved foreign carriers and 804 compact-kit records. The
audit verifies every candidate hash, BMP shape, target record header/trailer,
and the deterministic centred-template transparency mask. It reported zero
errors. The other 127 foreign carrier rows remain native fallbacks/gaps; V4
does not claim that they are historically resolved.

## Factory-template V1 candidate

The factory candidate starts with the original PM99 compact-kit catalogue,
rather than inventing a new shirt icon or projecting a modern PNG into a
legacy carrier. The selected original artwork supplies the shirt cut, collar,
seams, folds, shorts, anti-aliasing and dark line work. The dated source PNG
only supplies a compact colour/pattern recipe.

- `MINIESC.PKF` and `NANOESC.PKF` use the reviewed, front-facing original
  `EQ960004.BMP` artwork.
- `RIDIESC.PKF` is a tiny PM99 pattern swatch, not a reduced shirt silhouette;
  its reviewed template is selected by pattern type.
- Every RGB-to-index choice is made against the runtime `DAT.PKF` palette,
  never `SIMULDAT/SIMULPCF6.PAL`.
- The target carrier's BMP wrapper and all bytes outside its indexed-pixel
  lane remain byte-identical. Only the reviewed template's rendered pixels are
  copied into that target wrapper.

The candidate receipt is:

- `.local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v1.json`;
- `.local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v1/`.

Its independent audit is
`.local/kit-visual-forensics-v1/2015-16/factory-template-audit.json`: **268
approved foreign carriers, 804 compact-kit records, zero errors**. The audit
hash-checks every dated source, regenerates every bitmap, checks the chosen
original-template hash, checks the target BMP wrapper, and rejects any
simulator-palette provenance.

Visual QA is not inferred from bitmap validity. These sheets render indexed
candidate pixels using the actual runtime palette:

- `.local/kit-visual-forensics-v1/2015-16/factory-candidates-MINIESC.png`;
- `.local/kit-visual-forensics-v1/2015-16/factory-candidates-NANOESC.png`;
- `.local/kit-visual-forensics-v1/2015-16/factory-candidates-RIDIESC.png`.

The direct six-carrier original/live/factory comparison is
`.local/kit-visual-forensics-v1/2015-16/original-live-factory-v1.png`. It
shows the old live art's runtime palette corruption beside the factory
candidate's preserved PM99-era illustration.

The candidate was applied only to the disposable tree
`.local/season-workspace-v1/2015-16-kit-factory-template-v1-game`. Its
kit-only tree audit is
`.local/season-workspace-v1/2015-16-kit-factory-template-v1-receipts/kit-only-game-tree-audit.json`:
4,587 non-kit files unchanged, five kit archives read back, and 804 foreign
kit events read back. A local smoke run reached PM99's title screen without a
Wine debugger or crash at
`.local/kit-runtime-evidence-factory-v1/2015-16-smoke/summary.json`.

This is still **not promotion evidence**: the local selector capture can pick
the wrong X child window after the title screen. Do not call the factory
candidate release-ready until an outer-window capture shows a foreign club in
PM99 and a reviewer accepts that runtime image.

### Remote runtime palette/renderer proof

The remote runner's selector exposes selectable English carriers but not a
foreign club directly. To prove PM99's actual indexed rendering path, a second
disposable copy temporarily rendered Barcelona's factory recipe in Arsenal's
normally selectable carrier 309. This is explicitly a renderer/palette proof,
**not an Arsenal kit or a historical database assignment**.

- Probe receipt:
  `.local/kit-runtime-evidence-factory-v1/2015-16-barcelona-selector-probe-r2.json`.
  It changed exactly three compact-kit records (MINIESC, NANOESC, RIDIESC),
  with every changed byte confined to carrier 309's record extent.
- Remote runner summary:
  `upstream/pm99-runner/docs/artifacts/pm99_runner/world2015_factory_barcelona_selector_20260908/selector_discovery_summary.json`
  (`success: true`, one observation, no Wine debugger).
- Raw PM99 window frame:
  `upstream/pm99-runner/docs/artifacts/pm99_runner/world2015_factory_barcelona_selector_20260908/screens/007_select_division_01.png`.

The first Premier League selector icon in that raw frame is the dark-blue and
maroon Barcelona hoops. It is rendered by PM99 using the candidate's
`DAT.PKF`-indexed assets, which rules out the old external-preview-only colour
illusion. It does not replace the remaining gate: an authentic foreign-club
runtime route must still be captured before release promotion.

## Factory-template V2 pattern-structure candidate

V1 proved that using original PM99 artwork is materially better than drawing a
new generic kit. The next visual review identified a remaining limitation:
using one clean, plain original template for nearly every full-size shirt
preserved a general silhouette but discarded the original artist's
pattern-specific folds, waistband cuts, sleeve seams and trouser-leg shadows.

V2 changes only the explicit template-selection policy; it keeps V1's
recipe-only input, `DAT.PKF` palette, indexed-pixel-only write contract and
independent reproduction audit. The reviewed source templates are fixed in
every receipt:

| Recipe geometry | Original PM99 template carrier | Purpose |
| --- | ---: | --- |
| Plain/unknown | 4 | Clean front-facing shirt with a clear collar and shorts. |
| Vertical stripes | 2 | Original vertical striping with pronounced shirt folds. |
| Hoops | 1252 | Original horizontal bands, waistband separation and darker leg shading. |
| Halves/quarters | 3 | Original split-front illustration. |
| Contrasting sleeves | 309 | Original shoulder and contrasting-sleeve cut. |

This is a versioned forward candidate, not a rewrite of V1:

- Materialisation:
  `.local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v2-pattern-structure.json`.
- Content-addressed assets:
  `.local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v2-pattern-structure/`.
- Independent reproduction audit:
  `.local/kit-visual-forensics-v1/2015-16/factory-template-v2-pattern-structure-audit.json`:
  **268 approved foreign carriers, 804 assets, zero errors**.
- V1 regression audit:
  `.local/kit-visual-forensics-v1/2015-16/factory-template-v1-regression-audit.json`:
  **268 approved foreign carriers, 804 assets, zero errors**. V2 therefore
  cannot have changed the existing V1 candidate behind its back.
- V1-to-V2 differential audit:
  `.local/kit-visual-forensics-v1/2015-16/factory-template-v1-v2-differential-audit.json`:
  **804 assets checked, 270 intentional pattern-template changes, 534
  unchanged, zero errors**. It proves that plain-kit assets did not drift and
  that every changed asset corresponds to an explicitly different template.
- Runtime-palette contact sheets:
  `.local/kit-visual-forensics-v1/2015-16/factory-v2-pattern-structure-MINIESC.png`,
  `.local/kit-visual-forensics-v1/2015-16/factory-v2-pattern-structure-NANOESC.png`, and
  `.local/kit-visual-forensics-v1/2015-16/factory-v2-pattern-structure-RIDIESC.png`.

V2 was applied only to the disposable tree
`.local/season-workspace-v1/2015-16-kit-factory-template-v2-pattern-structure-game`.
The kit-only tree audit at
`.local/season-workspace-v1/2015-16-kit-factory-template-v2-pattern-structure-receipts/kit-only-game-tree-audit.json`
passed: **4,587 non-kit files unchanged, all five kit archives read back, and
804 foreign-kit events read back**.

The remote runner also captured V2 through PM99's real indexed rendering path.
As with V1, this is intentionally a disposable palette/renderer proof: the
Barcelona recipe temporarily occupies Arsenal carrier 309 because PM99's
new-game selector exposes English but not foreign carriers. The probe receipt
is `.local/kit-runtime-evidence-factory-v2/2015-16-barcelona-selector-probe.json`;
it changes only the three compact carrier-309 records. The raw PM99 frame is
`upstream/pm99-runner/docs/artifacts/pm99_runner/world2015_factory_v2_barcelona_selector_20260908/screens/007_select_division_01.png`.
It is **not** a historical Arsenal kit or foreign-club gameplay evidence.

## Factory-template V3 native-boundaries candidate

V3 is a further separate candidate prompted by visual review of V2's rough
shoulder pattern edges and occasional shirt/shorts colour bleed. It does not
replace V1 or V2. Rather than add a new hand-drawn mask, it uses deterministic
computer-vision techniques on the already reviewed original PM99 artwork:

- Otsu chroma segmentation identifies the native coloured and neutral garment
  panels in the selected stripe, hoop, or sleeve template. Two constrained
  majority passes remove isolated anti-aliasing speckles while retaining the
  original shoulder and sleeve contour.
- The waist is found from the compact silhouette's row-width valley; V3 paints
  the shorts from their own recipe below that point and preserves a restrained
  native-luminance crease across the two waist rows.
- The input remains only the dated colour/pattern recipe. No modern source
  pixels, generated art, or carrier wrapper bytes are introduced.

The V3 deterministic tests include a deliberately opposed red-shirt/
green-shorts case, proving that no non-structural shirt-recipe pixel can occur
below the inferred waist. The V3 candidate and independent evidence are:

- Materialisation:
  `.local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v3-native-boundaries.json`.
- Assets:
  `.local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v3-native-boundaries/`.
- Independent reproduction audit:
  `.local/kit-visual-forensics-v1/2015-16/factory-template-v3-native-boundaries-audit.json`:
  **268 approved foreign carriers, 804 assets, zero errors**.
- Runtime-palette visual sheets:
  `.local/kit-visual-forensics-v1/2015-16/factory-v3-native-boundaries-MINIESC.png`,
  `.local/kit-visual-forensics-v1/2015-16/factory-v3-native-boundaries-NANOESC.png`, and
  `.local/kit-visual-forensics-v1/2015-16/factory-v3-native-boundaries-RIDIESC.png`.
- Focused V2/V3 visual comparison:
  `.local/kit-visual-forensics-v1/2015-16/v2-v3-native-boundary-benchmark.png`.

The isolated V3 tree is
`.local/season-workspace-v1/2015-16-kit-factory-template-v3-native-boundaries-game`.
Its tree audit at
`.local/season-workspace-v1/2015-16-kit-factory-template-v3-native-boundaries-receipts/kit-only-game-tree-audit.json`
passed: **4,587 non-kit files unchanged, five kit archives and 804 foreign
events read back**.

The remote V3 renderer proof is at
`upstream/pm99-runner/docs/artifacts/pm99_runner/world2015_factory_v3_barcelona_selector_20260908/screens/007_select_division_01.png`.
As before, it temporarily renders Barcelona into selectable Arsenal carrier
309 solely to prove PM99's rendering path; it is not an Arsenal historical kit
or a foreign-club gameplay capture.

## Factory-template V4 native-hem-contour candidate

V3's remaining visual imperfection was the lower-right shirt tail. The PM99
factory silhouette is asymmetric around the waist: it shifts right before the
shorts widen. A single horizontal split therefore produced a wobbly overlap.
V4 retains the V3 native-region and no-bleed logic, then derives a smooth
per-column hem from the waist row's observed centre and width. Only the final
right third lifts by one or two native pixels; the original silhouette,
transparency and outer outline are not redrawn. A slightly deeper crease is
applied on the shirt-edge pixel, so kits with similarly coloured shirts and
shorts still read as two garments.

V4 is also separate from every prior candidate:

- Materialisation:
  `.local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v4-native-hem-contour.json`.
- Assets:
  `.local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v4-native-hem-contour/`.
- Independent audit:
  `.local/kit-visual-forensics-v1/2015-16/factory-template-v4-native-hem-contour-audit.json`:
  **268 approved foreign carriers, 804 assets, zero errors**.
- Visual evidence:
  `.local/kit-visual-forensics-v1/2015-16/v3-v4-native-hem-contour-benchmark.png` and
  `.local/kit-visual-forensics-v1/2015-16/factory-v4-native-hem-contour-MINIESC.png`.
- Isolated tree audit:
  `.local/season-workspace-v1/2015-16-kit-factory-template-v4-native-hem-contour-receipts/kit-only-game-tree-audit.json`:
  **4,587 non-kit files unchanged, five kit archives and 804 foreign events
  read back**.
- Remote PM99 renderer proof:
  `upstream/pm99-runner/docs/artifacts/pm99_runner/world2015_factory_v4_barcelona_selector_20260908/screens/007_select_division_01.png`.

The V4 right-hem logic is renderer-level and source-season-independent. Once
this candidate is accepted, every future season can use the same versioned
renderer and its no-bleed tests; it is not a per-season hand-art correction.
The remote capture remains a temporary Barcelona-in-Arsenal selector proof,
not a historical Arsenal kit or foreign-club gameplay evidence.

## Read-only visual receipt and isolated runtime test

The runtime-palette comparison is:

- `.local/kit-visual-review-v4/2015-16/foreign-kit-comparison.png`
- `.local/kit-visual-review-v4/2015-16/foreign-kit-comparison.json`

It compares legacy and V4 MINIESC candidates for Barcelona, Real Madrid,
Juventus, Bayern Munich, Ajax and Galatasaray using `DAT.PKF`'s actual runtime
palette. It confirms the palette correction but also shows the V4 icon is too
simple; it is rejection evidence, not an approval.

The direct original/live/V4 forensic comparison is:

- `.local/kit-visual-forensics-v1/2015-16/original-live-v4.png`
- `.local/kit-visual-forensics-v1/2015-16/original-live-v4.json`

It shows the original PM99 BMPs retain detailed, pose-aware shirt/shorts art,
whereas V4 replaces it with an inappropriate generic silhouette. Future work
must start from an original-game visual template and prove a rendered result
against that template before any candidate application.

V4 was applied only to this disposable tree:

- `.local/season-workspace-v1/2015-16-kit-runtime-palette-v4-game`

The tree-only audit at
`.local/season-workspace-v1/2015-16-kit-runtime-palette-v4-receipts/kit-only-game-tree-audit.json`
passed: 4,587 non-kit files were unchanged, all five kit archives read back,
and all 804 foreign-kit events read back. The local runner reached the title
screen and the club-selection flow without a Wine debugger or crash. Its
outer-window title screenshot is:

- `.local/kit-runtime-evidence-v4/manual/00_title.png`

The selector automation currently captures an inner black child window even
though its flow succeeds. That capture defect must be corrected before it is
used as kit visual evidence.

## Re-run commands

```bash
python3 scripts/rerender_2015_world_kits_shading_v1.py \
  --materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-final.json \
  --clean-dbdat .local/season-pipeline-v2/english92-clean-release-2015-16-20260830/DBDAT \
  --output-dir .local/season-pipeline-v2/world-2015-combined-kit-materialisation-centred-shirt-runtime-palette-v4 \
  --output .local/season-pipeline-v2/world-2015-combined-kit-materialisation-centred-shirt-runtime-palette-v4/materialisation.json

python3 scripts/audit_2015_world_kit_rerender_v1.py \
  --source-materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-final.json \
  --rerendered-materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-centred-shirt-runtime-palette-v4/materialisation.json \
  --clean-dbdat .local/season-pipeline-v2/english92-clean-release-2015-16-20260830/DBDAT \
  --output .local/season-pipeline-v2/world-2015-combined-kit-materialisation-centred-shirt-runtime-palette-v4/qa.json
```

The factory candidate is a separate lineage; do not overwrite any rejected
candidate directory with it:

```bash
python3 scripts/rerender_2015_world_kits_factory_v1.py \
  --materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-final.json \
  --clean-dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --output-dir .local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v1 \
  --output .local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v1.json

python3 scripts/audit_2015_world_factory_kit_candidates_v1.py \
  --source-materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-final.json \
  --candidate-materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v1.json \
  --clean-dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --output .local/kit-visual-forensics-v1/2015-16/factory-template-audit.json
```

The V2 pattern-structure candidate is separately reproducible:

```bash
python3 scripts/rerender_2015_world_kits_factory_v2.py \
  --materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-final.json \
  --clean-dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --output-dir .local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v2-pattern-structure \
  --output .local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v2-pattern-structure.json

python3 scripts/audit_2015_world_factory_kit_candidates_v2.py \
  --source-materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-final.json \
  --candidate-materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v2-pattern-structure.json \
  --clean-dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --output .local/kit-visual-forensics-v1/2015-16/factory-template-v2-pattern-structure-audit.json
```

The V3 native-boundaries candidate is separately reproducible:

```bash
python3 scripts/rerender_2015_world_kits_factory_v3.py \
  --materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-final.json \
  --clean-dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --output-dir .local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v3-native-boundaries \
  --output .local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v3-native-boundaries.json

python3 scripts/audit_2015_world_factory_kit_candidates_v3.py \
  --source-materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-final.json \
  --candidate-materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v3-native-boundaries.json \
  --clean-dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --output .local/kit-visual-forensics-v1/2015-16/factory-template-v3-native-boundaries-audit.json
```

The V4 native-hem-contour candidate is separately reproducible:

```bash
python3 scripts/rerender_2015_world_kits_factory_v4.py \
  --materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-final.json \
  --clean-dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --output-dir .local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v4-native-hem-contour \
  --output .local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v4-native-hem-contour.json

python3 scripts/audit_2015_world_factory_kit_candidates_v4.py \
  --source-materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-final.json \
  --candidate-materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v4-native-hem-contour.json \
  --clean-dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --output .local/kit-visual-forensics-v1/2015-16/factory-template-v4-native-hem-contour-audit.json
```

## Remaining gate

Do not replace the live 2015/16 world tree with the rejected legacy V4,
factory-template V1, factory-template V2, factory-template V3, or
factory-template V4. Factory-template V4 has met the original-template,
`DAT.PKF`, native-pattern/waist/hem-boundary, full materialisation,
independent-reproduction, isolated tree, and temporary runner-renderer gates.
Its remaining kit gate is a correct outer-window **foreign-club**
selector/gameplay screenshot and explicit runtime visual acceptance. Manager
ownership, player ownership and Handling defects remain independent 2015/16
V2 blockers.

## Factory-template V5 native tonal-depth transfer — 2026-09-10

Later in-game review accepted V4's palette, silhouette, shoulder, waist and
hem corrections but found the recoloured cloth visibly flatter than original
PM99 artwork. A native-resolution comparison confirmed the cause: V4 mapped
factory luminance through a narrow multiplier, causing distinct highlights
and folds to collapse onto the same runtime-palette entries.

V5 keeps V4's geometry and byte-safety rules, but treats the selected original
PM99 illustration as a relative tonal-depth map. It independently measures
shadow, midtone and highlight percentiles for the shirt pattern panels and
shorts, then maps the dated recipe colour through those bands. Shadows move
towards black and highlights towards white; no generated image pixels or
modern shirt pixels are copied. Original dark line work, collar, seams,
transparency, garment boundaries and the asymmetric hem remain intact.

Evidence:

- renderer: `scripts/pm99_factory_kit_renderer_v5.py`;
- full candidate: `.local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v5-native-tone-transfer.json`;
- independent audit: `.local/kit-visual-forensics-v1/2015-16/factory-template-v5-native-tone-transfer-audit.json` — 268 carriers, 804 assets, zero errors;
- runtime-palette sheet: `.local/kit-visual-forensics-v1/2015-16/factory-v5-native-tone-transfer-MINIESC.png`;
- 2014/15 Stoke runtime proof: `upstream/pm99-runner/docs/artifacts/pm99_runner/kit_v5_2014_15_stoke_20260910_r3/screens/008_pick_stoke.png` and `019_dashboard_select_finance.png`;
- 2015/16 kit-only tree audit: `.local/season-kit-runtime-overlays-v1/2015-16/v5/kit-only-game-tree-audit.json` — 4,587 non-kit files unchanged and 804 foreign records read back.

The source-backed seasonal renderer now records V5 explicitly in its render
receipt. `scripts/apply_post1999_factory_kit_v5_overlay.py all` applied the
same renderer to 25 preferred post-1999 runtimes: 92 English clubs per season,
exactly three compact-kit archive changes per runtime, and no database or
executable changes. The separate 2015/16 worldwide lane retains its certified
92 English kits, applies V5 to 268 sourced foreign carriers and leaves 127
declared native fallbacks unchanged. Pre-V5 2015/16 compact archives remain in
`.local/season-kit-runtime-overlays-v1/2015-16/v5/pre-v5/`.
