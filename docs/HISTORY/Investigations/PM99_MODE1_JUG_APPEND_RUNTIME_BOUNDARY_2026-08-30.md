# PM99 foreign JUG append runtime boundary (2026-08-30)

## Decision

Fresh compact (`dd6360`) JUG records are **not release-safe** for a PM99
foreign (`mode 1`) roster.  The season compiler must reject them, even if an
EQ roster tail is structurally valid and all fixed row counts and flag bytes
are preserved.

This does not affect the separately-proven English `mode 0` `dd6361`
25-player append route.

## Why this was tested

The 451 existing foreign roster tails contain 9,390 player occurrences but
only 9,354 distinct JUG IDs.  A true one-person-per-historical-player graph
would need to resolve the 36 pre-existing duplicate allocations.  Appending
a compact clone looked like the least invasive possibility, so it was tested
before being made available to a release package.

## Disposable controls

Both controls started from the corrected English 2015/16 materialisation and
changed one existing Barcelona (`EQ` carrier 1) row only.  They cloned JUG
16, kept the row's flag and terminal count exact, rebuilt the indexed JUG
directory, and used a unique visible name.

| Control | Fresh JUG ID | Search result | Selecting the result | Result |
| --- | ---: | --- | --- | --- |
| High-ID append | 33,366 (one above the current maximum) | `APPEND PROBE` appears with a full rating row | PM99 shows `Application cannot continue.` | Rejected |
| Low-ID append | 1 (unused below the current minimum) | `APPEND ONE` is not listed | No player profile can be reached | Rejected |

The high-ID screenshot is
`.local/runlogs/world2015-jug-append/mode1_jug_append_barcelona_20260830/screens/51_profile_only_append_probe_done.png`.
It visibly shows the search row and the native PM99 error modal.  The low-ID
search screenshot is
`.local/runlogs/world2015-jug-append/mode1_jug_append_id1_barcelona_20260830/screens/45_submit_append_one_search.png`.

The initial run exposed a runner defect: its generic "final step reached"
condition reported success without recognising the game's `Application cannot
continue` dialog.  `pm99-runner` now OCR-checks every final profile-only
screen for that modal, and the high-ID control is correctly recorded as
`success: false`, `blocking_error_modal_detected: true`.  Screenshots remain
the runtime authority.

## Interpretation

The results show two distinct behaviours:

- the indexed JUG directory is sufficiently visible for a high fresh ID to
  enter the transfer search list; but
- the player-profile path has another dependency or record invariant that
  rejects that record.

The controls do **not** identify the exact executable data structure.  It
could be a sidecar lookup, a profile-specific record invariant, or a loader
interaction.  Ghidra work is required before drawing a narrower conclusion.

## Compiler guardrail

`scripts/season_package_compiler_v2.py` now rejects a `dd6360`
`append_from_carrier_id` request with a `runtime-blocked` error.  Its
foreign complete-graph transaction remains useful for rearranging existing,
already-addressable JUG records, but it cannot create new compact IDs.

The disposable builder is `scripts/probe_mode1_jug_append.py`.  It is not a
database-editor command and must not be used to produce a season release.

## What must be learned to reopen this route

1. Use Ghidra plus runtime breakpoints around the player-profile lookup to
   identify the extra high-ID dependency.
2. Find the supporting record/table, or prove an existing valid ID range that
   can be extended coherently.
3. Repeat high/low/middle-ID controls, with a native no-photo decision, and
   make the runner treat PM99's error dialog as a failed run.
4. Prove a fresh player in a foreign profile and through a new-game route
   before re-enabling any compiler write path.
