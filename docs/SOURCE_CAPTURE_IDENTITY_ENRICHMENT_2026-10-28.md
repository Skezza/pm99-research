# Preserve old source captures when parsers add identity metadata

The Transfermarkt squad parser now emits a stable `source_identity` alongside
its original player facts. Old frozen captures predate that metadata. Comparing
the two complete dictionaries incorrectly reported `raw-capture-disagrees` even
when every original name, birthday, nationality, role and other fact agreed.

`captured_players_match` permits only this one enrichment, only on the existing
Transfermarkt branch, and only when the old row has no identity metadata. The
new value must contain exactly the Transfermarkt provider and a positive numeric
player-ID string. Player count/order, all original fields and existing identity
metadata remain strict. It does not normalise or discard factual differences.
Original capture files are never rewritten, and the public verification proof
shape is unchanged.

The real AZ 2000/01 capture contains 27 unchanged player rows. Independent raw
reparsing confirmed that added IDs were the only difference. It now verifies
without changing its capture or raw HTML bytes. This is a machinery repair,
not historical case closure or permission to certify rosters, ownership or
opening lineups. Adversarial tests reject factual changes, wrong existing IDs,
invalid added metadata and roster-size changes.

Evidence: `.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/source-capture-additive-identity-compatibility-v1.json`.
