# 2001/02 worldwide playable-provisional closeout

Date: 2026-09-07

## Outcome

2001/02 is the first post-1999 season rebuilt through the source-backed
English mode-0 ingress and proved in PM99. It is **playable-provisional**, not
historically final. The remaining measurable historical queue is 31 ambiguous
full-season transfer/loan ownership choices. Those choices are deterministic,
isolated in the duplicate-normalisation audit, and do not block playtesting.

The final local game tree is:

`.local/season-runtime-candidates-v1/2001-02/worldwide-source-backed-r2/game`

Launch it locally from the repository root with:

```bash
(cd .local/season-runtime-candidates-v1/2001-02/worldwide-source-backed-r2/game && wine ./MANAGPRE.EXE)
```

## Completed gates

- English source clubs: 92.
- English opening-squad/lineup layers: 92, zero layer gaps.
- English opening managers: 92, zero layer gaps.
- English editorial ratings: 2,296 players, zero rating gaps.
- English home kits: 92 exact-season source-ready contracts.
- English authoring blockers: zero.
- Worldwide duplicate groups: 59; 28 resolved by unique opening evidence and
  31 retained as explicit provisional editorial choices.
- Strict Season Package V2 validation: passed.
- Clean static compilation/audit: passed with 166 explicitly declared appended
  player carriers; no undeclared record-set drift was accepted.
- English kit render/materialisation: 92 carriers and 276 archive records.
- Calendar: 2001/02 executable applied and hash-verified.
- PM99 four-division selector smoke: passed without a crash or debugger.
- Genuine Stoke City Line-Up route: passed without a crash or debugger.

## Exact final evidence

- Strict package SHA-256:
  `620d66fcbac8bf9c69143de008144290d98312893b2ce498996d412f23eb452c`
- Duplicate-normalisation audit SHA-256:
  `d57c5e9c9c629397bbfa7d8bfdf28dc9fbda011b0bf1b5168e85d75fedea51c2`
- Static-ingress receipt SHA-256:
  `02bdf94c9fccd55f605575165989af9d89d201d21977b8d36704bbae0cf29cc2`
- Clean-static audit SHA-256:
  `ea89d95025ac6fbe962c4662792b45a3f4427c32f13b1b79973fd7b19965d80f`
- Kit archive receipt SHA-256:
  `90d159d9feb981d2be9b465cb6ec076707db17d505a91f7f4167170be55e22f0`
- Final Stoke runner summary SHA-256:
  `01237b73495c606532b15a5cffbb119b691f2384f6fd07b9ea914da4faaee0b8`
- Stoke Line-Up screenshot SHA-256:
  `2df58b54fd28f94632e8e801175e2d0518a47d44a845d140c7472f2035bd1503`

The screenshot is
`upstream/pm99-runner/docs/artifacts/pm99_runner/post1999_2001_02_stoke_lineup_20260907_r3/screens/021_line_up_inspect.png`.
It visibly identifies Stoke City and August 2001. The runner summary reports
`success=true`, `phase_reached=return_from_line_up`, `crash_detected=false`,
and `wine_debugger_detected=false`.

Two earlier route attempts selected Bury and Queens Park Rangers because the
old carrier coordinates do not describe the post-rename 12-by-2 selector.
They are diagnostic artifacts only. The accepted Stoke coordinate is division
`562,302`, team `332,350`. Future automation must discover or derive the
post-build selector position rather than reuse the pre-build carrier cell.

## Kit evidence and credit

Historical Football Kits provides the dated English kit evidence and is
credited as “Copyright Historical Football Kits and reproduced by kind
permission.” Source graphics remain only in the ignored hash cache; the game
contains independent PM99-scale renders. Oxford United's missing HFK interval
uses the explicit source-cited override in
`data/season-kit-overrides-v1/2001-02.json`, cross-checked against Football Kit
Archive and Wikimedia Commons. Stoke's 2001–03 evidence now classifies as
red/white vertical stripes with white shorts.

## Reproduction chain

The final immutable inputs and outputs are:

1. Opening correction manifest:
   `data/season-opening-overrides-v1/2001-02.json`.
2. Kit correction manifest: `data/season-kit-overrides-v1/2001-02.json`.
3. English compiler input:
   `.local/season-english-authoring-v1/2001-02/r8/english-compiler-input.json`.
4. Strict worldwide package:
   `.local/season-worldwide-merged-v1/2001-02/r4/strict-season-package.json`.
5. Static ingress:
   `.local/season-static-ingress-v1/2001-02-worldwide-source-backed-r4/`.
6. Kit archive stage:
   `.local/season-kit-archives-v1/2001-02/source-backed-r2/`.
7. Calendar executable: `.local/calendar-v1/2001-02/MANAGPRE.EXE`.
8. Playtest tree:
   `.local/season-runtime-candidates-v1/2001-02/worldwide-source-backed-r2/game`.

## Remaining editorial work

The 31 rows marked `editorial_review_required=true` in the duplicate audit are
the primary queue. Missing nationality, weight, shirt number or portrait are
logged secondary gaps and are not build blockers under the agreed policy.
Portrait fallback is `native-no-photo`. This candidate must not be promoted to
historically final until the ownership queue is reviewed, but it is ready for
user playtesting now.
