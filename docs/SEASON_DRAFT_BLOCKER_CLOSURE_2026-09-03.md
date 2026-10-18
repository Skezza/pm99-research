# Current Season Draft Blocker Closure — 2026-09-03

This receipt records a conservative replay of the 25 current historical
Season Package V2 source drafts (2000/01–2025/26, excluding the separately
released 2015/16 package).  It is a draft-authoring result, not a release,
compile, runtime, screenshot, or playable-game claim.

## Authorised closure

`season_source_package_builder_v1.py` may now resolve one duplicate sourced
person only when a hash-bound opening-fixture claim is the uniquely earliest
dated claim.  Later or undated claims are excluded.  Equal-date claims remain
unresolved.  This uses recorded source chronology only; it does not infer a
transfer date, manager, club alias, or player identity.

The builder continues to preserve unresolved secondary player facts as logged
non-blocking fallbacks.  Formation inference is owned by the later opening
authoring layer, and still requires a reconciled XI.  Manager strings still
require a dated source; native/current-manager fallback remains forbidden.

## Replay result

All 25 immutable `current.json` intake/allocation pointers were verified and
replayed against the matching season registry.  The output consists of 25
`draft-season-package.json` files and 25 source-package audits beneath
`.local/season-authoring-closure-v1/`.

| Measure | Before | After |
| --- | ---: | ---: |
| Unique-earliest opening-fixture identity resolutions | 0 | 87 |
| Safe opening-XI capacity blockers | 4,079 | 3,994 |
| Repeated-source-person identity blockers | 1,196 | 1,183 |
| Source-draft eligible | 0 | 0 |
| Playable | 0 | 0 |

All other aggregate blocker quantities are unchanged: carrier allocation and
identity 799 each; short source squads 285; retained-native conflicts 992;
opening, manager and kit gates 11,150 each; ratings 210,018; calendar
receipts 25.  The draft-category distribution remains 23 seasons with 11
hard-blocker categories and two with 10.

Consequently, no draft may be promoted.  Remaining hard gates include carrier
disposition, full opening-XI/formation integration, sourced managers, kits,
ratings, calendar receipts, strict identity reconciliation, clean compilation,
runtime verification, and screenshots.

## Reproduction

Use `scripts/season_draft_blocker_closure_v1.py`.  The tool verifies the
per-season registry pinned by each current intake, writes drafts/audits only,
and refuses to make any playable or release assertion.

## 2000/01 post-calendar-binding follow-up

The hash-bound 2000/01 calendar overlay was replayed separately using its
exact input pair:

- template draft:
  `.local/season-authoring-calendar-bound-v1/2000-01/draft-season-package.calendar-bound.json`
  (`90ec587fdef276912d7349d6fed538b5460c5b2f16909b85c2bac11c28d1b9d1`);
- overlay audit:
  `.local/season-authoring-calendar-bound-v1/2000-01/calendar-binding-audit.json`
  (`14cc5c84f72904a569f8bd8d7a7d06a1ccb6398392b7d0c591f557f6dd4785ad`).

The builder now accepts this calendar gate only when the audit's season,
template package hash, 1998/853 patch profile, receipt/executable hashes, and
the package's static-contract artifact/proof all agree.  It preserves that
claim through source authoring.  The receipt is
`50c42eb4f5fd9e6a5e34db857409ce5711f91a9176cb60ce926e1e8d7db24dec`; its
executable hash is
`cd065504ea1225d9e29942cbf08fa393f0fe97f7c37a45e7b42482b4681e42a0`.
Runtime validation remains pending and is not treated as a playable claim.

Because this template was itself an older source draft, a current-intake
replay can encounter a source person already present in a later unshared slot.
The deterministic promotion boundary now reserves such a slot only when its
source-person ID exactly matches one selected, source-order current row in the
same carrier.  It never uses a name/date guess, a cross-carrier match, or a
later row that would displace the normal capacity prefix.  This kept the draft
structurally valid while preserving the opening-XI ordering rule.

The resulting provisional artifacts are:

- `.local/season-authoring-post-calendar-binding-v1/2000-01/draft-season-package.json`
  (`0014298d6b0e2a96950a6d9d18467d0e3cd3ee203662ba9249eaa3c75c5b5ffc`);
- `.local/season-authoring-post-calendar-binding-v1/2000-01/source-package-build-audit.json`
  (`845d78e21940c6e3686d19a96e476723b0ef590f5905e32425bb72670cb642fe`);
- `.local/season-authoring-post-calendar-binding-v1/closure-matrix.json`
  (`8ea5df71574212ae3f7b57e4660127ca4827ec5418335364dea219210abd6781`).

The post-binding draft validates the non-release V2 structural contract.  It
is still `release_eligible: false`, has zero playable packages, and must not
be copied or promoted as a canonical package.

| Hard blocker | Before | After |
| --- | ---: | ---: |
| Repeated source-person identity | 113 | 113 |
| Carrier allocation gaps | 63 | 63 |
| Fixed-carrier season identity | 63 | 63 |
| Source squad below capacity | 13 | 13 |
| Safe opening-XI capacity | 167 | 165 |
| Retained native-person candidate conflicts | 1 | 1 |
| Opening lineups | 446 | 446 |
| Target-season managers | 446 | 446 |
| Kit dispositions | 446 | 446 |
| Ratings reconciliation | 7,817 | 7,817 |
| Calendar receipt | 1 | closed |

Thus categories fall from 11 to 10.  The two-opening-XI improvement is the
existing unique-earliest-fixture identity closure, not a calendar effect.  An
intermediate implementation briefly reported 206 XI shortfalls because it
let a later identity-reserved row displace an earlier source-order row.  That
was a replay policy defect, not a data finding; the final policy preserves the
source-order capacity prefix and the reproduced authoritative count is 165.

## Draft-to-canonical promotion boundary

The existing canonical-promotion factory accepts only a byte-identical,
strict-V2 package with an exact calendar-overlay audit.  It can then prepare a
canonical-workspace *candidate* but still cannot compile, run, screenshot, or
release it.  No 2000/01 candidate was made: its provisional output fails
strict V2 on the unresolved same-person opening-date candidate pair
`player-8758` / `player-8771` (`calleelkin`, `1980-05-20`, `COL`).

The reusable, policy-complete closures available from the present hash-bound
inputs are limited to: the exact calendar receipt binding above; a uniquely
earliest dated opening-fixture owner for a duplicate source person; exact
same-carrier source-person slot retention; and explicit
preserve-existing-mode1 fallbacks for secondary player facts.  These never
make the draft release eligible by themselves.

Genuine acquisition or a separate reviewed disposition remains required for
carrier allocation/season identity, short opening-date squads, unresolved
person collisions, opening XIs, sourced target-season manager strings,
continuing-club kits, and ratings.  A formation may be inferred only after a
sourced/reconciled XI exists; it cannot stand in for one.  Once those data
gates and strict V2 pass, the remaining factory gates are a clean binary
compile receipt, independently matching materialised inventories, runtime
validation, and a target-season lineup screenshot.

## 2012/13 calendar binding

The next cached calendar proof was bound to the 2012/13 closure-replay draft
without changing its source, allocation, or authoring inputs.  The provisional
outputs are:

- `.local/season-calendar-bound-batch-v2/2012-13/draft-season-package.calendar-bound.json`
  (`32653fdf25c304d63cccbb32f98e3ab43da623c00d225ddb8e2c938a507dc1c9`);
- `.local/season-calendar-bound-batch-v2/2012-13/calendar-binding-audit.json`
  (`16234e8ab78bafb1f49a03506de94ee9dfa3e67c4c0141f9d8beaa849ae7c16a`).

The audit binds calendar receipt
`ae0bb357ed3d99fe778c5bf4f70d286fa4cbc41934280841af07b6cb1dcf89d8`
to executable
`71c96627d7e6b75a015282fa29d7106bd6d80273eae7acc1726efc485681b4ea`
using the established 1998 base and 853-patch profile.  This removes only the
calendar-receipt category from the downstream bound draft, reducing its open
hard-blocker categories from 11 to 10.  It remains `release_eligible: false`:
runtime calendar validation, all ten source/editorial categories, clean static
compile/audit, runtime route, and bound screenshot evidence are still pending.

## 25-season cached calendar binding replay

The existing 25 replayed source drafts and 25 independently cached calendar
receipts/executables were bound in one fresh, no-overwrite batch at
`.local/season-calendar-bound-batch-v4/`.  The operation made no source,
allocation, canonical-package, release-tree, compile, runtime, or screenshot
change.

- Matrix: `.local/season-calendar-bound-batch-v4/calendar-binding-matrix.json`
  (`8708ad717dc80038659cebd5aed2304abfed78819b5cdd67a57098d476f17565`).
- Inputs: the 25 immutable-style replay drafts under
  `.local/season-draft-replay-v2/`, each paired with its existing
  `.local/calendar-v1/<season>/calendar-receipt.json` and `MANAGPRE.EXE`.
- Outputs: 25 `draft-season-package.calendar-bound.json` files and 25 exact
  `calendar-binding-audit.json` receipts, each with a matching
  `output_package_sha256`.

The matrix records `calendar_bound_draft_count: 25`, `season_count: 25`, and
`playable_count: 0`.  Every row is explicitly
`calendar-bound-provisional-draft`, `release_eligible: false`, and
`runtime_validation_pending: true`.  The 2012/13 output is byte-identical to
the prior independently recorded bound package
(`32653fdf25c304d63cccbb32f98e3ab43da623c00d225ddb8e2c938a507dc1c9`).

This establishes the hash-bound calendar prerequisite for all 25 drafts.  It
does not itself recompute a source-package blocker audit, promote a canonical
package, or close any remaining source/editorial, static-compile, runtime, or
screenshot gate.  A follow-up authoring replay must consume each exact binding
receipt before its calendar hard-blocker category is reported as closed.

## 2000/01 deterministic rating coverage

The current 2000/01 post-calendar-binding-v6 draft was passed to the
deterministic rating-input builder with its current, hash-bound carrier
allocation.  The resulting draft-only authoring receipt is:

- `.local/season-authoring-current-ratings-v1/2000-01/editorial-rating-input.json`
  (`a3aea5fed1c5aca73dea869716806b84ec6c616d7174cbc60e51f502f35d2e27`);
- `.local/season-authoring-current-ratings-v1/2000-01/editorial-ratings.json`
  (`ca165db16ed8b1656c61bb61cfd984d3b94f068b723b385c7c66b67e290e1c8b`); and
- `.local/season-authoring-current-ratings-v1/2000-01/editorial-rating-input-audit.json`
  (`8513f5f4b85f8ee0fecaf8482ae9ffeb82169ea733395221786a55f3316b281f`).

Its inputs are the v6 draft
`26d5e9c74a623034cbf34ec09fd563e53b33b729af00b354b4e163f935e21ba9`
and current allocation
`eb3bd1a71f24c9ac00e7f2bb1210964f00f41e4aa7a8513d1c04958f3eb1e940`.
The established country-strength policy covers 321 assigned clubs and emits
6,707 deterministic editorial ratings.  No opening-XI receipt was supplied,
so the declared snapshot is 2000-08-01 and all 6,707 are explicitly
`opening_squad`, not inferred starters.

The rating builder now records a missing country-strength policy as an
explicit hard blocker rather than aborting at the first country.  It leaves
uncovered players unrated: 62 assignments / 1,109 players across Albania,
Belarus, Bolivia, Cyprus, English non-league, Iceland, Israel, Kazakhstan,
Latvia, Lithuania, Northern Ireland and Wales.  One further player
(`player-3956`) lacks a usable primary position.  No strength was invented,
and the partial ratings output cannot close the draft's ratings reconciliation
gate until those two facts are resolved and the authoring layer is integrated.

This changes no draft package, source pointer, canonical package, release
tree, compile receipt, runtime receipt or screenshot.  2000/01 therefore
remains `calendar-bound-source-draft`, `release_eligible: false`, and
`provisional-not-playable`.

## 2005/06 canonical-workspace candidate

The existing 2005/06 post-calendar-binding-v6 draft was passed through the
fail-closed canonical-promotion factory using only its bound source-build
audit and the existing verified clean-base descriptor.  The completed
candidate is `.local/season-canonical-candidate-v1/2005-06/`.  A second
no-overwrite invocation completed after the first command window and produced
the byte-identical duplicate
`.local/season-canonical-candidate-v1/2005-06-complete-20260903/`; both are
retained without alteration.

Its candidate package is byte-identical to the bound draft
(`900fa34e93c2ccd8d8b4de03a4c64e76083fe34794799b709ae8f18263ecc570`).
Promotion audit
`1cc5fe6073b396b837df478b222c2ac205e25505cad9542f03aef3a080537791`
records passed strict-V2, calendar-binding, verified-base, workspace-contract,
and workspace-prepare checks.  The effective-package SHA-256 is
`19b251b88742b6cea34e59358cc5e1500b406a970bd22fbf6cbe2276addd0e30`.

This is an ingress proof only: it has no compiler materialisation, matching
second inventory, reviewed V2 build plan, runtime route, or target-season
screenshot.  It remains `release_eligible: false` and
`provisional-not-playable`.

## 2005/06 alias-bound static compiler guard — 2026-09-04

The parser-safe display-alias candidate was checked and then submitted once
to the year-neutral compiler against the hash-verified clean 1998 base.  The
candidate workspace check and strict validation of its effective package both
passed; the effective package is
`7f9dbcc7cadcd9c93a9ff9c53d7c60ccac882180f7e1b21e5fff56d3601c9e70`.

The compiler failed closed before writing a database receipt:

```text
mode-1 club carrier 1 changes its fixed roster row count
```

The disposable attempted materialisation is retained at
`.local/season-static-qualification-v1/2005-06-alias-bound-20260904-r4/`.
Its `JUG98030.FDI`, `EQ98030.FDI`, and `ENT98030.FDI` hashes still match the
verified base, respectively
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`,
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`, and
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`.

This creates no compiler receipt, audit, release manifest, runtime proof, or
screenshot and does not change eligibility: 2005/06 remains
`release_eligible: false` and `provisional-not-playable`.  The next smallest
repair is to reconcile carrier 1's package roster allocation with its
parser-backed fixed base-row count, then repeat a fresh no-overwrite static
qualification.

## 2005/06 carrier-1 base-row reconciliation — 2026-09-04

The one-row carrier-1 mismatch was repaired in a new static-only candidate,
using the same hash-verified 1998 base and without changing a source intake,
current manifest, canonical package, release tree, or the 2015/16 release.

- Input alias-bound package SHA-256:
  `3a18a2e1e70dcb85bfb1205bbca8ae54f3537dc47c5b6cd8a8fc419933d7996a`.
- Reconciled package:
  `.local/season-mode1-roster-reconcile-v1/2005-06-carrier-1-20260904/season-package.reconciled.json`
  (`b08b984f0124d7d651468cd7b1d24f3752a8310d91cd3b3dca0c9c1fa87d6482`).
- Reconciliation audit:
  `.local/season-mode1-roster-reconcile-v1/2005-06-carrier-1-20260904/reconciliation-audit.json`
  (`927869d20b5f37ef678b79ca6564dd564eb2ea1468b7838c94132556e0f33a62`).

The repair restores only base player carrier 16, `LUIS ENRIQUE Martínez
García`, in its original first Barcelona roster row.  It is explicitly
`preserve-existing-mode1`, has a parser-read payload SHA-256 of
`9a9870c0b826842923c71b5be8de4e520ed079adb7358c0ddc26be2bedace7ac`,
and has an unresolved/no-photo outcome.  It makes no claim that this retained
baseline row is a dated 2005/06 source fact.

Strict V2 validation passes with 9,178 players and 9,178 portrait outcomes;
Barcelona now has all 26 parser-backed rows in the exact base order.  A fresh
copy-base compiler invocation passed carrier 1 and next failed closed at
carrier 10:

```text
mode-1 club carrier 10 changes its fixed roster row count
```

No compiler receipt was written.  `JUG98030.FDI`, `EQ98030.FDI`, and
`ENT98030.FDI` in the disposable qualification tree remain byte-identical to
the verified base.  Carrier 10 has 23 declared rows versus 30 base rows,
with seven ordered base omissions (`199`, `762`, `2067`, `4960`, `8901`,
`13018`, and `17357`) and no extra or reordered row.

This is static ingress progress only.  The package remains
`release_eligible: false` and `provisional-not-playable`; it has no compiler
receipt, clean audit, runtime route, or screenshot.  The next smallest action
is a separate, fail-closed reconciliation of carrier 10's seven exact base
rows, followed by another fresh static qualification.

## 2005/06 carrier-10 base-row reconciliation — 2026-09-04

Carrier 10 (Sevilla) was reconciled against the same hash-verified clean 1998
base, using the carrier-1 static-only package as input.  The reconciler accepts
multiple omissions only where a selected mode-1 roster has no extra carriers
and its retained rows are the exact parser-backed base order.  It restores
whole base records only; it makes no target-season source, identity, rating, or
portrait claim.

- Input package SHA-256:
  `b08b984f0124d7d651468cd7b1d24f3752a8310d91cd3b3dca0c9c1fa87d6482`.
- Reconciled package:
  `.local/season-mode1-roster-reconcile-v1/2005-06-carrier-10-20260904/season-package.reconciled.json`
  (`08c36d16a2cbbd16f167397633a4770200196cd7a189a4141f9babda723d4d37`).
- Reconciliation audit:
  `.local/season-mode1-roster-reconcile-v1/2005-06-carrier-10-20260904/reconciliation-audit.json`
  (`7f682f8dfc71c89ed54a240addb77b61ed63c4642915ccbf9b931ea9d80bd891`).

The package retains the 23 declared Sevilla rows and restores base carriers
`199`, `762`, `2067`, `4960`, `8901`, `13018`, and `17357` in their original
positions.  Every added row is `preserve-existing-mode1`, uses a
parser-read payload hash, and has a named `unresolved` portrait outcome.  The
result is strict-V2-valid with 9,185 players and 9,185 portrait outcomes;
Sevilla now has all 30 parser-backed roster rows in exact base order.

This remains static ingress progress only.  No source intake, current
manifest, canonical package, binary compiler materialisation, audit, release,
runtime route, or screenshot changed; `release_eligible` remains false and
the delivery state remains `provisional-not-playable`.  The next smallest
action is one fresh, no-overwrite static qualification using this reconciled
package, to reveal or clear the next fixed-carrier guard without making any
runtime or release claim.

## 2005/06 carrier-10 reconciled static qualification — 2026-09-04

The reconciled static-only package was submitted once, directly to the
fail-closed V2 compiler, against the same hash-verified clean 1998 base. The
compiler passed the repaired carriers 1 and 10, then stopped before writing a
compiler receipt at the next exact topology guard:

```text
mode-1 club carrier 1001 changes its fixed roster row count
```

The input package was
`.local/season-mode1-roster-reconcile-v1/2005-06-carrier-10-20260904/season-package.reconciled.json`
(`08c36d16a2cbbd16f167397633a4770200196cd7a189a4141f9babda723d4d37`),
bound by reconciliation audit
`7f682f8dfc71c89ed54a240addb77b61ed63c4642915ccbf9b931ea9d80bd891`.
The disposable no-overwrite tree is
`.local/season-static-qualification-v1/2005-06-carrier-10-reconciled-20260904/`.

The guard left `JUG98030.FDI`, `EQ98030.FDI`, and `ENT98030.FDI` in that tree
byte-identical to the verified base, respectively
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`,
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`,
and `729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`.
No compiler receipt was written.

Parser comparison identifies carrier 1001 as Antalyaspor. Its declared
mode-1 roster retains the exact base order with no extra carriers but omits
only base player carrier `459` (28 declared rows versus 29 base rows). This
is eligible for a separate fail-closed whole-row preservation reconciliation;
it is not evidence of a dated 2005/06 player, ratings, identity, or portrait
fact.

No source intake, current manifest, canonical package, release tree, static
audit, runtime route, or screenshot changed. 2005/06 remains
`release_eligible: false` and `provisional-not-playable`. The next smallest
action is to reconcile just carrier 1001's omitted base player 459 using the
existing preservation contract, then perform one new static qualification.

## 2005/06 carrier-1001 base-row reconciliation — 2026-09-04

Carrier 1001 (Antalyaspor) was reconciled against the same hash-verified
clean 1998 inventory using the carrier-10 static-only package as input. The
nominal clean-base path had diverged, so the reconciler deliberately rejected
it; the repair instead used the existing no-overwrite qualification tree after
`verify-base` confirmed its exact locked inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

- Input package SHA-256:
  `08c36d16a2cbbd16f167397633a4770200196cd7a189a4141f9babda723d4d37`.
- Reconciled package:
  `.local/season-mode1-roster-reconcile-v1/2005-06-carrier-1001-20260904/season-package.reconciled.json`
  (`cf23fc92b85aa1e2becb2941a8bd06438e420d750ee8473fad8a790a81d66c8b`).
- Reconciliation audit:
  `.local/season-mode1-roster-reconcile-v1/2005-06-carrier-1001-20260904/reconciliation-audit.json`.

The package retains the 28 declared Antalyaspor rows and restores base carrier
`459`, `José G. DEL SOLAR Álvarez Calderón`, in its original second roster
position. It is `preserve-existing-mode1`, carries a parser-read payload hash
`987ffe37f747ec4ceeb9c4351ed68ebac991a08b7cd9702876839cfe6c82604b`, and
has a named unresolved/no-photo outcome. Strict V2 validation passes.

This is static ingress progress only: no source intake, current manifest,
canonical package, compiler materialisation, clean audit, release, runtime
route, or screenshot changed. 2005/06 remains `release_eligible: false` and
`provisional-not-playable`. The next smallest action is one fresh,
no-overwrite static qualification using this reconciled package to expose the
next fixed-carrier guard or produce a compiler receipt; it must not make a
runtime or release claim.

## 2005/06 carrier-1001 reconciled static qualification — 2026-09-04

The carrier-1001 reconciled static-only package was submitted once to the
fail-closed V2 compiler.  Before the attempt, the selected no-overwrite base
tree passed `verify-base` against the locked clean-1998 inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

- Input package:
  `.local/season-mode1-roster-reconcile-v1/2005-06-carrier-1001-20260904/season-package.reconciled.json`
  (`cf23fc92b85aa1e2becb2941a8bd06438e420d750ee8473fad8a790a81d66c8b`).
- Disposable no-overwrite materialisation:
  `.local/season-static-qualification-v1/2005-06-carrier-1001-reconciled-20260904-r3/`.

The compiler passed the carrier-1, carrier-10, and carrier-1001 topology
guards, then rejected the next mismatch before writing any database receipt:

```text
mode-1 club carrier 11 changes its fixed roster row count
```

Post-attempt SHA-256 values for `JUG98030.FDI`, `EQ98030.FDI`, and
`ENT98030.FDI` in the disposable tree remain the verified-base values,
respectively `95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`,
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`, and
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`.
No compiler receipt, static audit, release, runtime route, or screenshot was
created.

No source intake, current manifest, canonical package, or the established
2015/16 release changed. 2005/06 remains `release_eligible: false` and
`provisional-not-playable`.  The next smallest action is a separate
single-carrier reconciliation check for carrier 11; it must restore rows only
if the package is an exact in-order base-row omission with no extra carrier,
otherwise it must stop without a repair.

## 2005/06 carrier-11 base-row reconciliation — 2026-09-04

Carrier 11 (Real Sociedad) passed the narrow base-row preservation contract
against the existing hash-verified clean-1998 qualification tree.  The input
package was the carrier-1001 reconciliation
`cf23fc92b85aa1e2becb2941a8bd06438e420d750ee8473fad8a790a81d66c8b`.

- Reconciled package:
  `.local/season-mode1-roster-reconcile-v1/2005-06-carrier-11-20260904/season-package.reconciled.json`
  (`67cce0bf5c131ca81dc75525c2e2e716b253c45a0417437bb2dc472fbde1cc18`).
- Reconciliation audit:
  `.local/season-mode1-roster-reconcile-v1/2005-06-carrier-11-20260904/reconciliation-audit.json`
  (`a41007091990f81a7d1452a261b9de0aa7a8236a35202f01c859f36bf6daac57`).

The candidate retains the 23 declared Real Sociedad rows and restores the two
omitted base rows, carrier `224` (`Francisco Javier DE PEDRO Falque`) and
carrier `2618` (`Ricardo Manuel da Silva SÁ PINTO`), in their original base
positions.  Both are parser-read, whole-record `preserve-existing-mode1`
declarations with named unresolved/no-photo outcomes; neither is a dated
2005/06 source, identity, rating, or portrait claim.  Strict V2 validation
passes with 9,188 players and 9,188 portrait outcomes.

No source intake, current manifest, canonical package, compiler
materialisation, clean audit, release, runtime route, screenshot, or the
established 2015/16 release changed. 2005/06 remains
`release_eligible: false` and `provisional-not-playable`.  The next smallest action is one fresh,
no-overwrite static qualification using this carrier-11-reconciled candidate,
solely to expose the next fixed-carrier guard or produce a compiler receipt.

## 2005/06 carrier-11 reconciled static qualification — 2026-09-04

The carrier-11 static-only package passed strict V2 validation with SHA-256
`67cce0bf5c131ca81dc75525c2e2e716b253c45a0417437bb2dc472fbde1cc18`.
Before compilation, the selected no-overwrite base tree passed `verify-base`
against the locked clean-1998 inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The compiler accepted the repaired carrier-1, carrier-10, carrier-1001, and
carrier-11 roster topology, then stopped before writing a database receipt at
the next fixed-carrier guard:

```text
mode-1 club carrier 12 changes its fixed roster row count
```

The disposable materialisation is
`.local/season-static-qualification-v1/2005-06-carrier-11-reconciled-20260904/`.
Its `JUG98030.FDI`, `EQ98030.FDI`, and `ENT98030.FDI` remain byte-identical to
the verified base, respectively
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`,
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`, and
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`.
No compiler receipt was created.

Read-only parser comparison shows carrier 12 has 25 declared rows against 27
base rows, with no extra carrier and the retained rows in exact base order.
The only omissions are carrier `9229` (Oswaldo Giroldo Junior, JUNINHO) and
carrier `9852` (Mª Romero Poyón, JOSÉ MARI).  This establishes only a possible
preservation-contract repair; it makes no dated 2005/06, identity, ratings, or
portrait claim.

No source intake, current manifest, canonical package, clean static audit,
release, runtime route, screenshot, or the established 2015/16 release
changed. 2005/06 remains `release_eligible: false` and
`provisional-not-playable`. The next smallest action is a separate
single-carrier reconciliation check for carrier 12; it must restore these rows
only if the existing whole-record preservation contract accepts them.

## 2008/09 stale source-candidate ingress preflight — 2026-09-05

One no-overwrite static-ingress attempt for the 2008/09 hash-bound calendar
draft completed its narrow stale-candidate repair stage and then
failed closed before any binary write.  It used the verified clean-1998 base
whose inventory fingerprint is
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

- Input draft:
  `.local/season-calendar-bound-batch-v2/2008-09/draft-season-package.calendar-bound.json`
  (`f54719197f77db006ec4f417a8be0c1ff3a6118ac412aba2160fc58e948ca25a`).
- Reconciled static-only candidate:
  `.local/season-static-ingress-v1/2008-09-20260905-r2/season-package.stale-candidates-reconciled.json`
  (`ee7d5729d15a7c8f6cb5122b461154da459a12ac37a93ae3a5f38dfb9a221248`).
- Reconciliation audit:
  `.local/season-static-ingress-v1/2008-09-20260905-r2/stale-source-candidate-reconciliation-audit.json`
  (`269845b3793010fa2a78bd8c7b98e00200dd89a936cf919f7c06ba7cc7e0e006`).
- Fail-closed preflight receipt:
  `.local/season-static-ingress-v1/2008-09-20260905-r2/static-ingress-preflight-blocked.json`
  (`c0c2b9ff13d66dbe541ba48e09471a034553921316bec87a7b23a2f3d162d619`).

The reconciliation applied only the exact one-current-source versus one-legacy
non-source mode-1 candidate rule.  It restored 16 stale carrier rows as
preserve-only native records and reduced duplicate candidate groups from 27 to
11.  The remaining groups require an opening-date roster decision and are
explicitly retained, so strict V2 validation still fails.  No display-alias
repair, roster-tail reconciliation, compiler materialisation, static audit,
release manifest, runtime route, or screenshot was produced.

No source intake, current manifest, canonical package, release tree, or the
established 2015/16 release changed. 2008/09 remains
`release_eligible: false` and `provisional-not-playable`. The next smallest
action is to inspect the hash-bound opening-date evidence for one remaining
pair (starting with `alfiepotter`) and make a reconciliation only if that
evidence selects one carrier uniquely.

## 2008/09 `alfiepotter` opening-date reconciliation — 2026-09-06

The first remaining current-source duplicate was reconciled in a new
static-only candidate.  The input package binds the exact opening-squad
preallocation SHA-256
`f2d19d16c6141c05267b331ce5c229adef3513447b17d67b6c8a9fc2f41d3e9c`.
That evidence has one dated opening-XI claim: Kettering Town on 2008-08-09,
order 9, source row
`fba825ffc2b1d63f8f2cb71643239e5cbe489c0b88b899f309439afe8a4e48c6`.
The competing Kettering catalogue row is undated and has no opening-XI order.

- Input stale-candidate package SHA-256:
  `ee7d5729d15a7c8f6cb5122b461154da459a12ac37a93ae3a5f38dfb9a221248`.
- Reconciled package:
  `.local/season-static-ingress-v1/2008-09-alfiepotter-20260906/season-package.opening-date-reconciled.json`
  (`043aabd608d28e97a75ebb386633996ddf19da5197c7de5a7bd194d3b082bb48`).
- Reconciliation audit:
  `.local/season-static-ingress-v1/2008-09-alfiepotter-20260906/opening-date-candidate-reconciliation-audit.json`
  (`27c452d523e297c1dab64e44c76db469b30bff41b4e8fc9a61fc0246f820500e`).

The repair retained `player-10941` as the uniquely evidenced Alfie Potter
claim and restored losing carrier `11134` from its parser-read native whole
row (`Kevin HALES`, payload SHA-256
`cd6733f4cf28b7849adc8451efc2548c75492b9db77e474bd748da54a2036c5f`).
Its portrait outcome is explicitly unresolved/native-no-photo.  The ambiguous
current-source duplicate count fell exactly from 11 to 10; strict V2
validation no longer reports `alfiepotter` and still fails closed on the ten
named remaining groups.

No source intake, current manifest, canonical package, binary compiler output,
clean audit, release, runtime route, screenshot, or the established 2015/16
release changed.  2008/09 remains `release_eligible: false` and
`provisional-not-playable`.  The next smallest action is the same bounded,
hash-bound opening-date evidence check for `andyburgess`, with no repair if it
does not identify exactly one earliest dated opening-XI owner.

## 2008/09 `andyburgess` opening-date reconciliation — 2026-09-06

The next current-source duplicate was reconciled from the same package-bound
opening-squad preallocation.  The evidence has one dated opening-XI claim:
Rushden & Diamonds on 2008-08-09, order 6, source row
`3c134dc7f1b367e4b5b7ef7708246af74c17fbe3114b07a834798f4b08a60931`.
The competing Rushden catalogue row is undated and has no opening-XI order.

- Input package SHA-256:
  `043aabd608d28e97a75ebb386633996ddf19da5197c7de5a7bd194d3b082bb48`.
- Reconciled package:
  `.local/season-static-ingress-v1/2008-09-andyburgess-20260906/season-package.opening-date-reconciled.json`
  (`6a9cfd18d78ceeb1a5e7d78d8edb4f681febc9f5402999056afd87c2af956ed5`).
- Reconciliation audit:
  `.local/season-static-ingress-v1/2008-09-andyburgess-20260906/opening-date-candidate-reconciliation-audit.json`
  (`3bd83e1d7d63a2d654f6e7d6add7a3f708a67794ef0e2b19592b96ce6626f31f`).

The repair retained `player-11024` as the uniquely evidenced Andy Burgess
claim and restored losing carrier `11234` from its parser-read native whole
row (`David McKINLAY`, payload SHA-256
`2022643c7f6914eb252829e4d442bae77ff620192ceab79b61dd872d71750717`).
Its portrait outcome is explicitly unresolved/native-no-photo.  The ambiguous
current-source duplicate count fell exactly from 10 to 9; strict V2 validation
no longer reports `andyburgess` and still fails closed on the nine named
remaining groups.

No source intake, current manifest, canonical package, binary compiler output,
clean audit, release, runtime route, screenshot, or the established 2015/16
release changed.  2008/09 remains `release_eligible: false` and
`provisional-not-playable`.  The next smallest action is the same bounded,
hash-bound opening-date evidence check for `andyferrell`, with no repair if it
does not identify exactly one earliest dated opening-XI owner.

## 2008/09 `andyferrell` opening-date reconciliation — 2026-09-06

The next current-source duplicate was reconciled from the same package-bound
opening-squad preallocation.  The evidence has one dated opening-XI claim:
Kidderminster Harriers on 2008-08-09, order 10, source row
`689bf55c2e6cd8d218f504f8fd37f927e4ea0c09823881cf5c0481c52914455f`.
The competing Kidderminster catalogue row is undated and has no opening-XI
order.

- Input package SHA-256:
  `6a9cfd18d78ceeb1a5e7d78d8edb4f681febc9f5402999056afd87c2af956ed5`.
- Reconciled package:
  `.local/season-static-ingress-v1/2008-09-andyferrell-20260906/season-package.opening-date-reconciled.json`
  (`eb71ccde263f182d98235f446c608ade70bd2695ede75303f31992bd4ea903d5`).
- Reconciliation audit:
  `.local/season-static-ingress-v1/2008-09-andyferrell-20260906/opening-date-candidate-reconciliation-audit.json`
  (`1914c42b115bcab913b23f65f9d7253344944d43ebdd3298765bf06d8cb00dc4`).

The repair retained `player-10959` as the uniquely evidenced Andy Ferrell
claim and restored losing carrier `11079` from its parser-read native whole
row (`David HALL`, payload SHA-256
`d414f59aadb6c61d9b694a7fa5f40bd0461e6ca220409b5bfe02bd02554d4bea`).
Its portrait outcome is explicitly unresolved/native-no-photo.  The ambiguous
current-source duplicate count fell exactly from 9 to 8; strict V2 validation
no longer reports `andyferrell` and still fails closed on the eight named
remaining groups.

No source intake, current manifest, canonical package, binary compiler output,
clean audit, release, runtime route, screenshot, or the established 2015/16
release changed.  2008/09 remains `release_eligible: false` and
`provisional-not-playable`.  The next smallest action is the same bounded,
hash-bound opening-date evidence check for `brettsolkhon`, with no repair if it
does not identify exactly one earliest dated opening-XI owner.

## 2008/09 `brettsolkhon` opening-date reconciliation — 2026-09-06

The next current-source duplicate was reconciled from the same package-bound
opening-squad preallocation.  The evidence has one dated opening-XI claim:
Kettering Town on 2008-08-09, order 6, source row
`c9fdb4b571224b047deda893e91df4adf0952d4d2c7ab7548d13e361ac9e153d`.
The competing Kettering catalogue row is undated and has no opening-XI order.

- Input package SHA-256:
  `eb71ccde263f182d98235f446c608ade70bd2695ede75303f31992bd4ea903d5`.
- Reconciled package:
  `.local/season-static-ingress-v1/2008-09-brettsolkhon-20260906/season-package.opening-date-reconciled.json`
  (`8cafd7b45bf5d7cee9f13c3332875ae8539f650570693645b43b2c9a96c672dc`).
- Reconciliation audit:
  `.local/season-static-ingress-v1/2008-09-brettsolkhon-20260906/opening-date-candidate-reconciliation-audit.json`
  (`bdd365eaccaea58000b5bd3ec403d50b46161afde1bf19d3382fd605770d82d9`).

The repair retained `player-10937` as the uniquely evidenced Brett Solkhon
claim and restored losing carrier `11128` from its parser-read native whole
row (`Paul COPLEY`, payload SHA-256
`364df286c94334f4b8e92f0cfc7a1cc2d444400431c5d84fd8227cce1255defa`).
Its portrait outcome is explicitly unresolved/native-no-photo.  The ambiguous
current-source duplicate count fell exactly from 8 to 7; non-strict V2
validation passes, while strict V2 validation no longer reports
`brettsolkhon` and still fails closed on the seven named remaining groups.

No source intake, current manifest, canonical package, binary compiler output,
clean audit, release, runtime route, screenshot, or the established 2015/16
release changed.  2008/09 remains `release_eligible: false` and
`provisional-not-playable`.  The next smallest action is the same bounded,
hash-bound opening-date evidence check for `darrynstamp`, with no repair if it
does not identify exactly one earliest dated opening-XI owner.

## 2008/09 `darrynstamp` opening-date reconciliation — 2026-09-06

The next current-source duplicate was reconciled from the same package-bound
opening-squad preallocation.  The evidence has one dated opening-XI claim:
Northwich Victoria on 2008-08-09, order 10, source row
`5e5197dd514295c7560726a60c18da89551662d365242ea0778562806b704cd5`.
The competing Northwich catalogue row is undated and has no opening-XI order.

- Input package SHA-256:
  `8cafd7b45bf5d7cee9f13c3332875ae8539f650570693645b43b2c9a96c672dc`.
- Reconciled package:
  `.local/season-static-ingress-v1/2008-09-darrynstamp-20260906/season-package.opening-date-reconciled.json`
  (`738c90455012a8ec5fce09c34b7ec7f629c540349eecc58e9163023022976347`).
- Reconciliation audit:
  `.local/season-static-ingress-v1/2008-09-darrynstamp-20260906/opening-date-candidate-reconciliation-audit.json`
  (`b3409eeada32dbf9deec36e296ef09995286b42ff660edaf690b5aabc17f769d`).

The repair retained `player-11013` as the uniquely evidenced Darryn Stamp
claim and restored losing carrier `10901` from its parser-read native whole
row (`Jason GOODLIFFE`, payload SHA-256
`d6d852ddf692743ad4385231869825246b260d48b1854d22c11a30884e3dbcd2`).
Its portrait outcome is explicitly unresolved/native-no-photo.  The ambiguous
current-source duplicate count fell exactly from 7 to 6; non-strict V2
validation passes, while strict V2 validation no longer reports
`darrynstamp` and still fails closed on the six named remaining groups.

No source intake, current manifest, canonical package, binary compiler output,
clean audit, release, runtime route, screenshot, or the established 2015/16
release changed.  2008/09 remains `release_eligible: false` and
`provisional-not-playable`.  The next smallest action is the same bounded,
hash-bound opening-date evidence check for `deanbennett`, with no repair if it
does not identify exactly one earliest dated opening-XI owner.

## 2008/09 `deanbennett` opening-date reconciliation — 2026-09-06

The next current-source duplicate was reconciled from the package-bound
opening-squad preallocation.  The evidence has one dated opening-XI claim:
Kidderminster Harriers on 2008-08-09, order 6, source row
`89e7f4fd031cad75424762364b9fba5c64aa93247786786b172f0b1315bd89a7`.
The competing Kidderminster catalogue row is undated and has no opening-XI
order.

- Input package SHA-256:
  `738c90455012a8ec5fce09c34b7ec7f629c540349eecc58e9163023022976347`.
- Reconciled package:
  `.local/season-static-ingress-v1/2008-09-deanbennett-20260906/season-package.opening-date-reconciled.json`
  (`1b4f585ee2890bfc18223421bf7d972b54a8b7f64a3f1055b95be94ce283de43`).
- Reconciliation audit:
  `.local/season-static-ingress-v1/2008-09-deanbennett-20260906/opening-date-candidate-reconciliation-audit.json`
  (`0dc83a26af34761e65801a1ff0d654460621976665d24e7171a054dea2cb24fb`).

The repair retained `player-10955` as the uniquely evidenced Dean Bennett
claim and restored losing carrier `11080` from its parser-read native whole
row (`Lee COATHUP`, payload SHA-256
`931116c18d36c19dcf2cc91fbb7db725570593c38e02e1143c558b26dd878128`).
Its portrait outcome is explicitly unresolved/native-no-photo.  The ambiguous
current-source duplicate count fell exactly from 6 to 5.  Non-strict V2
validation passes; strict validation now fails only on `gregpearson`,
`justinrichards`, `michaelbostwick`, `scotttynan`, and `stuartelliott`.

No source intake, current manifest, canonical package, binary compiler output,
clean audit, release, runtime route, screenshot, or the established 2015/16
release changed.  2008/09 remains `release_eligible: false` and
`provisional-not-playable`.  The next smallest action is the same bounded,
hash-bound opening-date evidence check for `gregpearson`, with no repair if it
does not identify exactly one earliest dated opening-XI owner.

## 2008/09 `gregpearson` opening-date reconciliation — 2026-09-06

The next current-source duplicate was reconciled from the package-bound
opening-squad preallocation.  The evidence has one dated opening-XI claim:
Burton Albion on 2008-08-09, order 11, source row
`6e994b464dcdf58256c0a026943e02ce099c15b72165d3348c15109b36cc5016`.
The competing Burton catalogue row is undated and has no opening-XI order.

- Input package SHA-256:
  `1b4f585ee2890bfc18223421bf7d972b54a8b7f64a3f1055b95be94ce283de43`.
- Reconciled package:
  `.local/season-static-ingress-v1/2008-09-gregpearson-20260906/season-package.opening-date-reconciled.json`
  (`38b1bc178755bb3135473bf40c95cb62e679d1e94df8c0d5cdd3add7d61be376`).
- Reconciliation audit:
  `.local/season-static-ingress-v1/2008-09-gregpearson-20260906/opening-date-candidate-reconciliation-audit.json`
  (`9db774fc3a4120402eea51f633b9560aa7b169bf46755e70ac2a3c3a6b7f0c4b`).

The repair retained `player-10853` as the uniquely evidenced Greg Pearson
claim and restored losing carrier `11311` from its parser-read native whole
row (`Paul COMSTIVE`, payload SHA-256
`34945e8dc6e528842172eae12fb9f55d01e64476273725918aac657d132178c4`).
Its portrait outcome is explicitly unresolved/native-no-photo.  The ambiguous
current-source duplicate count fell exactly from 5 to 4.  Non-strict V2
validation passes; strict validation now fails only on `justinrichards`,
`michaelbostwick`, `scotttynan`, and `stuartelliott`.

No source intake, current manifest, canonical package, binary compiler output,
clean audit, release, runtime route, screenshot, or the established 2015/16
release changed.  2008/09 remains `release_eligible: false` and
`provisional-not-playable`.  The next smallest action is the same bounded,
hash-bound opening-date evidence check for `justinrichards`, with no repair if
it does not identify exactly one earliest dated opening-XI owner.

## 2008/09 `justinrichards` opening-date reconciliation — 2026-09-07

The next current-source duplicate was reconciled from the package-bound
opening-squad preallocation.  The evidence has one dated opening-XI claim:
Kidderminster Harriers on 2008-08-09, order 11, source row
`648b43ee247c555b23c92fe7e0309b5bf1d2aeb1e285ba2256e502b5cbcccc71`.
The competing Kidderminster catalogue row is undated and has no opening-XI
order.

- Input package SHA-256:
  `38b1bc178755bb3135473bf40c95cb62e679d1e94df8c0d5cdd3add7d61be376`.
- Reconciled package:
  `.local/season-static-ingress-v1/2008-09-justinrichards-20260907/season-package.opening-date-reconciled.json`
  (`4251b48ab8e8c9159b27d2f9f49436c74225ccf5f5a594281440b7832f2091a3`).
- Reconciliation audit:
  `.local/season-static-ingress-v1/2008-09-justinrichards-20260907/opening-date-candidate-reconciliation-audit.json`
  (`6ea8f5290126f5f5d7e74141cf643db8f9d8d8de1bdfc80cec61a26a9d8318e1`).

The repair retained `player-10960` as the uniquely evidenced Justin Richards
claim and restored losing carrier `11081` from its parser-read native whole
row (`Jamie BATES`, payload SHA-256
`1433b37a46f8fbac698712780c72d0f5e6310a9224f3ea765531bb27e39683c5`).
Its portrait outcome is explicitly unresolved/native-no-photo.  The ambiguous
current-source duplicate count fell exactly from 4 to 3.  Non-strict V2
validation passes; strict validation now fails only on `michaelbostwick`,
`scotttynan`, and `stuartelliott`.

No source intake, current manifest, canonical package, binary compiler output,
clean audit, release, runtime route, screenshot, delivery-status classification,
or the established 2015/16 release changed.  2008/09 remains
`release_eligible: false` and `provisional-not-playable`.  The next smallest
action is the same bounded, hash-bound opening-date evidence check for
`michaelbostwick`, with no repair if it does not identify exactly one earliest
dated opening-XI owner.

## 2008/09 `michaelbostwick` opening-date reconciliation — 2026-09-07

The next current-source duplicate was reconciled from the package-bound
opening-squad preallocation.  The evidence has one dated opening-XI claim:
Stevenage Borough on 2008-08-09, order 3, source row
`3bf69ec28ebdc11276d0535235cf86cabfee5296f07eba520256b484976cc0be`.
The competing Stevenage catalogue row is undated and has no opening-XI order.

- Input package SHA-256:
  `4251b48ab8e8c9159b27d2f9f49436c74225ccf5f5a594281440b7832f2091a3`.
- Reconciled package:
  `.local/season-static-ingress-v1/2008-09-michaelbostwick-20260907/season-package.opening-date-reconciled.json`
  (`26972c809422391849fb1936c7e2f7604c9708a4bd9781f000c42deaf3ccc41e`).
- Reconciliation audit:
  `.local/season-static-ingress-v1/2008-09-michaelbostwick-20260907/opening-date-candidate-reconciliation-audit.json`
  (`8e3def819ebac342ab5aefd37d2b3ebda2a6e027fff858f8fa05ee7914926fec`).

The repair retained `player-11092` as the uniquely evidenced Michael Bostwick
claim and restored losing carrier `10827` from its parser-read native whole
row (`Gary STEBBING`, payload SHA-256
`65a79dd5f568502125106f8d6aba2cc01d739bae434f094c31648120f738a2e9`).
Its portrait outcome is explicitly unresolved/native-no-photo.  The ambiguous
current-source duplicate count fell exactly from 3 to 2.  Non-strict V2
validation passes; strict validation now fails only on `scotttynan` and
`stuartelliott`.

No source intake, current manifest, canonical package, binary compiler output,
clean audit, release, runtime route, screenshot, delivery-status classification,
or the established 2015/16 release changed.  2008/09 remains
`release_eligible: false` and `provisional-not-playable`.  The next smallest
action is the same bounded, hash-bound opening-date evidence check for
`scotttynan`, with no repair if it does not identify exactly one earliest dated
opening-XI owner.

## 2008/09 `scotttynan` opening-date reconciliation — 2026-09-07

The next current-source duplicate was reconciled from the package-bound
opening-squad preallocation.  The evidence has one dated opening-XI claim:
Northwich Victoria on 2008-08-09, order 1, source row
`1bbe4084b5d11cc0bdf6a71816e543c8d230d5560d673c88b014cb75470c0d33`.
The competing Northwich catalogue row is undated and has no opening-XI order.

- Input package SHA-256:
  `26972c809422391849fb1936c7e2f7604c9708a4bd9781f000c42deaf3ccc41e`.
- Reconciled package:
  `.local/season-static-ingress-v1/2008-09-scotttynan-20260907/season-package.opening-date-reconciled.json`
  (`e14756654f0d936fc187cb105d944b030031308468d179b249b1ac71ca55e5c8`).
- Reconciliation audit:
  `.local/season-static-ingress-v1/2008-09-scotttynan-20260907/opening-date-candidate-reconciliation-audit.json`
  (`7ba5b9248f6be051f2f75d7efb8f9469f25970024fd31a7f140b34eaf476f0a4`).

The repair retained `player-11004` as the uniquely evidenced Scott Tynan
claim and restored losing carrier `10895` from its parser-read native whole
row (`Russell MEARA`, payload SHA-256
`42c0133043252fbc64307f659f5522d01e6cfb58c91f1e1078f292b8563b30cb`).
Its portrait outcome is explicitly unresolved/native-no-photo.  The ambiguous
current-source duplicate count fell exactly from 2 to 1.  Non-strict V2
validation passes; strict validation now fails only on `stuartelliott`.

The initial invocation continued to completion after exceeding its command
window.  A conservative retry also produced a no-overwrite duplicate under
`.local/season-static-ingress-v1/2008-09-scotttynan-20260907-r2/`: its package
is byte-identical, and its audit is semantically identical after excluding the
output path (audit SHA-256
`96b16b633fc1c9a281940fa622f3738c2c79f7881ea8fbd9cc9fb7124ac1f34f`).
Both are retained without alteration; the original directory above is the
primary evidence path.

No source intake, current manifest, canonical package, binary compiler output,
clean audit, release, runtime route, screenshot, delivery-status classification,
or the established 2015/16 release changed.  2008/09 remains
`release_eligible: false` and `provisional-not-playable`.  The next smallest
action is the same bounded, hash-bound opening-date evidence check for
`stuartelliott`, with no repair if it does not identify exactly one earliest
dated opening-XI owner.

## 2008/09 `stuartelliott` opening-date reconciliation — 2026-09-07

The final current-source duplicate was reconciled from the same package-bound
opening-squad preallocation.  The evidence has one dated opening-XI claim:
Grays Athletic on 2008-08-09, order 4, source row
`f7e5b4fe851918888de257f4859bdd019726111b68b7fbf12d607e08fcb0a438`.
The competing Grays catalogue row is undated and has no opening-XI order.

- Input package SHA-256:
  `e14756654f0d936fc187cb105d944b030031308468d179b249b1ac71ca55e5c8`.
- Reconciled package:
  `.local/season-static-ingress-v1/2008-09-stuartelliott-20260907/season-package.opening-date-reconciled.json`
  (`b6459cb87d11a517dae7c257324aea544a9ea9c50fe8534390baf0fd71236671`).
- Reconciliation audit:
  `.local/season-static-ingress-v1/2008-09-stuartelliott-20260907/opening-date-candidate-reconciliation-audit.json`
  (`cbfc4b3f62a4afe129a7dc62ab51cea63c8c6138729902d1c59452665a700bc6`).

The repair retained `player-11040` as the uniquely evidenced Stuart Elliott
claim and restored losing carrier `10917` from its parser-read native whole
row (`Wayne SIMPSON`, payload SHA-256
`0a8bde4559a8d38e2e3098921fde5906933be60d0321e6886fa8402894616d4b`).
Its portrait outcome is explicitly unresolved/native-no-photo.  The ambiguous
current-source duplicate count fell exactly from 1 to 0.  Both non-strict and
strict V2 validation now pass for this exact derivative.

No source intake, current manifest, canonical package, binary compiler output,
clean audit, release, runtime route, screenshot, delivery-status classification,
or the established 2015/16 release changed.  2008/09 remains
`release_eligible: false` and `provisional-not-playable`.  The next smallest
action is one fresh no-overwrite static ingress of this exact strict package
against the verified base; it must remain a draft/static qualification and
must not inherit the earlier derivative's runtime or screenshot claim.

## 2008/09 final-duplicate strict static ingress — 2026-09-07

The exact package produced by the final `stuartelliott` reconciliation was
submitted once to the no-overwrite static-ingress pipeline against the
hash-verified clean 1998 base.  Strict V2 validation passed before and after
the deterministic source-write-policy, display-alias, and fixed-row
reconciliation stages.

- Input package SHA-256:
  `b6459cb87d11a517dae7c257324aea544a9ea9c50fe8534390baf0fd71236671`.
- Static-ingress directory:
  `.local/season-static-ingress-v1/2008-09-strict-20260907-r1/`.
- Reconciled compiled package SHA-256:
  `6f9c4006f3064c35e493d7657016ff0dc991a60607db283368051823ea887d12`.
- Compiler receipt SHA-256:
  `ff29790cd5d67e732023a1256150779b801f29037555b15c5876fa84cae65cce`.
- Clean static audit SHA-256:
  `506c14c3be870462fd226588e820d33a4290516e0c5fa71d49796a4c15536d03`.
- Static-ingress receipt SHA-256:
  `5d38e44726f93fad1798fd5d0838ae67eb5d212903745ba593728a26391dc3c4`.

The compiler wrote 451 clubs and 9,354 player declarations.  The clean audit
passes against base inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`,
with zero append/recycle operations, all 451 fixed roster tails checked, and
zero tail mismatches.  Output database SHA-256 values are
`09697b79ab8adf7756f39cc291bfc2173c6f71d3971b201a73dd42cce2322573`
for `ENT98030.FDI`,
`9d7cc698f44234b15afb64abdc942a446909e9901b957ea99e7c9467d45896c5`
for `EQ98030.FDI`, and
`844ef2152927af3cf429755ceb94275823464c766523dbad0fe637f4c5eee5b0`
for `JUG98030.FDI`.

This is a static derivative only.  Its game tree still contains the clean-base
executable (`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158`),
not the 2008/09 calendar executable
(`14c1775361035b74460febb7110e13fbeb8562cf88d14e675965e704691764b2`).
The refreshed delivery status therefore does not attach the earlier selector
discovery runtime or screenshots to this build and continues to report the
canonical-package and canonical-package-bound static-audit gates as missing.

No source intake, current manifest, canonical package, release tree, runtime
route, screenshot, or the established 2015/16 release changed.  Eligibility
remains `release_eligible: false` and `provisional-not-playable`; the movement
is from strict-validation-blocked to clean-static-qualified for this exact
derivative.  The next smallest action is to create a fresh, hash-bound
canonical-workspace candidate for this exact repaired derivative, without
moving a current manifest or reusing the earlier runtime evidence.

## 2008/09 strict canonical-workspace candidate — 2026-09-07

The exact reconciled package from the final-duplicate static ingress was
carried into the fail-closed canonical-workspace candidate lane.  Its existing
2008/09 calendar contract was re-attested from the hash-bound cached receipt
and executable; the re-attested package remained byte-identical to the static
derivative at SHA-256
`6f9c4006f3064c35e493d7657016ff0dc991a60607db283368051823ea887d12`.

- Calendar re-attestation:
  `.local/season-canonical-candidate-v1/2008-09-strict-20260907-binding/`
  (audit SHA-256
  `fb6387f59bd7d64de5270625f979d64c71cdd931e6f3e19c04b1b1a68187d9ff`).
- Canonical-workspace candidate:
  `.local/season-canonical-candidate-v1/2008-09-strict-20260907/`.
- Promotion audit SHA-256:
  `c7d4135afce81f51c8fa4d8f176a071746f634655abdc09f8c1f0febfa2b1846`.
- Prepared effective-package SHA-256:
  `e16293bf486914013b45518203bd54455be81dbe288a9bb90575915965ffb7c8`.
- Build-plan candidate SHA-256:
  `3f4b27c1e6675b98fe1d1d7f89ed25e889da4d9114f018a1498a0f617618fe3e`.

Strict Season Package V2 validation, calendar binding, verified-base
validation, workspace validation, and deterministic workspace preparation all
pass.  The build-plan candidate remains `blocked-before-binary-compile` and
explicitly requires a clean compiler receipt for this exact effective package,
two matching independent output inventories, a reviewed V2 build plan, a
runtime receipt, and a bound Stoke City lineup screenshot.  The earlier
2008/09 selector-discovery runtime and 91 screenshots belong to an earlier
package derivative and were not reused.

No source intake, current manifest, canonical release package, game tree,
release tree, runtime route, screenshot, delivery-status classification, or
the established 2015/16 release changed.  Eligibility remains
`release_eligible: false` and `provisional-not-playable`; the movement is from
clean-static-qualified derivative to a strict, prepared, hash-bound
canonical-workspace candidate.  The next smallest action is one fresh
no-overwrite workspace compile of effective package
`e16293bf486914013b45518203bd54455be81dbe288a9bb90575915965ffb7c8`
against the verified clean base, without claiming the resulting first
inventory as a release.

## 2008/09 first canonical-candidate workspace compile — 2026-09-07

The exact prepared effective package from the strict canonical-workspace
candidate was compiled once into fresh, no-overwrite materialisation and
receipt directories against the hash-verified clean 1998 base.

- Effective package SHA-256:
  `e16293bf486914013b45518203bd54455be81dbe288a9bb90575915965ffb7c8`.
- Materialised game tree:
  `.local/season-workspace-v1/2008-09-canonical-compile-20260907-r1-game/`.
- Build receipts:
  `.local/season-workspace-v1/2008-09-canonical-compile-20260907-r1-build/`.
- Database compiler receipt SHA-256:
  `4e703b5655607941145aa9e2773748322a836517109b6d82bfb3872b860dfb34`.

The compiler receipt binds the exact effective package as both its source and
compiled package, records 451 clubs, 9,354 players, and 447 managers written,
and records no mode-0 append, mode-1 append, or mode-0 carrier recycle.  The
materialised database hashes are
`09697b79ab8adf7756f39cc291bfc2173c6f71d3971b201a73dd42cce2322573`
for `ENT98030.FDI`,
`9d7cc698f44234b15afb64abdc942a446909e9901b957ea99e7c9467d45896c5`
for `EQ98030.FDI`, and
`844ef2152927af3cf429755ceb94275823464c766523dbad0fe637f4c5eee5b0`
for `JUG98030.FDI`.  These match the prior strict static derivative, but that
derivative's audit is not treated as an audit bound to this effective-package
hash.  The copied executable remains the clean-base executable at
`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158`;
the target calendar was not overlaid.

Workspace validation, repository boundary validation, and `git diff --check`
passed.  No source intake, current manifest, canonical release package,
release tree, runtime route, screenshot, delivery-status classification, or
the established 2015/16 release changed.  Eligibility remains
`release_eligible: false` and `provisional-not-playable`; the movement is that
the exact canonical-candidate effective package now has its first clean binary
compiler receipt and materialised output inventory.  The next smallest action
is a second fresh no-overwrite compile of the same workspace, followed by an
exact inventory comparison; it must not be promoted or called playable.

## 2008/09 second canonical-candidate workspace compile — 2026-09-07

The exact same canonical-candidate workspace was compiled a second time into
fresh, no-overwrite materialisation and receipt directories against the same
hash-verified clean 1998 base.

- Effective package SHA-256:
  `e16293bf486914013b45518203bd54455be81dbe288a9bb90575915965ffb7c8`.
- Second materialised game tree:
  `.local/season-workspace-v1/2008-09-canonical-compile-20260907-r2-game/`.
- Second build receipts:
  `.local/season-workspace-v1/2008-09-canonical-compile-20260907-r2-build/`.
- Database compiler receipt SHA-256:
  `4e703b5655607941145aa9e2773748322a836517109b6d82bfb3872b860dfb34`.
- Complete 275-file inventory fingerprint for both independent game trees:
  `722c7b5b6718d1214def873ece158432393d5f727000518a9ecca13d99dd1a98`.

An exact path-ordered SHA-256 comparison of every regular file in the first
and second game trees produced no differences.  The independently emitted
compiler receipts are also byte-identical.  Their database outputs remain
`09697b79ab8adf7756f39cc291bfc2173c6f71d3971b201a73dd42cce2322573`
for `ENT98030.FDI`,
`9d7cc698f44234b15afb64abdc942a446909e9901b957ea99e7c9467d45896c5`
for `EQ98030.FDI`, and
`844ef2152927af3cf429755ceb94275823464c766523dbad0fe637f4c5eee5b0`
for `JUG98030.FDI`.

No source intake, current manifest, canonical release package, clean static
audit, calendar overlay, release tree, runtime route, screenshot,
delivery-status classification, or the established 2015/16 release changed.
Eligibility remains `release_eligible: false` and
`provisional-not-playable`; the movement is that the exact 2008/09
canonical-workspace candidate now has two independently materialised,
byte-identical output inventories.  The next smallest action is to create a
reviewed `pm99-season-build-plan-v2` bound to these two locked inventories,
without promoting either tree or attaching the earlier derivative's runtime
evidence.

## 2008/09 reviewed database build plan — 2026-09-07

The two byte-identical canonical-candidate workspace builds were used as the
reference evidence for one canonical `pm99-season-build-plan-v2` at
`.local/season-build-plans-v2/2008-09-strict-20260907/build-plan.json`.  The
canonical plan-document SHA-256 is
`b25f7829cbf76137c9444ef74228f0a2c41b5004c38524d832f51ecad61c5268`;
the complete on-disk file SHA-256, including its trailing newline, is
`7f7bf84aee7b4821054f31925a50e9ebbcf50b2fc4e08f93eb6b22589bc20e52`.

The plan locks the verified clean-base inventory
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`,
the exact effective-package canonical document hash
`4b5fac0e6e7b982fe113ee497dcec2a09f04006e58b642815721e762e07fe5f7`,
and the hashed generic database compiler
`bf576a8be2a06d9f821022b89c46af05c8dc98629f832a66653e293d0ee384ab`.
The package's on-disk byte SHA-256 remains
`e16293bf486914013b45518203bd54455be81dbe288a9bb90575915965ffb7c8`;
the two values differ because the V2 plan descriptor hashes canonical JSON
content while the earlier receipt records the complete file bytes including
the trailing newline.

Its only stage is the reviewed database-compiler adapter, with the exact
declared output surface `DBDAT/ENT98030.FDI`, `DBDAT/EQ98030.FDI`, and
`DBDAT/JUG98030.FDI`.  Their V2 stage-inventory fingerprint is
`4b18b25a4d807c1f096b4ba50b26a7c179289ef155ee8d3333cbf99be126f544`.
The complete 275-file V2 inventory fingerprint is
`20de5c43d7797be7429abaeabc7328b5167996423eb6f16ee095857a933e9d9a`;
both independent existing trees match it exactly.  The earlier
`722c7b5b6718d1214def873ece158432393d5f727000518a9ecca13d99dd1a98`
is the separately recorded raw path/hash-list fingerprint, not the
`pm99-file-inventory-v2` fingerprint used by the executable plan.

The plan was schema-validated and loaded back from canonical bytes.  It has
not been executed, so it creates no release manifest and makes no runtime or
playable claim.  No source intake, current manifest, canonical release
package, game tree, release tree, runtime route, screenshot, delivery-status
classification, or established 2015/16 release changed.  Eligibility remains
`release_eligible: false` and `provisional-not-playable`; the movement is that
the exact 2008/09 canonical candidate now has a reviewed, executable database
build plan bound to both reproducible reference inventories.  The next
smallest action is one fresh no-overwrite execution of this plan into a third
disposable tree and external metadata directory; it must still not be called
playable, and its base-calendar executable is not target-calendar runtime
proof.

## 2008/09 reviewed database build-plan execution — 2026-09-07

The reviewed plan was executed once against the hash-verified clean 1998 base
and the exact prepared canonical-workspace candidate.  The fail-closed runner
created a new disposable tree and external V2 metadata without changing any
source, current manifest, canonical package, or release link.

- Materialised tree:
  `.local/season-workspace-v1/2008-09-build-plan-20260907-r1-game/`.
- External metadata:
  `.local/season-build-plans-v2/2008-09-strict-20260907-r1-metadata/`.
- Build-plan receipt file SHA-256:
  `87216771c4ede956a790c43f87b8f27abcaede7097e2b739d4ca05fa2b8d15a9`.
- Release-manifest file SHA-256:
  `eb73000b8e5eef1e2755b716c384c6129f4fde7e1555f8b8ae51a07f3c582c9e`.
- Final 275-file V2 inventory fingerprint:
  `20de5c43d7797be7429abaeabc7328b5167996423eb6f16ee095857a933e9d9a`.

The receipt binds canonical plan hash
`b25f7829cbf76137c9444ef74228f0a2c41b5004c38524d832f51ecad61c5268`,
canonical package hash
`4b5fac0e6e7b982fe113ee497dcec2a09f04006e58b642815721e762e07fe5f7`,
and database-stage inventory fingerprint
`4b18b25a4d807c1f096b4ba50b26a7c179289ef155ee8d3333cbf99be126f544`.
An independent full-inventory comparison found no missing, extra, or changed
files against either prior canonical-candidate workspace build.

This is reproducible database build metadata, not release eligibility.  The
tree still contains the clean-base executable rather than the bound 2008/09
calendar executable, and no runtime route or screenshot is bound to this exact
plan output.  No canonical release package, release link, delivery-status
classification, or established 2015/16 release changed.  Eligibility remains
`release_eligible: false` and `provisional-not-playable`; the movement is from
an unexecuted reviewed plan to one successfully executed, receipt-bound V2
materialisation.  The next smallest action is to add and test a purpose-built,
hash-bound target-calendar adapter contract before reviewing a plan that may
materialise the 2008/09 executable; runtime and screenshot work must follow
that exact output.

## Target-calendar V2 adapter contract — 2026-09-07

`scripts/materialise_season_calendar_v1.py` now has an explicit
`--build-plan-adapter` mode and is directly executable.  The mode reuses the
existing fail-closed package, calendar-binding audit, patch receipt,
executable, and verified-base checks; changes only `MANAGPRE.EXE`; emits the
full materialisation receipt on stdout; and creates no receipt or other
metadata inside the game tree.  Its implementation SHA-256 is
`b5b05267a6ebc4ec794c637cbdb65a168584b2a579dcb1fbaf94d0f4398cee01`.

A focused synthetic integration executes the real adapter through
`season_pipeline_buildplan_v2.py`, with all four non-package inputs locked as
external artifacts.  It verifies the one-file stage inventory, complete final
inventory, V2 manifest stage record, and absence of an in-tree receipt.  The
combined calendar-materialiser and build-plan test set passes 10 tests.

No 2008/09 plan, package, manifest, game tree, release link, runtime route, or
screenshot was created or changed, and the established 2015/16 release was
not touched.  Eligibility remains `release_eligible: false` and
`provisional-not-playable`; the movement is that the previously missing
hash-bound target-calendar adapter contract is now implemented and tested.
The next smallest action is to review and write a new two-stage 2008/09 V2
build plan that composes the locked database stage with this calendar adapter
and predicts the exact target-calendar final inventory, without executing or
promoting it.

## 2008/09 reviewed database-and-calendar build plan — 2026-09-07

A separate canonical `pm99-season-build-plan-v2` now composes the already
locked database compiler with the tested target-calendar adapter.  The plan is
at
`.local/season-build-plans-v2/2008-09-strict-calendar-20260907/build-plan.json`.
Its canonical plan-document SHA-256 is
`a24b3e37c5f29eba2d84b719f49f56a39e62f787a8fb909edc1c582235877120`;
the complete on-disk file SHA-256, including its trailing newline, is
`4ceb4b0b29bf0a3fe7a99119fcc5b21e48503de15d0fd78367cd0fca6b3a0108`.

Stage 1 retains the reviewed database output inventory fingerprint
`4b18b25a4d807c1f096b4ba50b26a7c179289ef155ee8d3333cbf99be126f544`.
Stage 2 changes only `MANAGPRE.EXE`, locks the calendar adapter at SHA-256
`b5b05267a6ebc4ec794c637cbdb65a168584b2a579dcb1fbaf94d0f4398cee01`,
and locks the target executable at SHA-256
`14c1775361035b74460febb7110e13fbeb8562cf88d14e675965e704691764b2`.
Its one-file stage inventory fingerprint is
`62f2a5e6e4996b8115f82880533934395e186ce4c797989a84f3ce361aab5a3e`.
The predicted complete 275-file target-calendar inventory fingerprint is
`c04a30dcd0d603176be15e09ba86395ee14f4b70f985bbe0a814c43c32e685b7`.

The plan loads successfully through the fail-closed canonical validator and
all four external artifacts match their declared hashes.  It has not been
executed, and no canonical package, release link, runtime route, screenshot,
delivery-status classification, or established 2015/16 release changed.
Eligibility remains `release_eligible: false` and
`provisional-not-playable`; the movement is that 2008/09 now has a reviewed,
executable two-stage plan for the exact database and target-calendar
inventory.  The next smallest action is one fresh no-overwrite execution of
this plan into a new disposable game tree and external metadata directory,
without promotion or a playable claim.
