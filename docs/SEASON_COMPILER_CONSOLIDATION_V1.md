# Season compiler consolidation V1

The year-neutral release entry point is `scripts/season_workspace_v1.py`.
One canonical workspace now binds:

- the verified base or preceding season layer;
- one strict Season Package V2 document;
- a snapshot of the permanent cross-season editorial timeline;
- the fixed rating-source precedence;
- portrait results and the mandatory native-no-photo fail-open policy.

The first migrated workspace is `seasons/2015-16/workspace.json`. The same
shape is used for every season from 1999/00 to 2025/26. A new season supplies
different historical data and assets; it does not receive a new binary
compiler.

## Normal commands

```bash
python3 scripts/season_workspace_v1.py check \
  --workspace seasons/2015-16/workspace.json

python3 scripts/season_workspace_v1.py prepare \
  --workspace seasons/2015-16/workspace.json \
  --output-dir .local/builds/2015-16-prepared

python3 scripts/season_workspace_v1.py compile \
  --workspace seasons/2015-16/workspace.json \
  --base-tree .local/season-pipeline-v2/english92-clean-release-2015-16-20260830 \
  --materialisation-tree .local/builds/2015-16-game \
  --output-dir .local/builds/2015-16-receipts \
  --copy-base
```

`prepare` writes an effective package, a hash-locked editorial overlay and
application receipt, a coverage report, and a complete named missing-portrait
list. `compile` first verifies every byte of the declared base inventory and
then delegates database writes to Season-Package Compiler V2.

## Editorial corrections

Gameplay feedback is stored against real `identity_id`/`person_id` values in
the editorial timeline. A correction can cover one or several seasons. On the
next clean build it is compiled into a package-bound overlay with expected old
values, so stale or ambiguous feedback fails before a database is opened.

Unknown preserve-only foreign managers are intentionally not given invented
person identities. They remain unbound and cannot be editorially edited until
identified. All editable records must have an exact timeline binding.

The rating precedence is fixed and machine-readable:

1. reviewed editorial value;
2. nearby-season editorial continuity;
3. FIFA nearest-edition fallback;
4. deterministic context fallback;
5. preserve native value when identity or role is uncertain.

This is provenance precedence, not a demand to use FIFA. Hand-authored season
ratings remain the preferred source.

The migrated 2015 foreign layer does not yet meet that preferred editorial
mix. Its 9,177 players currently contain 3,688 FIFA-derived rating sets, 4,374
deterministic context fallbacks, five deterministic goalkeeper-handling
guards, 45 partial-source/native-rating rows and 1,065 preserved native rows.
It contains no foreign rating set falsely
labelled as reviewed editorial. A final provenance audit found 36 reviewed
duplicate-person ownership decisions whose unchanged native ratings had
previously inherited that label; the label, not the values, was corrected.
Future editorial passes replace lower-priority rows through the timeline; the
compiler itself does not average or flatten them.

## Clean-base correction found during migration

The signed-off cumulative world v11 folder was playable, but its foreign
package was compiled over an earlier world-modified database. It therefore
inherited expanded foreign roster tails and enlarged `dd6360` name windows.
It was not reproducible directly from the clean English 2015 layer.

The consolidated projection adds `--fit-native-rosters` to the 2015 source
adapter. It now:

- reads every foreign roster slot from the verified clean base;
- binds dated players to those slots in source order;
- preserves shared native references;
- shortens display names only through the parser-proven variable-name alias
  policy while retaining the exact source name separately;
- preserves native tail slots when a source squad is smaller;
- records, rather than hides, source depth players which cannot fit.

For 2015/16 the clean native graph has 9,177 unique foreign player carriers.
It accepts 8,064 dated player writes. Seventy-six source clubs exceed their
native capacity, so 177 depth players are omitted. No roster is expanded, no
club changes country, and league sizes and competition mechanics are untouched.
The complete per-club accounting is in
`seasons/2015-16/clean-base-projection-receipt-v2.json`.

The old cumulative v11 package and portrait receipts remain in the local
release evidence under `.local/season-pipeline-v2/`. They are not inputs to
the clean compiler or duplicated in the durable season source folder.

## Portraits

Portraits fail open. An unavailable, failed, unsafe or uncovered image becomes
PM99 native no-photo and is named in `missing-portraits.json`. A carrier image
is never silently inherited for a different player.

The clean rebinding stage joins the reviewed historical conversions by fixed
club plus exact normalized dated player identity, preferring the original
squad slot. It never copies a face by old carrier number. Of 8,112 sourced
foreign player rows, 3,350 reuse an identity-safe conversion and 4,762 become
native no-photo. The complete workspace result covers all 9,177 package
players: 3,350 applied portraits and 5,827 named no-photo outcomes. Fifty-seven
source identities could not be joined to the earlier asset manifest and are
listed rather than guessed. Fifteen old preserve-native portrait decisions
were deliberately rejected because their carrier ownership had changed.

The machine-readable evidence is under `seasons/2015-16/assets/` and the full
missing list is produced by `season_workspace_v1.py prepare`.

## Final clean release proof

The final release is materialised at
`.local/season-workspace-v1/2015-16-final-clean-game` and the stable local link
is `.local/releases/pm99-2015-16-world`.

- clean compiler hashes: JUG `e1c2f481c6eb000e4f5eb4702d7ae20afaf0cdc7fd9801f295bba4869dcc5ff0`,
  EQ `cbf1d2ab077d4519ad9872027681f5bd5ee2d4857a51909f81517cf583bc7396`,
  ENT `5ec1432d0a1de2800e6fc9a8d25b854fbe8e6eb263d05af8fd9ea2ba478f150a`;
- 451 fixed foreign roster tails are unchanged; 8,112 player, 395 club and
  174 manager carriers are the only declared database writes;
- 268 foreign club carriers have an identity-bound 2015 compact kit and 127
  sourced clubs retain the native PM99 kit with a named fallback reason;
- the goalkeeper audit records five guarded corrections and no remaining
  keeper whose handling is more than 15 points below quality;
- the clean Stoke runner route reaches squad, two player profiles and ground;
- the fixed foreign route reaches Barcelona's 2015 opponent lineup and kit;
- both runner processes exit cleanly without a Wine debugger or crash.

The final guarded build is proven by
`world2015_clean_final_guarded_stoke_20260831`. The earlier runner pass which used the old Division 2 coordinates selected
2015 Sheffield United. It remains useful new-game evidence but is not counted
as Stoke proof. The corrected Premier League coordinates are recorded by the
successful Premier League Stoke runs.

## 2015 English layer

The English 92-club update predates strict native package provenance. It is
retained as an approved cached-output layer with exact blobs, package hash,
build plan and output inventory under `seasons/2015-16/english-layer/`. The
foreign workspace declares that output inventory as its base. This is explicit
legacy composition, not a claim that the old English artwork can already be
regenerated from raw sources.

New seasons should be authored as strict native packages from the start. The
cached English bridge is a 2015 migration fact, not the intended 26-season
workflow.

## Release gates for each season

1. Canonical package, identity timeline and input hashes validate.
2. Clean base or previous layer inventory matches exactly.
3. Native roster counts and shared references remain unchanged.
4. Ratings report shows the source tier used for every player.
5. Portrait stage covers every package player; failures are named no-photo.
6. Two clean compilations have identical database hashes.
7. Static parser/reference audit passes.
8. Wine runtime smoke tests cover an English new game, representative squads,
   managers, kits, portraits and foreign opponent/browser routes.

Native Windows testing is not a per-season compiler stage. It remains useful
only when the executable/runtime layer changes.
