# Premier Manager 99 — Loader & Decode Summary

## Scope

Reverse-engineered the database/text loaders across `MANAGPRE.EXE`, `DBASEPRE.EXE`, and `PM99.EXE` to document how Premier Manager 99 reads `.FDI` and `TEXTOS.PKF` resources. Deliverables include breadcrumbs, decode verification, cross-binary comparison, and a minimal extractor stub.

---

## Key Findings

### Executable Roles
- [`PM99.EXE`](PM99.EXE:0x00401000) — launcher only; no direct decoding.
- [`MANAGPRE.EXE`](MANAGPRE.EXE:0x004b57b0) — canonical loader for FDI databases and TEXTOS packs.
- [`DBASEPRE.EXE`](DBASEPRE.EXE:0x00416dc0) — UI/views that consume decoded buffers via the shared helper.

### Canonical Loader Flow (MANAGPRE.EXE)
| Step | Function (RVA) | Responsibility |
| --- | --- | --- |
| Build filenames `dbdat\jug98%03u.fdi`, etc. | [`FUN_004b57b0()`](MANAGPRE.EXE:0x004b57b0) | Iterates region IDs, orchestrates imports |
| Read FDI header & directory | [`FUN_004a0a30()`](MANAGPRE.EXE:0x004a0a30) | Validates `DMFIv1.0`, loads offset triplets |
| Decode entries | [`decode_data_xor61()`](MANAGPRE.EXE:0x00677e30) | LE `uint16` length + XOR 0x61, null-terminates |
| TEXTOS loader | [`FUN_004c0090()`](MANAGPRE.EXE:0x004c0090) → [`FUN_004c1090()`](MANAGPRE.EXE:0x004c1090) | Opens PKF, XOR-decodes directory payloads |

Call-graph snapshot:
```
FUN_004b57b0
├─ FUN_004a0a30 ── decode_data_xor61 ── FUN_004a0370 / FUN_004afd80
└─ FUN_004c1090 ── decode_data_xor61
```

### Decode Algorithm

`decode_data_xor61()` (shared by MANAGPRE & DBASEPRE):

1. Read LE `uint16 len`.
2. XOR each byte with `0x61` (bulk handled with 32-bit/16-bit ops in binary).
3. Append `0x00`.
4. Return `len + 1`.

Pseudocode (matches [`out/decode_one.py`](out/decode_one.py:1-112)):
```python
length = struct.unpack_from("<H", buf, offset)[0]
encoded = buf[offset+2 : offset+2+length]
decoded = bytes(b ^ 0x61 for b in encoded) + b"\x00"
```

### Filename & Language Patterns
- Databases: `dbdat\jug98%03u.fdi`, `dbdat\eq98%03u.fdi`, `dbdat\ent98%03u.fdi`
- TEXTOS: `DBDAT\TEXTOS\paises.%u`, plus similar `nombres.xx`, `apellidos.xx` packs
- Region/language ID inserted via `%03u` / `%u` (e.g., `030` for English build)

### Struct Notes & Endianness

Confirmed little-endian fields and directory layout via [`out/struct_notes.md`](out/struct_notes.md:1-127):

```c
struct FdiHeader {
    char signature[8];      // "DMFIv1.0"
    uint32_t record_count;  // 0x2CD7 (11479)
    uint32_t version;       // 0x00000002
    uint32_t max_offset;
    uint32_t dir_size;      // first directory block length
    OffsetEntry entries[];  // { uint32 offset; uint16 tag; uint16 index; }
}
```

Offsets verified against `DBDAT/JUG98030.FDI` with Python probes; see measurements and decode snapshots in README + [`out/verify.txt`](out/verify.txt:1-53).

### Cross-Binary Triangulation
[`out/triangulation.md`](out/triangulation.md:1-30) compares implementations. Findings:

- MANAGPRE provides authoritative loader & decode.
- DBASEPRE imports the same XOR helper and reuses decoded buffers in UI routines; no alternate transform discovered.
- PM99 is purely a dispatcher; it never touches game data directly.

---

## Verification Artifacts

- `out/breadcrumbs.csv` — table of file/path strings per executable (binary, string, RVA, xrefs count).
- `out/struct_notes.md` — header layout, offset verification, decode proof for FDI/TEXTOS.
- `out/verify.txt` — before/after hexdumps for FDI (offset `0x000410`) and TEXTOS (`0x000000`) segments, CP1252 previews included.
- `textos_0000.bin` — decoded output produced via `python out/decode_one.py DBDAT/TEXTOS.PKF 0x0 --out textos_0000.bin`; inspecting it in CP1252 surfaces the Portuguese name roster (e.g., “Damian…” through “Dodô…”) confirming the stub reproduces in-game text once the XOR is removed.
- `out/triangulation.md` — summary of loader equivalence across binaries.

---

## Extractor Stub

[`out/decode_one.py`](out/decode_one.py:1-112) emulates `decode_data_xor61`.

Usage examples:

```bash
# Inspect a player entry from JUG98030.FDI
python out/decode_one.py DBDAT/JUG98030.FDI 0x410 --hexdump --preview

# Decode first TEXTOS block to file
python out/decode_one.py DBDAT/TEXTOS.PKF 0x0 --out textos_0000.bin
```

Outputs match in-engine behaviour; append additional parsing once field semantics are expanded.

---

## Recommended Next Steps

1. Expand `decode_one.py` into a directory-aware extractor (iterate offsets/storage per `FUN_004a0a30` logic).
2. Use [`HW-Charmap.map`](HW-Charmap.map) or Windows-1252 conversions to interpret high-byte glyphs.
3. Extend documentation with exact struct field labels as more records are decoded.
4. Integrate `out/verify.txt` data into future automation or regression checks.

---

## Artifact Checklist

| Deliverable | Location |
| --- | --- |
| Breadcrumb table | [`out/breadcrumbs.csv`](out/breadcrumbs.csv) |
| struct verification notes | [`out/struct_notes.md`](out/struct_notes.md) |
| Decode verification (before/after, CP1252) | [`out/verify.txt`](out/verify.txt:1-53) |
| Cross-binary triangulation | [`out/triangulation.md`](out/triangulation.md:1-30) |
| Extractor stub | [`out/decode_one.py`](out/decode_one.py:1-112) |
| Summary README (this file) | [`out/README.md`](out/README.md:1-112) |

All requested outputs reside under `/out`.