# World 2015 editorial fallback ratings V1

`scripts/apply_2015_world_editorial_fallback_ratings.py` resolves only the
full-roster draft’s explicit `editorial-fallback-required` rows. It retains
all complete FIFA16 candidates unchanged and produces a hash-locked
source/package receipt, never a PM99 binary write.

```bash
python3 scripts/apply_2015_world_editorial_fallback_ratings.py \
  --full-roster-draft .local/season-pipeline-v2/world-2015-full-fixed-roster-carrier-drafts-20260831.json \
  --output .local/season-pipeline-v2/world-2015-full-fixed-roster-editorial-ratings-20260831.json
```

For a fallback player, the policy takes a median retained FIFA16 quality from
the same carrier (or country/global fallback where the carrier has too few
matched rows), then applies the dated opening-fixture role, source-squad-order
band, age on 2015-08-08, broad-position skill profile, height aerial effect,
and a bounded stable separator. Its rating cannot exceed the carrier’s
retained-star protection ceiling. Each generated player stores this complete
basis; it does not pretend to be an observed FIFA/EA attribute.

The 2026-08-31 receipt has all 1,817 fixed rows across 77 carriers: 1,417
retained FIFA16 candidates and 400 applied editorial fallbacks. The resulting
quality distribution is non-flat (52–94, 40 distinct values); known star
ratings stay retained rather than being averaged down. All 77 carriers still
remain blocked: kit/portrait completion, ground/capacity, manager-link and
foreign mode-1 runtime write gates are external work, not rating gaps.
