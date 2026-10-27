# Exact replay of an opening-squad correction

A release whose latest transaction replaces a wrongly assigned player can now
replay that transaction through the normal registered-season build path. It uses
the recipe's own saved ownership plan and its exact immutable parent. It does
not return to the factory database or replay an older inherited country layer.
The immutable parent and its source cache must be retained locally; this is not
a clean-machine reconstruction of the entire historical parent chain.

The replay checks the saved plan filename/hash, original source hashes, inert
parent descriptor, parent recipe/compiler/build-chain hashes and complete
expected child recipe before building. It then compares the full resulting game
inventory and recipe bytes with the release being reproduced. An edited recipe
is rejected instead of silently discarding the edit. This is an exact replay
contract, not a general compiler for arbitrary edits.

Implementation: `scripts/season_opening_ownership_reconstruction_v1.py`, selected
by `scripts/build_registered_quality_release_v1.py` only when the current compiler
receipt names the generic opening-ownership transaction. Other transaction modes
continue to their existing handlers. Publication, preferred-season changes and
historical approval remain separate actions.

Validation: eight focused tests cover exact replay, edited recipe/plan/descriptor,
changed parent provenance, mismatching output and precedence over inherited
layers. The two older manager/Italian reconstruction test files have 14 failures
both with this dispatcher enabled and with it explicitly disabled (30 pass in
the latter baseline run); these are not reported as passing. Baseline evidence:
`.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/ownership-SOURCE-existing-reconstruction-tests-baseline-v1.log`.
The real two-player Parma/AZ A/B replay also passed: the complete recipe and game
inventory match. Evidence: `.local/consolidated-audit-20261009/parallel-rc-20261023/
resume-qa/frozen-crossclub-current-native-triage-20261027-v1/
combined-parma-az-after-swiss-r446-v1/build-A-SOURCE-B-proof-v1.json`.
That proves exact reconstruction; the candidate still needs its own runtime
review and installation before counting either historical correction delivered.
