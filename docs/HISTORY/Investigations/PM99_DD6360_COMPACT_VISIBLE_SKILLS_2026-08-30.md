# PM99 compact `dd6360` visible skills — 2026-08-30

## Decision

The compact indexed player family has ten named player-profile skill inputs.
The tenth is **Handling**, not an unknown trailing byte.  Two other inputs
are shared by two labels in the game UI:

- one byte drives both Fitness and Heading;
- one byte drives both Moral and Tackling.

This is a family-specific contract.  It must not be applied to `dd6361` or an
opaque player family merely because their bytes are nearby.

## Ghidra evidence

`MANAGPRE.EXE` `FUN_004afd80` is the compact player loader.  Once it has read
the native name strings, control byte and six role candidates, its instructions
at `0x004b0026..0x004b00ed` copy ten consecutive decoded bytes into the player
object.  The profile renderer at `0x0042ecd0` reads those object members under
the labels below.

| Compact decoded offset from `role_start` | Player member | Game profile label |
| ---: | ---: | --- |
| `+18` | `+0xcf` | Speed |
| `+19` | `+0xd0` | Stamina |
| `+20` | `+0xd1` | Aggression |
| `+21` | `+0xd2` | Quality |
| `+22` | `+0xd7` | Fitness and Heading |
| `+23` | `+0xd6` | Dribbling |
| `+24` | `+0xd5` | Passing |
| `+25` | `+0xd8` | Shooting |
| `+26` | `+0xd4` | Moral and Tackling |
| `+27` | `+0xd3` | Handling |

All values are stored as `decoded_value ^ 0x61` in the indexed payload.

## Runtime controls

### Full-core distinct-value control

An existing compact player was given deliberately distinct values through the
nine core bytes.  The PM99 profile showed, in order, `Speed 91`, `Stamina 92`,
`Aggression 93`, `Quality 94`, `Fitness 95`, `Moral 99`, `Passing 97`,
`Dribbling 96`, `Heading 95`, `Tackling 99`, and `Shooting 98`.  This is the
runtime confirmation of both shared pairs, not just a disassembly inference.

Evidence:

- `.local/research-probes/dd6360-kanu-full-core-ui-20260830/receipt.json`
- `.local/research-probes/dd6360-kanu-full-core-ui-20260830/analysis/stats-zoom.png`

### Isolated Handling control

The accessible compact Kluivert fixture (JUG `1802`, temporary visible name
`T TEST`) was used for an isolated one-byte control:

| Field | Before | After |
| --- | ---: | ---: |
| Handling (`role_start + 27`) | 10 | 77 |
| All other JUG bytes | unchanged | unchanged |

The runner mounted the altered file with a hash receipt and opened PM99's real
transfer/profile screen.  The screen visibly shows `HANDLING 77`; its other
profile skills retain their original values.  The driver marked the run failed
only because OCR read `T TEST` as `rEST`, not because PM99 failed or because a
profile was absent.  The screenshot is the authority.

Evidence:

- `.local/research-probes/dd6360-kluivert-handling-runtime-20260830/mutation-receipt.json`
- `.local/research-probes/dd6360-kluivert-handling-runtime-20260830/artifacts/dbdat_override.sha256`
- `.local/research-probes/dd6360-kluivert-handling-runtime-20260830/artifacts/screens/45_profile_only_t_test_done.png`

## Released writer rule

1. Resolve the compact native cursor from the two XOR/u16 strings.
2. Preserve the role/control block byte-for-byte except through its dedicated
   role writer.
3. Write the nine established core inputs at `+18..+26`.
4. Write Handling only when the package explicitly supplies it, at `+27`.
5. If a historical package has no Handling source, preserve the carrier's
   existing value and record that omission; do not use a generic player tail.

The season compiler, Python editor path and browser binary path implement this
layout and carry regression coverage for an isolated Handling-only mutation.
