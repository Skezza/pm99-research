"""Adjudicate a retained country fallback and disclose conflicting DOB sources."""
from bs4 import BeautifulSoup
from scripts import prepare_morecambe_owned_opening_20261017 as source
from scripts import capture_stock_replacement_sources_20261010 as cache
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def original(key):
    path=cache.ROOT/(key+'.html');receipt=cache.ROOT/(key+'.source.json')
    metadata=source.pipeline.read_json_file(receipt)
    if metadata['status']!='original-captured' or source.registry.sha256_file(path)!=metadata['sha256']:
        raise ValueError('Takano publisher original changed or was not captured')
    return path.read_bytes(),dict(source.bind(path),url=metadata['url'],receipt=source.bind(receipt))


def parse_news(raw):
    page=BeautifulSoup(raw,'lxml')
    dates=[t.get_text(' ',strip=True) for t in page.select('time')]
    text=page.get_text(' ',strip=True)
    exact=('Keisuke Takano (Japan) The student made history in 1997 when he became the first Japanese to score in the FA Cup. '
        'His goal, for Morecambe, came in a 3-3 first-round replay against Emley, who won on penalties.')
    if not any('07 November 2006' in d for d in dates) or exact not in text:
        raise ValueError('original article exact footballer/club/Japanese-1997 event is absent')
    return dict(full_name='Keisuke Takano',nationality='JPN',historical_event_year=1997,
        article_year=2006,not_a_2000_national_team_caps_claim=True)


def parse_legacy(raw):
    page=BeautifulSoup(raw,'lxml')
    matches=[tr for tr in page.select('tr') if 'Keisuke "Kenny" Takano' in tr.get_text(' ',strip=True)]
    if len(matches)!=1:
        raise ValueError('one original official legacy Takano row required')
    values=[c.get_text(' ',strip=True) for c in matches[0].find_all(['th','td'],recursive=False)]
    if not all(v in values for v in ('30-Sep-78','19-Feb-00','22-Apr-00')):
        raise ValueError('legacy explicit birthday and same Southport career dates differ')
    return dict(published_birthday='1978-09-30',row=values,
        birthplace_not_used_as_citizenship_evidence=True)


def main():
    output=source.ROOT/'takano-country-and-birthday-source-choice-v1.json'
    if output.exists():raise ValueError('existing Takano source adjudication must not be overwritten')
    doc=source.pipeline.read_json_file(source.ROOT/'original-opening-equivalence.json')
    actual=doc['actual'];reviews=source.pipeline.read_json_file(source.ROOT/'provider-identity-and-bench-role-review-v2.json')
    review=next(r for r in reviews['resolutions'] if r['name']=='Kenny Takano')
    actors=[r['soccerbase_person'] for group in actual['identity_bridges'].values() for r in group]
    actor=next(a for a in actors if a['source_player_id']==review['source_provider_person_id'])
    resolved=source.birthdays.resolve(review,actor,actual)
    official=BeautifulSoup(source.birthdays.publisher_original(review['external_biography']),'lxml')
    text=official.get_text(' ',strip=True)
    if 'Real name Keisuke Takano' not in text or 'Born 30/09/1976 Japan' not in text:
        raise ValueError('exact numerical official profile no longer bridges Kenny to Keisuke/1976')
    news,news_binding=original('takano-original-independent-2006-nationality')
    legacy,legacy_binding=original('takano-official-southport-legacy-row-validated')
    if news_binding['url']!='https://www.the-independent.com/sport/football/news/fa-cup-countdown-maradona-of-basingstoke-423354.html':
        raise ValueError('another article cannot be substituted')
    if legacy_binding['url']!='https://southportfc.net/player-list/':
        raise ValueError('another aggregate list cannot be substituted')
    country=parse_news(news);conflict=parse_legacy(legacy)
    retained(output,dict(season='2000-01',carrier_id=10992,name='Kenny Takano',
        source_provider_person_id=actor['source_player_id'],official_identity_resolution=resolved,
        nationality=country,nationality_original=news_binding,legacy_birthday=conflict,legacy_original=legacy_binding,
        adopted_birth_date='1976-09-30',birth_date_confidence='disputed-between-detailed-official-profile-and-aggregate-official-list',
        birth_date_choice='Retain the detailed numeric profile date used in the source-bound roster repair; aggregate1978 alternative explicitly retained, not consensus or a proven exact birthday. Optional secondary uncertainty, not a guessed correction.',
        nationality_choice='Replace inherited England fallback with explicit Japanese affiliation tied to the1997 Morecambe FA Cup event, before the target season; birthplace alone is not the authority. No England affiliation has been sourced.',
        country_fix_still_to_deliver=True,native_writes=0,frozen_case_dispositions_changed=0))
    print(dict(country_source_choice='JPN',birthday='detailed1976-versus-aggregate1978-disputed',native_writes=0),flush=True)


if __name__=='__main__':main()
