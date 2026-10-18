# Static Ingress Milestone — 2026-09-04

## Scope

This records nine clean-static ingress proofs for the reusable worldwide
season pipeline: 2000/01–2007/08, plus 2020/21. It is not a playable-game, runtime,
historical-release, or screenshot claim.

The work advances the shared mechanics without altering any frozen source
capture, current manifest, registry, release tree, or the legacy 2015/16
world release.

## Corrected reusable mechanics

An ingress defect was found in `season_source_package_builder_v1.py`: a dated
source person could be assigned to a fixed mode-1 carrier that still retained
the template's whole-record `preserve-existing-mode1` policy.  The compiler
then correctly made no record write, leaving the baseline person's identity
in-game despite a target-season source claim.

The builder now removes the whole-record policy whenever it binds a dated
source person. Explicit field-level preservation remains unchanged. Existing
historical candidates use the bounded
`lift_mode1_source_write_policy_v1.py` migration, then go through:

1. parser-safe display alias binding;
2. exact fixed mode-1 base-row preservation, including only proven shared
   base rows; and
3. fresh compile plus a declared-change clean-base audit.

`season_static_ingress_v1.py` makes this no-overwrite sequence a single
reusable static-only command for later strict packages. It also repairs an
exact one-current-source versus one-stale-legacy mode-1 candidate pair before
strict ingress, but refuses to decide between two current source claims.

A further name-preflight correction makes the alias stage use exact case
comparison with the compiler. A case-only difference can otherwise appear
safe in preflight while making an overlong native DD6360 name fail during
materialisation. The stage now selects a proven source-derived alias instead.

## Verified static results

| Season | Source-policy lift | Alias changes | Fixed-row candidate | Compiler receipt | Clean static audit |
| --- | ---: | ---: | --- | --- | --- |
| 2000/01 | 618 | 3,188 | `b3dd3df1355802d0789fd2a9f9eccea9597e933fd0265922fad682fed17bb99e` | `cabdfedec80d989332d9933dab21b057841b108d361a65ddad39e1da7f5f9962` | pass, `7b4c2594cc53942a6615b9f84e9fe3226a3f10724eabbba139644eb4d13013b8` |
| 2001/02 | 598 | 3,274 | `74b019321f05f002d780b6f363382e04594456ac736108863350602dbcd17f90` | `1545601fa9811310adc0d02880c8e559a0cf455895473ac3ddf6d1969d9083c2` | pass, `11ee8f947b635853c6c81eb79f9226697c0e265d65ac17a057a78d4209adfe83` |
| 2002/03 | 681 | 3,278 | `50af10fd5299e487772f421d5317491349091343ab0823c46a0959a8e25e292a` | `35b16fc6e7958b805cdf595bdbd887a4b00992f4f31df3ae46debe1227046562` | pass, `72f7540b24387a5d354536d278521bbeac34da8eed976e0e1974fe5a9db4429d` |
| 2003/04 | 696 | 3,379 | `9889cfa19a92e7187d8a5509af296b11723537ce1dbf1b2f387d42a0a31e1f8b` | `00223a5c4df4abc01a978328b2064669a7e22cee16dcbcee4d56d7c1da57fb8b` | pass, `e39f21d16ac792734b14628cdc013717d935df07739f7591f53b0cc9ba8b0f27` |
| 2004/05 | 841 | 3,425 | `0ecd4d50c9f50f8c6cc643ef28c6daed8da6c5c73aa602d2ab3cc2f553b1486e` | `63546509e414238b9e748edfcf96a093e12526bd3622bb78a96b33322fe5b7d3` | pass, `4df167e458f6d10c1d12aa552f5c0dd1574b5c66fef5dd478a7a1b474dc2ecfe` |
| 2005/06 | 793 | 403 | `5af450aa8321a2077594630757eb3b4193a2165d57b637eb517c47b4fa9a5734` | `2f75538e9e520c54a930f258a8887abfe398204f46d55a03533e6f1582bf6cb8` | pass, `3223bdffe027a4bfb5f50171061b13b46be750d8d598b935cc787187930753ec` |
| 2006/07 | 863 | 3,625 | `0d4c99a9778fe60ac8999d88fbca5805b93a98674fa84396f41e589ef85772f0` | `e21b17182cbbb90509bedc94f217c39b32b0f3b6a4716551a8eabe5da1974f08` | pass, `ce4f00b99689e769fc9607c48d51a4afeaac3a4e3f0a06e161334ff122fb2e25` |
| 2007/08 | 846 | 3,755 | `1a795c02bb3daa426fd4832212919ca3075c94c57c1693735716767f3210db1b` | `4c9431d092b85fb62efc4e46258e049dd3da15741644552113778721b9b35907` | pass, `2eb7dc8231c853033eba0cb9ddfd67714d9a320fe6c079fbc7af6a224b3c9f9c` |
| 2020/21 | 853 | 3,671 | `ee1a3ea66a6ef87eebb88ceb8a5458fe3cfdc31eb9c570b2d21189fb990c01ae` | `a970316763254a885e868537baab9613a247364ce7bac9f3368cb222759183ab` | pass, `ca394f7d661a88e5a6d0b6440a653031f6b518c97fda9dec7e689244b4de7a54` |

All nine candidates selected all 451 fixed mode-1 clubs. Their bounded
whole-record fallback reconciliation covered 77 eligible clubs / 177 newly
preserved base rows. The clean audits confirmed all 451 fixed roster tails
were byte-identical to the base.

The audits also recorded the only derived mode-0 donor transactions: player
carriers `8396`, `20957`, and `10958` were removed from base teams `305`,
`309`, and `353`, respectively. Each was parser-backed, deterministic and
left its donor roster above the 20-player guard. They are now explicit audit
outputs rather than hidden compiler side effects.

## Reproduction shape

Use a strict V2 package, the exact verified clean base, and a fresh output
directory:

```bash
python3 scripts/season_static_ingress_v1.py \
  --package PATH/TO/strict-season-package.json \
  --base-tree PATH/TO/verified-clean-base \
  --verified-base PATH/TO/verified-base.json \
  --output-dir .local/season-static-ingress-v1/SEASON-REVISION
```

The command writes source-policy, alias and roster-reconciliation receipts,
a fresh `game/` materialisation, compiler receipt, clean-static audit and a
top-level static-ingress receipt. It refuses to overwrite its output path.

## Still required before any playable assertion

- calendar runtime validation;
- target-season manager source review and correct strings;
- historical kit materialisation;
- portraits/native-no-photo materialisation;
- ratings reconciliation;
- opening-XI and formation review;
- PM99 runtime validation; and
- target-season screenshot evidence.

The two results above are therefore `clean-static-ingress-complete-not-playable`.

## Explicit source-identity queue

2016/17 demonstrates the remaining source issue without creating a database
candidate. The ingress command safely restored 33 exact stale legacy rows and
then stopped before aliasing, reconciliation or compilation because 14
current-source/current-source same-person claims remain. Its reconciled source
candidate is SHA-256
`550278a70e5e307314b630b14efa5b347c655e8bcf02560cbfb9af82e0ba1450`;
the sealed blocked-preflight receipt is SHA-256
`b07fa2ceb343616a63f0c46c7ff7b102cbd32e263e51fe483f3408931115cd63`.

The traces show a systematic raw-ingress cause: both an all-season source and
an August source represented the same National League club under different
names (for example `Sutton United` / `Sutton Utd`). The next source-level
stage must preserve both credits and hashes, select the August opening-squad
representation, and allocate one canonical club identity—not delete or
manually rewrite player rows. Genuine inter-club claims remain hard blockers.
