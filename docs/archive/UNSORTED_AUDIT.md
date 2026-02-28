# Archive Cleanup Summary

This file records the intent behind the archive cleanup.

What was removed:
- AI-generated handover bundles that duplicated or contradicted the code
- Archived bugfix writeups that no longer influenced the current implementation
- Duplicate roadmaps and status snapshots
- Legacy wrapper notes for tools that no longer exist in the active tree

What was kept:
- `README.md` as the archive entry point
- `TEAM_FIELD_STRUCTURE_GUESS.md` as the largest surviving technical note
- `verify.txt` as raw XOR validation evidence
- `breadcrumbs.csv` as a compact binary-analysis breadcrumb set

Current rule:
- If a legacy note is not uniquely useful, delete it instead of keeping another pointer document.
- If maintained docs and archived notes disagree, prefer `docs/` and `app/`.
