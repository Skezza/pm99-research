"""Reparse the positive Haladas opening keeper and frozen Kiraly copy pair.

Source decision only: it does not authorize a reserve-policy starter bypass,
claim the whole Haladas roster is historical, or count a native fix delivered.
"""
from bs4 import BeautifulSoup
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_within_club_reserve_repair_v1 as native
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_opening_order_repair_v1 as ownership
from scripts.build_original_carrier_label_20261017 import external
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/haladas2000-opening-keeper-20261017'


def page(key,url):
    binding=external(key)
    receipt=pipeline.read_json_file(registry.ROOT/binding['source_receipt_path'])
    if binding['url']!=url or receipt.get('sha256')!=binding['sha256']:
        raise ValueError('original keeper source URL/content receipt differs')
    return BeautifulSoup((registry.ROOT/binding['path']).read_bytes(),'html.parser'),binding


def decision(base):
    if base.season!='2000-01':raise ValueError('this original first fixture only covers2000')
    match,match_binding=page('haladas2000-original-opening-archive','https://tempofradi.hu/2000-vii-22-ferencvaros-haladas-4-0')
    text=' '.join(match.get_text(' ',strip=True).split())
    title=' '.join(match.title.get_text(' ',strip=True).split())
    prefix='Haladás: Kurucsai – Seper, Kaj (Németh 90.), Tóth P., Simon – Bodor, Somfalvi, Juhász, Nagy G. – Győri (Varga 68.), Halmosi (Sipos 73.)'
    if ('2000.VII.22. Ferencváros – Haladás: 4-0' not in title
            or 'Labdarúgó NB I., alapszakasz, 1. forduló, A-csoport:' not in text
            or text.count(prefix)!=1 or '2016. március 24.' not in text):
        raise ValueError('original first-round report/date/literal first keeper not unique')
    bio,bio_binding=page('haladas2000-index2001-secondary-player-facts','https://index.hu/sport/futball/mfcsapatok/2001/10/10/haladas/')
    bio_text=' '.join(bio.get_text(' ',strip=True).split())
    if 'Kapusok Kurucsai Kornél 1972.01.18 185/78' not in bio_text:
        raise ValueError('original secondary keeper exact name/date/height/weight absent')
    country,country_binding=page('kurucsai-original-stadler1996-country-row-validated','https://www.transfermarkt.com/stadler-fc/startseite/verein/26269/saison_id/1996')
    rows=[r for r in country.select('table.items > tbody > tr') if r.find('a',href='/kornel-kurucsai/profil/spieler/670636')]
    if (len(rows)!=1 or rows[0].find('a',href='/kornel-kurucsai/profil/spieler/670636').get_text(' ',strip=True)!='Kornél Kurucsai'
            or '18/01/1972' not in rows[0].get_text(' ',strip=True)
            or 'Goalkeeper' not in rows[0].get_text(' ',strip=True)
            or not rows[0].find('img',attrs={'title':'Hungary','alt':'Hungary'})):
        raise ValueError('original explicit keeper full-name/date/nationality row differs')
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    pkg=pipeline.read_json_file(base.package_path);actors={p['carrier_id']:p for p in pkg['players']}
    clubs={c['id']:c for c in pkg['clubs']};owners=ownership.native_owners(eq)
    facts={carrier:native.native_facts(jug,carrier) for carrier in (2211,8507)}
    for carrier,club in ((2211,421),(8507,1706)):
        actor=actors[carrier]
        if (actor.get('source_name')!='Gabor Király' or actor['facts']['birth_date']!='1976-04-01'
                or facts[carrier]['birth_date']!='1976-04-01' or facts[carrier]['position']!='G'
                or roster.normalise(actor['name'])!=roster.normalise(facts[carrier]['name'])
                or clubs[actor['club_id']]['carrier_id']!=club or owners.get(carrier)!={club}):
            raise ValueError('actual Kiraly source name/native birthday/keeper/exclusive owner differs')
    if facts[8507]['startup_order']!=1:raise ValueError('confirmed displaced slot is not opening keeper1')
    captures,_=roster.load_sources(base.season)
    hertha=[c for c in captures if c['club_name']=='Hertha Berlin' and any(
        roster.normalise(p['name'])=='gaborkiraly' and p.get('birth_date')=='1976-04-01' for p in c['players'])]
    if len(hertha)!=1:raise ValueError('one original exact retained Hertha annual person required')
    annual=roster.SourceVerifier(base.season).verify(hertha[0])
    if annual['status']!='raw-source-reparsed':raise ValueError('original Hertha annual not reparsed')
    frozen_path=registry.ROOT/'.local/consolidated-audit-20261009/cross-club-identities-enriched.json'
    frozen=pipeline.read_json_file(frozen_path)
    case=next(c for s in frozen['seasons'] if s['season']==base.season for c in s['candidates'] if c['identity']==['published-person',342])
    if {p['carrier_id'] for p in case['players']}!={2211,8507}:raise ValueError('frozen source pair changed')
    return dict(season=base.season,release_id=base.release_id,manifest_sha256=base.manifest_sha256,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),
        eq_sha256=registry.sha256_file(base.game_path/'DBDAT/EQ98030.FDI'),
        frozen_case=case,frozen_case_id=pipeline.canonical_json_sha256(dict(season=base.season,case=case)),
        originals=dict(opening=match_binding,secondary_biography=bio_binding,explicit_country=country_binding),
        original_fixture=dict(date='2000-07-22',round=1,phase='NB I qualification preliminary Group A',
            home='Ferencváros',away='Haladás',literal_opening_lineup=prefix,
            publication_kind='archive site administrator 2016 transcription of historical report; not claimed contemporaneous raw newspaper'),
        replacement=dict(published_full_name='Kornél Kurucsai',published_hungarian_name='Kurucsai Kornél',
            source_player_id=670636,birth_date='1972-01-18',nationality='HUN',position='G',height_cm=185,weight_kg=78,
            opening_membership_source='2000 first-round literal goalkeeper, not2001 annual or1996 country page',
            source_id_policy='literal original Transfermarkt numeric person670636; not a Soccerbase or local invented numeric identity'),
        retained=dict(carrier_id=2211,club='Hertha Berlin',annual=annual,native=facts[2211]),
        displaced=dict(carrier_id=8507,club='Szombathelyi Haladás',native=facts[8507]),
        full_Haladas_opening_XI_or_capacity_squad_approved=False,
        full_Hertha_XI_or_startup_order_approved=False,
        outstanding_scope='Haladas other players include future-year cohort; Hertha retained keeper startup7 is not certified by this identity proof. New typed opening-keeper repair required; reserve-only policy must continue refusing starter1.',
        native_writes=0,delivered=False,frozen_cases_closed=0)


if __name__=='__main__':
    path=ROOT/'positive-opening-keeper-and-frozen-pair.json'
    if path.exists():raise ValueError('completed positive source decision must not be regenerated')
    result=decision(registry.load_preferred_release('2000-01'));ROOT.mkdir(parents=True,exist_ok=True)
    retained(path,result);print(dict(opening_keeper='Kornél Kurucsai',nationality='HUN',native_writes=0,delivered=False),flush=True)
