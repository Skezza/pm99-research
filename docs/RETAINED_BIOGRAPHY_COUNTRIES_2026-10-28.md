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
two native country bytes. It was installed and verified with genuine profiles
at checkpoint 229; the corresponding 2005/06 correction passed at checkpoint 232.
Evidence is under `.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/henk-timmer-visible-country-review-v1/` and the adjacent
`runtime-nationality-originals-20261027-v1/three-source-native-proposals-v1/2003-04/`.

## Original HTML is a separate source format

The `11v11-original-profile-country-v1` provider reads the original HTML when
the reader response omits biography fields. It requires the numeric profile URL
and the page's own `og:url` to match, exactly one matching heading and title,
one biography block, an exact birthday and one explicit supported nationality.
Duplicate identity or fact fields are refused. A reader body cannot masquerade
as original HTML. Both paths use the same existing one-byte nationality writer.

The first original-HTML case is Simon Brown, born 1976-12-03, explicitly English
on profile 4443. His reader response lacks the required facts and remains
inadmissible. The original HTTP 200 HTML and its receipt are retained unchanged;
Coludata independently corroborates the identity and English nationality.
Soccerbase's conflicting birthday is not substituted for the selected birthday.

A read-only census of all 26 preferred releases found nine exact Brown
occurrences. Six already show England and require no change. The 2004/05,
2005/06 and 2006/07 native records show France, Scotland and France respectively.
Three nationality-only plans are prepared, not yet delivered. The 2004/05
Hibernian club/manager candidate is held until its country correction is composed
and verified. Evidence and hash-bound census:
`.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/simon-brown-known-country-luna-v1/`.
