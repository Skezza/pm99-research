# PM99 Season Compiler Pipeline V2

## Purpose

Pipeline V2 is the reproducibility boundary for the historical-database
programme: **1999/00 through 2025/26**.  It is not a binary editor and it does
not contain, copy, or publish PM99 files.  Individual compiler stages continue
to own their researched write lanes; V2 records precisely what a release was
built from and what it produced.

The output should be a clean release every time, not a chain of edits to the
previous release:

```text
verified immutable PM99 base + canonical season package + approved assets
                                  |
                                  v
database -> portraits -> kits -> calendar -> static audit -> runtime proof
                                  |
                                  v
complete output inventory + canonical release manifest + separate attestation
```

This allows a season to reuse the same approved photo crop or kit source as a
later/earlier season without treating a generated game folder as source data.

## Contract

`scripts/season_pipeline_v2.py` provides the common standard-library-only
building blocks.

- **Verified base.** A base descriptor contains a full, path-independent list
  of every file, size, and SHA-256. A build must match this descriptor before
  it begins. The descriptor must be made from the independently reviewed,
  pristine PM99 installation—not a prior `rN` output.
- **Season package.** A season-specific schema belongs to the season-data
  layer. V2 consumes it as a UTF-8 JSON object and records its canonical JSON
  SHA-256, so whitespace and key order cannot alter identity.
- **External artifacts.** Portrait originals, crop catalogues, kit sources,
  compiler tools, and runtime receipts are represented by logical ID, role,
  size, and content hash. Local paths do not appear in the canonical manifest.
- **Content-addressed stages.** A stage key includes the stage ID, the hash of
  the exact compiler implementation, input fingerprints, canonical parameters,
  and external artifacts. A changed script, source, crop recipe, or parameter
  therefore cannot reuse an old cache entry.
- **Output inventory.** The completed tree gets the same complete inventory
  treatment as the base. It is the release's byte-level identity, including
  files a hand-maintained shortlist would miss.
- **Fail closed.** Symlinks, special files, mixed/overlapping input/output
  trees, changed base data, malformed fingerprints, duplicate IDs, malformed
  JSON, and evidence-file overwrites are errors. V2 never silently skips a
  file or rewrites existing proof.

Artwork has a separate, deliberately different rule: **fail open**. A missing
or unavailable historical portrait resolves to PM99's native no-photo state,
with the reason retained in the asset receipt. It must never preserve an
unrelated carrier face, but image research must not block a season database
release.

The tree inventory deliberately records bytes, not Unix permission bits. That
makes its identity meaningful across native Windows and Wine/Linux research
machines. Any Windows-specific runtime result goes in the attestation.

## Canonical manifest versus attestation

`season-manifest.json` is canonical. It has no timestamp, hostname, absolute
path, or random run ID. Two clean builds with identical declared inputs should
produce byte-identical canonical manifest content and output inventories.

`attestation.json` is intentionally non-reproducible. It records when and
where a particular output inventory was checked, its runtime receipts, and its
environment. It is evidence attached to a release; it is never an input to a
compiler cache key or build identity.

The metadata directory is outside both game trees, so writing a manifest
cannot change the output inventory it describes.

## Minimal CLI flow

The commands only create JSON receipts. They do not mutate PM99 files.

```bash
# Once per independently reviewed vanilla/base installation.
python3 scripts/season_pipeline_v2.py verified-base \
  --base-id pm99-gog-en-1.00 \
  --tree /secure/pm99-base \
  --output releases/bases/pm99-gog-en-1.00.json

# Before each season build, fail if the source install is not that base.
python3 scripts/season_pipeline_v2.py verify-base \
  --tree /secure/pm99-base \
  --verified-base releases/bases/pm99-gog-en-1.00.json

# Each deterministic writer/tool stage receives a content-addressed key.
python3 scripts/season_pipeline_v2.py stage-key \
  --id database \
  --implementation scripts/compile_season_database.py \
  --inputs-json receipts/2015-16-stage-inputs.json \
  --parameters-json receipts/2015-16-database-parameters.json \
  --external-artifact roster-source=source/2015-16-roster.json \
  --output receipts/2015-16-database-stage.json

# After a fresh compiler output is built, materialise canonical release proof.
python3 scripts/season_pipeline_v2.py release-metadata \
  --season 2015-16 \
  --base-tree /secure/pm99-base \
  --verified-base releases/bases/pm99-gog-en-1.00.json \
  --season-package seasons/2015-16/season-package.json \
  --output-tree work/2015-16/game \
  --metadata-dir releases/2015-16/r1 \
  --external-artifact portrait-catalogue=assets/portraits/catalogue.json \
  --external-artifact kit-receipts=assets/kits/2015-16.json \
  --stage-record receipts/2015-16-database-stage.json

# Required reproducibility gate: clean output A must equal clean output B.
python3 scripts/season_pipeline_v2.py double-build \
  --first-tree work/2015-16-a/game \
  --second-tree work/2015-16-b/game

# Attach a runtime receipt only after it is tied to the finished inventory.
python3 scripts/season_pipeline_v2.py attest \
  --release-manifest releases/2015-16/r1/season-manifest.json \
  --output-tree work/2015-16-a/game \
  --run-id native-windows-smoke \
  --runtime-receipts-json receipts/2015-16-native-windows.json \
  --output releases/2015-16/r1/attestation.json
```

`--inputs-json` for `stage-key` is a JSON object whose values are lowercase
SHA-256 strings, for example:

```json
{
  "base-tree": "<64 lowercase hex characters>",
  "season-package": "<64 lowercase hex characters>"
}
```

The stage's cache key is an identity only; cache reuse must additionally check
that the cached output inventory matches the receipt expected by the calling
compiler. A cache miss is safe. A cache hit without both key and output
verification is not.

## Release gate

A season is not publishable just because V2 has produced a manifest. The
minimum final gate is:

1. Build in two separate clean directories from the same verified base and
   canonical season package.
2. Require `double-build` to report equality.
3. Verify the static contracts owned by the database, portrait, kit, calendar,
   and tactics stages.
4. Run PM99 runtime qualification against the exact output inventory. A fresh
   Wine start is the normal inexpensive per-database smoke test. Run a native
   Windows smoke test when the executable, launch/runtime layer or calendar
   patch changes, and for representative public release candidates. A pure
   FDI/PKF data refresh does not need a separate native-Windows session merely
   because its season label changed.
5. Write the attestation after the runtime checks. Do not put it inside the
   game/output tree or use it as an input for the next build.

The next work item is to have the generic season schema and real 2015 compiler
emit these receipts. Existing 2015 packages are useful research outputs but do
not become Pipeline V2 source inputs merely because they already contain faces
and kits.
