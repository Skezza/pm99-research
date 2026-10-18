# Mode-1 manager-link contract and cursor correction (2026-08-29)

## Result

The existing final `EQ -> ENT` manager ID is the live manager association for
the modern 700-byte mode-1 carrier layout, just as it is for mode 0. It is
safe to replace that one existing four-byte ID when the replacement ENT record
exists. The count and all preceding IDs must remain unchanged.

This is runtime-proven with F.C. Barcelona:

1. Its carrier (EQ record `1`) has one final manager ID, ENT `1069`, which
   parses as `Van Gaal`.
2. A same-length ENT surname mutation, `Van Gaal` -> `Test Mgr`, changed only
   the eight name bytes and the fresh game's Barcelona dashboard visibly showed
   `Test Mgr`.
3. A separate EQ mutation, `1069` -> `1641`, wrote only the existing four-byte
   manager-ID span. ENT `1641` is `Hiddink`, and the fresh dashboard visibly
   showed `Hiddink`.

The first test proves the profile/name association. The second proves manager
relinking. Both runs retain the remote OverlayFS root and a checksum receipt,
so the screenshots are tied to the exact files mounted into Wine.

Two indexed variable-length rebuild controls also close the manager surname
contract:

1. ENT 1069 (`dd6360`) grew from 17 to 22 bytes when `Van Gaal` became
   `Long Test Mgr`; the game displayed Long Test Mgr.
2. Barcelona was relinked to full-profile ENT 731 (`dd6361`). Its payload
   shrank from 65 to 58 bytes while surname `Teddy Sheringham` became
   `Tester Name` and its separate display-name segment became `Long Test
   Name`. The dashboard displayed Tester Name. All 555 unrelated ENT payloads
   and the profile's 22-byte prose tail were preserved exactly.

This demonstrates that the dashboard consumes the first surname segment in
both manager record families. It does not give the second full-profile
display-name segment its own edit contract.

## The corrected cursor

An intermediate note incorrectly reported Barcelona's manager ID as `52` and
then tested ENT record `22`. That was a cursor error, not a game finding: it
missed the four fixed bytes after the third club string in the mode-1 common
header.

For Barcelona's stored raw EQ payload:

- record size: `700`; mode: `1`;
- post-header mode-1 link base: `0x6b`;
- link-count byte: `0x6b + 0x6e7 = 0x752`, value `1`;
- active manager ID: four bytes at `0x753`, value `1069`.

ENT record `22` was indeed changed to `Test Manager!!` in a retained control
run and the dashboard correctly stayed on `Van Gaal`: record 22 was never the
linked manager. That negative result is useful only as a proof that the former
cursor was wrong. It does **not** disprove the real mode-1 manager lane.

## Evidence

| Purpose | Receipt / visible screen |
| --- | --- |
| Correct manager profile | `mode1_barcelona_manager_ent1069_kept_20260829/mutation-receipt.json`; `screens/30_pretransfer_inspect_02.png` (`Test Mgr`) |
| Exact ENT database input | `mode1_barcelona_manager_ent1069_kept_20260829/dbdat_override.sha256` (`ENT98030.FDI` SHA-256 `8656cbfe…b8e05`) |
| Correct manager relink | `mode1_barcelona_manager_link_kept_20260829/mutation-receipt.json`; `screens/30_pretransfer_inspect_02.png` (`Hiddink`) |
| Exact EQ database input | `mode1_barcelona_manager_link_kept_20260829/dbdat_override.sha256` (`EQ98030.FDI` SHA-256 `50ea9a2b…b1321`) |
| Variable surname rebuild | `mode1_barcelona_manager_variable_name_kept_20260829/mutation-receipt.json`; `screens/30_pretransfer_inspect_02.png` (`Long Test Mgr`) |
| Full-profile rebuild | `mode1_barcelona_manager_full_profile_kept_20260829/name-mutation-receipt.json`; `screens/30_pretransfer_inspect_02.png` (`Tester Name`) |
| Whole-corpus structural check | [`PM99_MODE1_MANAGER_LINK_AUDIT_2026-08-29.json`](../../PM99_MODE1_MANAGER_LINK_AUDIT_2026-08-29.json): 451 mode-1 carriers, all final IDs resolve to parsed ENT profiles |

The runtime artifacts live under
`artifacts/stars_player_offer_probe/`; their `dbdat_override.sha256` receipts
are produced by the runner immediately after its full OverlayFS hash check.

## Corpus shape

The machine-readable audit reports all 451 mode-1 carriers as structurally
valid. Link-list lengths are: 438 x 1, 10 x 2, 2 x 3 and 1 x 4. The last ID is
the active one. The list shape may not be resized or reordered; preceding IDs
remain preserve-only until their historical semantics are researched.

## Safe scope and remaining limits

- **Green:** read every existing mode-0/mode-1 final manager link; replace an
  existing final ID with an existing ENT ID; preserve count and preceding IDs.

- **Green:** variable-length surname rebuilds in both ENT manager families.
  Rebuild the indexed directory; reparse it; preserve every non-target payload
  and the full-profile display/prose tail.
- **Red:** full-profile display-name edits, biography/career prose, and Club
  Personnel attributes. These have no individual screen/write contract.

The manager-link and manager-surname gates are now closed. The full-profile
display-name and manager-biography gates remain deliberately open.
