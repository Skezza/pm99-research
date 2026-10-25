# Stock kit identity correction, 25 October 2026

The frozen 327-case kit queue contained a name collision: Portuguese Nacional
was matched to the original game's Nacional Montevideo. The original donor
has the Centenario ground and Uruguayan players; it is a different club.
The audit found 14 affected cases: one installed in 2002/03 and 13 not installed.
The original baseline remains 58 installed and 269 pending. An installed case
requiring correction is not silently counted as a new pending case.

Evidence is in
`.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/stock-identity-collision-audit-v1/country-family-audit-v1.json`.
The 13 unpublished mappings are withheld; the installed 2002/03 case still
needs correction. They need a Portuguese Nacional design, rather than another
club's asset justified by a matching short name. The remaining
country-family screen is not exhaustive historical kit certification.

`apply_stock_kit_seed_remap_v1.py` now checks the sealed donor's country family
against the live target club before preparing or materialising a patch.
Unknown families fail closed. The two explicit same-club exceptions are bounded
by donor carrier, target country, and published club-name variants:

- Vaduz, donor 1805, into Switzerland. The Liechtenstein federation documents
  participation in the Swiss competition and identifies the Rheinpark ground.
  [LFV 2013/14 information](https://www.lfv.li/fileadmin/user_upload/Dateien/Medien/Downloads/Fussball_in_Liechtenstein/Fussball_in_Liechtenstein_2013-2014.pdf).
- Colwyn Bay, donor 3331, into Wales. The club describes its English-pyramid
  years, its Llanelian Road ground, and its return to Welsh competition in
  2019/20. [Official club history](https://cbfc.wales/club-details/club-history/).

The 2003/04 request was reduced from 24 to 23 mappings, preserving the original
request and recording the excluded Nacional case. Building and installing that
subset are separate milestones. No historical kit-design claim is added.

Validation: 21 tests passed across the stock-remap and new country-identity
tests. Coverage includes the actual Nacional country collision, both legitimate
competition exceptions, an exception applied to the wrong club/country, and an
unknown country. Native data, portraits, ratings and tactics are outside this
change.
