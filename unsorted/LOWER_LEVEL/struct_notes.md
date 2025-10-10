# JUG98030.FDI Header Observations (preliminary)

Hex dump (first 0x80 bytes):

```
0000: 44 4d 46 49 76 31 2e 30 00 00 00 00 00 00 00 00  DMFIv1.0........
0010: d7 2c 00 00 02 00 00 00 00 ff 46 02 00 53 00 00  .,........F..S..
0020: 00 04 00 00 00 00 52 47 02 00 47 00 00 00 05 00  ......RG..G.....
0030: 00 00 00 99 47 02 00 4e 00 00 00 06 00 00 00 00  ....G..N........
0040: e7 47 02 00 4c 00 00 00 07 00 00 00 00 33 48 02  .G..L........3H.
0050: 00 4b 00 00 00 09 00 00 00 00 7e 48 02 00 4f 00  .K........~H..O.
0060: 00 00 0a 00 00 00 00 cd 48 02 00 48 00 00 00 0c  ........H..H....
0070: 00 00 00 00 15 49 02 00 51 00 00 00 0d 00 00 00  .....I..Q.......
```

* `0x0000` – ASCII signature `DMFIv1.0`, matching the loader expectation in `MANAGPRE.EXE.FUN_004a0a30()`.
* `0x0010` – `0x00002CD7` (11479 decimal). Candidate for total record count (club-wide player entries) referenced by `FUN_004b57b0()` when sizing arrays.
* `0x0014` – `0x00000002`. Appears in the loader path as the FDI “type/version” discriminator that controls optional segments (values ≥2 trigger extended record parsing).
* `0x0018` – `0x0246FF00`. This matches the offset table the game reads just after the header; `FUN_004a0a30()` compares entry offsets against the largest of the first two values before scaling to seconds (see the `fVar7 = (float)local_34c * _DAT_006f7248` line).
* `0x001C` – `0x00005300`. Likely byte size of the first directory block (0x5300 = 21248), immediately followed by an index.

The repeating pattern from `0x0020` onwards lines up with the structure parsed in `FUN_004a0a30()`:

```
struct OffsetEntry {
    uint32 data_offset;
    uint16 payload_id;   // e.g. 0x47 = 'G', 0x4E = 'N'
    uint16 entry_index;  // 0x0004, 0x0005, ...
}
```

Each triplet (offset, letter code, sequential counter) mirrors the decode loop’s expectation: the loader reads a `uint32` offset, a `char`/`uint16` tag that becomes an identifier (“G”, “N”, “L”, “O”, “H”, “Q”, …), and a small integer that ends up in the `param_1[...]` structures after decryption.

## Header unpack check (Python quick test)
A short script (`py -c`, see Terminal 1) unpacked the first twelve `<uint32, uint16, uint16>` triplets at offset `0x20`, yielding:

```
count=11479 version=2
00: offset=0x00000400 tag=0x0000 idx=18258
01: offset=0x00470002 tag=0x0000 idx=5
02: offset=0x99000000 tag=0x0247 idx=19968
03: offset=0x06000000 tag=0x0000 idx=0
04: offset=0x000247e7 tag=0x004c idx=0
05: offset=0x00000007 tag=0x3300 idx=584
06: offset=0x00004b00 tag=0x0900 idx=0
07: offset=0x487e0000 tag=0x0002 idx=79
08: offset=0x000a0000 tag=0x0000 idx=52480
09: offset=0x48000248 tag=0x0000 idx=3072
10: offset=0x00000000 tag=0x4915 idx=2
11: offset=0x00000051 tag=0x000d idx=0
```

The mixed endianness appearance matches the loader behaviour in [`MANAGPRE.EXE.FUN_004a0a30()`](MANAGPRE.EXE:0x004a0a30): each `<IHH>` tuple is read as LE before scaling/dispatch. The seemingly garbled `tag`/`idx` values correspond to the ASCII identifiers written as `uint16` (e.g., `'G' == 0x0047`) and their LE sequence numbers (`0x0004`, `0x0005`, …). Negative-looking offsets (e.g., `0x99000000`) reflect that the raw directory values are further normalised by subtracting the base `fdiDirOffset` inside the loader.

## Next verification step
Use these header offsets alongside the decoded buffers (`decode_data_xor61`) to:

1. Confirm that the offsets (e.g., `0x02475200`, `0x024E0000`) point into the file’s record region.
2. Validate lengths and counts by comparing the decoded record length returned by the XOR routine with the raw segment size in the file.
3. Cross-check the decoded strings using the provided `HW-Charmap.map` to ensure character encodings (especially accented names) are interpreted correctly.

## Sample entry decode (offset 0x000410)

Python probe:

```
entry @0x000410 len=649
encoded head: 00 4c 00 00 00 89 00 00 00 00 37 8a 02 00 4a 00 ...
decoded head: 61 2d 61 61 61 e8 61 61 61 61 56 eb 63 61 2b 61 ...
```

Interpretation:

- Entry prefix `len=0x0289` (649) matches the first non-zero length in the sequence and lines up with the tag `0x4c` (“L”) from the directory tuple.
- XORing all bytes with `0x61` reproduces the decoded payload just as [`MANAGPRE.EXE.decode_data_xor61()`](MANAGPRE.EXE:0x004b6a50) does (length word consumed, result null-terminated).
- The decoded text renders as high-ASCII characters under Windows-1252; pass through [`HW-Charmap.map`](HW-Charmap.map) before drawing conclusions about accented glyphs.

## Hex validation snapshot (offset 0x000410)

Command trace (Terminal 1) dumped the first 128 bytes before/after XOR 0x61:

```
encoded first 128
0000: 00 4c 00 00 00 89 00 00 00 00 37 8a 02 00 4a 00 .L........7...J.
0010: 00 00 8a 00 00 00 00 81 8a 02 00 52 00 00 00 8b ...........R....
0020: 00 00 00 00 d3 8a 02 00 51 00 00 00 8d 00 00 00 ........Q.......
0030: 00 24 8b 02 00 49 00 00 00 8f 00 00 00 00 6d 8b .$...I........m.
0040: 02 00 23 0a 00 00 90 00 00 00 00 90 95 02 00 48 ..#............H
0050: 00 00 00 92 00 00 00 00 d8 95 02 00 47 00 00 00 ............G...
0060: 93 00 00 00 00 1f 96 02 00 50 00 00 00 94 00 00 .........P......
0070: 00 00 6f 96 02 00 4f 00 00 00 96 00 00 00 00 be ..o...O.........

decoded first 128
0000: 61 2d 61 61 61 e8 61 61 61 61 56 eb 63 61 2b 61 a-aaa.aaaaV.ca+a
0010: 61 61 eb 61 61 61 61 e0 eb 63 61 33 61 61 61 ea aa.aaaa..ca3aaa.
0020: 61 61 61 61 b2 eb 63 61 30 61 61 61 ec 61 61 61 aaaa..ca0aaa.aaa
0030: 61 45 ea 63 61 28 61 61 61 ee 61 61 61 61 0c ea aE.ca(aaa.aaaa..
0040: 63 61 42 6b 61 61 f1 61 61 61 61 f1 f4 63 61 29 caBkaa.aaaa..ca)
0050: 61 61 61 f3 61 61 61 61 b9 f4 63 61 26 61 61 61 aaa.aaaa..ca&aaa
0060: f2 61 61 61 61 7e f7 63 61 31 61 61 61 f5 61 61 .aaaa~.ca1aaa.aa
0070: 61 61 0e f7 63 61 2e 61 61 61 f7 61 61 61 61 df aa..ca.aaa.aaaa.

decoded preview (CP1252)
a-aaaèaaaaVëca+aaaëaaaaàëca3aaaêaaaa²ëca0aaaìaaaaEêca(aaaîaaaa
êcaBkaañaaaañôca)aaaóaaaa¹ôca&aaaòaaaa~÷ca1aaaõaaaa÷ca.aaa÷aaaaß
```

The decoded stream remains non-ASCII because the underlying record is numeric data serialised as characters; lookup through [`HW-Charmap.map`](HW-Charmap.map) is expected to map these high-byte glyphs into meaningful league/stat abbreviations, matching the behaviour inferred from [`MANAGPRE.EXE.decode_data_xor61()`](MANAGPRE.EXE:0x004b6a50).

## Player record reverse-engineering (MANAGPRE.EXE)

Preliminary mapping extracted from [`FUN_004afd80()`](MANAGPRE.EXE:0x004afd80) and [`FUN_004a0370()`](MANAGPRE.EXE:0x004a0370):

- **Record framing**
  - Leading `uint16` length stored in `param_1[0]` (used to bound subsequent parsing).
  - `uint8` region/league code written at offset `0x114`.
  - Two immediate strings decoded via `decode_data_xor61`:
    - `param_1[2]`: given name block (truncated to ≤0x0D in cache).
    - `param_1[3]`: surname block.
- **Name/club initials**
  - Six bytes processed through a decrement-and-wrap loop populate offsets `0x1d..0x22` (likely initials/club identifiers).
  - Offsets `0x25`, `0x1a..0x1c`, and `param_1+7` capture nationality/position metadata.
- **Birth data**
  - Sequence of bytes/`uint16` placed at offsets `0x48`, `0x121`, `0x11e`; helper clamps year into 1990–1999 range using `FUN_004c2830`.
- **Attributes**
  - Bytes streamed into offsets `0xcf..0xe6`, `0xd1..0xd7`, `0xe1..0xe6` (core skill stats).
  - Version check (`param_5 >= 700`) enables extended fields at `0x117..0x11b`, `param_1+0x46..0x47`.
- **Optional blocks**
  - When club code equals `0x26ac`, a further decoded blob is stored at `param_1[4]`; otherwise, length-prefixed segments are skipped.
  - Additional `len + data` blocks skipped via `*piVar3 = *(ushort *)*piVar3 + 2 + *piVar3` loops (likely historical stats, contracts).
- **Fallback logic**
  - If height/weight values fall below thresholds, the loader synthesizes defaults via `FUN_004c2830`.
  - For early builds (`param_5 < 600`) the function defers to [`FUN_004a0370()`] which iterates through extra legacy segments before advancing the record pointer.

Action items:
1. Capture real decoded samples (using `out/decode_one.py`) and align each byte range with observed offsets.
2. Trace how DBASEPRE.EXE consumes the struct (e.g., [`FUN_00416dc0()`](DBASEPRE.EXE:0x004179a2)) to confirm semantics (name, nationality, skills).
3. Formalize the structure into a typed schema for the editor module.
## TEXTOS.PKF entry decode (offset 0x000000)

Terminal 1 dump confirms the PKF entries reuse the XOR helper:

```
encoded first 128
0000: 85 fb dc 20 0b 43 30 1f 10 03 f8 a7 15 f1 e0 50  ... .C0........P
0010: c4 a3 e8 01 00 00 00 00 00 00 00 04 e8 00 00 00  ................
...
decoded first 128
0000: e4 9a bd 41 6a 22 51 7e 71 62 99 c6 74 90 81 31  ...Aj"Q~qb..t..1
0010: a5 c2 89 60 61 61 61 61 61 61 61 65 89 61 61 61  ...`aaaaaaae.aaa
...
decoded preview (CP1252):
äš½Aj"Q~qb™Æt1¥Â‰`aaaaaaae‰aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
```

The leading length word (`0x8ae1` = 35585) matches the decoded block size plus one byte for the routine’s terminator, matching [`MANAGPRE.EXE.decode_data_xor61()`](MANAGPRE.EXE:0x00677e30). High-byte glyphs again indicate data that needs the engine’s custom charset mapping. Capture these before/after dumps in `verify.txt` alongside the FDI sample to complete Phase 5 evidence.

## TEXTOS.PKF header probe

Initial 0x100-byte dump of `DBDAT/TEXTOS.PKF` (Terminal 1) reveals a non-zero preamble followed by zero padding:

```
0000: 01 8b 85 fb dc 20 0b 43 30 1f 10 03 f8 a7 15 f1
0010: e0 50 c4 a3 e8 01 00 00 00 00 00 00 00 04 e8 00
...
00f0: e6 c4 23 11 07 7f 31 29 3b f8 a7 15 f1 e0 17 c8
```

`FUN_004c1090()` expects a PKF header containing a directory count, followed by an array of `{offset,size}` pairs and optionally an XOR-encoded name table. The leading 0x20 bytes align with the loader’s initial reads (multiple dword loads prior to the decode loop), while the large zero span corresponds to the directory block allocation before it is filled. The footer at `0x00f0` matches the first encrypted entry metadata read by the same XOR helper (`decode_data_xor61`). A quick dword probe showed the apparent “entry count” at `0x0010` as `0xA3C450E0`, which is clearly bogus until the XOR transform is applied—another confirmation that the PKF header itself must be decoded before parsing offsets.

Next steps:

1. Append these before/after dumps to `verify.txt` (Phase 5 deliverable) with context.
2. Repeat the procedure for a TEXTOS.PKF entry to confirm the same XOR path feeds the text resources.
3. Continue documenting struct interpretations in this file before moving on to the extractor stub and cross-binary triangulation.