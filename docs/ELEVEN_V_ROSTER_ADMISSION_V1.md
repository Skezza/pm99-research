# Dated 11v11 and FootballSquads roster admissions

The existing opening-identity exchange can admit a new reserve from a retained
11v11 biography/career table and an independently captured FootballSquads season
row. The exact profile URL, provider ID, full name, birthday, nationality,
career interval and capture receipt are checked. The destination club and
season must match, and the career interval must intersect that season's August.
This establishes roster membership, not a match appearance or opening XI claim.

FootballSquads rows may be in “Past Players”. The adapter reparses that exact
row separately because the older canonical roster reader omits that section.
The broader source file is still checked by the existing source verifier.
Its two-digit birthday corroborates day, month and year suffix; the complete
year and explicit nationality come from 11v11. No nationality column or
independent century is invented. Annual height/weight literals use the existing
unit converters; unavailable or unsupported literals remain recorded gaps.
Published shirt numbers stay in evidence while this writer preserves the
destination shirt byte; that is a deliberate boundary, not absent source data.

Fine roles are explicitly compatible editorial projections where the sources
publish only broad positions. Ratings use the existing deterministic model.
Provider IDs use `11v11:<id>` and `person-11v11-<id>`, with original admission
replayed before issuing the person ID; they are never labelled Transfermarkt.
The original fixed-carrier writer, reserve guard, unchanged-data checks and
SOURCE reconstruction remain in force. A source-ready plan is not a delivered
game correction.
