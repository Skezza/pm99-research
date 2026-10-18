# 2020/21 world-season intake

**Status: intake only — not a delivered database.**

This directory records the evidence gathered for the 2020/21 all-country
world-season workstream.  It deliberately does not contain a season package,
PM99 output tree, release manifest, runtime attestation, or screenshot.  None
of those can be truthfully produced until the complete world ledger has
source-backed historical decisions.

## Captured source facts

`sources/footballsquads-2020-21.json` is canonical JSON with SHA-256
`5d723b5855a2822273d5d999afd0786046bd79dcab7e0c36b751b4f43ba078b3`.
It captures 542 dated squad-source club entries, containing 16,740 player
rows, from 21 FootballSquads country catalogues and 31 competition catalogues.
The source is `footballcsv/cache.footballsquads`, CC0-1.0, revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555`.

All 542 source files were parsed; there are no blocked source files.  The
capture retains the source-file SHA-256 for each club.  It records 1,124 player
rows with at least one unresolved source fact: birth date (132), height (999),
shirt number (24), or weight (1,100).  Those counts overlap by player row.
They are editorial queues, not values to infer.

The dated Stoke City source is
`eng/2020-2021/flcham/stoke.txt`, SHA-256
`b7332050efda25a05fe8632fe461623a12d94bfc9ce9e072d6b1e20e6a49e99d`.
It has 38 captured squad rows.  This is source evidence for later lineup
review, not a runtime lineup screenshot.

## Fixed-carrier boundary

The immutable-base carrier registry is
`fixed-carrier-registry.json`, SHA-256
`19c921ad64a6694f33087a96ebff30553b7ff5906de35fc72b3d973e17e6e19b`.
It declares 451 foreign fixed carriers.  The season ledger is
`fixed-carrier-ledger.json`, SHA-256
`339640ab7b1dd2cca702d494cf52dcfc8442aca3053a09bd9fae47f395ecf248`;
the corresponding audit is `fixed-carrier-intake-audit.json`, SHA-256
`b2da1cbface643e21f3d781de44b36ed377e7fc1ab70e634563cf028a92f2e45`.

The audit is intentionally blocking: all 451 carriers are unassigned, no
player slots are complete, and no kit or portrait decision has been made.  The
baseline also has 36 shared player-carrier identities requiring a single
consistent assignment or an explicit unresolved blocker.  The registry is a
binary capacity/layout constraint only; it is not evidence for 2020/21 club,
country, competition, or membership identity.

## Candidate-only foreign identity leads

The separate base assignment remains empty: its SHA-256 is
`bfe21408dd6d709a0e016b14324e8d1dedc6fbc90c7641fbe60b784ada9a8b8b`.
It is locked to the registry and the dated squad capture.  From its six
reviewed Spanish host-country facts, the queue contains five single,
capacity-compatible name-token leads and one explicit no-lead row.

The coordinator created these deterministic editorial artefacts:

| File | SHA-256 | Role |
| --- | --- | --- |
| `foreign-carrier-candidate-proposal.json` | `4ff490bd2690e95688724bca9f9495967e408e60caf0c217966e90fb715eb6f2` | Candidate-only overlay. |
| `foreign-carrier-assignment-candidates.json` | `d91f197f4003bb7ad52b6f83f4fd13ff16c7798c8c61f7b7c59a5671d87d71d0` | Separate derived assignment ledger. |
| `foreign-carrier-assignment-candidates-audit.json` | `034b0b58a2d562221b250843fccded491356f03abcf04884027c32cb1ab49f55` | Derived-ledger coverage audit. |

The candidate rows are carrier 1 → Barcelona, 3 → Zaragoza, 4 → Real Madrid,
5 → Athletic Bilbao, and 7 → Valencia.  Every row has status `candidate` and
the same three blockers: editorial approval of the name-token link,
independent club-identity review, and the complete club/player/manager/kit/
portrait/runtime transaction.  No candidate is approved and no PM99 content
was written.

Carrier 2 has the queue state `no-name-token-candidate`; it is deliberately
absent from both the proposal and derived ledger, and therefore remains
unassigned.  The candidate audit reports five candidate assignments and 446
unassigned carriers.  This does not modify the independent fixed-carrier
intake ledger, whose 451 carriers remain unassigned until complete historical
world content is reviewed.

## Reproducibility checks

The local verified base `pm99-gog-en-1998-clean` passed inventory verification
with fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The calendar profile accepts this base for 2020/21.  Its local-only output is
`.local/season-workers/2020-21/calendar/MANAGPRE.EXE`, SHA-256
`bbfa0d1b70e559da1ddc823324c07e38e73409ab3950c4b7c511a2e5928cf927`,
with 853 verified patches and target rollover year 2021.  This proves only
the calendar executable transformation; it is not a database build or runtime
qualification.

Recreate the recorded inputs with:

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2020-2021 \
  --output seasons/2020-21/sources/footballsquads-2020-21.json
python3 scripts/world_fixed_carrier_ledger_v2.py init-registry \
  --dbdat .local/season-pipeline-v2/pm99-base-clean/DBDAT \
  --registry-id pm99-2020-21-fixed-carriers \
  --output seasons/2020-21/fixed-carrier-registry.json
python3 scripts/world_fixed_carrier_ledger_v2.py init-ledger \
  --registry seasons/2020-21/fixed-carrier-registry.json \
  --ledger-id pm99-2020-21-fixed-carrier-ledger --start-year 2020 \
  --output seasons/2020-21/fixed-carrier-ledger.json
python3 scripts/world_fixed_carrier_ledger_v2.py audit \
  --registry seasons/2020-21/fixed-carrier-registry.json \
  --ledger seasons/2020-21/fixed-carrier-ledger.json \
  --output seasons/2020-21/fixed-carrier-intake-audit.json
python3 scripts/season_candidate_identity_milestone_v1.py \
  --season-dir seasons/2020-21
python3 scripts/foreign_carrier_candidate_proposal_v1.py \
  --registry seasons/2020-21/fixed-carrier-registry.json \
  --source-capture seasons/2020-21/sources/footballsquads-2020-21.json \
  --assignment seasons/2020-21/foreign-carrier-assignment.json \
  --queue seasons/2020-21/foreign-carrier-candidate-queue.json \
  --proposal seasons/2020-21/foreign-carrier-candidate-proposal.json
python3 scripts/foreign_carrier_assignment_v1.py \
  --registry seasons/2020-21/fixed-carrier-registry.json \
  --source-capture seasons/2020-21/sources/footballsquads-2020-21.json \
  --assignment seasons/2020-21/foreign-carrier-assignment-candidates.json \
  --output .local/season-workers/2020-21/candidate-assignment-audit-validated.json
```

## Required work before delivery

Reconcile every in-scope club, manager and player to stable identities; map
them to valid non-conflicting fixed carriers; fill or explicitly resolve every
fact; and collect source-backed ratings, kits, portraits/no-photo decisions,
and opening-state evidence.  Only then can a strict package be validated and
built twice from the verified base.  A Stoke City lineup screenshot is required
only from that completed, inventory-bound runtime build.  **No such screenshot
exists for this intake, and none is claimed.**
