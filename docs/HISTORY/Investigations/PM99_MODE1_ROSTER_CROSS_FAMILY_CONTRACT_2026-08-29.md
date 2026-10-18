# Mode-1 roster link and player-club cross-family result (2026-08-29)

## Result

The five-byte external `EQ -> JUG` rows form the live foreign-club roster
graph. A player profile's current club is reconciled from that graph; it is
not an independent JUG field that needs a second write.

This is a useful positive and negative result. A one-row replacement changes
the named foreign club's offer roster. It becomes a real transfer only when
the source-club row is changed in the same transaction. Leaving a player in
two rows creates ambiguous legacy membership, and the profile continues to
show the other club.

## Disposable Barcelona control

The fixture uses F.C. Barcelona (`EQ` record `1`) and a copy of the 2015/16
research baseline.  The normal list starts with `14 Abelardo`; the only
database change is its first external player reference:

| Item | Before | After |
| --- | ---: | ---: |
| Row | first F.C. Barcelona external `EQ -> JUG` row | same row |
| Flag | `0` | `0` |
| JUG record id | `27` Abelardo Fernández Antuña | `20` Raúl González Blanco |
| File bytes changed | one | one |
| File offset | `0x2300` | byte `0x1b` -> `0x14` |

The indexed-EQ writer reopened the resulting file cleanly. Its receipt is
`.local/research-probes/mode1-barcelona-roster-20260829/roster-edit.json`.

## Live evidence

The untouched-executable foreign offer route visibly shows the replacement:

- Baseline F.C. Barcelona roster: `mode1_league_route_20260829/screens/51_inspect_after_search_return.png`
  (first row `14 Abelardo`).
- Mutated F.C. Barcelona roster:
  `mode1_barcelona_roster_raul_20260829/screens/50_inspect_barcelona_roster_after_relink.png`
  (first row `9 Raúl`).

The replacement is therefore consumed by the game. In this deliberately
incomplete one-row control, selecting the newly displayed Raúl opens a real
profile whose club line remains **Real Madrid C.F.**:

- `mode1_barcelona_roster_raul_profile_20260829/screens/52_inspect_relinked_raul_profile.png`

That is not a second JUG club field. The decisive second control changes the
corresponding Real Madrid row (record `4`, slot `5`) from JUG `20` to the
outgoing JUG `27`. The final database differs from the original at exactly two
bytes: `0x2300` (`27 -> 20`) and `0x3a90` (`20 -> 27`). Raúl's same game
profile now visibly says **F.C. Barcelona**:

- `mode1_barcelona_real_swap_raul_profile_20260829/screens/52_inspect_relinked_raul_profile.png`

All runs used the unmodified `MANAGPRE.EXE`; the mutation runs exited without
a Wine debugger or game crash.

## What this proves

- External roster rows are live for a mode-1 club's offer-list rendering and
  current-club resolution.
- Existing rows have a bounded direct replacement operation: preserve the
  flag and row count, replace only the existing four-byte JUG id.
- A two-club, two-row swap changes both the foreign offer list and the moved
  player's displayed club without changing the executable.
- The updated rows can be reopened by the parser and consumed by the game.

## What it deliberately does not prove

- Adding/removing rows, changing the roster count, or changing row flags.
- Squad-management, opening XI, shirt number, tactics, contract or transfer
  behaviour for a foreign club.

`FUN_004b9e80` supplies the runtime safety reason for treating this as a graph
transaction. Its current-squad filter compares the selected team context with
a runtime player word at `player + 0x90` (`0x004b9ebc..0x004b9ec5`). The
two-row Raúl control proves the roster graph supplies a coherent value for
that word. The precise duplicate-row precedence rule has not been reverse
engineered and is not needed for a generated historical database: generated
club rosters must not duplicate a JUG id.

## Product/compiler rule

The compiler may change foreign roster membership only by a complete planned
transaction. A public editor may eventually expose a constrained **move
player** action, not an unguarded raw-row editor. Each operation must:

1. replace an existing target row and preserve its flag/count;
2. replace the outgoing source row where applicable;
3. reject a final generated roster graph containing a duplicate JUG id;
4. re-open the EQ file and audit every affected carrier; and
5. retain the opening-XI/tactics/contract/flag and row-count fields unless
   they have their own contract.

The 35 duplicate JUG ids in the 1998 baseline are legacy data to preserve,
not an example to copy. They need a separate semantics investigation before a
public editor supports intentional duplicates or linked-player loans.
