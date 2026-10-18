"""Explicitly bind the one legacy 2015 English layer before any duplicate write.

This is not a waiver for shared carriers, starters, source evidence or bytes.
Every overlay row must still pass the ordinary independent ownership/source
replay and native player writer. The original playable 2015 release is retained.
"""
import json
from scripts import season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase

POLICY='exact-bound-current-2015-English-overlay-nonstarter-duplicate-delta-v1'
ARTIFACT='english-contextual-package-2015-16'


def binding(release):
    layers=planner.package_layers(release)
    english=[(p,path) for label,p,path in layers if label=='english']
    if release.season!='2015-16' or len(english)!=1:
        raise ValueError('English overlay repairs require exactly the current 2015 English layer')
    document,path=english[0]
    return {'policy':POLICY,'artifact_id':ARTIFACT,'path':registry.relative_workspace_path(path),
            'sha256':registry.sha256_file(path)}


def validate_binding(release,plan):
    rows=[r for r in plan['updates'] if r['layer']=='english']
    enabled=bool(plan.get('allow_english_overlay_replacements'))
    claim=plan.get('bindings',{}).get('english_overlay')
    if not rows and not enabled and claim is None:return
    if not enabled or claim!=binding(release):
        raise ValueError('English duplicate replacement lacks the exact bound current overlay')
    if not all(plan.get('bindings',{}).get(k) for k in (
            'published_person_supplement','published_transfer_supplement','opening_person_supplement_policy',
            'soccerbase_opening_sources')):
        raise ValueError('English overlay repair requires independent original people/history and actual native-XI protection')
    layers=planner.package_layers(release)
    _,english,_=next(r for r in layers if r[0]=='english')
    players={p['id']:p for p in english['players']};clubs={c['id']:c for c in english['clubs']}
    occurrences={}
    for label,pkg,_ in layers:
        for p in pkg['players']:occurrences.setdefault(p['carrier_id'],[]).append((label,p['id']))
    cache=None;checked={}
    for row in rows:
        old=players.get(row['player_id']);club=clubs.get(row['club_id'])
        if old!=row['before'] or club is None or old['club_id']!=club['id'] or old['carrier_id']!=row['carrier_id']:
            raise ValueError('English duplicate replacement is not the exact prior overlay player')
        if occurrences[old['carrier_id']]!=[('english',old['id'])]:
            raise ValueError('English duplicate replacement cannot change a shared native carrier')
        if old['carrier_family']!='dd6361':
            raise ValueError('English overlay delta requires the proven modern player record layout')
        if old['id'] in club.get('opening',{}).get('starting_xi_player_ids',[]):
            raise ValueError('English overlay duplicate replacement cannot change a declared starter')
        if club['id'] not in checked:
            checked[club['id']],cache=soccerbase.native_starters(release,club,cache)
        if old['carrier_id'] in checked[club['id']]:
            raise ValueError('English overlay duplicate replacement cannot change an actual native starter')
