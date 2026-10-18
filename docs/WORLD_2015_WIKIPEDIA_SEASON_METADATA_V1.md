# World 2015 dated club metadata evidence

`capture_2015_world_wikipedia_season_metadata.py` obtains 2015–16 club-season
infobox evidence from the MediaWiki API. Every accepted row records page ID,
revision ID, revision timestamp and SHA-256 of the exact wikitext used. The
receipt is source-only and never writes a PM99 file.

Page discovery is not identity resolution. A page must declare season 2015–16
and its infobox club must equal the FootballSquads strict key or one of the
small fixed set of presentation-only title forms (such as `FC Barcelona`).
Search rank, text similarity and inferred aliases are not accepted. Multiple
valid pages remain a review status.

The merge first consumes the reviewed Transfermarkt/FootballSquads receipt:
175 unique carrier references (93 strict, 82 explicit country-scoped
overrides). Its dated opening-fixture manager/stadium facts take precedence
over Wikipedia. This closes 98 previously unlinked carrier metadata lanes,
leaving 127 explicit `2015-manager-source-required` rows in the 302-carrier
candidate. Selector conflicts stay in the receipt; none occurred in this run.

The Wikipedia 302 receipt has six exact season-page matches, all with manager
and stadium text, but no season-scoped capacity. Stadium evidence is recorded
only as dated evidence, never as a permanent-ground or capacity assertion.
Thus all 302 `2015-club-ground-and-capacity-source-required` blockers remain.
The same capture supports the later integrated 317-source-ready draft; its
receipt keeps the 317 input hash and reports six exact matches.

Player facts are now scoped correctly: the base 302 candidate has 143 absent
physical values (703 in the integrated 317 candidate), each using a
deterministic competition/position median with per-field provenance. Missing
shirt numbers are preserve-only, and only six missing-DOB players (four
carriers) form the named source-or-editorial-fallback review queue. The 17
FIFA same-name candidates are retained as non-matching ratings provenance and
receive deterministic editorial ratings; FootballSquads club/DOB/nationality
continues to establish their roster identities.

The integrated 317-carrier candidate additionally consumes the 30-row
mode-1 recycle allocation. Each target slot receives its
`new_foreign_player_carrier_id`; the corresponding mode-0 source keeps an
appended clone. The builder asserts 6,819 final player IDs are unique before
any later portrait/package stage, and rejects an integrated receipt unless its
allocation count is exactly 30. This includes carrier 3101 slot 0 (Daniel
Bocanegra: old 8770 -> foreign 7223; mode-0 clone 33219). Its enriched receipt has 98 reconciled
Transfermarkt metadata attachments, six Wikipedia page receipts, and 142
explicit dated-manager source gaps. No PM99 binary is written.

Foreign mode-1 membership and opening grid are preserve-existing constraints,
not package blockers. The package eligibility report still names genuine
manager ENT, dated-manager, ground/capacity, kit, portrait and missing-DOB
content/schema gaps.
