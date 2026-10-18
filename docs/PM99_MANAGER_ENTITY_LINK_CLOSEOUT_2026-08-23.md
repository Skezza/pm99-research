# PM99 manager-to-team research status

`ENT98030.FDI` is the manager-profile store used by modern `EQ98030.FDI`
carriers. It is not the Club Personnel/staff database.

## Proven relationship

Every modern 700-byte EQ carrier contains a count followed by existing
four-byte ENT IDs. The **final** ID is its active manager.

| EQ mode | Carriers | Cursor to manager table | Status |
| --- | ---: | --- | --- |
| `0` | 92 | after the variable English-club metadata block | Runtime-proven by Coventry |
| `1` | 451 | immediately after the shared EQ header | Runtime-proven by F.C. Barcelona |

Mode 1's structural scan is complete: its list lengths are 438 x 1, 10 x 2,
2 x 3 and 1 x 4, with every final ID resolving to a parsed ENT profile. Those
preceding IDs are not editable, reordered or assigned a semantic meaning.

## Runtime evidence

- Coventry, mode 0: replacing final ENT `691` (Strachan) with `1069` (Van
  Gaal) changed the game dashboard to Coventry / Van Gaal.
- Barcelona, mode 1: changing the surname-only ENT `1069` from `Van Gaal` to
  `Test Mgr` changed the fresh Barcelona dashboard to Test Mgr.
- Barcelona, mode 1: changing the final EQ ID from `1069` to existing ENT
  `1641` changed that dashboard to Hiddink.

The Barcelona controls have retained runner roots and OverlayFS checksum
receipts. See
[`PM99_ENT_CROSS_CARRIER_PRESERVATION_2026-08-29.md`](HISTORY/Investigations/PM99_ENT_CROSS_CARRIER_PRESERVATION_2026-08-29.md)
and [`PM99_MODE1_MANAGER_LINK_AUDIT_2026-08-29.json`](PM99_MODE1_MANAGER_LINK_AUDIT_2026-08-29.json).

## What the manager record contains

- 464 `dd6360` surname-only profiles, with one variable-length CP1252
  surname segment; its indexed rebuild is runtime-proven.
- 92 `dd6361` full profiles, with a variable-length surname, a variable-length
  display name and unsegmented biography/career prose. The rebuilt surname is
  runtime-proven; the second display-name segment and prose remain read-only.
- No manager skill, wage, rating or tactical scalar in the traced profile
  contract. Club Personnel attributes are a separate unresearched system.

## Safe contract

- Read all existing final manager IDs in mode 0 and mode 1.
- Replace only an existing final ID with an existing, non-zero ENT ID.
- Preserve the count and every preceding ID byte-for-byte.

- Rebuild the variable-length surname in either manager family with a complete
  indexed directory rewrite and verify all non-target payloads are unchanged.

Do not insert/delete IDs, resize/reorder lists, rebuild a variable-length ENT
display-name segment or touch biography/career prose. Those remain preserve-only
until separately proved in a fresh game.

The browser editor should use
[`manager_entity_field_matrix.json`](manager_entity_field_matrix.json): it may
show the linked manager and read-only profile content, and offer the narrow
relink control above. It must not present Club Personnel staff attributes as
manager fields.
