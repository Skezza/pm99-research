# World 2015/16 final source package closeout (2026-08-31)

This is the source-only handoff after merging the 81-club supplemented NTF
capture with the additional Luxembourg and Northern Ireland dated captures.
It does not write PM99 databases, executable files, or proprietary assets.

## Recomputed result

The canonical fixed-carrier registry contains 451 foreign carriers. The final
source draft binds 362 carriers to 7,680 fixed slots. The merged capture holds
89 NTF-bound clubs and 22,571 source rows; 60 of those clubs meet capacity and
29 provide a dated sourced prefix only. The 29 prefixes are explicitly
separated from a preserved native tail: no identity is invented for a missing
tail row and the native no-photo policy remains fail-open.

The player reconciliation retains the existing FIFA16 matching policy:

- exact name and birth date: 3,271
- unique name: 228
- unique name and nationality: 7
- unique surname and birth date: 269
- ambiguous name: 18
- fallback required: 3,887 (no unambiguous FIFA16 row; no rating is invented)

Role demand for the selected 7,680 slots is G 766, D 2,788, M 2,580, F
1,546. The deterministic mode-1 recycle audit allocates 32 carriers. The
allocation-remapped asset manifest confirms 7,680 unique final player
carriers, while portraits and kits remain source candidates rather than
release-ready assets.

## Explicit dispositions

The disposition ledger contains all 89 unresolved carriers:

- 29 `partial-sourced-prefix-preserved-native-tail`: use the recorded source
  URL/hash and prefix rows; preserve the exact native tail count.
- 46 `genuinely-unresolved-no-dated-source`: acquire a dated 2015/16 or 2015
  calendar-year squad and perform an exact country-constrained binding. This
  includes the no-country historical/fantasy carriers, which are not eligible
  for guessed joins.
- 14 `genuinely-unresolved-selector-capacity-conflict`: add a distinct dated
  same-country top-competition selector or explicitly approve a lower-tier
  source. A consumed selector is never reused.

The additional dated NTF work moved eight carriers from no-source to explicit
partial dispositions (Grevenmacher, Jeunesse, Linfield, Crusaders, Glenavon,
Portadown, Glentoran, and Cliftonville). Those captures are intentionally not
promoted to source-ready because their row counts do not fill their fixed
capacities.

## Content-addressed receipts

All JSON outputs are canonical UTF-8 JSON and are reproducible from the listed
scripts. SHA-256 hashes:

| Receipt | SHA-256 |
| --- | --- |
| `world-2015-ntf-complete-capture-20260831.json` | `40afeb9e9b2c50fab3711fda1b0e1884ed53e8a48671b2d52687717aaae6db3a` |
| `world-2015-final-integrated-source-capture-20260831.json` | `7dc1f3ef6f29b002911a875053c7ad02a1cd4d24d23e5c4a79950484c9869153` |
| `world-2015-final-integrated-source-carrier-draft-20260831.json` | `8978313e379cfac8bf1ad2011a971b2418229340aac563697f866a98d26dcf77` |
| `world-2015-final-integrated-source-player-reconciliation-20260831.json` | `a356ba218f3a548e63453c44529ff1756a97f5b6bbacd5d886fb532f17fa8a5f` |
| `world-2015-final-recycle-role-demand-20260831.json` | `bb99ee7cd93d99498fc885ab519eaf916c9e589ab511a3f8448a588b6199058f` |
| `world-2015-final-mode1-recycle-allocation-20260831.json` | `f0fad2f0abf3159a3e8f79906a90d6e2c1a74611a9688e71fad28792fbf2a268` |
| `world-2015-final-allocation-remapped-asset-manifest-20260831.json` | `9c61831cbe0146565e21922c8bcff1e1cfcfb6c9ebb3f6573039e04e2fe3000b` |
| `world-2015-final-unresolved-carrier-dispositions-20260831.json` | `34fcfd19ae1ef0d01a649f84b67bb7c34660b470c9a11bf2845f29171ffb5c00` |

The disposition ledger is the authoritative next-action list. No unresolved
carrier is silently released as a guessed player identity.
