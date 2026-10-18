# First foreign-carrier UI discovery: F.C. Barcelona (2026-08-29)

## Positive result

The normal PM99 new-game preseason UI can identify a foreign carrier without
guessing from its EQ record number, record order or mode byte.

In a disposable, untouched-executable run, the following actual UI route
selects F.C. Barcelona:

1. Open the Europe preseason map.
2. Select the Spain flag at the observed PM99 screen point `67,250`.
3. Select the red-and-blue F.C. Barcelona kit tile at `27,382`.

The game visibly names **Spain** and **F.C. Barcelona** in
`mode1_preseason_barcelona_probe_20260829/screens/20_select_barcelona_kit.png`.
After assignment it visibly names **F.C. Barcelona** and **Camp Nou** in
`mode1_preseason_barcelona_probe_20260829/screens/21_assign_rival1.png`.

The indexed EQ reader identifies F.C. Barcelona as `EQ` record 1 in the
same database.  This gives one evidence-backed registry row:

| EQ record | Country UI | Club UI | Ground UI | Evidence state |
| ---: | --- | --- | --- | --- |
| 1 | Spain | F.C. Barcelona | Camp Nou | fresh-game preseason screen |

## Boundaries

This is discovery evidence only.  It does **not** prove a Spanish league
membership table, a competition name, a safe membership write, a manager
link/name write, a kit asset mapping, or opening tactics.  In particular, the
preseason kit tile is a useful club identity surface but does not tell us which
`KIT*.PKF` asset belongs to the carrier.

Coordinates are a runner fixture for this exact 640×480 game screen, not a
data format.  Future country-registry tests must record their own visible
club/country/competition result and may not infer the rest of the map from
this one row.
