# Luna release-research first-batch review

2026-10-18, Vostro `joe-Vostro-3350`, source session
`01a0592d-fcd5-7262-a637-743a8253d9b4`.

Two read-only `gpt-6-luna` workers were assigned independent bounded batches.
Neither may edit shared recipes, build, publish or run the game. The lead owns
integration and serial runtime validation. Findings below are research review,
not evidence that any playable release changed.

## Reviewed first batches

### Stoke 2013/14

Worker `/root/luna_stoke_opening_review` inspected the three already-known
late arrivals and six-person ownership graph. Lead checked the cached original
BBC Arnautovic article's body and 2 September 2013 timestamp against the report.
The existing report retains hashes for the other dated transfer bodies.

- Carriers9266 Odemwingie,9267 Arnautovic,9273 Guidetti are currently at Stoke,
  but their Stoke arrivals are after the August17 opener (September2,
  September2 and January14 respectively).
- Proposed opening owners: West Brom, Werder Bremen, Manchester City. These
  follow dated transfer chronology, not direct opening-day registration sheets.
- Jones1865 is currently at Cardiff, but is a sourced Stoke opening substitute.
  Restoring him requires a coupled ownership correction, not a new duplicate.
- Pennant and Jerome are sourced opening substitutes without matching current
  native identities in the reviewed graph. That is not proof that fixed carriers
  can be created or that arbitrary other players may be removed.
- No frozen2013 case IDs were found for these named findings. Do not reuse the
  unrelated2015 Odemwingie duplicate case or change the2809 denominator.

Inputs: `.local/consolidated-audit-20261009/luna-closeout-20261017/`
`stoke-2013-opening-three-review-v2.md`,
`stoke-six-player-opening-ownership-graph.json`, `stoke-source-cache-v2/`;
original opener `.local/transfermarkt-opening-plans-current-v1/2013-14/cache/report/2350359.html`.

Disposition: chronology finding accepted; global correction transaction NOT
approved until recipient rosters and capacity are reconciled. Second bounded
batch assigned to current West Brom/Werder/City/Cardiff admission constraints,
not another transfer-date recheck.

Second-batch lead review: worker found current recipe counts WBA25, City25,
Cardiff25, Werder22. The lead independently loaded the preferred2013 release
and parsed actual `EQ98030.FDI` roster rows:301/307/314/320 are mode0 with25
rows each,403 is mode1 with22 rows. This confirms existing capacities, not
permission to grow/shrink them. The worker's suggestion that22-to23 Werder has
"no observed capacity collision" was rejected: absent JSON max fields do not
waive native constraints. Underfilled Stoke23/Cardiff24 are not complete fixed
roster repairs either. Worker redirected to source-positive Werder actor-swap
options rather than presumed append/delete operations.

Additional reported late arrivals Anichebe/Amalfitano at WBA and Demichelis at
City are research leads, NOT approved deletions. Their current owners before
arrival and all coupled slots must be reconciled. No new confirmed-bug count
is added merely from the worker's URL list; original sources require review.

### Aldershot 2018/19

Worker `/root/luna_aldershot_reserve_review` checked McCoy, Mannion and Fowler.
Lead independently inspected official July2/August9 article bodies and matched
their SHA256 values to the prior v3 adjudication; also inspected the exact
Soccerbase91175/100491 profile birthday text.

- McCoy11052: official July2 signing supports August reserve membership, not a
  claim that he was in the August4 XI/bench or a precise birthday.
- Mannion11051: official August9 loan supports the agreed August reserve pool,
  NOT first-matchday membership. Soccerbase91175 says1998-05-05; worker reports
  the existing target carrier birthday1998-04-01. No birthday mutation approved
  solely on this comparison. Existing composition request proposes transferring
  another source carrier11315 into11051; that exact donor must be distinguished
  from retaining11051's old birthday before assessing the actual final result.
- Fowler11041: exact opener links the person to Soccerbase100491, whose birthday
  is1997-12-20; existing native date1997-11-20 remains disputed. Preserve identity
  and label the birthday conflict rather than guessing or removing him.

Six previously listed affected frozen IDs remain unresolved:

```
a7802d4595a2d617e08e493900846c4f36c8e5257547f6cfed0c5599a6ca437c
aba8fcb6ce6738207ea23368f01f17a2f80cd973302acd607f141306cc6bd840
3a6f0910a37ab26128b60301f6eba1c55397ebd6f9cb0df9cceb4395d1a23390
c3484bdbddb7a22a42a999b2e59a6869660b89036ec4d4ab5df013401a6be422
c1a9fc7c67f76fd2399013ae807ff9a99aa44a7053ffca1712891920a242abe2
7ea916b81f83219a52203f8127140e4fe69a19c695bc0b0db6cf936682688ca1
```

These are the worker's referenced affected IDs, not six new dispositions.
Input v3 adjudication and original official bodies live in the same local
`luna-closeout-20261017/` directory; exact linked profile HTML lives under
`.local/season-2018-19/soccerbase-august-cache-v1/player/`.

Second bounded batch sought primary DOB corroboration. Official Aldershot
announcements support identities and ages but do not distinguish either pair
of birthdays; no correction approved from age alone. Missing primary evidence
does not prove an existing birthday correct. Unavailable secondary facts remain
distinct from required roster/ownership fixes.

## Integration boundary

No actual game, recipe or registration was changed by these reviews. No case
closure, fresh runtime verification or historical-correctness percentage is
claimed. First-batch review preceded further delegation. Lead meanwhile
inspected editor amendment materialisation and retained-club composition code:
the former does not auto-promote releases; the latter remains explicitly an
in-memory preflight, not a publisher. These are integration work, not reasons
to repeat completed native-mechanics research.

## Lead safe work while research ran: known runner fixture failure

Reproduced the prior failing
`test_stoke_season_profile_capture_restores_scroll_after_each_return`.
Its classifier stub supplied a screen label but no OCR. Production correctly
requires nonempty profile OCR, so the old test incorrectly expected two captures
from an invalid first profile. No production guard was relaxed or changed.

Updated the upstream fixture with valid allowed-probe OCR and explicit first/
second blank-OCR rejection plus second wrong-screen-with-OCR rejection. A third
requested profile proves an invalid second capture stops the loop. Exact action
labels forbid Return/scroll/third selection after that invalid capture.

Commands (from research root, existing local test environment):

```
.local/venvs/season-pipeline/bin/python -m pytest -q upstream/pm99-runner/tests/test_pm99_runner_scripts.py -k stoke_season_profile_capture_restores_scroll_after_each_return
.local/venvs/season-pipeline/bin/python -m pytest -q upstream/pm99-runner/tests/test_pm99_runner_scripts.py
```

Final results:4 focused PASS;205 full-file PASS,1 SKIP,23.16s. Luna independently
reviewed the final diff and found the stop/restore assertions correct. This is
unit-test maintenance, not a genuine game capture or proof of player identity.
Upstream source commit `3a072b6`, snapshot branch. Existing deleted fixture
assets were not restored, staged or included in that commit.

## Continued bounded reviews — 2026-10-18 14:43 UTC

Vostro/session as CURRENT_WORK. Two Luna workers remain research/QA only;
lead owns native changes and serial runtime. Generic opening ownership exchange
and adult-height-only masks passed independent adversarial review. Approved
Transfermarkt HTTPS request/canonical origins are now required, with spoof tests.
90 focused publisher/source/label/recipe tests PASS,2 SKIP. SOURCE equality is
incremental exact-parent reconstruction, not a clean-machine factory claim.

The current2000/01 audit was refreshed against r148a, not replayed from oldr17.
Only1252/1258 still need Scottish cohort labels: Celtic/Kilmarnock. Grounds
already Celtic Park/Rugby Park and stay fixed. Original July29 report3838375
names Williamson; Celtic July30 report3838377 has no parsed coach. Lead checked
the retained original Celtic plc June1,2000 RNS announcement naming O'Neill.
Private r152a therefore corrects two labels and two exclusively owned coach
names, native aliases O'Neill/Williamson. Actual readback and complete SOURCE
replay PASS; no player, ground or kit bytes change. Runtime not yet approved.
Evidence `.local/consolidated-audit-20261009/Scotland2000-label-manager-v1/`.
Generic planner's unrelated unchanged coach rows were deliberately omitted
after verifying their before==after; their parent evidence is preserved.

These label corrections DO NOT certify every roster member. Luna identified
Canero19260 wrong-club and Lennon19261/Douglas19262 late-arrival candidates.
Lead independently checked the October19,2000 Douglas signing report; other
claims still require original-source admission before correction. Bonnes22055
was already Celtic in1999 and must not be rejected merely absent the opener.
IMPORTANT rejected worker suggestion: McGovern joined Celtic in2001, NOT a
verified August2000 keeper replacement. Do not admit that season-table inference.
Riseth may be a source-positive August midfielder; verify exact identity/owner.

Gary Holt frozen case0543df1f3f24c24c94e197f586ef328cb872295d77e5b5367d3432fcdd305013
remains open. Kilmarnock12209 should retain him; Norwich9962 arrival was March2001.
Worker proposes actual August12 Norwich substitute Raimond de Waard as the
capacity-fitting replacement, citing 11v11 match833/profile4029. No admission,
game change or case closure for this proposal yet. Next independent source/cache
and native reserve/ownership verification precedes any correction.
