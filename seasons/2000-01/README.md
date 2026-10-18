# PM99 2000/01 all-country intake milestone

Status: **dated squad-source and fixed-carrier intake complete; not a strict
V2 package, database build, playable release, or runtime-qualified season.**
This folder records only facts that can be reproduced from the locally pinned
source cache and the clean native PM99 carrier inventory.  It must not be
represented as a delivered world update.

## Durable inputs

| Input | SHA-256 | Purpose |
| --- | --- | --- |
| `sources/footballsquads-2000-01.json` | `55f5f4b1eb49b95dff90b9a1053bc67a55a0c8d675dd58003ffd6f99fbfcf169` | Dated club-squad facts captured from 178 FootballSquads pages. |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | Clean-base foreign carrier inventory: 451 clubs and 9,390 roster slots. |
| `fixed-carrier-ledger.json` | `bcf17b90e6402d57b80797d43b096123a9eec4490fa04699a61d1ea31527e946` | Empty 2000/01 authoring ledger, locked to the registry. |
| `fixed-carrier-intake-audit.json` | `8fe22a58ca7a84a3d7c14c5d9013f8809bce9b4c15e99de657ba9748171c63c1` | Initial coverage audit and release blockers. |
| `source-intake.json` | `3e81c2a83d9c78ea6fb624a0658e983d09ddb8fe2b5ddfb1734988ed6f788de6` | Generic raw, all-carrier source intake; it contains no PM99 writes or inferred identities. |
| `source-intake-audit.json` | `b7799f7ec93b54fef1de75c0f074e1ec325b57f667aa66f6e8226216632b727f` | Generic source-intake coverage receipt and explicit non-release blockers. |

The squad capture is pinned to `footballcsv/cache.footballsquads` revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` (CC0-1.0).  It covers 5,590
players in nine competition catalogues:

| Catalogue | Clubs | Players |
| --- | ---: | ---: |
| England | 92 | 2,965 |
| France | 18 | 505 |
| Germany | 18 | 523 |
| Italy | 18 | 578 |
| Scotland | 12 | 436 |
| Spain | 20 | 583 |

This is not all-country source coverage.  It is only the dated catalogue
content available locally for 2000/01; no inference has filled countries or
clubs absent from it.

### Reproducible foreign-squad expansion

`sources/transfermarkt-historical-squad-scope-v1.json` declares a separate,
season-neutral source route for 20 historical top divisions absent from the
early FootballSquads cache. The declaration pins reviewed Transfermarkt
competition identifiers; it does not fuzzy-match PM99 club names. Run:

```bash
python3 scripts/capture_transfermarkt_historical_squads_v1.py \
  --scope seasons/2000-01/sources/transfermarkt-historical-squad-scope-v1.json \
  --season-start-year 2000 \
  --cache-dir .local/season-2000-01/transfermarkt-historical-squad-cache-v1 \
  --output .local/season-2000-01/transfermarkt-historical-squads-v1.json \
  --gaps-output .local/season-2000-01/transfermarkt-historical-squad-gaps-v1.json
```

The first run caches the exact historical competition and squad pages; use
`--offline` thereafter. Transfermarkt is credited for the published factual
competition and squad data. Every retained page has its URL-equivalent cache
key and SHA-256 in the capture. This project does not redistribute page
artwork. An inaccessible competition or club becomes an explicit gap and no
player or secondary fact is invented.

National Football Teams is additionally credited for exact historical club
index and player-appearance facts used to investigate fixed-carrier gaps. Its
captured URLs and response hashes are retained locally. These rows are often
too sparse to establish an opening squad: fewer than eleven players is an
explicit source blocker, and eleven alone does not make a release allocation.
A release allocation requires enough dated players to fill the chosen
carrier's complete writable roster capacity unless a separate runtime-proven
vacancy policy is supplied.

The current expanded local work is published through the atomic manifest
`.local/season-historical-squad-backfill-v1/2000-01/current.json`. Each
revision lives in a new immutable `revisions/<revision-id>/` directory and the
manifest binds the source, gap receipt, allocation, assignment and intake by
SHA-256. Downstream jobs must verify those hashes rather than trusting a
well-known filename while another source pass is running.

## Source gaps and carrier constraints

The early FootballSquads source has no nationality column.  All 5,590 rows
therefore carry an explicit `nationality` gap.  The capture also records 50
missing birth dates, 129 heights, 134 weights, 11 primary positions and eight
shirt numbers.  A strict package needs every applicable fact reconciled to
stable identities before it can write a PM99 carrier.

The registry uses the hash-locked `pm99-gog-en-1998-clean` baseline:

| File | SHA-256 |
| --- | --- |
| `DBDAT/JUG98030.FDI` | `95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844` |
| `DBDAT/EQ98030.FDI` | `e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c` |
| `DBDAT/ENT98030.FDI` | `729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238` |

No foreign carrier is assigned in this milestone.  The audit correctly reports
451 unassigned foreign carriers, zero complete player slots, zero kit and
portrait decisions, and 36 shared baseline player carriers.  The baseline is
only a capacity inventory: it is not evidence that any existing club identity,
membership or roster is historically correct for 2000/01.  Country, division,
draw-pool and competition topology remain untouched.

## Candidate-only Spanish identity pilot

Six Spanish carrier/source links have subsequently been derived as separate
**candidate-only** review rows.  They leave the base assignment ledger above
unchanged, retain three explicit blockers per row, and leave 445 foreign
carriers unassigned.  They are not club updates or approved identities.  See
[the 2000/01 candidate-identity pilot](../../docs/2000_01_FOREIGN_CARRIER_CANDIDATE_IDENTITY_PILOT_2026-08-31.md)
for the exact proposal, derived-ledger and audit hashes.

## Calendar proof

The clean `MANAGPRE.EXE` (`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158`)
was patched locally for target year 2000 and rollover 2001.  The local receipt
at `.local/builds/2000-01-calendar/calendar-receipt.json` records 853 patches;
the resulting executable hash is
`cd065504ea1225d9e29942cbf08fa393f0fe97f7c37a45e7b42482b4681e42a0`.
Those proprietary local files are not a release and do not provide database or
runtime proof.

## Stoke City evidence

The source capture includes the dated 29-player Stoke City squad at
`eng/2000-2001/d2/stoke.txt` (source SHA-256
`2025590b984ae4427a2516d36157c7297a0b465b5eb8f1f87189b2e2636c88ba`) in
English Football League Division Two.  That FootballSquads input is a squad
list, not an opening-fixture source on its own; the separate source backfill
below supplies the match-report XI evidence. No carrier mapping, strict English
package, playable game tree, or runtime screenshot exists; consequently there
is no reliable Stoke City lineup screenshot for this milestone.

## First-fixture source backfill (unreleased)

The reusable first-fixture capture stage selects a club only from the published
roster for the declared season and competition, then records that club's
earliest published domestic-league fixture. Every response is cached locally
with a SHA-256 receipt; an offline rerun consumes those same bytes. This is a
**source backfill**, not a PM99 write or release.

| Gate | Result |
| --- | ---: |
| Dated squad-source clubs | 178 |
| First-fixture XIs captured | 154 |
| Captures with a published formation and at least five bench players | 49 |
| XIs reconciled uniquely to the dated squad source | 67 |
| First-fixture starters absent from that squad source | 140 |
| Those dated starters with a captured source profile | 139 |
| English Division Three clubs without a season roster in this source | 24 |

| Local receipt | SHA-256 |
| --- | --- |
| `.local/season-2000-01/opening-lineup-source-v1.json` | `4709c81e993aa5d3cc2a683860b757ccf3b5b20a92cc7dda1f20ba57c524e753` |
| `.local/season-2000-01/opening-lineup-reconciliation-v1.json` | `3f908c1ce06c85e6d564fe56d392e48ff417c4db6f2db4a90ba661c70b218d28` |
| `.local/season-2000-01/opening-lineup-person-evidence-v1.json` | `555e9e2af0de188130503e819f56eed6dbb0fdad2c4926872ab7045d0bb4f0ce` |
| `.local/season-2000-01/opening-lineup-reconciliation-profile-v1.json` | `1aae5893ad41782b4175903a072c4f8a15a6b140cd7edd48baae4c0e33d0edd3` |
| `.local/season-2000-01/opening-fixture-player-additions-v1.json` | `167acfc6f0c901f3401e43f4cb5e2ebca6339f36ab849ccbe7d22de89f77146f` |

Transfermarkt is credited as the source of its published season competition
rosters, schedules and match reports. Older reports can publish an XI grouped
by position but neither formation grid nor bench; those remain explicit source
blockers rather than inferred tactics. Stoke's 12 August 2000 first league
fixture against Wycombe has an 11/11-reconciled XI and manager, but its source
report lacks a formation grid and bench. It is therefore not eligible for a
historical PM99 tactics preset or in-game screenshot claim yet.

The person-evidence stage snapshots only unresolved match-report player IDs.
It links one to the dated roster only when its published date of birth occurs
once in that club's source squad. The current pass supplied 250 of 251 profiles
and 111 such links; its one missing published birth-date fact remains a queue
item rather than a guessed match.

The remaining 140 first-fixture starters are not treated as parser failures or
silently substituted with people from the later-season squad list. They are
materialised as a separate hash-bound opening-date additions queue: 139 carry
the linked profile's published name, date of birth, nationality label, broad
position label and height where published; one remains profile facts pending.
That queue proves a person appeared in the opening fixture, but does not
allocate a fixed PM99 carrier or make a roster replacement.

### English Division Three source-rights gate

The 24 uncovered English Division Three clubs are a source-availability gap,
not a variable-length-string or PM99 database-format limitation. AFS/11v11
has historical reports for the opening fixtures, but its terms permit private
reading/downloading and prohibit copying, redistribution and derivative use
without express permission. The source also returns an access-control page to
the reproducible cache client. It has therefore **not** been scraped or merged
into this receipt. A narrow written AFS licence (or a licensed historical
extract from Stats Perform/Football DataCo) must explicitly cover the 24
fixtures, XI, full bench, manager, local snapshot cache and database use before
an adapter can be enabled. Credit alone is not a substitute for that permission.

The capture cache now rejects access-control interstitials—even large ones—so
they cannot be mistaken for immutable source evidence. It also orders same-day
fixtures by numeric source match id, rather than lexical string order.

## Reproduce

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2000-2001 \
  --output seasons/2000-01/sources/footballsquads-2000-01.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-base-clean-fixed-carriers \
  --output seasons/2000-01/fixed-carrier-registry.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2000-01/fixed-carrier-registry.json \
  --ledger-id pm99-2000-01-fixed-carrier-intake --start-year 2000 \
  --output seasons/2000-01/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2000-01/fixed-carrier-registry.json \
  --ledger seasons/2000-01/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2000-01/fixed-carrier-registry.json \
  --ledger seasons/2000-01/fixed-carrier-ledger.json \
  --output seasons/2000-01/fixed-carrier-intake-audit.json

python3 scripts/season_source_intake_v1.py build \
  --registry seasons/2000-01/fixed-carrier-registry.json \
  --source-capture seasons/2000-01/sources/footballsquads-2000-01.json \
  --assignment seasons/2000-01/foreign-carrier-assignment.json \
  --intake-id world-2000-01-source-intake \
  --output seasons/2000-01/source-intake.json

python3 scripts/season_source_intake_v1.py audit \
  --registry seasons/2000-01/fixed-carrier-registry.json \
  --source-capture seasons/2000-01/sources/footballsquads-2000-01.json \
  --assignment seasons/2000-01/foreign-carrier-assignment.json \
  --intake seasons/2000-01/source-intake.json \
  --output seasons/2000-01/source-intake-audit.json

# Initial source pass; caches published source pages locally.
python3 scripts/capture_transfermarkt_opening_lineups_v1.py \
  --source-capture seasons/2000-01/sources/footballsquads-2000-01.json \
  --competition-map scripts/data/transfermarkt-opening-lineup-competition-map-2000-01-early-six-v1.json \
  --club-identity-aliases seasons/2000-01/opening-lineup-club-identity-aliases-v1.json \
  --season-start-year 2000 \
  --cache-dir .local/season-2000-01/transfermarkt-opening-lineups-cache-v1 \
  --output .local/season-2000-01/opening-lineup-source-v1.json

# Deterministic repeat; makes no network request.
python3 scripts/capture_transfermarkt_opening_lineups_v1.py \
  --source-capture seasons/2000-01/sources/footballsquads-2000-01.json \
  --competition-map scripts/data/transfermarkt-opening-lineup-competition-map-2000-01-early-six-v1.json \
  --club-identity-aliases seasons/2000-01/opening-lineup-club-identity-aliases-v1.json \
  --season-start-year 2000 \
  --cache-dir .local/season-2000-01/transfermarkt-opening-lineups-cache-v1 \
  --output .local/season-2000-01/opening-lineup-source-v1.json \
  --offline

python3 scripts/reconcile_transfermarkt_opening_lineups_v1.py \
  --source-capture seasons/2000-01/sources/footballsquads-2000-01.json \
  --lineup-capture .local/season-2000-01/opening-lineup-source-v1.json \
  --manual-aliases seasons/2000-01/opening-lineup-identity-aliases-v1.json \
  --output .local/season-2000-01/opening-lineup-reconciliation-v1.json

python3 scripts/capture_transfermarkt_lineup_person_evidence_v1.py \
  --lineup-capture .local/season-2000-01/opening-lineup-source-v1.json \
  --reconciliation .local/season-2000-01/opening-lineup-reconciliation-v1.json \
  --cache-dir .local/season-2000-01/transfermarkt-lineup-person-cache-v1 \
  --output .local/season-2000-01/opening-lineup-person-evidence-v1.json

python3 scripts/reconcile_transfermarkt_opening_lineups_v1.py \
  --source-capture seasons/2000-01/sources/footballsquads-2000-01.json \
  --lineup-capture .local/season-2000-01/opening-lineup-source-v1.json \
  --manual-aliases seasons/2000-01/opening-lineup-identity-aliases-v1.json \
  --person-evidence .local/season-2000-01/opening-lineup-person-evidence-v1.json \
  --output .local/season-2000-01/opening-lineup-reconciliation-profile-v1.json

python3 scripts/derive_transfermarkt_opening_player_additions_v1.py \
  --source-capture seasons/2000-01/sources/footballsquads-2000-01.json \
  --lineup-capture .local/season-2000-01/opening-lineup-source-v1.json \
  --reconciliation .local/season-2000-01/opening-lineup-reconciliation-profile-v1.json \
  --person-evidence .local/season-2000-01/opening-lineup-person-evidence-v1.json \
  --output .local/season-2000-01/opening-fixture-player-additions-v1.json
```

## Required work before delivery

1. Capture and reconcile dated sources for every fixed foreign carrier and
   every English club, including stable people, managers and opening fixtures.
2. Resolve the recorded player-fact gaps without guessing, then bind each
   sourced club and player to its permitted carrier family while preserving
   shared references and native topology.
3. Add source-backed ratings, kit decisions and era-correct portrait or
   native-no-photo dispositions for every package player.
4. Validate one complete strict V2 package, make two identical clean builds,
   pass static audits, and attach runtime evidence from the exact release.
5. Produce a Stoke City screenshot only after the exact opening XI and
   formation are evidenced and the release has passed the preceding gates.
