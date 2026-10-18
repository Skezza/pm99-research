# Lead assessment of the independent Sonnet audit

Source: `CLAUDE_SONNET_5_5_ADVERSARIAL_REVIEW_2026-10-17.md` and original
`.local/consolidated-audit-20261009/claude-sonnet-5-5-adversarial-review-20261017.json`.
Claude Code completed successfully, exact canonical `claude-sonnet-5-5`,
133 turns, 748535 ms, reported cost USD 3.4506174, no permission denials.
Read-only code/document audit: no tests/builds/runner/hash verification performed
by the reviewer. Its findings are not a new release attestation.

## Findings independently confirmed by the lead

- `git ls-files` returns none of CURRENT_WORK.md, pm99-season,
  scripts/pm99_simple_season_v1.py, scripts/season_package_v2.py,
  scripts/season_owned_club_composition_v1.py and
  data/preferred-season-releases-v1.json. `git status` marks all six untracked.
  This is a real source-control/recovery and clean-checkout problem. Other
  backups were not audited; do not assert there is only one surviving copy.
- The preview explicitly emits release_eligible=false, zero opening lineups,
  native manager fallbacks and an unauthored English-leagues gap. It is not an
  end-to-end unseen-season release generator. The CLI routes preview and the
  registered-release build through different scripts.
- canonical_player in capture_transfermarkt_historical_squads_v1.py does not
  retain provider player IDs in its normalized output.
- _person_candidate_key in season_package_v2.py returns None when DOB is not a
  string. That conservative guard cannot establish duplicate-free identities
  for those rows; a separate reported unknown-identity lane is needed.
- The v116 checklist has 48 cross_club_dispositions and 2761 remaining
  candidates. Those counts do not measure how many confirmed defects remain.

## Claims or recommendations not accepted without qualification

- F7's 34/42/48 discrepancy is not demonstrated: the reviewer counted status
  strings recursively rather than parsing the authoritative array. Direct jq
  inspection confirms its cross_club_dispositions length is 48. Embedded
  evidence may repeat statuses. Do not introduce a counting bug based on F7.
- A read-only audit cannot certify that replay/runtime claims fail, nor prove
  them correct. It inspected their code, not execution or screenshots.
- Do not silently remove non-playable/foreign historical identity or ownership
  defects from scope. The owner's product is worldwide. Any scope reduction
  requires an explicit decision, not the reviewer's preferred release bar.
- Do not abandon the generator after an arbitrary two failed criteria. A
  source-coverage failure and a software failure require different responses.
- Do not rebuild all 26 merely because the reviewer recommends it. The existing
  instruction prohibits regenerating unaffected releases. Reuse bound evidence
  and use isolated reconstruction checks where a fresh test is actually needed.
- Keep binary guardrails until experiments justify changes. Evidence that some
  player appends work does not establish unrestricted club/topology capacity.
- Club-specific data is necessary; club-specific code/manual orchestration is
  the issue. A generic transaction consuming sourced data is not automatically
  a failure, but its input preparation and allocation must also be runnable.

## Proposed direction, not an implemented change

Protect/version the non-proprietary toolchain; define one bounded issue ledger
with confirmed defects separate from candidates; retain native guards; preserve
provider IDs and explicit dated ownership upstream; include identity checks in
ordinary QA; join existing intake layers into one parameterized generation
workflow. Prove it with an isolated 1990/91 acceptance run and offline replay,
with honest coverage/gaps and no manually written club-specific code. Preserve
the 26 current releases and all completed corrections throughout. Do not claim
the unseen-season milestone complete until this experiment actually passes.
