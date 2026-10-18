# PM99 foreign topology writer closeout (2026-08-30)

## Decision

There is **no released foreign league-membership writer**.  This is a closed
research decision, not an unfinished editor button: no persistent,
database-backed foreign membership representation has been identified or
runtime-proven, so writing one would be a guess.

The safe world-database operation is instead a **fixed-carrier replacement**:
replace the supported club, player, manager, kit and photo data inside an
existing foreign EQ carrier while preserving its EQ directory record ID,
directory position, structural bytes and the game's existing topology.  It is
the same distinction as replacing the name on a numbered seat, rather than
moving the seat into another stand.

This is sufficient for a historical world package only when the season plan
assigns each historical club to an existing compatible carrier slot.  It does
not create foreign domestic-league simulation, add a club, change the number
of slots in a country, or change which record PM99 draws in continental
fixtures.

## Fresh runner evidence

The initial context capture hit an unrelated runner navigation problem: after
dismissing `The initial line-up is not correct`, the disposable game could
return to the dashboard and reopen the same warning.  It was not evidence of
a database fault.

The fresh replacement route is:

```bash
./scripts/run_pm99_experiment.sh route-capture --worker default \
  --run-tag foreign_competition_valletta_boundary_v3_validlineup_20260830 \
  --allow-dirty-runner -- \
  --skip-setup --skip-prepare --skip-build \
  --team-name 'Manchester Utd.' --team-select-x 209 --team-select-y 360 \
  --division-select-x 78 --division-select-y 302 \
  --season-sentinel-full-times 1 --season-sentinel-max-steps 120 \
  --profile-count 0 \
  --foreign-competition-snapshot-name Valletta \
  --foreign-competition-snapshot-record-id 2151 \
  --foreign-competition-snapshot-max-mib 96
```

The run reached `competition_round_continue` successfully after one completed
match, with no lineup repair and no database or executable override.  It
captured exactly the requested read-only snapshots either side of the empty
Round-2 screen's Continue action:

- `.local/runlogs/pm99_runner/foreign_competition_valletta_boundary_v3_validlineup_20260830/summary.json`
- `.local/runlogs/pm99_runner/foreign_competition_valletta_boundary_v3_validlineup_20260830/memory/foreign_competition_pre_competition_round_continue.json`
- `.local/runlogs/pm99_runner/foreign_competition_valletta_boundary_v3_validlineup_20260830/memory/foreign_competition_post_competition_round_continue.json`
- `.local/runlogs/pm99_runner/foreign_competition_valletta_boundary_v3_validlineup_20260830/memory/foreign_competition_pre_namecopy_diff.json`

The second capture improves the earlier negative control by recording a small
context window around each ID signal.  It confirms that ID `2151` and the
loaded Valletta object are present before and after the action.  The changed
pages also contain generated / cache-shaped objects.  None identifies a
pre-name-copy selected-ID field or says where the candidate came from.

In particular, the repeatedly structured `0x03ed*` pages contain many IDs
and their surrounding data changes together.  That is a loaded cache/UI state,
not a membership table.  Treating its appearance as a country or division map
would recreate the false-lead problem documented in
`PM99_FOREIGN_COMPETITION_PRE_NAMECOPY_BLOCKER_2026-08-30.md`.

## Persistent database check

`scripts/probe_pm99_foreign_topology_boundary.py` is a new read-only guard.
It scans the decoded payload of every indexed `EQ98030.FDI`, `JUG98030.FDI`
and `ENT98030.FDI` entry for the little-endian ID of a proven live carrier.

On the 2015 English V2 source package, live draw carrier `EQ 2151` (Valletta)
has an EQ directory entry at `0x1604` with a payload at `0x0d68df`.  Its ID has
zero decoded-payload references across all three FDI families.  Raw byte
coincidences are only in indexed directories and therefore do not constitute
a relation field.

This proves a limited but important point: the existing editable database
families do not encode a decoded payload relation to the carrier which PM99
uses for this live draw.  It does **not** prove that the executable has no
candidate-pool algorithm; it rules out promoting an FDI byte as a safe writer.

The probe returns `payload-reference-present-investigate-before-writing` if a
future corpus does contain such a reference.  It will never silently treat a
matching two-byte value as a relation.

## Ghidra availability

The stale MCP project was left untouched.  A separate analysis-only project,
`PM99_FOREIGN_AUG30`, was imported from the runner's pristine `MANAGPRE.EXE`
on the server.  This repairs access to an analysable PM99 program without
overwriting the shared MCP project.  It does not change the conclusion above:
the known hardware watch remains a generic sorted lookup and no Ghidra
call-chain identifies the candidate-pool source.

## What the world compiler may do

| Operation | Status | Rule |
| --- | --- | --- |
| Replace an existing foreign carrier's supported club identity | Allowed | Keep its EQ directory record ID and position fixed. |
| Replace supported roster / manager / club text / compact kit / photo state | Existing contract only | Validate each family and retain no-photo where a portrait is unavailable. |
| Publish a historical carrier-assignment ledger | Required | Every foreign club must name its immutable carrier ID and source evidence. |
| Reorder EQ directory entries or change record IDs | Forbidden | These may be part of executable topology. |
| Write a country, division or league byte | Forbidden | No semantic field or runtime write proof exists. |
| Add/remove foreign carriers or change domestic league size | Forbidden | This is engine expansion, not a database edit. |
| Change continental draw candidates | Forbidden | Candidate-pool source remains untraced. |

## Operational release guard

[Fixed-Carrier World Ledger V1](../../FIXED_CARRIER_WORLD_LEDGER_V1.md)
turns the allowed operation into a release check.  It binds every club in a
world package to its existing EQ carrier ID and its immutable directory
ordinal, hashes the exact base EQ directory identity, requires hashed identity
evidence, and audits the output for record/key/order/count changes or a write
to an unassigned EQ carrier.  It deliberately does not add a topology field or
a membership writer.

The same validation produces a non-blocking review queue of every player whose
portrait becomes PM99's native no-photo state.  A missing or unsafe source can
never fall back to the historical carrier photo or an unrelated placeholder.

## Consequence for 2015 and later seasons

The world package can safely model the fixed international club capacity as a
season-specific assignment ledger.  For example, a 2015 Spanish club can
replace the content of a Spanish carrier that is already in PM99's fixed
Spanish group.  The compiler must not use that as evidence that it has written
La Liga membership; it has supplied a historically appropriate club inside
the existing game topology.

If a desired season cannot be represented by the existing carrier count and
country/competition slot pattern, that is an explicit release blocker or a
separate executable-mod project.  It must not be papered over with a guessed
DBDAT write.

## Verification

```bash
/home/joe/ductor/.venv/bin/pytest -q \
  scripts/test_probe_pm99_foreign_topology_boundary.py \
  upstream/pm99-runner/tests/test_foreign_competition_memory_snapshot.py

python3 scripts/probe_pm99_foreign_topology_boundary.py \
  --dbdat .local/season-2015-16/english92-2015-16-editorial-v1-r2/game/DBDAT \
  --record-id 2151
```

The research milestone is therefore closed **preserve-only**.  The world
compiler can proceed only with explicit fixed-carrier assignments; a
foreign-membership writer remains deliberately absent.
