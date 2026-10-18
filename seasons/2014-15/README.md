# 2014/15 all-country world intake

## Status

**Intake only — not a package, build, runtime-qualified database, or
delivered season.** This directory records reproducible dated source facts
and the fixed-carrier authoring boundary for the 2014/15 workstream. It does
not claim that the available source cache covers every PM99 world carrier.

The delivery gate is intentionally unsatisfied. All 451 foreign fixed
carriers remain explicitly unassigned, so no historical club identity,
player, manager, kit, portrait, rating, opening lineup, country, division,
draw-pool, or competition membership has been inferred from the 1998 base.

## Source-bundle repair and reprocessed intake

[`source-bundle.json`](source-bundle.json) now preserves both source
conventions as named hash-locked inputs while producing the logical 2014/15
capture `sources/footballsquads-2014-15-composed-v2.json`
(`505775823961ec8e615ba03947d2250894d6906bfd4711bd64f157e682b38b66`) and
the newly capture-bound `foreign-carrier-assignment-composed-v2.json`
(`ecef5d7b66b10b575890e249f93bd3bcef38c4e742643d56d806c2a26aac7426`). The
reprocessed raw source intake is `source-intake.json`
(`d4883bba7d6623d0b95baee177b45edbb39009b526f9137ed558cdbe83d1b4ca`) and
its audit is `source-intake-audit.json`
(`f74af8328a01bb2d74c3a6546058d30a0c56f4b9649e315230f2730b3e45f9fb`).

This removes the prior competing-capture pipeline blocker only. The v2
composed capture retains the strictly blocked Greek source page; the prior
receipts are preserved under `*-before-blocked-source-preservation.json`. The active
composed assignment still records 451 unassigned foreign carriers; no
historical identity, candidate approval, topology change, or PM99 build was
created.

## Evidence captured

| Receipt | SHA-256 | Evidence |
| --- | --- | --- |
| `sources/footballsquads-2014-15-world.json` | `f29b11bac6c3ae0f74b98c5b7b689c4bb6f5535ce5046a1eedacc1ebae05bf4a` | 525 split-year club-squad receipts / 15,775 player rows from 20 catalog countries and 30 competition catalogs. |
| `sources/footballsquads-2014-calendar-world.json` | `0f5e5ff85926237f84ce326767bb2babc165b62e0caef2c6dc1f31a7e386ae8f` | 137 calendar-year club-squad receipts / 4,103 player rows from eight catalog countries and eight competition catalogs. |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | 451 existing mode-1 foreign carriers and 9,390 immutable roster slots, read from the verified clean base. |
| `fixed-carrier-ledger.json` | `1cf8166cad84264986433da32a68c9a7fd212db4c3fbb72817dedc225c0522bc` | Empty, registry-bound 2014/15 authoring ledger. |
| `fixed-carrier-intake-audit.json` | `c813a0b0850f1226b7e943ac70d8970241396832466d7d67193f23ad16e1782f` | Audit showing 451 unassigned carriers and zero completed slots, kits, or portraits. |

Both squad captures come from `footballcsv/cache.footballsquads`, revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555` (CC0-1.0). The source cache uses
two legitimate season conventions, which are retained as separate receipts:
European-style `2014/15` competitions and calendar-year `2014` competitions.
Combining them into a fictional common source season would lose evidence
meaning, so later identity reconciliation must declare how each competition's
opening date is handled.

The split-year capture blocks one source, exactly and visibly:
`greece/2014-2015/superl/nikivolos.txt` (SHA-256
`d180ada894dc3ef23fb6bda796991b573c4f10b2e8e5f20d7639140a6296ff96`)
contains no current-squad CSV section. It is a release blocker, not an empty
club roster. Across both admitted receipts, 488 height, 510 weight, 46 birth
date, 153 shirt-number, and one primary-position facts remain unresolved.
These require separately dated, identity-safe sources; no defaults were
applied.

The 2014/15 calendar profile was calculated from the verified base as a
local-only artifact:

- output: `.local/builds/2014-15-calendar/MANAGPRE.EXE`
- SHA-256: `f1b534807fce895c2a83585ccca7885de5cfa2f81905638a3010f3a32cedaf20`
- receipt: `.local/builds/2014-15-calendar/calendar-receipt.json`
- receipt SHA-256: `e8bd3f2622a6b71f76339c4f48bdbd8470034ceb125e1a59586c393e58a34d6b`
- 853 version-checked operands, 2014 start / 2015 rollover.

Calendar eligibility alone does not make a database build valid.

## Pre-composition foreign-carrier candidate queue: validated and blocked

The existing carrier-assignment and candidate-queue records were validated
without change. They are tied to the *calendar-year* source receipt, not the
separate split-year receipt:

| Receipt | SHA-256 | Validation state |
| --- | --- | --- |
| `foreign-carrier-assignment.json` | `e06ab4054b81d3f488473fb94366f6d8d042288d3d21530a695875b475edcfad` | Six reviewed Spain host-country facts, but zero historical-identity assignments; bound to calendar receipt `0f5e5ff85926237f84ce326767bb2babc165b62e0caef2c6dc1f31a7e386ae8f`. |
| `foreign-carrier-assignment-audit.json` | `f408ba16472d82c6179a7d7ebc7dc4fec9131e857e34fa7edec93d9bcb974824` | Fresh recomputation matches the stored audit: 451 fixed foreign carriers, zero identity assignments, and 451 unassigned. |
| `foreign-carrier-candidate-queue.json` | `81299f68f5ad21670ca4a58862352003e3967f20da85d7a35d404897e0edbe3b` | Six reviewed Spanish host carriers, all `no-name-token-candidate`, each with an empty candidate list. |

The receipt named by that assignment/queue has eight calendar-year country
catalogs (`arg`, `brazil`, `china`, `ireland`, `japan`, `norway`, `sweden`,
and `usa`): it contains no `spain` catalog and no Spanish club-name lead.
The empty candidate lists are therefore the correct result. No candidate
proposal, derived candidate assignment, PM99 output, or approval has been
created.

The split-year receipt does contain Spanish clubs. The retained historical
queue is not interchangeable with the active composed assignment and has not
been promoted or approved by source composition.

## Stoke City status

The split-year receipt includes the 28-player Stoke City Premier League squad
at `eng/2014-2015/faprem/stoke.txt` (source SHA-256
`17262bf580a575a97e40b628727f97ce176950675f81a11c84b1e7ece52f21f3`).
This is a squad receipt, **not** opening-XI or formation evidence. No Stoke
carrier has been reconciled or written, no playable 2014/15 build exists, and
there is therefore no valid Stoke lineup screenshot. A screenshot from the
1998 base or an unqualified patch would be misleading and is intentionally
absent.

## Reproduction and validation

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2014-2015 \
  --output seasons/2014-15/sources/footballsquads-2014-15-world.json
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2014 \
  --output seasons/2014-15/sources/footballsquads-2014-calendar-world.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-base-clean-fixed-carriers \
  --output seasons/2014-15/fixed-carrier-registry.json
python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2014-15/fixed-carrier-registry.json \
  --ledger-id pm99-2014-15-fixed-carrier-intake --start-year 2014 \
  --output seasons/2014-15/fixed-carrier-ledger.json
python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2014-15/fixed-carrier-registry.json \
  --ledger seasons/2014-15/fixed-carrier-ledger.json
python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2014-15/fixed-carrier-registry.json \
  --ledger seasons/2014-15/fixed-carrier-ledger.json \
  --output seasons/2014-15/fixed-carrier-intake-audit.json
```

## Remaining delivery gates

1. Reconcile every in-scope club and person to stable identifiers and source
   every missing player fact, including the blocked Greek source.
2. Complete every fixed-carrier/slot update without changing carrier topology;
   resolve the 36 shared baseline player carriers consistently or leave them
   blocked.
3. Source and review managers, ratings, kits, portrait/no-photo dispositions,
   and opening-lineup evidence for the declared world scope.
4. Create and strictly validate a `pm99-season-package-v2`; then produce two
   clean byte-identical builds and release hashes.
5. Qualify the finished inventory at runtime and capture a Stoke lineup
   screenshot only from that qualified build.
