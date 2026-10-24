# Stock kit fallback follows the logical club

Research checkpoint: 2026-10-24, Vostro, session
`01a0592d-fcd5-7262-a637-743a8253d9b4`.

Some foreign clubs have the wrong stock kit because their season roster occupies
a different native club slot. Preserving that slot's original bitmap preserves
the old club's colours. Matching the game's palette does not detect this error.

The confirmed example is Internazionale in the 2000/01 release. It occupies
carrier 225, which belonged to Perugia in the clean game. Its inherited compact
kit images are exactly Perugia's red/white records. The clean Inter records are
at carrier 213. The runner's original Gimmelli profile displays the bitmap stored
at the current club's carrier, confirming the route from database to image.

For a declared stock fallback, use the clean game's kit for the same logical club
when that identity is unique and the bitmap record fits. Read donors from the
immutable clean archives, so swaps cannot overwrite subsequent donors. Preserve
source-backed season kits and every untargeted record. Do not claim that a stock
kit is an authenticated kit for the target season.

The frozen audit identifies 322 candidates across 25 main seasons and five in the
current legacy 2015/16 release. The original 2015 backup is excluded. These are
kit candidates with their own stable identifiers, separate from the player
duplicate checklist. Missing stock matches are explicit gaps, not permission to
guess a donor.

The 2000/01 prototype remaps 18 clubs in `MINIESC.PKF`, `NANOESC.PKF` and
`RIDIESC.PKF` using the existing bitmap-copy and visual-patch APIs. Independent
readback confirms each target equals its clean donor and every untargeted bitmap
is unchanged. Full A/B game inventories and raw recipe bytes match. Player and
club databases, managers, portraits, palette and executable remain unchanged.
At this checkpoint the prototype is built and byte-verified, but not installed or
runtime-approved. A fresh Inter profile is required before promotion.

Evidence is under
`.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/`:

- `kit-seed-misassignment-review-v1/combined26-stock-kit-remap-candidate-checklist-v1.json`
- `kit-seed-misassignment-review-v1/2000-r224a-prototype-v1/actual-r235-ab-independent-qa-v1.json`
- `2015-kit-stock-carrier-audit-v1/2015-r202-current-stock-kit-seed-mismatch-audit-v1.json`

This is a correction to stock asset assignment. It does not establish that every
previously reported contrast or rendering problem has the same cause.
