# 2009/10 world-season intake

## Status

**Not delivered.** This is source and fixed-carrier intake only. It contains no strict `pm99-season-package-v2`, no materialised PM99 database, no two matching clean builds, no runtime proof, and no Stoke City lineup screenshot. No club identity has been inferred from a baseline PM99 carrier.

Stoke City's 31-player source roster is retained at `eng/2009-2010/faprem/stoke.txt` (source SHA-256 `e0b7312f054d54f6c5b885b5c8ac035fb8b083c91181c609ad9109979d07cb06`), but it is not opening-XI evidence and cannot support a runtime screenshot.

The intended scope is an all-country world update under immutable PM99 carrier topology. These captures are roster-source evidence, not proof that every source club maps to a PM99 fixed carrier.

## Source-bundle repair and reprocessed intake

[`source-bundle.json`](source-bundle.json) now names both dated conventions,
their exact hashes, and the safe assignment rebinding. It verifies the
composed capture `sources/footballsquads-2009-10-composed-v2.json`
(`e0b5b239063c0ac8085bb4d9c5598de3ae14940928950f6716585368610e346c`) and
the derived `foreign-carrier-assignment-composed-v2.json`
(`b55ec26e58e221dd5218f10b1e4007832ec82566e7fd4b4777bf4793c3aea3d1`). The
reprocessed raw source intake is `source-intake.json`
(`9dabf1938d32fae00abea2e1ccd488a3a58b66c60a5a064b7834664bc878d73d`) and its
audit is `source-intake-audit.json`
(`d7ebad308c5518b2dd5cf2ea435d7dc5012d2c339f4cc859394099b188d14877`).

It closes only the split/calendar source selection gap. The v2 composed
capture also retains the two explicitly blocked raw pages; the prior receipts
are preserved under `*-before-blocked-source-preservation.json`. The derived
assignment still has 451 unassigned carriers; it does not promote the six
older candidate leads, alter topology, or create a build.

## Canonical source captures

Both captures use `footballcsv/cache.footballsquads`, revision `187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` (CC0-1.0), and retain a SHA-256 for each original club file.

| Capture | Coverage | SHA-256 |
| --- | --- | --- |
| `sources/footballsquads-2009-10-split.json` | 21 split-year country catalogues; 552 club records; 17,067 player rows | `15b3cb02913c04b914d1367d6cff2b978e3634a2ec37a7058094b8222909782c` |
| `sources/footballsquads-2009-calendar.json` | 8 calendar-year country catalogues; 127 club records; 3,998 player rows | `e5394dab59281c60ffd59ba5c87f604b36fe3a2f2641231e09bf98b7d8b4b1dd` |

Together the receipts cover all 29 locally available source catalogues, with 679 club records and 21,065 player rows. 1,271 rows have one or more explicit source gaps: 102 birth-date, 639 height, 732 weight, 582 shirt-number, and 1 primary-position gaps. These are source facts to reconcile; they are not values that may be inferred.

The calendar-year receipt deliberately remains separate. It records Brazil, China, Ireland, Japan, Norway, Russia, Sweden, and the USA under their source's calendar-year convention; it is not coerced to a fictional `2009/10` title.

## Source blockers retained in the split receipt

The shared importer distinguishes past-only material from a current squad and retains it as a hash-pinned blocker. It did not reinterpret the rows as an opening roster.

| Original source | SHA-256 | Recorded blocker |
| --- | --- | --- |
| `belgium/2009-2010/prolge/mouscron.txt` | `4b1f87f2539fd4039f302e28c26691c7c073b2d5b43df1858d116deb57bc8bf3` | `contains no current-squad CSV section` |
| `eng/2009-2010/confprem/chester.txt` | `c58da4bb7d4d2ab356724e4f36d3c2b199870c29b8b58f6a52a63a89ced0ff85` | `contains no current-squad CSV section` |

The source tool recognises the Mexican `2010 Bicentenario` dated phase, so the Mexican Apertura and Bicentenario records are part of the split capture.

## Fixed-carrier intake

The registry was generated from the verified `pm99-gog-en-1998-clean` base. It contains 451 existing foreign mode-1 carriers and 9,390 immutable roster slots. It is a capacity/layout constraint, not historical club, country, division, or competition evidence.

| Receipt | SHA-256 | Result |
| --- | --- | --- |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | Baseline carrier inventory retained. |
| `fixed-carrier-ledger.json` | `fca6295c692d8879165514d63ee57d54545ebdbafa2e1a843a702081a282e91b` | Empty, registry-locked 2009/10 authoring ledger. |
| `fixed-carrier-intake-audit.json` | `6bba0edfd785976f1f34bd54684df808281d00ecd4bfcce6f6fdc838acbe2a22` | Release blocked: all 451 carriers unassigned; 36 shared baseline player carriers unresolved. |

## Candidate-only identity milestone

The guarded candidate milestone derives six eligible **single name-token leads** from the six independently reviewed Spanish host-country facts and the split-year capture pinned by the base assignment. The leads are Barcelona, Deportivo La Coruña, Zaragoza, Real Madrid, Athletic Bilbao, and Valencia. Every row has status `candidate`, not `approved`, and retains blockers for independent identity review and the complete club/player/manager/kit/portrait/runtime transaction.

| Candidate-only receipt | SHA-256 | Result |
| --- | --- | --- |
| `foreign-carrier-candidate-proposal.json` | `841bf02aa3f65ccf2ed83bb8efca39e7716f13f12a3c940e849969d241340bc2` | Six unapproved candidate proposals. |
| `foreign-carrier-assignment-candidates.json` | `d8ca267403e94cc389dc84e8a3e32a72204a1f39c98e1713812b6079d368f4a0` | Derived candidate ledger; the base assignment remains unchanged. |
| `foreign-carrier-assignment-candidates-audit.json` | `11a290862ef0eec03d5ec7e676b33a261e27841f33cee5fe336177fa68fc4f23` | Six candidate rows, 445 unassigned carriers, and `identity-assignment-incomplete`. |

This milestone does not approve a historical identity, write PM99, alter carrier topology, or claim a database release.

## Calendar evidence (local only)

The verified-base calendar patcher produced a local 2009-to-2010 executable candidate: 853 patches, target year 2009, rollover 2010. The output SHA-256 is `316f5908cf001cdd3c6959d7cefa39b26958d7934d7107e430f194a4a806b2a9`; the receipt SHA-256 is `cb6ae88b540e13c0e2c20ead45d19ea8fc42a86f958dfd67a4d2044ba12ded79`. Both remain local under `.local/builds/2009-10-calendar/`. This is neither a database build nor runtime proof.

## Required work before delivery

1. Obtain dated replacement evidence for the two past-only squad blockers and reconcile every included club, manager, and player to stable identities.
2. Attach source-backed facts, ratings, kits, portraits/no-photo decisions, and opening evidence. Preserve all unresolved facts as blockers until reviewed.
3. Complete all 451 carrier assignments, resolve shared JUG carrier identities, and obtain an audit with no blockers.
4. Create and strictly validate a native V2 package, then make two independent, byte-identical builds with static validation receipts.
5. Qualify the final inventory at runtime. Only then capture a safe local Stoke City starting-XI screenshot and record its SHA-256 in the attestation.

## Reproduction and checks

```bash
python3 scripts/capture_footballsquads_season.py --source-root .local/external-sources/cache.footballsquads --season 2009-2010 --output seasons/2009-10/sources/footballsquads-2009-10-split.json
python3 scripts/capture_footballsquads_season.py --source-root .local/external-sources/cache.footballsquads --season 2009 --output seasons/2009-10/sources/footballsquads-2009-calendar.json
python3 scripts/world_fixed_carrier_ledger_v2.py validate --registry seasons/2009-10/fixed-carrier-registry.json --ledger seasons/2009-10/fixed-carrier-ledger.json
python3 scripts/world_fixed_carrier_ledger_v2.py audit --registry seasons/2009-10/fixed-carrier-registry.json --ledger seasons/2009-10/fixed-carrier-ledger.json --output seasons/2009-10/fixed-carrier-intake-audit.json
sha256sum seasons/2009-10/sources/*.json seasons/2009-10/fixed-carrier-*.json
```
