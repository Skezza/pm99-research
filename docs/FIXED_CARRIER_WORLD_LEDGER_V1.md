# PM99 Fixed-Carrier World Package Guard V1

> **Status:** this is the low-level package/EQ audit guard. It is not the
> per-season authoring format. New world historical data is authored in
> [World fixed-carrier content ledger V2](WORLD_FIXED_CARRIER_LEDGER_V2.md),
> which has one baseline registry and one source ledger per season. Use this
> V1 guard only after that source has been derived into a V2 season package,
> to prove the compiler did not alter EQ topology or an unassigned carrier.

The world package may update historical content in an existing foreign PM99
carrier. It may **not** write league membership, country, division, domestic
competition size or continental draw membership. The research result is
preserve-only: those relationships have not been located and runtime-proven as
a persistent database field.

`pm99-fixed-carrier-world-ledger-v1` makes the final package/EQ boundary
executable. It is a canonical audit sidecar for a V2 season package, not a
second source ledger, database format or editor feature. It binds every
derived package club to one immutable existing `EQ98030.FDI` record and records
the evidence for that output audit.

## What the ledger locks

Each ledger contains:

- The SHA-256 of the canonical season package it describes.
- The SHA-256, record count, and ordered `(ordinal, record_id, key)` identity
  of the exact base `EQ98030.FDI` file. Payload offsets and lengths are not
  locked because variable-length content rebuilds can legitimately move them.
- One source-evidenced assignment for **every** package club. Its `carrier_id`
  must equal the package club's `carrier_id`, and its `carrier_ordinal` must
  equal the ordinal of that ID in the locked base EQ directory.
- A source record with a content hash and one or more linked V2 source IDs.
  A URL alone never counts as provenance.
- A mandatory fail-open portrait policy: a missing/unsafe portrait becomes
  PM99's native no-photo state and is listed in the review queue.

The schema intentionally has no `country`, `division`, `league`, `membership`
or `draw` property. Adding one would make the ledger look like it controls a
relationship the research has not proven.

## Workflow

1. Start from the exact base game copy for a world build. Inspect its EQ file:

   ```bash
   python3 scripts/fixed_carrier_world_ledger_v1.py inspect-base-eq \
     --eq /path/to/base/DBDAT/EQ98030.FDI
   ```

2. Write a canonical ledger alongside the canonical `pm99-season-package-v2`
   package. Set its `package_sha256` to the hash of the package's canonical
   bytes, paste the inspected topology lock values, then assign every club to
   its existing EQ record and ordinal.

3. Before compiling, validate both content and topology binding:

   ```bash
   python3 scripts/fixed_carrier_world_ledger_v1.py validate \
     --ledger world-2015-16.carriers.json \
     --package world-2015-16.package.json \
     --base-eq /path/to/base/DBDAT/EQ98030.FDI \
     --report world-2015-16.carriers.validation.json
   ```

   The package must declare `scope.competition_policy` as
   `existing-carriers-only`. A package that claims a membership writer is
   rejected here.

4. After a compiler produces EQ output, prove it neither changed EQ topology
   nor modified a carrier absent from the ledger:

   ```bash
   python3 scripts/fixed_carrier_world_ledger_v1.py audit-eq \
     --ledger world-2015-16.carriers.json \
     --package world-2015-16.package.json \
     --base-eq /path/to/base/DBDAT/EQ98030.FDI \
     --output-eq /path/to/release/DBDAT/EQ98030.FDI \
     --report world-2015-16.carriers.audit.json
   ```

   This allows variable-length payload movement, but rejects an EQ record ID,
   key, order or count change. It also rejects decoded payload changes in an
   unassigned EQ record. It does not attempt to interpret unproven structural
   bytes.

## Portrait review is fail-open

The validation report includes every `native-no-photo` and `unresolved`
portrait declaration with player name, PM99 carrier ID, club, status and
reason. These records are release-visible but non-blocking:

- `applied`: a supplied historic portrait met the source/crop/conversion
  contract.
- `native-no-photo`: deliberately remove any inherited carrier image.
- `unresolved`: also remove any inherited image, leave the native no-photo
  state, and retain the exact player in the next editorial review queue.

No random placeholder, inherited 1999 face, or failed download may become a
portrait. An editor/reviewer fixes one later by adding the approved source and
crop to the season package or editorial overlay, then rebuilding a fresh
release. They do not patch a distributed output folder.

## Limits

This does not establish a world 2015 data set or prove a foreign club has
entered a different PM99 domestic league. It gives the compiler a safe,
auditable way to populate the finite carrier topology that PM99 already has.
If a season needs a different country slot count, a carrier add/remove, or
different draw candidates, that season is blocked for this release path and
requires separate executable/topology research.

The decision and runner/Ghidra evidence behind this guard are recorded in
[PM99 foreign topology writer closeout](HISTORY/Investigations/PM99_FOREIGN_TOPOLOGY_WRITER_CLOSEOUT_2026-08-30.md).
