"""Versioned ability-only calibration. Estimates are never historical facts.

FIFA identity requires a complete published name AND DOB, unambiguous player
ID and compatible keeper/outfield class. Use the target edition; allow a
declared past proxy for at most three years, never future editions for older
seasons. No identity, position, opening XI or membership changes here.
"""
import csv
import datetime as dt
import hashlib
from collections import defaultdict
from functools import lru_cache
from statistics import median
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_package_v2 as packages,season_historical_roster_audit_v1 as roster
from scripts import season_editorial_ratings_v1 as model
from scripts import season_editorial_rating_input_builder_v1 as inputs
from scripts.materialise_english_rating_layer_v1 import _club_key

SOURCE_ID='source-bound-rating-calibration-v2'
FIFA=registry.ROOT/'.local/external-sources/sofifa-fifa16/male_players_legacy.csv'
MAPPING=dict(quality='overall',speed='movement_sprint_speed',stamina='power_stamina',
    aggression='mentality_aggression',passing='attacking_short_passing',
    tackling='defending_standing_tackle',heading='attacking_heading_accuracy',
    shooting='attacking_finishing',dribbling='skill_dribbling',handling='goalkeeping_handling')
POLICY=dict(version=2,identity='exact normalized full published name plus literal DOB, unique FIFA player ID',
    edition='target season edition where cached; past only <=3 years; no future extrapolation',
    mapping=MAPPING,proxy_ageing='per elapsed year: speed -2/stamina -1 after age30; quality -1 after32; keeper handling unchanged',
    editorial='known prior-season English club hierarchy, otherwise compatible source cohort median or declared native club-quality prior bounded to country tier +/-12; deterministic person seed and proven fine-role specialization',
    youth_reserve='non-XI age<=21: additional -10 quality/field abilities; goalkeeper floor maintained',
    outfield_handling='1..20; generic unsourced technique centred on8',
    unchanged='existing prior-table English estimates without a matching FIFA identity, whole-record seed fallbacks and incomplete source identities retained except handling safety')

def sha(value):return hashlib.sha256(packages.canonical_json_bytes(value)).hexdigest()

@lru_cache(maxsize=2)
def fifa_index(file_sha):
    result=defaultdict(dict)
    for row in csv.DictReader(FIFA.open(newline='')):
        edition=int(row['fifa_version'])
        if not row.get('dob') or any(not row.get(col) for col in MAPPING.values()):continue
        compact=dict(player_id=row['player_id'],edition=edition,date=row['fifa_update_date'],dob=row['dob'],
            positions=row['player_positions'],values={key:max(1,min(99,int(row[col]))) for key,col in MAPPING.items()})
        for name in {row['long_name'],row['short_name']}:
            result[(edition,roster.normalise(name),row['dob'])][row['player_id']]=compact
    return result

def match(player,year,index):
    dob=player['facts'].get('birth_date');name=player.get('source_name') or player['name']
    if not isinstance(dob,str):return None
    edition=year-1999
    editions=[edition] if 15<=edition<=23 else ([23] if 24<=edition<=26 else [])
    for e in editions:
        candidates=index.get((e,roster.normalise(name),dob),{})
        if len(candidates)!=1:continue
        row=next(iter(candidates.values()))
        if (player['facts']['primary_position']=='G')!=('GK' in row['positions'].split(', ')):continue
        return row
    return None

def fifa_values(row,year,position):
    values=dict(row['values']);elapsed=year-(row['edition']+1999)
    age=year-int(row['dob'][:4]);prior_age=age-elapsed
    mature_years=max(0,age-30)-max(0,prior_age-30)
    if elapsed:
        for field,rate in [('speed',2),('stamina',1)]:values[field]=max(1,values[field]-mature_years*rate)
        values['quality']=max(1,values['quality']-(max(0,age-32)-max(0,prior_age-32)))
    if position!='G':values['handling']=max(1,min(20,values['handling']))
    return values

def english_strengths(path):
    layer=pipeline.read_json_file(path)
    rows=layer['club_strengths']
    if isinstance(rows,dict):return {_club_key(name):value for name,value in rows.items()}
    result={}
    for row in rows:
        key=_club_key(row['club'])
        if key in result:raise ValueError('English prior hierarchy duplicate club')
        result[key]=row['strength']
    return result

def editorial(player,strength,starting,snapshot):
    facts=player['facts'];dob=facts.get('birth_date')
    context=dict(person_id=player['person_id'],position=facts['primary_position'],
        squad_status='starting_xi' if starting else 'opening_squad',club_id=player['club_id'],
        birth_date=dob if isinstance(dob,str) else None,
        height_cm=facts.get('height_cm') if isinstance(facts.get('height_cm'),int) else None)
    generated=model._editorial_ratings(player=context,snapshot=snapshot,
        club=dict(strength=strength,source_ids=[SOURCE_ID]),hierarchy_sha256=sha(dict(strength=strength)))['values']
    age=model._age_on(context['birth_date'],snapshot)
    if not starting and age is not None and age<=21:
        generated={k:max(1,v-10) if k!='handling' else v for k,v in generated.items()}
    fine=facts.get('fine_roles')
    primary=fine[0] if isinstance(fine,list) and fine else None
    changes={}
    if facts['primary_position']=='D' and primary in (1,2):changes=dict(speed=8,dribbling=8,passing=4,heading=-4)
    if facts['primary_position'] in ('M','F') and primary in (6,10,11,13):changes=dict(speed=7,dribbling=7,heading=-5,tackling=-5)
    if facts['primary_position']=='M' and primary==14:changes=dict(tackling=6,shooting=-6)
    for k,delta in changes.items():generated[k]=max(1,min(99,generated[k]+delta))
    if facts['primary_position']=='G':generated['handling']=max(35,generated['handling'],generated['quality']-12)
    return generated

def rows(base):
    package=pipeline.read_json_file(base.package_path);year=int(base.season[:4]);snapshot=dt.date(year,8,1)
    fifa_sha=registry.sha256_file(FIFA);index=fifa_index(fifa_sha)
    layer=(registry.ROOT/'scripts/data/2015-16-english92-editorial-ratings-v1.json' if base.season=='2015-16'
        else registry.ROOT/'.local/season-english-preseason-rating-policy-v4'/base.season/'english-rating-audit.json')
    strengths=english_strengths(layer)
    clubs={c['id']:c for c in package['clubs']};cohorts=defaultdict(list);fifa_matches={}
    for player in package['players']:
        row=match(player,year,index)
        if row:
            fifa_matches[player['carrier_id']]=row
            cohorts[player['club_id']].append(fifa_values(row,year,player['facts']['primary_position'])['quality'])
    old_cohorts=defaultdict(list)
    for player in package['players']:old_cohorts[player['club_id']].append(player['ratings']['values']['quality'])
    club_strength={}
    for cid,club in clubs.items():
        group=roster.club_group(club)
        if len(cohorts[cid])>=3:value=round(median(cohorts[cid]));method='identity-matched-FIFA-cohort-median'
        elif group=='england' and _club_key(club['name']) in strengths:
            # The old table score drives board ambition, not a FIFA overall.
            # Keep its within-division ordering without treating champion90
            # as every academy player's ability90.
            value=round(60+(strengths[_club_key(club['name'])]-60)*0.8)
            method='pinned-prior-English-standings-ability-scale-0.8'
        else:
            tier=inputs.COUNTRY_STRENGTH.get(group,48 if group=='england' else 60)
            value=max(tier-12,min(tier+12,round(median(old_cohorts[cid])))) if old_cohorts[cid] else tier
            method='explicit-editorial-native-club-prior-country-bounded-not-historical-fact'
        club_strength[cid]=(max(30,min(95,value)),method)
    updates=[]
    for player in sorted(package['players'],key=lambda p:p['carrier_id']):
        position=player['facts'].get('primary_position');current=player['ratings']['values']
        if position not in ('G','D','M','F') or player.get('policy')=='preserve-existing-mode1':continue
        club=clubs[player['club_id']];method=player['ratings']['provenance']['method']
        matched=fifa_matches.get(player['carrier_id']);basis={}
        if matched:
            values=fifa_values(matched,year,position)
            new_method='exact-name-DOB-target-edition-FIFA-v2' if matched['edition']==year-1999 else 'bounded-past-FIFA-editorial-age-proxy-v2'
            basis=dict(fifa_player_id=matched['player_id'],fifa_edition=matched['edition'],fifa_snapshot=matched['date'],
                match_name=player.get('source_name') or player['name'],match_dob=player['facts']['birth_date'],
                past_proxy_years=year-(matched['edition']+1999))
        elif method=='deterministic prior-season table editorial rating model v1':
            values=dict(current);new_method='prior-table-estimate-preserved-with-handling-guard-v2'
        elif isinstance(player['facts'].get('birth_date'),str):
            opening=club.get('opening',{});starting=player['id'] in opening.get('starting_xi_player_ids',[])
            strength,strength_method=club_strength[player['club_id']]
            values=editorial(player,strength,starting,snapshot);new_method='identity-seeded-club-role-editorial-calibration-v2'
            basis=dict(club_strength=strength,club_strength_method=strength_method,starting_xi=starting,
                fine_roles=player['facts'].get('fine_roles'),age=model._age_on(player['facts']['birth_date'],snapshot))
        else:
            values=dict(current);new_method='incomplete-identity-baseline-retained-with-handling-guard-v2'
        if position!='G':values['handling']=max(1,min(20,values['handling']))
        if values==current:continue
        updates.append(dict(carrier_id=player['carrier_id'],before_sha256=sha(player),
            source_name=player.get('source_name') or player['name'],
            ratings=dict(profile='pm99-visible-skills-v1',values=values,
                provenance=dict(method=new_method,proof_grade='reviewed-editorial',source_ids=[SOURCE_ID])),
            rating_basis=basis))
    bindings=[dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))
        for path in (FIFA,layer,registry.ROOT/'scripts/season_rating_calibration_v1.py',
            registry.ROOT/'scripts/season_editorial_ratings_v1.py',registry.ROOT/'scripts/season_editorial_rating_input_builder_v1.py',
            registry.ROOT/'scripts/materialise_english_rating_layer_v1.py')]
    bindings.append(dict(policy=POLICY,policy_sha256=sha(POLICY)))
    return updates,bindings
