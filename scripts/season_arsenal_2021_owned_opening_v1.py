"""Original Arsenal25 plus four coupled reserves, within existing carriers.

This transaction fixes the opponent XI without rewriting a season. Sixteen
represented people retain their actual ten skills. New actors use the existing
v3 rating policy; correct starter identity controls contextual phase tactics.
"""
import copy
from datetime import date
import hashlib
from statistics import median

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_birth_date import rewrite_indexed_native_birth_dates
from app.player_initial_order import read_initial_order
from app.xor import xor_decode
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_package_v2 as packages,season_duplicate_ownership_delta_v1 as delta
from scripts import prepare_arsenal_native_assignment_20261016 as assignment
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_rating_calibration_v3 as ratings
from scripts import season_exact_fifa_role_delta_v1 as exact_roles
from scripts.season_historical_role_plan_v1 import ROLE_MAP
from scripts import season_contextual_tactics_rollout_v1 as rollout
from scripts import season_contextual_tactics_v1 as tactics
from scripts import season_opening_order_repair_v1 as ordering
from scripts import season_same_carrier_name_capacity_v1 as capacity
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
from scripts.build_woking_owned_opening_20261011 import skills

SCHEMA='pm99-original-Arsenal2021-owned-opening25-four-paired-reserves-v1'
PREFIX='sourced-arsenal2021-owned-opening-'
FILENAME='sourced-arsenal2021-owned-opening.json'
MODE='known-good-baseline-original-Arsenal2021-owned-opening25-v1'


def digest(raw):return hashlib.sha256(raw).hexdigest()
def filename(plan):return FILENAME
def selected_carriers(plan):return {r['carrier_id'] for r in plan['assignment']['replacements']}


def composition(package,prepared):
    by={p['carrier_id']:p for p in package['players']}
    rows=[dict(layer='main',player_id=by[r['carrier_id']]['id'],carrier_id=r['carrier_id'],
        before=by[r['carrier_id']],replacement=r['replacement'],
        replacement_opening_evidence=dict(date='2021-08-13')) for r in prepared['replacements']]
    return dict(season='2021-22',updates=rows,
        bindings=dict(snapshot=dict(project_url='https://www.brentfordfc.com/')),
        source_title='Original Arsenal opening XI, bench, August reserves and four positive paired club members',
        proof_covers=['Arsenal2021-source25-and-four-paired-reserves; not global squad approval'])


def provisional(package,prepared):
    result=delta.updated_package(package,composition(package,prepared))
    by={p['carrier_id']:p for p in result['players']}
    for row in prepared['replacements']:
        by[row['carrier_id']]['name']=row['display']['display_name']
    wanted={p['source_person']['source_player_id']:p for p in prepared['source_admission']['desired_people']}
    for pid,carrier in prepared['retained_Arsenal']:
        if by[carrier]['facts']['primary_position']!=wanted[pid]['source_player']['position']:
            raise ValueError('retained Arsenal broad position needs separate source resolution')
        by[carrier]['facts']['birth_date']=wanted[pid]['source_person']['birth_date']
    return result


def rating_and_role_decisions(base,package,prepared,jug):
    result=provisional(package,prepared);by={p['carrier_id']:p for p in result['players']}
    old={p['carrier_id']:p for p in package['players']}
    mapping=dict(prepared['retained_Arsenal'])
    mapping.update({r['replacement']['source_person']['source_player_id']:r['carrier_id']
        for r in prepared['replacements'] if old[r['carrier_id']]['club_id']=='english-club-309'})
    preserved={carrier:carrier for _,carrier in prepared['retained_Arsenal']}
    preserved.update({mapping[pid]:carrier for pid,carrier in prepared['moved_into_Arsenal']})
    fifa_sha=registry.sha256_file(ratings.old.FIFA)
    index=ratings.old.fifa_index(fifa_sha);expanded=ratings.by_dob(fifa_sha)
    role_index={key:[dict(row,player_positions=row['positions'],fifa_update_date=row['date']) for row in rows]
        for key,rows in expanded.items()}
    layer=registry.ROOT/'.local/season-english-preseason-rating-policy-v4/2021-22/english-rating-audit.json'
    strengths=ratings.old.english_strengths(layer)
    divisions={ratings.old._club_key(r['club']):r['current_division'] for r in pipeline.read_json_file(layer)['club_strengths']}
    clubs={c['id']:c for c in package['clubs']}
    starters=set(prepared['ordered_Arsenal_carriers'][:11]);decisions=[]
    targets=selected_carriers(dict(assignment=prepared))|set(preserved)
    for carrier in sorted(targets):
        p=by[carrier];broad=p['facts']['primary_position']
        if carrier in preserved:
            original=old[preserved[carrier]];actual=skills(jug,preserved[carrier])
            if original['ratings']['values']!=actual:raise ValueError('preserved recipe/native skills already disagree')
            profile=copy.deepcopy(original['ratings']);basis=dict(method='preserve-existing-person-ten-native-skills',
                original_carrier=preserved[carrier],native_skills=actual)
            roles=original['facts']['fine_roles']
            if not isinstance(roles,list) or not roles or not exact_roles.compatible(broad,roles[0]):
                raise ValueError('existing represented actor lacks compatible declared fine roles')
            role_basis=dict(method='preserve-existing-source-bound-person-roles')
        else:
            matched=ratings.match(p,2021,index,expanded)
            if matched:
                values=ratings.old.fifa_values(matched,2021,broad)
                method='identity-DOB-target-edition-FIFA-v3'
                basis=dict(method=method,player_id=matched['player_id'],edition=matched['edition'],date=matched['date'])
            else:
                club=clubs[p['club_id']];key=ratings.old._club_key(club['name']);group=roster.club_group(club)
                if group=='england' and key in strengths:
                    strength=round(60+(strengths[key]-60)*.8)
                    if key in divisions:
                        low,high=ratings.DIVISION_BOUNDS[divisions[key]];strength=max(low,min(high,strength))
                    origin='source-prior-table-ability-scale'
                else:
                    tier=ratings.old.inputs.COUNTRY_STRENGTH.get(group,60)
                    prior=[x['ratings']['values']['quality'] for x in package['players'] if x['club_id']==p['club_id']]
                    strength=max(tier-12,min(tier+12,round(median(prior))))
                    origin='explicit-native-club-prior-country-bounded-editorial-estimate'
                state='starting_xi' if carrier in starters else 'opening_squad'
                values=ratings.editorial(p,strength,state,date(2021,8,1))
                method='identity-club-role-age-optional-editorial-calibration-v3'
                basis=dict(method=method,club_strength=strength,club_strength_method=origin,opening_status=state)
            if broad!='G':values['handling']=max(1,min(20,values['handling']))
            profile=dict(profile='pm99-visible-skills-v1',values=values,
                provenance=dict(method=method,proof_grade='reviewed-editorial',source_ids=[ratings.SOURCE_ID]))
            match=exact_roles.match(p,'2021-22',role_index)
            labels=match['player_positions'].split(', ') if match else []
            roles=list(dict.fromkeys(ROLE_MAP[label] for label in labels)) if labels and all(l in ROLE_MAP for l in labels) else []
            if roles and exact_roles.compatible(broad,roles[0]):role_basis=dict(method='exact-target-edition-FIFA-roles',source=match)
            else:
                roles=[{'G':0,'D':4,'M':9,'F':12}[broad]]
                role_basis=dict(method='explicit-editorial-broad-class-default',
                    rejected_incompatible_or_missing_exact_source=match)
        decisions.append(dict(carrier_id=carrier,ratings=profile,rating_basis=basis,fine_roles=roles,
            role_basis=role_basis,preserved_source_carrier=preserved.get(carrier)))
    if len(decisions)!=29 or len(preserved)!=16:raise ValueError('exact29 selected/16 preserved skill profiles required')
    bindings=[assignment.source.bound(p) for p in (ratings.old.FIFA,layer,
        registry.ROOT/'scripts/season_rating_calibration_v3.py',registry.ROOT/'scripts/season_rating_calibration_v1.py',
        registry.ROOT/'scripts/season_exact_fifa_role_delta_v1.py')]
    return decisions,bindings


def prepare(base):
    if base.season!='2021-22':raise ValueError('this original source is Arsenal2021 only')
    prepared=assignment.prepare(base)
    original=pipeline.read_json_file(assignment.source.arsenal.ROOT/'native-assignment-preparation.json')
    if prepared!=original:raise ValueError('original fitted assignment changed')
    package=pipeline.read_json_file(base.package_path)
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    decisions,bindings=rating_and_role_decisions(base,package,prepared,jug)
    return dict(schema=SCHEMA,season=base.season,release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=digest(jug),eq_sha256=digest(eq),
        assignment=prepared,player_decisions=decisions,policy_bindings=bindings,
        implementation=assignment.source.bound(registry.ROOT/'scripts/season_arsenal_2021_owned_opening_v1.py'),
        scope='Arsenal25 startup/order/formation/contextual phases;17 sourced identity slots; two retained DOBs;16 represented people ten skills preserved. Four paired reserve identities; no manager/kit/EXE changes; unrelated records/files exact.')


def verify(base,plan):
    if plan.get('schema')!=SCHEMA or prepare(base)!=plan:raise ValueError('Arsenal original source transaction does not reproduce')


def native_display_names(base,players,carriers):
    """Predict exact native casing through the writer, not string heuristics."""
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
    result={}
    for carrier in carriers:
        raw=entries[carrier].decode_payload(jug)
        current=delta.compiler._player_name(raw,record_id=carrier)
        desired=players[carrier]['name']
        if current.casefold()!=desired.casefold():
            raw,_=delta.compiler._patch_indexed_player_variable_name_payload(raw,current,desired)
        native=read_initial_order(raw).name
        if native.casefold()!=desired.casefold():raise ValueError('predicted native full name differs from sourced display')
        result[carrier]=native
    return result


def bind(package,plan):
    baseline=registry.load_registered_release(plan['season'],plan['release_id'])
    if registry.sha256_file(baseline.package_path)!=plan['package_sha256'] or pipeline.read_json_file(baseline.package_path)!=package:
        raise ValueError('Arsenal recipe preimage differs')
    prepared=plan['assignment'];result=provisional(package,prepared)
    by={p['carrier_id']:p for p in result['players']}
    aid=PREFIX+plan['season']
    for row in plan['player_decisions']:
        p=by[row['carrier_id']];p['ratings']=copy.deepcopy(row['ratings'])
        if row['carrier_id'] in selected_carriers(plan):p['facts']['fine_roles']=copy.deepcopy(row['fine_roles'])
    club=next(c for c in result['clubs'] if c['carrier_id']==309)
    ordered=prepared['ordered_Arsenal_carriers']
    native_names=native_display_names(baseline,by,ordered)
    club['roster_player_ids']=[by[c]['id'] for c in ordered]
    opening=club['opening'];opening.update(fixture_date='2021-08-13',formation='4-2-3-1',
        starting_xi_player_ids=[by[c]['id'] for c in ordered[:11]],
        substitute_player_ids=[by[c]['id'] for c in ordered[11:20]],proof=dict(artifact_id=aid,grade='source-receipt'),
        tactics_positions=[list(anchor[1:]) for anchor in rollout.formation_template('4-2-3-1')])
    offsets=rollout.movement_offsets((registry.ROOT/'.local/visual-qa-20261003/native-source/EQ98030.FDI').read_bytes())
    context=rollout.build_context(club,{p['id']:p for p in result['players']},
        [(c,native_names[c]) for c in ordered[:11]],offsets)
    opening.update(tactics_context=context,tactics_positions=tactics.summary_positions(context))
    for pid,c in prepared['retained_Arsenal']:
        before=next(p for p in package['players'] if p['carrier_id']==c)
        if before['facts']['birth_date']!=by[c]['facts']['birth_date']:by[c]['proof']=dict(artifact_id=aid,grade='source-receipt')
    composition_plan=composition(package,prepared)
    artifact=next(a for a in result['artifacts'] if a.get('relative_path')==delta.plan_filename(composition_plan))
    old_id=artifact['id'];artifact.update(id=aid,relative_path=FILENAME,sha256=digest(packages.canonical_json_bytes(plan)))
    for p in result['players']:
        if p.get('proof',{}).get('artifact_id')==old_id:p['proof']['artifact_id']=aid
        for f in p.get('fact_fallbacks',[]):
            if f.get('proof',{}).get('artifact_id')==old_id:f['proof']['artifact_id']=aid
    for row in result['assets']['portraits']:
        if row.get('proof',{}).get('artifact_id')==old_id:row['proof']['artifact_id']=aid
    for collection in ('sources','proofs'):
        for row in result[collection]:
            for key in ('artifact_id','evidence_artifact_id'):
                if row.get(key)==old_id:row[key]=aid
    result['artifacts'].sort(key=lambda a:a['id']);packages.validate_package(result)
    return result


def apply(jug,eq,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    original_eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if (digest(original),digest(original_eq))!=(plan['jug_sha256'],plan['eq_sha256']):raise ValueError('Arsenal immutable native baseline differs')
    package=bind(pipeline.read_json_file(base.package_path),plan)
    by={p['carrier_id']:p for p in package['players']}
    prepared=original
    for row in plan['assignment']['replacements']:
        if row.get('same_carrier_name_capacity'):
            prepared,claim=capacity.recover_slot(prepared,row['carrier_id'],plan['assignment']['same_carrier_capacity'])
            if claim!=row['same_carrier_name_capacity']:raise ValueError('Arsenal paired name capacity does not reproduce')
    countries=delta.compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    changed=selected_carriers(plan)
    candidate=delta.compile_players(prepared,package,{by[c]['id'] for c in changed},countries)
    baseline_players={p['carrier_id']:p for p in pipeline.read_json_file(base.package_path)['players']}
    initial_entries={e.record_id:e for e in IndexedFDIFile.from_bytes(candidate).entries}
    dates={c:dict(native_name=roster.native_player(initial_entries[c].decode_payload(candidate),c)['name'],
        before_birth_date=baseline_players[c]['facts']['birth_date'],birth_date=by[c]['facts']['birth_date'])
        for _,c in plan['assignment']['retained_Arsenal']
        if by[c]['facts']['birth_date']!=baseline_players[c]['facts']['birth_date']}
    candidate,_=rewrite_indexed_native_birth_dates(candidate,dates)
    ix=IndexedFDIFile.from_bytes(candidate);entries={e.record_id:e for e in ix.entries}
    order=plan['assignment']['ordered_Arsenal_carriers']
    rows=[]
    for n,c in enumerate(order,1):
        raw=entries[c].decode_payload(candidate);end=roster.native_player(raw,c)['name_end']
        field=read_initial_order(raw)
        if field.name.casefold()!=by[c]['name'].casefold():raise ValueError('actual order target full name differs')
        rows.append(dict(native_player_id=c,native_name=field.name,before=field.order,after=n))
    candidate=ordering.apply_layer(original_eq,candidate,dict(schema_version=ordering.SCHEMA,
        clubs=[dict(carrier_id=309,players=rows)]),allow_compact=True)
    e=next(e for e in IndexedFDIFile.from_bytes(original_eq).entries if e.record_id==309)
    raw=original_eq[e.payload_offset:e.payload_offset+e.payload_length]
    parsed=delta.compiler.parse_eq_external_team_roster_payload(raw,{})
    if parsed is None or parsed.mode_byte!=0 or {r.player_record_id for r in parsed.rows}!=set(order) or any(r.flag for r in parsed.rows):
        raise ValueError('Arsenal original native roster is not exact exclusive mode0 capacity25')
    roster_eq=delta.compiler._rebuild_indexed(original_eq,IndexedFDIFile.from_bytes(original_eq),
        {309:xor_decode(delta.compiler._rewrite_roster_tail(raw,order))})
    club=next(c for c in package['clubs'] if c['carrier_id']==309)
    candidate_eq=tactics.apply_layer(roster_eq,candidate,dict(schema_version=tactics.SCHEMA,
        clubs=[dict(carrier_id=309,context=club['opening']['tactics_context'])]))
    preserve_other_records(original,candidate,set(order)|changed)
    preserve_other_records(original_eq,candidate_eq,{309})
    for row in plan['player_decisions']:
        if skills(candidate,row['carrier_id'])!=row['ratings']['values']:raise ValueError('Arsenal final actual ten-skill readback differs')
    if (jug,eq) not in ((original,original_eq),(candidate,candidate_eq)):
        raise ValueError('Arsenal transaction accepts only exact pre/postimages')
    return candidate,candidate_eq


def reconstruction(previous,release_id):
    receipt_path=getattr(previous,'compiler_receipt_path',None)
    if receipt_path is None:return None
    receipt=pipeline.read_json_file(receipt_path)
    if receipt.get('compilation_mode')!=MODE:return None
    from scripts import publish_historical_role_delta_v1 as publisher
    path=registry.ROOT/previous.locator['sourced_profile_assignment_plan_path'];plan=pipeline.read_json_file(path)
    base=registry.load_registered_release(previous.season,plan['release_id']);verify(base,plan)
    package=pipeline.read_json_file(previous.package_path)
    artifact=next(a for a in package['artifacts'] if a['id']==PREFIX+previous.season)
    if path.resolve()!=(previous.package_path.parent/FILENAME).resolve() or registry.sha256_file(path)!=artifact['sha256']:
        raise ValueError('Arsenal source artifact changed')
    if bind(pipeline.read_json_file(base.package_path),plan)!=package:raise ValueError('edited Arsenal recipe cannot be silently reconstructed')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    expected=dict(season=previous.season,release_id=base.release_id,package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'],updates=[],unresolved=[])
    if pipeline.read_json_file(descriptor)!=expected:raise ValueError('Arsenal reconstruction descriptor differs')
    for release in (base,previous):pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,
        profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path)!=package:raise ValueError('complete Arsenal SOURCE recipe differs')
    return dict(season=previous.season,release_id=release_id,complete_game_inventory_identical=True,
        complete_recipe_identical=True,reused=False,compilation_mode=MODE)
