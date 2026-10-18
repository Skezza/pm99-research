# PM99 foreign competition pre-name-copy blocker (2026-08-30)

## Result

No foreign membership or carrier data was changed.  The available read-only
traces still prove only that PM99 can resolve a scheduled `???` Champions
League opposition to existing EQ carrier 2151 (Valletta), then copy that
carrier's displayed identity into generated fixtures.  They do **not** locate
the candidate-pool source, a pre-name-copy selected-id slot, or a writable
membership contract.

This investigation adds two precise negative controls rather than extending
that result beyond its evidence.

## Ghidra availability check

The approved GhidraMCP health wrapper reaches the remote service, but the
project inventory is presently internally inconsistent for `MANAGPRE.EXE`:

- `list_programs` lists `/PM99/MANAGPRE.EXE` and
  `/PM99_SKEZMOD/MANAGPRE.EXE`.
- `manage_project get_program_info` returns `resource_not_found` for both
  exact paths.
- The standard health script also stops early because `/PM97/MANAGER.EXE`
  cannot be opened.

The new read-only probe deliberately makes **no** static inference when that
happens.  Its remote report was written to
`/home/joe/pm9x-lab/logs/pm99-foreign-competition-ghidra-20260830.json`.
The stale inventory is not proof that an executable analysis exists; it blocks
the requested Ghidra call-chain work until the project is repaired or
reimported through the approved tooling.

## Local static negative control

The local, unmodified `MANAGPRE.EXE` used by the English 2015/16 playable
build has SHA-256
`de50fcb9b0572e720ac0167d2d66d26bc8c82f974ec97759341691fc10cd145e`.
Read-only `objdump` of the runtime watch addresses shows:

- `0x004b1340` reads a word at its input `+0x18`, then passes it to
  `0x004b5c20`.
- `0x004b5c20` binary-searches a sorted table whose comparison value is at
  candidate `+0x10`; it can inspect carrier 2151 while looking for another id.
- The caller subsequently bounds its computed result between `0x28` and
  `0x63` (40 and 99).  The same function is invoked from general
  calculation/presentation paths.

Together with the captured runtime stack argument `0x080f` (2063), this
confirms the prior watch hit at `0x004b5c4b` is a generic lookup traversal.  It
cannot be promoted to an assertion about the `???` draw resolver, fixture
selection, or foreign membership.

The reproducer is
`scripts/probe_pm99_competition_lookup_static.py`; it reads only the supplied
executable and prints the preserved instruction windows and checks.

## Why no new live run was launched

The approved route-capture interface presently captures named/hex memory only
after a Fixtures calendar click, which is **after** the draw has materialised
fixture text.  Its only pre-draw debugging hook resolves a known carrier name
and watches that carrier object's ID dword.  The current hook therefore either
records the generic lookup above or no access; it cannot capture a candidate
selection slot.  Re-running it would duplicate a known negative result rather
than test membership safely.

## Required next probe

After Ghidra is repaired, add a runner-owned, read-only two-boundary capture:

1. Snapshot relevant writable PM99/Wine allocation ranges while the empty
   `competition_round_screen` is paused, before the Continue action.
2. Capture the same ranges immediately after that one action, before the
   calendar fixture text is opened, and rank only newly allocated or changed
   blocks that contain a valid loaded-carrier pointer or known record id.
3. Use the static caller chain to attach a bounded write watch to a *verified*
   changed selected-id field, then demonstrate its population from the `???`
   state.

Only if that trace identifies an actual database-backed membership source may
a disposable, reversible one-record transaction be considered.  Until then,
foreign topology and carrier ordering remain baseline-preserved.
