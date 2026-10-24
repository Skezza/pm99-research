# Source-cohort club-label corrections

A retained source squad can identify a wrongly labelled club even when its
original opening XI is incomplete. The explicit full-cohort route in
`season_historical_club_label_full_cohort_optin_v2.py` admits that identity
proof through the existing review, plan and publisher. It does not certify an
opening lineup or create a new native database writer.

The default opening-XI route remains unchanged. The optional review argument
`--full-cohort-witness` selects a hash-bound candidate document. Documents may
contain several seasons; only the requested season's entries are considered,
and duplicate entries for that season are rejected.

Admission requires every current target actor to match its exact source person
ID, source row, available DOB and preallocation proof. The source selector must
be unique and in the same country. Every selected actor must have one active
native EQ owner at that carrier. Competing complete source cohorts are rejected.
A separate, distinct carrier must anchor the old label's source identity.
Provider IDs alone do not adjudicate historical aliases; the caller must review
that the proposed identities are distinct clubs.

The coach is a separate claim. Retained dated source bytes must contain the
named coach and target club, and the native manager record must be exclusively
owned. These text checks accompany source review; they do not infer a tenure
from arbitrary mentions. Existing coach-name and final club-name collision
checks remain blocking. A collision must be resolved with evidence for the
other affected coach, not by weakening the guard or swapping manager IDs.

The planner and publisher reverify the witness against its immutable registered
parent. Reconstruction does not depend on that parent remaining preferred.
Changes still pass the existing guarded EQ/ENT writers. Players, roster order,
ratings, tactics, grounds, kits and photos are outside this correction's scope.
A successful identity witness is not a claim of complete historical accuracy.

Validation:

```sh
PYTHONPATH=.:upstream/pm99-skezmod-db-editor \
  .local/venvs/season-pipeline/bin/python -m pytest \
  scripts/test_season_historical_club_label_review_v1.py \
  scripts/test_season_historical_club_label_plan_v1.py \
  scripts/test_season_historical_club_label_full_cohort_optin_v2.py -q
```

Portable guards use synthetic inputs. The retained-corpus integration test skips
when its local source parents are absent; invalid existing evidence fails.
