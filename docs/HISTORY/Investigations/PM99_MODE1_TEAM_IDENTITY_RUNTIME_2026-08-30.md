# Mode-1 foreign team identity: variable strings and capacity

## Result

The full visible identity of an existing mode-1 foreign EQ carrier is safe to
rewrite in place: short club name, ground name, full club name and seated
capacity.  The identity strings are genuinely variable length; rebuilding the
indexed container updates offsets correctly.  The terminal foreign roster
table stays byte-for-byte unchanged.

This is a content contract for an existing carrier only.  It does not write a
country, division, competition, draw pool or league-size field.

## Static and Ghidra evidence

- `MANAGPRE.EXE!FUN_004b57b0` formats and opens `dbdat\\eq98%03u.fdi`
  (format literal at `0x73524c`) before loading the indexed external-team
  records.
- The parser-backed EQ layout has two layers: the indexed outer XOR is removed
  for its compact variable-string stream, while the visible metadata and the
  terminal JUG roster graph are read from the outer-encoded payload.
- `scripts/build_2015_english92_release.py::_rewrite_eq_strings` adjusts the
  inner total length and all three string lengths.  The compiler then rebuilds
  the indexed container rather than relying on stale offsets.

## Disposable runtime probe

Input carrier: `EQ 1`, the existing Spanish Barcelona carrier.

| Field | Baseline | Probe value |
| --- | --- | --- |
| Short name | `F.C. Barcelona` | `F.C. Barcelona 2015` |
| Ground | `Camp Nou` | `Camp Nou 2015` |
| Full name | `Fútbol Club Barcelona` | `Futbol Club Barcelona 2015` |
| Seated capacity | `120000` | `99354` |
| Payload length | `2010` | `2025` |

The receipt is
`.local/research-probes/mode1-team-identity-barcelona-20260830/receipt.json`.
It confirms record mode/size stay `1`/`700` and the terminal roster-tail hash
remains exactly `b59d4318beffccacee9c4ee9eb696f3b496417b54ffec3ddd143fbdaa9421c8c`.

A fresh-game runner route selected the existing Spain flag and its first
existing tile.  The game showed **F.C. Barcelona 2015** in the live picker
and reached the club dashboard with `crash_detected: false`:

`.local/runlogs/mode1-team-identity-barcelona-20260830/mode1-team-identity-barcelona-20260830/screens/19_spain_tile_382_0.png`

## Release guardrails

1. Write only an existing mode-1 EQ record and keep its record ID/order.
2. Use CP1252 text, non-empty and at most 255 bytes per identity string.
3. Reparse all four changed fields after the rebuild.
4. Preserve the exact terminal roster bytes unless performing the separately
   proven complete foreign-graph roster transaction.
5. Keep foreign finance and opening tactics preserve-only.
