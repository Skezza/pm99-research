# PM99 Stars database-only contract (2026-08-28)

## Decision

The historical-database programme must repair the `Stars` slot in the
database.  It must **not** depend on a permanent `MANAGPRE.EXE` crash guard.
The older guard is useful diagnostic hardening, but it is not the content fix.

For a 2015/16 release, the ten `Stars` roster slots will subsequently be
reused for ten real, opening-date free agents.  That is a data-curation step;
the contract here establishes that the carrier itself is safe first.

## Root cause, checked in Ghidra

`Stars` is the indexed EQ record with id `9900` (`0x26AC`).  MANAGPRE treats
that id as a special case and bypasses its normal team lookup.  The special
path supplies the player record's `+0x10` club-text field, which is empty for
these records.

The generic text routine at `FUN_0066F1F0` loads that pointer into `ECX` at
`0x0066F1FB` and executes `MOV AL, byte ptr [ECX]` at `0x0066F208` before it
can take the game's ordinary empty-string branch at `0x0066F243`.

That is a **null-pointer dereference**.  It is not a failure caused by
Valderrama's name, nationality, photo, or rating.

## Database repair

1. Change only the indexed EQ directory id for the linked `Stars` record from
   `9900` to unused safe id `9899`.  The record remains a non-club carrier;
   its roster and unknown payload bytes stay intact.
2. Resolve the roster from that EQ record, rather than a hard-coded player
   list.  Every linked JUG payload must be at least 80 decoded bytes.
3. Rebuild JUG's indexed offsets and payload lengths after padding.  Preserve
   each short payload's existing final decoded byte as filler.
4. Do not patch the executable for this proof.

The investigated database had seven short linked JUG payloads:

| Player id | Before | After |
| ---: | ---: | ---: |
| 8425 | 72 | 80 |
| 17126 | 70 | 80 |
| 20863 | 66 | 80 |
| 20864 (Valderrama) | 73 | 80 |
| 20865 | 72 | 80 |
| 20866 | 64 | 80 |
| 20867 | 63 | 80 |

## Disposable build receipt

` .local/research-probes/stars-db-only-20260828` is a copy of the English
2015 build used only for this proof.  The source and probe `MANAGPRE.EXE`
SHA-256 values are both:

`de50fcb9b0572e720ac0167d2d66d26bc8c82f974ec97759341691fc10cd145e`

The repair changed the EQ id to `9899`; all ten linked player payloads now
reparse at 80 bytes or more.  The detailed receipt is local-only at
`.local/research-probes/stars-db-only-20260828/stars-db-only-repair.json`.

## Runtime proof (complete)

The untouched executable now opens the exact profile surface for all ten
linked records.  The machine-readable receipt is
[`PM99_STARS_DB_ONLY_RUNTIME_AUDIT_2026-08-29.json`](../../PM99_STARS_DB_ONLY_RUNTIME_AUDIT_2026-08-29.json):
10 of 10 cases pass the live-window, no-crash, terminal-phase, screenshot and
profile-title checks.

Carlos Muñoz is deliberately included as a non-trivial guardrail.  His compact
search key is the non-unique `Carlos`, so the run scrolls to and opens the
exact `CARLOS Muñoz Cobos` row; it does not claim success for the first Carlos
result.  The screenshot is retained at
`artifacts/stars_player_offer_probe/stars_db_only_carlos_munoz_r11_20260829/screens/86_profile_only_carlos_munoz_done.png`.

The separate offer route also completed through Carlos Valderrama with the
same untouched EXE:
`artifacts/stars_player_offer_probe/stars_db_only_valderrama_offer_20260829`.
The actual contract screen is visible at `58_inspect_ready_to_submit.png`; the
post-submit screen returns to the repaired Stars roster at
`60_inspect_post_submit.png`, with no crash or Wine debugger.

This completes the carrier repair.  It does not automatically approve the
later historical content decision: the ten slots still need sourced 2015
opening-date free agents and a photo/no-photo disposition before they are
used in a release.

### Evidence rule added during the proof run

An automation process reaching its final step is not profile proof. The game
can remain on the search dialog when a query is not a stored PM99 name.
`scripts/audit_stars_db_only_runtime.py` therefore requires all of the
following for every slot: successful process, a live window, no crash, the
expected terminal step, a profile screenshot, and the expected player token
in the profile-title OCR.

The runner key helper now accepts explicit `CP1252:NN` character tokens. This
is required for authentic searches such as `HERNÁNDEZ`, `MUÑOZ` and `SOÑORA`;
UTF-8 key text was not faithfully delivered to the 1999 ANSI game. Queries
must use the compact primary name the game indexes, not blindly the longer
display string. If it is not unique, the test driver must inspect and select
the correct result row rather than calling the first result a pass.

Only after this completed probe may the ten slots receive sourced 2015
free-agent records and portrait/no-photo decisions.
