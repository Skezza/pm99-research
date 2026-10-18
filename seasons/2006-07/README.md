# PM99 2006/07 candidate identity milestone

Status: **candidate-only editorial proposal; not an approved assignment,
database build, or release.**  This milestone adds deterministic identity leads
to a separate derived ledger.  It does not alter the base assignment, the
fixed-carrier ledger, PM99 binaries, or foreign competition topology.

| File | SHA-256 | Status |
| --- | --- | --- |
| `sources/footballsquads-2006-07.json` | `0e0324156a57763e4196b702d6b12ebcaa5c64c200a37079a0ed3b4a26cab566` | Dated CC0 squad capture. |
| `foreign-carrier-candidate-proposal.json` | `cf807e3051b8edb17beb7b7620b749170281a9b37c436e95a5f7631399da025a` | Five unapproved, capacity-compatible leads. |
| `foreign-carrier-assignment-candidates.json` | `46d504564052380b52170df52749203ef5ad8d6ae46fbbff629bdf083eb054dd` | Separate candidate ledger; base assignment remains unchanged. |
| `foreign-carrier-assignment-candidates-audit.json` | `15b2b5310a2cad6187a35ed7b54222695b6d28e69cff7ccba589cf26b0c11bf3` | Five candidate identities and 446 unassigned carriers. |

The dated source is pinned to `footballcsv/cache.footballsquads` revision
`187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555`.  The five eligible leads are
carrier IDs 1 Barcelona, 2 Deportivo La Coruña, 3 Zaragoza, 5 Athletic Bilbao,
and 7 Valencia.  Each remains `candidate` with required independent identity
review and complete club/player/manager/kit/portrait/runtime evidence.

Carrier 4 is deliberately absent.  Its baseline name is Real Madrid C.F.,
but the dated capture has two capacity-compatible name-token matches: Real
Madrid (La Liga) and Real Madrid Castilla (Segunda).  This ambiguity is
unresolved; neither source row has been selected or approved.

The candidate audit retains 451 fixed foreign carriers in scope: 5 candidate
identities and 446 unassigned.  It is an editorial queue, not an authority to
write a database or claim historical completeness.

Reproduce and validate the deterministic milestone:

```bash
python3 scripts/season_candidate_identity_milestone_v1.py \
  --season-dir seasons/2006-07 --replace

PYTHONPATH=. /home/joe/ductor/.venv/bin/pytest -q \
  scripts/test_foreign_carrier_assignment_v1.py \
  scripts/test_foreign_carrier_candidate_queue_v1.py \
  scripts/test_foreign_carrier_candidate_proposal_v1.py
```
