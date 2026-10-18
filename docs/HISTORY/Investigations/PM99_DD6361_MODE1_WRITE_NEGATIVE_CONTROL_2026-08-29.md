# Mode-1 `dd6361` write negative control (2026-08-29)

## Result

The only mode-1 roster-linked `dd6361` player is Marcus Bignot (JUG `10958`,
Kidderminster Harriers).  The existing generic `player-edit` CLI can parse his
nationality, height, weight and visible attributes, but it is **not** a safe
writer for this record family.

This is a fail-closed result.  No game runtime claim is made from this mutated
database and no `dd6361` edit is promoted.

## Controlled write

The release-mode CLI was applied to a disposable copy, targeting the exact
indexed payload offset `2746977`:

- nationality `30 -> 27`
- height `178 -> 199`
- weight `71 -> 99`
- visible attribute slots `3..11 -> 99`

It retained the file length (3,842,627 bytes), all 11,479 indexed record IDs,
and the 11,478 unrelated player payloads exactly.  The target record did
reparse with all requested visible values.

However, comparing the decoded target payload found three additional changes:

| Decoded payload offset | Before | After | Status |
| ---: | ---: | ---: | --- |
| `0` | `0x57` | `0x00` | unknown/header, unapproved |
| `1` | `0x61` | `0x00` | unknown/header, unapproved |
| `48` | `0x26` | `0x02` | untraced metadata/control, unapproved |

The other changes were at expected parsed field locations, but the three
unapproved bytes are enough to reject this writer.  A successful reparse is
not a byte-preservation contract.

## Evidence

- Original copy:
  `.local/research-probes/mode1-bignot-dd6361-core-20260829/JUG98030.before.FDI`
- Mutated disposable game file:
  `.local/research-probes/mode1-bignot-dd6361-core-20260829/game/DBDAT/JUG98030.FDI`
- Product CLI result:
  `.local/research-probes/mode1-bignot-dd6361-core-20260829/editor-result.json`

## Rule

`dd6361` player names, metadata, positions and skills remain read-only for
the browser editor and season compiler.  Before changing that decision, a new
family-specific writer must:

1. identify the header and control bytes at offsets `0`, `1` and `48` with
   Ghidra/runtime evidence;
2. patch only approved bytes or rebuild a verified structure that preserves
   every other target-payload byte;
3. pass this Bignot byte-diff control; and
4. show the intended field on Bignot's real PM99 profile after a fresh game.
