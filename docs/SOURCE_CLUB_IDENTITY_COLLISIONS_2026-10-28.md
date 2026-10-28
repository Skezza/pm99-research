# Reject colliding provider club identities

Opening-lineup capture now rejects results when distinct club selectors resolve
to the same Transfermarkt numeric club ID. Both conflicting selectors remain
explicit failures for review; neither is silently certified or reassigned.

This prevents a unique substring match from mapping Olympiakos to Olympiakos
Volos and then borrowing the latter's squad or manager. Explicit identity aliases
remain the existing correction mechanism. Provider numeric identity is global,
so the check also covers selectors from different countries or competitions.

The guard does not rewrite existing recipes or historical capture evidence.
A read-only replay against the retained 25 standard season captures found the
2010/11 Olympiakos/Volos collision. The original legacy 2015 capture is a separate
workflow and was not included. Existing player data for the affected club needs
its own identity assessment; this check alone does not certify that roster.

Validation: 23 opening-lineup and person-evidence tests passed, including rejection
of two distinct selectors sharing one provider ID and acceptance of distinct IDs.
