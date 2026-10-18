# 2008/09 all-country world intake

## Status

**Not a delivered database.** This directory is a hash-locked source and
fixed-carrier intake for 2008/09. It does not contain a strict
`pm99-season-package-v2`, a game build, runtime qualification, or a Stoke City
lineup screenshot. A historical fact is included only when the referenced
source supplied it; missing facts have not been inferred.

## Source-bundle repair and reprocessed intake

[`source-bundle.json`](source-bundle.json) now makes the two complementary
receipts one hash-locked logical 2008/09 source without relabelling either
original input. It reproduces `sources/footballsquads-2008-09-composed.json`
(`a8949eb281c0004b5275299e83051a760b006806bf78dd4d9742b42be3f8cd4f`) and
the fresh capture-bound `foreign-carrier-assignment-composed.json`
(`b653c2e879c38883c2e8702a1dbffa07c3da6332bfc31bb20d7235d06c0532c6`). The
reprocessed raw source intake is `source-intake.json`
(`5e3ab733d606d5dae8dc7c86eb05bc9247c43f383e676b7395e489702689ae9e`) and its
audit is `source-intake-audit.json`
(`18be348e16db59d7d611cefbb9b6ca5babf2c4992bb531b8cda142b3ea8304bb`).

The composed assignment remains zero approved identities and 451 unassigned
foreign carriers. This fixes the source-composition blocker only; it does
not convert the historical candidate queue into an approval or a PM99 build.

## Captured source receipts

The FootballSquads cache uses two valid historical conventions in this
period. European split-year competitions are captured separately from
calendar-year leagues. The latter have not been coerced into a fictional
`2008/09` source label.

| Receipt | SHA-256 | Clubs | Player rows | Unresolved player rows |
| --- | --- | ---: | ---: | ---: |
| `sources/footballsquads-2008-09-split.json` | `4012b81b2d21615598f4cf3f65a5f4cba3445e1bb361ee925cd3f259c5db73bc` | 554 | 16,652 | 710 |
| `sources/footballsquads-2008-calendar.json` | `3b595695f43d4e5b68debf53c380a3074b92ef4a41193a103c17819f9aba463a` | 126 | 4,057 | 717 |
| **Total** | — | **680** | **20,709** | **1,427** |

Both receipts declare `footballcsv/cache.footballsquads`, revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555`, CC0-1.0. Together they cover 29
source-country catalogs. This is source coverage, not evidence that those
clubs correspond to PM99 membership or carriers.

The retained gaps are: split-year `birth_date` 100, `height_cm` 526,
`primary_position` 4, `shirt_number` 126 and `weight_kg` 588; calendar-year
`birth_date` 19, `height_cm` 59, `shirt_number` 681 and `weight_kg` 64.

The dated Stoke City roster source is `eng/2008-2009/faprem/stoke.txt`, whose
source SHA-256 is
`9b5705a283b37fa8c027eaf85e04e13d89d11da3c3a5d3f288082bd85bd4a797`.
It records squad facts only: it is not evidence of a particular starting XI,
formation, or PM99 runtime display.

## Fixed-carrier intake

The registry was read from the verified `pm99-gog-en-1998-clean` base. Its
DBDAT hashes are JUG
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`, EQ
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`, and ENT
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`.

| Artifact | SHA-256 | Result |
| --- | --- | --- |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | 451 immutable mode-1 carriers / 9,390 roster slots |
| `fixed-carrier-ledger.json` | `99d338b00f1622fad6d16d60e1ed721d426464664eba2a69393bcf26cca77469` | empty, registry-bound 2008/09 ledger |
| `fixed-carrier-intake-audit.json` | `0095fcf254f1636e3171436f5325ea09d5be2974bc2e3969c75faaa11fe9fb3b` | all 451 carriers unassigned; 0 complete slots, kits, or portraits |

The audit also records 36 shared baseline player carriers. They require one
consistent historic identity or an explicit unresolved decision; they cannot
be silently assigned to multiple players.

## Pre-composition Spanish-host identity queue — blocked

The hash-locked empty assignment ledger
`foreign-carrier-assignment.json` (SHA-256
`2bd9973a5cf50dd42dea7f998362591bf4def24a54d9987d33d0102ad65845d8`)
retains six independently reviewed Spanish-host carrier facts: IDs 1, 2, 3,
4, 5 and 7. Its audit (SHA-256
`813b66a4d66e2df918fa39a83879012c6d79a39ae99018dc65ca149897f73930`)
reports zero historical identity assignments and all 451 foreign carriers
unassigned.

Its candidate queue (SHA-256
`4ad81cc5d9aef3e0a63d7256c809f2bfee26ea1f2417f0531d1646cb00c3d8ee`)
has six `no-name-token-candidate` rows and zero candidate clubs. This is an
intentional, validated refusal: the ledger is bound to the calendar-year
receipt `sources/footballsquads-2008-calendar.json`, whose catalogs are
Brazil, China, Ireland, Japan, Norway, Russia, Sweden and USA—none is
`spain`. The separate split-year receipt does contain a Spanish catalog, but
has a different hash and cannot silently replace the queue's bound source.

That historical queue remains retained but is not the active composed
assignment. Candidate-proposal generation consequently refuses with `queue has no
unassigned single capacity-compatible candidate leads`. No proposal, identity
approval, PM99 write, or release claim was made. This is absence in the bound
capture, not a claim that no 2008/09 Spanish historical source exists.

## Proven local calendar component

`tools/pm99_calendar_patcher.py` accepted the verified base executable and
created the local-only file
`.local/builds/2008-09-calendar/MANAGPRE.EXE`. The receipt at
`.local/builds/2008-09-calendar/calendar-receipt.json` reports 853 recognised
operands, target year 2008, rollover year 2009, and output SHA-256
`14c1775361035b74460febb7110e13fbeb8562cf88d14e675965e704691764b2`.
This does not qualify a database build.

## Release blockers

1. PM99 has 543 existing modern club carriers (92 mode 0 and 451 mode 1),
   whereas this broad source capture contains 680 clubs. The format has no
   approved writer for extra carriers, countries, division membership or draw
   pools. Source competition names are provenance, never write instructions.
2. No carrier-to-historic-club assignments have been reviewed. All 451
   foreign carriers are therefore correctly unassigned.
3. Club and person reconciliation, managers, ratings, kits,
   portraits/no-photo decisions, and opening-XI evidence are absent. The
   captured rows retain their source gaps rather than inventing replacements.
4. Mode-1 opening lineup/player-to-grid writing is not a complete approved
   release transaction. A broad all-country runtime proof is required before
   package compilation can claim historical opening states.
5. With no valid build and no runtime qualification, there is no reliable
   Stoke City lineup screenshot. None is supplied.

## Reproduction

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2008-2009 \
  --output seasons/2008-09/sources/footballsquads-2008-09-split.json

python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2008 \
  --output seasons/2008-09/sources/footballsquads-2008-calendar.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-base-clean-fixed-carriers \
  --output seasons/2008-09/fixed-carrier-registry.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2008-09/fixed-carrier-registry.json \
  --ledger-id pm99-2008-09-fixed-carrier-intake --start-year 2008 \
  --output seasons/2008-09/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2008-09/fixed-carrier-registry.json \
  --ledger seasons/2008-09/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2008-09/fixed-carrier-registry.json \
  --ledger seasons/2008-09/fixed-carrier-ledger.json \
  --output seasons/2008-09/fixed-carrier-intake-audit.json
```
