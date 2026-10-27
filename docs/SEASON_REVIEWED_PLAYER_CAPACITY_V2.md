# Reviewed player name-capacity recovery v2

The v1 reviewed-country adapter remains unchanged because earlier SOURCE receipts
bind its file hash. Its selected-player route did not apply `name_capacity`,
although its whole-club route did. A longer published surname could therefore
pass authoring recovery but correctly fail native publication.

`season_authored_country_delta_v2.py` has its own schema and compilation mode.
It applies the existing, independently proved same-carrier factory-window
recovery before compiling selected players. It retains v1's closed recipe mask,
exclusive ownership checks, native writer, explicit recovery claims and SOURCE
reproduction checks. No name truncation or generic record growth is permitted.
The publisher and SOURCE dispatcher select v2 only for its explicit schema;
all existing v1 transactions continue through v1. Factory compilation continues
to reject the shared reviewed-transaction artifact prefix.

Tests cover absent recovery, exact selected-slot recovery, unchanged unrelated
records, repeatability and rejection of wrong scope, duplicate claims, forged
pre/postimage hashes, forged proofs and changed factory bindings. The actual
2020 Colón/Gimnasia transaction additionally requires exactly two changed native
player records, unchanged other records and orders, and full SOURCE equality
before runner validation or promotion. Its historical scope is those two
ownership corrections, not certification of both entire squads.
