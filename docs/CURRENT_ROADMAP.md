# Current Editor Roadmap

This is the active roadmap for the PM99 editor.

The historical plans under `docs/HISTORY/enhancement_plans/` are retained for
provenance, but they are not the current execution plan.

## Product Direction

The editor should be built from parser-backed, writable contracts first.

- Default product flows should prefer strict record boundaries and confirmed
  field contracts.
- Heuristic scanners and probes remain useful, but they are fallback or
  investigation tools, not the primary source of truth.
- Unknown regions should be preserved until their layout is confirmed.

## Current Product Shell

The active desktop product path is now the refreshed club-first Tk shell exposed
through `app.gui` and implemented in `app/gui_refresh.py`.

- The GUI resolves a full PM99 database set (`JUG*.FDI`, `EQ*.FDI`, `ENT*.FDI`)
  from any one selected file.
- Startup now prioritizes editor readiness:
  clubs and coaches load first, then the player catalog is deferred.
- The player catalog still uses the full parser + fallback recovery path, but it
  now loads on demand and can warm in the background after the shell becomes
  usable.
- Reverse-engineering tools stay available in `Tools -> Advanced Workspace`
  instead of driving the main editor workflow.
- The right-hand editor remains the canonical staged-edit surface; saves are
  still validated through the shared reopen validation path.

## Near-Term Product Milestones

1. Finish roster parity.
   - Complete the unresolved legacy inline roster family so more clubs resolve
     through confirmed roster mappings instead of falling back to “unavailable”.
   - Keep the club editor, CLI, and Advanced workspace aligned on the same
     authoritative roster contracts.

2. Expand editor parity cautiously.
   - Improve coach linkage resolution so club cards can route into meaningful
     linked coach edits.
   - Continue promoting only parser-backed fields into the normal edit surface.

3. Add an asset/bitmap discovery track.
   - Treat bitmap / image assets as part of the product plan, even if they are
     not yet first-class in the editor UI.
   - Identify where `BMP` / related references are stored in the PM99 data and
     formalize a read-only contract first.
   - Use the Advanced Workspace bitmap-reference probe as the first discovery
     surface, then promote richer asset tooling only after the backing contract
     is stable.
   - Build a future asset browser/editor surface only after the file references,
     ownership model, and write safety are understood.

## Immediate Baseline

1. Make the default editor load path strict-first.
   - Prefer real FDI entry boundaries and parser-backed records.
   - Use the embedded scanner only to fill gaps.

2. Stabilize the player contract before expanding writes.
   - Keep `PlayerRecord` as the canonical player model.
   - Finish unresolved fields such as `weight`.
   - Lock down the user-facing meaning of the trailing attribute bytes.

3. Strengthen the team contract around proven roster linkage.
   - Treat `EQ -> JUG` linked roster extraction as the authoritative roster path.
   - Continue reverse engineering the unresolved legacy inline roster mode.
   - Keep heuristic team metadata parsing clearly labeled as partial.

4. Expand write support only after read support is proven.
   - Do not add synthetic writes into unresolved regions.
   - Preserve unknown bytes by default.
   - Allow broader structural rewrites only when parser-backed read/write rules
     are documented and tested.

5. Clean the codebase by separating product and investigation paths.
   - Product modules should expose stable APIs.
   - Scripts and heuristic probes should stay available, but clearly outside the
     core editor path.
   - Delete obsolete code only after a strict replacement exists.

## Current Priorities

- Replace remaining heuristic-first editor paths with strict-first behavior.
- Extend team-side authoritative editing beyond read-only linked rosters, while keeping writes inside proven fixed-size overlays.
- Continue promoting same-entry authoritative roster families from read-only analysis into explicit fixed-size overlay contracts.
- Keep the proven team roster edit surfaces aligned across the shared action layer, CLI, and GUI.
- Add a read-only asset discovery path for bitmap-backed content once the
  reference contract is stable, then promote it into the editor shell only when
  the ownership / write story is clear.
- Keep confirmed parser-backed inspection/reporting contracts visible in the GUI as well as the CLI, while leaving unstable heuristic investigation flows in tools-first surfaces until their contracts settle.
- Prefer persistent in-app workspaces (for example, the `Analysis` tab) over transient dialogs when a confirmed inspection surface becomes part of the normal editor workflow.
- Treat “save succeeded” and “database is healthy” as separate checks:
  the main GUI save path should keep running a parser-backed reopen validation after write,
  and equivalent CLI validation should stay available through the shared action layer.
- Keep row-shape confidence and mapping confidence separate for same-entry fallbacks:
  the current preferred fallback families now share the confirmed `xor_pid + 0x61 0x61 0x61`
  row shape, but only the strongest mappings should be promoted into write-safe overlays.
- Finish the unresolved team roster families beyond the currently supported same-entry overlay set
  (`same_entry_authoritative` plus the strongest proven fallback) before attempting broader
  team structural writes.
- Use the now-broader `player-inspect` read path on non-indexed files to drive the remaining
  legacy player parity work, especially non-indexed `weight` and the trailing attribute contract.
- The legacy `marker + 14` weight candidate is now promoted for records that expose a real
  dedicated slot before the trailing attribute window. The remaining weight work is now about
  corpus validation across more legacy shapes, not whether the slot exists at all.
- Keep the legacy weight validation visible in the same confirmed inspection surfaces: the CLI
  profiler and the GUI `Inspect Indexed Player Byte Profiles...` view should continue to report
  both the indexed control-set evidence and the real name-only parser-path cross-check.
- Keep the unresolved tail-prefix bytes on the same footing: they are now a confirmed read-side
  probe exposed by `player-inspect`, `player-tail-prefix-profile`, and the GUI analysis view,
  but they still stay out of the normal edit contract until the binary-side consumer is found.
- The latest binary evidence narrows that search: `DBASEPRE.EXE`'s indexed parser helper
  materializes the confirmed suffix/physical fields into fixed struct offsets, but it still
  does not reveal comparable fixed-offset stores for the trailing attribute window. Instead,
  it bulk-copies the late opaque region into a sidecar area after `[player + 0x6E]` /
  `[player + 0x6F]`. Treat the tail prefix as a structural signature / sidecar contract
  unless a later consumer proves otherwise.
- Keep using the new tail-prefix histograms to drive the next RE step: the current indexed
  corpus strongly suggests `Attr 2` is a low-cardinality class marker (`107` vs `25`) rather
  than a normal stat, so the next binary target should be consumers that branch on that class.
- Use the now-formalized tail-layout split in future work:
  `attributes[0..2]` sit in the final variable-length block payload, while `attributes[3..11]`
  sit in the fixed trailer. That means the remaining open question is the meaning of the front
  block bytes, not the placement of the already-named trailer stats.
- The byte immediately after indexed `weight` is now also surfaced as a read-only probe
  (`post_weight_byte` / `postwt`). `FUN_0043d170` copies it into `[player + 0x48]` before
  it advances into the three variable-length string blocks, so it is now part of the
  stable parser-backed analysis surface even though the label is still unknown.
  The current evidence is stronger than “unknown byte”, though: `FUN_0043d960` tests
  `[player + 0x1D]` and `[player + 0x48]` against the same lookup value, and the
  known caller sits inside the search-options builder where that value is resolved
  through the same nationality table used by the player-view nationality label.
  The anchored indexed corpus currently shows about a `94%` exact match between
  `post_weight_byte` and `nationality`. Treat it as a secondary nationality/search
  key until a cleaner semantic label is proven.
  The remaining mismatch cases are now explicitly surfaced in the shared profile view;
  the current dominant divergence is `postwt=30 -> nat=31`, followed by `30 -> 45`,
  and `30` is also the dominant grouped `postwt` key in that non-mirror subset.
  More importantly, that dominant group is no longer just “nearby IDs”: on the
  current real corpus, `57` of the `66` `postwt=30` mismatches collapse to the
  home-nation IDs `31`, `45`, `19`, and `32`, which makes a grouped UK/Ireland-style
  search umbrella the strongest current hypothesis.
  That makes the next RE target sharper: explain the grouped/non-mirror nationality
  buckets instead of re-proving the mirror cases.
- Use the new direct `a0/a1/a2` tail-prefix filters to isolate the two current `Attr 2`
  classes and hunt for a consumer that branches on that split.
- The current `Attr 2` split is now sharper than before:
  `a2=25` collapses to the single `[1, 0, 25]` family, while `a2=107` contains the rest
  of the variation. The next binary trace should specifically target code that distinguishes
  those two classes.
- The fixed trailer byte is now exposed alongside that tail prefix in the same shared
  profile surface. Treat it as a secondary structural discriminator:
  for example, `a2=25` plus `trail=19` currently isolates the dominant combined signature
  `[1, 0, 25 | trail=19]`, but it is still not safe to name until the consuming code is found.
- The next byte after that fixed trailer is now also exposed (`sidecar`), because the
  binary consumes `[player + 0x6E]` and `[player + 0x6F]` separately before the later
  sidecar block. That makes `sidecar` a tertiary discriminator:
  the current `a2=25` + `trail=19` branch splits into `[... sidecar=0]` and
  `[... sidecar=1]`. The next binary trace should target the later consumer of the copied
  `[player + 0x70]` sidecar region, not the loader itself.
- This is no longer just a loader-side fact: at least one `DBASEPRE.EXE` UI path also reads
  `[player + 0x6E]` and `[player + 0x6F]` individually and renders them as separate one-byte
  values. That strengthens the contract boundary (two discrete subfields plus a copied sidecar),
  but the semantic labels are still unknown.
- The next binary trace should stay focused on the actual late consumer of the indexed
  variable blocks / copied sidecar region. The loader boundary is now materially clearer:
  the open questions are the exact semantic role of the nationality-like `post_weight_byte`,
  the front tail-prefix bytes, and the later sidecar consumer, not whether those bytes exist.
- Complete the remaining player field map, especially legacy/non-indexed parity and the trailing attribute contract.
- Finish the front of the trailing 12-byte player attribute window:
  slots `3 .. 11` are now strongly corroborated, but slots `0 .. 2` still need naming.
- Keep `attributes[0 .. 2]` out of the normal edit surface until they are named; treat them as
  read-only probe bytes rather than user-facing stats.
- Add tests whenever a formerly heuristic rule becomes parser-backed.
