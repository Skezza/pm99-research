# Source-Club Selection Review Proposals V1

## Purpose and boundary

`season_source_club_selection_proposals_v1.py` turns the existing all-season
collision matrix into a deterministic, read-only human-review queue. It groups
only the narrow cases where the matrix has an exact same-person source/source
collision and its transparent normaliser sees a direct alternate club label
(for example `Kettering` / `Kettering Town`).

It is deliberately not a source-club selection manifest. It does not choose
which selector owns the fixed carrier, which selector supplies the dated
opening squad, or whether the collision is actually one club rather than a
transfer. It never changes raw intakes, packages, allocations, the carrier
registry, compiled files, or releases.

Every direct candidate contains both exact source selectors, their source
document hashes, the matched source-row hashes, the input V6 package hash,
the source-package audit hash, and the collision-matrix hash. A reviewer must
verify dated opening evidence and create a separately hash-bound
`pm99-season-source-club-selection-manifest-v1` entry before the existing
source-selection projection can act on it.

Source/source collisions with no direct label-normalisation signal are
reported as `ambiguous-player-overlap`. They are never selection proposals:
they may be a source abbreviation the weak normaliser does not recognise, or
they may be a genuine player move.

## Verified 25-season report

The first receipt reads all 25 V6 draft packages through the immutable
collision matrix:

- collision matrix: `.local/season-source-collision-matrix-v1/20260904/collision-matrix.json`
  (`4744462b01414a8953e9bcbecc854e0e463cb7147d02bd8afef358b563c767c2`)
- proposal report:
  `.local/season-source-club-selection-proposals-v1/20260904-r1/proposal-report.json`
  (`2ea7e83614f95d91bcf428c24419bb2e9f5d4aff6f80a3e720a08e2b86d9692a`)

| Season | Direct alias candidates | Same-person evidence in those candidates | Ambiguous player overlaps |
| --- | ---: | ---: | ---: |
| 2008/09 | 2 | 3 | 8 |
| 2009/10 | 2 | 3 | 9 |
| 2010/11 | 1 | 1 | 5 |
| 2011/12 | 3 | 8 | 4 |
| 2012/13 | 6 | 14 | 2 |
| 2013/14 | 7 | 15 | 4 |
| 2014/15 | 5 | 14 | 0 |
| 2016/17 | 5 | 11 | 3 |
| 2017/18 | 6 | 15 | 6 |
| 2018/19 | 8 | 31 | 7 |
| 2019/20 | 7 | 28 | 3 |
| 2021/22 | 5 | 17 | 19 |
| 2022/23 | 3 | 14 | 10 |
| 2023/24 | 4 | 29 | 22 |
| 2024/25 | 5 | 30 | 16 |
| 2025/26 | 6 | 41 | 26 |

The other nine V6 seasons have no current-source/current-source collision in
this input. Across all 25 seasons, the report accounts for 418 such
collisions: 274 direct-label evidence rows grouped into 75 review candidates,
and 144 ambiguous player overlaps. The existing 574 source/legacy collisions
are intentionally absent: their stale-candidate reconciliation has a separate
safe mechanism and is not a source-club ownership decision.

The 2016/17 queue illustrates the distinction. It surfaces direct label
candidates such as `Aldershot Town` / `Aldershot`, but it also keeps the
`North Ferriby United` / `Nth Ferriby` collisions ambiguous because the
normaliser does not equate that abbreviation. This report therefore neither
supersedes nor changes the separate, explicitly reviewed 2016 selection
manifest. In particular, a direct `Dover Athletic` / `Dover` label signal is
not permission to select Dover: dated evidence still decides whether it is an
opening-source substitution or a transfer conflict.

## Reproduce and validate

Write a new report directory; the tool refuses to replace an existing receipt:

```bash
python3 scripts/season_source_club_selection_proposals_v1.py \
  --matrix .local/season-source-collision-matrix-v1/20260904/collision-matrix.json \
  --expected-season-count 25 \
  --output .local/season-source-club-selection-proposals-v1/REVISION/proposal-report.json
```

Running without `--output` is a read-only validation and deterministic hash
check. The tool validates that every direct item exposes exactly two source
selectors, prohibits automatic selection, and that its summary accounts for
every current-source/current-source collision in the matrix. The accompanying
test module additionally exercises direct grouping, ambiguity preservation,
byte determinism, and rejection of a report tampered to include an automatic
canonical selector.

Neither this receipt nor its validation is a static-ingress, runtime,
historical-accuracy, playable-game, or screenshot assertion.
