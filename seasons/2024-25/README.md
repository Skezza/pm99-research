# PM99 2024/25 all-country source-availability baseline

Status: **raw source intake complete; not a strict V2 package, build, or
playable release.** The previously unavailable source cache has been replaced
by an attributed, content-addressed FootballSquads web snapshot. It does not
infer any missing fact or make a club-to-carrier assignment.

## Attributed FootballSquads source snapshot

The user authorised FootballSquads for non-commercial use with prominent
credit. The source is credited here and in the retained receipt:
[FootballSquads archive](https://footballsquads.co.uk/archive.htm) and
[terms of use](https://www.footballsquads.co.uk/tou.htm).

`sources/footballsquads-web-snapshot.json`
(`39b9a97e7ba282d7d7ab78530b3b5ec4f3e990dc66c8646fd71d721362eb77fa`) pins
the 2026-09-01 acquisition: 43 dated league indexes and 751 local club-page
HTML receipts. The local, ignored snapshot cache is
`.local/external-sources/footballsquads-web/2024-25-r2`; regeneration and
verification read only that cache, not the changing public site.

| Receipt | SHA-256 | Coverage |
| --- | --- | --- |
| `sources/footballsquads-2024-25-web-split.json` | `aa3bdbe321ee246c49eeca93d0e8e3836fa312bf422be8f5a9ce2f63c3542c2d` | 580 clubs / 18,181 player rows |
| `sources/footballsquads-2024-web-calendar.json` | `8dee31bd483b20fff28776e66f0a123258e55589b4bb7219347f04480f658ee8` | 171 clubs / 5,523 player rows |
| `sources/footballsquads-2024-25-web-composed.json` | `5e33e5546f1af6e47a3014a804dd4ccaac05ebdc030a1ab75fdcbee01bcd4da0` | 751 clubs / 23,704 player rows |
| `source-intake.json` | `0e7dcf04113fc99fb691f7b491e771bac01d599d910d0878cc130708a6ef14d5` | Valid raw all-carrier source intake; 2,800 rows retain explicit source gaps. |
| `source-intake-audit.json` | `a3054a24b1e2467ef5a49343001b57bbeda8457fe0d0a84c7e1148ba4bfa0bed` | 451 fixed carriers / 9,390 slots, all explicitly unassigned. |

`source-bundle.json` verifies both dated source conventions and the composed
assignment (`fc3b1b21fe25cfde6f295c5253ac28a49a2645566f79218f50c823b72e88fb30`)
before the raw intake is accepted. A squad-page snapshot is not opening-XI,
formation, transfer-date, or runtime evidence.

## Evidence retained

| Input | SHA-256 | Purpose |
| --- | --- | --- |
| `sources/source-availability.json` | `73894113981d7e20566c37f2d53cecc959a7021e31cf5fd3784e0fd318c3e24e` | Historical proof that the earlier pinned CC0 cache had zero `2024-2025` club files; superseded as an active input by the credited web snapshot above. |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | Native-base inventory of 451 foreign fixed carriers and 9,390 roster slots. |
| `fixed-carrier-ledger.json` | `2f25a79130c5811f4cb11bb0e65fcff1c0628980a7390832b486e40a378a6e79` | Empty 2024/25 authoring ledger, locked to that registry. |
| `fixed-carrier-intake-audit.json` | `12a173aebf7c4a06d0c7fb7abae64995c0b805c03f7df850bfc41225be7cdd03` | Explicit release blockers; it is not evidence of historical content. |

The formerly consulted canonical squad source was
`footballcsv/cache.footballsquads`, revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` (CC0-1.0).  Its `origin/master`
ref is that same revision.  The full Git tree contains no path containing
`2024-2025`; its most recent European split-season catalogues are `2023-2024`.
The detailed, per-top-level-catalogue inventory is in
`sources/source-availability.json`.

The cache remains unavailable for 2024/25, but the attributed snapshot above
now supplies dated squad rows. Stable person reconciliation, managers,
ratings, kits, portraits and opening-lineup facts still need independent,
dated evidence.

## Fixed-carrier state

The ledger uses the unmodified `pm99-gog-en-1998-clean` carrier inventory.  It
preserves the topology and makes no country, division, draw-pool or membership
claim.  All 451 foreign carriers remain `unassigned`; zero player slots, kits
and portrait decisions are complete.  The audit also records 36 shared
baseline player carriers.  Its blockers are `world-content-incomplete` and
`baseline-shared-player-carriers`.

## Calendar component

The clean `MANAGPRE.EXE` input hash
`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158` was
patched locally to the 2024/25 calendar.  The local-only receipt is
`.local/season-2024-25/calendar/calendar-receipt.json`; it records 853
substitutions, target year 2024, rollover 2025, and output hash
`8e941a04ce8994f9039d721795eeb93c047ace1a727565ff9718bad6bd1b75aa`.
That component is not a database build or runtime qualification.

## Stoke City evidence

The source snapshot contains a Stoke City squad page, but it is not opening
lineup evidence. No PM99 build or screenshot exists for 2024/25; producing
one now would misrepresent a raw intake as a release.

## Reproduce

```bash
git -C .local/external-sources/cache.footballsquads rev-parse HEAD
git -C .local/external-sources/cache.footballsquads ls-remote --heads origin
git -C .local/external-sources/cache.footballsquads ls-tree -d -r HEAD | rg '2024-2025'

python3 scripts/capture_footballsquads_web_season.py verify \
  --snapshot seasons/2024-25/sources/footballsquads-web-snapshot.json \
  --cache-root .local/external-sources/footballsquads-web/2024-25-r2 \
  --catalog 2024-2025 \
  --capture seasons/2024-25/sources/footballsquads-2024-25-web-split.json

python3 scripts/capture_footballsquads_web_season.py verify \
  --snapshot seasons/2024-25/sources/footballsquads-web-snapshot.json \
  --cache-root .local/external-sources/footballsquads-web/2024-25-r2 \
  --catalog 2024 \
  --capture seasons/2024-25/sources/footballsquads-2024-web-calendar.json

python3 scripts/season_source_bundle_v1.py verify \
  --bundle seasons/2024-25/source-bundle.json

python3 scripts/season_source_intake_batch_v1.py \
  --seasons-root seasons --season 2024-25

python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2024-25/fixed-carrier-registry.json \
  --ledger seasons/2024-25/fixed-carrier-ledger.json

python3 tools/pm99_calendar_patcher.py \
  .local/season-pipeline-v2/pm99-base-clean/MANAGPRE.EXE \
  --year 2024 \
  --output .local/season-2024-25/calendar/MANAGPRE.EXE \
  --receipt .local/season-2024-25/calendar/calendar-receipt.json
```

## Required next evidence

1. Establish the PM99-supported historical scope and bind every in-scope club
   to a fixed carrier without changing topology.
2. Reconcile people, managers, kits, ratings, portraits/no-photo decisions and
   opening lineups to dated, identity-safe evidence.
3. Only after the ledger is complete, produce a strict package, two matching
   clean builds, static receipts, and a runtime-qualified Stoke lineup
   screenshot.

Until all gates pass, this is a blocker record, not a delivered database.
