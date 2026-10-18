"""Calibrated ability-only policy: unknown XI is not a substitute declaration.

Keep rejected v2 implementation unchanged for reproducibility. Full DOB is
required for EA identity matching, NOT for an explicitly age-neutral editorial
estimate. Do not touch the missing DOB itself. Names/roles/assets stay exact.
"""
import csv
import datetime as dt
import re
from collections import defaultdict
from functools import lru_cache
from statistics import median
from scripts import season_rating_calibration_v1 as old

registry=old.registry;pipeline=old.pipeline;roster=old.roster;model=old.model
SOURCE_ID='source-bound-rating-calibration-v3'
ROOT=registry.ROOT/'.local/consolidated-audit-20261009/rating-calibration-v3'
DIVISION_BOUNDS={'Premier League':(68,84),'Championship':(56,74),'League One':(48,64),'League Two':(40,56)}
ALIASES={('joshwilsonesbrand','2002-12-26'):'Joshua Wilson-Esbrand'}
POLICY=dict(version=3,base_mapping=old.MAPPING,FIFA_edition_policy=old.POLICY['edition'],
    identities='exact full/short source name OR full published tokens in order in full FIFA name plus exact DOB, unique player ID; documented Josh/Joshua alias only',
    missing_XI='unknown status has zero bonus, never reserve/youth-reserve penalty; preserve native XI/tactics',
    missing_DOB='age-neutral editorial estimate; no invented date or FIFA identity match',
    seed='normalized published full name plus exact DOB; source-person ID only when no DOB exists; never carrier or club order',
    English_ability_bounds=DIVISION_BOUNDS,English_table_scale='60+0.8*(prior table score-60), bounded within source-proven current division',
    youth_reserve='extra -10 only with an actual declared XI that excludes the age<=21 player',
    Yamal='explicit editorial 2024/2025 anchor informed by dated Euro2024 award and July2025 Barcelona report, NOT EA numerical ratings',
    whole_record_fallback='preserved; source-authored roles can receive estimates even if DOB unavailable',
    scope='ten ability bytes/provenance only; no identity, DOB, nationality, position, formation, order, manager, artwork or executable changes')

def tokens(name):
    return tuple(roster.normalise(word) for word in re.findall(r"[^\W\d_]+",name,flags=re.UNICODE))

def subsequence(needle,haystack):
    cursor=iter(haystack)
    return len(needle)>=2 and all(any(word==part for word in cursor) for part in needle)

@lru_cache(maxsize=2)
def by_dob(file_sha):
    result=defaultdict(list)
    for row in csv.DictReader(old.FIFA.open(newline='')):
        if not row.get('dob') or any(not row.get(col) for col in old.MAPPING.values()):continue
        result[(int(row['fifa_version']),row['dob'])].append(dict(player_id=row['player_id'],edition=int(row['fifa_version']),
            date=row['fifa_update_date'],dob=row['dob'],positions=row['player_positions'],long_name=row['long_name'],
            short_name=row['short_name'],values={key:max(1,min(99,int(row[col]))) for key,col in old.MAPPING.items()}))
    return result

def match(player,year,index,expanded):
    direct=old.match(player,year,index)
    if direct:return direct
    dob=player['facts'].get('birth_date');name=player.get('source_name') or player['name']
    if not isinstance(dob,str):return None
    name=ALIASES.get((roster.normalise(name),dob),name);edition=year-1999
    editions=[edition] if 15<=edition<=23 else ([23] if 24<=edition<=26 else [])
    for e in editions:
        candidates={row['player_id']:row for row in expanded.get((e,dob),[])
            if (roster.normalise(name) in (roster.normalise(row['long_name']),roster.normalise(row['short_name']))
                or subsequence(tokens(name),tokens(row['long_name'])))
            and (player['facts']['primary_position']=='G')==('GK' in row['positions'].split(', '))}
        if len(candidates)==1:return next(iter(candidates.values()))
    return None

def status(player,club):
    opening=club.get('opening',{})
    if 'starting_xi_player_ids' not in opening:return 'unknown'
    return 'starting_xi' if player['id'] in opening['starting_xi_player_ids'] else 'opening_squad'

def editorial(player,strength,state,snapshot):
    born=player['facts'].get('birth_date');published=player.get('source_name') or player['name']
    p=dict(player)
    p['person_id']=('name-dob-'+old.sha(dict(name=roster.normalise(published),dob=born))
        if isinstance(born,str) else player['person_id'])
    values=old.editorial(p,strength,state=='starting_xi',snapshot)
    if state=='unknown':
        # Undo the old -4 reserve bonus and additional -10 young-reserve cut.
        age=model._age_on(born,snapshot) if isinstance(born,str) else None
        undo=4+(10 if age is not None and age<=21 else 0)
        values={key:max(1,min(99,value+undo)) if key!='handling' else value for key,value in values.items()}
        if player['facts']['primary_position']=='G':values['handling']=max(35,values['quality']-12,values['handling'])
    return values

def yamal_anchor(player,year):
    if (roster.normalise(player.get('source_name') or player['name']),player['facts'].get('birth_date'))!=('lamineyamal','2007-07-13'):
        return None
    if year not in (2024,2025):return None
    quality=82 if year==2024 else 86
    return dict(quality=quality,speed=88 if year==2024 else 90,stamina=76 if year==2024 else 81,
        aggression=48,passing=78 if year==2024 else 84,tackling=29,heading=45,
        shooting=75 if year==2024 else 81,dribbling=88 if year==2024 else 93,handling=8)

def rows(base):
    package=pipeline.read_json_file(base.package_path);year=int(base.season[:4]);snapshot=dt.date(year,8,1)
    fifa_sha=registry.sha256_file(old.FIFA);index=old.fifa_index(fifa_sha);expanded=by_dob(fifa_sha)
    layer=(registry.ROOT/'scripts/data/2015-16-english92-editorial-ratings-v1.json' if base.season=='2015-16'
        else registry.ROOT/'.local/season-english-preseason-rating-policy-v4'/base.season/'english-rating-audit.json')
    strengths=old.english_strengths(layer);clubs={c['id']:c for c in package['clubs']}
    division={}
    if base.season!='2015-16':
        division={old._club_key(row['club']):row['current_division'] for row in pipeline.read_json_file(layer)['club_strengths']}
    cohort=defaultdict(list);prior=defaultdict(list);matched={}
    for player in package['players']:
        prior[player['club_id']].append(player['ratings']['values']['quality'])
        if player.get('policy')=='preserve-existing-mode1':continue
        if player['facts'].get('primary_position') not in ('G','D','M','F'):continue
        row=match(player,year,index,expanded)
        if row:
            matched[player['carrier_id']]=row;cohort[player['club_id']].append(old.fifa_values(row,year,player['facts']['primary_position'])['quality'])
    hierarchy={}
    for cid,club in clubs.items():
        key=old._club_key(club['name']);group=roster.club_group(club)
        if len(cohort[cid])>=3:value=round(median(cohort[cid]));method='identity-matched-target-or-bounded-past-FIFA-cohort'
        elif group=='england' and key in strengths:
            value=round(60+(strengths[key]-60)*0.8);method='source-prior-table-ability-scale'
            if key in division:
                low,high=DIVISION_BOUNDS[division[key]];value=max(low,min(high,value))
        else:
            tier=old.inputs.COUNTRY_STRENGTH.get(group,48 if group=='england' else 60)
            value=max(tier-12,min(tier+12,round(median(prior[cid])))) if prior[cid] else tier
            method='explicit-native-club-prior-country-bounded-editorial-estimate'
        hierarchy[cid]=(max(30,min(95,value)),method)
    updates=[]
    for player in sorted(package['players'],key=lambda p:p['carrier_id']):
        position=player['facts'].get('primary_position');current=player['ratings']['values']
        if position not in ('G','D','M','F') or player.get('policy')=='preserve-existing-mode1':continue
        row=matched.get(player['carrier_id']);anchor=yamal_anchor(player,year);club=clubs[player['club_id']]
        if anchor:
            values=anchor;method='dated-achievement-informed-Yamal-editorial-anchor-v3'
            basis=dict(not_EA_numerical_fact=True,evidence='Yamal Euro2024/Barcelona July2025 sources',year=year)
        elif row:
            values=old.fifa_values(row,year,position)
            method='identity-DOB-target-edition-FIFA-v3' if row['edition']==year-1999 else 'bounded-past-FIFA-editorial-age-proxy-v3'
            basis=dict(fifa_player_id=row['player_id'],fifa_edition=row['edition'],fifa_snapshot=row['date'],
                match_name=player.get('source_name') or player['name'],match_dob=player['facts']['birth_date'],
                past_proxy_years=year-(row['edition']+1999))
        else:
            strength,strength_method=hierarchy[player['club_id']];state=status(player,club)
            values=editorial(player,strength,state,snapshot);method='identity-club-role-age-optional-editorial-calibration-v3'
            basis=dict(club_strength=strength,club_strength_method=strength_method,opening_status=state,
                birth_date_available=isinstance(player['facts'].get('birth_date'),str),
                age=model._age_on(player['facts']['birth_date'],snapshot) if isinstance(player['facts'].get('birth_date'),str) else None)
        if position!='G':values['handling']=max(1,min(20,values['handling']))
        if values==current:continue
        updates.append(dict(carrier_id=player['carrier_id'],before_sha256=old.sha(player),source_name=player.get('source_name') or player['name'],
            ratings=dict(profile='pm99-visible-skills-v1',values=values,
                provenance=dict(method=method,proof_grade='reviewed-editorial',source_ids=[SOURCE_ID])),rating_basis=basis))
    sources=ROOT/'dated-policy-sources.json'
    bindings=[dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)) for path in
        (old.FIFA,layer,registry.ROOT/'scripts/season_rating_calibration_v3.py',registry.ROOT/'scripts/season_rating_calibration_v1.py',
            registry.ROOT/'scripts/season_editorial_ratings_v1.py',registry.ROOT/'scripts/season_editorial_rating_input_builder_v1.py',
            registry.ROOT/'scripts/materialise_english_rating_layer_v1.py',sources)]
    for item in pipeline.read_json_file(sources)['sources']:
        path=registry.ROOT/item['path']
        if registry.sha256_file(path)!=item['sha256']:raise ValueError('dated policy raw source differs')
        bindings.append(item)
    bindings.append(dict(policy=POLICY,policy_sha256=old.sha(POLICY)))
    return updates,bindings
