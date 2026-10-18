# PM99 compact player tactical-role writer — 2026-08-30

## Question

Can the six compact (`dd6360`) role bytes be changed for a historical player
without making the player unsafe in the live game?

## Static contract

The runner's `GhidraMCP` project establishes the compact loader and evaluator:

- `FUN_004afd80` consumes two native compact strings, a control byte, exactly
  six role bytes, a second control byte, then the visible metadata.
- `FUN_004b13f0` reads all six decoded role values at player offsets
  `+0x1d..+0x22` when calculating tactics suitability. It accepts role codes
  `0..17`; native zero denotes an unused slot in the database.

The position shown beside `ROL.` is therefore derived by PM99. It is not a
stored primary-role field and must not be described as one by the editor or a
season package.

## Live mutation

Kanu (JUG `20957`) was selected because he is an existing compact player that
the runner can identify by name after starting a clean game with Arsenal.

Only decoded payload offsets `39..44` (the six role candidates) changed:

| Version | Decoded candidates | In-game result |
| --- | --- | --- |
| Original | `2, 8, 12, 98, 98, 98` | Kanu profile opens; `ROL.` shows Centre Forward. |
| Mutation | `0, 1, 2, 3, 4, 5` | Clean new game boots; Kanu profile opens by exact name; `ROL.` shows Right Back. |

The file-level receipt is
`.local/research-probes/dd6360-role-set-kanu-20260830/receipt.json`. It shows
that no other byte of `JUG98030.FDI` changed. The live proof is
`.local/research-probes/dd6360-kanu-role-set-cycle-ui-20260830/summary.json`;
it recorded `success: true`, exact Kanu profile capture, six role-menu cycle
captures, and no native error modal. The visible mutated profile is
`screens/37_profile_open_27.png`.

## Released write rule

1. Parse the two compact native strings.
2. Preserve the following control byte.
3. Write exactly six role slots: an active candidate `r` as `(r + 1) ^ 0x61`,
   and an unused slot as `0 ^ 0x61`.
4. Preserve the second control byte and every other payload byte.
5. Reject any requested code outside `0..17`, any legacy outlier in the input
   role window, or more than six candidates.

The compiler and browser editor now use this rule. A full season release still
has to run the normal package audit and runtime sweep; this result closes the
field-level layout/write uncertainty rather than claiming every historical
role assignment is correct.
