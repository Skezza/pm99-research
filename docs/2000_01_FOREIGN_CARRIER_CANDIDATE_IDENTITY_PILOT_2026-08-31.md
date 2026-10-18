# 2000/01 foreign carrier candidate-identity pilot — 2026-08-31

## Result

The 2000/01 milestone now has a **six-row candidate-only foreign identity
bridge**.  It is an editorial-review artefact, not a database, club-content
transaction, or approved historical identity map.

It begins with six independently reviewed Spanish host-country facts from the
stock PM99 preseason picker and six single, dated, capacity-compatible source
leads in the 2000/01 FootballSquads capture.  The derived assignment retains
445 of the 451 fixed foreign carriers as unassigned.

| Carrier | PM99 baseline display | Dated source club | Status |
| ---: | --- | --- | --- |
| 1 | F.C. Barcelona | Barcelona | `candidate` |
| 2 | R.C. Deportivo | Deportivo La Coruña | `candidate` |
| 3 | R. Zaragoza | Zaragoza | `candidate` |
| 4 | Real Madrid C.F. | Real Madrid | `candidate` |
| 5 | Athletic Club | Athletic Bilbao | `candidate` |
| 7 | Valencia C.F. | Valencia | `candidate` |

The display-name relationship is useful and auditable, but remains only a
candidate because historical carrier reuse must be editorially confirmed.
The `candidate` status cannot be presented as an approved identity, and is
not usable as a release claim.

## Durable artefacts

| File | SHA-256 | Role |
| --- | --- | --- |
| `seasons/2000-01/foreign-carrier-candidate-proposal.json` | `9d1d3942e71b9efbd6bd968d7e9615e6335bb2ec7736c108aead1cb818ab3d79` | Deterministic overlay generated from the six single capacity-compatible review leads. |
| `seasons/2000-01/foreign-carrier-assignment-candidates.json` | `44354216135a8cb36315e643901992adef740abb9ba2757576e946cb99b72e59` | Separate derived ledger; the base assignment is unchanged. |
| `seasons/2000-01/foreign-carrier-assignment-candidates-audit.json` | `1051dafc5f4ea2c324213483f896cbf5733a6b74cbc24aeec9ca1667533598c9` | Reports six candidate identities and 445 unassigned carriers. |

Each candidate has three sorted blockers:

1. the name-token link is not editorially approved;
2. independent club-identity review is required; and
3. player, manager, kit, portrait/no-photo, opening-state, package, clean-build
   and runtime work remains mandatory.

The source selector preserves the precise dated FootballSquads path and file
digest.  The source's La Liga catalogue is provenance only and has not been
used as a PM99 division, country, membership, competition, or draw-pool write.

## Validation

```bash
python3 scripts/foreign_carrier_candidate_proposal_v1.py \
  --registry seasons/2000-01/fixed-carrier-registry.json \
  --source-capture seasons/2000-01/sources/footballsquads-2000-01.json \
  --assignment seasons/2000-01/foreign-carrier-assignment.json \
  --queue seasons/2000-01/foreign-carrier-candidate-queue.json \
  --proposal seasons/2000-01/foreign-carrier-candidate-proposal.json

python3 scripts/foreign_carrier_assignment_v1.py \
  --registry seasons/2000-01/fixed-carrier-registry.json \
  --source-capture seasons/2000-01/sources/footballsquads-2000-01.json \
  --assignment seasons/2000-01/foreign-carrier-assignment-candidates.json \
  --output /tmp/world-2000-01-candidate-audit.json
```

The candidate-proposal generator and its focused test coverage reject a
short-source roster, a changed queue/proposal, an attempted promotion to
`approved`, and all ambiguous or no-lead rows.

## What this does not close

This milestone does not resolve a single player identity, person fact, rating,
manager, shirt, kit, portrait, opening lineup, formation, or runtime state.
It neither builds nor runs PM99.  It has no Stoke City update or screenshot.

The next safe editorial move is to review these six candidate identities with
independent club-identity evidence.  Only then may a maintainer create a
manually reviewed `approved` proposal; that approval still unlocks only the
carrier identity layer, not a historical database release.
