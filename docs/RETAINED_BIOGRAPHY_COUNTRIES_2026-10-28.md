# Retained reader biographies for narrow nationality corrections

`season_retained_reader_country_v1.py` admits explicit 11v11 biography facts
retained through Jina Reader when direct origin access refuses the request.
Credit belongs to [11v11](https://www.11v11.com/) for the biography and
[Jina Reader](https://jina.ai/reader/) for the extracted transport format.

The response is explicitly recorded as **reader-extracted text, not original
HTML**. Its original canonical numeric profile URL, reader URL, response title,
full name, exact birthday and one explicit Nationality field must agree.
Birthplace, club, names and national-team appearances never supply a country.
Ambiguous, absent or unsupported values are refused. Original response bytes,
network URL/status and SHA256 receipts are retained.

The existing known-wrong-country writer authenticates these inputs, writes only
selected nationality bytes and preserves every other fact and asset. SOURCE
reconstruction uses the retained inputs; building does not re-fetch a website.
This is a biography country claim, not exclusive citizenship at an historical
instant, international eligibility or target-season club ownership.

The first real input identifies Henk Timmer, born 1971-12-03, explicitly Dutch.
Eight existing occurrences were independently read back: two wrong native flags
(2003/04 Yugoslavia, 2005/06 USA) and six already Holland. A 2003/04 paired
Duijnhoven/Timmer correction has complete A/SOURCE-B equality and changes exactly
two native country bytes; it awaits actual-game profile validation/installation.
Evidence is under `.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/henk-timmer-visible-country-review-v1/` and the adjacent
`runtime-nationality-originals-20261027-v1/three-source-native-proposals-v1/2003-04/`.
