# Mode-1 pre-link block / opening-formation boundary (2026-08-29, corrected 2026-08-31)

## Result

The 1,767 bytes immediately before a modern mode-1 carrier's external
manager/roster tail are a **live, validation-sensitive opaque block**. Its
interior has a repeatable `11 × 20 × 8` shape, with a two-byte prefix and a
five-byte trailer, but it is **not a proven mode-1 initial-tactics writer**.

The earlier version of this note incorrectly said that the indexed `DBASEPRE`
loader parses the interior for both modern record modes. The corrected control
flow proves that its sparse state parser is mode-0-only. A later game consumer
can still make the mode-1 block validation-sensitive (as the runtime controls
show), but the player-to-slice mapping and field semantics have not been
located. No compiler may write any byte of this block.

## Corrected static evidence

In `DBASEPRE.EXE` `FUN_00439f50`, the raw EQ mode byte is read into `EBP` at
`0x0043a002`. At `0x0043a0db`, `TEST EBP,EBP; JNE 0x0043a329` bypasses the
entire sparse parser when the record is mode 1. The byte-reading/state-store
loop at `0x0043a2ca..0x0043a328` is therefore reachable only for mode 0.

For mode 1, the loader starts after the shared strings, skips exactly
`0x6e7` bytes at `0x0043a32f`, then reads the manager/roster tail. Barcelona
EQ 1's mode-1 block begins at stored raw payload offset `107` and its link
count begins at `107 + 0x6e7 = 1874`.

This proves a durable **boundary**, not the meaning of the bytes inside it.
The nearby consumer at `DBASEPRE.EXE!0x00424e34` reads a runtime table through
an index held outside this EQ raw block, so it cannot establish that tactical
slice 1 corresponds to external-roster row 1 (or any other roster row).

## Fresh-game controls

Both tests mutate Barcelona EQ record 1 only and preserve every byte outside
the 1,760-byte interior, including its header/trailer, roster rows and manager
link. They demonstrate a real runtime dependency, but cannot identify the
later consumer or attach any of the eleven apparent slices to a player.

| Control | Mutation | Result |
| --- | --- | --- |
| Invalid cluster | All eleven players and all twenty states set to `(128, 250, 128, 250)` | PM99 reaches Barcelona's presentation, then rejects the new game with `Application cannot continue.` |
| Valid 4-3-3-shaped control | Eleven distinct PM99-range positions, repeated across the twenty states | A fresh Barcelona-versus-Arsenal friendly reaches half-time normally. |

Evidence:

- invalid receipt: `.local/research-probes/mode1-barcelona-tactics-cluster-20260829/mutation-receipt.json`;
- valid receipt: `.local/research-probes/mode1-barcelona-tactics-433-20260829/mutation-receipt.json`;
- invalid runtime capture: `artifacts/mode1_dashboard_route/mode1_barcelona_tactics_cluster_live_capture_20260829/screens/36_inspect_live_match.png`;
- valid runtime capture: `artifacts/mode1_dashboard_route/mode1_barcelona_tactics_433_runtime_20260829/screens/35_inspect_mutated_match.png`.

## Guardrails

1. `scripts/probe_eq_initial_tactics.py --allow-mode1-candidate` remains
   research-only. It must never become a release writer on the strength of the
   two controls above.
2. Treat the entire `0x6e7` bytes as preserve-only, including the apparent
   two-byte prefix, all 1,760 interior bytes and five-byte trailer. Do not
   copy a template, reorder slices or set coordinates for a foreign carrier.
3. The native compiler's mode-1 lane must keep the block byte-identical while
   allowing only separately-proven strings, capacity, manager link and a
   validated fixed-row roster transaction. The regression test
   `test_native_compiler_writes_mode1_safe_core_and_fine_role_lanes_in_fixed_carrier_slots`
   asserts exactly that preservation.
4. A future promotion requires both: (a) trace the later game consumer from a
   loaded mode-1 block to a named player object, and (b) run a fresh-game
   control in which one source player, one resolved tactical slice and one
   visible pitch/line-up location agree. Until then, historical foreign
   formations are source data for review only, not database writes.
