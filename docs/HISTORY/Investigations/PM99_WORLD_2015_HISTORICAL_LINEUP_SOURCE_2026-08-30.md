# 2015/16 historical lineup source qualification (2026-08-30)

## Result

A local, reproducible source snapshot has been qualified for **opening XI,
bench, shirt number, manager, ground and declared formation** facts.  It is
the published Transfermarkt-derived DuckDB dataset from the public
`jso-w/transfermarkt-datasets-f` project.  The raw database is local-only at
`.local/external-sources/transfermarkt-datasets/transfermarkt-datasets.duckdb`
and is not part of PM99RE or any release.

The source has 2015/16 games from 30 June 2015 through 10 July 2016, and its
`game_lineups` table supplies individual starting/bench rows.  Its `games`
table carries home/away manager, stadium, and formation fields.  This directly
addresses a real gap in the earlier squad-only capture: a club roster alone
cannot determine PM99's opening XI or shape.

## 2015/16 domestic league coverage

The snapshot has a complete season game route for the following country
families: Belgium, Denmark, England, France, Germany, Greece, Italy,
Netherlands, Portugal, Russia, Scotland, Spain, Türkiye and Ukraine.  It is a
supplementary *dated evidence source*, not a claim that every PM99 foreign
carrier already has a historical assignment.

English is intentionally excluded from the foreign receipt because the
English-92 release has its own carrier-mapped first-fixture evidence lane. The
foreign receipt therefore covers the other **13 countries / 218 source clubs**
in this snapshot, rather than incorrectly calling the 14-country raw route a
13-country foreign route.

It does **not** currently close the uncaptured-country queue (for example
Serbia, Croatia and Romania) and it does not include player ratings.  Existing
source reconciliation and the review ledger therefore remain mandatory.

## Compiler contract

When this source is promoted into the package pipeline it must:

1. save the exact source URL, download SHA-256 and selection query in the
   season source receipt;
2. pick a declared opening-date fixture per club, rather than taking a random
   season lineup;
3. reconcile player identities using the existing strict date-of-birth rules;
4. use its formation only as a source fact until the mode-1 player-to-grid
   mapping is runtime-proven; and
5. leave a missing or ambiguous row unresolved for review.  It must never
   substitute a current player table value for historical club membership.

The relevant reproducible source project is
https://github.com/jso-w/transfermarkt-datasets-f .

## Deterministic receipt (2026-08-31)

`scripts/extract_2015_world_transfermarkt_opening_fixtures.py` turns that
local-only DuckDB file into a canonical source receipt without touching a PM99
file:

```bash
python3 -m pip install duckdb
python3 scripts/extract_2015_world_transfermarkt_opening_fixtures.py \
  --database .local/external-sources/transfermarkt-datasets/transfermarkt-datasets.duckdb \
  --output .local/season-pipeline-v2/world-2015-transfermarkt-opening-fixtures.json
```

The receipt pins the local snapshot SHA-256, supplied dataset version and the
selection policy. It selects each club's earliest domestic fixture by
`date, game_id`, retains its XI, named substitutes, shirt numbers, manager,
formation and reported match stadium, then separately records the earliest
home-fixture stadium as **ground evidence only**.

Against the qualified local snapshot (`154367dfa6d6eb0b86332e332f9df0a080c7ddce`),
the result is:

| Fact available in the first-fixture receipt | Foreign clubs |
| --- | ---: |
| Source club contexts | 218 |
| Exact 11-player opening XI | 214 |
| Named fixture manager | 218 |
| Reported opening-fixture stadium | 218 |
| Reported earliest-home-fixture stadium | 218 |
| Declared formation | 214 |
| Missing XI and declared formation — review required | 4 |

The four omissions are Dutch rows: Roda JC Kerkrade, FC Groningen, FC Twente
Enschede and Heracles Almelo. They have neither source lineup rows nor a
declared formation, and remain explicit `requires-review` rows. The receipt
makes **no** persistent-ground/capacity claim, does not supply a kit, portrait
or rating, and deliberately contains no PM99 carrier, roster-slot or
tactics-grid assignment. It cannot be fed to the writer until those separate
contracts are satisfied.

An intentionally strict, accent-insensitive club-name comparison against the
existing FootballSquads capture finds only **93 of 218** receipt clubs with one
identical source-club identity; **125** have no such match, commonly because
the two sources use a different historical/expanded club label. That is an
identity-review queue, not permission to fuzzy-join the squad and lineup
sources or to attach either one to a PM99 carrier.
