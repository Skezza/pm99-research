"""Acquire the dated Madinda/Celta witness without approving a native swap."""
from bs4 import BeautifulSoup
import re

from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_published_transfer_history_v1 as histories
from scripts import capture_source_bound_people_v1 as people
from scripts import season_historical_transfer_review_v1 as transfer


def capture():
    raw,binding=source.original('celta-2015-original-annual')
    page=BeautifulSoup(raw,'html.parser')
    if page.title is None or 'Celta de Vigo - Detailed squad 15/16' not in page.title.get_text():
        raise ValueError('Celta replacement source identifies another season/club')
    matches=[]
    for tr in page.select('table.items > tbody > tr'):
        ids={int(m.group(1)) for a in tr.select('a[href*="/profil/spieler/"]')
            if (m:=re.search(r'/profil/spieler/(\d+)',a.get('href','')))}
        if ids=={21297}:
            names={a.get_text(' ',strip=True) for a in tr.select('a[href*="/profil/spieler/"]') if a.get_text(' ',strip=True)}
            role=tr.select_one('td.rueckennummer')
            if names!={'Levy Madinda'} or role is None or role.get('title')!='Midfield':
                raise ValueError('original Madinda person/broad role changed')
            matches.append(tr)
    if len(matches)!=1: raise ValueError('original Celta annual lacks one stable Madinda row')
    inputs=[binding]
    cache=source.AUDIT/'celta-2015-history-originals'
    history_path=source.AUDIT/'celta-2015-madinda-original-history-v1.json'
    person_path=source.AUDIT/'celta-2015-madinda-original-person-v1.json'
    if not history_path.exists(): histories.capture_ids({21297},cache,history_path,inputs,
        'Exact original Celta15/16 stable21297 annual row. Requires completed transfer bracket at2015-08-01; annual appearance alone not ownership.')
    if not person_path.exists(): people.capture_ids([21297],cache,person_path,inputs)
    history=pipeline.read_json_file(history_path)
    if history['input_plans']!=inputs: raise ValueError('Celta original history query source changed')
    events,review=histories.merge({},history)
    bracket=transfer.transfer_interval(events.get(21297,[]),'2015-08-01')
    proposal=pipeline.read_json_file(source.AUDIT/'ofk-2015-fixed18-source-feasibility-v1.json')
    existing=proposal['outside_identity_owners']
    if len(existing)!=1 or existing[0]['source_player_id']!=291247 or existing[0]['carrier_id']!=5468 or existing[0]['club_id']!='club-48':
        raise ValueError('OFK outside ownership does not identify the known Celta slot')
    official,official_binding=source.original('celta-2015-original-drazic-announcement')
    announcement=BeautifulSoup(official,'html.parser').get_text(' ',strip=True)
    if '07-agosto-2015' not in announcement or 'Drazic' not in announcement:
        raise ValueError('Celta original announcement lacks the dated target signing')
    output=source.AUDIT/'celta-2015-opening-replacement-source-review-v1.json'
    if output.exists(): raise ValueError('Celta replacement source review is immutable')
    result=dict(season='2015-16',opening_reference_date='2015-08-01',
        source_player_id=21297,original_annual_binding=binding,
        history_binding=dict(path=registry.relative_workspace_path(history_path),sha256=registry.sha256_file(history_path)),
        person_binding=dict(path=registry.relative_workspace_path(person_path),sha256=registry.sha256_file(person_path)),
        positive_ownership_bracket=bracket,
        strict_opening_membership_confirmed=bracket.get('status')=='recorded-entry-and-exit-bracket-fixture' and bracket.get('source_owner_club_id')==940,
        original_Drazic_announcement=official_binding,
        native_slot_to_review=existing[0],native_writes=0,publication_authorised=False,
        remaining=['Confirm published Madinda biography/facts; exclusive slot/display capacity and absence of another owner.',
            'Compose/verify coupled OFK18+Celta1 without changing unselected recipe/native/game files.',
            'Opening date policy explicit: OFK first leagueJuly19 versus Celta first leagueAugust23; August1 roster anchor.',
            'Whole-game/recipe exact replay and fresh genuine actual profiles/startup.'])
    pipeline.write_canonical_json(output,result)
    return result


if __name__=='__main__':
    x=capture()
    print(dict(strict_Celta_membership=x['strict_opening_membership_confirmed'],native_writes=0),flush=True)
