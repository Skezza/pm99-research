# PM99 season objective inputs — 10 September 2026

## Finding

The pre-season club objective is driven by the squad-rating profile, not the
club finance field.  The first post-1999 recipe policy gave every club in an
English division the same base strength.  That collapsed the game's objective
input and produced a Premier League screen made entirely of `Mid Table`.

This was a recipe-model defect.  It was not a variable-length-string, kit, or
database-carrier defect.

## Controlled runner evidence

All three tests used a disposable 2014/15 Stoke copy and the same observed
Stoke selector coordinates (`division 559,224`; `team 302,360`).

| Test | Change | Result |
| --- | --- | --- |
| Baseline | Current 2014/15 candidate | All 20 Premier League clubs were `Mid Table`. |
| Finance A/B | Stoke cash only, £20m to £200m; exactly four declared bytes changed | Stoke remained `Mid Table`. |
| Rating A/B | Stoke's 11 opening-XI mapped visible rating fields only, fixed-size JUG trailers | Stoke became `Champion`; the other 19 clubs remained `Mid Table`. |

The corresponding runner captures are retained below.  The first two rule out
finance as the causal input; the third isolates squad ratings as the causal
input.

- Baseline: `upstream/pm99-runner/docs/artifacts/pm99_runner/objective_ab_2014_15_stoke_baseline_20260910/screens/033_championships_continue_retry.png`
- Finance A/B: `upstream/pm99-runner/docs/artifacts/pm99_runner/objective_ab_2014_15_stoke_200m_bytemin_20260910/screens/031_championships_continue_retry.png`
- Rating A/B: `upstream/pm99-runner/docs/artifacts/pm99_runner/objective_ab_2014_15_stoke_xi99_20260910/screens/030_championships_continue_retry.png`

The finance probe remains a copy-only diagnostic script at
`scripts/patch_mode0_finance_probe_v1.py`.  It is deliberately not part of
the production repair.

## Production repair

`scripts/capture_english_preseason_standings_v1.py` captures the four completed
English tables from the season immediately before the target season.  Each
source CSV is retained under
`.local/season-english-preseason-standings-v1/cache/` and every canonical
standing document retains the original Football-Data URL and raw SHA-256.

`scripts/materialise_english_rating_layer_v1.py` now consumes that document.
It maps the completed prior finish to a deterministic strength in the club's
current division:

- established clubs taper from their prior finish;
- relegated clubs start as strong contenders in their new lower division;
- promoted clubs start below established sides in their new higher division;
- clubs entering from outside the four English divisions are explicit,
low-strength newcomers rather than silent mid-table fallbacks.

The policy is one reusable rule, not a manual Manchester City exception.  For
2014/15 it assigns Manchester City (2013/14 champions) strength 90, Chelsea
(third) 86, Stoke (ninth) 76, and the promoted Leicester, Burnley and QPR
67.  Outfield handling remains constrained to goalkeeper-appropriate values
by the existing editorial-rating model.

The 2019/20 League One and League Two source records record the real
curtailed-table exception explicitly and rank by points per game.  This avoids
pretending that an incomplete result feed is a normal full fixture list.

## Cascade record

`scripts/cascade_english_preseason_rating_policy_v2.py` materialised this
policy for all 25 playable post-1999 season presets.  Its immutable receipt is
at:

`.local/season-english-preseason-rating-policy-v4/cascade-receipt.json`

It covers 2,300 English clubs and 57,434 player rating rows.  The unmatched
names recorded in the receipt are the real promoted entrants from outside the
previous four English divisions (two per modern season, with the historical
early-2000 exceptions retained), not unresolved normalisation collisions.

`scripts/promote_post1999_worldwide_v1.py` now requires the standing document
and passes it into the rating layer, so the next ingress revision cannot
reintroduce division-flat ratings by omission.

`scripts/pm99_season_qa_v1.py` now also blocks a complete English division
whose opening-XI mean Quality spread is below eight points.  Against 2014/15,
the old recipe fails all four English divisions (the Premier League span was
only 1.91); the repaired recipe has zero such failures.  This is a cheap
recipe-level guard before a runner capture, while the runner remains the
release proof of the game's actual objective screen.

## 2014/15 release proof

The isolated rebuilt recipe is under
`.local/objective-ratings-policy-v2/2014-15/`.  It passed the English authoring
gate, strict package preparation, and clean static ingress.  The runner then
selected Stoke using the recorded coordinates and reached a `Start Of Season`
screen with 0.99 classifier confidence:

`upstream/pm99-runner/docs/artifacts/pm99_runner/objective_policy_2014_15_prior_table_v2_20260910/screens/031_championships_continue_retry.png`

The screen shows Manchester City as `Champion`, the promoted Burnley,
Leicester and QPR as `Avoid Relegation`, and Stoke as `PM Euro Trophy`, rather
than the former all-`Mid Table` result.  This is proof that the repair changes
the real PM99 objective calculation.  It is not yet a claim that every
individual target label is the final editorial judgement; that remains a
separate calibration/review queue.

The normal selectable 2014/15 candidate has now been promoted as source-backed
`r2`.  A bounded follow-up corrected Rotherham's two mis-positioned opening-XI
records (and nothing else); its receipt is
`.local/season-direct-opening-lineup-position-repairs-v1/2014-15-r2.json`.
The final r2 runtime was then run again, successfully reaching the same
start-of-season objective screen at 0.99 classifier confidence:

`upstream/pm99-runner/docs/artifacts/pm99_runner/objective_policy_2014_15_r2_final_20260910/screens/031_championships_continue_retry.png`

`./pm99-season validate 2014-15` passes against r2's static-ingress receipt.
The prior r1 candidate remains on disk; the preferred selector now uses r2.
