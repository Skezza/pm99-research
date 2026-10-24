# Squad-row biographies with dated membership

The existing opening-identity exchange can read a retained detailed squad row
instead of requiring a separate player-profile page. This establishes the
person's full name, numeric provider ID, literal DOB, position and nationality.
It does not establish opening ownership: an independently dated registration
contract or the existing original first-league report/bench guards must pass.
The first league fixture may be outside August; the schedule and report must
prove it is the target season's first fixture.

Birth dates need a separately hosted corroborating witness. The existing
Soccerbase named-biography route remains supported. The additional
`wikidata-exact-provider-name-day-birthday-v1` witness reparses a hash-bound
original entity JSON, requiring the exact entity URL/QID, full published name,
one nondeprecated P2446 matching the squad's numeric Transfermarkt ID, and one
precise Gregorian day in P569. It rejects conflicting, approximate or malformed
dates. A separately hosted record is not necessarily an independent underlying
research source; original FIGC and local-news biographies also corroborate the
reviewed Vicenza examples.

Explicit `N/A` height remains unknown. It is not zero or a verified measurement.
Native slot fallbacks stay declared rather than becoming sourced person facts.
Current-club and joined-date columns in retrospective squad pages are not used
to prove historical ownership.

When a full name will not fit the existing native record, a source-bound P734
family-name claim can identify the complete published family component. The
family entity's original URL/hash and literal label must match, along with the
same person's provider ID, full name and precise birthday. The source full name
remains in the recipe. This does not split names by spaces, truncate surnames,
or expand native record windows.

Vicenza's reviewed provider-ID-scoped label aliases cover `Vicenza Calcio` and
`LR Vicenza` for provider 2655 and native `Vicenza`. They do not apply to another
club ID or authorize renaming the game club.

Implementation: `scripts/season_transfermarkt_squad_biography_v1.py`, composed
with the existing `scripts/season_opening_identity_exchange_v1.py` reader,
compiler and SOURCE replay. No new database writer or fixture-extraction
exception is introduced.
