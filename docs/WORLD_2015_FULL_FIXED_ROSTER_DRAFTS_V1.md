# World 2015 full fixed-roster carrier drafts V1

`scripts/build_2015_world_full_roster_carrier_drafts.py` expands each strict
club link in the opening-fixture source join to every immutable row in its
`world-2015-source-player-reconciliation` plan. This is source/package-level
material only. It emits no PM99 database or asset write.

```bash
python3 scripts/build_2015_world_full_roster_carrier_drafts.py \
  --opening-fixture-source-join .local/season-pipeline-v2/world-2015-opening-fixture-source-join-20260831.json \
  --player-reconciliation .local/season-pipeline-v2/world-2015-source-player-reconciliation-20260830.json \
  --asset-dispositions .local/season-pipeline-v2/world-2015-asset-dispositions.json \
  --output .local/season-pipeline-v2/world-2015-full-fixed-roster-carrier-drafts-20260831.json
```

The join and reconciliation hashes must match. The output retains manager,
formation, XI/bench/shirt and fixture-stadium facts, but labels every stadium
as evidence only: it does not assert a permanent club ground or capacity.
Every fixed slot has either a complete FIFA16 candidate rating projection or
`editorial-fallback-required`; no rating is invented. Asset disposition rows
are copied only when their carrier and fixed slot match; otherwise an
identity-safe FIFA URL remains `pending-source-materialisation` and a missing
URL becomes a native-no-photo review requirement.

The current receipt covers 77 strict linked carriers and all 1,817 of their
fixed roster slots. 1,417 rows have complete FIFA16 candidate ratings and 400
require editorial fallback. The asset input supplies 400 explicit
native-no-photo dispositions and 1,417 pending portrait-materialisation rows.
All 77 carriers remain blocked (zero compiler/package-ready carriers): no
reviewed era kit, permanent ground/capacity source, manager-entity mapping,
or runtime-proven foreign mode-1 write contract has been supplied.
