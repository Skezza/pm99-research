# Correcting an inherited birthday without trusting it as identity

A captured annual squad can name a player and position without giving a birthday.
The old native birthday then describes the donor slot, not necessarily the new
player. The explicit `annual-source-row-person-identity-null-dob-v1` policy
admits a correction without treating that inherited date as evidence.

This opt-in path requires the exact annual row and selector, one full-name match
within the source club, the selected recipe person and native owner, and an exact
native preimage. The annual source birthday must be null; conflicting published
dates do not qualify. The source club must uniquely match the selected package
club. An official playing-career clause must identify the same person and club
and cover the target year strictly inside its stated year range. Boundary years
and ambiguous prose require additional evidence.

The supported providers are named DFB player profiles and UEFA technical reports,
corroborated by a UEFA playing-career article. Birth date and nationality must
belong to the same named profile/card, with two independent official publishers.
The PDF and its raw text extraction are retained and hashed; extraction must
reproduce those exact bytes. Tool versions are QA provenance, not semantic inputs.
Birthplace is not nationality. Existing identity policies remain unchanged.

The source policy changes birthday/country only through the existing masked
native writer. A separate, verified facts-parent role projection may replace an
incompatible inherited forward role with the existing editorial defender default.
That default is not presented as a published historical fine position. Parent
replay caches rehash source bindings and reject symlink substitution before reuse.

The real Fischer parent also exposed an inconsistent factory slot: Jerren Nixon
has broad position M with primary fine role 15 (Right Forward). The verified
null-birthday defender path can correct that retained seed without requiring
the factory's own broad/fine pair to be compatible. Exact seed bytes, different
identity, changed broad position, corrected birthday, exclusive ownership and
the official defender evidence remain required. The earlier midfield policy
keeps its original factory-compatibility requirement.

The first case is Urs Fischer at Zürich in 2000/01. DFB gives his birthday and
Swiss nationality; UEFA corroborates those facts and his Zürich playing spell.
Sources are credited in the retained receipts and here:
[DFB player profile](https://datencenter.dfb.de/personen/urs-fischer/spieler),
[UEFA career article](https://www.uefa.com/uefaeuropaleague/news/01f5-0e79738121cc-333257df258a-1000--zurich-out-to-end-portuguese-hoodoo-against-sporting/),
[UEFA technical report](https://www.uefa.com/MultimediaFiles/Download/uefaorg/General/02/40/05/26/2400526_DOWNLOAD.pdf).

Evidence: `.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/fischer-2000-inherited-native-facts-v1/`.
Adversarial tests cover borrowed subjects, other clubs and coaches' dates,
same-table fact borrowing, unapproved publishers, namesakes, native ownership,
byte masks and replay-cache substitution. Game delivery still requires SOURCE
rebuild equality and an original runner screenshot; source tests alone do not
establish delivery.
