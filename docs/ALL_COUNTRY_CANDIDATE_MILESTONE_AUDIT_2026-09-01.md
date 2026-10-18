# All-country candidate milestone audit — 2026-09-01

## Outcome

All 26 original season workstreams have now completed their current bounded
milestone.  This is a **candidate-identity programme**, not a programme of 26
historical PM99 database releases.

| Outcome | Seasons | Result |
| --- | --- | --- |
| Candidate-only identity milestone | 2000/01–2003/04, 2005/06–2007/08, 2009/10–2013/14, 2016/17–2023/24 | 20 derived ledgers with 106 total unapproved candidate links. |
| Bound-source candidate block | 2004/05, 2008/09, 2014/15 | Three assignment ledgers and queues validate, but their hash-bound source receipts have no Spanish name lead.  No proposal was created. |
| Separate release revalidation | 2015/16 | Existing reproducible legacy engineering release revalidated; it is not a current complete all-country historical release. |
| Attributed raw source intake | 2024/25, 2025/26 | The CC0-cache availability receipts remain historical evidence; user-authorised FootballSquads web snapshots now provide composed raw intakes and empty base assignments. No candidate queue or approval is permitted. |

After this candidate-only audit, source composition was repaired for
2004/05, 2008/09, 2009/10 and 2014/15. The active raw intake for each now
uses a hash-locked composed source and a fresh, all-unassigned derived
assignment. This does not promote the historical candidate ledgers or change
their candidate-only status. See
[source-composition repair](SOURCE_COMPOSITION_REPAIR_2026-09-01.md).

The 20 candidate ledgers contain 106 rows in `status: candidate`; **zero are
approved**.  Every row retains blockers for editorial club-identity approval
and for the full club/player/manager/kit/portrait/opening-state/package/build/
runtime transaction.  The immutable 451-carrier topology is unchanged.

## Candidate coverage

| Candidate count | Seasons | Unassigned fixed carriers per season |
| ---: | --- | --- |
| 6 | 2000/01–2003/04, 2007/08, 2009/10, 2016/17, 2018/19, 2019/20 | 445 |
| 5 | 2006/07, 2010/11, 2011/12, 2017/18, 2020/21–2023/24 | 446 |
| 4 | 2005/06, 2012/13, 2013/14 | 447 |
| 0 | 2004/05, 2008/09, 2014/15 | 451 |

The lower counts are evidence, not shortfalls to fill mechanically:

- reserve source rows create Barcelona/Barcelona B and/or Real Madrid/Real
  Madrid Castilla ambiguities;
- source squads below the immutable carrier capacity remain excluded; and
- carrier 2 has no current captured lead in 2020/21–2023/24.

## Pipeline conclusion

The pipeline is not blocked on creating files.  It reliably performed the
repetitive work: source hash binding, host-evidence binding, queue creation,
candidate proposal derivation, separate-ledger creation, audit, deterministic
replay and validation.

It deliberately refuses the steps that would make history up:

1. Only six of 451 foreign carriers have independently reviewed runner
   host-country evidence.  The next fresh runner probe is still prevented by
   the retained remote-artifact budget; no evidence has been deleted.
2. A name-token candidate is not a reviewed club identity.  Human editorial
   approval must be supported by independent evidence.
3. Identity is only one release lane.  Player facts/ratings, managers, kits,
   portraits/no-photo, opening lineups, fixed shared-carrier resolution,
   package compilation, two clean builds and runtime proof remain required.
4. The PM99 world topology writer is intentionally unsupported: country,
   division, competition membership and draw pools remain preserve-only.

The orchestrator was strengthened during this milestone.  It now chooses the
one source receipt whose canonical SHA-256 is already bound by the base
assignment ledger, rather than assuming a season has only one source file.
That preserves valid calendar and split-year receipts and prevents a convenient
but incorrect source substitution.

## Validation

- 54 focused regression tests passed, including the new multiple-receipt
  selection guard.
- Every produced candidate ledger/audit reports only `candidate` status;
  no derived candidate audit has an `approved` row.
- Repository boundary and Markdown whitespace checks passed.

There are still no newly qualified all-country database releases and no Stoke
City opening-lineup screenshots.  The viewer’s review batch remains useful for
the next editorial stage, but its bulk annotations are deliberately separate
from all PM99 write paths.
