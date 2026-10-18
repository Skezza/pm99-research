# PM99 Season Package V2

`pm99-season-package-v2` is the portable, canonical input contract for a
historical PM99 database. It is metadata only: it never contains PM99 game
files, copied EXEs, FDIs, PKFs, or licensed source images. The build pipeline
resolves its content-addressed artifacts from a separately managed asset store
and a verified local game installation.

V2 is designed for seasons from 1999/00 through 2025/26. It is independent of
the build implementation: a compiler can change, but a season package must
continue to describe the same data and inputs.

## Why a package exists

A playable release is a materialised output, not the source of truth. Editing a
previous game folder makes it impossible to establish which changes came from
which data. A V2 package instead declares:

- Existing PM99 club, player and manager carrier IDs and their season facts.
- Player ratings and the method/evidence behind them.
- The opening XI, substitutes, declared formation and exact PM99 tactics-grid
  coordinates for every club in scope.
- Kit, portrait-original, portrait-crop and conversion-receipt identities.
- The calendar target and exact calendar patch output identity.
- Static/runtime proof receipts and the hashes that bind them to a build.

The compiler must create a new package output from these inputs. It must not
treat an earlier output folder as an authoritative source.

The first native binary adapter is documented in
[Season-Package Compiler V2](SEASON_PACKAGE_COMPILER_V2.md). It accepts only
a strict native package and writes the proven JUG/EQ/ENT lanes in a clean
materialisation; legacy migration output remains an inventory/provenance bridge
until it has been replaced with a native package.

## Contract files and commands

- [pm99-season-package-v2.schema.json](../schemas/pm99-season-package-v2.schema.json)
  is the published JSON Schema.
- [season_package_v2.py](../scripts/season_package_v2.py) adds canonical-byte
  and cross-record validation that JSON Schema cannot express.

```bash
python3 scripts/season_package_v2.py validate --package season-package.json
python3 scripts/season_package_v2.py validate --package season-package.json --strict
python3 scripts/season_package_v2.py migrate-2015 \
  --input-dir .local/season-2015-16/english92-2015-16-build31-centred-tactics-correct \
  --output .local/season-2015-16/2015-16-english92.v2.json
```

`--strict` accepts only native V2 packages with no known migration gaps. A
legacy adapter output is useful as a measured inventory, but is intentionally
not a release-ready package.

## Canonical and portable form

The one accepted on-disk encoding is UTF-8 JSON, NFC-normalised strings, sorted
object keys, compact separators, and one final newline. `write_canonical_package`
is the only writer. Validation rejects:

- Absolute Unix or Windows filesystem paths.
- Parent-directory artifact paths.
- Timestamps such as `generated_at_utc` or `created_at`.
- Non-NFC strings, duplicate IDs, unsorted ID collections and invalid SHA-256
  strings.
- Unknown artifact/source/proof references.

Artifact IDs are logical identifiers, not paths. Every concrete artifact has a
lowercase SHA-256. A source points to a hashed evidence artifact; a player
rating points to at least one source. A URL alone is never provenance.

This deliberately permits the same package to be built on Linux, macOS and
Windows. Machine-specific paths and build dates belong in a non-reproducible
execution log, never in the package.

## Core entities

`clubs`, `players` and `managers` use package-record IDs plus the PM99 carrier
ID that a compiler may write. Both are local to that package; carrier IDs are
an implementation binding and must remain unique within a collection. Strict
native packages also carry `identity_id` for each club and `person_id` for each
player/manager. Those are reconciled real-world identities, shared through the
[Editorial Timeline V1](EDITORIAL_TIMELINE_V1.md), and are deliberately not
derived from a PM99 carrier number.

Each player has:

- Facts: date of birth, nationality, height, weight, primary position, known
  fine roles and shirt number.
- Carrier family (for example `dd6360` or `dd6361`). This stops a compiler
  applying a mode-specific write contract to the wrong record family.
- The ten visible PM99 rating values, including handling, plus a declared
  rating method, proof grade and one or more source IDs.

Each club has its manager and full roster plus an opening fixture declaration:
exactly eleven unique starters, distinct substitutes, an outfield formation
that totals ten, and eleven four-value tactics positions. This is deliberate:
formation text is not sufficient to reproduce an opening tactical state.

The exception is an existing foreign mode-1 carrier. It may declare
`opening: {"policy": "preserve-existing-mode1", "proof": ...}` because the
qualified compiler preserves that carrier's opaque opening-state region
byte-for-byte. This avoids inventing a tactical grid for an unplayable club.
Its `division` may be the descriptive value
`preserve-existing-mode1-membership`; foreign membership is not written.
Mode-0 clubs still require the complete opening fixture declaration above.

V2 does not claim unknown PM99 fields are editable. A package can only carry
fields whose write contracts have been proven; preserve-only bytes remain the
compiler's responsibility.

## Assets

Each club has exactly one kit declaration referencing one or more hashed PM99
kit render artifacts. Each player has exactly one portrait declaration:

- `applied` requires a hashed original, a hashed crop and the hashed conversion
  receipt/container it was written into.
- `native-no-photo` records an intentional no-photo state.
- `unresolved` records a research gap explicitly. At materialisation time it
  must become PM99's native no-photo state; it may not silently reuse a 1999
  carrier image or block an otherwise sound season release.

`native-no-photo` and `unresolved` may carry a `review_reason`: the
machine-readable explanation shown in the post-playtest portrait review queue.
See [SEASON_REVIEW_V2.md](SEASON_REVIEW_V2.md) and
[Editorial Timeline V1](EDITORIAL_TIMELINE_V1.md) for the source-overlay
workflow that turns ordinary feedback into a new build without editing a
released game folder.

A native package should also keep an editable crop recipe as an approved asset
in the asset store. The schema permits a `crop_recipe_artifact_id`; a release
compiler should require it for every non-default crop. The migration adapter
does not invent recipes that old receipts did not retain.

## Proof grades

The grade describes the evidence, not how much the editor would like to edit:

| Grade | Meaning |
| --- | --- |
| `source-captured` | Exact source content was retained and hashed. |
| `source-receipt` | A local receipt proves a source-processing step. |
| `reviewed-editorial` | A documented human editorial decision. |
| `static-contract` | Parser/reference/inventory checks passed. |
| `runtime-wine` | Reached and verified in the Wine research environment. |
| `runtime-native-windows` | Verified in a native Windows PM99 run. |
| `legacy-migrated` | Derived from an older receipt; not sufficient for strict release. |

The build release receipt needs both a complete static inventory and runtime
proof tied to the final package/output hashes. Native-Windows proof is a
release-candidate qualification when the executable/runtime layer changes; it
is not a per-season compiler input or an excuse to block a data-only rebuild
that already passes its Wine smoke test.

## 2015 English adapter: what it can and cannot claim

`migrate-2015` reads a previous English-92 build's manifest, player ledger,
manager audit, calendar receipt, optional face receipt and kit receipt. It
creates a canonical V2 metadata package and hashes retained inputs, portrait
originals/crops, kit renders and output-container identities where they are
available. It never copies game data into the package.

It cannot faithfully upgrade these existing facts:

- Original web pages were not captured with content hashes. Old URLs are not a
  replacement for source content.
- Most old portrait rows retain pixels but no per-player crop recipe. They can
  be reused by hash, not regenerated from the original image alone.
- The old face receipt has one `MINIFOTO.PKF` hash, not a rendered bitmap hash
  for every player record.
- The kit receipt has finished PM99 bitmap hashes but no editable kit recipe or
  source-artwork hash.
- Old build manifests contain timestamps and absolute paths. V2 omits them
  rather than laundering them into a supposedly reproducible release.

These gaps are emitted in `migration.known_gaps`, which means the output fails
`--strict` by design. Closing them is an asset-store/provenance task, not a
reason to weaken reproducibility checks.
