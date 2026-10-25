# Source-backed opening-squad profile crosswalk

`season_opening_profile_crosswalk_admission_v3` is an explicit opt-in source
family for the existing identity-exchange pipeline. The request supplies the
person IDs, facts, season, club and retained evidence; the provider contains
no player or season-specific exceptions.

It joins an official Premier League profile, Sky's named birthday/position
profile, an explicitly labelled nationality reference, and the numeric person
in the club's first league match. Original HTTP bodies and indexed web-tool
extracts have distinct receipt types. A used substitute proves appearance and
membership, not a complete bench or starting XI. Full-name, DOB, country, club,
fixture and source hashes must agree; birthplace is not nationality evidence.

The existing native writer, deterministic editorial ratings and no-photo
policy remain responsible for the resulting records. An editorial fine role
is labelled as editorial. Missing height, weight and shirt number remain
declared gaps, rather than invented facts.

The build/replay entry points accept an explicit reviewed `minimum_free_bytes`;
the default remains 8 GiB and values below 6 GiB are rejected. Both publication
and SOURCE replay receive the same reserve. Completed releases are not rebuilt
to change this setting.

Source credits: Premier League, Sky Sports, Wikipedia and Transfermarkt.
Evidence stays in local source packages; proprietary game files are not tracked.

Portable synthetic tests run without local captures. Separate optional corpus
checks and a real canonical prepare/verify/bind/apply test are required for a
particular correction before publication.
