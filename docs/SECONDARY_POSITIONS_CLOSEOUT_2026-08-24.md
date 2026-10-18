# Secondary Positions: Research Closeout (24 August 2026)

## Decision

The PM99 player record has a safe, bounded fine-role contract.  It is not the
same thing as the `ROL.` text shown on a player profile.  This note supersedes
the earlier, one-byte-late marker decode recorded on the same date.

- Slot 0 is the player's intrinsic primary fine role.
- Slots 1 to 4 are optional intrinsic secondary fine roles.
- Slot 5 is retained exactly as stored.  It is often outside the valid role
  range and must not be presented as a secondary position.
- Valid fine-role codes are `0..17`; zero bytes in the stored role window mean
  unassigned.  Duplicates of the primary role are not secondary positions.

The browser editor may eventually expose this as a primary role plus up to four
secondary roles, with a fail-closed writer for the relevant player-record
family.  It must not expose the profile's tactical `ROL.` value as this field.

## Larus Sigurdsson baseline

The current runner-pristine `JUG98030.FDI` has Larus at Stoke visible squad row
4.  The true six-byte window starts at `name_end - 2`, not `name_end - 1`.
His stored role-window bytes are:

| Slot | Stored byte | Meaning |
| ---: | ---: | --- |
| 0 | `06` | **Inside Centre Right** (code 5) |
| 1 | `05` | **Inside Centre Left** (code 4) |
| 2 | `00` | unassigned |
| 3 | `00` | unassigned |
| 4 | `00` | unassigned |
| 5 | `00` | unassigned |

The following byte is `21`, outside the six-role window, and remains
preserve-only.

So Larus's positions are:

- Primary fine role: **Inside Centre Right** (slot 0).
- Secondary fine role: **Inside Centre Left** (slot 1).
- Remaining fine-role slots: empty; Larus has no third stored fine role.
- Coarse position: **Defender**.

The profile screen can display `ROL. INS. CENT. RIGHT` for this same player.
That is the tactical assignment selected by the initial Stoke line-up, not a
contradiction and not a secondary-position readout.

## Evidence

### Binary consumer

Ghidra analysis of `MANAGPRE.EXE` establishes both the loader and the runtime
consumer:

- `FUN_004afd80` reads six consecutive role values into the player structure
  at `+0x1d..+0x22`, and mirrors slot 0 at `+0x23`.
- `FUN_004b13f0` iterates all six values at `player + 0x1d` when computing the
  penalty for a requested tactical role.  The game shows `100 - penalty` in
  its role-selection UI; those percentages are derived, not stored.

This is direct runtime evidence that secondary slots participate in PM99 role
suitability, rather than being parser decoration.

### Isolated game test

The runner tests changed only one file byte in Larus's entry at a time:

| Database | Role bytes | Change |
| --- | --- | --- |
| Baseline | `06 05 00 00 00 00` | none |
| First-role control | `01 05 00 00 00 00` | Tactics shows Keeper 100% while retaining Inside Centre Left 100% |
| Second-role control | `06 01 00 00 00 00` | Tactics changes the other live-role contribution; the original 100% Inside Centre Left is lost |

Each `cmp -l` reported exactly one difference.  Both control databases
completed a new game and opened the Tactics row-4 dropdown in PM99.

- Baseline menu: `larus_tactics_role_menu_retry_20260824`.
- First-role control: `larus_tactics_secondary_candidate_20260824`.
- Second-role control: `larus_tactics_primary_control_20260824`.

The Tactics dropdown is the relevant UI evidence.  Baseline Larus shows
Inside Centre Left 100% and Inside Centre Right 98%; changing either of the two
adjacent live bytes changes the role-suitability table without disturbing the
other live role.  The profile `ROL.` label remains a tactical assignment and
is not a fine-role display.

## What this closes and what it does not

This closes the *format and runtime-consumer research*: the field is six
fine-role slots, the primary/secondary/tail boundaries are known, and an
isolated secondary write loads in the real game without touching adjacent data.

Before exposing editing in the browser product, add the record-family-aware
read/write implementation, unit tests for round-trip preservation, a manifest
shape, and a tactics-screen assertion of the derived suitability percentage.
Those are product-integration tasks, not unresolved format research.
