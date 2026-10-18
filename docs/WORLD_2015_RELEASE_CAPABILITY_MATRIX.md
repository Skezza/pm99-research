# 2015/16 world database release capability matrix

This is the release-facing summary for the clone-free v11 PM99 2015/16 world
database. “World” means PM99's existing foreign database carriers are updated
for opponents, competitions and player browsing. Foreign clubs do **not**
become human-selectable; the playable English scope is unchanged.

This is an in-place content replacement. Country blocks, carrier counts,
league sizes, promotion/relegation rules and continental draw logic remain
native PM99 topology. No foreign league expansion or game-rule patch is
claimed.

## Signed-off v11 disposition

| Area | Updated | Preserved / unresolved |
| --- | ---: | ---: |
| Foreign club carriers | 395 complete dated squads | 7 dated prefixes with native tails; 49 wholly native |
| Player graph | 9,354 unique JUG carriers / 9,390 roster references | 36 native shared references deliberately retained; no recycle or append operations |
| Dated player writes | 8,239 full-squad players + 48 partial-prefix players = 8,287 | 994 source-gap rows + 36 transfer-overlap displacements + 37 shared/invalid fallbacks = 1,067 preserved rows |
| Club identity | 402 updated short/full identities (395 full + 7 partial) | 49 wholly native identities |
| Duplicate club identity repair | 9 same-country carrier rebindings | 0 known same-country duplicate identities remain |
| Player display strings | 7,893 parser-validated source-derived aliases | Native strings on preserved rows; no fixed-length fallback |
| Managers | 174 dated graph-safe writes | Missing facts and one shared manager-entity conflict preserve native |
| Grounds/capacity | 6 dated season-ground writes | Other grounds and all capacities without season-scoped evidence preserve native |
| Foreign kits | 268 approved era carriers / 804 patched records | 183 native total: 127 explicit source-ready fallbacks + 56 not-source-ready carriers |
| English kits | 92 clubs / 447 verified records | — |
| World portrait stage | 3,479 identity-bound portraits applied across 8,311 selected records | 4,760 selected native no-photo; 72 selected native portraits preserved; 1,043 records untouched outside the selected stage; 0 pending |
| English portraits | 2,294 restored | 6 native no-photo |
| Opening XI / tactics | Native stored state retained | No claim of historically correct foreign opening line-ups or formations |
| Finance and shirt number | — | Foreign values preserved; foreign writers remain unqualified |
| Country/league membership and draw pools | — | Preserved byte-for-byte/topologically |

The club partition is exact: **395 full + 7 partial + 49 preserved = 451**.
The seven partial carriers contribute 48 dated prefix players and retain their
native tails. The 49 wholly preserved carriers have no safe complete dated
source. These are explicit fail-open outcomes, not historical completion.

The player accounting is also explicit. v11 removes the rejected recycle
route, leaves 36 native shared references in the fixed graph, and preserves 37
affected carriers/slots rather than inventing or appending replacements.
The 8,287 dated writes plus 1,067 preserved rows equal the 9,354 unique player
carriers. The 36 additional roster references are the deliberately shared
native links.

## Field contract

| Surface | v11 behaviour | Qualification boundary |
| --- | --- | --- |
| Club short/full name | Variable-string writer for sourced identities | Existing carrier only; no country move or added club |
| Ground/capacity | Write only season-scoped dated facts | Six ground writes; no sourced capacity write |
| Manager link/name | Existing ENT carrier/link writer | 174 safe writes; missing/shared-conflict facts preserve native |
| Club finance | Preserve | Mode-1 finance has no release need or runtime proof |
| Club kit | Carrier-keyed archive replacement | 268 approved foreign carriers; 183 native carriers (127 explicit source-ready fallbacks plus 56 not source-ready) |
| Compact player name | Variable-length writer with parser revalidation | 7,893 aliases trace to source names; no fixed-length fallback |
| Birthday, nationality, height, weight | Reconciled facts or deterministic editorial fallback | Unknown native bytes remain preserved |
| Broad position and visible ratings | Source/FIFA facts or deterministic editorial fallback | Not independent historical scouting proof for every player |
| Fine/secondary roles | Native compact writer on safe rows | Shared-link/recycle-affected rows preserve native; no clone route |
| Shirt number | Preserve | Foreign storage writer is not independently qualified |
| Portrait | Identity-bound converted bitmap or native no-photo | No random or inherited modern-face substitution |
| Unknown bytes and roster tails | Preserve | No semantic-editability claim |

## Final v11 receipts

Paths are relative to `.local/season-pipeline-v2/`; proprietary binaries and
materialised game trees remain untracked.

| Receipt | SHA-256 / result |
| --- | --- |
| `world-2015-16-source-core-395-strict-v2-v11.json` | `e1724d47a508409ea31d45aaa1cb1460eb01266d59246638eea32078838d8832` |
| `world-2015-16-source-core-395-strict-v2-v11-qa-receipt.json` | `cea074db157e4b6a1744f7db204ccd25f274df4e1a6b95f7817f3aeff1d8685b`; pass, 0 failures |
| `world-2015-16-source-core-395-compiler-receipt-v11.json` | `55ff06c4b82bb29ad096bc492d9bcf23ec9c29332c0a50a4313c699539078317` |
| `world-2015-distinct-club-ownership-aware-asset-manifest-v11.json` | `4fad275a6aac9af011bab43593dd9f8ec62e2a4ec3c41c40e051d160825aba50`; clone operations 0 |
| `world-2015-16-source-core-395-english-asset-restoration-receipt-v11.json` | `510e8d2e79025a1ec17ba7a38193fd945be1fe8d3443462bea3d3d8d817dbad3` |
| `world-2015-16-source-core-395-world-portrait-application-receipt-v11.json` | `b4134c17240c107a1eddc7f34d8bdbaf5a18c43fef6dd0fa09de9934c611814a` |
| `world-2015-16-source-core-395-post-portrait-asset-audit-v11.json` | `0b26d603be1fb12bcfcff43a7b5bdccaef30e437d1b366aae3120a711d7ae9fd`; pass |
| `world-2015-16-source-core-395-final-kit-application-receipt-v11.json` | `c437e55aa34c814bc1639373bc400d57dc22ed1975596049194aa49406802294`; complete for approved kits |
| `world-2015-16-source-core-395-final-kit-postwrite-audit-v11.json` | `76403b0677c419041b44c1d6832d80830568ffe20b8e6250eca2fcec0714a3a2`; pass |

The materialised release tree is
`.local/season-pipeline-v2/world-2015-16-source-core-395-final-game-v11c`.

## Runtime sign-off

v11 passed the three final runtime routes that cover the defect and the main
updated-game surfaces:

- Arsenal shared-link preservation and complete playable roster:
  [`world2015_v11_arsenal_shared_preserve_clean_20260831`](../upstream/pm99-runner/docs/artifacts/pm99_runner/world2015_v11_arsenal_shared_preserve_clean_20260831)
- Stoke playable English route:
  [`world2015_v11_final_stoke_20260831`](../upstream/pm99-runner/docs/artifacts/pm99_runner/world2015_v11_final_stoke_20260831)
- Real Madrid foreign opponent/profile route:
  `.local/runlogs/world2015_v11_final_foreign/world2015_v11_final_spain_real_madrid_20260831`

These final routes supplement the targeted writer controls documented in:

- [`PM99_MODE1_TEAM_IDENTITY_RUNTIME_2026-08-30.md`](HISTORY/Investigations/PM99_MODE1_TEAM_IDENTITY_RUNTIME_2026-08-30.md)
- [`PM99_MODE1_MANAGER_LINK_AUDIT_2026-08-29.json`](PM99_MODE1_MANAGER_LINK_AUDIT_2026-08-29.json)
- [`PM99_FOREIGN_KIT_ARCHIVE_CONTRACT_2026-08-29.md`](HISTORY/Investigations/PM99_FOREIGN_KIT_ARCHIVE_CONTRACT_2026-08-29.md)

## Rejected clone builds

r9 and r10 are retained only as negative controls. Both statically passed but
failed the Arsenal effective-roster runtime route. Moving clone IDs below
32,768 in r10 did not fix it, disproving the ID-threshold hypothesis. The
recycle/append route is therefore not release-safe and v11 performs no such
transactions.

## Release statement

Clone-free v11 is the signed-off, runtime-proven 2015/16 world database
candidate. It is structurally safe and records every fallback, but it is not a
claim of complete historical coverage: 7 squads are partial, 49 clubs remain
native, 37 affected shared/recycle rows remain native, 183 foreign kits remain
native (including 127 explicit source-ready fallbacks), most ground/capacity
facts are preserved, and foreign
opening tactics are not historically authored. Foreign clubs remain
non-playable database content.
