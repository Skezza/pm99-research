# World 2015 all-carrier package V2 eligibility V1

The all-302 source candidate now distinguishes three states clearly:

- `preserved_constraints`: foreign competition membership is preserved; this
  is satisfied protection, never release-blocking missing content.
- `stage_status`: the receipt is a source/package candidate and has no binary
  write authorisation; this is a workflow label, not content debt.
- `blockers`: only missing source, asset or identity decisions remain.

The candidate’s per-player compiler graph consumes the allocation-specific
recycle receipt. It declares 6,510 mode-1 core in-place rows and 29 mode-1
recycle edges; all requested recycle primary roles are runtime-qualified. The
seven absent dated duplicate slots are outside the selected 302-carrier scope,
so they are not misreported as a binary-contract failure here.

Run the V2 eligibility audit after candidate generation:

```bash
python3 scripts/audit_2015_world_candidate_package_v2.py \
  --candidate .local/season-pipeline-v2/world-2015-all-302-source-carrier-package-candidate-20260831.json \
  --output .local/season-pipeline-v2/world-2015-all-302-package-v2-eligibility-20260831.json
```

No canonical `pm99-season-package-v2` is emitted yet, because the candidate
cannot meet its structural cross-reference contract. The eligibility receipt
lists the exact gaps: division evidence and manager-ENT mapping for 302
clubs; all-carrier opening XI/formation/tactics grids; 225 absent fixture
metadata rows; 17 ambiguous player identities; and required kit, portrait and
permanent-ground/capacity evidence. This leaves the V2 schema boundary honest
without turning the preserved-membership guardrail or source-only stage label
into fake release blockers.
