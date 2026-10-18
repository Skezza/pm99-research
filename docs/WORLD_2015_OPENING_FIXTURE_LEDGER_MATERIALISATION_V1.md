# World 2015 opening-fixture ledger materialisation V1

`scripts/materialise_2015_world_opening_fixture_ledger.py` converts only the
already exact, hash-locked opening-fixture source links into valid
`pm99-world-fixed-carrier-ledger-v2` **blocked** rows. It is a source/package
authoring step, not a PM99 writer and not an approval to use the future
compiler.

```bash
python3 scripts/materialise_2015_world_opening_fixture_ledger.py \
  --registry .local/season-pipeline-v2/world-fixed-carriers-english92-mode0-append-2015-16-20260830-b.json \
  --base-ledger .local/season-pipeline-v2/world-2015-16-ledger-english92-mode0-append-2015-16-20260830-b.json \
  --opening-fixture-source-join .local/season-pipeline-v2/world-2015-opening-fixture-source-join-20260831.json \
  --player-reconciliation .local/season-pipeline-v2/world-2015-source-player-reconciliation-20260830.json \
  --output-ledger .local/season-pipeline-v2/world-2015-opening-fixture-blocked-ledger-20260831.json \
  --output-report .local/season-pipeline-v2/world-2015-opening-fixture-blocked-ledger-report-20260831.json
```

The materialiser verifies the join’s strict-player-reconciliation hash,
preserves fixed carrier/slot IDs, retains the dated manager and fixture shirt
facts, and converts the FootballSquads facts plus complete FIFA candidate
ratings into ledger player rows. It defers a row when ratings are incomplete,
when a fixed JUG carrier has multiple registry owners, or when one FIFA person
would be assigned to two distinct fixed JUG carriers.

The 2026-08-31 input produces 77 blocked carrier rows. It has 963 strict
opening-fixture player links; 845 have complete rating candidates; 826 are
safe, standalone fixed-slot ledger rows across 74 carriers. The remaining 137
rows are explicitly deferred for incomplete ratings, shared-JUG ownership or
the duplicated FIFA-person identity review. Every carrier remains blocked:
ground/capacity, kit, portrait/no-photo, manager-entity and mode-1
role/shirt/opening-tactics write decisions are deliberately unresolved.

The receipt never promotes a reported fixture stadium into a club ground or
capacity. It never changes foreign membership/topology or writes an EQ, JUG,
ENT, PKF or BMP file.
