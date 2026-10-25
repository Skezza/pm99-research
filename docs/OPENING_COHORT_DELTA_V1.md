# Source-bound opening-cohort corrections

`season_opening_cohort_delta_v1.py` integrates typed roster corrections with the
existing native publisher and SOURCE builder. It uses the ordinary season
recipe, an immutable registered parent and a hash-bound source plan. It does
not download a new season or certify facts outside the selected correction.

The plan records source fixture identities, XI and bench membership, period
position rows, selected actor changes, complete native lineup order, and
explicit no-photo decisions. NFF and Transfermarkt assertions are data-driven;
club names, player names, fixture IDs and dates are not hardcoded in the provider.

Validation checks source bodies, same-person transfer preimages, recipe changes
outside the allowed fields, and every affected XI slot's native position. A
source-backed utility deployment can retain a different primary position only
with an explicit exception and a compatible native secondary role. The first
fixture uses this for Kupczak, a midfielder deployed in a defensive slot.

SOURCE constructs a new child through the existing publisher, from the pinned
parent and saved input plan. It checks the complete game inventory and exact
recipe bytes against the first child. Changed recipes fail rather than silently
discarding edits. The ordinary builder dispatches to this handler only for its
specific compiler receipt mode.

Secondary facts may be missing. A missing source value cannot justify a factual
correction. Two-digit FootballSquads birth years use the target season's century,
so `66` in a 2000 recipe means 1966, not Python's default 2066. Explicit four-digit
dates are retained for separate chronology checks.

The manager publisher also validates its explicit surname-display policy.
Declaring that policy while passing a full first-and-last name is rejected
before publication; complete published surname tokens and supported common
display names are preserved.

Verification during promotion: 20 source-row and local integration tests,
33 existing compiler tests, and 30 targeted manager-display/SOURCE tests passed.
The integration tests require the local source/native corpus and skip explicitly
when it is absent. Their mocked publisher test is not an actual game rebuild;
the real A/B build and runner evidence are recorded separately in CURRENT_WORK.

Source credits for the first correction: the Norwegian Football Federation's
match records, FootballSquads period rosters, Transfermarkt match records, and
Moss FK's official player profile. Raw bodies and capture receipts remain local;
the typed plan retains their URLs where supplied, paths and SHA-256 bindings.
