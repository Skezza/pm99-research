# Loader/decoder cross-reference

| Binary | Role | Key functions | Notes |
| --- | --- | --- | --- |
| `MANAGPRE.EXE` | Primary loader/decode implementation | [`FUN_004a0a30()`](MANAGPRE.EXE:0x004a0a30) – FDI header/parser; [`FUN_004c1090()`](MANAGPRE.EXE:0x004c1090) – PKF directory loader; [`decode_data_xor61()` / `FUN_00677e30()`](MANAGPRE.EXE:0x00677e30) – shared XOR helper | All offsets validated against on-disk records; produces decoded payloads used by the manager UI |
| `DBASEPRE.EXE` | UI/browser for decoded databases | [`FUN_00439eb0()`](DBASEPRE.EXE:0x00439eb0) references `dbdat\eq98030.fdi`; [`FUN_00416dc0()`](DBASEPRE.EXE:0x00416dc0) walks player entries; [`FUN_0043de80()`](DBASEPRE.EXE:0x0043de97) uses `DBDAT\TEXTOS\PAISES.%u` | Uses the same XOR routine via imports; file paths and struct access match the decoded layouts from `MANAGPRE.EXE`, no independent decode reimplementation observed |
| `PM99.EXE` | Launcher only | [`FUN_00401000()`](PM99.EXE:0x00401000) dispatches to MANAGPRE/DBASEPRE/INFO apps | No direct access to `*.FDI` or `TEXTOS.PKF`; serves as entry point launcher |

## Decode routine equivalence

Both MANAGPRE and DBASEPRE import `FUN_00677e30` and call it with the same calling pattern (length word at `[ptr]`, XOR 0x61 applied byte-wise, terminator appended). PM99.EXE does not include the helper; it invokes MANAGPRE/DBASEPRE for any database work.

## Call graph parity

- MANAGPRE: `FUN_004b57b0` → `FUN_004a0a30` → `FUN_00677e30`
- DBASEPRE: navigation routines (e.g., `FUN_00416dc0`) initialize buffers then call the shared helper through the import table rather than re-implementing the decode.
- Both binaries reference identical filename templates (`dbdat\jug98%03u.fdi`, `dbdat\textos\paises.%u`) confirming they consume the same data sources.

```
MANAGPRE.EXE
└─ FUN_004b57b0
   ├─ FUN_004a0a30 → decode_data_xor61
   └─ FUN_004c1090 → decode_data_xor61

DBASEPRE.EXE
└─ FUN_00416dc0 / FUN_0043de80
   └─ decode_data_xor61 (imported)
```

Conclusion: MANAGPRE hosts the canonical loader/decoder; DBASEPRE simply reuses the shared XOR helper on demand, and PM99 remains a thin launcher without direct decode logic.