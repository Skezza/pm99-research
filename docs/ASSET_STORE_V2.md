# PM99 Content-addressed Asset Store Import

The asset store is a local cache for approved historical artwork. It is not a
game distribution format and it does not make a third-party portrait or kit
source redistributable.

The importer exists to stop a release build from depending on an old mutable
game folder. It records every retained byte by SHA-256 and distinguishes two
different promises which must not be confused.

| Build mode | 2015 English result | Meaning |
| --- | --- | --- |
| Cached-output replay | Qualified, with matching base | Exact retained PM99 bitmap bytes can be reapplied to a container whose pre-patch hash matches the receipt. |
| Strict source-provenance regeneration | Blocked | The old receipts do not retain enough source/crop/renderer/palette evidence to recreate the artwork honestly from source. |

## Store layout and contract

[pm99-asset-store-import-v1.schema.json](../schemas/pm99-asset-store-import-v1.schema.json)
defines the portable index. The local store has this shape:

```text
asset-store/
  index.json
  blobs/
    ab/
      ab...<64-character SHA-256>
```

`index.json` is canonical UTF-8 JSON: sorted keys, compact separators and one
final newline. It contains no absolute machine paths or timestamps. Each blob
path is derived from its hash; the importer checks an existing blob before
reusing it.

The index includes:

- Original portrait files retained by the old face stage, when still present.
- Its 32×32 rendered preview files, when still present.
- Exact raw PM99 portrait bitmap output bytes extracted from the final
  `MINIFOTO.PKF`, or exact loose `J96xxxxx.BMP` output files.
- Exact raw kit bitmap output bytes extracted from the five kit archives.
- The before/after container hashes, offsets and lengths needed for a safe
  byte-for-byte replay.
- Every loose minifoto in the final folder that is not linked by the old face
  receipt. These are called `unlinked_loose_outputs`; they are cached so a
  replay cannot silently lose existing output, but they are not represented as
approved portraits.

The importer does not copy a PM99 PKF archive into the store. It stores only
the output slices needed to reproduce the declared patch, and requires a
matching pre-patch archive hash before any future writer may use them.

## Importing the retained 2015 artwork

This command is local-only and has no network step:

```bash
python3 scripts/asset_store_v2.py import-2015 \
  --face-receipt .local/season-2015-16/english92-2015-16-build26-native-first-fixture/face-stage-receipt.json \
  --kit-receipt .local/season-2015-16/english92-2015-16-build31-centred-tactics-correct/kit-stage/2015-16-english-92-native-kit-receipt.json \
  --game-root .local/season-2015-16/english92-2015-16-build26-native-first-fixture/game \
  --store-root .local/asset-store/2015-16-english92-v1

python3 scripts/asset_store_v2.py validate \
  --store-root .local/asset-store/2015-16-english92-v1 --verify-blobs
```

For the retained 2015 material this imports:

- 2,283 cached portrait outputs and records 17 unresolved rows without
inventing a face.
- 447 cached kit bitmap outputs across five archives.
- 21 loose minifoto outputs which exist in the final folder but have no row in
the face receipt.

The exact counts are a property of the indexed receipt hashes, not a claim
that all 2,300 players have historically proven photographs.

## Why cached output is acceptable here

A cached-output replay is reproducible when all of these gates pass:

1. The input face/kit receipt hashes match the asset index.
2. Each input PM99 container matches its declared pre-patch SHA-256.
3. Every cached output blob re-hashes correctly.
4. Patches write only the declared offset/length ranges and the resulting
   container matches its declared post-patch SHA-256.

That gives a deterministic replay of a known output. It is useful for release
build efficiency: no image download or crop needs repeating merely because a
database/tactics change caused a fresh game directory to be materialised.

It is deliberately not the same as source regeneration.

## Why strict source provenance remains blocked

The importer records these blockers instead of concealing them:

- Existing portrait rows do not include a per-player crop recipe. A retained
  source PNG and preview PNG prove bytes, not the original crop decision.
- The old face receipt does not pin the original converter and palette inputs
  as a source-build contract.
- Portrait URLs and kit reference pages were not captured as immutable
  content. A URL is not a source-content hash.
- Kit receipts retain rendered PM99 bitmap hashes and visual descriptions, but
  not source-artwork hashes or a fully pinned renderer/palette recipe.

To make a new season strict-source-provenance capable, capture the original
asset byte hash, licence/source reference, crop recipe, converter version and
palette/base input hash before rendering. Store each of those as approved,
content-addressed assets. Do not backfill invented recipes into 2015.
