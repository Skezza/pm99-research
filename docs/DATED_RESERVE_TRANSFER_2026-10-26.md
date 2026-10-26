# Source-bound dated reserve transfers

`scripts/season_source_bound_reserve_transfer_v1.py` moves an existing, uniquely
owned mode-0 reserve between two existing clubs. Requests supply the season,
player and provider IDs, native club carriers, an August date, immutable parent
hashes and retained original-source paths/hashes. It contains no hard-coded
player or season. QPR is explicitly mapped to Queens Park Rangers for the Sky
publisher abbreviation; other non-structural aliases are not inferred.

Admission reparses the publisher's completed transfer history and requires
positive entry and exit around the August date, an unambiguous latest transfer,
the published full-name slug, and an independent Sky profile full name, birth
date and dated source/destination transfer row. The independent announcement may
precede the effective transfer date by up to seven days; both must precede the
August anchor. A missing source, wrong identity, changed hash, contradictory
owner or same-day ambiguity refuses the transaction. Transfermarkt's published
history service and Sky Sports are credited as the original evidence providers.

The implementation uses the existing checked mode-0 roster writer and native
startup-order writer. It keeps both main and English authoring recipes aligned,
removes the moved player from the old bench, and appends him as a destination
reserve. Both native first XIs, every player fact and skill, all tactics,
managers and image assets are preserved. Roster limits are 16–25. An existing
starter cannot move through this path. This is ownership evidence, not proof
that the player appeared in an opening match or that every secondary fact is
historically correct.

The common delta publisher writes an uninstalled candidate. SOURCE reconstruction
reparses the original request and source bodies, rebuilds from the immutable
parent, and compares the entire recipe and game inventory. Factory compilation
must refuse this layer instead of silently dropping it. Promotion still needs
native scope/readback, playable validation and relevant genuine runner evidence.

The first request is Daniel Nardiello, 2007/08: Barnsley carrier331 to QPR339,
player9834. Sources bracket QPR ownership from 1 July2007 to24 January2008;
Sky independently reports the27 June2007 transfer announcement and DOB22/10/1982.
These sources do not approve a shirt-number change, rating change or new portrait.
