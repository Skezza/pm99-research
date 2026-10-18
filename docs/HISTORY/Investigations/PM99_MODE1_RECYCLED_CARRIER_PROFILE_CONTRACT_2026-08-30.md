# PM99 mode-1 recycled-carrier profile contract (2026-08-30)

## Purpose

The 2015/16 world baseline has 36 foreign roster slots that share a JUG
carrier.  A historically faithful world package needs one player record per
slot, but a fresh compact (`dd6360`) JUG directory entry is not profile-safe.
This investigation tests whether a pre-existing mode-0 carrier can be made
available to the foreign graph by first replacing its English row with the
already-proven `dd6361` append route.

All tests start from the corrected English 2015/16 build and are disposable.
They keep both roster row counts and every existing row flag unchanged.

## What the executable does

Ghidra establishes two separate indexed loaders:

- `FUN_004b6a50` loads `dbdat\\jug98%03u.fdi` (string at `0x735260`) and
  creates a sorted `{JUG record ID, compact player pointer}` table.  It
  enumerates the JUG directory, so a structurally valid fresh entry can reach
  Search Player By Name.
- `FUN_004b57b0` then loads `dbdat\\eq98%03u.fdi` (string at `0x73524c`) into
  the separate fixed-size team objects used by profile rendering.

This corrects an earlier overstatement: the second lookup is an EQ/team
lookup, not a hidden fourth player database.  The three editable database
files remain the authoritative game inputs.

## Runtime controls

| Control | Foreign profile result | What it establishes |
| --- | --- | --- |
| Fresh high compact JUG ID 33,366 | Native `Application cannot continue` | A new compact directory entry is not enough, even though Search lists it. |
| Same append plus a valid copied `MINIFOTO` entry | Same native error | This is not caused by the native no-photo state. |
| Existing English carrier 4,151 (Artur Boruc) linked to Barcelona without changing its JUG payload | Profile opens | An existing carrier can safely move between a mode-0 and a mode-1 roster when its existing player representation is retained. |
| Carrier 4,151 rewritten as midfielder Luis Enrique | Native error | Reusing an ID is insufficient if its player representation is incompatible. |
| Goalkeeper control: carrier 4,151 rewritten as Vítor Baía (role 0) | Profile opens as `RECYCLE KEEPER` | The recycle route is viable for the exact goalkeeper role. |
| Forward control: carrier 10,006 (roles 12, 8) rewritten as Patrick Kluivert (role 8) | Profile opens as `RECYCLE FORWARD` | A compact role can match one of the retained `dd6361` role slots; it need not be the first slot. |
| Midfielder control: carrier 5,444 (roles 9, 14) rewritten as Philip Cocu (role 9) | Profile opens as `MIDCOCU` | The rule also holds for the midfield branch. |
| Defender control: carrier 10,000 (roles 4, 5) rewritten as Mauricio Pellegrino (role 4) | Profile opens as `DEFPELL` | The rule also holds for the defender branch. |
| Provisioned Sweeper control: existing English carrier 10,000 `[4, 5]` is changed only to `[3]` in its appended `dd6361` clone, then compact JUG 70 (roles `[3, 1, 6, 2]`) is moved into Barcelona | Profile opens as `RECYCLE SWEEPER` | Role code **3** is a valid foreign recycle role, even though the clean English source corpus contains no pre-existing `dd6361` code-3 vector. The surviving appended clone's role vector—not the discarded source bytes—must be compatible. |
| Broad-midfielder mismatch: Dan Gosling role 9 rewritten as Luis Enrique role 20 | Native error | Broad position alone, and a different fine-role code, is not a sufficient allocation key. |

The runner now classifies the native modal as a failed run rather than a
spurious final-step success.  It also accepts an expected profile-name token:
a profile-only control cannot pass merely because the search opened another
listed player.  Runtime evidence lives under
`.local/runlogs/world2015-jug-append/` with one hash receipt per control.

### Role-3 reproducible evidence (2026-08-31)

The new control starts from the hash-identified corrected English base and is
fully disposable:

```bash
PYTHONPATH=upstream/pm99-skezmod-db-editor:. \
python3 scripts/probe_mode1_jug_carrier_recycle.py \
  --base-game .local/season-pipeline-v2/english92-mode0-append-2015-16-20260830-b/game \
  --output-game /tmp/pm99-role3-recycle/game \
  --receipt /tmp/pm99-role3-recycle/receipt.json \
  --mode0-team-record-id 363 --mode0-slot 13 \
  --mode1-team-record-id 1 --mode1-slot 0 \
  --new-mode0-player-id 33377 --mode1-clone-player-id 70 \
  --mode0-source-role-set 3,98,98,98,98,98 \
  --name 'RECYCLE SWEEPER'
```

The receipt proves that only decoded payload offsets `34` and `35` in the
English source clone changed (`[4, 5, 98, 98, 98, 98]` →
`[3, 98, 98, 98, 98, 98]`).  The compact donor is the existing foreign JUG
70, Alberto Belsué, whose active role set begins with code 3.  The runner then
searched and opened the exact `RECYCLE SWEEPER` profile with no native error:

- receipt:
  `.local/research-probes/mode1-jug-carrier-recycle-sweeper-role3-20260831/role3-recycle-receipt.json`;
- runner summary:
  `.local/research-probes/mode1-jug-carrier-recycle-sweeper-role3-20260831/summary.json`;
- native profile screenshot:
  `screens/53_inspect_recycle_sweeper_profile.png`
  (SHA-256 `70489dd8f1296fda1955455c8024909aa4f37ec94b6cd084f320d3d5eada8c16`).

The profile shows `RECYCLE SWEEPER`, `DEFENDER`, and F.C. Barcelona. Its
visible `ROL.` assignment reads `Right Back`, which is expected: PM99 chooses
the displayed tactical assignment from the candidate set and current team
context; it is not a direct dump of slot zero. The proof is profile reachability
with a live code-3 candidate, not a claim that code 3 must always display as
`Sweeper`.

### Role-12 reproducible evidence (2026-08-31)

The same guarded transaction was repeated for the central-striker role used
by the current 2015 source mapping.  The disposable build used mode-0 carrier
`10000`, appended its English clone as `33378` with role vector
`[12, 98, 98, 98, 98, 98]`, and rewrote carrier `10000` from compact donor
`35` (Óscar García, native primary fine-role code `12`).

The runner opened the exact `RECYCLE STRIKER` profile.  Its summary records
`success=true`, phase `profile_only_recycle_striker_done`,
`expected_name_token_satisfied=true`, no blocking PM99 modal and no crash:

- build receipt:
  `.local/research-probes/mode1-jug-carrier-recycle-striker-role12-20260831/role12-recycle-receipt.json`;
- runner summary:
  `.local/research-probes/mode1-jug-carrier-recycle-striker-role12-20260831/summary.json`;
- native profile screenshot:
  `screens/53_inspect_recycle_striker_profile.png`
  (SHA-256 `2ca863e2f695033eab982dad57f18e40cce6dd7e8c929cfe47c08b19d1e7e1be`).

This qualifies role code `12` for the recycle path.  It does not qualify
unrelated fine-role codes.

## Current safe conclusion

There is a promising, bounded way to resolve the 36 shared foreign carrier
slots without creating a fresh compact JUG ID:

1. choose a mode-0 `dd6361` carrier and write a compatible tactical-role
   vector to its appended English clone (the existing mode-0 `dd6361` writer
   is the only permitted route);
2. append that `dd6361` clone for its English roster row;
3. move that English row to the appended carrier, preserving its flag and
   position;
4. rewrite the freed, existing carrier as a compact foreign player; and
5. place it in the corresponding fixed foreign roster slot as part of the
   complete foreign graph transaction.

The compiler now has a deliberately **guarded experimental transaction** for
an explicitly declared recycle: it requires the paired `dd6361` append, exact
mode-0 ownership, exact mode-1 graph reconstruction, and a primary fine-role
match against the declared surviving mode-0 clone.  That is a safety implementation,
**not release permission**.  A release still needs every role code required by
the actual allocation to be mapped and runtime-proven, plus a whole-graph
playthrough.  The disposable runtime builder is
`scripts/probe_mode1_jug_carrier_recycle.py`.

## Capacity audit against the corrected English 2015 base

`scripts/audit_mode1_recycle_capacity.py` was run against the corrected
English 2015/16 build, which is the intended base for a subsequent world
materialisation.  Its immutable receipt is
`.local/research-probes/mode1-recycle-capacity-2015-english-base-20260830.json`.

After the role-3 and role-12 controls, the regenerated receipt is
`.local/research-probes/mode1-recycle-capacity-2015-english-base-20260831.json`.
The older receipt remains historical evidence of the pre-qualification state.

- There are exactly **36 shared compact carriers**, therefore 36 extra foreign
  slots require a recycle transaction.
- There are parser-backed *baseline* mode-0 `dd6361` source carriers for every
  role code except **3**.  The report records that zero baseline capacity; the
  role-3 control proves a source can instead be provisioned through its paired
  `dd6361` clone, never by assigning an arbitrary near match.
- Only role codes **0, 3, 4, 8, 9 and 12** have direct foreign-profile runtime
  controls.  The report lists the other codes as unqualified even where a
   structural source exists.
- The original 1998 duplicates happen to have primary role codes 0, 2 and 3.
  Those are diagnostics only, never claimed as historical 2015 facts.

The report is intentionally read-only.  It cannot pick a historical player,
change a foreign roster, or turn availability into a release.  Any explicit
allocation must name its source player and compatible target, then pass the
compiler and native profile route.

## Remaining qualification work

1. Map the 36 real duplicate slots to compatible source carriers, then prove
   every role code used by that allocation.  The current direct controls cover
   compact role codes 0, 3, 4, 8, 9 and 12 only.
2. Determine whether every historical 2015 role code required by the 36 slots
   can be paired to a declared, role-compatible mode-0 clone.  Values outside
   the editor's normal 0..17 field contract must remain blocked until
   independently explained.
3. Add a transactional recycle allocation stage to the season compiler,
   including mode-0 and mode-1 exact-tail checks, no duplicate JUG IDs and
   profile-proven release gates.
4. Only then use it in a fully sourced, reviewed world ledger.  It resolves a
   technical allocation gap; it does not supply the still-missing historical
   club, player, manager, kit and portrait data for the 451 foreign carriers.
