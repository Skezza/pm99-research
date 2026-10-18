"""Replay the August26 original XI and four positively dated reserves.

This source-only package retains published surnames and unproved identity
bridges; acquiring a biography does not prove an ambiguous fixture actor.
"""
import copy
import hashlib
import re

from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_published_person_identity_v1 as people
from scripts import season_published_transfer_history_v1 as histories
from scripts import season_historical_transfer_review_v1 as transfer
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts import season_august_source_fallback_v1 as fallback

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/stock-club-history-v1'
URL='https://www.partizanopedia.rs/0102.html'
LINE=("Mladost Apatin: Žakula, Đurković, Opsenica (46' Savić), Lilić, Višković, "
      "Desnica, Davidov, Krišanović (46' Petković), Belić, Mešter, Ćirić (65' Trifunac) Trener: Dragi Bogić")
XI=['Žakula','Đurković','Opsenica','Lilić','Višković','Desnica','Davidov','Krišanović','Belić','Mešter','Ćirić']
USED=[dict(published_match_name='Savić',minute=46),dict(published_match_name='Petković',minute=46),
      dict(published_match_name='Trifunac',minute=65)]
RESERVES=[19723,538007,46859,41792]
ACTOR_POLICY='original-Mladost2001-published-surname-unresolved-identity-v1'
UNRESOLVED={2,3,6,7,9,10,12,13}


def unresolved_actor(index):
    if type(index) is not int or index not in UNRESOLVED:
        raise ValueError('unreviewed Mladost surname actor index')
    path,raw,binding=source_rows('partizanopedia-2001-original-season')
    receipt=pipeline.read_json_file(path.with_suffix('.source.json'))
    actual=parse_match(raw,url=receipt['url'])
    label=(actual['starting_xi']+actual['used_substitutes'])[index]['published_match_name']
    claim=fallback.surname(published_surname=label,provider='original-Partizanopedia',
        club=actual['club'],fixture_date=actual['fixture_date'],source_binding=binding)
    claim.update(policy=ACTOR_POLICY,match_person_index=index)
    key='fixture-actor:'+hashlib.sha256(pipeline.canonical_json_bytes(claim)).hexdigest()[:24]
    return dict(source_player_id=key,source_provider='original-fixture',name=label,
        given_name=None,family_name=label,birth_date=None,identity_policy=fallback.SCHEMA,
        identity_evidence=claim,original_fixture_bindings=[binding])


def verify_actor(person):
    expected=unresolved_actor(person.get('identity_evidence',{}).get('match_person_index'))
    if person!=expected:raise ValueError('Mladost actor changes published surname, original fixture or missing biography')
    return 'person-original-fixture-'+expected['source_player_id'].split(':')[1]


def parse_match(raw,*,url=URL):
    if url!=URL or not isinstance(raw,bytes) or not 500<=len(raw)<=2*1024**2:
        raise ValueError('original Mladost source URL or size differs')
    page=BeautifulSoup(raw,'html.parser')
    headings=[h for h in page.select('h3') if h.get_text(' ',strip=True)=='Mladost Apatin - Partizan 1:3 (1:1)']
    if len(headings)!=1:raise ValueError('Mladost August fixture missing or ambiguous')
    lines=[]
    for row in headings[0].find_all_next(['h3','p']):
        if row.name=='h3':break
        lines.append(re.sub(r'\s+',' ',row.get_text(' ',strip=True)))
    if len(lines)<2 or lines[0]!='26. avgust 2001. Gledalaca: 7 000' or lines[1]!=LINE:
        raise ValueError('original Mladost fixture date, XI, substitutes or manager changed')
    return dict(season='2001-02',fixture_date='2001-08-26',club='Mladost Apatin',
        manager='Dragi Bogić',first_league_xi=False,round=2,formation=None,
        starting_xi=[dict(published_match_name=n,full_identity=None) for n in XI],
        used_substitutes=copy.deepcopy(USED),unused_substitutes=None,
        limitations=['August26 is a later-August round2 sample, not the first league XI.',
            'Published surname identity bridges and precise positions require review.',
            'Four reserves are positive club intervals, NOT an invented unused match bench.'])


def prepare(output):
    if output.exists():raise ValueError('Mladost source review is immutable')
    path,raw,binding=source_rows('partizanopedia-2001-original-season')
    receipt=pipeline.read_json_file(path.with_suffix('.source.json'))
    actual=parse_match(raw,url=receipt['url'])
    docs=[ROOT/f'mladost-2001-{stem}-v1.json' for stem in [
        'original-person-candidates','additional-original-person-candidates','third-original-person-candidates']]
    history_paths=[ROOT/f'mladost-2001-{stem}-v1.json' for stem in [
        'original-candidate-histories','additional-original-histories','third-original-histories']]
    persons={};events={}
    for doc in docs:
        data=pipeline.read_json_file(doc);people.merge({},data)
        for batch in data['batches']:
            for person in batch['people']:persons[person['source_player_id']]=person
    for doc in history_paths:events,_=histories.merge(events,pipeline.read_json_file(doc))
    reserves=[]
    for id in RESERVES:
        interval=transfer.transfer_interval(events.get(id,[]),actual['fixture_date'])
        if interval.get('status')!='recorded-entry-and-exit-bracket-fixture' or interval['source_owner_club_id']!=904:
            raise ValueError('reserve lacks positively dated August Mladost ownership')
        reserves.append(dict(source_person=persons[id],opening_interval=interval,
            membership='positive-original-dated-August-reserve-not-published-match-bench'))
    return_value=dict(schema_version='pm99-original-mladost2001-August-XI-and-four-positive-reserves-source-review-v1',
        original_opening=actual,positive_reserves=reserves,source_people_count=18,
        original_bindings=[binding]+[dict(path=registry.relative_workspace_path(p),sha256=registry.sha256_file(p))
            for p in docs+history_paths],
        rejected_reserve_candidates=[dict(source_player_id=id,interval=transfer.transfer_interval(rows,actual['fixture_date']))
            for id,rows in events.items() if id not in RESERVES
            and transfer.transfer_interval(rows,actual['fixture_date']).get('source_owner_club_id')!=904],
        identity_gaps=['Ćirić cannot be assigned automatically to Marjan or Veljko Ciric from the all-time catalogue.',
            'Unresolved full fixture identities must retain literal published surnames and explicit unknown birthdays.',
            'Exact fine roles/physical facts/nationalities/ground/kit remain unapproved.'],
        native_writes=0,closed_duplicate_cases=0,publication_authorised=False,
        next_step='Join safe original identities or typed surname actors, fixed18 allocation, native build/source replay/runner/checkpoint.')
    pipeline.write_canonical_json(output,return_value)
    return return_value


if __name__=='__main__':
    result=prepare(ROOT/'mladost-2001-original-August26-source-review-v1.json')
    print(dict(people=result['source_people_count'],positive_reserves=len(result['positive_reserves']),native_writes=0),flush=True)
