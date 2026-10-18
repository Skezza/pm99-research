# 2021/22 world-season intake

## Status

**Blocked intake; not a delivered PM99 database.**  This directory records
the reproducible 2021/22 source and fixed-carrier starting point.  It includes
five unapproved, candidate-only carrier identity leads, but contains no season
package, compiled game tree, release inventory, runtime attestation, or Stoke
City screenshot.

The release gate has not been relaxed: every historical claim must have a
dated, identity-safe source, and the fixed PM99 carrier topology must remain
unchanged.  In particular, the carrier registry is a binary capacity record,
not evidence that a carrier represents a historical club, country, division,
or competition.

## Captured source scope

`sources/footballsquads-2021-22.json`

- SHA-256: `ba5d6cfc81a588e4d4eb5b71af6955e32a2369f5c768db0d7080ecfe526b8005`
- Schema: `pm99-footballsquads-season-capture-v1`
- Source: `footballcsv/cache.footballsquads`, revision
  `187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555`, CC0-1.0.
- 555 dated club source files, 17,112 captured player rows, 21 country
  catalogs and 32 competition catalogs.
- Each captured club retains its cache-relative source path and SHA-256;
  no source fact is accepted merely by club-name matching.

The capture preserves only source-provided squad facts: name, shirt number,
coarse position, nationality where provided, birth date, height and weight.
It is not a person reconciliation and contains no manager, rating, kit,
portrait/no-photo, opening-lineup, carrier-assignment, or PM99 write claim.

The capture reports 1,783 player rows with at least one unresolved source
fact: 211 birth dates, 1,633 heights, 1,755 weights, and 28 shirt numbers
(a row can have more than one gap).  Those gaps remain blockers until
independently sourced and reconciled.

### Stoke City source state

The dated Stoke squad source is
`eng/2021-2022/flcham/stoke.txt`, SHA-256
`7de1ed5f49276bf49b070fadd8976967e052918c852136048bd7abdeda600cb5`.
It identifies Stoke City in the English Football League Championship and
contains 35 squad rows.  Two rows lack both source height and weight.  This
is source evidence only: it does not establish an opening XI, formation,
player-to-PM99-carrier mapping, or a runtime lineup.

## Fixed-carrier baseline and audit

`fixed-carrier-registry.json`

- SHA-256: `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375`
- Schema: `pm99-world-fixed-carrier-registry-v2`
- 451 existing foreign mode-1 carrier slots from the verified clean base.
- Baseline database hashes: `JUG98030.FDI`
  `95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`,
  `EQ98030.FDI`
  `e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`,
  and `ENT98030.FDI`
  `729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`.

`fixed-carrier-ledger.json`

- SHA-256: `e0bc7a5abf8aa58de7380f6a58f6633f44aa6b6d95537e13db948cb4fa1168be`
- Schema: `pm99-world-fixed-carrier-ledger-v2`
- Season: 2021/22; topology policy:
  `preserve-existing-carriers-no-membership-write`.
- Zero carrier updates.  This is intentional: no historical club has been
  assigned to a fixed carrier without reviewed host and identity evidence.

`fixed-carrier-intake-audit.json`

- SHA-256: `a55eb19274dec6b873ef39ee1df1b14b874ff0ac651f7cf0cfc339b384ce0f32`
- Schema: `pm99-world-fixed-carrier-ledger-audit-v2`
- 451 of 451 foreign carriers unassigned; zero complete player slots, kits,
  or portrait decisions.
- Blocking conditions: `world-content-incomplete` and 36
  `baseline-shared-player-carriers` requiring a single consistent historical
  identity or an explicit unresolved decision.

## Candidate-only carrier identity milestone

The original base assignment is unchanged:

- `foreign-carrier-assignment.json`: SHA-256
  `e87cc6b56be0f9181aef678fe86124a48fd51ad31362efc7a7eae93069a9982d`.
- It remains the separate, hash-locked unassigned assignment ledger.  No
  approval, PM99 edit, carrier-topology change, or shared-carrier decision
  has been made.

The candidate-only coordinator materialised three additional canonical files:

| File | SHA-256 | Meaning |
| --- | --- | --- |
| `foreign-carrier-candidate-proposal.json` | `b4faad2a922fbb98bb010a21465f1436e1a747617cc5ee6d2d8fddadb89b9f8a` | Five deterministic `candidate` proposals from single capacity-compatible source-name leads. |
| `foreign-carrier-assignment-candidates.json` | `740050f2ed7fc11ee9a4f744ff16018c0692065916a9108d8417596cadf6b89a` | Separate derived assignment ledger: five candidates and 446 unassigned carriers. |
| `foreign-carrier-assignment-candidates-audit.json` | `266df720a4ca1febebf8224ac454e937e57aa86127ccc65a6ef3551eaf26d6f2` | Audit of the separate candidate ledger. |

The five leads are carrier 1 → Barcelona, 3 → Zaragoza, 4 → Real Madrid,
5 → Athletic Bilbao, and 7 → Valencia.  Their only evidence is reviewed host
country plus dated source-name-token and capacity compatibility; all retain
the blockers for independent identity approval and complete club/player/
manager/kit/portrait/runtime work.  The source competition catalogs are
provenance only and make no PM99 membership, draw-pool, or division claim.

Carrier 2 (`R.C. Deportivo`) is `no-name-token-candidate` in the canonical
queue.  Its absent source lead means it is deliberately omitted from the
proposal and derived ledger; it remains unassigned.  This is not an identity
decision about Deportivo and must not be filled by inference.

## Reproduce and verify

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2021-2022 \
  --output seasons/2021-22/sources/footballsquads-2021-22.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-base-clean-fixed-carriers \
  --output seasons/2021-22/fixed-carrier-registry.json

python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2021-22/fixed-carrier-registry.json \
  --ledger-id pm99-2021-22-fixed-carrier-intake \
  --start-year 2021 \
  --output seasons/2021-22/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2021-22/fixed-carrier-registry.json \
  --ledger seasons/2021-22/fixed-carrier-ledger.json

python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2021-22/fixed-carrier-registry.json \
  --ledger seasons/2021-22/fixed-carrier-ledger.json \
  --output seasons/2021-22/fixed-carrier-intake-audit.json

python3 scripts/season_candidate_identity_milestone_v1.py \
  --season-dir seasons/2021-22

python3 scripts/foreign_carrier_candidate_proposal_v1.py \
  --registry seasons/2021-22/fixed-carrier-registry.json \
  --source-capture seasons/2021-22/sources/footballsquads-2021-22.json \
  --assignment seasons/2021-22/foreign-carrier-assignment.json \
  --queue seasons/2021-22/foreign-carrier-candidate-queue.json \
  --proposal seasons/2021-22/foreign-carrier-candidate-proposal.json
```

The following checks passed against this intake:

```bash
PYTHONPATH=. /home/joe/ductor/.venv/bin/pytest -q \
  scripts/test_capture_footballsquads_season.py \
  scripts/test_world_fixed_carrier_ledger_v2.py
python3 scripts/world_fixed_carrier_ledger_v2.py validate \
  --registry seasons/2021-22/fixed-carrier-registry.json \
  --ledger seasons/2021-22/fixed-carrier-ledger.json
python3 scripts/check_repo_boundary.py
```

The focused test lane reported 14 passed.  Structural ledger validation and
the repository-boundary check also passed.  These checks do not waive the
content, build, or runtime gates listed below.

The coordinator's proposal, derived assignment, and audit were also
recomputed from their canonical inputs.  The recomputation passed, confirmed
that every proposal status is `candidate`, and confirmed that carrier 2 is
not present in the proposal.

## Required work before delivery

1. Reconcile every in-scope club, manager, and player to stable identities,
   and fill every source gap with dated provenance.
2. Review host-carrier assignments without using the source competition
   catalogs to infer PM99 topology; resolve all shared JUG carriers.
3. Provide sourced ratings, kits, portraits or native-no-photo decisions, and
   opening formation/lineup evidence for every released club.
4. Build a strict `pm99-season-package-v2`, compile it twice from clean,
   verified bases, validate matching inventories and release hashes, and
   qualify the exact release at runtime.
5. Only then capture and attest a runtime Stoke City lineup screenshot.  No
   screenshot exists for this intake because no verified 2021/22 game tree
   exists.
