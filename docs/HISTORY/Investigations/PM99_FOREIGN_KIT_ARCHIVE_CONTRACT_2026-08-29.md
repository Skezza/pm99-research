# Foreign carrier kit-archive contract (2026-08-29)

## Decision

The stock game has a direct carrier-keyed **compact UI kit** surface for every
modern club.  It is not a five-archive universal surface.

An asset record is named `EQ96<four-digit EQ carrier id>.BMP`.  The carrier id
is the indexed `EQ98030.FDI` record id, not a country code, roster position or
club-name hash.  The stock archive census is recorded in
[`PM99_KIT_ARCHIVE_COVERAGE_2026-08-29.json`](../../PM99_KIT_ARCHIVE_COVERAGE_2026-08-29.json):

| Archive | Modern carriers present | Mode 0 | Mode 1 | Contract |
| --- | ---: | ---: | ---: | --- |
| `BIGCAMP.PKF` | 80 | 80 | 0 | English-only large artwork; do not create a foreign record here. |
| `BIGESC.PKF` | 91 | 91 | 0 | English-only large artwork; do not create a foreign record here. |
| `MINIESC.PKF` | 543 | 92 | 451 | Carrier-keyed compact UI artwork. |
| `NANOESC.PKF` | 543 | 92 | 451 | Carrier-keyed compact UI artwork. |
| `RIDIESC.PKF` | 543 | 92 | 451 | Carrier-keyed compact UI artwork. |

The one extra record in each compact archive is a non-carrier/dummy record;
it is not a club slot.

## Foreign runtime proof

F.C. Barcelona is `EQ` carrier `1`; Real Madrid is carrier `4`.  A disposable
copy replaced the pixel data for Barcelona's `EQ960001.BMP` with Real Madrid's
`EQ960004.BMP` in exactly the three compact archives.  No archive directory,
name, offset, length, other asset or database byte was changed.

The structural receipt is
[`kit-copy-receipt.json`](../../../.local/research-probes/mode1-barcelona-kit-art-20260829/kit-copy-receipt.json):

| Archive | Target extent | Pixel bytes changed |
| --- | --- | ---: |
| `MINIESC.PKF` | `EQ960001.BMP`, 48×64, 8-bit | 1,648 |
| `NANOESC.PKF` | `EQ960001.BMP`, 24×32, 8-bit | 414 |
| `RIDIESC.PKF` | `EQ960001.BMP`, 17×20, 8-bit | 149 |

The normal untouched-executable preseason route selected **Spain** and then
**F.C. Barcelona**.  The selected Barcelona tile visibly changed from its
stock blue/red shirt to the copied white Real Madrid shirt:

- baseline: `artifacts/stars_player_offer_probe/mode1_preseason_barcelona_rival1_20260829/screens/19_select_barcelona_kit.png`
- patched: `artifacts/stars_player_offer_probe/mode1_barcelona_foreign_kit_20260829/screens/19_select_barcelona.png`
- runner mount hashes: `artifacts/stars_player_offer_probe/mode1_barcelona_foreign_kit_20260829/dbdat_override.sha256`

The patched run completed its Kluivert profile route as well, so the asset
change did not prevent a fresh game from progressing.

## Safe scope

A world compiler may replace an existing carrier's compact UI artwork only
when all of these are true:

1. the carrier already exists in all three compact archives;
2. the replacement is an exact valid PM99 bitmap shape/palette for that
   archive record;
3. the writer changes only the target bitmap extent in each archive and
   rereads every target record; and
4. it writes the three compact archives as one asset transaction.

This is enough for the compact selection/squad-style kit surface.  It is not
permission to manufacture `BIGCAMP`/`BIGESC` foreign records, to claim a
separate home/away model, or to claim that a 3D match kit has been proved.  A
future 3D or large-art surface needs its own field-specific game proof.

`scripts/patch_carrier_kit_art.py --archive-set foreign-ui` is the constrained
research helper.  Its default `--archive-set all` remains only for an English
carrier that already has all five stock archive records.
