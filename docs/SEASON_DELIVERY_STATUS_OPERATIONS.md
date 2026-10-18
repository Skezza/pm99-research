# Season delivery status operations

`scripts/season_delivery_status_v1.py` is the read-only status surface for an
overnight watcher. It reports per-season source binding, package state, audited
compile state, runtime proof, screenshot evidence, exact current SHA-256
records, and the Bentley SD archive-copy state.

It deliberately distinguishes these labels:

| Label | Required evidence |
| --- | --- |
| `playable-known-good` | Clean static audit, successful registered runtime route, and a screenshot from that route. |
| `provisional-not-playable` | Any source intake, draft package, calendar-only clone, missing static audit, missing runtime proof, or missing runtime screenshot. |

A draft package is not promoted just because its JSON validates. A successful
file copy is not an archive verification just because its byte total looks
right. The report will keep both claims conservative.

Run a local-only refresh while the Pi is unavailable:

```bash
python3 scripts/season_delivery_status_v1.py \
  --no-remote \
  --output .local/operations/season-delivery-status.md \
  --json-output .local/operations/season-delivery-status.json
```

The same reader is available from the top-level season command:

```bash
./pm99-season status --no-remote \
  --output .local/operations/season-delivery-status.md \
  --json-output .local/operations/season-delivery-status.json
```

The report also recognises hash-verified provisional normalization derivatives.
It exposes their target-calendar binding and unresolved editorial ownership
count while keeping them `provisional-not-playable`. A normalized derivative
is not silently promoted to the current canonical package.

For the normal read-only Pi query, omit `--no-remote`:

```bash
python3 scripts/season_delivery_status_v1.py \
  --output .local/operations/season-delivery-status.md \
  --json-output .local/operations/season-delivery-status.json
```

The Markdown is the quick human handover. The companion JSON retains full
hashes rather than table abbreviations, including the installed 2015/16
release files and their static receipts. The script writes only the requested
output paths; it never mutates source manifests, packages, caches, game trees,
or archive inputs.

The Bentley source can be deleted only after an explicit complete checksum
comparison has passed. Until then the archive state is `pending`, even if the
copy process is active or its transferred byte count reaches the local total.

## 2008/09 canonical-candidate static qualification (2026-09-07)

The two existing clean compiles from the strict, calendar-bound 2008/09
canonical-workspace candidate now both have passing clean-base audits:

- `.local/season-workspace-v1/2008-09-canonical-compile-20260907-r1-build/clean-base-audit.json`;
- `.local/season-workspace-v1/2008-09-canonical-compile-20260907-r2-build/clean-base-audit.json`.

Both audits are byte-identical with SHA-256
`0c236a78a4b037a88f79c3d7aae48c383557c853e8a95f09fd0bc24ca18da56d`.
They report `result: pass`, 8,963 declared player-carrier changes, 431
club-carrier changes, 174 manager-carrier changes, zero append/recycle
operations, and all 451 fixed roster tails unchanged. Their compiler receipts
are also byte-identical with SHA-256
`4e703b5655607941145aa9e2773748322a836517109b6d82bfb3872b860dfb34`.

This closes deterministic clean static qualification for that exact candidate
only. It does not turn `season-package.candidate.json` into a canonical release
package, and the existing 2008/09 runtime screenshots are not yet bound to
these canonical compile hashes. The season therefore remains
`provisional-not-playable`; the generated status JSON intentionally remains
unchanged until those release and runtime bindings exist.

## 2008/09 database-and-calendar plan execution (2026-09-07)

The reviewed two-stage V2 plan at
`.local/season-build-plans-v2/2008-09-strict-calendar-20260907/build-plan.json`
has now been executed once into fresh, no-overwrite paths:

- game tree:
  `.local/season-workspace-v1/2008-09-build-plan-calendar-20260907-r1-game/`;
- external metadata:
  `.local/season-build-plans-v2/2008-09-strict-calendar-20260907-r1-metadata/`.

The fail-closed runner returned `ok: true`. The final 275-file inventory
fingerprint is
`c04a30dcd0d603176be15e09ba86395ee14f4b70f985bbe0a814c43c32e685b7`,
exactly matching the plan. The database stage fingerprint is
`4b18b25a4d807c1f096b4ba50b26a7c179289ef155ee8d3333cbf99be126f544`;
the target-calendar stage fingerprint is
`62f2a5e6e4996b8115f82880533934395e186ce4c797989a84f3ce361aab5a3e`.
The emitted build-plan receipt has file SHA-256
`3990fbfeec94a15437c46be1d8d9f03077e16d235e48b5af6f9719d195d53cb7`
and the emitted V2 manifest has file SHA-256
`899921e9ad13371631075426f05073384e9d53cf26d22ecf4a1fc438ab10f53a`.
The external base and output inventory files have SHA-256 values
`4d4bcda2b522684c1f0bb381bbe61a7e65ae42db77e9b28ea016e3ac4a8ea7ee`
and
`f70fb7de82b06833d7dadae820c7bdf2fadfe38b18fc340473717d1e8f2baf59`,
respectively.

This is a deterministic candidate materialisation, not a release promotion.
There is still no canonical 2008/09 release package, and the earlier runtime
route and screenshots are not bound to this exact inventory. The season
therefore remains `provisional-not-playable`; the generated delivery-status
JSON remains unchanged. The next smallest action is a successful PM99 runtime
route with a screenshot bound to this exact plan receipt and final inventory,
without creating a release link or playable claim.

## 2008/09 final-plan clean static audit (2026-09-07)

The exact calendar-bound materialisation above now also has a fresh passing
clean-base audit at
`.local/season-build-plans-v2/2008-09-strict-calendar-20260907-r1-metadata/clean-base-audit.json`
(SHA-256 `0c236a78a4b037a88f79c3d7aae48c383557c853e8a95f09fd0bc24ca18da56d`).
It is bound to effective-package SHA-256
`e16293bf486914013b45518203bd54455be81dbe288a9bb90575915965ffb7c8`
and the verified-base inventory
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The audit reports 8,963 declared player-carrier changes, 431 club-carrier
changes, 174 manager-carrier changes, all 451 fixed roster tails unchanged,
and zero append/recycle operations. Its three database output hashes match the
already recorded plan inventory. This adds static evidence for that exact
calendar-bound game tree only; it creates no release link and does not bind a
runtime route or screenshot. 2008/09 consequently remains
`provisional-not-playable`, with the canonical-package and bound-runtime gates
still open.

## 2008/09 exact-plan runtime attestation (2026-09-07)

One fresh four-division selector route ran against the exact audited
database-and-calendar build-plan output at
`.local/season-workspace-v1/2008-09-build-plan-calendar-20260907-r1-game/`.
The run tag is
`post1999_2008_09_exact_plan_runtime_20260907_r1`.  Its summary reports
`success: true`, four divisions, 80 observations, and no Wine debugger; the
runner, artifact sync, and cleanup statuses were all zero.  The summary
SHA-256 is
`27530e732c35250067a7d8e439300d0b1432080e0f7cceaaf10d3faddcc2a11f`.
It produced 91 screenshots; the bound sample
`screens/090_probe_division_04_team_20.png` has SHA-256
`7143f8e1e5f13d2ee39b0240fee4cd3073b6f41561d6d99fee53230319192a84`.

The runtime evidence is attached by
`.local/season-build-plans-v2/2008-09-strict-calendar-20260907-r1-metadata/runtime-attestation.json`.
Its SHA-256 is
`6ea1025f97ecae81fb658bf1a15a191aa56ab2330ff9ccd79bbf3b9cedceb1ee`;
the bound runtime-receipts input has SHA-256
`7bdcf8299cfc6234737d32ec333e85cb76162b5d4bcfc438dcd45c8ade143ca0`.
The attestation re-verifies final inventory
`c04a30dcd0d603176be15e09ba86395ee14f4b70f985bbe0a814c43c32e685b7`
against the plan's release manifest before binding the run receipt and
screenshot.  This closes the successful-runtime and bound-screenshot gates
for that exact candidate only.  It does not create a canonical season package
or release link, so 2008/09 remains `provisional-not-playable`.  The next
smallest action is a reviewed canonical-package promotion decision for this
already audited and runtime-attested candidate, without changing the 2015/16
release.

## 2008/09 canonical-package registration (2026-09-07)

The reviewed strict canonical-workspace candidate has now been registered at
`seasons/2008-09/season-package.json`. It is byte-identical to
`.local/season-canonical-candidate-v1/2008-09-strict-20260907/season-package.candidate.json`:
both have SHA-256
`6f9c4006f3064c35e493d7657016ff0dc991a60607db283368051823ea887d12`.
Strict V2 validation passes for the registered bytes.

A local-only status refresh now records `package.state: canonical-package` for
2008/09 and removes the canonical-package gate. It still reports
`provisional-not-playable`, with the one remaining gate `canonical
package-bound clean static compile/audit`. No release link, final-build receipt
directory, game tree, runtime artifact, screenshot, or 2015/16 release file
was created or changed by this registration.

The next smallest action is a fail-closed status/evidence binding that proves
the registered package's candidate-to-effective-package chain against the
existing clean audit and two-stage build-plan receipt. It must not infer a
release link or a playable classification until that binding is verified.

## 2008/09 canonical build-chain binding (2026-09-07)

The status reader now verifies the complete existing 2008/09 chain before it
can close the canonical package-bound static gate. The registered canonical
package at `seasons/2008-09/season-package.json` and its promotion-candidate
copy both have file SHA-256
`6f9c4006f3064c35e493d7657016ff0dc991a60607db283368051823ea887d12`.
The promotion receipt binds that byte stream to the prepared effective-package
file SHA-256 `e16293bf486914013b45518203bd54455be81dbe288a9bb90575915965ffb7c8`.

The V2 plan and manifest use the deliberately distinct canonical-content hash
of that effective JSON (without its on-disk trailing newline),
`4b5fac0e6e7b982fe113ee497dcec2a09f04006e58b642815721e762e07fe5f7`.
The reader checks both hash domains, the plan receipt, final inventory,
clean-base audit, release manifest, runtime attestation, registered runner
summary, and bound screenshot. Any mismatch or missing sidecar fails closed.

The local-only status refresh consequently records
`static-audited-canonical-package` and
`verified-canonical-package-bound-static-runtime-attested` for 2008/09. Its
registered four-division route and screenshot are now bound to this canonical
package, so the report classifies 2008/09 `playable-known-good` under the
published gate. This action did not create a `.local/releases` link, alter a
game tree, change a manifest, or modify the established 2015/16 release.

The next smallest action is a separate reviewed decision on immutable 2008/09
release registration; it must retain the recorded package, plan, audit, and
runtime hashes rather than rebuilding or moving current manifests.

## 2005/06 carrier-12 fixed-row preservation (2026-09-07)

The next blocked fixed-carrier guard in the existing 2005/06 static candidate
was reconciled in a new, no-overwrite derivative.  The input was
`.local/season-mode1-roster-reconcile-v1/2005-06-carrier-11-20260904/season-package.reconciled.json`
(SHA-256 `67cce0bf5c131ca81dc75525c2e2e716b253c45a0417437bb2dc472fbde1cc18`),
bound to the verified clean-base inventory
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The new package is
`.local/season-mode1-roster-reconcile-v1/2005-06-carrier-12-20260907/season-package.reconciled.json`
(SHA-256 `880202dba034973c1be457955a6eb61e734d059b2b6f23e792f7ca2131ca9582`),
with reconciliation audit SHA-256
`2d30bb33aab0837c60b1b22450f00e045b43e5095e11c65d92ecbcad87e91d25`.
It restores only the two missing base rows for mode-1 club carrier 12:
carrier 9229, Oswaldo Giroldo Junior (JUNINHO), and carrier 9852, Mª Romero
Poyón (JOSÉ MARI).  Both are parser-read whole-record
`preserve-existing-mode1` declarations with unresolved/native-no-photo
outcomes; neither is a target-season source, identity, ratings, or portrait
claim.

Strict V2 validation and a semantic-isolation check pass.  All pre-existing
player, club, and portrait declarations remain unchanged; the club's roster
is otherwise identical and retains exact base order.  No source intake,
manifest, canonical package, compiler materialisation, clean audit, release
link, runtime route, screenshot, or 2015/16 release file changed.  2005/06
therefore remains `provisional-not-playable` and `release_eligible: false`.
The next smallest action is one fresh no-overwrite static qualification of
this exact derivative against the verified base, solely to expose the next
fixed-carrier guard or produce a compiler receipt.

## 2005/06 carrier-12 static qualification (2026-09-08)

The requested fresh, no-overwrite static ingress has completed at
`.local/season-static-qualification-v1/2005-06-carrier-12-reconciled-20260908/`.
It consumed the carrier-12 preservation derivative with SHA-256
`880202dba034973c1be457955a6eb61e734d059b2b6f23e792f7ca2131ca9582`
against the verified clean-1998 base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`
and its 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The deterministic ingress completed the existing source-write-policy,
display-alias, and whole-row-preservation stages before compilation.  The
resulting static-only package has SHA-256
`07f48dfdffb3663366ac055a81dd3fffa502ecca68b0690ef4b9a11c67679589`.
Its batch preservation receipt records 72 eligible mode-1 clubs and 164
preserved base rows (with no shared new row); this is still a derived static
candidate, not a source or canonical-package change.

The compiler receipt SHA-256 is
`56258781e32de6c8300d9a34538ee4bd43f87568bb25112f6126602ee95da192`.
The clean static audit SHA-256 is
`8a4f1bbaf20aa84e23c71dac401698fd1f114766eb27eb6c57abd89413509f0c` and
reports `result: pass`: 8,905 player carriers, 427 club carriers, and 174
manager carriers changed; all 451 fixed roster tails match; append/recycle
and derived-mode-0-donor mismatch counts are zero.  The static-ingress
receipt is SHA-256
`688b97d8c446c0b15ecedad54f1de6fc783ed910f3371610a93ce7ed72610bc1`.

This closes the fixed-carrier static qualification frontier for this exact
derived candidate only.  It remains `clean-static-ingress-complete-not-playable`
and `release_eligible: false`: no canonical package or release link was
registered, and no calendar runtime validation, manager review, kit or
portrait materialisation, ratings/lineup review, PM99 runtime route, or bound
screenshot was created.  The generated delivery-status JSON remains
conservatively unchanged because its static-ingress reader deliberately only
indexes the established ingress roots, not this separate qualification root.
The next smallest action is a read-only review of the three generated
reconciliation receipts for a possible canonical-promotion decision; it must
not register the derivative or infer runtime/playable status.

## 2007/08 canonical-package registration (2026-09-08)

The byte-identical, hash-bound 2007/08 canonical-workspace candidate has been
registered at `seasons/2007-08/season-package.json`.  The registered file, the
current calendar-bound frozen draft, and
`.local/season-canonical-candidate-v1/2007-08/season-package.candidate.json`
all have SHA-256
`99a716821f4df36d1b07ef3c8fb6bffdfeb30906df717fc1a9ecc31806ae3308`.
Strict V2 validation passes for the registered bytes.

The candidate's promotion audit is
`.local/season-canonical-candidate-v1/2007-08/promotion-audit.json` (SHA-256
`7a41b062b14fddd230f1fc0dac8a3a663556e3707311c1042bac34ffa7e60d48`).
It records passing strict-package, calendar-binding, verified-base,
workspace-contract, and workspace-prepare checks against verified-base
descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`.

This removes only the canonical-package gate. It creates no game tree,
two-stage build plan, clean audit bound to the registered package, release
link, PM99 route, or screenshot, and does not alter the established 2015/16
release. 2007/08 remains `provisional-not-playable`. The next smallest action
is a fresh no-overwrite canonical-package-bound static materialisation and
clean audit, retaining this package and base hash; it must not claim runtime
or playable status.

## 2007/08 canonical-workspace compile blocker (2026-09-08)

One fresh canonical-workspace compile was attempted against the verified
clean base.  Workspace validation passed, including the registered/candidate
package SHA-256 `99a716821f4df36d1b07ef3c8fb6bffdfeb30906df717fc1a9ecc31806ae3308`,
and all 275 files in `.local/season-pipeline-v2/pm99-base-clean` matched the
candidate's verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`.

The no-overwrite materialisations at
`.local/season-workspace-v1/2007-08-canonical-compile-20260908-r1-{game,build}/`
and `...-r2-{game,build}/` are incomplete and must not be reused or treated
as evidence.  The r2 preparation did produce the expected effective package,
SHA-256 `a2190cd567d3aadcc2304def5d3818b50294155e4a5f009ffa50dda0f8b8e908`,
byte-identical to the reviewed candidate's prepared package.  The binary
compiler then failed closed before writing database records or producing a
compiler receipt or clean-base audit:

```text
player player-10320 carrier 10320 cannot apply variable name 'Darren Mackie':
Native dd6360 target name exceeds stable native string window:
new_role_start=31, old_role_start=30
```

Existing deterministic static-ingress evidence identifies the parser-safe
display alias for that same identity as `D. Mackie` in
`.local/season-static-ingress-v1/2007-08-20260905-r1/display-alias-repair-audit.json`
(SHA-256 `1e5c676bfde72f87f3373b88dabc31add5c195a082a710e2f213bf8b699e181d`).
That alias is presently only in a static-only derivative, not the registered
canonical package, so it has not been silently promoted.

The local-only delivery-status refresh remains `canonical-package` plus
`static-audited-ingress-only`, with no runtime proof or screenshot;
2007/08 remains `provisional-not-playable` and `release_eligible: false`.
No release link was created and the established 2015/16 release was not
altered.  The next smallest action is a read-only review of the existing
hash-bound display-alias repair audit for a canonicalisation decision; it
must keep the canonical package unchanged unless that decision is explicitly
recorded.

## 2007/08 display-alias canonicalisation review (2026-09-08)

The prescribed read-only review of the existing display-alias evidence is now
complete.  The repair audit remains byte-verified at SHA-256
`1e5c676bfde72f87f3373b88dabc31add5c195a082a710e2f213bf8b699e181d`.
It was derived from package SHA-256
`72f8607cd99f2454d31c9c674239fc0b41d719fedd9b48b1091d6ca5983ece38`,
not from the registered canonical package SHA-256
`99a716821f4df36d1b07ef3c8fb6bffdfeb30906df717fc1a9ecc31806ae3308`.
Its alias-bound output has SHA-256
`88e4644fab6c3963da06bd252aa94294a7b16618555b1fdcfdaaec14ef74d14f`.

The audit's `D. Mackie` declaration is identity-safe for the current
canonical `player-10320`: carrier `10320`, person ID, club, source name,
facts, fallbacks, ratings, and proof are identical; only the parser-safe
display name differs from `Darren Mackie`.  However, the cached alias output
changes 3,755 display names and differs from the registered canonical package
in 846 player records even after player names are excluded.  It is therefore
not safe to copy or register as a whole-package replacement.  The alias-repair
unit lane passes (3 tests), and no package, manifest, game tree, release link,
runtime evidence, screenshot, or 2015/16 release file changed.

2007/08 consequently remains `provisional-not-playable` and
`release_eligible: false`; its canonical-package, static-audit, runtime, and
screenshot gates are unchanged.  The next smallest action is to derive a new,
no-overwrite alias candidate directly from the registered canonical package,
verify its receipt and strict validation, then use that candidate for a fresh
canonical-package-bound static compile.  It must not register or call the
derivative playable before those later gates pass.

## 2007/08 canonical-bound display-alias candidate (2026-09-08)

The prescribed no-overwrite alias candidate has been derived directly from the
registered `seasons/2007-08/season-package.json`, not from the older bulk
alias derivative.  Its input package SHA-256 is
`99a716821f4df36d1b07ef3c8fb6bffdfeb30906df717fc1a9ecc31806ae3308`; it
uses verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6` and
the matching 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The new candidate is
`.local/season-canonical-alias-candidate-v1/2007-08-20260908-r1/season-package.alias-bound.json`
(SHA-256 `c1b08d2574e4e31f1cbfcbaa3f577b8516ae7881aded82260f8af2f27ae6a33e`),
with its parser-exercised repair audit at
`.local/season-canonical-alias-candidate-v1/2007-08-20260908-r1/display-alias-repair-audit.json`
(SHA-256 `5b675a480c513124659bd918ac5fc19c2378c2a98c44c5595ada15b0d59dca63`).
Strict V2 validation passes.  The audit records 3,708 parser-safe display-name
changes across the 8,112 writable player carriers; all 1,065
`preserve-existing-mode1` rows remain untouched.  A semantic comparison
confirms that these audited name changes are the only package differences.
For the original blocker, carrier 10320 retains the same person, source name,
facts, fallbacks, ratings, and proof while its display field becomes `D.
Mackie` by the source-derived initial-and-surname rule.

This is explicitly an `alias-bound-static-candidate-only` result and is not
release eligible.  It neither changes the registered canonical package nor
creates a binary materialisation, clean static audit, release manifest, PM99
runtime route, screenshot, or release link.  The generated delivery-status
JSON therefore remains unchanged and 2007/08 remains
`provisional-not-playable`.  The next smallest action is one fresh,
no-overwrite canonical-package-bound static materialisation and clean audit
using this exact candidate; no runtime or playable claim may be made until
the later gates are independently satisfied.

## 2007/08 alias-bound canonical compile blocker: carrier 1 (2026-09-08)

The prescribed fresh static qualification was started only after a new
alias-bound canonical-workspace candidate had verified the registered package,
calendar source-build audit, verified clean base, strict V2 contract,
editorial workspace, and exact display-alias receipt.  The candidate is at
`.local/season-canonical-alias-workspace-v1/2007-08-20260908-r2/`; its
promotion audit SHA-256 is
`e7c0d1d2ad75ae5dd74907ecb5670edbc1991ff1134f448a04aa9c2424572808`.
It binds registered package SHA-256
`99a716821f4df36d1b07ef3c8fb6bffdfeb30906df717fc1a9ecc31806ae3308` to
the alias-only candidate SHA-256
`c1b08d2574e4e31f1cbfcbaa3f577b8516ae7881aded82260f8af2f27ae6a33e`,
with display-alias audit SHA-256
`5b675a480c513124659bd918ac5fc19c2378c2a98c44c5595ada15b0d59dca63`.
Its prepared effective package SHA-256 is
`a30f6737bf089436006561eeb6aa6e66554698be99443e09e1f5cd5ea14dbbe9`.

The single disposable compile against the verified 275-file clean base then
failed closed before any database write, compiler receipt, or clean static
audit.  The exact compiler error was:

```text
mode-1 club carrier 1 changes its fixed roster row count
```

Its incomplete, non-evidence paths are
`.local/season-workspace-v1/2007-08-alias-canonical-compile-20260908-r1-game/`
and `...-r1-build/`; they must not be reused as a compile, audit, release, or
runtime input.  The prepared effective-package file there is byte-identical
to the candidate's prepared file.

Existing hash-bound static-ingress reconciliation evidence identifies the
specific fixed-row cause without inferring a repair: canonical Barcelona
(carrier 1) declares 25 roster carriers while the verified base has 26.  The
missing base row is carrier 16, Luis Enrique, whose whole record is recorded
as `preserve-existing-mode1` in
`.local/season-static-ingress-v1/2007-08-20260905-r1/mode1-roster-reconciliation-audit.json`.
That older reconciled package must not be promoted wholesale: the next
smallest action is a new no-overwrite derivative directly from this exact
alias-bound candidate that restores only carrier 16, followed by strict and
semantic-isolation validation.  No canonical package, status classification,
release link, runtime evidence, screenshot, or 2015/16 release file changed;
2007/08 remains `provisional-not-playable` and `release_eligible: false`.

## 2007/08 alias-bound carrier-1 preservation derivative (2026-09-08)

The prescribed narrow derivative has now been created directly from the
alias-bound candidate at
`.local/season-canonical-alias-candidate-v1/2007-08-20260908-r1/season-package.alias-bound.json`
(SHA-256 `c1b08d2574e4e31f1cbfcbaa3f577b8516ae7881aded82260f8af2f27ae6a33e`).
It remains bound to the verified clean-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6` and
its 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The new no-overwrite candidate is
`.local/season-canonical-alias-roster-candidate-v1/2007-08-20260908-r1/season-package.alias-roster-reconciled.json`
(SHA-256 `26a509e0bc88d16cf9277f5c0aba399e3996514e102f76718ba5665e43df4c17`).
Its reconciliation audit is
`.local/season-canonical-alias-roster-candidate-v1/2007-08-20260908-r1/mode1-roster-reconciliation-audit.json`
(SHA-256 `f3ae2bf23f9b3104003dd124355c031a6ed8047da937aa3701d510538637e4a7`).
It restores exactly the one omitted Barcelona mode-1 base row: carrier 16,
Luis Enrique Martínez García.  The row is a parser-read whole-record
`preserve-existing-mode1` declaration with a static-contract proof and an
unresolved/native-no-photo outcome; it makes no dated source, identity,
ratings, or portrait claim.

Strict V2 validation passes.  A deep semantic-isolation comparison also
passes: relative to the alias-bound input, the only additions are
`players/player-16`, its unresolved portrait declaration, and `player-16` at
the start of `club-1`'s roster, restoring the exact 26-carrier base order.
The registered canonical package remains SHA-256
`99a716821f4df36d1b07ef3c8fb6bffdfeb30906df717fc1a9ecc31806ae3308` and
was not changed.

This is still a static candidate only.  It creates no binary materialisation,
clean static audit, release manifest or link, runtime route, screenshot, or
playable claim, so the generated delivery-status JSON remains unchanged and
2007/08 remains `provisional-not-playable` and `release_eligible: false`.
The next smallest action is one fresh no-overwrite static compile and clean
audit using this exact alias-and-roster candidate against the same verified
base; it must not register the derivative or infer runtime/playable status.

## 2007/08 alias-and-roster static qualification blocker: carrier 10 (2026-09-08)

One fresh, disposable static qualification was attempted from the exact
alias-and-roster candidate at
`.local/season-canonical-alias-roster-candidate-v1/2007-08-20260908-r1/season-package.alias-roster-reconciled.json`
(SHA-256 `26a509e0bc88d16cf9277f5c0aba399e3996514e102f76718ba5665e43df4c17`).
The materialisation tree is
`.local/season-static-qualification-v1/2007-08-alias-roster-20260908-r1/game/`.
The candidate passed strict V2 validation; its registered-package, alias, and
carrier-1 reconciliation lineage remains bound to the verified clean-base
descriptor SHA-256 `512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`
and 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The binary compiler failed closed before issuing a compiler receipt or writing
database records:

```text
mode-1 club carrier 10 changes its fixed roster row count
```

The disposable output tree subsequently re-verified byte-for-byte as that
same clean base.  In particular its JUG, EQ, and ENT SHA-256 values remain
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`,
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`,
and `729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`.
There is consequently no compiler receipt or clean static audit to use as
release or runtime evidence.

The exact fixed-row cause is now bounded: canonical club carrier 10 declares
23 of the base's 30 player carriers, with no extra carriers.  The missing
base rows are 199 (Sebastián Cruzado Fernández, CHANO), 762 (Francisco Javier
López Aguilera, JAVI LÓPEZ), 2067 (DOMINGOS José Paciencia de Oliveira), 4960
(Sergio Martínez BALLESTEROS), 8901 (Fernando NAVARRO MONTOYA), 13018
(Ferdinand Rudols Marcel VIERKLAU), and 17357 (Federico Guillermo LUSSENHOFF).
No package, source intake, manifest, runtime evidence, screenshot, release
link, or 2015/16 release file changed. 2007/08 remains
`provisional-not-playable` and `release_eligible: false`; the generated status
JSON remains correctly unchanged because no qualifying static audit exists.

The next smallest action is one new, no-overwrite whole-row preservation
derivative directly from this exact alias-and-roster candidate for carrier 10
only, using its existing static-contract source/artifact bindings.  It must
restore precisely those seven rows in base order, pass strict and semantic
isolation validation, and make no dated source, ratings, identity, portrait,
runtime, or playable claim.

## 2007/08 alias-and-roster carrier-10 preservation derivative (2026-09-08)

The prescribed no-overwrite derivative has been created directly from the
alias-and-carrier-1 candidate at
`.local/season-canonical-alias-roster-candidate-v1/2007-08-20260908-r1/season-package.alias-roster-reconciled.json`
(SHA-256 `26a509e0bc88d16cf9277f5c0aba399e3996514e102f76718ba5665e43df4c17`).
It is bound to the verified clean-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6` and
the matching 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The new static candidate is
`.local/season-canonical-alias-roster-carrier10-candidate-v1/2007-08-20260908-r1/season-package.alias-roster-carrier10-reconciled.json`
(SHA-256 `d08e975e245224c6ac0bc6865c12af45388e58f622f050166f1bbd8cf5bea0ad`).
Its reconciliation audit is SHA-256
`d5d2ff6f73af4d99ef5504361a51f3255266e86712a31ec8d4cc5549d2b0c83c`.
It restores precisely the seven omitted carrier-10 base rows in parser-backed
base order: 199 (Sebastián Cruzado Fernández, CHANO), 762 (Francisco Javier
López Aguilera, JAVI LÓPEZ), 2067 (DOMINGOS José Paciencia de Oliveira), 4960
(Sergio Martínez BALLESTEROS), 8901 (Fernando NAVARRO MONTOYA), 13018
(Ferdinand Rudols Marcel VIERKLAU), and 17357 (Federico Guillermo LUSSENHOFF).
Every row is a parser-read whole-record `preserve-existing-mode1` declaration
with a `static-contract` proof and unresolved/native-no-photo outcome; none is
a dated source, identity, ratings, or portrait claim.

Strict V2 validation passes. A semantic-isolation comparison also passes:
aside from those seven player and unresolved-portrait declarations, all
pre-existing player, club, and portrait declarations are byte-for-byte
equivalent; carrier 10's non-roster metadata is unchanged and its roster is
the exact 30-row base order. The registered canonical package remains
unchanged. This creates no binary materialisation, clean audit, release
manifest or link, runtime route, screenshot, or playable claim. The generated
delivery-status JSON is correctly unchanged: 2007/08 remains
`provisional-not-playable` and `release_eligible: false`.

The next smallest action is one fresh no-overwrite static compile and clean
audit using this exact carrier-10 derivative against the same verified base.
It must not register the derivative or infer runtime/playable status.

## 2007/08 alias-and-roster carrier-10 static qualification (2026-09-08)

The prescribed fresh static ingress has completed in the new, no-overwrite
directory
`.local/season-static-qualification-v1/2007-08-alias-roster-carrier10-20260908-r2/`.
It consumed the exact carrier-10 preservation derivative
`.local/season-canonical-alias-roster-carrier10-candidate-v1/2007-08-20260908-r1/season-package.alias-roster-carrier10-reconciled.json`
(SHA-256 `d08e975e245224c6ac0bc6865c12af45388e58f622f050166f1bbd8cf5bea0ad`)
against the verified clean-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6` and
its 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The reusable ingress performed its existing, deterministic source-write-policy,
display-alias, and whole-row-preservation stages before compilation.  Its final
static-only package has SHA-256
`79f797fb00d074896cd31f3d5a3c7e2ac65ddb72d94d4818d0e9133d86e7ab8d`.
The source-write-policy stage changed 846 eligible source-bound declarations,
the alias stage changed 454 parser-safe display names, and the preservation
stage covered 75 eligible mode-1 clubs.  These are generated static-contract
repairs, not new dated-source, ratings, identity, or portrait claims.

The compiler receipt SHA-256 is
`a01e1b01df84b201038f539689ff12b263ee375be3c44b3292dcfdc35b1a8642`.
The clean static audit SHA-256 is
`18aeaf5b4f817019fa801d14337eac5103785ad8a49dcb0d53bf0e50fbb12435` and
reports `result: pass`: 8,958 player carriers, 432 club carriers, and 174
manager carriers changed; all 451 fixed roster tails match; append/recycle and
derived-mode-0-donor mismatch counts are zero.  The static-ingress receipt is
SHA-256 `264e87a78248feaac389e7aedfb4d0d9cdb98bc3369baa899d9fc02b4f0b88d6`.

This closes the current carrier-layout static frontier for this exact derived
candidate only.  It is still `clean-static-ingress-complete-not-playable` and
`release_eligible: false`: the registered canonical package was not changed,
and no release manifest or link, calendar/runtime validation, asset
materialisation, PM99 route, or bound screenshot was created.  The generated
delivery-status JSON remains conservatively unchanged because its static-ingress
reader does not index this separate qualification root.  A prior interrupted
`...-r1/` directory contains only a source-policy intermediate and must not be
used as evidence.  The next smallest action is a read-only review of the three
`r2` repair receipts for a canonicalisation decision; it must not register this
derived package or infer runtime/playable status.

## 2007/08 `r2` static-repair canonicalisation review (2026-09-08)

The prescribed read-only review of
`.local/season-static-qualification-v1/2007-08-alias-roster-carrier10-20260908-r2/`
is complete. The source-write-policy, display-alias, and roster receipts have
SHA-256 values
`ea4fc6e47d7be39df3e568933b86582b5eb80144fb7065fe756b73f247d030e5`,
`0164e4c3bb6a42e8f773ab34cf9db85ffa1631620ee4d7b277be450487e5e65c`,
and `ce0c6fa4020ce7f288a08dbdae24d75bf239d442e6b048aceeeccaccea0ab5d6`,
respectively. Their package chain is continuous: carrier-10 input
`d08e975e245224c6ac0bc6865c12af45388e58f622f050166f1bbd8cf5bea0ad`,
then source-writable `84e5a29f5d344322058a488878c95680b1b1d2f6cbe98c8b6da4efa064d52197`,
alias-bound `261d096d1f210c1979d45a49a46f3fc4b6ff06a5977f13c28a8fd5bf5a62422b`,
and reconciled `79f797fb00d074896cd31f3d5a3c7e2ac65ddb72d94d4818d0e9133d86e7ab8d`.
Every stage remains bound to verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6` and
its 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The package delta is narrowly classified but material: 846 source-bound
mode-1 players lose only the whole-record preserve policy (retaining their
declared fallback fields); 4,162 existing player records change only their
parser-safe display name; and the final package adds 177 preserved base rows
while changing 77 club rosters (two shared-preserve lists also change). No
existing player facts, ratings, person identities, source proofs, or portrait
claims change. The roster stage records 75 eligible clubs and 170 restored
rows, of which 169 are `preserve-existing-mode1` and one is an already
preserved shared base row. It performs no source acquisition or manifest
change.

The exact reconciled package passes strict V2 validation. Its compiler receipt
(SHA-256 `a01e1b01df84b201038f539689ff12b263ee375be3c44b3292dcfdc35b1a8642`)
and clean static audit (SHA-256
`18aeaf5b4f817019fa801d14337eac5103785ad8a49dcb0d53bf0e50fbb12435`) agree
on the reconciled hash; the audit passes with 8,958 player, 432 club, and 174
manager carrier changes, zero append/recycle and derived-donor mismatches, and
all 451 fixed roster tails preserved.

This review clears the evidence for a separate, explicitly recorded canonical
promotion decision, but is not that decision: the registered canonical package
and all release/runtime classifications remain unchanged. 2007/08 is still
`provisional-not-playable` and `release_eligible: false`; no release link,
runtime route, screenshot, source manifest, or 2015/16 release file changed.
The generated delivery-status JSON remains unchanged because it does not index
this unregistered static-qualification root. The next smallest action is an
explicit canonical-promotion decision that records this exact three-receipt
chain before any registration; it must retain the static evidence and cannot
infer asset, runtime, screenshot, or playable gates.

## 2007/08 `r2` static-repair canonical-promotion decision (2026-09-08)

The exact repair chain has passed the required canonical-promotion decision
review.  The decision permits a later, separate registration of only the
reconciled package at
`.local/season-static-qualification-v1/2007-08-alias-roster-carrier10-20260908-r2/season-package.reconciled.json`
(SHA-256 `79f797fb00d074896cd31f3d5a3c7e2ac65ddb72d94d4818d0e9133d86e7ab8d`).
It does not itself register that file or replace the existing canonical
package.

The approved chain is continuous and bound throughout to verified-base
descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6` and
275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`:

- carrier-10 input `d08e975e245224c6ac0bc6865c12af45388e58f622f050166f1bbd8cf5bea0ad`;
- source-write-policy receipt `ea4fc6e47d7be39df3e568933b86582b5eb80144fb7065fe756b73f247d030e5`,
  producing `84e5a29f5d344322058a488878c95680b1b1d2f6cbe98c8b6da4efa064d52197`;
- display-alias receipt `0164e4c3bb6a42e8f773ab34cf9db85ffa1631620ee4d7b277be450487e5e65c`,
  preserving the calendar contract and producing
  `261d096d1f210c1979d45a49a46f3fc4b6ff06a5977f13c28a8fd5bf5a62422b`;
- roster-reconciliation receipt
  `ce0c6fa4020ce7f288a08dbdae24d75bf239d442e6b048aceeeccaccea0ab5d6`,
  producing the approved reconciled package.

Strict V2 validation passes for the approved bytes.  Its compiler receipt
`a01e1b01df84b201038f539689ff12b263ee375be3c44b3292dcfdc35b1a8642` and
clean static audit `18aeaf5b4f817019fa801d14337eac5103785ad8a49dcb0d53bf0e50fbb12435`
agree on that package; the audit passes with all 451 fixed roster tails
unchanged and zero append/recycle or derived-mode-0 donor mismatches.

This decision closes no release gate by itself.  The registered 2007/08
package, generated delivery-status JSON, release eligibility, runtime status,
and 2015/16 release remain unchanged; 2007/08 is still
`provisional-not-playable`.  The next smallest action is a separate,
no-overwrite registration of exactly the approved reconciled bytes, retaining
the recorded receipt chain and without making any asset, runtime, screenshot,
or playable claim.

## 2007/08 approved repaired-package registration (2026-09-08)

The approved repaired package has now been registered at
`seasons/2007-08/season-package.json`.  Its SHA-256 is
`79f797fb00d074896cd31f3d5a3c7e2ac65ddb72d94d4818d0e9133d86e7ab8d`,
exactly matching the reconciled output approved by the preceding promotion
decision.  Strict V2 validation passes for the registered bytes.

A local-only delivery-status refresh now binds the canonical-package record to
that new hash.  This registration does not make the separate static
qualification root canonical-package-bound, so the season remains
`provisional-not-playable`.  Its open published gates are a canonical
package-bound clean static compile/audit, a successful runtime route, and a
bound runtime screenshot.  The established 2015/16 release database and
portrait hashes remain unchanged, and no release link, game tree, source
manifest, runtime artifact, or screenshot was created or changed.

The next smallest action is a fail-closed canonical-package binding for the
existing `r2` compiler receipt and clean static audit.  It must prove the
registered hash and full three-receipt repair chain before closing the static
gate, without rebuilding or inferring runtime or playable status.

## 2007/08 canonical-package static-chain binding (2026-09-08)

The delivery-status reader now verifies the existing `r2` static qualification
as a complete canonical-package-bound chain. It requires the source-write-policy,
display-alias, and roster-reconciliation receipts to form a continuous package
hash chain from input
`d08e975e245224c6ac0bc6865c12af45388e58f622f050166f1bbd8cf5bea0ad`
to the registered canonical package
`79f797fb00d074896cd31f3d5a3c7e2ac65ddb72d94d4818d0e9133d86e7ab8d`.
Every stage must retain the same verified-base descriptor hash, and its output
file is re-hashed before the compiler receipt, three database outputs, and
passing clean audit are accepted.

The local-only status refresh consequently records
`static-audited-canonical-package` with evidence state
`verified-canonical-package-bound-static-repair-chain`. This closes the
canonical package-bound clean static compile/audit gate for 2007/08. The season
remains `provisional-not-playable` and `release_eligible: false`; the two open
published gates are a successful PM99 runtime route and a screenshot bound to
that route. No package, manifest, game tree, release link, runtime artifact,
screenshot, or 2015/16 release file changed.

The next smallest action is a successful PM99 runtime route against the exact
qualified 2007/08 game tree, followed by a screenshot attestation bound to its
canonical package and database hashes. It must not create a playable claim
until both runtime gates verify.

## 2007/08 exact static-tree runtime probe (2026-09-08)

The prescribed bounded route was run through the protected PM99 runner with
the exact DBDAT and `MANAGPRE.EXE` from
`.local/season-static-qualification-v1/2007-08-alias-roster-carrier10-20260908-r2/game/`.
The run tag is
`post1999_2007_08_exact_qualified_runtime_20260908_r1`; its control manifest
records the hash-verified disposable `DBDAT`/executable overrides.  The local
artifact directory is
`.local/season-runtime-evidence-v1/post1999_2007_08_exact_qualified_runtime_20260908_r1/`.

The route completed successfully through `return_from_line_up`, with
`crash_detected: false` and `wine_debugger_detected: false`.  Its summary is
100,171 bytes with SHA-256
`fd19046489b0973818910e3e3831a84807705bc992b116074f81e3b2b5201e10`.
The retained final route screenshot
`screens/029_return_from_line_up.png` is 295,272 bytes with SHA-256
`41985b07cebcec1e36161d60fb5245a45819b1a8afd0001edc17688aa5b5cfdd`.

This probe does not yet close a release gate.  The exact static qualification
tree carries `MANAGPRE.EXE` SHA-256
`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158`, while
the hash-bound 2007/08 target calendar executable is
`8b6de10ebbcbdfdb27b598806971e0c4887a00f0eeebb3568dcfb0089374edf3`.
The route therefore proves PM99 navigation for the qualified static database
tree only; its screenshot is not a target-calendar-bound release attestation.
No package, manifest, game tree, release link, or 2015/16 release file
changed, and `.local/operations/season-delivery-status.json` remains unchanged:
2007/08 is still `provisional-not-playable` with runtime and screenshot gates
open.  The next smallest action is a fresh target-calendar-bound runtime route
using the same qualified database files and the hash-bound calendar executable,
then a fail-closed screenshot attestation against all three hashes.

## 2007/08 target-calendar runtime attestation (2026-09-08)

The prescribed single target-calendar-bound route completed against the exact
qualified r2 database files, using the existing target calendar executable
`.local/calendar-v1/2007-08/MANAGPRE.EXE` (SHA-256
`8b6de10ebbcbdfdb27b598806971e0c4887a00f0eeebb3568dcfb0089374edf3`).  The
run tag is
`post1999_2007_08_target_calendar_runtime_20260908_r1`, and its summary at
`.local/season-runtime-evidence-v1/post1999_2007_08_target_calendar_runtime_20260908_r1/summary.json`
has SHA-256
`053f08dc1ee34a18dde64cf94a69e29ccf92968cca0871c0a3b0974858fa059c`.
It reports `success: true`, `crash_detected: false`,
`wine_debugger_detected: false`, and phase `return_from_line_up`.  The squad
route's expected screen and route signal both matched.  The line-up screen
matched its expected screen, although its secondary route signal was false;
the bound proof therefore uses the squad-route screenshot
`screens/025_return_from_squad.png` (SHA-256
`ecf0658508a92ea62a4c8e67105eb1a97fab4a245f471cf91c8aebff2d1c18e0`).

The new fail-closed attestation is
`.local/season-runtime-evidence-v1/post1999_2007_08_target_calendar_runtime_20260908_r1/runtime-attestation.json`
(SHA-256
`75251dd592fd1903193f345449cf2c781b5b2c89c72b6152c1f418ac47dca405`).  It
re-verifies the registered canonical package SHA-256
`79f797fb00d074896cd31f3d5a3c7e2ac65ddb72d94d4818d0e9133d86e7ab8d`, the
passing static compiler/audit chain, all compiled database hashes, the exact
launch manifest, the target calendar hash, and the bound screenshot.  The
status reader now accepts this one registered attestation only after those
hashes and route conditions re-check successfully; it does not infer a
release link or mutate any package or game tree.

The local status refresh consequently moves 2007/08 from
`provisional-not-playable` to `playable-known-good`.  The programme summary
now records playable target seasons `2007-08` and `2008-09` in addition to the
established `2015-16` release.  This is not a release-eligibility promotion:
`seasons/2007-08/season-package.json` still records `release_eligible: false`,
there is no immutable 2007/08 release link, and the existing static-ingress
receipt still names target-season manager, kit, portrait/no-photo, ratings,
and opening-XI/formation work as open release work.  The qualified static
tree's embedded executable also remains the pre-target-calendar hash; the
attested route used the target calendar as a disposable executable override.

The next smallest action is a read-only review of the existing 2007/08
manager/kit/portrait/rating and opening-XI receipts to select one deterministic
cached release-blocker repair, beginning with the target-season manager-source
review.  Do not register a release link until those package-level gates are
closed.

## 2007/08 allocated-manager cache triage (2026-09-08)

The bounded manager-source review has now checked the selected `manager-v2`
overlay and every existing allocated-manager receipt against the current
2007/08 source and carrier-allocation hashes.  Its read-only receipt is
`.local/operations/2007-08/manager-gap-triage-20260908.json` (SHA-256
`3559b078ee203a3dfeb12a2d692ff65e45277e7c401a409df946dbbe90ae4dc8`).

The exact current allocation has 239 carriers.  It leaves 86 manager gaps;
all 86 are `genuinely-uncaptured`, with zero already-captured candidates and
zero conflicting dated candidates.  The triage therefore found no safe cached
manager integration to apply and deliberately performed no web fetch, manager
selection, overlay write, package write, compilation, or release action.  The
selected manager ledger and inputs remain hash-bound, including ledger
`7677bd4310e112a514abe3efd875b22cd0e0759809db598e121133eb09b34a12` and
current source `b4d8fb5e27123c0eb3ffdf1b1459443142fae8cc53f2d775e1b4415fa2367490`.

2007/08 therefore has no eligibility movement: it remains
`playable-known-good` but `release_eligible: false`, with manager, kit,
portrait/no-photo, ratings, opening-XI/formation, and immutable-release work
still open.  The generated delivery-status JSON, registered package, runtime
evidence, and established 2015/16 release were unchanged.  The next smallest
action is a new, explicitly scoped source-acquisition decision for one of the
86 genuinely uncaptured allocated managers; no manager name may be inferred
from native/current data.

## 25-season kit-cache provenance triage (2026-09-08)

One read-only, cache-only kit-requirement triage was run against the current
25-season allocation pointers, the retained historical kit source chains, and
their render receipts.  Its new receipt is
`.local/operations/season-kit-requirement-triage-20260908.json` (SHA-256
`84a0c105b09442c5b0ed1c7f0fb88aaccb62be1cab35f3687c0e799864794a91`).

The receipt covers 10,351 allocated requirements across 25 seasons.  The
current fail-closed classification is 10,351 `conflicting`, 0
`rendered-and-bound`, 0 `captured-but-unrendered`, 0 `renderable-but-unbound`,
and 0 `genuinely-uncaptured`, with zero current seasons clean.  The exact
provenance failure is that every retained capture chain disagrees with its
current revision/allocation hashes, so the triage found zero safe automated
integration candidates.  The stale-artifact diagnostic still records 97
rendered-and-bound, 1,632 captured-but-unrendered, 365 conflicting, and 8,257
genuinely-uncaptured retained requirements; these are backlog diagnostics, not
current release evidence.

For 2007/08, the 427 current requirements are all fail-closed by the stale
capture provenance.  The retained-artifact diagnostic is 1 rendered-and-bound,
30 captured-but-unrendered, 20 conflicting, and 376 genuinely uncaptured.
This changes no package, asset archive, game tree, runtime evidence, release
link, or 2015/16 release, and 2007/08 remains `playable-known-good` but
`release_eligible: false`.  The next smallest action is one no-overwrite
revalidation of a single retained 2007/08 kit capture against the current
allocation before considering any kit integration; no stale artifact may be
promoted by carrier number alone.

## 2007/08 single-carrier kit revalidation (2026-09-08)

The prescribed bounded revalidation completed for the sole 2007/08 retained
artifact that was diagnostically `rendered-and-bound`: carrier 417, VfL
Bochum.  It used the current pointer revision
`rev-148b3e047f3828abd5ad`, whose allocation file SHA-256 is
`b70ec57250df934e1a1bf1ecb4bbe8a1dbfc523a706282c752e854bd8aa766b7`, and
created only the new root
`.local/season-kit-revalidation-v1/2007-08-vfl-bochum-20260908-r1/`.

The existing content-addressed Wikipedia cache was replayed offline.  The
fresh source capture found the same exact page identity as the retained
capture: page `47663327`, title `2007–08 VfL Bochum season`, revision
`1307457765`, and cached source object SHA-256
`8d9272022c58c27e6c0545a1b90fb78589531f721eb6c63ec74dfd7cf50b42b8`.
The fresh chunk plan, source capture, subset allocation, catalogue request,
and catalogue are recorded by the validation receipt at
`.local/season-kit-revalidation-v1/2007-08-vfl-bochum-20260908-r1/kit-chunk-validation-receipt-v1.json`
(SHA-256
`b58c5dcc38e5294a6327c480e9b94e788eed0be3f729cae90b6db7e6ae22e250`).

The fresh source-ready row rendered one carrier-bound set of three compact-kit
artifacts, and the write-once archive stage materialised three corresponding
archive events.  The validation result is `chunk-validated-not-release` with
one fresh revision-pinned source, one rendered carrier, zero source gaps, zero
render gaps, and `release_eligible: false`.  Its exact render and archive
receipts remain under the same revalidation root; the archive-stage receipt is
SHA-256
`27f128073f919222dfd1e80ad5a533875087b5cc507c171f30f5e108cc336264`.

This closes current-allocation-bound evidence for this one kit requirement
only.  It does not update the season kit roots, canonical package, status JSON,
game tree, release link, or established 2015/16 release.  2007/08 remains
`playable-known-good` under the existing package/static/runtime/screenshot
gate, but remains `release_eligible: false`; season-wide kit materialisation
and the separate package/release integration gates remain open.  The next
smallest action is a separately reviewed disposable game-tree integration of
this exact current kit archive stage, without changing the canonical package
or any release tree.

## 2007/08 single-carrier kit game-tree integration (2026-09-08)

The reviewed disposable integration of the exact current-allocation-bound VfL
Bochum stage completed at
`.local/season-kit-integration-v1/2007-08-vfl-bochum-20260908-r1/`.  It copied
the qualified 2007/08 static tree, then used the existing carrier-kit patcher
to apply carrier 417 (`EQ960417.BMP`) from the three-archive revalidation stage.
The stage was built from a different clean archive baseline, so whole-archive
replacement was deliberately not used; the patcher matched the carrier's
existing offsets and bitmap shapes and changed only its bound payloads.

The copy receipt
`.local/season-kit-integration-v1/2007-08-vfl-bochum-20260908-r1/carrier-kit-art-copy.json`
has SHA-256
`8bfbcae16dc04464d192bf0911f8bc046585c1f7f816b403e3933cf5e84f22b8` and
records 1,661, 419, and 197 changed bytes in `MINIESC.PKF`, `NANOESC.PKF`,
and `RIDIESC.PKF`, respectively.  The persistent integration audit is
`.local/season-kit-integration-v1/2007-08-vfl-bochum-20260908-r1/game-tree-kit-integration-audit.json`
with SHA-256
`cb0630f428155a5a43cfd57f873770dd926724eb4819864230a81c78ae85e47d`.
It verifies all 275 tree files, 272 unchanged non-kit files, no archive
resize, and no changes outside the three bound bitmap payloads.

This remains `pass-not-release` and `release_eligible: false`: it does not
materialise season-wide kits, alter the canonical package or status JSON,
create runtime evidence, create a screenshot, create a release link, or alter
the established 2015/16 release. 2007/08 remains `playable-known-good` only
under its prior package/static/runtime/screenshot attestation. The next
smallest action is a separate review of this single-carrier integration before
selecting another current-allocation kit requirement; no stale archive may be
promoted by carrier number alone.

## 2007/08 single-carrier kit integration review (2026-09-08)

The bounded review of the disposable VfL Bochum carrier-417 integration is
recorded at `.local/operations/2007-08/kit-integration-review-20260908.json`.
It re-hashed the exact qualified-baseline and integration trees: both contain
275 files, their relative file sets are identical, all 272 non-kit files are
byte-identical, and the three changed kit archives match the carrier-copy
receipt's declared before/after hashes.  The review also confirms the copy
receipt's all-archives-patched, source-bitmap-equality, and no-resize checks.

This is accepted as `pass-not-release` evidence for one current-allocation
carrier only.  It does not materialise season-wide kits, alter the canonical
package or generated delivery-status JSON, create runtime evidence, or close
immutable release registration. 2007/08 remains `playable-known-good` but
`release_eligible: false`, with no eligibility movement.  The next smallest
action is a separately reviewed or revalidated current-allocation kit
requirement; stale artifacts must not be promoted by carrier number alone.

## 2007/08 Piacenza single-carrier kit revalidation (2026-09-08)

The next bounded current-allocation revalidation completed for carrier 219,
Piacenza, under the new write-once root
`.local/season-kit-revalidation-v1/2007-08-piacenza-20260908-r1/`. The frozen
chunk selects only carrier 219 and binds to subset-allocation SHA-256
`12fb777f7b26c13ad5ac76a344873a1291d2afd7b59baa6c5161f3f34eb23680` and the
current full allocation SHA-256
`b70ec57250df934e1a1bf1ecb4bbe8a1dbfc523a706282c752e854bd8aa766b7`.

Offline source replay found the retained exact page `2007–08 Piacenza Calcio
season`, page `72546566`, revision `1324881771`, with home-kit fields ready.
The fresh source capture and catalogue then rendered one carrier-bound set of
three compact-kit artifacts using the existing cached `Kit_body_collarwhite`
layer (SHA-256
`e059323a2f9fb38f73567caf4706d5fa03d5e57f92e3bd82f933cc0ac2a8aab7`); the
left- and right-arm pattern fields were explicitly empty in the source
contract.

The fail-closed validation receipt is
`.local/season-kit-revalidation-v1/2007-08-piacenza-20260908-r1/kit-chunk-validation-receipt-v1.json`
(SHA-256
`a5ed2d3fe4c8951665429b986e4cbdcdc3b8a1d798d8602872a9114e554cc7f6`). It
reports `chunk-validated-not-release`, one fresh revision-pinned source, one
rendered carrier, three archive events, zero source gaps, and zero render
gaps. The separate archive-stage receipt is SHA-256
`ce08b3c8131c61f64b164997536866c750dca4d09ac46e108091f876aed090e8`.

This adds current-allocation-bound kit evidence for Piacenza only. It does not
update the canonical package or status JSON, copy an archive stage into a game
tree, create runtime or screenshot evidence, create a release link, or alter
the established 2015/16 release. 2007/08 remains `playable-known-good` under
the existing package/static/runtime/screenshot gate but `release_eligible:
false`, with no eligibility movement. The next smallest action is a separate
review of this Piacenza archive stage before any disposable game-tree
integration; no season-wide kit promotion is implied.

## 2007/08 Piacenza single-carrier kit archive-stage review (2026-09-08)

The prescribed read-only review is recorded at
`.local/operations/2007-08/piacenza-kit-archive-stage-review-20260908.json`.
Its SHA-256 is
`62e81a07c9e07ef408e842152341fd904cb029aaa8aa14e029c0ee3ac990535b`. It
re-verifies the current 2007/08 full-allocation hash
`b70ec57250df934e1a1bf1ecb4bbe8a1dbfc523a706282c752e854bd8aa766b7`, its
carrier-219 Piacenza assignment, the fresh revision-pinned source page
`2007–08 Piacenza Calcio season` (page `72546566`, revision `1324881771`),
and the revalidation receipt SHA-256
`a5ed2d3fe4c8951665429b986e4cbdcdc3b8a1d798d8602872a9114e554cc7f6`.

The staged archive receipt remains byte-verified at SHA-256
`ce08b3c8131c61f64b164997536866c750dca4d09ac46e108091f876aed090e8`.
All three rendered artifact bindings match its declared carrier-219 events;
the staged archives have their expected after hashes, no resize, and changes
only within their declared kit-pixel ranges: 622 bytes in `MINIESC.PKF`, 151
in `NANOESC.PKF`, and 60 in `RIDIESC.PKF`. Crucially, all three stage-before
hashes exactly match the already qualified 2007/08 static tree, so the stage
is an approved input to one future disposable tree integration without an
archive-baseline conversion.

This is `approved-for-disposable-integration-not-release` evidence for one
current-allocation carrier. It does not alter a package, game tree, runtime or
screenshot, release link, generated delivery-status JSON, or the 2015/16
release. 2007/08 remains `playable-known-good` but `release_eligible: false`;
season-wide kits and the other package-level release blockers remain open.
The next smallest action is one new disposable copy of the qualified static
tree that applies only carrier 219's three reviewed archive payloads, followed
by a no-out-of-scope-change audit.

## 2007/08 Piacenza single-carrier kit game-tree integration (2026-09-09)

The reviewed carrier-219 Piacenza archive stage has been applied once to a new,
disposable copy of the qualified 2007/08 static tree at
`.local/season-kit-integration-v1/2007-08-piacenza-20260909-r1/game/`.
The input stage remained the reviewed current-allocation stage at
`.local/season-kit-revalidation-v1/2007-08-piacenza-20260908-r1/`; its three
before-archive hashes match the qualified tree exactly.

The bounded carrier patcher changed only the existing `EQ960219.BMP` payloads
in `MINIESC.PKF`, `NANOESC.PKF`, and `RIDIESC.PKF`: 622, 151, and 60 bytes,
respectively.  Each target bitmap read back byte-identical to its
revision-pinned staged artifact, and no archive was resized.  The patcher
receipt is
`.local/season-kit-integration-v1/2007-08-piacenza-20260909-r1/carrier-kit-art-copy.json`
(SHA-256 `619662f7d09ce34ef38dcb227e636db7b042d89d8cdafa9ee4111a5e46c30ed9`).

The integration adapter at
`.local/season-kit-integration-v1/2007-08-piacenza-20260909-r1/kit-application-receipt.json`
(SHA-256 `94ea6ef84f4a8136538927319c2a0a5350b443790107a276579c59d32cf21f80`)
binds the carrier-copy receipt, reviewed archive stage, and all five expected
archive hashes.  The independent no-out-of-scope audit at
`.local/season-kit-integration-v1/2007-08-piacenza-20260909-r1/game-tree-kit-only-audit.json`
(SHA-256 `abe0f7931bcc3697bfafea552df309b888f0acc3b6473c530d6b30aa4b701184`)
passes: its 275-file baseline/target sets agree, all 270 non-kit files are
byte-identical, all five kit archive hashes match the bound expectations, and
all three declared Piacenza events read back with zero errors.

This is `pass-not-release` evidence for a second current-allocation 2007/08
kit carrier only.  It does not alter a canonical package, source manifest,
status JSON, runtime evidence, screenshot, release link, or the established
2015/16 release.  2007/08 remains `playable-known-good` but
`release_eligible: false`; season-wide kit materialisation and the separate
manager, portrait/no-photo, ratings, opening-XI/formation, and immutable
release gates remain open.  The next smallest action is a bounded read-only
review of this Piacenza integration before selecting another current-allocation
kit requirement.

## 2007/08 Piacenza single-carrier kit integration review (2026-09-09)

The prescribed bounded review is recorded at
`.local/operations/2007-08/piacenza-kit-integration-review-20260909.json`.
It re-verifies the qualified compiler receipt (SHA-256
`a01e1b01df84b201038f539689ff12b263ee375be3c44b3292dcfdc35b1a8642`), clean
static audit (SHA-256
`18aeaf5b4f817019fa801d14337eac5103785ad8a49dcb0d53bf0e50fbb12435`),
current-allocation revalidation, reviewed archive stage, carrier-copy receipt,
integration adapter, and independent kit-only audit. Every named input was
re-hashed successfully.

The qualified and integration trees each contain 275 files. All 270 non-kit
files are byte-identical, including the three database files and
`MANAGPRE.EXE`; the three Piacenza kit archives retain their sizes. Their
stage-before hashes match the qualified tree, stage-after hashes match the
integration tree, and all three `EQ960219.BMP` payloads re-read byte-identical
to their staged artifacts. No changes outside the declared kit pixels were
accepted.

This is `pass-not-release` evidence for a second current-allocation kit
carrier only. It changes no canonical package, delivery-status JSON, runtime
attestation, screenshot, release link, or established 2015/16 release.
2007/08 remains `playable-known-good` but `release_eligible: false`; its
season-wide kit, manager, portrait/no-photo, ratings, opening-XI/formation,
and immutable-release gates remain open. The next smallest action is to
separately review or revalidate one further current-allocation 2007/08 kit
requirement, without promoting stale evidence by carrier number alone.

## 2007/08 Monaco single-carrier kit revalidation (2026-09-09)

One further current-allocation kit requirement has been revalidated entirely
from existing local caches, in the new write-once root
`.local/season-kit-revalidation-v1/2007-08-monaco-20260909-r2/`. It freezes
only carrier 505, Monaco, from the current allocation SHA-256
`b70ec57250df934e1a1bf1ecb4bbe8a1dbfc523a706282c752e854bd8aa766b7`.
The fresh cache replay re-verified `2007–08 AS Monaco FC season`, page
`47918600`, revision `1369055792`, and source object SHA-256
`1ef1a3e0b332bbbbca5270f8eac1f866a9e46ae594671c55a9eedabdd500f86b`.

The source-ready contract rendered all three carrier-bound compact-kit
artifacts using the existing exact cached layers `Kit_body_asm10h`
(SHA-256 `e2c532940429e09469d6ac02a52bdc0aeb673c9b3caf9d45d14407bd120db024`)
and `Kit_right_arm_thinwhiteborder` (SHA-256
`807baaa17199940f1c456808f35a15211d4e7aec1d710d4bf6d55f3e6cd8ea45`).
The three archive events apply only `EQ960505.BMP` in `MINIESC.PKF`,
`NANOESC.PKF`, and `RIDIESC.PKF`; their archive-stage receipt SHA-256 is
`bed9ef6442cd5a33e04e1d3e0a22cd9ddb6f732ad6fbe78ac5bddae2e94c0222`.
The fail-closed validation receipt is
`.local/season-kit-revalidation-v1/2007-08-monaco-20260909-r2/kit-chunk-validation-receipt-v1.json`
(SHA-256 `570edbc2ea676bacaf02efd2b671b715af3877fd8d9fd105ba0fdcdd87f1636a`):
it reports one fresh revision-pinned source, one rendered carrier, three
archive events, and zero source or render gaps.

An earlier `...-r1/` attempt used a cache root without Monaco's retained page
object and failed closed before archive materialisation or validation; it is
not evidence and was not reused or overwritten. The successful `r2` result is
`chunk-validated-not-release` and `release_eligible: false`. It changes no
canonical package, generated delivery-status JSON, game tree, runtime proof,
screenshot, release link, or established 2015/16 release. 2007/08 therefore
remains `playable-known-good` but not release-eligible; season-wide kits and
the manager, portrait/no-photo, ratings, opening-XI/formation, and immutable
release gates remain open. The next smallest action is a bounded read-only
review of this Monaco archive stage before considering one disposable
single-carrier game-tree integration.

## 2007/08 Monaco single-carrier kit archive-stage review (2026-09-09)

The prescribed read-only review is recorded at
`.local/operations/2007-08/monaco-kit-archive-stage-review-20260909.json`.
It re-verifies the current 2007/08 full-allocation hash
`b70ec57250df934e1a1bf1ecb4bbe8a1dbfc523a706282c752e854bd8aa766b7`, its
carrier-505 Monaco assignment, and the fresh revision-pinned source page
`2007–08 AS Monaco FC season` (page `47918600`, revision `1369055792`). The
source capture, catalogue, render bindings, render receipt, chunk-validation
receipt, and archive-stage receipt all re-hash to their recorded values.

The staged archive receipt remains byte-verified at SHA-256
`bed9ef6442cd5a33e04e1d3e0a22cd9ddb6f732ad6fbe78ac5bddae2e94c0222`.
All three rendered artifact bindings match its declared carrier-505 events;
the staged archive before hashes exactly match the qualified 2007/08 static
tree. Each archive keeps its original size and changes only inside its
declared kit-pixel range: 602 bytes in `MINIESC.PKF`, 164 in `NANOESC.PKF`,
and 78 in `RIDIESC.PKF`.

This is `approved-for-disposable-integration-not-release` evidence for one
current-allocation carrier. It does not alter a package, game tree, runtime or
screenshot, release link, generated delivery-status JSON, or the 2015/16
release. 2007/08 remains `playable-known-good` but `release_eligible: false`;
season-wide kits and the other package-level release blockers remain open.
The next smallest action is one new disposable copy of the qualified static
tree that applies only carrier 505's three reviewed archive payloads, followed
by a no-out-of-scope-change audit.

## 2007/08 Monaco single-carrier kit game-tree integration (2026-09-09)

The reviewed carrier-505 Monaco archive stage has been applied once to a new,
disposable copy of the qualified 2007/08 static tree at
`.local/season-kit-integration-v1/2007-08-monaco-20260909-r1/game/`.
The exact reviewed stage remains
`.local/season-kit-revalidation-v1/2007-08-monaco-20260909-r2/`; its three
before-archive hashes match the qualified tree exactly.

The bounded carrier patcher changed only the existing `EQ960505.BMP` payloads
in `MINIESC.PKF`, `NANOESC.PKF`, and `RIDIESC.PKF`: 602, 164, and 78 bytes,
respectively. Each target bitmap read back byte-identical to its
revision-pinned staged artifact, and no archive was resized. The patcher
receipt is
`.local/season-kit-integration-v1/2007-08-monaco-20260909-r1/carrier-kit-art-copy.json`
(SHA-256 `2a39a2e3a956f0b82a5eddb61b7f6ea848b2ad47b75bb44cb957ceacf4e16a5d`).

The integration adapter at
`.local/season-kit-integration-v1/2007-08-monaco-20260909-r1/kit-application-receipt.json`
(SHA-256 `03440d4ea670ece252cc925d1143cac29b66e4d67ca68739d9679980651b357d`)
binds the carrier-copy receipt, reviewed archive stage, and all five expected
archive hashes. The independent no-out-of-scope audit at
`.local/season-kit-integration-v1/2007-08-monaco-20260909-r1/game-tree-kit-only-audit.json`
(SHA-256 `ce4eadd93a25804f47c65a80184be74e5a619b450f98e65a579785b686cf8765`)
passes: its 275-file baseline/target sets agree, all 270 non-kit files are
byte-identical, all five kit archive hashes match the bound expectations, and
all three declared Monaco events read back with zero errors.

This is `pass-not-release` evidence for a third current-allocation 2007/08
kit carrier only. It does not alter a canonical package, source manifest,
generated delivery-status JSON, runtime evidence, screenshot, release link,
or the established 2015/16 release. 2007/08 remains `playable-known-good`
under its existing package/static/runtime/screenshot evidence, but
`release_eligible: false`; season-wide kit materialisation and the separate
manager, portrait/no-photo, ratings, opening-XI/formation, and immutable
release gates remain open. The next smallest action is a bounded read-only
review of this Monaco integration before selecting another current-allocation
kit requirement.

## 2007/08 Monaco single-carrier kit integration review (2026-09-09)

The prescribed bounded review is recorded at
`.local/operations/2007-08/monaco-kit-integration-review-20260909.json`
(SHA-256 `a01f6783403363065bdc19a9f05c7425e5e03b41ab56aa857193969f3174e06a`).
It independently re-verifies the qualified compiler receipt (SHA-256
`a01e1b01df84b201038f539689ff12b263ee375be3c44b3292dcfdc35b1a8642`),
clean static audit (SHA-256
`18aeaf5b4f817019fa801d14337eac5103785ad8a49dcb0d53bf0e50fbb12435`),
current-allocation Monaco revalidation, reviewed archive stage, carrier-copy
receipt, integration adapter, and kit-only audit. Every named input re-hashed
to its recorded SHA-256.

The qualified and carrier-505 integration trees each contain 275 files with
identical relative paths. All 270 non-kit files are byte-identical, including
the three database files and `MANAGPRE.EXE`. The three changed compact-kit
archives retain their sizes; their stage-before hashes match the qualified
tree, their stage-after hashes match the integration tree, and direct target
readback for each `EQ960505.BMP` payload matches its stage-bound artifact
SHA-256. No change outside the declared Monaco kit pixels was accepted.

This is `pass-not-release` evidence for a third current-allocation 2007/08 kit
carrier only. It changes no canonical package, generated delivery-status
JSON, runtime attestation, screenshot, release link, or established 2015/16
release. 2007/08 remains `playable-known-good` but
`release_eligible: false`; its season-wide kit, manager, portrait/no-photo,
ratings, opening-XI/formation, and immutable-release gates remain open. The
next smallest action is to separately review or revalidate one additional
current-allocation 2007/08 kit requirement, without promoting stale evidence
by carrier number alone.

## 2007/08 Milan single-carrier kit cache revalidation blocker (2026-09-09)

One further bounded, offline revalidation has frozen current carrier 201,
Milan, from the current 2007/08 allocation (SHA-256
`b70ec57250df934e1a1bf1ecb4bbe8a1dbfc523a706282c752e854bd8aa766b7`).
The new write-once root is
`.local/season-kit-revalidation-v1/2007-08-milan-20260909-r1/`. Its chunk
plan and subset allocation have SHA-256 values
`a901d8ee3402e6953957c2b141afeaa7db97ec9083ebdf6b7771a2977f2040b9` and
`3496c846199caedd9b27ef343502462a869222d2dc5e784ce180435558fbddc2`,
respectively.

The existing content-addressed Wikipedia cache replayed offline and matched
the current carrier identity to `2007–08 AC Milan season`, page `12777091`,
revision `1367286672`. The fresh chunk capture is
`revision-captured-home-fields-ready`; its receipt has SHA-256
`d75bf5432208a8bff32dd0fa731ebfed295a5f303fe640a4c4f2a4ecdd7d9eed`.
Its newly derived catalogue is SHA-256
`830539ee741f58f381330e80a591d3ad4137d5e98de40bb5f43ec2a0ff6ccb9e`.

The asset boundary correctly failed closed at rendering. Milan's exact
captured contract requires `_acm0708h` for body, left arm, and right arm. The
existing cache has the body layer but not the exact left- or right-arm layer,
so the render receipt (SHA-256
`0df6899d661b60a39342da0072f8779baf43e286f0384cd03b6da4edf4d56bb9`)
reports one `not-rendered-exact-pattern-unavailable` row and zero rendered
carriers or artifacts. No archive stage, game tree, package, runtime
evidence, screenshot, release link, status JSON, or 2015/16 release file was
created or changed.

This converts no kit requirement into release evidence and makes no
eligibility movement: 2007/08 remains `playable-known-good` but
`release_eligible: false`, with season-wide kits and the manager,
portrait/no-photo, ratings, opening-XI/formation, and immutable-release gates
still open. The next smallest action is a separately scoped decision on
obtaining only Milan's two exact missing 2007/08 sleeve layers; do not
substitute a nearby-season pattern or promote the source-only cache replay.

## Post-1999 coordinator durable kit-cache binding (2026-09-09)

The resume-safe post-1999 promotion coordinator's `kit-archives` stage had
been wired to `.local/season-kit-pattern-cache-v1`, an absent root.  The
documented durable exact-layer cache is instead
`.local/source-cache/wikimedia-kit-patterns-v1`; it currently has 594 cache
files: 297 index records and 297 content-addressed pattern objects. The
coordinator now passes that documented root to
`season_kit_render_bindings_v1.py`, so future no-overwrite kit stages can
replay existing hash-checked pattern evidence rather than failing solely from
the stale path.

This is a deterministic pipeline-path repair only.  It did not acquire an
asset, render a kit, create an archive stage or game tree, alter a package or
manifest, refresh the delivery status, create runtime evidence, or change the
established 2015/16 release.  It therefore moves no season's eligibility:
2007/08 remains `playable-known-good` but `release_eligible: false`, and the
Milan exact-sleeve cache miss remains a hard asset gap.  The next smallest
action is a separately scoped decision on obtaining only those two exact Milan
2007/08 sleeve layers; no nearby-season substitution is permitted.

## Post-1999 coordinator durable kit-cache preflight (2026-09-09)

The promotion coordinator now fails closed before its `kit-archives` stage
unless the documented durable cache exposes both `pattern-index/` and
`patterns/`.  This prevents a deleted or incorrectly rewired cache from being
treated as a collection of per-club unavailable-art outcomes.  The coordinator
continues to pass `.local/source-cache/wikimedia-kit-patterns-v1` explicitly to
`season_kit_render_bindings_v1.py`; the current cache has 297 index records
and 297 content-addressed pattern objects.

The focused coordinator regression lane passes (2 tests).  The implementation
and test file SHA-256 values are, respectively,
`ae55436cf8fd8cd5231d74bc8865d77604428c5c05e5824cc0de4156c372a77a` and
`516b45222e7d38ee92cc302e798c3063f6c23038802f45857370532527d0ad9c`.
No package, manifest, cache object, game tree, runtime evidence, release link,
or 2015/16 release file changed.  This is a deterministic pipeline guard for
all post-1999 draft promotions, not release evidence: eligibility and playable
classifications remain unchanged.  The next smallest action remains a
separately scoped decision on acquiring Milan's two exact 2007/08 sleeve
layers; do not substitute a nearby-season pattern.

## 2005/06 carrier-12 canonical-promotion review (2026-09-09)

The prescribed read-only review is recorded at
`.local/operations/2005-06/carrier-12-canonical-promotion-review-20260909.json`
(SHA-256 `84c9dcfa7746559ae60407aed13bdc1e0085d4e8ad53ce84310c0c12ba7835b0`).
It independently re-hashes the source-write-policy lift, display-alias repair,
mode-1 roster-reconciliation, static-ingress, compiler, clean-audit and final
package files. The reviewed package chain is
`880202dba034973c1be457955a6eb61e734d059b2b6f23e792f7ca2131ca9582` to
`351cce18fd7a07010c2b7b029218c7b26b2204c4bf1f3c7eed09b54ca99c7c93` to
`f89254c45c67a80ec798884e98637b159225910fc2a875a5f920b926ad5e21fe` to
`07f48dfdffb3663366ac055a81dd3fffa502ecca68b0690ef4b9a11c67679589`.

Strict V2 validation passes for the final package. Its calendar contract is
byte-identical to the carrier-12 input, retains calendar receipt
`84901fc3908cf17094626f31b3dbd041582c317e649d97df25ac922ba12e1843`, and
the clean audit is a pass against verified-base inventory
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118` with
zero fixed-tail, append/recycle, or derived-mode-0-donor mismatches.

The review deliberately does not approve canonical registration. The final
bytes are a 72-club mode-1 roster-preservation derivative after the
calendar-bound draft, whereas the existing canonical-promotion factory admits
only the direct calendar-bound package and an optional display-only derivative.
No reviewed source/canonical decision binds this roster-changing preservation
repair as the canonical 2005/06 package. The existing promotion factory
therefore rejects direct admission of these final bytes because the calendar
audit does not bind that exact package byte stream. Nothing was registered,
materialised or launched; 2005/06 remains `provisional-not-playable` and
`release_eligible: false`, so the generated delivery-status JSON remains
unchanged.

The next smallest action is a separately reviewed canonical-promotion decision
that explicitly binds the exact final derivative to its source and calendar
chain. It must not register a package or infer runtime evidence before that
decision.

## 2005/06 carrier-12 canonical-promotion decision (2026-09-09)

The separately scoped decision is recorded at
`.local/operations/2005-06/carrier-12-canonical-promotion-decision-20260909.json`.
It approves only canonical-package registration of the exact final
preservation derivative, SHA-256
`07f48dfdffb3663366ac055a81dd3fffa502ecca68b0690ef4b9a11c67679589`.

The decision reuses the already hash-verified source-write-policy,
display-alias, roster-reconciliation, static-ingress, compiler and clean-audit
receipts. It binds the complete package chain
`880202dba034973c1be457955a6eb61e734d059b2b6f23e792f7ca2131ca9582` to
`351cce18fd7a07010c2b7b029218c7b26b2204c4bf1f3c7eed09b54ca99c7c93` to
`f89254c45c67a80ec798884e98637b159225910fc2a875a5f920b926ad5e21fe` to
the approved final bytes. The calendar contract remains SHA-256
`fbcff2743ec2f617156e76cf76fa23cfbc5e85527e7761fb289b1c595b6fe231`,
with calendar receipt SHA-256
`84901fc3908cf17094626f31b3dbd041582c317e649d97df25ac922ba12e1843`.
All 72 reconciliations restore parser-backed base order as whole-record
`preserve-existing-mode1` declarations. The existing clean audit remains a
pass against inventory
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`, with
zero fixed-tail, append/recycle and derived-mode-0-donor mismatches.

No canonical package was registered, no manifest, game tree, runtime route,
screenshot or release link was created, and the established 2015/16 release
was not altered. 2005/06 consequently remains `provisional-not-playable` and
`release_eligible: false`; the generated delivery-status JSON remains correct
and unchanged. The next smallest action is to register exactly those approved
bytes at `seasons/2005-06/season-package.json`, then independently bind the
registered package to the existing clean static receipt. It must not infer a
runtime or playable result.

## 2005/06 carrier-12 canonical-package registration (2026-09-09)

The approved final preservation derivative has now been registered, with no
overwrite, at `seasons/2005-06/season-package.json`. It is byte-identical to
`.local/season-static-qualification-v1/2005-06-carrier-12-reconciled-20260908/season-package.reconciled.json`:
both have SHA-256
`07f48dfdffb3663366ac055a81dd3fffa502ecca68b0690ef4b9a11c67679589`.
Strict V2 validation passes for the registered bytes.

A local-only delivery-status refresh independently re-verifies the already
recorded canonical repair chain, compiler receipt, and passing clean static
audit. It now reports `canonical-package` and
`static-audited-canonical-package` for 2005/06, with evidence state
`verified-canonical-package-bound-static-repair-chain`. The existing audit
remains a pass with zero fixed-roster-tail, append/recycle, or derived-mode-0
donor mismatches.

This closes the canonical-package and canonical package-bound static gates
only. It creates no game tree, target-calendar runtime attestation,
screenshot, release link, asset materialisation, or immutable release
registration, and it does not change the established 2015/16 release.
2005/06 remains `provisional-not-playable` and `release_eligible: false`.
The next smallest action is a new no-overwrite PM99 runtime route that binds
the exact canonical static database outputs to the 2005/06 target-calendar
executable and records a screenshot from that route; it must not make a
playable or release claim while the separate manager, kit, portrait/no-photo,
ratings, opening-XI/formation, and immutable-release gates remain open.

## 2005/06 target-calendar runtime route capacity block (2026-09-09)

The prescribed no-overwrite route was attempted with the exact registered
2005/06 package, the qualified static `DBDAT` directory, and the bound
2005/06 calendar executable. The first `r1` launcher invocation stopped in
the local sandbox before a remote connection could be made; its retained
control manifest is
`.local/season-runtime-evidence-v1/post1999_2005_06_target_calendar_runtime_20260909_r1/control_launch.json`
(SHA-256 `db93e2f015bddd945b7ff30df8f00faa8361c2568b1a570a9d8588ecdc773bdf`).

The corresponding protected remote `r2` invocation reached the runner guard
but stopped before Wine or PM99 launched because the remote run-root budget
reported `36/20` roots and `42,614,559,213/25,769,803,776` bytes. Its retained
control manifest is
`.local/season-runtime-evidence-v1/post1999_2005_06_target_calendar_runtime_20260909_r2/control_launch.json`
(SHA-256 `e6e0e15cbe4f0da7ea751ac6da9f2704eea5c6f416bf8dcdb0b4cc4e8e48fd12`).
Both control manifests name only
`.local/season-static-qualification-v1/2005-06-carrier-12-reconciled-20260908/game/DBDAT`
and `.local/calendar-v1/2005-06/MANAGPRE.EXE` as overrides.

Neither directory contains a runner summary, screenshot, or runtime
attestation. The generated delivery-status JSON therefore remains unchanged:
2005/06 is still `provisional-not-playable` and `release_eligible: false`,
with its successful-runtime-route and runtime-screenshot gates open. No
package, static game tree, manifest, release link, or 2015/16 release file was
changed. The next smallest action is to recover the remote runner capacity
through its established non-destructive retention/archival procedure, then
launch one fresh no-overwrite 2005/06 target-calendar-bound route and attest a
resulting screenshot.

## 2005/06 target-calendar runtime capacity recovery plan (2026-09-09)

The prescribed retention procedure has now completed a read-only remote
inventory and plan at
`.local/operations/runner-recovery/2005-06-runtime-capacity-20260909-r4-plan/`.
The inventory SHA-256 is
`ae7c9d2474745e8dd6d32b970a91f3abd80725a143a5572f73db9c9f5bd76105` and
the plan SHA-256 is
`2e7db5757a121acb2e8603fc5319893b487bb833f0c6f7545c4e170b516522d0`.

At `2026-09-09T13:02:45Z`, the remote runner had 37 run roots consuming
44,317,821,396 bytes. The plan retains 11 roots (1,703,521,798 bytes),
including the failed 2005/06 `r2` control-run root, and identifies 26 older
roots (42,614,299,598 bytes) as candidates for the existing retention action.
Twenty-five of those candidates have remote artifact directories. The runner
also removed the stale host-lock left by the failed `r2` control invocation
before producing the plan.

This was a dry run only: no run root or artifact was archived, removed, or
otherwise changed. No package, static game tree, manifest, runtime evidence,
screenshot, release link, delivery-status JSON, or 2015/16 release file
changed. 2005/06 therefore remains `provisional-not-playable` and
`release_eligible: false`, with successful-runtime-route and runtime-screenshot
gates open. The next smallest action, subject to explicit authority to alter
remote retention state, is to archive the exact planned stale roots through
the verified retention procedure, then launch one fresh no-overwrite 2005/06
target-calendar-bound route and attest a screenshot.

## 2000/01 current-draft canonical-candidate ingress blocker (2026-09-09)

One no-overwrite canonical-workspace ingress was attempted for the current
2000/01 calendar-bound draft at
`.local/season-calendar-bound-batch-v2/2000-01/draft-season-package.calendar-bound.json`
(SHA-256 `26d5e9c74a623034cbf34ec09fd563e53b33b729af00b354b4e163f935e21ba9`).
It used the current calendar-binding audit (SHA-256
`361548e3822c57609e176c3903d6c30451cfc4bacb86484f1ff8b109f3e48992`) and
the already verified clean-base descriptor (SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`).

The promotion factory failed closed during strict V2 validation before it
created its requested no-overwrite output directory. The exact current-draft
blocker is an ambiguous same-person opening-date candidate: `player-8758` and
`player-8771` both resolve to Calle Elkin (born `1980-05-20`, Colombia). The
older `2000-01` canonical-candidate root is not a substitute: its candidate
package has SHA-256 `90ec587fdef276912d7349d6fed538b5460c5b2f16909b85c2bac11c28d1b9d1`,
which differs from the current calendar-bound draft and must not be registered
in its place.

No package, source capture, candidate, manifest, game tree, runtime evidence,
screenshot, release link, delivery-status JSON, or 2015/16 release file
changed. 2000/01 remains `provisional-not-playable` and
`release_eligible: false`; its canonical-package and canonical
package-bound-static gates remain open. The next smallest action is a
separate, identity-safe reconciliation of only these two existing
opening-date player candidates, followed by a fresh no-overwrite candidate
ingress; do not acquire new sources or promote either existing candidate.

## 2000/01 Calle Elkin stale-source candidate reconciliation (2026-09-09)

The prescribed narrow reconciliation completed against the current
calendar-bound 2000/01 draft at
`.local/season-calendar-bound-batch-v2/2000-01/draft-season-package.calendar-bound.json`
(SHA-256 `26d5e9c74a623034cbf34ec09fd563e53b33b729af00b354b4e163f935e21ba9`).
It re-verified the 275-file clean base against descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6` and
inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The new write-once static candidate is
`.local/season-opening-date-reconciliation-v1/2000-01-calle-elkin-20260909-r1/season-package.stale-source-reconciled.json`
(SHA-256 `a51d67e2eb01f454cfe27b16379c7330edf6902c6a95fd7348200f926cf81550`).
Its reconciliation audit has SHA-256
`b84934c47c917583ce22274e2d317f3534fdd03ac51c74e866cca5d02ffe0a95`.
The audit proves there was exactly one eligible pair in the draft: the
current source-backed Calle Elkin at `player-8758` remains, while stale legacy
`player-8771` at carrier 8771 is restored from its parser-read native whole
record as Milton PATIÑO Rosero (payload SHA-256
`d52b3a8dfce40599f779cc3d6cd8fdec84c0444cc21acab50ae6ad2f97f9e2e7`).

Strict V2 validation passes for the new canonical bytes. A focused recheck of
every strict-only gate finds zero ambiguous same-person candidates, no missing
required player, club, or manager identity IDs, `migration.status: native-v2`,
and no migration gaps. A semantic-isolation comparison finds only
`players/player-8771` and its portrait declaration changed. No source was
acquired; no source or current manifest, canonical package, compiler output,
clean audit, game tree, runtime proof, screenshot, release link, delivery
status JSON, or 2015/16 release file changed.

This removes the recorded current-draft strict identity blocker, but is only a
static candidate: 2000/01 remains `provisional-not-playable` and
`release_eligible: false`, with canonical-package, canonical
package-bound-static, runtime, screenshot, and package-level release work
still open. The next smallest action is a fresh no-overwrite canonical-workspace
candidate ingress from these exact reconciled bytes, retaining the recorded
calendar and base bindings without registering a package or inferring runtime.

## 2000/01 Calle Elkin reconciled canonical-workspace ingress (2026-09-09)

The exact stale-source-reconciled 2000/01 package has now entered a fresh,
write-once canonical-workspace candidate lane. The existing cached calendar
receipt and executable were re-attested at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-20260909-r1-binding/`.
The re-attested package is byte-identical to the reconciliation output, with
SHA-256 `a51d67e2eb01f454cfe27b16379c7330edf6902c6a95fd7348200f926cf81550`;
the new calendar-binding audit has SHA-256
`5b8184eb62d4a7a008fa1db126ddd4e154f527e68c3f7eec214caada9f6501b4`.
It binds the existing 2000/01 calendar receipt
`50c42eb4f5fd9e6a5e34db857409ce5711f91a9176cb60ce926e1e8d7db24dec` and
executable `cd065504ea1225d9e29942cbf08fa393f0fe97f7c37a45e7b42482b4681e42a0`.

The three fresh, no-overwrite candidate materialisations are
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-20260909-r1/`,
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-20260909-r2/`, and
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-20260909-r3/`.
Their promotion audits are byte-identical (SHA-256
`a401b139233d3dd9c70b8429afc36a29040edb08486dfbbc763e2fee402ea517`)
and record `canonical-workspace-candidate-only`: strict V2 validation, calendar
binding, verified-base validation, workspace validation, and workspace
preparation all pass. It binds the verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`.
Their prepared effective packages are byte-identical with SHA-256
`95f554fc9827c701447d355173d9da6637ec71be8c77452315d0b464e0a733d8`;
the non-executable build-plan candidates are byte-identical with SHA-256
`ebe1615b140810a6d164c7c7666f264a3cd7452b1caf77030082ac91634776c9`.

No source was acquired, no current manifest or canonical package was moved,
and no binary compiler materialisation, static audit, runtime route,
screenshot, release link, or 2015/16 release file was created or changed.
The refreshed local-only delivery status remains
`provisional-not-playable` and `release_eligible: false`; no pre-existing
runtime evidence is bound to this candidate. The next smallest action is one
fresh no-overwrite workspace compile of the exact prepared effective package
against the verified clean base. A later independent matching compile remains
required; neither may be treated as a release or runtime proof.

## 2000/01 Calle Elkin canonical-workspace compile blocker: Arild Stavrum (2026-09-09)

The prescribed first clean workspace compile was attempted from the exact
`2000-01-calle-elkin-20260909-r1` candidate. The workspace check passed, and
the newly prepared effective package at
`.local/season-workspace-v1/2000-01-calle-elkin-20260909-r2-build/season-package.effective.json`
has the expected SHA-256
`95f554fc9827c701447d355173d9da6637ec71be8c77452315d0b464e0a733d8`.
The compile re-verified the candidate workspace (SHA-256
`9f170172a9e15814da2b348be375830f21eb4a33a9af686d9a09eb8fbd13f243`)
and the clean-base descriptor (SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`).

The `r2` compiler invocation failed closed before producing a compiler receipt
or static audit. The exact parser guard is: `player player-10320 carrier 10320
cannot apply variable name 'Arild Stavrum': Native dd6360 target name exceeds
stable native string window: new_role_start=32, old_role_start=30`.
The first `r1` paths contain only a copied 275-file base and the five workspace
prepare outputs, without a compiler receipt; both `r1` and `r2` are retained
untouched and are non-evidence.

The three `r2` database files remain byte-identical to the verified base after
the rejection: `ENT98030.FDI` SHA-256
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`,
`EQ98030.FDI` SHA-256
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`,
and `JUG98030.FDI` SHA-256
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`.
No source, current manifest, canonical package, release link, runtime route,
screenshot, or 2015/16 release file changed. 2000/01 remains
`provisional-not-playable` and `release_eligible: false`; the generated
delivery-status JSON remains correct and unchanged.

The next smallest action is a parser-bound, no-overwrite display-alias repair
of the exact candidate for this string-window blocker, followed by a fresh
canonical-workspace candidate ingress. It must retain the source name and
identity, acquire no source, and make no release or runtime claim.

## 2000/01 Calle Elkin candidate display-alias repair (2026-09-09)

The prescribed parser-bound, no-overwrite display-alias repair completed from
the exact Calle Elkin canonical-workspace candidate at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-20260909-r1/season-package.candidate.json`
(SHA-256 `a51d67e2eb01f454cfe27b16379c7330edf6902c6a95fd7348200f926cf81550`).
It re-verified the clean-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6` and
the 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The new static-only candidate is
`.local/season-canonical-alias-candidate-v1/2000-01-calle-elkin-20260909-r1/season-package.alias-bound.json`
(SHA-256 `2f1c586a99c3057bf01e216558ef8855d6c455f67f4a3115d78eb8388cd9d15c`).
Its parser-exercised repair audit has SHA-256
`93869ffc55c2f7683950f1270fb7cb9412336e55ee7e20625b39bcc8f227a34f`.
Strict V2 validation passes.  The repair changes 3,216 display names across
8,111 writable player carriers, leaves all 1,066
`preserve-existing-mode1` rows untouched, and preserves the calendar
contract.  An independent semantic-isolation check confirms that the only
package differences are those player `name` fields.

For the exact compiler blocker, `player-10320` remains carrier 10320 with the
same person ID and source name `Arild Stavrum`; its parser-safe display alias
is `A. Stavrum` by the source-derived initial-and-surname rule.  No source was
acquired, and no source/current manifest, canonical package, compiler output,
clean audit, game tree, runtime proof, screenshot, release link, or 2015/16
release file changed.  The delivery-status JSON correctly remains unchanged:
2000/01 is `provisional-not-playable` and `release_eligible: false`.

The next smallest action is a fresh no-overwrite canonical-workspace candidate
ingress from these exact alias-bound bytes, retaining the recorded calendar
and verified-base bindings.  It must not register a canonical package or make
a static, runtime, or playable claim.

## 2000/01 alias-bound canonical-workspace ingress (2026-09-09)

The exact parser-safe display-alias derivative has now entered a fresh,
write-once canonical-workspace candidate lane at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-20260909-r2/`.
The factory completed with `canonical-workspace-candidate-only` and
`release_eligible: false`; strict V2 validation, calendar binding,
display-alias binding, verified-base validation, workspace validation, and
workspace preparation all passed.

The candidate package remains byte-identical to the alias derivative with
SHA-256 `2f1c586a99c3057bf01e216558ef8855d6c455f67f4a3115d78eb8388cd9d15c`.
The promotion audit has SHA-256
`a26a00b8f8eea5b6d744b8bcb60b7cac566f1f9a26984c7af84737eb6ed82be5`;
the workspace, prepared effective package, and non-executable build-plan
candidate have SHA-256 values
`c222b980364fd159ecad9f902287d0bab8d6832319ca1aa7d54285bb7f51561b`,
`f083a46a2995611f57f3d8fcd895283677af930480a9938bb3ce082c57bec70e`,
and `237f325bbbb67d92267d55e107406a11ab0b08f6dbef1b54206d1f85d7cf82c4`,
respectively.

An earlier `r1` invocation was interrupted before the factory emitted its
promotion audit or prepared outputs. Its four-file partial directory is
retained untouched and is explicitly non-evidence. No source, current
manifest, canonical package, compiler output, clean audit, runtime route,
screenshot, release link, delivery-status JSON, or 2015/16 release file was
changed. 2000/01 remains `provisional-not-playable` and
`release_eligible: false` with no delivery-gate movement. The next smallest
action is one fresh no-overwrite workspace compile of the exact `r2` prepared
effective package against its verified clean base; it must not be treated as
a clean audit, runtime proof, or release.

## 2000/01 alias-bound compile blocker: club carrier 1 (2026-09-09)

The prescribed fresh, no-overwrite compile was attempted from the exact
`2000-01-calle-elkin-alias-20260909-r2` canonical-workspace candidate. The
compiler re-prepared an effective package with the expected SHA-256
`f083a46a2995611f57f3d8fcd895283677af930480a9938bb3ce082c57bec70e`
and copied all 275 verified-base files into
`.local/season-workspace-v1/2000-01-calle-elkin-alias-20260909-r3-game/`.

The compile then failed closed before producing a compiler receipt or static
audit: `mode-1 club carrier 1 changes its fixed roster row count`. The exact
effective package declares 25 roster player IDs for carrier 1 (Barcelona).
The retained `r3` tree is non-evidence. Its three database files remain
byte-identical to the verified clean base: `ENT98030.FDI` SHA-256
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`,
`EQ98030.FDI` SHA-256
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`,
and `JUG98030.FDI` SHA-256
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`.

No source, current manifest, canonical package, clean audit, runtime proof,
screenshot, release link, delivery-status JSON, or 2015/16 release file was
changed. 2000/01 remains `provisional-not-playable` and
`release_eligible: false`, with no delivery-gate movement. The next smallest
action is a parser-bound, no-overwrite fixed-row reconciliation for only mode-1
club carrier 1 from the exact alias-bound candidate, preserving source and
identity claims, followed by a fresh candidate ingress; do not acquire source
or infer static or runtime qualification.

## 2000/01 alias-bound carrier-1 preservation derivative (2026-09-09)

The prescribed no-overwrite derivative has been created directly from the
exact alias-bound canonical-workspace candidate at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-20260909-r2/season-package.candidate.json`
(SHA-256 `2f1c586a99c3057bf01e216558ef8855d6c455f67f4a3115d78eb8388cd9d15c`).
The reconciler verified the candidate's clean-base descriptor and its
275-file inventory before emitting the derivative.

The new static candidate is
`.local/season-canonical-alias-roster-candidate-v1/2000-01-20260909-r1/season-package.alias-roster-reconciled.json`
(SHA-256 `7e17d4397e513874459e9b544f8da601dc2df6e79bc471aeff274f8436c36bbb`).
Its reconciliation audit has SHA-256
`67fb6f8360d390838725b0f8dbc33f11cc913549942f4d7fd9391a97900a7938`.
It restores precisely the one omitted Barcelona fixed row, carrier 16 (Luis
Enrique Martínez García), in the parser-backed 26-row base order. The added
player is a whole-record `preserve-existing-mode1` declaration with an
existing static-contract proof and an unresolved/native-no-photo portrait
outcome; it makes no new dated source, identity, ratings, or portrait claim.

Strict V2 validation and a deep semantic-isolation comparison pass. Relative
to the input candidate, the only additions are `players/player-16`, its
unresolved portrait declaration, and `player-16` at the start of `club-1`'s
roster; all other clubs and Barcelona's non-roster fields are unchanged. This
action created no binary materialisation, clean audit, canonical package,
release manifest or link, runtime route, screenshot, or 2015/16 release
change. The generated delivery-status JSON therefore remains unchanged:
2000/01 is still `provisional-not-playable` and `release_eligible: false`.
The next smallest action is a fresh no-overwrite canonical-workspace candidate
ingress from these exact reconciled bytes, retaining the existing calendar,
display-alias, and verified-base bindings; it must not register a canonical
package or infer static, runtime, or playable qualification.

## 2000/01 alias-and-roster canonical-workspace ingress (2026-09-09)

The existing promotion factory has been extended with one fail-closed ingress
lane for an already audited whole-row mode-1 preservation derivative. The new
lane requires both the pre-existing exact display-alias receipt and the exact
roster-reconciliation receipt; it rejects any change outside the declared
restored player, portrait, and club-roster rows. It remains an ingress-only
operation and has no compiler, release, runtime, or screenshot path.

The exact 2000/01 alias-and-roster derivative now has a fresh, no-overwrite
canonical-workspace candidate at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-20260909-r1/`.
The candidate package is byte-identical to the carrier-1 preservation output,
with SHA-256 `7e17d4397e513874459e9b544f8da601dc2df6e79bc471aeff274f8436c36bbb`.
Its promotion audit SHA-256 is
`775af547c881a5d0b7dce50fa4280aacdea9e9233f583f6443949a5d4b4b5687`.

The audit binds the re-attested calendar-bound candidate SHA-256
`a51d67e2eb01f454cfe27b16379c7330edf6902c6a95fd7348200f926cf81550`,
the 3,216-name display-alias derivative SHA-256
`2f1c586a99c3057bf01e216558ef8855d6c455f67f4a3115d78eb8388cd9d15c`,
and the one-row roster-reconciliation audit SHA-256
`67fb6f8360d390838725b0f8dbc33f11cc913549942f4d7fd9391a97900a7938`.
It retains the verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`.
Strict V2 validation, calendar binding, display-alias binding, mode-1
roster-reconciliation binding, workspace validation, and workspace preparation
all pass. The prepared effective package SHA-256 is
`68b2a9518913d1907bf47594c92e78ae49fdb8e9b23281057c2ed0f0a5e5575b`; the
non-executable build-plan candidate SHA-256 is
`c7d006c6c4a4fdeef11fa2206f874c06f8e4d417ebb4d929c0a5ca6305bb05c6`.

No source was acquired, no current manifest or canonical package was moved,
and no binary compiler materialisation, static audit, runtime route,
screenshot, release link, delivery-status JSON, or 2015/16 release file was
created or changed. 2000/01 remains `provisional-not-playable` and
`release_eligible: false`; this candidate closes no published release gate.
The next smallest action is one fresh no-overwrite workspace compile of this
exact prepared effective package against the verified clean base. It must not
be treated as a clean audit, runtime proof, or release; an independent
matching compile remains required later.

## 2000/01 alias-and-roster compile blocker: club carrier 10 (2026-09-10)

The prescribed fresh, no-overwrite compile was attempted from the exact
`2000-01-calle-elkin-alias-roster-20260909-r1` canonical-workspace candidate.
The compiler re-prepared an effective package with the expected SHA-256
`68b2a9518913d1907bf47594c92e78ae49fdb8e9b23281057c2ed0f0a5e5575b`
and copied all 275 verified-base files into
`.local/season-workspace-v1/2000-01-calle-elkin-alias-roster-20260910-r1-game/`.

The compile then failed closed before producing a compiler receipt or static
audit: `mode-1 club carrier 10 changes its fixed roster row count`. The exact
effective package declares 23 roster player IDs for carrier 10 (Racing
Santander). The retained game tree is non-evidence. Its three database files
remain byte-identical to the verified clean base: `ENT98030.FDI` SHA-256
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`,
`EQ98030.FDI` SHA-256
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`,
and `JUG98030.FDI` SHA-256
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`.

No source, current manifest, canonical package, clean audit, runtime proof,
screenshot, release link, delivery-status JSON, or 2015/16 release file was
changed. 2000/01 remains `provisional-not-playable` and
`release_eligible: false`, with no delivery-gate movement. The next smallest
action is a parser-bound, no-overwrite fixed-row reconciliation for only
mode-1 club carrier 10 from this exact alias-and-roster candidate, preserving
source and identity claims, followed by a fresh candidate ingress; do not
acquire source or infer static or runtime qualification.

## 2000/01 alias-and-roster carrier-10 preservation derivative (2026-09-10)

The prescribed no-overwrite fixed-row reconciliation has completed directly
from `.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-20260909-r1/season-package.candidate.json`
(SHA-256 `7e17d4397e513874459e9b544f8da601dc2df6e79bc471aeff274f8436c36bbb`).
It re-verified the clean-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6` and
its 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The new static candidate is
`.local/season-canonical-alias-roster-carrier10-candidate-v1/2000-01-20260910-r1/season-package.alias-roster-carrier10-reconciled.json`
(SHA-256 `9fd4d0219acdb366a0cf999975b44f2fc9923a7dd3c1c4ada2e037c1c3920e21`).
Its reconciliation audit is SHA-256
`ea9379d0126a54162f8f865d4abef8a5b227efd37437beefb3f13cb11f950f21`.
It restores precisely the seven omitted carrier-10 base rows in parser-backed
base order: 199 (Sebastián Cruzado Fernández, CHANO), 762 (Francisco Javier
López Aguilera, JAVI LÓPEZ), 2067 (DOMINGOS José Paciencia de Oliveira), 4960
(Sergio Martínez BALLESTEROS), 8901 (Fernando NAVARRO MONTOYA), 13018
(Ferdinand Rudols Marcel VIERKLAU), and 17357 (Federico Guillermo LUSSENHOFF).
Every row is a parser-read whole-record `preserve-existing-mode1` declaration
with a `static-contract` proof and unresolved/native-no-photo outcome; none
is a dated source, identity, ratings, or portrait claim.

Strict V2 validation passes within the reconciler. An independent
semantic-isolation check also passes: other than those seven player and
unresolved-portrait declarations, all pre-existing declarations are unchanged;
carrier 10's non-roster metadata is unchanged and its roster is the exact
30-row base order. No source, current manifest, canonical package, binary
materialisation, clean audit, release link, runtime route, screenshot, or
2015/16 release file changed. The generated delivery-status JSON remains
unchanged: 2000/01 is still `provisional-not-playable` and
`release_eligible: false`.

The next smallest action is a fresh, no-overwrite canonical-workspace ingress
from this exact carrier-10 derivative, binding the existing display-alias and
both roster-reconciliation receipts. It must not register the derivative or
infer static, runtime, or playable qualification.

## 2000/01 eight-repair canonical-workspace ingress (2026-09-10)

The prescribed no-overwrite canonical-workspace ingress completed at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1256-20260910-r1/`.
Its candidate package is byte-identical to the carrier-1256 preservation
derivative, SHA-256
`48eae462a005cfa290476668c4e36f3c0e87b525a1f93f583c0ae994e09e3374`.
The prepared effective package, promotion audit, and non-executable build-plan
candidate have SHA-256 values
`64e433592c5b40b25dba1652452d8dc56264967f80381852530dbdaeb82062df`,
`e17925834760a14c4986982775889d156562be2b4c9ab38488a61856a2ffb9fa`, and
`ff9a20f2ce5da0d2632675f53de91695e164321d6cffaebb43e3c53320de926d`,
respectively.

The factory re-attested the calendar-bound source package SHA-256
`a51d67e2eb01f454cfe27b16379c7330edf6902c6a95fd7348200f926cf81550`,
calendar-binding audit SHA-256
`5b8184eb62d4a7a008fa1db126ddd4e154f527e68c3f7eec214caada9f6501b4`,
3,216-name display-alias derivative SHA-256
`2f1c586a99c3057bf01e216558ef8855d6c455f67f4a3115d78eb8388cd9d15c`,
and verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`.
It verifies the ordered whole-row reconciliation chain for club carriers 1,
10, 1001, 11, 12, 1251, 1252, and 1256; the final carrier-1256 receipt is
SHA-256 `16bc394d89558d802119293df7396d63ced774e98a7cca53103cd99fa88b5953`
and restores only carrier 5472 under the existing unresolved/native-no-photo
preservation rule.

Strict V2, calendar, display-alias, all eight ordered roster-reconciliation,
verified-base, workspace, and workspace-preparation contracts pass. A direct
workspace check also returns `ok: true`. No source was acquired and no current
manifest or canonical package was moved; no binary compiler materialisation,
clean audit, release link, PM99 runtime route, screenshot, delivery-status
JSON, or 2015/16 release file changed. 2000/01 therefore remains
`provisional-not-playable` and `release_eligible: false`. The next smallest
action is one fresh, no-overwrite workspace compile of this exact prepared
effective package against the verified clean base. It must remain static-only
and needs a later independent matching compile before a build plan or runtime
work.

## 2000/01 two-repair canonical-workspace ingress (2026-09-10)

The prescribed carrier-10 derivative has entered two fresh, no-overwrite
canonical-workspace candidate lanes at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier10-20260910-r1/`
and
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier10-20260910-r2/`.
The promotion factory now verifies an ordered sequence of whole-row mode-1
preservation receipts; its existing single-repair result format remains
unchanged. The two candidate packages, workspaces, prepared effective packages,
non-executable build-plan candidates, and promotion audits are byte-identical.

Each completed promotion audit has SHA-256
`8e922e81988fcc6d926fb23128182ea63539846c3b6cd63376880584df7fdca6`.
It binds the calendar-bound Calle Elkin candidate SHA-256
`a51d67e2eb01f454cfe27b16379c7330edf6902c6a95fd7348200f926cf81550`,
the 3,216-name alias derivative SHA-256
`2f1c586a99c3057bf01e216558ef8855d6c455f67f4a3115d78eb8388cd9d15c`,
and the ordered roster-preservation chain: carrier 1's one restored row via
audit `67fb6f8360d390838725b0f8dbc33f11cc913549942f4d7fd9391a97900a7938`
to package SHA-256
`7e17d4397e513874459e9b544f8da601dc2df6e79bc471aeff274f8436c36bbb`,
then carrier 10's seven restored rows via audit
`ea9379d0126a54162f8f865d4abef8a5b227efd37437beefb3f13cb11f950f21`
to package SHA-256
`9fd4d0219acdb366a0cf999975b44f2fc9923a7dd3c1c4adae037c1c3920e21`.
It also binds the verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`.

Strict V2, calendar, display-alias, ordered roster-reconciliation,
verified-base, workspace, and workspace-preparation contracts all pass. The
candidate package is byte-identical to the carrier-10 derivative; its prepared
effective package SHA-256 is
`3f130e853bfb5d1a2a3fccfd51a07800f154223e2d513ca22062d1a7c4f23d80`,
and its non-executable build-plan candidate SHA-256 is
`28241b71c7ff6978d4efc442d3018a53d24fcbf8bf2344954a551cbf69399259`.

No source was acquired, no current manifest or canonical package was moved,
and no binary compiler materialisation, clean audit, release link, runtime
route, screenshot, delivery-status JSON, or 2015/16 release file changed.
2000/01 remains `provisional-not-playable` and `release_eligible: false`; no
published delivery gate has moved. The next smallest action is one fresh,
no-overwrite workspace compile of this exact prepared effective package against
the verified clean base. It must remain a static-only compile attempt, with a
later independent matching compile still required.

## 2000/01 two-repair canonical-workspace compile blocker: club carrier 1001 (2026-09-10)

The prescribed first fresh, no-overwrite workspace compile was attempted from
the exact
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier10-20260910-r1/`
candidate against `.local/season-pipeline-v2/pm99-base-clean`.  The candidate
package, workspace, verified-base descriptor, and prepared effective package
were re-verified at SHA-256 values
`9fd4d0219acdb366a0cf999975b44f2fc9923a7dd3c1c4ada2e037c1c3920e21`,
`bf251b11c937f3a1b9c5add97a6b66825f6740722f801409f22129079509f81d`,
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`, and
`3f130e853bfb5d1a2a3fccfd51a07800f154223e2d513ca22062d1a7c4f23d80`.

The compiler failed closed before emitting a compiler receipt or static audit:
`mode-1 club carrier 1001 changes its fixed roster row count`.  The fresh
paths `.local/season-workspace-v1/2000-01-calle-elkin-alias-roster-carrier10-20260910-r2-game/`
and `...-r2-build/` are retained untouched as non-evidence.  The game tree
contains the expected 275 copied base files, and its three database files
remain byte-identical to the verified base: `ENT98030.FDI`
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`,
`EQ98030.FDI`
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`, and
`JUG98030.FDI`
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`.

No source, current manifest, canonical package, static audit, runtime route,
screenshot, release link, or 2015/16 release file changed.  2000/01 remains
`provisional-not-playable` and `release_eligible: false`; no published delivery
gate has moved, so the generated delivery-status JSON is intentionally
unchanged.  The next smallest action is a parser-bound, no-overwrite fixed-row
reconciliation for only mode-1 club carrier 1001 from this exact two-repair
candidate, preserving source and identity claims, followed by a fresh
canonical-workspace candidate ingress.  It must not acquire source or infer
static, runtime, or playable qualification.

## 2000/01 two-repair carrier-1001 preservation derivative (2026-09-10)

The prescribed no-overwrite fixed-row reconciliation completed from the exact
two-repair canonical-workspace candidate at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier10-20260910-r1/season-package.candidate.json`
(SHA-256 `9fd4d0219acdb366a0cf999975b44f2fc9923a7dd3c1c4ada2e037c1c3920e21`).
It re-verified the clean-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6` and
the 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The new static-only derivative is
`.local/season-canonical-alias-roster-carrier1001-candidate-v1/2000-01-20260910-r1/season-package.alias-roster-carrier1001-reconciled.json`
(SHA-256 `e60a0f8b211283d1e0d605297dffadde917ca3f0ca3e1d90db04a7c9e08ae690`);
its reconciliation audit is SHA-256
`cb32a848e2c6907c0451b85a2600d74a8a380a562a01d9cb47defbca5b4b37e9`.
It restores only Istanbulspor's omitted base roster carrier 459, José G. DEL
SOLAR Álvarez Calderón, in the parser-backed 29-row base order. The added row
is a whole-record `preserve-existing-mode1` declaration with a static-contract
proof and an unresolved/native-no-photo outcome; it makes no dated source,
identity, ratings, or portrait claim.

Strict V2 validation and an independent semantic-isolation check pass. Apart
from `players/player-459`, its unresolved portrait declaration, and
`club-1001`'s roster insertion, the output is byte-for-byte semantically
identical to its input. No source, current manifest, canonical package,
binary materialisation, static audit, release link, runtime route, screenshot,
or 2015/16 release file changed. The generated delivery-status JSON remains
correct and unchanged: 2000/01 is `provisional-not-playable` and
`release_eligible: false`.

The next smallest action is a fresh, no-overwrite canonical-workspace candidate
ingress from these exact carrier-1001 bytes, binding the existing display-alias
receipt and all three ordered roster-reconciliation receipts. It must not
register a canonical package or infer static, runtime, or playable
qualification.

## 2000/01 three-repair canonical-workspace ingress (2026-09-10)

The prescribed carrier-1001 derivative has entered a fresh, no-overwrite
canonical-workspace candidate lane at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1001-20260910-r1/`.
Its candidate package is byte-identical to the carrier-1001 preservation
derivative, with SHA-256
`e60a0f8b211283d1e0d605297dffadde917ca3f0ca3e1d90db04a7c9e08ae690`.

The promotion audit has SHA-256
`b5b8347d41bf66259b33d5ff07c36f1d039a2091598be9d78894b3938a14ecc0`.
It binds the calendar-bound Calle Elkin package SHA-256
`a51d67e2eb01f454cfe27b16379c7330edf6902c6a95fd7348200f926cf81550`,
the 3,216-name display-alias derivative SHA-256
`2f1c586a99c3057bf01e216558ef8855d6c455f67f4a3115d78eb8388cd9d15c`,
and the ordered whole-row roster-preservation chain: carrier 1's one restored
row via audit `67fb6f8360d390838725b0f8dbc33f11cc913549942f4d7fd9391a97900a7938`,
carrier 10's seven restored rows via audit
`ea9379d0126a54162f8f865d4abef8a5b227efd37437beefb3f13cb11f950f21`,
and carrier 1001's one restored row via audit
`cb32a848e2c6907c0451b85a2600d74a8a380a562a01d9cb47defbca5b4b37e9`.
It also retains the verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`.

Strict V2, calendar, display-alias, ordered roster-reconciliation,
verified-base, workspace, and workspace-preparation contracts all pass. The
emitted workspace, prepared effective package, and non-executable build-plan
candidate have SHA-256 values
`26da68418661bdf76e16880242146c7511b344b01d673466ef91362c20e7e5f6`,
`d492f2e49fc06530859ab8d07e4c67d7b9434f7dfefe16afccb571244d5b0cbd`,
and `b8d4141057543bd4d46678fbd9de0936883e9b788331255b806cb03a8961c746`,
respectively. A direct workspace check also returns `ok: true`.

No source was acquired, no current manifest or canonical package was moved,
and no binary compiler materialisation, clean audit, release link, runtime
route, screenshot, delivery-status JSON, or 2015/16 release file changed.
2000/01 remains `provisional-not-playable` and `release_eligible: false`; no
published delivery gate has moved. The next smallest action is one fresh,
no-overwrite workspace compile of this exact prepared effective package against
the verified clean base. It must remain a static-only compile attempt, with a
later independent matching compile still required.

## 2000/01 three-repair canonical-workspace compile blocker: club carrier 11 (2026-09-10)

The prescribed fresh, no-overwrite workspace compile was attempted from the
exact
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1001-20260910-r1/`
candidate against `.local/season-pipeline-v2/pm99-base-clean`. The candidate
package, workspace, verified-base descriptor, and re-prepared effective package
were re-verified at SHA-256 values
`e60a0f8b211283d1e0d605297dffadde917ca3f0ca3e1d90db04a7c9e08ae690`,
`26da68418661bdf76e16880242146c7511b344b01d673466ef91362c20e7e5f6`,
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`, and
`d492f2e49fc06530859ab8d07e4c67d7b9434f7dfefe16afccb571244d5b0cbd`.

The compiler failed closed before emitting a compiler receipt or static audit:
`mode-1 club carrier 11 changes its fixed roster row count`. The exact
effective package names 23 Real Sociedad rows; the parser-bound base roster
has 25 rows, with only base carriers 224 and 2618 omitted. The fresh paths
`.local/season-workspace-v1/2000-01-calle-elkin-alias-roster-carrier1001-20260910-r4-game/`
and `...-r4-build/` are retained untouched as non-evidence. The game tree has
the expected 275 copied base files, and its three database files remain
byte-identical to the verified base: `ENT98030.FDI`
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`,
`EQ98030.FDI`
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`, and
`JUG98030.FDI`
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`.

No source, current manifest, canonical package, static audit, runtime route,
screenshot, release link, or 2015/16 release file changed. 2000/01 remains
`provisional-not-playable` and `release_eligible: false`; no published delivery
gate has moved, so the generated delivery-status JSON remains correct and
unchanged. The next smallest action is a parser-bound, no-overwrite fixed-row
reconciliation for only mode-1 club carrier 11 from this exact three-repair
candidate, preserving source and identity claims, followed by a fresh
canonical-workspace candidate ingress. It must not acquire source or infer
static, runtime, or playable qualification.

## 2000/01 three-repair carrier-11 preservation derivative (2026-09-10)

The prescribed no-overwrite fixed-row reconciliation completed directly from
the exact three-repair canonical-workspace candidate at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1001-20260910-r1/season-package.candidate.json`
(SHA-256 `e60a0f8b211283d1e0d605297dffadde917ca3f0ca3e1d90db04a7c9e08ae690`).
It re-verified the clean-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6` and
the matching 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The new static-only candidate is
`.local/season-canonical-alias-roster-carrier11-candidate-v1/2000-01-20260910-r1/season-package.alias-roster-carrier11-reconciled.json`
(SHA-256 `00e14831e478389d43c2c54a373226811d5972285b7f7dc2fd7eca82b04b9da5`),
with reconciliation audit SHA-256
`4fb846d9e0fa4194ca82b15378b9b5216ca8eb335ddf53e0e2f5d7960fea8116`.
It restores precisely the two omitted Real Sociedad base rows in parser-backed
base order: carrier 224, Francisco Javier DE PEDRO Falque, and carrier 2618,
Ricardo Manuel da Silva SÁ PINTO. Both are whole-record
`preserve-existing-mode1` declarations with `static-contract` proof and
unresolved/native-no-photo outcomes; neither creates a dated source, identity,
ratings, or portrait claim.

Strict V2 validation passes in the reconciler and independently for the
written package. A semantic-isolation comparison passes after removing only
those two player and unresolved-portrait declarations and restoring carrier
11's original 23-row list: the remainder is identical to the input candidate.
No source, current manifest, canonical package, binary materialisation, clean
audit, release link, runtime route, screenshot, delivery-status JSON, or
2015/16 release file changed. 2000/01 remains `provisional-not-playable` and
`release_eligible: false`; no published delivery gate has moved.

The next smallest action is a fresh, no-overwrite canonical-workspace
candidate ingress from these exact carrier-11 bytes, binding the display-alias
receipt and all four ordered roster-reconciliation receipts. It must not
register a canonical package or infer static, runtime, or playable
qualification.

## 2000/01 four-repair canonical-workspace ingress (2026-09-10)

The prescribed no-overwrite canonical-workspace ingress has completed at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier11-20260910-r1/`.
Its candidate package is byte-identical to the carrier-11 preservation
derivative, with SHA-256
`00e14831e478389d43c2c54a373226811d5972285b7f7dc2fd7eca82b04b9da5`.
The promotion audit has SHA-256
`fbfa52b50dcddade1fb29d2e27d0603b584aa87e6887d143fa9eac445fb0e135`.

The factory re-attested the calendar-bound Calle Elkin package SHA-256
`a51d67e2eb01f454cfe27b16379c7330edf6902c6a95fd7348200f926cf81550`,
the calendar-binding audit SHA-256
`5b8184eb62d4a7a008fa1db126ddd4e154f527e68c3f7eec214caada9f6501b4`,
the 3,216-name display-alias repair SHA-256
`2f1c586a99c3057bf01e216558ef8855d6c455f67f4a3115d78eb8388cd9d15c`,
and the verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`.
It also verifies the ordered whole-row preservation chain: carrier 1 through
audit `67fb6f8360d390838725b0f8dbc33f11cc913549942f4d7fd9391a97900a7938`,
carrier 10 through audit
`ea9379d0126a54162f8f865d4abef8a5b227efd37437beefb3f13cb11f950f21`,
carrier 1001 through audit
`cb32a848e2c6907c0451b85a2600d74a8a380a562a01d9cb47defbca5b4b37e9`,
and carrier 11 through audit
`4fb846d9e0fa4194ca82b15378b9b5216ca8eb335ddf53e0e2f5d7960fea8116`.

Strict V2 validation, calendar binding, display-alias binding, all four
ordered roster-reconciliation bindings, verified-base validation, workspace
validation, and workspace preparation pass. The emitted workspace, prepared
effective package, and non-executable build-plan candidate have SHA-256
values `d71605be6a088ea0afd0a8d4d901c79fe7ba0637ff7227cf0b3d388fd71e59d1`,
`f3dd8f43942fbd24a85565c0ba39ef09edc5e83512f4ae0aab6a7b3f1e5d0168`,
and `d5f75428c7108a4381ec002352c1391b4dd8aea83090e48334b1e938911d5ac8`,
respectively.

This remains an ingress-only static candidate: no compiler materialisation,
static audit, release manifest or link, PM99 runtime route, screenshot, source
acquisition, current manifest, canonical package, or 2015/16 release file was
changed. 2000/01 therefore remains `provisional-not-playable` and
`release_eligible: false`; no published delivery gate moved, so the delivery
status JSON remains unchanged. The next smallest action is one fresh,
no-overwrite workspace compile of this exact prepared effective package against
the verified clean base; a later independent matching compile remains
required, and neither compile may be treated as runtime or release evidence.

## 2000/01 four-repair canonical-workspace compile incomplete (2026-09-10)

One fresh, no-overwrite workspace compile was started from the exact
four-repair candidate into
`.local/season-workspace-v1/2000-01-calle-elkin-alias-roster-carrier11-20260910-r2-{game,build}/`.
The retained `r2` game tree contains the expected 275 copied base files, and
the five workspace-preparation reports were written.  Its effective package
has SHA-256 `f3dd8f43942fbd24a85565c0ba39ef09edc5e83512f4ae0aab6a7b3f1e5d0168`,
matching the already recorded prepared-effective hash.  The three `DBDAT`
files remain byte-identical to the verified clean base: `ENT98030.FDI`
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`,
`EQ98030.FDI` `e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`,
and `JUG98030.FDI`
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`.

The invocation did not produce a database-compiler receipt or clean-base
audit.  A retry against `r2` then correctly refused to replace the retained
materialisation tree.  `r2` is therefore incomplete non-evidence and must not
be reused, moved, or treated as static qualification.  No source, package,
manifest, release link, runtime evidence, screenshot, delivery-status JSON,
or 2015/16 release file changed.  2000/01 remains
`provisional-not-playable` and `release_eligible: false`; no published gate
moved.  The next smallest action is one new `r3` no-overwrite workspace
compile of the same four-repair candidate, allowed to complete before its
compiler receipt and clean audit are assessed.

## 2000/01 four-repair canonical-workspace `r3` compile blocker: carrier 12 (2026-09-10)

One fresh, no-overwrite workspace compile was run from the same four-repair
candidate into
`.local/season-workspace-v1/2000-01-calle-elkin-alias-roster-carrier11-20260910-r3-{game,build}/`.
It failed closed with `mode-1 club carrier 12 changes its fixed roster row
count` before a database-compiler receipt or clean-base audit was written.

The retained `r3` game tree contains 275 files. Its three database files
remain byte-identical to the verified clean base: `ENT98030.FDI`
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`,
`EQ98030.FDI`
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`,
and `JUG98030.FDI`
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`.
The five workspace-preparation reports were written; the effective package
has SHA-256 `f3dd8f43942fbd24a85565c0ba39ef09edc5e83512f4ae0aab6a7b3f1e5d0168`,
matching the prepared effective package from the candidate. The candidate
package remains SHA-256
`00e14831e478389d43c2c54a373226811d5972285b7f7dc2fd7eca82b04b9da5`.

`r3` is incomplete non-evidence and must not be reused, moved, or treated as
static qualification. No source, current manifest, package, release link,
runtime evidence, screenshot, delivery-status JSON, or 2015/16 release file
changed. 2000/01 remains `provisional-not-playable` and
`release_eligible: false`; no published delivery gate moved. The next
smallest action is one no-overwrite whole-row preservation derivative for
club carrier 12, bound to this exact four-repair package and the verified
clean base, followed by a new ingress rather than reuse of `r3`.

## 2000/01 four-repair carrier-12 preservation derivative (2026-09-10)

The prescribed no-overwrite fixed-row reconciliation completed from the exact
four-repair canonical-workspace candidate at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier11-20260910-r1/season-package.candidate.json`
(SHA-256 `00e14831e478389d43c2c54a373226811d5972285b7f7dc2fd7eca82b04b9da5`).
It re-verified verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6` and
the matching 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The new static-only derivative is
`.local/season-canonical-alias-roster-carrier12-candidate-v1/2000-01-20260910-r1/season-package.alias-roster-carrier12-reconciled.json`
(SHA-256 `4f938d93078ad749f74a938af65fe08b4cef2658a4e534ec8e9aa1471c1af5e9`),
with reconciliation audit SHA-256
`8394405ba6216071b8572fc7f3273aa2bfed1646de96e07ccd93aa3e3c2c3843`.
It restores precisely the two omitted Zaragoza base rows in parser-backed
27-row order: carrier 9229, Oswaldo Giroldo Junior, JUNINHO, and carrier 9852,
Mª Romero Poyón, JOSÉ MARI. Both are whole-record
`preserve-existing-mode1` declarations with `static-contract` proof and
unresolved/native-no-photo outcomes; neither creates a dated source, identity,
ratings, or portrait claim.

Strict V2 validation, canonical-receipt validation, and an independent
semantic-isolation comparison pass. Apart from `players/player-9229` and
`players/player-9852`, their unresolved portrait declarations, and the two
base-order insertions in `club-12`'s roster, the output is semantically
identical to the input candidate. No source, current manifest, canonical
package, binary materialisation, static audit, release link, runtime route,
screenshot, or 2015/16 release file changed. The generated delivery-status
JSON remains correctly unchanged: 2000/01 is still
`provisional-not-playable` and `release_eligible: false`; no published
delivery gate moved.

The next smallest action is a fresh, no-overwrite canonical-workspace
candidate ingress from these exact carrier-12 bytes, binding the display-alias
receipt and all five ordered roster-reconciliation receipts. It must not
register a canonical package or infer static, runtime, or playable
qualification.

## 2000/01 five-repair canonical-workspace ingress (2026-09-10)

The prescribed no-overwrite canonical-workspace ingress has completed at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier12-20260910-r1/`.
Its candidate package is byte-identical to the carrier-12 preservation
derivative, with SHA-256
`4f938d93078ad749f74a938af65fe08b4cef2658a4e534ec8e9aa1471c1af5e9`.
The promotion audit has SHA-256
`29142d39e9bfa6f5fc34f954e6a38972920c0851298566f46591e2e4bcdc1700`.

The factory re-attested the calendar-bound Calle Elkin package SHA-256
`a51d67e2eb01f454cfe27b16379c7330edf6902c6a95fd7348200f926cf81550`,
calendar-binding audit SHA-256
`5b8184eb62d4a7a008fa1db126ddd4e154f527e68c3f7eec214caada9f6501b4`,
3,216-name display-alias repair SHA-256
`2f1c586a99c3057bf01e216558ef8855d6c455f67f4a3115d78eb8388cd9d15c`,
and verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`.
It verifies the ordered whole-row preservation chain for club carriers 1, 10,
1001, 11, and 12 through audits
`67fb6f8360d390838725b0f8dbc33f11cc913549942f4d7fd9391a97900a7938`,
`ea9379d0126a54162f8f865d4abef8a5b227efd37437beefb3f13cb11f950f21`,
`cb32a848e2c6907c0451b85a2600d74a8a380a562a01d9cb47defbca5b4b37e9`,
`4fb846d9e0fa4194ca82b15378b9b5216ca8eb335ddf53e0e2f5d7960fea8116`,
and `8394405ba6216071b8572fc7f3273aa2bfed1646de96e07ccd93aa3e3c2c3843`,
respectively.

Strict V2, calendar, display-alias, all five ordered roster-reconciliation,
verified-base, workspace, and workspace-preparation contracts pass. The
emitted workspace, prepared effective package, and non-executable build-plan
candidate have SHA-256 values
`c2781e30989a988f1b2778ec8540a85262fec9813f6ac442220f33be29f48bf2`,
`fb52739bcc1556f22f5b6460a7f3d7c22fa88a976617e5ddccc68d0294aa6a23`,
and `8485f4e2f93aad1b192fe0b46033129f5cbd890fda92452039c3514f9c2f24d6`,
respectively. A direct workspace check also returns `ok: true`.

No source was acquired, no current manifest or canonical package was moved,
and no binary compiler materialisation, clean audit, release link, runtime
route, screenshot, delivery-status JSON, or 2015/16 release file changed.
2000/01 remains `provisional-not-playable` and `release_eligible: false`; no
published delivery gate has moved. The next smallest action is one fresh,
no-overwrite workspace compile of this exact prepared effective package against
the verified clean base. It must remain static-only, with a later independent
matching compile still required before a build plan or runtime work is
considered.

## 2000/01 five-repair canonical-workspace compile blocker: club carrier 1251 (2026-09-10)

One fresh, no-overwrite workspace compile was run from the exact five-repair
candidate at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier12-20260910-r1/`
against `.local/season-pipeline-v2/pm99-base-clean`. The compiler re-prepared
the expected effective package at
`.local/season-workspace-v1/2000-01-calle-elkin-alias-roster-carrier12-20260910-r5-build/season-package.effective.json`;
its SHA-256 is
`fb52739bcc1556f22f5b6460a7f3d7c22fa88a976617e5ddccc68d0294aa6a23`,
matching the candidate's prepared-effective hash.

The compiler then failed closed before emitting a compiler receipt or clean
static audit: `mode-1 club carrier 1251 changes its fixed roster row count`.
The bounded base/package comparison identifies Rangers (carrier 1251) as
declaring 23 of its 24 parser-backed base rows, with no extra rows. The sole
omission is carrier 8540, Giovanni VAN BRONCKHORST, between carriers 7183 and
9099; the existing static-ingress reconciliation audit records its parser-read
whole-record payload SHA-256
`5a505f6b1c95493871766d407c1b6a73589a666aa50b89a35115eeb27ff27844`.

The fresh `r5` game tree is incomplete non-evidence and must not be reused,
moved, or treated as static qualification. Its three database files remain
byte-identical to the verified base: `ENT98030.FDI`
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`,
`EQ98030.FDI`
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`,
and `JUG98030.FDI`
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`.
No source, current manifest, canonical package, static audit, runtime route,
screenshot, release link, delivery-status JSON, or 2015/16 release file
changed. 2000/01 remains `provisional-not-playable` and
`release_eligible: false`; no published delivery gate moved. The next smallest
action is one parser-bound, no-overwrite whole-row preservation derivative for
only mode-1 club carrier 1251, restoring carrier 8540 in exact base order with
an unresolved/native-no-photo outcome, followed by a fresh canonical-workspace
candidate ingress. It must not acquire source or infer static, runtime, or
playable qualification.

## 2000/01 five-repair carrier-1251 preservation derivative (2026-09-10)

The prescribed no-overwrite fixed-row reconciliation completed from the exact
five-repair canonical-workspace candidate at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier12-20260910-r1/season-package.candidate.json`
(SHA-256 `4f938d93078ad749f74a938af65fe08b4cef2658a4e534ec8e9aa1471c1af5e9`).
It re-verified the verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6` and
the matching 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The new static-only derivative is
`.local/season-canonical-alias-roster-carrier1251-candidate-v1/2000-01-20260910-r1/season-package.alias-roster-carrier1251-reconciled.json`
(SHA-256 `b041af8f8e2de36d2b4c69e3836c23e07764ece752e1632692d1b008a31317d8`),
with reconciliation audit SHA-256
`50010bb9dab948d62e60b32887f8ef3aa3a6c8abdb375b989e84277561f77e66`.
It restores exactly one omitted Rangers base row in parser-backed 24-row order:
carrier 8540, Giovanni VAN BRONCKHORST, between carriers 7183 and 9099. The
row is a whole-record `preserve-existing-mode1` declaration with
`static-contract` proof and an unresolved/native-no-photo outcome; it makes no
dated source, identity, ratings, or portrait claim.

The reconciler and an independent strict V2 validation pass. No source,
current manifest, canonical package, binary materialisation, clean audit,
release link, runtime route, screenshot, or 2015/16 release file changed.
2000/01 remains `provisional-not-playable` and `release_eligible: false`; no
published delivery gate moved, so the generated delivery-status JSON remains
correctly unchanged. The next smallest action is a fresh, no-overwrite
canonical-workspace candidate ingress from these exact carrier-1251 bytes,
binding the display-alias receipt and all six ordered roster-reconciliation
receipts. It must not register a canonical package or infer static, runtime,
or playable qualification.

## 2000/01 six-repair canonical-workspace ingress (2026-09-10)

The prescribed no-overwrite canonical-workspace ingress completed at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1251-20260910-r1/`.
An independently materialised `r2` path is byte-identical for the candidate,
prepared effective package, and promotion audit; it provides a deterministic
check of this ingress only, not a second static compile. The candidate package
SHA-256 is `b041af8f8e2de36d2b4c69e3836c23e07764ece752e1632692d1b008a31317d8`,
the prepared effective-package SHA-256 is
`a0068a151266abc2f852d2ca9d457eb0cdcb854c0e172ecf5aa202ffd0b5803d`, and
the promotion-audit SHA-256 is
`650fd6336eead48962cd25217e6fc46ea893fbb39686dc1a053d96bfd77d3fc9`.

The factory passes strict V2, calendar, display-alias, verified-base, workspace,
and workspace-preparation contracts. It also verifies the ordered whole-row
reconciliation chain for club carriers 1, 10, 1001, 11, 12, and 1251; the final
carrier-1251 audit is SHA-256
`50010bb9dab948d62e60b32887f8ef3aa3a6c8abdb375b989e84277561f77e66` and
restores only Giovanni VAN BRONCKHORST (carrier 8540) under the existing
unresolved/native-no-photo preservation rule. The verified-base descriptor
remains SHA-256 `512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`.

This is an ingress-only static candidate: no binary compiler materialisation,
clean audit, release manifest or link, PM99 runtime route, screenshot, source
intake, current manifest, canonical package, or 2015/16 release file changed.
The candidate explicitly remains `release_eligible: false`; 2000/01 remains
`provisional-not-playable`, so the generated delivery-status JSON correctly
remains unchanged. The next smallest action is one fresh, no-overwrite
workspace compile of the exact prepared effective package against the verified
clean base; it must remain static-only and needs a later independent matching
compile before build-plan or runtime work.

## 2000/01 six-repair canonical-workspace compile blocker: club carrier 1252 (2026-09-10)

One fresh, no-overwrite static-only workspace compile ran from
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1251-20260910-r1/`
against `.local/season-pipeline-v2/pm99-base-clean`.  It re-prepared
`season-package.effective.json` with SHA-256
`a0068a151266abc2f852d2ca9d457eb0cdcb854c0e172ecf5aa202ffd0b5803d`,
matching the candidate's prepared-effective package, then failed closed before
emitting a compiler receipt or clean static audit: `mode-1 club carrier 1252
changes its fixed roster row count`.

The bounded parser-backed comparison identifies `club-1252` as declaring 22
of its 23 fixed base roster rows.  The missing base row is carrier 9283,
between carriers 9179 and 9621.  The incomplete `r6` game tree's three
database files remain byte-identical to the verified clean base:
`ENT98030.FDI` `729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`,
`EQ98030.FDI` `e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`,
and `JUG98030.FDI`
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`.
Those incomplete paths are non-evidence and must not be reused, moved, or
treated as static qualification.

No source was acquired, and no current manifest, canonical package, static
audit, runtime route, screenshot, release link, delivery-status JSON, or
2015/16 release file changed.  2000/01 remains `provisional-not-playable`
and `release_eligible: false`; no published delivery gate moved.  The next
smallest action is one parser-bound, no-overwrite whole-row preservation
derivative for mode-1 club carrier 1252, restoring carrier 9283 in exact base
order with an unresolved/native-no-photo outcome, followed by fresh canonical
candidate ingress.  It must not acquire source or infer static, runtime, or
playable qualification.

## 2000/01 six-repair carrier-1252 preservation derivative (2026-09-10)

The prescribed parser-bound, no-overwrite fixed-row reconciliation completed
from the exact six-repair canonical-workspace candidate at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1251-20260910-r1/season-package.candidate.json`
(SHA-256 `b041af8f8e2de36d2b4c69e3836c23e07764ece752e1632692d1b008a31317d8`).
It re-verified the verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6` and
the matching 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The new static-only derivative is
`.local/season-canonical-alias-roster-carrier1252-candidate-v1/2000-01-20260910-r1/season-package.alias-roster-carrier1252-reconciled.json`
(SHA-256 `b8e9e453036cd4bf51f0b24214c00f0eaf182e04ea2a875bc6120832771fdb53`),
with reconciliation audit SHA-256
`275ef88e02f2f8c5536bd6e3eb9fc1926681d335049f5ef53527bcfe1ccfe2f0`.
It restores exactly one omitted `club-1252` base row in parser-backed 23-row
order: carrier 9283, Reginald (Regi) Waldie BLINKER, between carriers 9179
and 9621. The row is a whole-record `preserve-existing-mode1` declaration
with `static-contract` proof and an unresolved/native-no-photo outcome; it
makes no dated source, identity, ratings, or portrait claim.

The reconciler's strict V2 validation passes. An independent semantic
isolation comparison also passes: after removing only `player-9283`, its
unresolved portrait declaration, and its one `club-1252` roster insertion,
the result is identical to the input candidate. No source, current manifest,
canonical package, binary materialisation, clean audit, release link, runtime
route, screenshot, or 2015/16 release file changed. 2000/01 remains
`provisional-not-playable` and `release_eligible: false`; no published
delivery gate moved, so the generated delivery-status JSON remains correctly
unchanged. The next smallest action is a fresh, no-overwrite
canonical-workspace candidate ingress from these exact carrier-1252 bytes,
binding the display-alias receipt and all seven ordered roster-reconciliation
receipts. It must not register a canonical package or infer static, runtime,
or playable qualification.

## 2000/01 seven-repair canonical-workspace ingress (2026-09-10)

The prescribed no-overwrite canonical-workspace ingress completed at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1252-20260910-r1/`.
Its candidate package is byte-identical to the carrier-1252 preservation
derivative, SHA-256
`b8e9e453036cd4bf51f0b24214c00f0eaf182e04ea2a875bc6120832771fdb53`.
The prepared effective package, promotion audit, and non-executable build-plan
candidate have SHA-256 values
`3b4bcd329c32b1134edb8a8dae7d0e99772d0dbca53df7b4771d30d5d001dcb9`,
`cd8c0a4456937133737c951fa2c4e9e20049ef839c34fdd6f33c950dc48898bc`, and
`2e3dd7c18ab07cc9d997dc821b4481b150769010d35ddaf597e03306d3804daf`,
respectively.

The factory re-attested the Calle Elkin calendar-bound source package SHA-256
`a51d67e2eb01f454cfe27b16379c7330edf6902c6a95fd7348200f926cf81550`,
its calendar-binding audit SHA-256
`5b8184eb62d4a7a008fa1db126ddd4e154f527e68c3f7eec214caada9f6501b4`,
the 3,216-name display-alias derivative SHA-256
`2f1c586a99c3057bf01e216558ef8855d6c455f67f4a3115d78eb8388cd9d15c`,
and the verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`.
It verifies the ordered whole-row preservation chain for club carriers 1, 10,
1001, 11, 12, 1251, and 1252; the final receipt is SHA-256
`275ef88e02f2f8c5536bd6e3eb9fc1926681d335049f5ef53527bcfe1ccfe2f0` and
restores only carrier 9283 under the existing unresolved/native-no-photo
preservation rule.

Strict V2, calendar, display-alias, all seven ordered roster-reconciliation,
verified-base, workspace, and workspace-preparation contracts pass. No source
was acquired and no current manifest or canonical package was moved; no binary
compiler materialisation, clean audit, release link, PM99 runtime route,
screenshot, delivery-status JSON, or 2015/16 release file changed. 2000/01
therefore remains `provisional-not-playable` and `release_eligible: false`.
The next smallest action is one fresh, no-overwrite workspace compile of this
exact prepared effective package against the verified clean base. It must
remain static-only and needs a later independent matching compile before a
build plan or runtime work is considered.

## 2000/01 seven-repair canonical-workspace compile blocker: club carrier 1256 (2026-09-10)

One fresh, no-overwrite static-only workspace compile ran from
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1252-20260910-r1/`
against `.local/season-pipeline-v2/pm99-base-clean`, using new `r7` game and
build paths under `.local/season-workspace-v1/`. It prepared the effective
package with SHA-256
`3b4bcd329c32b1134edb8a8dae7d0e99772d0dbca53df7b4771d30d5d001dcb9`,
matching the hash-bound candidate preparation, then failed closed before a
database-compiler receipt or clean static audit was emitted: `mode-1 club
carrier 1256 changes its fixed roster row count`.

The retained `r7` tree has the expected 275 copied base files, and its three
database files remain byte-identical to the verified clean base: `ENT98030.FDI`
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`,
`EQ98030.FDI`
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`,
and `JUG98030.FDI`
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`.
It is incomplete non-evidence and must not be reused, moved, or treated as
static qualification.

A read-only parser-backed comparison identifies Heart of Midlothian
(`club-1256`) as declaring 24 of its 25 fixed base rows, with no extra rows.
The sole omission is carrier 5472, Juan José Carricondo Pérez (`JUANJO`),
between carriers 2752 and 8406; its parsed base payload SHA-256 is
`33c3617480386f4ca5499065776a0c9c71d1a9bdb7e39f4969c28c7e84abfb83`.

No source was acquired, and no current manifest, canonical package, static
audit, release link, runtime route, screenshot, delivery-status JSON, or
2015/16 release file changed. 2000/01 remains `provisional-not-playable` and
`release_eligible: false`; no published delivery gate moved. The next smallest
action is one parser-bound, no-overwrite whole-row preservation derivative for
only mode-1 club carrier 1256, restoring carrier 5472 in exact base order with
an unresolved/native-no-photo outcome, followed by fresh canonical-candidate
ingress. It must not acquire source or infer static, runtime, or playable
qualification.

## 2000/01 seven-repair carrier-1256 preservation derivative (2026-09-10)

The prescribed parser-bound, no-overwrite fixed-row reconciliation completed
from the exact seven-repair canonical-workspace candidate at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1252-20260910-r1/season-package.candidate.json`
(SHA-256 `b8e9e453036cd4bf51f0b24214c00f0eaf182e04ea2a875bc6120832771fdb53`).
It re-verified the verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6` and
the matching 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The new static-only derivative is
`.local/season-canonical-alias-roster-carrier1256-candidate-v1/2000-01-20260910-r1/season-package.alias-roster-carrier1256-reconciled.json`
(SHA-256 `48eae462a005cfa290476668c4e36f3c0e87b525a1f93f583c0ae994e09e3374`),
with reconciliation audit SHA-256
`16bc394d89558d802119293df7396d63ced774e98a7cca53103cd99fa88b5953`.
It restores exactly one omitted Heart of Midlothian (`club-1256`) base row in
parser-backed 25-row order: carrier 5472, Juan José Carricondo Pérez
(`JUANJO`), between carriers 2752 and 8406. The row is a whole-record
`preserve-existing-mode1` declaration with `static-contract` proof and an
unresolved/native-no-photo outcome; it makes no dated source, identity,
ratings, or portrait claim.

The reconciler and an independent strict V2 validation pass. A semantic
isolation comparison also passes: after removing only `player-5472`, its
unresolved portrait declaration, and its one `club-1256` roster insertion,
the derivative is byte-identical in canonical JSON to the input candidate. No
source, current manifest, canonical package, binary materialisation, clean
audit, release link, runtime route, screenshot, or 2015/16 release file
changed. 2000/01 remains `provisional-not-playable` and
`release_eligible: false`; no published delivery gate moved, so the generated
delivery-status JSON remains correctly unchanged. The next smallest action is
a fresh, no-overwrite canonical-workspace candidate ingress from these exact
carrier-1256 bytes, binding the display-alias receipt and all eight ordered
roster-reconciliation receipts. It must not register a canonical package or
infer static, runtime, or playable qualification.

## 2000/01 eight-repair canonical-workspace ingress qualification (2026-09-10)

The existing no-overwrite canonical-workspace ingress at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1256-20260910-r1/`
has now been independently qualified. Its candidate package is byte-identical
to the carrier-1256 preservation derivative, SHA-256
`48eae462a005cfa290476668c4e36f3c0e87b525a1f93f583c0ae994e09e3374`.
The prepared effective package, promotion audit, and non-executable build-plan
candidate have SHA-256 values
`64e433592c5b40b25dba1652452d8dc56264967f80381852530dbdaeb82062df`,
`e17925834760a14c4986982775889d156562be2b4c9ab38488a61856a2ffb9fa`,
and `ff9a20f2ce5da0d2632675f53de91695e164321d6cffaebb43e3c53320de926d`,
respectively.

The audit binds the unchanged calendar source, display-alias derivative,
verified clean base, and the ordered whole-row preservation chain for club
carriers 1, 10, 1001, 11, 12, 1251, 1252, and 1256. The final carrier-1256
receipt is SHA-256
`16bc394d89558d802119293df7396d63ced774e98a7cca53103cd99fa88b5953`;
the verified-base descriptor remains SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`.
Independent strict V2 validation and a direct workspace check both return
`ok: true`.

No source was acquired and no current manifest, canonical package, binary
materialisation, clean audit, release link, PM99 runtime route, screenshot, or
2015/16 release file changed. This ingress remains explicitly
`release_eligible: false`; 2000/01 remains `provisional-not-playable`, with no
published delivery gate moved. The next smallest action is one fresh,
no-overwrite workspace compile of this exact prepared effective package
against the verified clean base. It must remain static-only and needs a later
independent matching compile before build-plan or runtime work.

## 2000/01 eight-repair canonical-workspace compile blocker: club carrier 1260 (2026-09-10)

One fresh, no-overwrite static-only workspace compile ran from
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1256-20260910-r1/`
against `.local/season-pipeline-v2/pm99-base-clean`, using new `r8` game and
build paths under `.local/season-workspace-v1/`. It prepared the effective
package with SHA-256
`64e433592c5b40b25dba1652452d8dc56264967f80381852530dbdaeb82062df`,
matching the hash-bound candidate preparation, then failed closed before a
database-compiler receipt or clean static audit was emitted: `mode-1 club
carrier 1260 changes its fixed roster row count`.

The retained `r8` tree is incomplete non-evidence. Its three database files
remain byte-identical to the verified clean base: `ENT98030.FDI`
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`,
`EQ98030.FDI`
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`,
and `JUG98030.FDI`
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`.
It must not be reused, moved, or treated as static qualification.

The existing hash-bound static-ingress reconciliation audit identifies
`club-1260` as declaring 24 of its 25 parser-backed base rows, with no extra
rows. The sole omission is carrier 19290, Scott Anderson James MCCULLOCH,
between carriers 19289 and 29898; its parser-read whole-record payload SHA-256
is `9f0bbe3f8ddd7d342c8dbccdac74887a1e504dfcef07ba5b716e591c91d35147`.

No source was acquired, and no current manifest, canonical package, clean
audit, release link, runtime route, screenshot, delivery-status JSON, or
2015/16 release file changed. 2000/01 remains
`provisional-not-playable` and `release_eligible: false`; no published
delivery gate moved. The next smallest action is one parser-bound,
no-overwrite whole-row preservation derivative for only mode-1 club carrier
1260, restoring carrier 19290 in exact base order with an
unresolved/native-no-photo outcome, followed by fresh canonical-candidate
ingress. It must not acquire source or infer static, runtime, or playable
qualification.

## 2000/01 eight-repair carrier-1260 preservation derivative (2026-09-11)

The prescribed parser-bound, no-overwrite fixed-row reconciliation completed
from the exact eight-repair canonical-workspace candidate at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1256-20260910-r1/season-package.candidate.json`
(SHA-256 `48eae462a005cfa290476668c4e36f3c0e87b525a1f93f583c0ae994e09e3374`).
It re-verified the verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`
and its 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The new static-only derivative is
`.local/season-canonical-alias-roster-carrier1260-candidate-v1/2000-01-20260911-r1/season-package.alias-roster-carrier1260-reconciled.json`
(SHA-256 `6e8c11ecdd81a336e61ee8816827b2bf232e4e8c2b490bb64020306d3aaee3e8`),
with reconciliation audit SHA-256
`c544bd878028cbcc629f830e3cc1c305192949fb5960022171c631ecd73129ec`.
It restores exactly one omitted Dundee (`club-1260`) base row in parser-backed
25-row order: carrier 19290, Scott Anderson James MCCULLOCH, between carriers
19289 and 29898. The row is a whole-record `preserve-existing-mode1`
declaration with `static-contract` proof and an unresolved/native-no-photo
outcome; it makes no dated source, identity, ratings, or portrait claim.

The reconciler and an independent strict V2 validation pass. A semantic
isolation comparison also passes: after removing only `player-19290`, its
unresolved portrait declaration, and its one `club-1260` roster insertion,
the derivative is identical to the input candidate. No source, current
manifest, canonical package, binary materialisation, clean audit, release
link, runtime route, screenshot, delivery-status JSON, or 2015/16 release
file changed. 2000/01 remains `provisional-not-playable` and
`release_eligible: false`; no published delivery gate moved. The next
smallest action is a fresh, no-overwrite canonical-workspace candidate ingress
from these exact carrier-1260 bytes, binding the display-alias receipt and all
nine ordered roster-reconciliation receipts. It must not register a canonical
package or infer static, runtime, or playable qualification.

## 2000/01 nine-repair canonical-workspace ingress (2026-09-11)

The prescribed fresh, no-overwrite canonical-workspace ingress completed at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1260-20260911-r1/`.
Its candidate package is byte-identical to the carrier-1260 preservation
derivative, SHA-256
`6e8c11ecdd81a336e61ee8816827b2bf232e4e8c2b490bb64020306d3aaee3e8`.
The prepared effective package, promotion audit, and non-executable build-plan
candidate have SHA-256 values
`93e44d2d03fadf8cbb8530fa1685555fe8024f490784c099d59d87e1dd486adb`,
`69ce67a0f650734492be778a58e072dae3f96f619d8ab2ab849bdd70e7bd5956`,
and `b732790aacbf4911d9dbd6b7fbf37fb6f827d3eccbf0d13ce2f0c684f9128bd`,
respectively.

The audit re-verifies the calendar binding, display-alias receipt, verified
clean base, and all nine ordered whole-row preservation receipts for club
carriers 1, 10, 1001, 11, 12, 1251, 1252, 1256, and 1260. Its final receipt
binding is SHA-256
`c544bd878028cbcc629f830e3cc1c305192949fb5960022171c631ecd73129ec`;
the verified-base descriptor remains SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`.
Independent strict V2 validation and a direct workspace check both returned
`ok: true`.

No source was acquired and no current manifest, canonical package, binary
materialisation, clean audit, release link, PM99 runtime route, screenshot, or
2015/16 release file changed. The candidate remains `release_eligible: false`;
2000/01 remains `provisional-not-playable`, so the generated delivery-status
JSON remains correctly unchanged. The next smallest action is one fresh,
no-overwrite static-only workspace compile from this exact candidate against
the verified clean base. It must not reuse an incomplete prior tree or infer
static, runtime, or playable qualification from a failed compile.

## 2005/06 existing runtime attestation binding (2026-09-11)

The existing successful r2 Stoke route was bound without rerunning acquisition or
changing a game tree. The attestation is
`.local/season-runtime-evidence-v1/post1999_2005_06_target_calendar_runtime_20260909_r2/runtime-attestation.json`
(SHA-256 `7547502a959f0f102e314cecd2e8f45c4b6f29132c235260fa0a43b0ddb79e52`).
It binds the canonical 2005/06 package and clean static qualification to the
target calendar, successful route summary, and
`screens/021_squad_inspect.png` (SHA-256
`ac56801b83b2c40a3bd2fb560e3dbddfd82ff42fed4d80ef0b4f82b53a916f5f`).

The status refresh and direct runtime-binding check pass. 2005/06 moved from
missing runtime proof to `playable-known-good`; no release link was created and
the established 2015/16 release is unchanged. The next smallest action is a
separate reviewed decision on immutable 2005/06 release registration.

## 2000/01 nine-repair canonical-workspace compile blocker: club carrier 1303 (2026-09-11)

One fresh, no-overwrite static-only workspace compile ran from
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1260-20260911-r1/`
against `.local/season-pipeline-v2/pm99-base-clean`, using new `r9` game and
build paths under `.local/season-workspace-v1/`. It prepared the effective
package with SHA-256
`93e44d2d03fadf8cbb8530fa1685555fe8024f490784c099d59d87e1dd486adb`,
matching the hash-bound candidate preparation, then failed closed before a
database-compiler receipt or clean static audit was emitted: `mode-1 club
carrier 1303 changes its fixed roster row count`.

The retained `r9` tree is incomplete non-evidence. Its three database files
remain byte-identical to the verified clean base: `ENT98030.FDI`
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`,
`EQ98030.FDI`
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`,
and `JUG98030.FDI`
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`.
It must not be reused, moved, or treated as static qualification.

Parser-backed read-only comparison identifies PAS Giannina (`club-1303`) as
declaring 20 of its 23 base rows, with no extra rows. The three omissions, in
base order, are carrier 19601, Stylianos GIANNAKOPOULOS (payload SHA-256
`368dcdf68b17407a31bdaf81f116b2da99301c844c6578ccd5c2d8fe5e1129c3`),
carrier 32090, Stavros TZIORTZIOPOULOS (payload SHA-256
`19e84c6d9e2a01c55147fdd218f3ee2e22309c79ce421e61e537a6d83de10520`),
and carrier 32094, Dimitrios ELEFTHEROPOULOS (payload SHA-256
`0e8fcc10728847119154e97c5ed8a7cb0cea8f5dea4015e9bc890ad29fba9215`).

No source was acquired, and no current manifest, canonical package, clean
audit, release link, runtime route, screenshot, delivery-status JSON, or
2015/16 release file changed. 2000/01 remains
`provisional-not-playable` and `release_eligible: false`; no published
delivery gate moved. The next smallest action is one parser-bound,
no-overwrite whole-row preservation derivative for only mode-1 club carrier
1303, restoring those three carriers in exact base order with unresolved
native-no-photo outcomes. It must not acquire source or infer static, runtime,
or playable qualification.

## 2000/01 nine-repair carrier-1303 preservation derivative (2026-09-11)

The prescribed parser-bound, no-overwrite fixed-row reconciliation completed
from the exact nine-repair canonical-workspace candidate at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1260-20260911-r1/season-package.candidate.json`
(SHA-256 `6e8c11ecdd81a336e61ee8816827b2bf232e4e8c2b490bb64020306d3aaee3e8`).
It re-verified the verified-base descriptor SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`
and its 275-file inventory fingerprint
`310f27f5d31fa53b5f1b9521a9b6b89322c4d5807f126d778dc693dfbe560118`.

The new static-only derivative is
`.local/season-canonical-alias-roster-carrier1303-candidate-v1/2000-01-20260911-r1/season-package.alias-roster-carrier1303-reconciled.json`
(SHA-256 `e06d96045b836ec9579a7ae54fd510579c49baf54604afd90451299748f760f2`),
with reconciliation audit SHA-256
`8ac5949f8b40c0f3bcf0fae147216afb7723fb1dff8530ed1d274b5b0b323ad7`.
It restores exactly three omitted PAS Giannina (`club-1303`) rows in their
parser-backed 23-row order: carrier 19601, Stylianos GIANNAKOPOULOS; carrier
32090, Stavros TZIORTZIOPOULOS; and carrier 32094, Dimitrios
ELEFTHEROPOULOS. Each is a whole-record `preserve-existing-mode1` declaration
with `static-contract` proof and an unresolved/native-no-photo outcome; none
makes a dated source, identity, ratings, or portrait claim.

The reconciler and an independent strict V2 validation pass. A semantic
isolation comparison also passes: after removing only those three players,
their three unresolved portrait declarations, and their `club-1303` roster
insertions, the derivative is identical to the input candidate. No source,
current manifest, canonical package, binary materialisation, clean audit,
release link, runtime route, screenshot, delivery-status JSON, or 2015/16
release file changed. 2000/01 remains `provisional-not-playable` and
`release_eligible: false`; no published delivery gate moved. The next
smallest action is a fresh, no-overwrite canonical-workspace candidate ingress
from these exact carrier-1303 bytes, binding the display-alias receipt and all
ten ordered roster-reconciliation receipts. It must not register a canonical
package or infer static, runtime, or playable qualification.

## 2000/01 ten-repair canonical-workspace ingress (2026-09-11)

The prescribed fresh, no-overwrite canonical-workspace ingress completed at
`.local/season-canonical-candidate-v1/2000-01-calle-elkin-alias-roster-carrier1303-20260911-r1/`.
Its candidate package is byte-identical to the carrier-1303 preservation
derivative, SHA-256
`e06d96045b836ec9579a7ae54fd510579c49baf54604afd90451299748f760f2`.
The prepared effective package, promotion audit, and non-executable build-plan
candidate have SHA-256 values
`b122512e72dbcbea2cf4c87342bff4da2e69100fe33e04b32c3844a149ed7893`,
`2e30bd644483f3e0d21ff5970ce63a57c2d520ee9b0f0be10947fc0d27a4a0e3`,
and `57d78948488d887b5bf986a45e3fc5388506c26162febfb5677e802c1f5fdd1f`,
respectively.

The audit re-verifies the calendar binding, display-alias receipt, verified
clean base, and all ten ordered whole-row preservation receipts for club
carriers 1, 10, 1001, 11, 12, 1251, 1252, 1256, 1260, and 1303. The verified
base descriptor remains SHA-256
`512e27ec6209435e3904bcc3954251b8eace1570292847a9e3f7251313fe36f6`.
Independent strict V2 validation and a direct workspace check both returned
`ok: true`.

No source was acquired and no current manifest, canonical package, binary
materialisation, clean audit, release link, PM99 runtime route, screenshot, or
2015/16 release file changed. The candidate remains `release_eligible: false`;
2000/01 remains `provisional-not-playable`, so the generated delivery-status
JSON remains correctly unchanged. The next smallest action is one fresh,
no-overwrite static-only workspace compile from this exact candidate against
the verified clean base. It must not reuse an incomplete prior tree or infer
static, runtime, or playable qualification from a failed compile.
