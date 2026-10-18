# 2015/16 release revalidation

Revalidated on 2026-09-01. This directory describes the separately existing
2015/16 reproducible PM99 release; it is not a candidate-queue season and is
not represented as a historically complete all-country release.

The stable local release link resolves to
`.local/season-workspace-v1/2015-16-final-clean-game`. Its verified release
hashes are:

| File | SHA-256 |
| --- | --- |
| `DBDAT/JUG98030.FDI` | `e1c2f481c6eb000e4f5eb4702d7ae20afaf0cdc7fd9801f295bba4869dcc5ff0` |
| `DBDAT/EQ98030.FDI` | `cbf1d2ab077d4519ad9872027681f5bd5ee2d4857a51909f81517cf583bc7396` |
| `DBDAT/ENT98030.FDI` | `5ec1432d0a1de2800e6fc9a8d25b854fbe8e6eb263d05af8fd9ea2ba478f150a` |
| `DBDAT/MINIFOTO.PKF` | `57dda4b6ea713370a58406947db4b807c336e1eb1426cd8f2f2388ad71ac6ff9` |

`python3 scripts/season_workspace_v1.py check --workspace
seasons/2015-16/workspace.json` passed. The five declared local source and
calendar artifacts in `season-package.json` also match their recorded hashes.
The final clean-base audit at
`.local/season-workspace-v1/2015-16-final-build/clean-base-audit.json` passes:
451 fixed roster tails, zero tail mismatches, zero append/recycle operations,
and declared writes of 8,112 player, 395 club, and 174 manager carriers.

The retained Wine smoke-test receipt is
`upstream/pm99-runner/docs/artifacts/pm99_runner/world2015_clean_final_guarded_stoke_20260831/summary.json`
(SHA-256 `21defbc8c88b31a426adbcbc42a9153efb25c27f11f8a92d992f29372b5c1a0c`).
It selects Stoke City using `(559,224)` then `(395,360)`, reaches the Stoke
Squad Management screen, and records no crash. It is a squad-route smoke test,
not opening-lineup proof.

## Remaining world-scope gates

The recorded package/projection deliberately retains measurable historical
gaps: 395 source-updated clubs and 8,064 source-updated players; 56 preserved
source-gap clubs and 993 preserved source-gap players; 174 dated manager
writes across 447 manager entities; six dated ground writes; and 36 shared
native preserve carriers. The handover also records omitted squad depth,
portrait, kit, rating, and manager-reconciliation queues.

Consequently, this release remains a reproducible, statically audited and
runtime-smoke-tested engineering milestone. It must not be relabelled as a
perfect-historical or current all-country delivered database without resolving
those gaps and producing the programme's required independent builds and
runtime qualification.

See `docs/HANDOVER_2015_16_WORLD_DATABASE_AND_SEASON_PIPELINE_2026-08-31.md`
for the complete release receipts, constraints, and editorial queues.
