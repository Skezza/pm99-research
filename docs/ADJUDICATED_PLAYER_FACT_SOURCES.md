# Correcting known player facts

The existing source-backed field writer can correct a known wrong birthday or
country without changing ownership, ratings, tactics or artwork. Historical
identity must first match the retained source row and numeric provider in its
dated fixture. An old native birthday is a checked preimage, not identity proof.
An explicitly unknown recipe birthday additionally requires the measured old
native birthday in the request before a source-backed correction is prepared.

`season_adjudicated_player_facts_v1.py` keeps its existing `official_sources`
route and its legacy plan-policy value. The additional `independent_sources`
route admits birthdays only: an explicitly classified official club or
association biography plus a named reference on another host. Both original
bodies, capture receipts, complete subject headings, identity context and full
day/month/year must agree. Reference publications are labelled as references,
not official sources. Publisher classification is a reviewed input; it is not
inferred from agreement between models.

Official Premier League player responses can be JSON rather than server-rendered
HTML. `season_premier_league_profile_facts_v1.py` reads the exact public SDP
player endpoint, requires its numeric player ID and full display name, and
checks every returned career record for the same precise birthday and country.
Unknown countries, malformed nested fields, duplicate JSON properties,
conflicting records and alternate origins are rejected. These sources retain
their original JSON representation; the HTML text-label checks are unchanged.

These additions change source admission only. The common native writer,
explicit field masks, source hashes, unchanged-data checks and SOURCE rebuild
remain mandatory. A source-ready request or passing parser test is not an
installed game correction.


An additional typed source pair handles a null-DOB annual player row using an
explicit DIF player-profile card and an original dated match programme mirrored
by DIF Historia. The profile's single subject card must publish DOB and an
explicit supported nationality; birthplace is not substituted. The programme
must bind its filename date to its printed match date, identify the selected
club/opponent, and contain one exact named position/DOB block in its layout
column. Body hashes, original capture receipts and reproducible PDF extraction
remain required. A context DOB conflicting with the adjudicated DOB is rejected.

The retained 2002 case uses DIF's profile and the Shamrock Rovers *Hoops Scene*
programme for 15 August 2002, archived by DIF Historia. Archive hosting is not
a claim that DIF published that programme. Sources remain local; the repository
tracks adapters and tests, not the PDF or game binaries.
