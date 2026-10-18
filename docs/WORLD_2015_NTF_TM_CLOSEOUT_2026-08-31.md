# 2015 world dated-source closeout (2026-08-31)

The final source/package pass combines the 682-club FootballSquads capture,
81 National Football Teams captures, and 48 explicitly matched Transfermarkt
detailed-squad supplements.  It does not write PM99 binaries or database
records.

## Coverage

The canonical integrated draft now has 362 source-ready fixed carriers out of
451, with 7,680 selected immutable slots.  This is an increase from 302
source-ready carriers and 6,539 slots before the Transfermarkt supplement.
The integrated source capture contains 763 clubs and 22,545 player rows.

The 89 remaining carriers are represented by
`world-2015-tm-unresolved-carrier-dispositions-20260831.json`:

* 21 `partial-sourced-prefix-preserved-native-tail`: every sourced prefix is
  retained with primary/supplemental URL and SHA-256 provenance; the remaining
  slots explicitly preserve the native carrier tail as no-photo/unresolved,
  with no invented identity;
* 54 `genuinely-unresolved-no-dated-source`: the next action is to acquire a
  dated source and perform an exact country-constrained binding;
* 14 `genuinely-unresolved-selector-capacity-conflict`: the next action is to
  resolve the existing selector conflict with a distinct same-country source
  or an explicitly reviewed lower-tier source.

The receipt enumerates all 89 IDs and each exact next action.

## Recomputed downstream receipts

The player reconciliation reports 3,887 FIFA fallback-required rows.  The
existing policy is preserved: unmatched FIFA rows remain editorial fallback
rows and receive no invented, averaged, or zero rating.  Broad role demand
for the selected 7,680 slots is G 766, D 2,788, M 2,580, F 1,546.

The updated mode-1 role audit has 362 selected carriers and 32 recycle demands
(fine roles 0:9, 4:14, 9:9); all 32 received an exclusive allocation.  The
allocation-remapped asset manifest has 7,680 globally unique final player
carrier IDs.  It remains source-only and not release-ready: 451 kits still
need era sources and portrait/no-photo review remains explicit.

Receipts:

* `world-2015-tm-integrated-source-capture-20260831.json` — SHA-256
  `f1ea58b98877513df808061228c1e86bc9eeb2bf9a4014fa2de41f49a7e1e2bc`;
* `world-2015-tm-integrated-source-carrier-draft-20260831.json` — SHA-256
  `5b06838a9f042b4674a9b036fcb8988ea7c2a456bb452dcc0cf203717c025a8e`;
* `world-2015-tm-integrated-source-player-reconciliation-20260831.json` — SHA-256
  `c1ce4e2dcaef86219e447dcd632b232d17d8b66ce875f20d3c18c54d4c507451`;
* `world-2015-tm-integrated-mode1-recycle-allocation-20260831.json` — SHA-256
  `4a905e6f551cf0ad23f5dc9c048dd468684f5c340a41418b6f70fb7ef6732dc8`;
* `world-2015-tm-integrated-asset-candidate-manifest-20260831.json` — SHA-256
  `0a4ed8d13a4fb88f84513a6a918ecdc02ec09f73dc458a552a71a93ac7faf124`;
* `world-2015-tm-unresolved-carrier-dispositions-20260831.json` — SHA-256
  `9aa13ee298dd33a9bbcde6f6eea332346836a4688048570f934e54087f1e8eb1`.
