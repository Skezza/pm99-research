# Shared manager references

Some fixed-carrier clubs share one ENT manager actor. Renaming that actor for
one club also changes the other club. A sourced manager correction must therefore
resolve both owners before separating their references.

The existing manager-plan publication/reconstruction path now accepts one explicit
`owner_isolations` binding. It uses an existing ENT slot, checks its exact encoded
record SHA-256 and rejects any active or inactive EQ reference to that destination.
The destination must not already have a recipe actor. The source recipe and native
owner sets must agree. A sourced ordinary manager update is required for both the
new actor and the sole remaining owner; normal manager evidence guards still apply.
An unchanged remaining manager may be source-confirmed through the ordinary plan.

Only the selected existing EQ active manager link changes. Existing SDK writers
handle the link and manager name spans. The new recipe actor is sorted by ID.
Other ENT fields, unrelated EQ records, players, tactics and assets are preserved.
Plans without this optional binding retain their previous behavior.

Validation on 2026-10-28: 28 focused tests passed, two skipped; independent Luna
review caught missing remaining-owner decisions and unsorted actor insertion,
which were corrected before a real build. The 2025/26 prototype r506 isolates
Alavés/Coudet into existing slot1829 and corrects the remaining Universidad
Católica/Garnero actor1190, alongside Nantes/Castro1413. Actual native readback
confirms the three sole owners. Independent SOURCE reconstruction matches the
complete game and recipe. Runtime validation and publication remain separate
requirements; this document does not claim that prototype is installed.

Private evidence: `.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/manager-owner-isolation-qa-v1/`.
