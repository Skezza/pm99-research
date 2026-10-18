# 2015/16 foreign-carrier source-gap candidate audit

This receipt audits the 149 foreign-carrier source gaps identified by the
2015/16 world source draft. It is deliberately a source-only lane: it does
not assign a club to a PM99 carrier, select a roster order, change membership,
or write EQ/JUG/ENT data.

## Reproduce

```bash
python3 scripts/audit_2015_world_missing_source_candidates.py \
  --registry .local/season-pipeline-v2/world-fixed-carriers-english92-mode0-append-2015-16-20260830-b.json \
  --source-draft .local/season-pipeline-v2/world-2015-source-carrier-drafts-20260830.json \
  --footballsquads .local/season-sources/footballsquads-2015-world-hybrid.json \
  --fifa16-player-stats .local/season-2015-16/fifa16-player-stats.csv \
  --fifa16-fut .local/season-2015-16/fifa16-fut-source.csv \
  --fifa16-ea-meta .local/season-2015-16/fifa16-ea-player-meta.json \
  --transfermarkt-receipt .local/season-pipeline-v2/world-2015-transfermarkt-opening-fixtures-20260831.json \
  --output .local/season-pipeline-v2/world-2015-missing-source-candidates-20260831.json
```

The machine receipt records the exact path and SHA-256 for every input. It is
local-only and is not a PM99 build input.

## Result

| Scope | Count |
| --- | ---: |
| Existing fixed carriers | 451 |
| Existing source-ready carriers | 302 |
| Foreign source-gap carriers | 149 |
| Foreign source-gap fixed slots | 2,851 |
| Carriers with an exact dated candidate in a captured source | 5 |
| Direct exact FootballSquads closures | 0 |
| Explicitly unresolved remainder | 144 |

The five exact candidates are:

| Carrier | Preserved family | Baseline name | Exact source | Source rows | Blocking fact |
| ---: | --- | --- | --- | ---: | --- |
| 250 | Italy | Empoli | FootballSquads `Empoli` | 32 | selector already used by carrier 221; FIFA16 has 24 rows |
| 421 | Germany | Hertha Berlín | FootballSquads `Hertha Berlin` | 30 | selector already used by carrier 410 |
| 871 | Belgium | Lokeren | FootballSquads `Lokeren` | 29 | selector already used by carrier 856 |
| 1111 | Switzerland | Zurich | FootballSquads `Zürich` | 29 | selector already used by carrier 1108 |
| 1112 | Switzerland | Young Boys | FootballSquads `Young Boys` | 26 | selector already used by carrier 1110 |

These are not assignments. Each source selector is already consumed by a
different source-draft row, so the receipt correctly reports them as
`exact-source-candidate-needs-review`. A future deterministic allocation
rebalance may investigate those five families; it must account for the
displaced carrier before claiming closure. Empoli also has an exact dated
Transfermarkt opening fixture and an exact FIFA16 club/league join, but the
FIFA16 player snapshot is undersized for the 31 fixed slots and the
Transfermarkt receipt supplies only opening-fixture facts.

The remaining 144 carriers are explicitly unresolved. They include every
carrier in the uncaptured families (Serbia, Croatia, Romania, Czechia,
Bulgaria, Slovakia, Slovenia, Cyprus, Wales, Israel, Malta, Faroe Islands,
Lithuania, Albania, Georgia, Moldova, Bolivia, Ecuador, Belarus, Peru,
Uruguay, Venezuela, Colombia, Paraguay, Latvia, Armenia, North Macedonia,
Kazakhstan and Azerbaijan), plus the special/unclassified carriers. The
remainder also includes Perugia, Westerlo, Trelleborgs and six English
non-league rows whose captured top-competition pools cannot satisfy their
fixed capacities after the exact candidates are accounted for. No source from
another country is used to fill these rows.

## Source lanes and guardrails

* FootballSquads is the only lane that can provide a full dated squad
  candidate. The receipt retains `country_catalog`, `competition_catalog`,
  `source_path` and the capture's `source_sha256` for every exact match.
* FIFA16 player stats are a season-16/year-2016 player-fact and rating
  candidate. The receipt retains exact FUT league/club labels, player IDs and
  player-page URLs. It is not opening-date membership evidence.
* The Transfermarkt receipt is the dated 2015 opening domestic fixture lane.
  It retains fixture IDs, dates, source URLs, manager, formation, XI counts
  and reported stadium facts. It is not a complete squad, kit, portrait,
  rating or PM99 assignment source.
* Name joins are strict normalisation only (case, accents and harmless club
  punctuation); no similarity score, fuzzy carrier assignment, or cross-family
  substitution is permitted.

The audit is covered by
`scripts/test_audit_2015_world_missing_source_candidates.py`. In environments
without pytest, `python3 -m py_compile` still verifies the source receipt and
the command above provides a full-data smoke test.
