# 2015/16 English V2 pipeline closeout

## Result

The existing qualified English-92 2015/16 release can now be rebuilt as a
clean, reproducible **cached-output** V2 materialisation. It no longer depends
on copying a previous playable game folder.

The two independent local materialisations produced the identical full-tree
fingerprint:

```text
74476eafad18a233f483b551a8b2149ac954e425cd9563892d6df8c3fd5e1226
```

They also produced byte-identical canonical release manifests and build-plan
receipts. The input season package was independently migrated twice with the
same canonical hash:

```text
c3a9fb893bc3ff4941078d7e71cbc0438e522fba12a9d9984d9c47926d59e6bf
```

The local paths are intentionally not part of the release identity. They live
under ignored `.local/season-pipeline-v2/` and `.local/asset-store/` roots.

## What the real V2 build proved

1. A clean base was made from the known PM99 installation after removing only
   its top-level `SAVE` runtime directory. Every remaining byte was locked in
   a verified-base inventory.
2. The bridge retained 977 explicit game outputs in a content-addressed
   bundle: the database, calendar executable, five kit archives, portrait
   archive and loose portrait files. No Wine prefix, save, screenshot, log or
   helper script was retained.
3. The adapter validated the base fingerprint, season-package hash, bundle
   index and every blob hash before writing into each new tree.
4. The build-plan runner rejected any unlisted modification, new runtime
   directory, symlink or unexpected final file.
5. `audit_2015_english92_release.py` then audited the first clean V2 tree
   against the immutable release ledgers and passed all checks:
   - 92 clubs in the expected 20/24/24/24 division structure;
   - 2,300 players and 92 linked managers;
   - 177 native `dd6360` records and 2,123 `dd6361` visible-skill records;
   - all 269 goalkeepers on the proven Handling lane;
   - all 92 opening tactics grids, with centered safe pitch coordinates;
   - all 92 kits / 447 archive patches;
   - the 2015/16 calendar patch; and
   - 2,294 approved portraits plus six deliberate PM99 no-photo records.

## Portrait policy going forward

The image stage now fails open. If a portrait cannot be obtained, downloaded
or converted safely, it disables the inherited PM99 photo and records an
`intentionally-no-photo` result with its reason. It does not halt the build,
insert a placeholder or leave the wrong 1998 carrier face visible.

The V2 review workflow now normalises those per-player results and emits a
machine-readable no-photo queue containing player, club, carrier ID, declared
and resulting state, plus the reason. For this release it records six
deliberate native-no-photo decisions; none are silently treated as unresolved
or omitted from later human review. See [SEASON_REVIEW_V2.md](SEASON_REVIEW_V2.md).

This is a product-quality rule for every future season. It means a complete
football database is not held hostage by incomplete image research.

## Limits retained honestly

This particular 2015 package is `legacy-migrated`, not a strict
source-provenance package. Its old portrait/kit work lacks original source
content hashes and reusable crop/render recipes. The V2 cached bundle is
therefore a reproducible replay of approved PM99 output bytes, not a claim
that V2 has recreated those pixels from the original web sources.

The foreign/world competition membership writer is also still a separate
research gate. V2 has not used the pipeline to make an unproven foreign league
rewrite.

## Repeating this for 26 seasons

The release mechanics are now reusable: a new season needs a canonical package,
approved asset bundle and one V2 plan, then two clean builds and the normal
static/runtime qualification. There is no need to invent a new release process
for each year.

The remaining scale work is season content, not pipeline architecture:

| Work item | Status for the 26-season programme |
| --- | --- |
| Clean base, manifests, inventories, double-build gate | complete |
| Strict safe build-plan execution | complete |
| Legacy cached-output bridge | complete for English 2015/16 |
| No-photo fallback behaviour | complete |
| Native data compiler adapter from a V2 season package | next engineering milestone |
| Source-hashed portrait/crop/kit inputs for new seasons | required per season |
| English club/player/manager/tactics data packages | required per season |
| Foreign membership proof and world compiler lane | still research-blocked |
| Native Windows runtime attestation | required when EXE/launch layer changes; representative public data-release smoke |

So the process is ready to repeat now for an English-only season using either
new source-captured inputs or the explicit cached-output bridge. The worldwide
edition cannot be responsibly automated until the foreign membership gate is
closed.
