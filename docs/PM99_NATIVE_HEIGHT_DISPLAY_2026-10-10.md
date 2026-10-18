# Native height display: truncate, do not round

Verified 2026-10-10 on joe-Vostro-3350; source session
`01a0592d-fcd5-7262-a637-743a8253d9b4`.

The original player-profile screenshot for Nemanja Jovšić shows **6 ft 5 in**
with source-bound native height **197 cm**. The old checkpoint expected
`round(197 / 2.54)` (6 ft 6 in) and would incorrectly reject that correct game
display. Do not change the player's centimetre value to satisfy this display.

Read-only disassembly of the candidate MANAGPRE.EXE proves the conversion:

- Function at VA `0x4c26a0` loads the integer centimetre argument.
- At `0x4c26c0`, it multiplies by the double at `0x6fc898`
  (`0.03280839895013123`) and calls `0x6bef40`.
- That thunk jumps through import `0x6e64c4` to MSVCRT `_ftol`, which truncates.
- At `0x4c26dd`, it multiplies the truncated feet by double `0x6fc8a0`
  (`30.48`), subtracts that from the original centimetres, multiplies the
  remainder by double `0x6fc8a8` (`0.39370078740157477`), and calls `_ftol` again.
- The resulting feet and inches are passed to `sprintf`.

Thus the checkpoint now reproduces both truncations. Tests cover 178, 185,
191 and 197 cm, reject a rounded 6 ft 6 in for 197 cm, and reject invalid input.
This is a validator correction, not a native database mutation or a waiver.

Evidence root:
`.local/consolidated-audit-20261009/stock-club-history-v1/`.
Executable: `jedinstvo-2005-complete-source-replay-v2/game/MANAGPRE.EXE`,
SHA256 `13a1424ab88babd2e240ae081ef90af11961fdc0b0bfe18871e8bf5a3c150ef5`.
Original frame:
`runtime/jedinstvo_2005_jovsic_20261010/jedinstvo_2005_jovsic_20261010/screens/45_profile_only_jovsic_done.png`,
SHA256 `f73275d7cf19810736d2c23e4bf05b7c598948b17fba0373dc363819d523b7f2`.
The independently checked 153 interior kit pixels have zero channel error.
The profile's weight, blank portrait and opaque foreign tactics are not
historically approved by this check.

## Unknown native height/weight sentinels are randomised at startup

Verified 2026-10-10 21:27 UTC on the same machine/session. This is a separate
loader rule, not a reason to change the conversion for valid centimetre values.

Borac's first private B. DJURIC14605 record preserved seed height byte140 and
weight byte1, while its actual original runner profile showed5ft8 and11st11.
Read-only disassembly proves why those stored bytes cannot be converted as
literal historical centimetres/kilograms:

- `0x4aff28` loads height into runtime player member `+0x115`.
- `0x4aff3b` tests height against150; values below150 call `0x4c2830(10)`.
- `0x4aff4f` subtracts86 from the returned byte. Byte wrapping makes the
  result170..179cm, replacing the unknown native value.
- `0x4aff57` tests weight against20; values below20 call the same helper and
  `0x4aff6a` adds75, producing75..84kg.
- `0x4c2830` calls imported MSVCRT `rand`, multiplies by the requested bound,
  and shifts right15: `floor(rand()*10/32768)` is0..9. These are runtime
  estimates, not hidden published facts in the database.

The original frame SHA is
72217ab5922efaa61d6db0de72d0c38636adcd6247c72b2072dddea319679e98:
`stock-club-history-v1/runtime/borac_2003_djuric_20261010/borac_2003_djuric_20261010/screens/48_profile_only_djuric_done.png`.
Executable SHA6c164f2b0852d5e91bb0fb32642721961f6e0f15f66c7820a5546fde55ba888c:
`stock-club-history-v1/borac-2003-complete-source-replay-v1/game/MANAGPRE.EXE`.

The first private Borac candidate was not promoted. Its V2 source proposal
uses explicit, reproducible unsourced physical defaults (G185cm/80kg,
D180/76, M178/74, F180/76), labelled as estimates. They are not historical
claims. Published physical facts must never be overwritten by these defaults.
The V2 trial exposed another coupling: the rating model uses supplied height
to adjust heading, changing eight players by one point. That trial was not
delivered. V3 keeps height unpublished (`None`) for rating generation while
writing the explicit physical estimate into the native physical fields.
All ten skills for all18 players now match the original V1 values. Decoded
V1→V3 native records differ only in the two physical bytes per player; all
other records are unchanged. No executable modification was needed.

The ROOT-inspected V3 original Djuric frame shows6ft0, age27, YUGOSLAVIA and
all ten unchanged skills (heading28, handling57). SHA256
`2afd10405672a164e3ead89fad1e8317954279702575851852369b333d669c33`;
`stock-club-history-v1/runtime/borac_2003_djuric_physical_v3_20261010/borac_2003_djuric_physical_v3_20261010/screens/48_profile_only_djuric_done.png`.
All153 interior kit pixels also match with zero channel error. Original
unknown-sentinel and V2 trial evidence remain retained; their source replay
keeps their respective original policies. Final V3 normal startup was also
ROOT-inspected; final promotion/checkpoint is separate from this research note.
