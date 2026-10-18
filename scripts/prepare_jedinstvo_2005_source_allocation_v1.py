"""Replay firstXI11/used3 plus four positive opening reserves into fixed18.

No first-match bench invention. An adjacent-year catalogue supplies three reserve
identities/broad roles only; their explicit entry AND exit dates prove opening
ownership. Existing seasons, native games and preferred registrations untouched.
"""
import copy
import re

from bs4 import BeautifulSoup

from scripts import prepare_jedinstvo_2005_identity_review_v1 as original
from scripts.capture_stock_replacement_sources_20261010 import ROOT
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts.prepare_ofk_2004_source_allocation_v1 import annual_roles
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_published_person_identity_v1 as biographies
from scripts import season_published_transfer_history_v1 as histories
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_published_display_names_v1 as display
from scripts import season_published_family_component_v1 as families
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import audit_published_player_identities_v1 as identities

POLICY='original-first-XI-used-subs-plus-positive-dated-reserves-fixed18-v1'


def native_membership(value):
    if value=='starting-xi':
        return 'starting_xi'
    if value not in ('used-opening-substitute','positive-bracketed-and-original-signed-arrival','positive-original-dated-opening-reserve'):
        raise ValueError('unsupported original opening membership category')
    return value


def source18():
    first=original.prepare()
    _,raw,binding=source_rows('jedinstvo-2006-original-annual')
    roles=annual_roles(raw,2006,'Jedinstvo Bijelo Polje')
    page=BeautifulSoup(raw,'html.parser')
    names={int(re.search(r'/spieler/(\d+)',a['href'])[1]):a.get_text(' ',strip=True)
        for a in page.select('table.items a[href*="/profil/spieler/"]')}
    history_path=ROOT.parent/'jedinstvo-2005-adjacent-catalogue-history-leads-v1.json'
    events,_=histories.merge({},pipeline.read_json_file(history_path))
    people_path=ROOT.parent/'jedinstvo-2005-additional-opening-reserve-identities-v1.json'
    supplement=pipeline.read_json_file(people_path)
    biographies.merge({},supplement)
    for b in supplement['historical_opening_inputs']:
        if registry.sha256_file(registry.ROOT/b['path'])!=b['sha256']:
            raise ValueError('additional original identity input changed')
    persons={p['source_player_id']:p for b in supplement['batches'] for p in b['people']}
    # Both signed defensive arrivals need the same single long reserve-name
    # window. Keep Bojan and use the three other positively dated members;
    # never truncate either original surname or alter the sourced firstXI.
    matched=[copy.deepcopy(r) for r in first['matched_people'] if r['source_player_id']!=36009]
    for id,role in ((26084,'M'),(28562,'F'),(36038,'M')):
        bracket=transfer.transfer_interval(events[id],'2005-08-06')
        if (bracket.get('status')!='recorded-entry-and-exit-bracket-fixture'
                or bracket['source_owner_club_id']!=8357 or roles[id]!=role
                or names[id]!=persons[id]['name']):
            raise ValueError('additional reserve original identity/role/positive dated membership differs')
        matched.append(dict(source_player_id=id,canonical_published_name=persons[id]['name'],birth_date=persons[id]['birth_date'],
            position=roles[id],membership='positive-original-dated-opening-reserve',bracket=bracket,
            role_basis='explicit adjacent2006 catalogue broad role; transfer dates independently prove2005 opening membership'))
    if len(matched)!=18 or len({r['source_player_id'] for r in matched})!=18:
        raise ValueError('original positive fixed18 incomplete or repeated')
    combined=pipeline.read_json_file(ROOT.parent/'jedinstvo-2005-original-person-identities-v1.json')
    combined=copy.deepcopy(combined)
    combined['batches']+=copy.deepcopy(supplement['batches'])
    combined['historical_opening_inputs']+=copy.deepcopy(supplement['historical_opening_inputs'])
    biographies.merge({},combined)
    bindings=first['original_bindings']+[binding,
        dict(path=registry.relative_workspace_path(history_path),sha256=registry.sha256_file(history_path)),
        dict(path=registry.relative_workspace_path(people_path),sha256=registry.sha256_file(people_path))]
    return first['original_match'],matched,combined,bindings


def prepare(output,baseline_release_id=None):
    if output.exists():
        raise ValueError('source-only allocation is immutable')
    actual,matched,combined,bindings=source18()
    biography=ROOT.parent/'jedinstvo-2005-combined-original-identities-v1.json'
    if biography.exists():
        if pipeline.read_json_file(biography)!=combined:
            raise ValueError('retained combined original biography changed')
    else:
        pipeline.write_canonical_json(biography,combined)
    index,_=identities.load_identity_snapshot()
    index,review=biographies.merge(index,combined)
    if review['refused']:
        raise ValueError('original biographies conflict with pinned source identities')
    persons={p['source_player_id']:p for b in combined['batches'] for p in b['people']}
    ids=[r['source_player_id'] for r in matched]
    if any(persons[r['source_player_id']]['birth_date']!=r['birth_date'] for r in matched):
        raise ValueError('confirmed original birthday conflict')
    release=registry.load_registered_release('2005-06',baseline_release_id) if baseline_release_id else registry.load_preferred_release('2005-06')
    layers=list(planner.package_layers(release))
    owners=[(label,p,path,c) for label,p,path in layers for c in p['clubs'] if c['carrier_id']==706]
    if len(owners)!=1:
        raise ValueError('native706 must have one recipe owner')
    layer,package,path,club=owners[0]
    if club['name']!='Becej' or any('jedinstvo' in c['name'].casefold() for _,p,_ in layers for c in p['clubs']):
        raise ValueError('stock carrier changed or proposed club already represented')
    slots=[p for p in package['players'] if p['club_id']==club['id']]
    if len(slots)!=18:
        raise ValueError('fixed native roster capacity changed')
    jug=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    desired=[]
    for row in matched:
        person={k:copy.deepcopy(v) for k,v in persons[row['source_player_id']].items() if k!='published_name_variants'}
        desired.append(dict(source_person=person,source_player=dict(name=person['name'],birth_date=person['birth_date'],position=row['position'],
                nationality=None,height_cm=None,weight_kg=None,shirt_number=None),membership=native_membership(row['membership']),
            raw_evidence=dict(status='raw-source-reparsed',local_path=bindings[0]['path'],source_sha256=bindings[0]['sha256']),
            source_role_basis=dict(role=row['position'],basis='explicit catalogue broad role or original dated signed defensive arrival',identity=row),
            secondary_facts_status='unconfirmed-log-not-inherit-as-source-fact'))
    if [r['source_person']['source_player_id'] for r in desired if r['membership']=='starting_xi']!=ids[:11]:
        raise ValueError('source-to-native adapter lost the original eleven starter memberships')
    allocation.validate_opening_birth_dates(desired,actual['fixture_date'])
    fitted=allocation.allocate(jug,slots,desired,display.claims(biography),published_families=families.claims(biography,ids),
        opening_slot_orders=allocation.startup_orders(jug,slots),allow_keeper_order_exchange=True)
    outside=[]
    for _,p,_ in layers:
        clubs={c['id']:c['name'] for c in p['clubs']}
        for player in p['players']:
            key=identities.key(player,index)
            if player['club_id']!=club['id'] and key and key[0]=='published-person' and key[1] in ids:
                outside.append(dict(source_player_id=key[1],carrier_id=player['carrier_id'],club=clubs[player['club_id']],native_recipe_player=player))
    result=dict(schema_version='pm99-private-original-jedinstvo2005-fixed18-feasibility-v1',season='2005-06',policy=POLICY,
        baseline_release_id=release.release_id,layer=layer,
        baseline_package=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)),
        before_club=club,new_club='Jedinstvo Bijelo Polje',country='serbia',transfermarkt_club_id=8357,
        original_opening=actual,first_fixture=dict(date=actual['fixture_date']),original_bindings=bindings,
        biography_input=dict(path=registry.relative_workspace_path(biography),sha256=registry.sha256_file(biography)),
        desired_people=desired,allocation=fitted,selected_bench_ids=ids[11:],outside_identity_owners=outside,
        capacity_selection_policy='OriginalXI11/used3 plus four positively dated opening reserves; NOT an invented unused opening bench.',
        role_disagreements=[],native_writes=0,publication_authorised=False,
        limitations=['One positively sourced goalkeeper; no invented second keeper.',
            'Positive Mladen Kaludjerovic excluded only for bounded reserve-name capacity; Bojan and three other positive reserves fit instead. Neither surname truncated.',
            'Serbian native league carrier represents pre-independence Serbia and Montenegro; no club relocation claimed.',
            'Annual broad roles not independently sourced formation or fine deployment.'],
        remaining=['secondary facts','dated manager/ground/kits','native readback','whole source replay','runtime proof'])
    pipeline.write_canonical_json(output,result)
    return result


if __name__=='__main__':
    result=prepare(ROOT.parent/'jedinstvo-2005-fixed18-source-feasibility-v1.json')
    print(dict(people=len(result['desired_people']),outside_owners=len(result['outside_identity_owners']),native_writes=0))
