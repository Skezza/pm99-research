# 2015/16 world kit materialisation

`scripts/materialise_2015_world_kits.py` captures MediaWiki source for the
source-squad-ready world clubs and extracts the exact home fields:
`pattern_la1`, `pattern_b1`, `pattern_ra1`, `leftarm1`, `body1`, `rightarm1`,
`shorts1`, and `socks1`. Page titles are generated with FC/AC/legal-name
aliases and accepted only when the resolved season title contains the club's
meaningful identity tokens. The raw wikitext is stored content-addressed in
the requested cache directory.

When all fields are present and colours are six-digit RGB values, the stage
resolves exact Wikimedia Commons `Kit_body_<token>.png`,
`Kit_left_arm_<token>.png`, and `Kit_right_arm_<token>.png` layers (each arm is
resolved from its own infobox token). Those layers are composited into
candidate BMPs for each of `MINIESC.PKF`, `NANOESC.PKF`, and `RIDIESC.PKF`,
preserving the archive's BMP shape and PM99 palette. Layer bytes and URLs are
content-addressed and recorded. If an exact layer is unavailable, a
colour-silhouette candidate may still be emitted, but it is marked
`rendered-colour-candidate-pattern-unresolved` and remains blocked. No old
1998 art is copied, modified, or claimed as a substitute.

Missing season pages, missing/blank fields, invalid colours, and absent PM99
carrier records are listed in `missing_follow_up` with `no-write` actions.
The receipt reports all 451 identities, including 149 not source-squad-ready,
and separately reports the 302 source-ready club lane.

Example:

```bash
python3 scripts/materialise_2015_world_kits.py \
  --candidate-manifest .local/season-pipeline-v2/world-2015-asset-candidate-manifest.json \
  --dbdat .local/season-pipeline-v2/english92-clean-release-2015-16-20260830/DBDAT \
  --cache-dir .local/season-pipeline-v2/world-2015-wikipedia-kit-cache \
  --output-dir .local/season-pipeline-v2/world-2015-kit-candidates \
  --output .local/season-pipeline-v2/world-2015-kit-materialisation.json \
  --workers 4
```

## FIFA 16 world-scale source

`scripts/materialise_2015_world_fifaindex_kits.py` is the scalable dated
source for licensed FIFA 16 clubs.  It binds a unique FIFA team id/name using
identity-matched player club votes and a CC0 SoFIFA FIFA16 team-id crosswalk,
then captures the exact FIFAIndex home-kit URL.  FIFAIndex's image CDN blocks
local scripted clients, so the bytes are retrieved through DuckDuckGo's
external-content image cache; the receipt retains the original URL, transport
URL, source dimensions and SHA-256.  Only unique bindings produce candidates.

For important clubs absent from FIFA 16, the reviewed ledger at
`scripts/data/world_2015_reviewed_kit_geometry.json` binds carrier identity,
season, home-kit type, design and colours to a dated Football Kit Archive
club-season page. `scripts/supplement_2015_world_reviewed_kits.py` renders
that deliberately limited geometry into the same three PM99 record shapes.
The receipt calls these `release-eligible-reviewed-2015-geometry`; it does
not claim that a source texture, badge or sponsor was copied. A carrier/name
mismatch or a carrier already resolved by FIFA fails closed.

`scripts/apply_2015_world_kits.py` is the isolated archive-write boundary.  It
first verifies and restores the 92-club/447-record signed English 2015 kit
set, then overlays approved foreign candidates in `MINIESC`, `NANOESC` and
`RIDIESC`.  It verifies exact record extents and readback and proves that every
unapproved carrier remains byte-identical to the certified input.  Those
remaining carriers are recorded individually as unresolved native fallbacks;
they are never reported as historical 2015 kits.
