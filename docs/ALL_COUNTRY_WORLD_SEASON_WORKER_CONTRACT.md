# All-country PM99 season worker contract

This contract governs the world-season programme for **2000/01 through
2025/26**.  It does not lower the release gate used for the 1999/00 intake.
"Perfect historical accuracy" is an evidence standard: a worker may claim only
facts it can trace to dated, identity-safe sources.  Missing proof is a
blocker, never a reason to copy a later season or infer a value.

## Ownership and boundaries

- One worker owns exactly one `seasons/YYYY-YY/` directory and a dedicated
  local build directory under `.local/`.
- The verified clean PM99 base is read-only.  It may never be used as a shared
  output tree.
- Workers may not change shared scripts, schemas, upstream repositories, or
  another season's directory.  A tooling defect is reported to the coordinator
  with a minimal reproducer.
- PM99 binaries, generated game folders, screenshots, and private source
  material stay local unless they are explicitly approved and safe to track.

## Required content evidence

A world season must retain canonical source receipts for every in-scope club,
manager, player, kit, and portrait decision.  Player and manager identities
need stable reconciled IDs; each player fact, rating, and opening-lineup claim
needs its declared provenance.

The fixed-carrier registry is a capacity and binary-layout contract only.  It
is not historical evidence of club identity, country, division, draw pool, or
competition membership.  Existing carrier topology must remain unchanged
unless a separately proven writer and release contract explicitly allow a
change.  Shared player carriers need a single consistent identity or an
explicit unresolved blocker.

Missing portraits resolve only to a documented native-no-photo state.  They
must never retain an unrelated baseline face.

## Worker deliverables

Each worker returns:

1. Canonical, hash-verified source capture(s), club/person reconciliation, and
   a complete fixed-carrier ledger/audit for its season.
2. A strict `pm99-season-package-v2` package with source-backed managers,
   ratings, kits, portraits/no-photo decisions, and opening evidence.
3. Two independently clean, byte-identical builds from the verified base,
   with static validation receipts and release hashes.
4. Runtime qualification tied to the finished inventory.  If Stoke City is in
   the released playable scope, capture a runtime lineup screenshot and store
   its safe local path and SHA-256 in that season's attestation.
5. A concise handover naming files, hashes, test commands, source coverage,
   unresolved items, and any blockers.

## Delivery rule

Only a season with zero blocking gaps in the declared world scope, matching
clean builds, and runtime proof is a delivered database.  An intake, partial
ledger, static package, or a screenshot from an unverified build is useful
research but is explicitly **not delivered**.
