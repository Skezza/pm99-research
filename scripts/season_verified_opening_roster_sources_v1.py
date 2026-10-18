"""Reusable original-fixture and positive opening-reserve source reader.

Input is retained source bindings, not club/season-specific Python decisions.
This module authorises no native write and does not approve global ownership.
"""
import copy
from datetime import date
from bs4 import BeautifulSoup
from scripts import season_source_verified_player_changes_v1 as fields
from scripts import season_soccerbase_original_opening_v1 as original
from scripts import season_original_soccerbase_reserves_v1 as reserves
from scripts import season_soccerbase_secondary_facts_v2 as countries
from scripts import capture_soccerbase_august_squads_v1 as biographies
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts.capture_2015_source_tail_squads_v1 import NATIONALITY_CODES

POLICY='original-first-league-XI-bench-plus-positive-opening-career-reserves-v1'
SOURCE_COUNTRIES={**NATIONALITY_CODES,**biographies.NATIONALITY,
                  'Tanzania':'TAN','St Kitts & Nevis':'SKN'}


def body(binding):
    path=fields.original_path(binding['path'])
    receipt=fields.pipeline.read_json_file(path.with_suffix(path.suffix+'.source.json'))
    if (fields.registry.sha256_file(path)!=binding['sha256']
            or receipt!={'url':binding['url'],'sha256':binding['sha256']}):
        raise ValueError('retained original roster source changed')
    return path.read_bytes()


def profile(binding,person_id):
    raw=body(binding)
    person=original.profile(raw,dict(provider_player_id=person_id,
        source_player_id='soccerbase:'+str(person_id)),binding['url'])
    facts=biographies.player_profile(raw,fallback_name='',fallback_position='?')
    # Exact original reader supplies identity; legacy secondary-fact parsing
    # must neither replace it nor require unrelated Date Signed text.
    facts.update(name=person['name'],birth_date=person['birth_date'])
    gaps=[]
    try:
        facts['nationality']=countries.country(raw,person_id=person_id,name=person['name'],
            birth_date=person['birth_date'],url=binding['url'],
            nationality_codes=SOURCE_COUNTRIES)['nationality']
    except ValueError as exc:
        facts['nationality']=None
        gaps.append(dict(field='nationality',reason=str(exc)))
    return person,facts,gaps


def published_alias(season,group,person,witness):
    """Later same-season labels prove display spelling, not opening ownership."""
    raw=body(group['schedule']);game_id=witness['game_id']
    rows=BeautifulSoup(raw,'lxml').select('tr#tgc'+str(game_id))
    if len(rows)!=1:raise ValueError('display witness lacks one original schedule row')
    row=rows[0];stamp=row.select_one('td.dateTime span.hide')
    if stamp is None:raise ValueError('display witness lacks original date')
    competition=row.select_one('td.tournament a')
    if competition is None or original.key(competition.get_text(' ',strip=True))!=original.key(group['competition']):
        raise ValueError('display witness is not in the source league')
    day=stamp.get_text(' ',strip=True).split()[0]
    if date.fromisoformat(day).isoformat()!=day:
        raise ValueError('display witness date is not canonical ISO')
    year=int(season[:4])
    if not f'{year}-07-01'<=day<=f'{year+1}-06-30':
        raise ValueError('display witness outside target season')
    # The match reader binds actual home/away numeric IDs to the schedule.
    from urllib.parse import urlparse,parse_qs
    sides=[]
    for side in ('homeTeam','awayTeam'):
        links=row.select('td.'+side+' a[href]')
        if len(links)!=1:raise ValueError('display witness has ambiguous sides')
        query=parse_qs(urlparse(links[0]['href']).query)
        sides.append(dict(team_id=int(query['team_id'][0]),name=links[0].get_text(' ',strip=True)))
    goals=row.select('td.score a.vs em')
    if len(goals)!=2 or any(not goal.get_text(strip=True).isdigit() for goal in goals):
        raise ValueError('display witness lacks a completed original score')
    fixture=dict(date=day,game_id=game_id,sides=sides,
        score=[int(goal.get_text(strip=True)) for goal in goals])
    sheet=original.match(body(witness['match']),fixture,group['provider_team_id'],witness['match']['url'],True)
    matches=[p for key in ('starting_xi','published_bench') for p in sheet[key]
             if p['provider_player_id']==person['provider_player_id']]
    if len(matches)!=1:raise ValueError('display witness does not identify the exact numeric person')
    return dict(policy=allocation.soccerbase.POLICY,
        source_provider_person_id=person['source_player_id'],source_person_id=person['source_player_id'],
        birth_date=person['birth_date'],names=[dict(field='dated-match-label',name=matches[0]['published_match_name'])])


def read(season,group,*,selected_person_ids=None):
    team=group['provider_team_id']
    fixture=original.first_fixture(body(group['schedule']),team,season,group['competition'],
        group['club_name'],group['schedule']['url'])
    if fixture['game_id']!=group['expected_opening_game_id']:
        raise ValueError('source does not reproduce the reviewed first fixture')
    sheet=original.match(body(group['match']),fixture,team,group['match']['url'],True)
    selected=None if selected_person_ids is None else set(selected_person_ids)
    if selected is not None:
        published={p['provider_player_id'] for key in ('starting_xi','published_bench') for p in sheet[key]}
        if (not selected or len(selected)!=len(selected_person_ids)
                or any(type(pid) is not int for pid in selected) or not selected<=published
                or group.get('reserves') or group.get('display_witnesses')):
            raise ValueError('partial source read needs unique published matchday IDs, without reserve claims')
    desired=[];seen=set();gaps=[]
    for membership in ('starting_xi','published_bench'):
        for player in sheet[membership]:
            if selected is not None and player['provider_player_id'] not in selected:continue
            pid=player['provider_player_id'];binding=group['profiles'][str(pid)]
            person,facts,missing=profile(binding,pid)
            if pid in seen or player['position'] not in ('G','D','M','F'):
                raise ValueError('original roster has duplicate identity or unproven match role')
            seen.add(pid);facts['position']=player['position'];person['source_provider']='soccerbase'
            desired.append(dict(source_person=person,source_player=facts,membership=membership,
                raw_evidence=dict(status='raw-source-reparsed',local_path=binding['path'],source_sha256=binding['sha256']),
                source_display_aliases=dict(policy=allocation.soccerbase.POLICY,
                    source_provider_person_id=person['source_player_id'],source_person_id=person['source_player_id'],
                    birth_date=person['birth_date'],names=[dict(field='dated-match-label',name=player['published_match_name'])])))
            gaps.extend(dict(provider_player_id=pid,**g) for g in missing)
    starters=[r for r in desired if r['membership']=='starting_xi']
    if selected is None and (len(starters)!=11 or starters[0]['source_player']['position']!='G' or sum(r['source_player']['position']=='G' for r in starters)!=1):
        raise ValueError('complete sourced XI with one opening goalkeeper required')
    for pid in group.get('reserves',[]):
        if pid in seen:raise ValueError('reserve repeats a source matchday identity')
        binding=group['profiles'][str(pid)];person,facts,missing=profile(binding,pid)
        interval=reserves.career_interval(body(binding),team,fixture['date'])
        if not interval['from_date']<fixture['date']<interval['to_date']:
            raise ValueError('opening reserve needs an unambiguous interior career interval')
        if facts['position'] not in ('G','D','M','F'):raise ValueError('opening reserve role unavailable')
        seen.add(pid);person['source_provider']='soccerbase'
        replacement=dict(source_person=person,source_player=facts,membership='positive-original-provider-dated-opening-reserve',
            original_provider_career_interval=interval,reserve_policy=reserves.POLICY,
            raw_evidence=dict(status='raw-source-reparsed',local_path=binding['path'],source_sha256=binding['sha256']))
        witness=group.get('display_witnesses',{}).get(str(pid))
        if witness:replacement['source_display_aliases']=published_alias(season,group,person,witness)
        desired.append(replacement);gaps.extend(dict(provider_player_id=pid,**g) for g in missing)
    if set(group.get('display_witnesses',{}))-{str(p) for p in group.get('reserves',[])}:
        raise ValueError('unused or non-reserve display witness')
    result=dict(policy=POLICY,fixture=fixture,desired=desired,secondary_fact_gaps=gaps,
                source_group=copy.deepcopy(group),native_writes=0)
    if selected is not None:
        result['selection']=dict(provider_player_ids=sorted(selected),
            complete_roster_biographies_verified=False,original_match_XI_rows=len(sheet['starting_xi']))
    return result
