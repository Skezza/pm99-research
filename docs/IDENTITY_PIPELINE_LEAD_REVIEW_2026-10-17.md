# Identity pipeline implementation: lead review

UTC: 2026-10-17 19:41. Machine: joe-Vostro-3350.
Source session: 01a0592d-fcd5-7262-a637-743a8253d9b4.

## Delivered source changes

Claude Sonnet 5.5 implemented the bounded identity batch, followed by lead
review and additional corrections. Optional source_identity holds a provider
namespace and literal player ID. The historical parser and DOM fallback retain
it; composition, normalization, intake and draft building carry it into V2
players. Ordinary season QA now reports provider-ID collisions, conflicting
metadata, fallback name/DOB candidates and incomplete identity coverage. Missing
optional IDs do not newly invalidate old recipes. Existing strict name/DOB
guards remain intact. No players are automatically removed or reassigned.

Lead compared the actual files to the pre-worker scripts/schemas archive. The
worker stayed within the source allowlist. Original Sonnet JSONL and brief are
retained; exact-model execution succeeded in 76 turns / 811722 ms, reported
USD 3.3338532, no permission denials.

## Problems found and corrected during review

1. Profile extraction accepted numeric prefixes in malformed paths and arbitrary
   absolute hosts. It now checks URL components, explicit supported provider
   hosts and numeric path-segment boundaries.
2. Explicit source_identity=null was treated as absent by the reusable audit
   and composition. It now reports malformed metadata; ordinary QA blocks it.
3. Profiled opening additions dropped IDs. They now carry an identity when the
   literal Transfermarkt profile URL agrees with the declared source ID;
   disagreement is rejected. An unrelated URL plus a number does not establish
   the provider. Reconciled original intake rows already retain their facts.
4. Identified annual and opening rows previously used different candidate keys.
   Their explicit provider identity now takes precedence, so the same sourced
   identity does not acquire two keys simply by taking a different lane.

Added 17 lead adversarial tests. Source code changed beyond the worker batch:
scripts/materialise_opening_squad_preallocation_v1.py plus hardening in the
identity helper and builder. Details in SONNET_IDENTITY_IMPLEMENTATION_2026-10-17.md.

## Independent verification actually run

- Initial existing targeted tests: 74 passed.
- Final targeted suite including lead negative tests and opening materialiser:
  139 passed in 9.34 s.
- Broader related regression: 363 passed, 1 deselected in 34.73 s.
  The deselected test is test_season_roster_visibility_v1.py::
  test_flag_only_delta_is_not_skipped_and_preserves_all_other_files. Sonnet's
  broader run reached its real 8 GiB disk-reserve guard; the volume is now
  approximately 7.6 GiB free. This is not a passing test or a waived production
  guard. No production disk checks were weakened. One unrelated marker warning
  occurs because an upstream fixture module is imported from the research suite.
- Real cached source test: 154 historical 1990 squad pages / eight competition
  directories, 3718 player rows, all 3718 retain provider IDs, no parser errors.
  Every page was parsed twice and canonical outputs matched. Summary and
  aggregate source/output fingerprint:
  .local/consolidated-audit-20261009/identity-1990-offline-replay-20261017.json.
  This is parser replay, not a complete recipe build or runtime validation.
- Repository boundary and git diff --check passed.
- Preferred catalogue hash unchanged:
  5f68223af26ecef7a5cd4a22cc0f75a8f0fcd21e332670fa03e0dfabf91e6abe.
- Retained catalogue hash unchanged:
  cd942c5a46bcd6623be8c500c2ef5d3eed96800d97c5c2c2e1ddd96e2af16393.

## Limits and next work

This is an implemented and tested upstream data-quality improvement, not a
retroactive correction of the 26 games or completion of the generator. No game,
recipe, release registration or runner was modified. Existing games have not
magically acquired provider IDs. Strict same-name/DOB candidates still require
review even if distinct provider IDs exist; this batch does not weaken that
guard. Only Transfermarkt is currently registered in the new identity schema;
legacy namespaced opening IDs from other providers retain their old behavior.

Source-control/clean-checkout protection and joining the generator stages remain
open. Next use the preserved-ID chain for a bounded source/recipe acceptance
experiment and integrate dated ownership before native allocation. Do not claim
that identity screening alone proves historical accuracy, or that a parser-only
1990 replay proves a runnable full-season generation command. Resolve disk headroom
before any actual build requiring the 8 GiB reserve. Preserve the v116 games and
the in-memory 2018 ownership work, which remain separate pending delivery.
