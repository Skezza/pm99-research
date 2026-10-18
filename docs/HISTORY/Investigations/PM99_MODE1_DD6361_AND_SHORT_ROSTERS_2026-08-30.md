# Mode-1 `dd6361` and short-roster contracts — 2026-08-30

## Result

Two former fixed-carrier compiler blockers are closed:

1. The single full-player `dd6361` foreign record, JUG `10958` in
   Kidderminster carrier EQ `3310`, has an isolated byte-preserving core
   writer.
2. Existing mode-1 roster tails with fewer than sixteen rows are valid fixed
   data and are no longer rejected merely for their length.

Neither result changes a country, division, competition, roster length, row
order, row flag, shirt number, role candidate set, finance or tactics state.

## `dd6361` evidence and guardrail

`JUG 10958` is `dd6361`, length 891. A disposable mutation changed only its
visible core profile lanes: nationality, broad position, date of birth,
height, weight and nine visible skill bytes. It retained:

- the original two-byte indexed-payload preamble;
- the payload length;
- all six raw fine-role bytes; and
- every other byte.

The receipt is
`.local/research-probes/mode1-dd6361-bignot-core-20260830/core-receipt.json`.
It records the fifteen changed payload offsets and the before/after decoded
facts.

The runner completed a clean game startup and reached the player-search route
without a Wine debugger or game crash. Bignot is not exposed by PM99's
transfer-search result set, so the probe correctly records that as an
unavailable profile-route assertion rather than falsely claiming OCR profile
proof. The database-load and byte-accounting proof remain valid.

The compiler writer round-trips a full-player record untouched before it
permits a mutation. It restores the opaque preamble, preserves the complete
role candidate sequence, rejects any role or shirt-number change, and writes
only the proven core fields. The one record is now a supported family, not a
release blocker.

## Short fixed rosters

PM99's untouched database has valid mode-1 linked tails smaller than sixteen
rows. The previous compiler lower bound was therefore its own mistaken
restriction. The rule is now:

- mode 0 (playable English records): 16 to 255 rows;
- mode 1 (fixed passive/background records): 1 to 255 rows, always preserving
  the existing row count unless an already-proven complete-graph transaction
  explicitly replaces IDs.

The synthetic compiler test covers a 14-row mode-1 carrier. The production
registry's 14-, 15-, 11-, 10- and 1-row passive tails now pass the structural
length contract when their roster contents are otherwise source-complete.

## Scope

Foreign topology is intentionally preserved, not an unresolved blocker. A
2015/16 world update is an in-place content replacement: countries,
divisions, competition pools, promotion/relegation rules and draw behaviour
remain PM99's existing game mechanics.
