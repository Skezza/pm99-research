# Historical squad import guards

`capture_transfermarkt_historical_squads_v1.py` checks structured outer table
rows even when the legacy parser returns a nonempty result. A partial result
is not proof of a complete squad. Every literal player ID in those rows must
be emitted or capture fails explicitly. Structured role cells and country
flags take priority over free text; stronger legacy secondary facts are kept
only for the same provider identity.

Different provider IDs remain distinct even when names match. An unidentified
namesake remains a separate unresolved row, and conflicting repeated IDs fail
instead of silently overwriting facts. An unrecognized nationality stays an
explicit gap. The source code IMN is retained for Isle of Man; the native game
has no matching country, so the existing unsupported-country fallback is XXX.

Opening-lineup preallocation uses an original profile URL and matching numeric
ID before name reconciliation. A contradictory URL/ID fails. An absent exact
ID cannot be inferred from an unidentified same-name row. Bare numeric IDs
without a provider profile URL do not disambiguate namesakes.

A first-fixture lineup establishes membership on that fixture date, not at a
later August snapshot. In calendar-year leagues, retain that lineup as a
dated reference and resolve later transfers before allocating August squads.
Likewise, filtering an annual squad is insufficient when profile additions
can restore an excluded person: final combined rows must be checked against
unchanged clubs and existing verified identities before publication.

These guards prevent mechanical losses and unsafe identity joins. They do
not certify every historical fact or establish that a private candidate has
been installed in a playable release.
