# 2015/16 world portrait materialisation

`scripts/materialise_2015_world_portraits.py` executes the portrait lane from
the world candidate manifest. It selects only `fifa16-url-candidate` rows from
source-squad-ready clubs, validates that each URL encodes the same FIFA16
player id, downloads with bounded identity-bound mirrors, and validates the
image bytes before use.

The manifest FIFAIndex URL is retained as the primary provenance. That host can
return HTTP 403 from a scripted client, so the downloader tries these
deterministic ID-derived mirrors first, then records the FIFAIndex attempt if
needed:

1. Futbin FIFA16 CDN: `cdn.futbin.com/content/fifa16/img/players/<id>.png`.
2. SoFIFA FIFA16 CDN: `cdn.sofifa.net/players/<id//1000>/<id%1000:03d>/16_120.png`,
   with `Referer: https://sofifa.com/`.

Both mirrors are derived from the verified player id; they are not name or
search substitutions. The receipt records every attempted URL, HTTP result,
request headers, selected download URL, image dimensions/format, and SHA-256.
Successful bytes are stored at `cache/<first-two-hash>/<full-hash>.png`.

Each successful source is passed to the existing `_build_replacement_bitmap`
PM99 crop/autocontrast/palette conversion helper. The resulting indexed BMP and
RGB preview are candidates under the output directory, not game artifacts.
Any HTTP failure, malformed image, or conversion failure produces a
`native-no-photo` row with its exact attempts and reason. There is no fallback
to another player or carrier. `MINIFOTO.PKF` is read-only and its hash is in
the receipt.

Example:

```bash
python3 scripts/materialise_2015_world_portraits.py \
  --candidate-manifest .local/season-pipeline-v2/world-2015-asset-candidate-manifest.json \
  --minifoto .local/season-pipeline-v2/english92-clean-release-2015-16-20260830/DBDAT/MINIFOTO.PKF \
  --cache-dir .local/season-pipeline-v2/world-2015-fifa16-portrait-cache \
  --output-dir .local/season-pipeline-v2/world-2015-fifa16-portrait-candidates \
  --output .local/season-pipeline-v2/world-2015-fifa16-portrait-materialisation.json \
  --workers 24
```

The receipt has `successes`, `failures`, `pending`, and complete `rows` lists,
plus exact counts. It is safe to rerun into the same local cache; existing
content-addressed bytes are hash-checked before reuse.
