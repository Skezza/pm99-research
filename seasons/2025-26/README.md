# PM99 2025/26 all-country world workstream

**Status: raw source intake complete; not a delivered database.**

The earlier CC0 cache is still absent for this season, but it has been
replaced by a user-authorised, attributed FootballSquads web snapshot. This
directory remains a source intake only: it contains no club-to-carrier
identity approval, manager, rating, kit, portrait, opening-lineup, package,
or game-build claim.

## Attributed FootballSquads source snapshot

The user authorised FootballSquads for non-commercial use with prominent
credit. The source is credited here and in the retained receipt:
[FootballSquads archive](https://footballsquads.co.uk/archive.htm) and
[terms of use](https://www.footballsquads.co.uk/tou.htm).

`sources/footballsquads-web-snapshot.json`
(`23cd0b5d068f330e95fbc2557a3054a6dab0d7a1fd6809c0b6b374c50d661d82`) pins
the 2026-09-01 acquisition: 41 dated league indexes and 734 local club-page
HTML receipts. The local, ignored snapshot cache is
`.local/external-sources/footballsquads-web/2025-26-r1`; regeneration and
verification read only that cache, not the changing public site.

| Receipt | SHA-256 | Coverage |
| --- | --- | --- |
| `sources/footballsquads-2025-26-web-split.json` | `88f106e47bdc008a2ab165457fd1b32df5e6bef75652f831707446931ca2517c` | 561 admitted clubs / 17,988 player rows; one blocked Volos page has duplicate shirt numbers. |
| `sources/footballsquads-2025-web-calendar.json` | `85ebf5ad2bc27c08e93c96e5c70667772242360b5974b22e7b97677b3f715294` | 172 clubs / 5,730 player rows |
| `sources/footballsquads-2025-26-web-composed-v2.json` | `8d9994566c114aceb5253f7b939535ef0ff5a31a453bac74c0b8a6a4f2bb722c` | 733 clubs / 23,718 player rows; retains the blocked Volos page. |
| `source-intake.json` | `9c857486c3cea78d8003ecbaa6c5e168a45910c46825549aa778c8ebf82273c7` | Valid raw all-carrier source intake; 3,268 rows retain explicit source gaps. |
| `source-intake-audit.json` | `2ded98b88c133f811e13aab858716b6325c91e06991642081ce8fa98190e188a` | 451 fixed carriers / 9,390 slots, all explicitly unassigned. |

`source-bundle.json` verifies both dated source conventions and the composed
assignment (`f736b8d539b8e1216760483d1f1c9411b9fb077f09fd2099085d53a9827f824d`)
before the raw intake is accepted. A 2025/26 squad-page snapshot is not
opening-XI, formation, transfer-date, or runtime evidence.

The earlier raw-intake receipts remain preserved under
`*-before-blocked-source-preservation.json`; v2 is the active output because
it keeps the Volos source failure visible.

## Superseded CC0-cache availability receipt

[`sources/footballsquads-2025-26-availability.json`](sources/footballsquads-2025-26-availability.json)
is the first-party availability receipt.  It records an attempted canonical
capture from the pinned CC0-1.0 `footballcsv/cache.footballsquads` corpus:

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2025-2026 \
  --output seasons/2025-26/sources/footballsquads-2025-26.json
```

At source revision and remote HEAD
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555`, the selected dated-file set is
empty (listing SHA-256
`01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b`).  The
capture correctly exits with status 1: `no usable current-squad source files
matched the requested season`.

This is a historical source-availability receipt, **not** a zero-club
canonical capture. It remains useful as proof of the cache boundary but is no
longer the active source input. The credited web snapshot supplies a dated
Stoke squad page, not opening-eleven, formation, or runtime evidence.

## Fixed-carrier baseline

| File | SHA-256 | State |
| --- | --- | --- |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | 451 immutable foreign carriers / 9,390 player slots from the verified base. |
| `fixed-carrier-ledger.json` | `333a648b5645d44239ecb64a2631da74c074dd717ca70436ead11cb66f8b5b0f` | Empty, structurally valid 2025/26 ledger. |
| `fixed-carrier-intake-audit.json` | `4e1dd84bf1b588bcf9c48fb3194f1d21fe3f7efc11f2063edb5a3646e3c53921` | Release-blocking audit. |

The carrier registry is locked to verified base
`pm99-gog-en-1998-clean`, inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.  It is
a binary capacity/layout constraint only; it does not identify 2025/26 clubs,
countries, divisions, draw pools, or competition membership.  The audit
correctly records all 451 carriers as unassigned, no complete player slots,
no kit or portrait decisions, and the 36 shared baseline player carriers.  Its
release blockers are `world-content-incomplete` and
`baseline-shared-player-carriers`.

## Calendar capability receipt

The verified base `MANAGPRE.EXE` hash
`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158` was
patched locally to target 2025 with 2026 rollover, 853 substitutions.  The
local-only output is
`.local/season-workers/2025-26/calendar/MANAGPRE.EXE`, SHA-256
`a39d8ae8d7ac33161b01d5488f7aa1cd57bb6b517ec0ddda895a58876d867fbc`; its
receipt is `.local/season-workers/2025-26/calendar/calendar-receipt.json`,
SHA-256 `5b60af1ecd95ea8c505e4a8d5a5ba08d4601099e9df34c2fa741a439689d2027`.
This proves only a fingerprinted calendar transform.  It is not a database
build or runtime qualification.

## Validation and reproduction

```bash
python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2025-26/fixed-carrier-registry.json \
  --ledger seasons/2025-26/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2025-26/fixed-carrier-registry.json \
  --ledger seasons/2025-26/fixed-carrier-ledger.json \
  --output seasons/2025-26/fixed-carrier-intake-audit.json

python3 scripts/capture_footballsquads_web_season.py verify \
  --snapshot seasons/2025-26/sources/footballsquads-web-snapshot.json \
  --cache-root .local/external-sources/footballsquads-web/2025-26-r1 \
  --catalog 2025-2026 \
  --capture seasons/2025-26/sources/footballsquads-2025-26-web-split.json

python3 scripts/capture_footballsquads_web_season.py verify \
  --snapshot seasons/2025-26/sources/footballsquads-web-snapshot.json \
  --cache-root .local/external-sources/footballsquads-web/2025-26-r1 \
  --catalog 2025 \
  --capture seasons/2025-26/sources/footballsquads-2025-web-calendar.json

python3 scripts/season_source_bundle_v1.py verify \
  --bundle seasons/2025-26/source-bundle.json

python3 scripts/season_source_intake_batch_v1.py \
  --seasons-root seasons --season 2025-26
```

Structural ledger validation passes.  The audit intentionally fails the
world-release gate, and must continue to do so until every assigned carrier
has complete, source-backed content.

## Required work before delivery

1. Reconcile every declared club, manager, and player to stable IDs, including
   all opening-state facts, without treating the carrier inventory as
   historical topology evidence.
2. Complete every fixed-carrier assignment and shared-carrier resolution;
   attach dated ratings, kits, portraits/native-no-photo decisions, and
   formation/lineup provenance.
3. Produce a strict `pm99-season-package-v2`, make two independent clean
   matching builds, validate their inventories, and qualify the exact release
   at runtime.
4. Only then capture and attest a real Stoke City lineup screenshot from that
   finished runtime inventory.
