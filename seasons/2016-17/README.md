# 2016/17 all-country world intake

**Status: intake only — not a delivered PM99 database.**

This directory records the first reproducible evidence and carrier-capacity
intake for the 2016/17 world-season workstream.  It is deliberately not a
`pm99-season-package-v2` package, game build, or release candidate.  No club
has been mapped to a PM99 foreign carrier and no player, manager, rating, kit,
portrait, opening lineup, or competition-membership fact has been inferred.

## Captured source scope

`sources/footballsquads-2016-17.json`

- SHA-256: `0e974be2496cdfb8b83765b73769226155c808b67c341f78c3f247c5ee88f798`
- source: local `footballcsv/cache.footballsquads`, revision
  `187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555`, CC0-1.0
- season catalogue: `2016-2017` (`2016/17`)
- 596 club-squad files; 17,876 player rows; 23 country catalogues and 34
  competition catalogues
- each club record retains its source path and individual SHA-256 receipt

The capture reports, rather than fills, 733 rows with unresolved physical or
shirt facts: 85 birth dates, 629 heights, 671 weights, and 69 shirt numbers.
It contains no evidence for ratings, managers, kits, portraits, opening-date
ownership, or starting lineups.

Stoke City is present in the source capture as
`eng/2016-2017/faprem/stoke.txt` (SHA-256
`50092373787542d887d1dfadb4b865f5569eec60026c8a44f8dd7f8f37b64e32`), with
49 roster rows.  That is roster evidence only; it is not a match-specific
starting XI.  There is therefore no valid Stoke runtime screenshot.

## Fixed-carrier intake

- `fixed-carrier-registry.json`
  - SHA-256: `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375`
  - 451 native foreign carriers and 9,390 native roster slots from the verified
    clean base.
- `fixed-carrier-ledger.json`
  - SHA-256: `3fc80759c7f501ca675ba5a82d346440e429687e40584655047baf2eb7c5750b`
  - valid empty 2016/17 authoring ledger locked to the registry.
- `fixed-carrier-audit.json`
  - SHA-256: `4fbea0e761bd097cf8e45c60e37130c03a9cdc5eddd5c78431ef60fce4514697`
  - reports all 451 foreign carriers unassigned, zero complete player slots,
    kits, and portraits, plus 36 shared baseline player carriers requiring
    consistent identity decisions.

The registry is a binary capacity contract only.  It does not establish a
2016/17 country, division, club, draw-pool, or competition assignment.

## Candidate-only carrier-identity milestone

The deterministic coordinator has converted the existing reviewed host-country
queue into a separate, **unapproved** candidate layer.  It has not modified
`foreign-carrier-assignment.json`, `fixed-carrier-ledger.json`, or any PM99
file.

| File | SHA-256 | Result |
| --- | --- | --- |
| `foreign-carrier-candidate-proposal.json` | `2658359bb7495bd80bd46d0c1762216eae859602789028231e222519f6b68d62` | Six single, capacity-compatible source-name leads. |
| `foreign-carrier-assignment-candidates.json` | `138bca3dfe22cea02f9a2ba3194b37d914f994344c0767643552db548bf50714` | Separate derived assignment: six `candidate` identities and 445 unassigned foreign carriers. |
| `foreign-carrier-assignment-candidates-audit.json` | `73a47dd320501cb7226be7126f9b6bf6ba63f8e55806f6762cd2b36422ddf4ae` | Canonical audit of that separate candidate assignment. |

The six leads are existing Spanish host-country carriers 1, 2, 3, 4, 5 and 7,
with source selectors for Barcelona, Deportivo La Coruña, Zaragoza, Real
Madrid, Athletic Bilbao and Valencia respectively.  Each requires independent
club-identity review, approval of the display-name link, and a complete club,
player, manager, kit, portrait/no-photo, package, clean-build and runtime
transaction.  The source competition catalogue remains provenance only; it is
not a PM99 membership, division, country, draw-pool, or topology claim.

## Calendar component proof

A local, non-release calendar artefact was generated from the verified base:

- local output: `.local/builds/2016-17-intake-calendar/MANAGPRE.EXE`
- output SHA-256: `2681654af1b1b6498d8566685e49f0659536f6c89ea4a8f558c9a7df62ed262f`
- receipt: `.local/builds/2016-17-intake-calendar/calendar-receipt.json`
  (SHA-256 `e980cccd313d2f125fd39534c513c059b2602538340e5e8410fe8a39ac6b8d0b`)
- target year / rollover: 2016 / 2017; 853 verified substitutions.

This confirms only the supported calendar transformation.  It is not runtime
qualification and must not be combined with an incomplete database.

## Reproduce

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2016-2017 \
  --country arg --country australia --country austria --country belgium \
  --country chile --country czech --country denmark --country eng \
  --country france --country ger --country greece --country hungary \
  --country italy --country mexico --country netherl --country poland \
  --country portugal --country russia --country scots --country spain \
  --country switz --country turkey --country ukraine \
  --output seasons/2016-17/sources/footballsquads-2016-17.json

python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2016-17/fixed-carrier-registry.json \
  --ledger seasons/2016-17/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2016-17/fixed-carrier-registry.json \
  --ledger seasons/2016-17/fixed-carrier-ledger.json \
  --output seasons/2016-17/fixed-carrier-audit.json

python3 scripts/season_candidate_identity_milestone_v1.py \
  --season-dir seasons/2016-17

python3 scripts/foreign_carrier_candidate_proposal_v1.py \
  --registry seasons/2016-17/fixed-carrier-registry.json \
  --source-capture seasons/2016-17/sources/footballsquads-2016-17.json \
  --assignment seasons/2016-17/foreign-carrier-assignment.json \
  --queue seasons/2016-17/foreign-carrier-candidate-queue.json \
  --proposal seasons/2016-17/foreign-carrier-candidate-proposal.json

python3 scripts/foreign_carrier_assignment_v1.py \
  --registry seasons/2016-17/fixed-carrier-registry.json \
  --source-capture seasons/2016-17/sources/footballsquads-2016-17.json \
  --assignment seasons/2016-17/foreign-carrier-assignment-candidates.json \
  --output /tmp/pm99-2016-17-candidate-assignment-audit.json
```

## Release blockers and next authoring work

This intake cannot be compiled or delivered.  To reach the all-country world
release gate, it needs source-backed club-to-carrier assignments; stable person
reconciliation and opening-date ownership; complete manager, rating, kit, and
portrait/no-photo receipts; every required fixed-carrier slot resolved
consistently; a strict package; two byte-identical clean builds; static and
runtime qualification; and, only then, a Stoke City lineup screenshot tied to
that finished inventory.
