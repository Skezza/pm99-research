# PM99 `dd6360` Native Fine-Role Window — 2026-08-30

## Correction — 2026-10-04

The interpretation below is superseded. Direct disassembly of all 26 current
season executables proves that the loader consumes one byte **and skips a
second byte** after the two native strings. Roles occupy `name_end +2..+7`,
not `+1..+6`. At `0x004afe58..5b` the first loaded role is copied to the initial
profile label. This applies to both native indexed player families. The
loader slice at `0x004afd80`, length `0x106`, has SHA-256
`10706290f7d31d3d65cd583767599a498decf422f46e919191c06f154fbd8ba2`
in every registered executable. The older apparent role outlier was caused by
reading the skipped byte as a role; it is not grounds for modifying that byte.

The bounded writer is now `app/indexed_jug_roles.py` in the canonical editor.
Historical roster audits are in `scripts/season_historical_roster_audit_v1.py`;
they explicitly do not certify August ownership from season appearances.

The following sections are retained as the historical record of the mistaken
interpretation, not as the current byte contract.

## Decision

The compact indexed player family (`dd6360`) has a six-byte fine-role window
which starts **one byte after** the end of its second native compact string.
The byte at the compact-string end and the byte immediately following the
six-slot window are controls, not positions. Both remain preserve-only.

This supersedes the previous cursor interpretation for compact fine roles. It
does not alter the established metadata offsets after that window.

## Native evidence

The remote `GhidraMCP` project, program `MANAGPRE.EXE`, was inspected on the
PM99 runner. `FUN_004afd80` reads a compact player as follows:

1. It consumes the two compact native strings beginning at decoded payload
   byte 8.
2. It consumes one following byte as a control value.
3. It loops six times over the next byte, decoding zero as `98` (unassigned)
   and a non-zero encoded value as `value - 1`, into the fine-role array.
4. It consumes a second control byte before nationality and the remaining
   visible metadata.

`FUN_004b13f0` loops across the populated role array to calculate role
scores. The first array position is not a semantic primary role.
The role labels are the existing 18-label table at `0x00735340`.

## Corpus evidence

Read-only audit of the fixed PM99 `JUG98030.FDI` corpus found 9,353 compact
`dd6360` rows. The six-byte window contains valid role codes `0..17` and
unassigned `98`, with one pre-existing legacy outlier (record `29795`, code
`254`). That one record is reported and preserved rather than normalised.

Run the audit with:

```bash
PYTHONPATH=upstream/pm99-skezmod-db-editor:. \
python3 scripts/audit_dd6360_native_cursor.py \
  --player-file <DBDAT/JUG98030.FDI> \
  --output <audit.json>
```

The audit is intentionally read-only. It reports structural parser failures
as failures and reports legacy role outliers separately.

## Product and compiler guardrails

- The browser/editor variable-name writer now retains the complete compact
  native suffix byte-for-byte when a variable-length compact name changes.
  It no longer invents an eight-byte pseudo-role block.
- The compact mode-1 compiler accepts one to six candidate role codes
  (`0..17`) and rewrites the complete six-byte window. Missing candidates are
  encoded as the native zero/unassigned value. It preserves the two adjoining
  control bytes byte-for-byte.
- A compact mode-1 player whose existing role window contains any value other
  than `0..17` or `98` is rejected by the compiler. It must be preserved or
  replaced with a compatible carrier; a historical update must never silently
  erase the exceptional value.
- `probe_mode1_player_variable_name.py` now proves that the six decoded
  fine-role values are identical before and after a compact variable-name
  rebuild.

## Scope

This closes the compact role-byte layout and writer contract needed for world
database work. The editor exposes the values as six **tactical-role
candidates**, not a primary/secondary hierarchy: PM99 computes the displayed
role and percentages itself. The remaining release requirement is a
whole-package runtime sweep, not more field-layout research.
