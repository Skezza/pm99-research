# Source-bound opening membership corrections

The opt-in `source-bound-opening-fixture-membership-plan` recipe artifact moves
existing players into their source-proven opening squads. It does not exchange
their identities or invent substitute players to balance roster counts.

The admission provider reparses retained Transfermarkt match bodies, selects the
club by provider ID, and joins each published player ID to a hash-bound annual
full name/date-of-birth row and the native player. Position-group tables retain
their published names. Formation grids reuse the original capture parser and
retain published surnames where that is all the report provides; they do not
expand initials or invent given names. The published formation and the exact
eleven provider IDs/names must also match the bound season fixture capture.
Grid rows do not acquire a claimed published broad position from their pitch
coordinates. Sources must use
an HTTPS Transfermarkt report URL with the exact match ID. Ambiguous joins,
changed source hashes and wrong parent releases are rejected.

Both the main recipe and its English overlay are updated. The native writer
supports only parsed mode-0 rosters with zero flags, unique positive player IDs,
16–25 members and a contiguous terminal count-and-rows table. It preserves the
payload prefix and every unselected roster payload. Removing a donor starter
requires a separate correction; this provider rejects that operation.

The compiler reconstructs the complete proposed recipes, roster membership,
opening order and contextual tactics from the immutable registered parent and
the retained sources. It rejects a different native postimage before writing
the clean game tree. Legacy packages without the artifact retain their existing
receipt fields and follow the same compilation path.

The bounded publisher uses the same source admission. The binder emits required
artifact metadata in canonical order and validates the complete resulting recipe
before publication. A process-local composition cache rehashes every parent and
source input before reuse, returns independent copies, and is cleared before the
SOURCE reconstruction. It never substitutes a candidate's output for its parent.

This is a mechanism, not a release approval. Corrected games still need an
independent SOURCE replay, unchanged-data checks and relevant runtime evidence.
In particular, the Rob Lee/Robert Lee duplicate must be resolved separately;
moving David James into the sourced West Ham XI does not close that duplicate.

During lead review, the private proposal failed because visibility replay used
the updated recipe before constructing it. Replay now follows construction of
both recipe layers. The original failed log is retained alongside the passing
20-test private review. Canonical regression results and release deliveries
are recorded in `CURRENT_WORK.md` and the release checklist.
