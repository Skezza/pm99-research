# Source-composition repair — 2026-09-01

## Outcome

Four seasons that previously had several valid, complementary squad receipts
are now reproducibly composed and reprocessed as raw source intakes. The
repair is data-driven: each season has a `source-bundle.json` that locks the
carrier registry, every retained raw capture, the prior assignment binding,
and the two derived output paths. It does not choose club identities, promote
candidates, or write PM99 files.

| Season | Bundle inputs | Composed capture SHA-256 | Reprocessed intake SHA-256 | Source coverage |
| --- | ---: | --- | --- | --- |
| 2004/05 | 11 | `6f6365de637bd6a28e224783841f3a34655d9a381915cb5ece2c6a89160a00d4` | `74a687bbf396a64926eb23f8c24daa6aa74e7ec7f034af197fa6f7380b6dca52` | 362 clubs / 10,534 player rows |
| 2008/09 | 2 | `a8949eb281c0004b5275299e83051a760b006806bf78dd4d9742b42be3f8cd4f` | `5e3ab733d606d5dae8dc7c86eb05bc9247c43f383e676b7395e489702689ae9e` | 680 clubs / 20,709 player rows |
| 2009/10 | 2 | `e0b5b239063c0ac8085bb4d9c5598de3ae14940928950f6716585368610e346c` | `9dabf1938d32fae00abea2e1ccd488a3a58b66c60a5a064b7834664bc878d73d` | 679 clubs / 21,065 player rows |
| 2014/15 | 2 | `505775823961ec8e615ba03947d2250894d6906bfd4711bd64f157e682b38b66` | `d4883bba7d6623d0b95baee177b45edbb39009b526f9137ed558cdbe83d1b4ca` | 662 clubs / 19,878 player rows |

All four derived assignments remain at zero approved identities and 451
unassigned foreign carriers. Source gaps, existing blocked source pages, and
the package/build/runtime gates remain intact.

## Reproduce

The normal batch path discovers a verified season-local source bundle and
uses its derived assignment automatically; no special filename override is
needed:

```bash
python3 scripts/season_source_bundle_v1.py verify \
  --bundle seasons/2004-05/source-bundle.json

python3 scripts/season_source_intake_batch_v1.py \
  --seasons-root seasons --season 2004-05 --write
```

Repeat that pair with `2008-09`, `2009-10`, or `2014-15`. `build` refuses to
overwrite completed outputs; `verify` recomputes them from the hash-locked
inputs. The batch coordinator also refuses unbundled competing captures.

## 26-season receipt pass

The read-only default pass over 2000/01–2025/26 reports 25 validated eligible
raw source intakes and one intentionally blocked row:

| Season | State |
| --- | --- |
| 2015/16 | Separate legacy release workspace; it is not a source-intake-v1 workstream. |
| 2024/25–2025/26 | Attributed FootballSquads web snapshots now supply raw source intakes; see each season README. |

That is source-authoring coverage only. It is not evidence of a playable
database, a historical Stoke lineup, or a release candidate.
