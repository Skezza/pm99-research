# 2000/01 worldwide playable-provisional closeout

Date: 2026-09-07

## Outcome

2000/01 has been rebuilt through the reusable source-backed English ingress
and proved in PM99. It is **playable-provisional**, not historically final.
The remaining historical queue is 30 ambiguous full-season transfer/loan
ownership choices. They are isolated in the duplicate-normalisation audit and
do not prevent playtesting.

The game tree is:

`.local/season-runtime-candidates-v1/2000-01/worldwide-source-backed-r1/game`

Launch it from the repository root with:

```bash
(cd .local/season-runtime-candidates-v1/2000-01/worldwide-source-backed-r1/game && wine ./MANAGPRE.EXE)
```

## Passed gates

- 92 English clubs have source-backed opening squads, ordered first XIs and
  dated managers, with zero layer gaps.
- The deterministic rating layer contains 2,300 players with zero rating gaps.
- All 92 English home kits have target-season HFK evidence and 276 rendered
  PM99 archive records.
- English authoring has zero blockers.
- 58 duplicate-person groups were normalised: 28 by unique opening evidence;
  30 remain explicit editorial ownership choices.
- Strict Season Package V2 validation and clean static compilation passed.
- The 2000/01 calendar executable was applied.
- PM99 reached and returned from Stoke City's Line-Up screen without a crash
  or Wine debugger.

## Hash-bound evidence

- Strict package SHA-256:
  `66a038cb37d7e534f97571d040f8113fcabe6dbfe19513e3c66943d8f04c27b0`
- Duplicate audit SHA-256:
  `c363b348a7e613eb94980f20d0180a1bb19b4acd7dfa3042369f95f59a70a0cd`
- Static ingress receipt SHA-256:
  `7a570d9a914ba42f48f4728176078f485aed5ff7f400307d319eb0839cd00134`
- Clean static audit SHA-256:
  `75503d20387965c9c681c93538f9843d11d2c41e8dc6ed06589d49778ee6b75b`
- Kit archive receipt SHA-256:
  `ef9575467b8d25471507b139a2e28b6d1cc4a838fbaa6bd5e22b8080b08304b3`
- Runner summary SHA-256:
  `8840ba2d8a4d70f8642df1309f325cae278eb162def56589b564b9b6e69adafb`
- Stoke screenshot SHA-256:
  `fd58f03cfc779ae8bc2353a312546fbc0ee35f8293bfabf4d9d2ba34dda89cae`

The accepted screenshot is
`upstream/pm99-runner/docs/artifacts/pm99_runner/post1999_2000_01_stoke_lineup_20260907_r2/screens/021_line_up_inspect.png`.
It visibly identifies Stoke City and August 2000. The accepted selector point
is division `562,302`, club `306,360`.

The earlier `r1` route selected Coventry City and is diagnostic evidence only.
This rejection demonstrates that runtime proof is checking the visible result,
not merely accepting a successful process exit.

## Source credit

Historical Football Kits supplies the dated English home-kit evidence and is
credited as “Copyright Historical Football Kits and reproduced by kind
permission.” Source graphics remain in the ignored evidence cache; the game
contains independent PM99-scale renders.
