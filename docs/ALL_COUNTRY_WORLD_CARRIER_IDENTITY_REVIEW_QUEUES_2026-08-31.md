# All-country fixed-carrier identity review queues — 2026-08-31

## Result

This is the next, deliberately narrow layer after the 26-season source-intake
programme.  It creates **review queues, not database edits**.

Twenty-three dated squad captures (2000/01–2023/24 excluding the already
separate 2015/16 workstream) now each have:

- `foreign-carrier-assignment.json`: an empty, hash-locked assignment ledger
  with six reviewed PM99 host-country facts; and
- `foreign-carrier-candidate-queue.json`: deterministic candidate-only leads
  derived from those facts and the dated squad capture.

Every assignment ledger still has **451 unassigned carriers** and makes no
club, player, manager, kit, portrait, league, membership, or draw-pool write.
No historical club has been approved automatically.

## Reusable evidence

Six fixed carriers have independently reviewed, one-fresh-route preseason
picker evidence that their existing PM99 host country is Spain:

| Carrier ID | Baseline visible name |
| ---: | --- |
| 1 | F.C. Barcelona |
| 2 | R.C. Deportivo |
| 3 | R. Zaragoza |
| 4 | Real Madrid C.F. |
| 5 | Athletic Club |
| 7 | Valencia C.F. |

The evidence is bound to the clean-base `EQ98030.FDI` hash and retained in
the hash locks embedded in every assignment ledger.  The six reviewed local
reports are `foreign-host-spain-20260830-report.json` plus the five
one-tile `foreign-host-spain-tile-*.json` reports under
`.local/season-pipeline-v2/`.  They remain local runner evidence; no
proprietary PM99 content is tracked.

`scripts/foreign_carrier_candidate_queue_v1.py` then makes a lead only when
all meaningful normalised tokens from the baseline display name occur in a
dated source-club display name from that reviewed host country.  Thus
`F.C. Barcelona` → `Barcelona`, and `Athletic Club` → `Athletic Bilbao`, are
review leads rather than silently approved carrier identities.  Source
competition catalogues remain provenance only.

## Queue inventory

There are 138 host-carrier review rows: 107 single name-token leads, nine
ambiguous rows (18 candidate source clubs), and 22 rows with no lead.  The
125 candidate source clubs are all explicitly non-authoritative.  A reviewer
must make the identity decision and record its historic evidence before a
proposal can be applied.

| Season | Candidate source clubs | Single | Multiple | None | Queue SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| 2000/01 | 6 | 6 | 0 | 0 | `73b1becb59f7d7c4ad05c64c910fd04ab94febd4271d188e9488b22fce82a780` |
| 2001/02 | 6 | 6 | 0 | 0 | `2729b2d1faa04291da1258e0a1fe75f7ae12831b719462f6c6263b758fe413ed` |
| 2002/03 | 6 | 6 | 0 | 0 | `ac621cd8d02676b132f0ad098bd4585a206be1454a1064a0f71f97248b74534a` |
| 2003/04 | 6 | 6 | 0 | 0 | `02408fc3114dd86cd32276347369873b0ab985a281016a847e7338c9f23be373` |
| 2004/05 | 0 | 0 | 0 | 6 | `6bc95aaa692dae14f0bbeb8cd529e3e3f7798affdfd26b9ac816ec381690e79f` |
| 2005/06 | 7 | 5 | 1 | 0 | `864e2f5c31edfcc99af2e1657b8ad7a07c87a79439539a91c760789e81e1586f` |
| 2006/07 | 7 | 5 | 1 | 0 | `d6e469f6d2ec1734020c56ab604d02f2ac4d85797de644c897f572a312a5be4f` |
| 2007/08 | 6 | 6 | 0 | 0 | `2a13feeca0bbe7db07f7ef6ca7edae79adfa33b369e627c0645e192a1213c2f8` |
| 2008/09 | 0 | 0 | 0 | 6 | `4ad81cc5d9aef3e0a63d7256c809f2bfee26ea1f2417f0531d1646cb00c3d8ee` |
| 2009/10 | 6 | 6 | 0 | 0 | `bbe585bd23ac51060bd14d2d88529ee99887090b0bb4c916a218058aac6a2015` |
| 2010/11 | 7 | 5 | 1 | 0 | `c3459d54d2c67eba1b4074d150a243c67820ca2a02ee9b972324227c92b30cbd` |
| 2011/12 | 7 | 5 | 1 | 0 | `14863cb38cc0ab721b643f619b25e21b6e982534fa5c2fd49af7d18ec4d71d6c` |
| 2012/13 | 8 | 4 | 2 | 0 | `9229392bde7560df9f7055b3e7eb1cc3e2bb496837edfc3da719ddb37889f94d` |
| 2013/14 | 8 | 4 | 2 | 0 | `44c552d5ced351a429f477ed4a4bb0a31dd8b6b7be4b0d9619b5543b5e93dcd5` |
| 2014/15 | 0 | 0 | 0 | 6 | `81299f68f5ad21670ca4a58862352003e3967f20da85d7a35d404897e0edbe3b` |
| 2016/17 | 6 | 6 | 0 | 0 | `f2b0f6795096539607579929ad2f031b3b352dd142c416b669cc21ddf9a0ab2f` |
| 2017/18 | 7 | 5 | 1 | 0 | `f5e706bbb42b840cae15e827661116279cc6f5cc387aedb81566f896d19b7146` |
| 2018/19 | 6 | 6 | 0 | 0 | `60e47658bd4a3570681a0a2d5ff83e31bbdc2668352363fa439b92b46174bd23` |
| 2019/20 | 6 | 6 | 0 | 0 | `79245d40328fbcc28bb0d6bd399f53dcb2a8e8fa24ef3fb7b5c4a40f46a061af` |
| 2020/21 | 5 | 5 | 0 | 1 | `05f6fc02d35a54be7bdff66220709cb0b569d4ac0bf5bbabd053d6f61e853389` |
| 2021/22 | 5 | 5 | 0 | 1 | `be69cd2b240bc1db45295bb8aa936a0b3e5c5cb8fdb1a715a18b747a3dafbce4` |
| 2022/23 | 5 | 5 | 0 | 1 | `41bc919fd26fc91fde8d2c4109693cc72ff33b6674ad0772a0b53ac14b5112f1` |
| 2023/24 | 5 | 5 | 0 | 1 | `a5a9a83b955e5eb73f2fbbcef47f8ae87d57989fe57ea07952abf791e2cacd4a` |

The nine ambiguity rows are deliberate.  They distinguish the first team from
similarly named reserve source rows: Barcelona/Barcelona B (2010/11, 2011/12,
2012/13, 2013/14 and 2017/18) and Real Madrid/Real Madrid Castilla (2005/06,
2006/07, 2012/13 and 2013/14).  They must not be bulk-approved.

The 2004/05, 2008/09 and 2014/15 captures contain no Spanish catalogue at
all.  In 2020/21–2023/24, carrier 2 has no matching source-name lead; that is
an explicit absence in the captured catalogue, not a claim that Deportivo had
no historical squad.

## Excluded workstreams

- **2015/16:** remains governed by the existing reproducible release and
  separately documented world editorial queues; this new preparatory work
  does not reclassify it as a complete all-country release.
- **2024/25 and 2025/26:** now have attributed, hash-bound FootballSquads web
  source snapshots and empty base assignments. An identity queue would still
  be fabricated without independent carrier-identity evidence, so none was
  created.

## Review and authoring procedure

Load any or all `foreign-carrier-candidate-queue.json` files in the private
PM99 Manifest Desk.  It exposes each carrier as a filterable, bulk-annotatable
row, including its host country, alternative source leads, capacity status and
blockers.  Its exported review patch is a human annotation only; it does not
mutate a binary, manifest or carrier assignment.

For a one-file programme review, load
`seasons/all-country-foreign-carrier-candidate-review-batch-2000-2024.json`
(SHA-256 `9380aa4cea578a6ba55c533291d31d10c7c02cbea1ebdb46605e8ec1d688b212`).
It embeds the 23 canonical queues verbatim with each original queue hash; the
desk recognises this batch format and retains the individual season and source
labels in its rows.

For every proposed identity, the maintainer must then:

1. inspect the lead and its contemporaneous club-identity evidence;
2. author a reviewed `pm99-foreign-carrier-assignment-proposal-v1` row with
   the exact source selector and explicit status;
3. derive and validate the assignment ledger; and
4. complete the separate player, manager, rating, kit, portrait/no-photo,
   opening-lineup, package, clean-build and runtime gates.

An `approved` carrier assignment is still only a host-country-compatible
identity decision.  It is never, by itself, a historical PM99 database or a
license to create a Stoke City lineup screenshot.

## Reproduce and validate

For a captured season, first initialise and audit the empty assignment ledger
with the six reviewed host reports, then generate and validate the queue:

```bash
python3 scripts/foreign_carrier_assignment_v1.py \
  --registry seasons/2000-01/fixed-carrier-registry.json \
  --source-capture seasons/2000-01/sources/footballsquads-2000-01.json \
  --host-report .local/season-pipeline-v2/foreign-host-spain-20260830-report.json \
  --host-report .local/season-pipeline-v2/foreign-host-spain-tile-1-report.json \
  --host-report .local/season-pipeline-v2/foreign-host-spain-tile-2-report.json \
  --host-report .local/season-pipeline-v2/foreign-host-spain-tile-3-report.json \
  --host-report .local/season-pipeline-v2/foreign-host-spain-tile-4-report.json \
  --host-report .local/season-pipeline-v2/foreign-host-spain-tile-5-report.json \
  --initialise --assignment-id world-2000-01-fixed-carriers \
  --output seasons/2000-01/foreign-carrier-assignment.json

python3 scripts/foreign_carrier_candidate_queue_v1.py \
  --registry seasons/2000-01/fixed-carrier-registry.json \
  --source-capture seasons/2000-01/sources/footballsquads-2000-01.json \
  --assignment seasons/2000-01/foreign-carrier-assignment.json \
  --queue seasons/2000-01/foreign-carrier-candidate-queue.json

queue_args=()
for queue in seasons/20??-??/foreign-carrier-candidate-queue.json; do
  queue_args+=(--queue "$queue")
done
python3 scripts/foreign_carrier_candidate_batch_v1.py "${queue_args[@]}" \
  --batch-id pm99-all-country-foreign-carrier-review \
  --output seasons/all-country-foreign-carrier-candidate-review-batch-2000-2024.json

python3 scripts/foreign_carrier_candidate_batch_v1.py \
  --batch seasons/all-country-foreign-carrier-candidate-review-batch-2000-2024.json
```

The focused foreign-assignment/candidate-queue/batch test lane passes nine
tests.
