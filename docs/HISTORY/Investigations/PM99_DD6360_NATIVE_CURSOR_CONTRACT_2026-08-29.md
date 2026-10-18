# `dd6360` native player cursor contract (2026-08-29)

## Decision

`dd6360` player records must use the native `MANAGPRE.EXE` cursor. The old
generic `PlayerRecord` marker cursor is not a player-metadata cursor and must
not be used to read or write nationality, date of birth, physicals, roles or
skills for this family.

This closes the **structural cursor** question for `dd6360`.  It now also has
the required two-shape foreign runtime proof for the named visible metadata
lanes: nationality, date, height, weight and the profile's ten stored skill
bytes. The compact role window is separately proved. A family-aware product
writer is still required before the browser editor can use a field; the
structural cursor alone is not permission to write arbitrary bytes.

## Format

After the record id/signature/header bytes, `MANAGPRE.EXE` parses two compact
strings beginning at decoded payload offset `8`:

1. a two-byte little-endian length, with each length byte XORed by `0x61`,
   followed by the surname bytes;
2. the same form for the full display name.

The end of the second string is the native role cursor. The following bytes
are the player stream used by the game:

| Native offset | Meaning/status |
| ---: | --- |
| `+0` | opaque control byte; preserve |
| `+1..+6` | six fine-position candidates; zero is represented by `0`, otherwise the game stores role code + 1 |
| `+7` | opaque control byte; preserve |
| `+8` | visible nationality code |
| `+9` | unknown control byte; preserve |
| `+10` | parser position code |
| `+11` | visible position code |
| `+12..+13` | day and month |
| `+14..+15` | little-endian birth year |
| `+16..+17` | height cm and weight kg |
| `+18..+26` | nine named post-cursor skill bytes; `+22` is the shared Fitness/Heading value and `+26` the shared Morale/Tackling value; see the compact visible-skill contract for the complete mapping |
| `+27` | Handling; named tenth profile-skill byte |

The field/control status above is about storage. It is not permission to edit
the `+0`, `+7`, `+9` or any unnamed byte.

## Broad-position UI proof (2026-08-30)

The two stored broad-position bytes are not merely parser labels.  A fresh,
unmodified-executable foreign runtime control used Patrick Kluivert (Barcelona,
JUG `1802`) and changed **only** decoded native offsets `+10` and `+11` from
`3` (Forward) to `0` (Goalkeeper).  His six tactical-role candidates,
nationality, date, physicals, all ten profile values and every other JUG byte
were retained exactly.

The PM99 profile opened normally and visibly showed **GOALKEEPER** while still
showing the separately derived `ROL. Centre Forward`.  That deliberately
inconsistent result is useful evidence: the two broad-position bytes control
the profile's headline position, and the tactical-role candidate window is a
separate game surface.  The game did not crash or show an error modal.

- mutation receipt:
  `.local/research-probes/mode1_kluivert_broad_position_g_20260830/position-receipt.json`;
- hash-checked runner summary:
  `.local/research-probes/mode1_kluivert_broad_position_g_20260830/summary.json`;
- visible profile:
  `.local/research-probes/mode1_kluivert_broad_position_g_20260830/screens/47_profile_only_kluivert_goalkeeper_done.png`.

This closes the compact mode-1 **broad-position** lane.  A historical compiler
must write a compatible broad position and tactical-role candidate set together
when it has sourced both; it must not make the intentionally contradictory
control above into production data.

## Why the generic result was wrong

The generic parser finds a run that looks like its marker after the second
string. In this corpus that marker is three bytes later for 6,487 records and
four bytes later for 2,866 records. It therefore consumes real position and
control bytes as if they were framing.

Patrick Kluivert (JUG id `1802`, Barcelona) makes the error obvious:

| Reader | Nationality | Birthday | Height/weight |
| --- | ---: | --- | --- |
| obsolete generic cursor | `1` | 7 / **184** / 1975 | 175 / unset |
| native cursor | `27` | 1 / 7 / 1976 | 187 / 78 |

The latter matches Kluivert. Josep Guardiola (id `34`) is the gap-3 control:
the native read gives 18 January 1971, 180 cm/76 kg and the expected nine
skill bytes.

## Static executable evidence

In `MANAGPRE.EXE`, `FUN_004afd80` is the loader path used for this record
family. It calls the compact-string reader at `0x00677e30` twice
(`0x004afdc5` and `0x004afde8`), preserves the leading control byte, then
reads six consecutive bytes into the fine-position fields at
`0x004afe2e..0x004afe54`, and preserves the following control byte. This agrees with the
cursor derived from the decoded record and is direct Ghidra evidence that the
cursor follows the second compact string, not the later generic marker.

## Corpus receipt

`scripts/audit_dd6360_native_cursor.py` is read-only and generated
[`PM99_DD6360_NATIVE_CURSOR_AUDIT_2026-08-29.json`](../../PM99_DD6360_NATIVE_CURSOR_AUDIT_2026-08-29.json)
against the 2015/16 research baseline.

| Result | Count |
| --- | ---: |
| `dd6360` records | 9,353 |
| Gap-3 native-cursor matches | 6,487 |
| Gap-4 native-cursor matches | 2,866 |
| Native cursor structural failures | 0 |
| unresolved legacy birth-year encodings | 2 |

The two exceptions are JUG ids `28453` (Delfim José Fernandes; native year
`777`) and `29678` (Nelson Leonel Alves; native year `764`). Their day/month,
roles and other bytes remain readable, but their birth-year encodings are
preserve-only until a separate runtime/Ghidra contract explains them.

## Mode-1 runtime mutation proof

The two foreign cursor shapes have been proved without changing the
executable.  Each disposable probe changed exactly the 16 approved native
metadata bytes (nationality, day/month/year, height/weight and nine skills),
and left every other JUG byte unchanged.  The game then showed the deliberately
obvious values in the real offer/profile screen.

| Fixture | Native gap | Visible game result |
| --- | ---: | --- |
| Patrick Kluivert, Barcelona, JUG 1802 | 4 | Spain, age 49, 6 ft 6, 15 st 8 and all visible skills 99 |
| Josep Guardiola, Barcelona, JUG 34 | 3 | Holland, age 49, 6 ft 6, 15 st 8 and all visible skills 99 |

The machine receipt is
[`PM99_DD6360_MODE1_RUNTIME_AUDIT_2026-08-29.json`](../../PM99_DD6360_MODE1_RUNTIME_AUDIT_2026-08-29.json),
which passes 2/2. The screenshots are retained at:

- `artifacts/stars_player_offer_probe/dd6360_native_kluivert_20260829/screens/55_profile_only_patrick_kluivert_done.png`
- `artifacts/stars_player_offer_probe/dd6360_native_guardiola_20260829/screens/48_profile_only_josep_guardiola_done.png`

Both probe `MANAGPRE.EXE` files retain SHA-256
`de50fcb9b0572e720ac0167d2d66d26bc8c82f974ec97759341691fc10cd145e`.

## Product and compiler guardrails

1. Move `dd6360` facts to a family-aware native reader/writer. Do not patch
   offsets produced by the generic `PlayerRecord` parser.
2. Keep ids `34`, `1802`, `28453` and `29678` as regression fixtures.
3. Fail closed on the two birth-year exceptions and on an unresolved compact
   string cursor.
4. Preserve the `+6..+7`, `+9` and all unnamed/raw bytes byte-for-byte.
5. The gap-3 and gap-4 foreign player proofs are complete for nationality,
   broad position, date, height, weight and the compact profile skills. The
   six-role writer has its own runtime proof; retain separate promotion gates
   for historical role sourcing and every unnamed byte.

## Mode-1 variable player-name proof

The compact names are not fixed-byte labels. A disposable foreign-player probe
used the product's staged indexed writer to rebuild Patrick Kluivert's
`dd6360` compact stream (JUG `1802`, gap `4`) as `T TEST`.

- The native role cursor moved by 15 bytes inside the same 70-byte payload;
  the writer rebuilt the compact prefix, role block and tail padding rather
  than overwriting a text-sized window.
- The indexed directory still contained 11,479 entries and all 11,478
  unrelated JUG payloads were byte-for-byte identical.
- The remote runner mounted the rebuilt JUG hash
  `5c78f4dcd57f7553aaa6bc02433d134a8fd1bd7216173981b94f359a62fe69b4`.
- PM99's actual offer/profile screen identifies the player as `T TEST` while
  retaining F.C. Barcelona as his club and Forward / Centre Forward as his
  game data.

Evidence:

- `.local/research-probes/mode1-barcelona-kluivert-variable-name-v2-20260829/mutation-receipt.json`
- `artifacts/stars_player_offer_probe/mode1_kluivert_variable_name_20260829/dbdat_override.sha256`
- `artifacts/stars_player_offer_probe/mode1_kluivert_variable_name_20260829/screens/48_profile_only_t_test_done.png`

This promotes a **dd6360 native-window name writer**, not arbitrary player
name growth. The new native compact strings must end at or before the old role
cursor; an overlong name is rejected rather than moving unknown data. `dd6361`
and opaque player families retain their separate gates.
