# 2015/16 world source coverage inventory

This is a factual inventory of the current world authoring inputs. It is not a
claim that a 2015/16 world database is complete, and it must not be used to
infer a foreign country, division, league, continental draw pool or membership
write.

## Reproduce

Run this against the approved mode-1 carrier registry and the 2015/16 ledger:

```bash
python3 scripts/audit_world_2015_source_coverage.py \
  --registry .local/season-pipeline-v2/world-fixed-carriers.json \
  --ledger .local/season-pipeline-v2/world-2015-16-ledger.json \
  --player-csv .local/season-2015-16/fifa16-player-stats.csv \
  --output .local/season-pipeline-v2/world-2015-16-source-coverage.json
```

The generated JSON is the machine-readable receipt. It hashes the exact
registry, ledger and candidate player snapshot used for the count.

## Current result

The result is still `not-ready-for-world-compile`. It is no longer accurate to
say that no historical source has been captured: the source capture and its
fixed-carrier draft are now a useful, reproducible starting point. They are
not a release ledger because they do not yet carry each manager, ground, kit,
portrait decision and full player reconciliation.

| Scope | Count |
| --- | ---: |
| Fixed mode-1 carriers | 451 |
| Fixed roster slots | 9,390 |
| `dd6360` slots | 9,389 |
| `dd6361` slots | 1 |
| Kit dispositions | 0 |
| Portrait/no-photo dispositions | 0 |
| Complete carrier updates in the release ledger | 0 |
| Complete roster slots in the release ledger | 0 |
| Foreign carriers with a distinct, same-country, dated FootballSquads squad candidate | 302 |
| Fixed roster slots covered by those source squads | 6,539 |
| Carriers without a captured country source | 135 |
| Carriers whose captured top-flight pool has no distinct squad large enough for the fixed carrier | 14 |

The release ledger is therefore correctly empty rather than a partially
modernised database disguised as complete. The source draft is deliberately
separate from it:

```bash
python3 scripts/prepare_2015_world_source_carrier_drafts.py \
  --registry .local/season-pipeline-v2/world-fixed-carriers-english92-mode0-append-2015-16-20260830-b.json \
  --source-capture .local/season-sources/footballsquads-2015-world-hybrid.json \
  --output .local/season-pipeline-v2/world-2015-source-carrier-drafts-20260830.json
```

It has the strict policy `existing-carriers-only; preserve-country-family-and-
roster-capacity; no-topology-write`. A proposal says only that a dated squad
is available for editorial reconciliation; it is not permission to generate a
PM99 build.

The next deterministic join makes every selected slot reviewable. It matches
only an exact name/date, a unique surname/date, a unique name, or a unique
name/nationality; all other rows remain explicitly unresolved.

```bash
python3 scripts/reconcile_2015_world_source_player_facts.py \
  --registry .local/season-pipeline-v2/world-fixed-carriers-english92-mode0-append-2015-16-20260830-b.json \
  --source-draft .local/season-pipeline-v2/world-2015-source-carrier-drafts-20260830.json \
  --source-capture .local/season-sources/footballsquads-2015-world-hybrid.json \
  --fifa16-player-csv .local/season-2015-16/fifa16-player-stats.csv \
  --output .local/season-pipeline-v2/world-2015-source-player-reconciliation-20260830.json
```

The current receipt resolves 3,762 of the 6,539 selected player rows to a
specific FIFA 16 snapshot identity, leaves 2,760 for an editorial rating
fallback and leaves 17 ambiguous names for manual identity review. It records
the source-fact gaps separately (6 birth dates, 70 heights, 73 weights and 26
shirt numbers); no missing fact is replaced silently.

## Reusable candidate input

`.local/season-2015-16/fifa16-player-stats.csv` is a local 10,500-row FIFA 16
snapshot covering 594 club names. It has a name, club, nationality, date of
birth, height, weight, overall rating, the source components needed to map the
ten stored PM99 profile values, preferred positions, kit number and a
headshot URL for every row; only one row lacks a club and kit number.

It is useful for generating a review queue and for proposing core player facts
and ratings. It is not a replacement for dated club/squad sources, a kit
source, a portrait capture, a manager source, or a PM99 carrier assignment.

The receipt reports two deliberately non-authoritative discovery counts:

| Candidate match rule | Carriers | Fixed slots | Candidate source rows | Carriers with at least as many source rows as fixed slots |
| --- | ---: | ---: | ---: | ---: |
| Strict present-name spelling | 74 | 1,673 | 1,491 | 37 |
| Loose abbreviation discovery | 92 | 2,062 | 1,784 | 39 |

Neither count can be used to write the database: PM99 has 1998 carrier names,
some historical teams disappeared or changed, and a matching display name does
not prove 2015/16 competition placement or a complete roster. The loose rule
is intentionally more permissive, so it is a human-review queue only.

## Exact blockers

- The release ledger still needs a complete historical identity transaction for
  all 451 carriers. 302 can start from a dated squad capture; the remaining
 149 need a new dated country source or a documented capacity-resolution
  decision.
- 36 base JUG player records are shared across 72 roster occurrences. A shared
  carrier cannot receive two different historical identities.
- The fixed-slot compiler can write the compact `dd6360` variable name,
  nationality, broad position, date, physicals, ten stored profile values and
  six fine-role candidates. Broad position and fine roles now have separate
  native profile controls. It still preserves shirt number, opening player
  order, row flags and opening tactics byte-for-byte until the source-player
  to foreign-grid mapping is proved.
- No complete foreign-era kit source, portrait/no-photo decision, or
  ground/capacity source has yet been joined into a release ledger. The
  Transfermarkt-derived 2015/16 receipt now supplies dated fixture manager,
  XI/bench/shirt-number, reported stadium and (for 214 of 218 source clubs)
  declared-formation facts for 13 supported foreign countries. It is still a
  source-only receipt: it is not a PM99 carrier assignment and formation-to-
  grid mapping remains unproven. A source squad alone is not a complete club
  update.

The isolated full-player `dd6361` record and existing short mode-1 roster
tails are now covered by the compiler contract. They are no longer release
blockers. Country, division, draw-pool and competition membership are scope
exclusions: an in-place world update preserves them rather than trying to
rewrite game rules.

## Safe next action

Use the snapshot to generate per-carrier review candidates, then capture
dated source material before adding a single `carrier_updates` row. A completed
row must account for all of that carrier's existing slots and source every
club, manager, player, kit and portrait/no-photo decision. The existing
compiler will then reject anything outside its proven fixed-slot write lanes.
