# Integrated 2015 world NTF source package (2026-08-31)

The source-only integration command is:

```text
python3 scripts/integrate_2015_ntf_source_package.py \
  --registry .local/season-pipeline-v2/world-fixed-carriers-english92-mode0-append-2015-16-20260830-b.json \
  --base-capture .local/season-sources/footballsquads-2015-world-hybrid.json \
  --base-draft .local/season-pipeline-v2/world-2015-source-carrier-drafts-20260830.json \
  --ntf-capture .local/season-pipeline-v2/world-2015-missing-family-ntf-capture-20260831.json \
  --fifa16-player-csv .local/season-2015-16/fifa16-player-stats.csv \
  --integrated-capture-output .local/season-pipeline-v2/world-2015-integrated-source-capture-20260831.json \
  --integrated-draft-output .local/season-pipeline-v2/world-2015-integrated-source-carrier-draft-20260831.json \
  --reconciliation-output .local/season-pipeline-v2/world-2015-integrated-source-player-reconciliation-20260831.json
```

The generated, ignored local receipts have these hashes:

* integrated capture: `3886ff6ea866b2698421305bd3e8eae575e4524ee89dc9a47613a81eff7d5e96`;
* integrated draft: `f5410f00369ce921b31083bc59e2279c07bea9ebd1ae3e8b36516cdecee57b00`;
* player reconciliation: `ff1f5720957eb26c367dae93d3c50bcc8225c09225c1ad8c7533745f383e677b`.

## Result

The combined capture contains 763 clubs and 21,283 player rows: 682 original
FootballSquads clubs plus 81 NTF clubs.  The draft remains exactly 451 fixed
PM99 carriers.  NTF bindings are explicit and country constrained: 81 were
added, of which 15 have enough dated appearance rows to fill their immutable
capacity.  The resulting package has 317 source-ready carriers and 6,819
selected fixed slots, compared with the previous 302 source-ready carriers.

The 66 NTF captures with fewer rows than their fixed capacity retain their
source rows but are marked `undersized-source-squad`; no player is invented or
borrowed from another club.  FIFA16 ratings are joined using the existing
reconciliation policy.  An unambiguous FIFA match retains its published
values; `fallback-required` means no safe match exists and no zero/default
rating is supplied.

The updated player receipt reports 3,039 `fallback-required` rows, 3,271 exact
name/date matches, 269 unique surname/date matches, 216 unique-name matches,
7 unique-name/nationality matches, and 17 ambiguous-name matches.  Broad role
demand for the 6,819 selected slots is G 707, D 2,234, M 2,538, F 1,340.

There are 134 remaining unresolved carriers.  The full explicit list is in
`coverage.remaining_unresolved_carriers` and the IDs are in
`coverage.remaining_unresolved_carrier_ids` in the player receipt.  Reasons
are either an unavailable/insufficient source squad, no captured source
country, or the pre-existing no-distinct-top-competition capacity conflict.
This is a package/review receipt only: no PM99 binary, database, FDI, PKF, or
BMP was written.
