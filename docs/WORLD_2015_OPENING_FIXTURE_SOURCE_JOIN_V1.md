# World 2015 opening-fixture source join V1

`scripts/join_2015_world_opening_fixture_facts.py` joins the hash-locked
Transfermarkt opening-fixture receipt with the existing FootballSquads source
capture, source-carrier draft and strict player reconciliation. It is a
canonical JSON receipt only: it neither writes nor authorises a PM99 file
write.

The club rule is deliberately narrow: `country_catalog` plus the existing
`strict_club_key` must be identical and unique. There is no fuzzy matching,
alias table or inferred carrier assignment. A match may carry an existing
source-draft reference and exact-name player-reconciliation reference solely
for review; neither is a PM99 write instruction.

Build the current receipt with:

```bash
python3 scripts/join_2015_world_opening_fixture_facts.py \
  --footballsquads-capture .local/season-sources/footballsquads-2015-world-hybrid.json \
  --source-draft .local/season-pipeline-v2/world-2015-source-carrier-drafts-20260830.json \
  --player-reconciliation .local/season-pipeline-v2/world-2015-source-player-reconciliation-20260830.json \
  --opening-fixture-receipt .local/season-pipeline-v2/world-2015-transfermarkt-opening-fixtures-20260831.json \
  --output .local/season-pipeline-v2/world-2015-opening-fixture-source-join-20260831.json
```

Every input must be canonical JSON and is SHA-256 pinned in `sources`. The
draft and player-reconciliation receipts must also prove their bindings to the
same FootballSquads capture and source draft. The output retains the manager,
opening XI, bench, shirt number, reported opening-fixture stadium, earliest
home-fixture stadium evidence and formation exactly as source facts.

For the 2026-08-31 inputs, the join has 218 receipt clubs: 93 strict
FootballSquads club-identity matches and 125 explicitly unmatched club names.
The latter remain an identity-review queue. The four Dutch rows with missing
XI/formation evidence remain a separate incomplete-fixture queue (Roda JC
Kerkrade, FC Groningen, FC Twente Enschede and Heracles Almelo). A reported
stadium is never promoted to a permanent ground or capacity fact, and missing
XI/formation values are never inferred.
