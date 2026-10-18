# World 2015 exact conflict-source closeout (2026-08-31)

This receipt records the next acquisition pass over the 14 selector/capacity
conflicts. Ten exact, country-scoped Transfermarkt squad pages pinned to
`saison_id/2015` were acquired and bound to their matching PM99 carriers:
Perugia (225), Empoli (250), Hertha (421), Lokeren (871), Westerlo (872),
Trelleborgs (960), Zürich (1111), Young Boys (1112), Boston United (3326),
and Chorley (3330). Each is an alternate source selector retained alongside
the existing FootballSquads/NTF capture; no source selector or identity is
reused.

The source-ready count therefore rises from 362 / 7,680 slots to 372 / 7,919
slots. The 10 captured pages contain 366 parsed player rows, all meeting the
immutable carrier capacities. The remaining four selector conflicts are the
English non-league carriers Bishop A. (3327), Blyth S. (3328), Buxton (3329),
and Colwyn B. (3331); their exact 2015 Transfermarkt pages do not expose a
dated squad table. They remain blocked pending a stable dated source.

## Recomputed package

The player plan has 7,919 unique selected slots. Role demand remains runtime
qualified and the deterministic recycle lane now allocates 36 carriers. The
allocation-remapped asset manifest is still source-only: kits need era sources
and portrait candidates need identity-safe era approval. No PM99 binary or
executable was written.

The full unresolved ledger now has 79 rows:

- 29 partial sourced-prefix / preserved-native-tail rows;
- 46 genuinely no-dated-source blockers;
- 4 genuinely selector-capacity conflicts (the four English clubs above).

The 29 partial rows retain exact URL/hash provenance and a native no-photo tail
count. No player identity or rating is invented for any tail or fallback row.

## Content-addressed receipts

| Receipt | SHA-256 |
| --- | --- |
| `world-2015-conflict-source-capture-20260831.json` | `932848380e57051ea163d058c96e1b1dee54be76acdd88fed89d7865183801d1` |
| `world-2015-conflict-integrated-source-capture-20260831.json` | `8036b725d1cd3f0aeb242189a1c74d27e07ccc49523da1a89ac28673f5cbb88c` |
| `world-2015-conflict-integrated-source-carrier-draft-20260831.json` | `6cf83b8dc6616e14e0a135c689f4c6483e3eb4072022a645df6352fddf818a15` |
| `world-2015-conflict-integrated-source-player-reconciliation-20260831.json` | `d7b7b8e88a626bcccf86fd1cf72666d36ff97a66eefcca4aef9066b6ed807145` |
| `world-2015-conflict-recycle-role-demand-20260831.json` | `93120316a4c3de2c3d1c6edd5c3d731ab426a5ce843cc1735b1d1e96edd50df6` |
| `world-2015-conflict-mode1-recycle-allocation-20260831.json` | `1956e3c68befa836390569b5e84542b83188e0c00bccab1fb27cf311f6a5f71c` |
| `world-2015-conflict-allocation-remapped-asset-manifest-20260831.json` | `82e493c41420a1aa4febc096a873420f2a572149d264a1c953a306f79e4997ad` |
| `world-2015-conflict-unresolved-carrier-dispositions-20260831.json` | `c12a4c95ff43e485aa2b8d9830d96a21ef89b56510751873b233746b99adff0d` |

The four remaining conflicts have an explicit next action: acquire a dated
2015/16 lower-tier or club archive squad for the exact English club, or
preserve its native carrier tail if no reliable source can be found.
