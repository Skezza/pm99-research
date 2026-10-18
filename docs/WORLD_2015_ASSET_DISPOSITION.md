# 2015/16 world asset disposition

`scripts/dispose_2015_world_assets.py` is the source-only release gate for
`world-2015-asset-candidate-manifest.json`. It produces a JSON receipt and,
when requested, portrait PNG crop candidates. It never writes a PM99 binary or
release database.

## Portrait decisions

Only a candidate manifest row marked `cached-approved-era` and pointing to an
existing local source image can become `approved-crop-candidate`. The stage
records the source hash and writes a deterministic 32x32 RGBA PNG under the
requested portrait output directory. It does not claim that this candidate has
been inserted into `MINIFOTO.PKF`.

Rows without an identity-safe source become `native-no-photo` with the action
`preserve-native-no-photo`. This is an explicit disposition, not an
instruction to reuse a carrier face. URL-only FIFA candidates remain
`pending-source-materialisation` until downloaded and reviewed; treating a URL
as a completed source would make the receipt non-reproducible.

## Kit decisions

The candidate manifest's `EQ96*.BMP` archive presence is deliberately ignored
for release purposes. A kit is eligible only when a reviewed ledger row names
the same carrier, country catalog, and club, has season `2015-16`, has review
status `approved` or `reviewed-2015-16`, and points to a local artifact whose
declared SHA-256 matches. The ledger also records an HTTP provenance URL.

Ledger format:

```json
{
  "schema_version": "pm99-world-reviewed-kit-candidates-v1",
  "rows": [{
    "carrier_id": 205,
    "source_country_catalog": "italy",
    "source_club_name": "Roma",
    "season": "2015-16",
    "review_status": "approved",
    "source_url": "https://example.invalid/roma-2015-16.png",
    "source_path": "/absolute/path/roma-2015-16.png",
    "source_sha256": "..."
  }]
}
```

Every other club receives `blocked-no-reviewed-2015-kit` and `no-write`,
including clubs with base kit art or art copied by an earlier probe. The
receipt's `asset_release_ready_carrier_count` requires source-ready roster,
complete portrait dispositions, and an approved reviewed kit. It is therefore
an asset-lane count, not a claim that a full game carrier has been built.

Example:

```bash
python3 scripts/dispose_2015_world_assets.py \
  --candidate-manifest .local/season-pipeline-v2/world-2015-asset-candidate-manifest.json \
  --portrait-output .local/season-pipeline-v2/world-2015-portrait-candidates \
  --output .local/season-pipeline-v2/world-2015-asset-dispositions.json
```

To add reviewed kits, repeat `--reviewed-kit-ledger` for each independently
audited ledger. The command rejects duplicate carrier rows, mismatched hashes,
non-2015/16 seasons, unapproved rows, missing local artifacts, and HTTP-less
provenance.
