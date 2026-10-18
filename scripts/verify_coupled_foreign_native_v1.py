"""Independent native/identity readback of the private source-bound19-player delta."""
from pathlib import Path
import tempfile

from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import prepare_ofk_2015_verified_inputs_v1 as inputs
from scripts import prepare_duplicate_whole_club_native_v1 as native
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_published_person_identity_v1 as people
from scripts import audit_published_player_identities_v1 as identities
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts.verify_paired_club_identity_v1 import groups
from app.fdi_indexed import IndexedFDIFile
from app.editor_actions import _read_native_dd6360_fields
from app.player_initial_order import read_initial_order
from app.ent_manager_profiles import parse_indexed_ent_manager_profile


def verify(candidate,output, *, source_bound_game=False):
    if output.exists():raise ValueError('coupled native readback evidence is immutable')
    receipt_path=candidate/('candidate-receipt.json' if source_bound_game else 'native-proof.json')
    receipt=pipeline.read_json_file(receipt_path)
    if receipt.get('registered') or receipt.get('publication_authorised'):
        raise ValueError('private coupled candidate falsely claims delivery')
    path=registry.ROOT/receipt['source_plan']['path']
    if registry.sha256_file(path)!=receipt['source_proposal_sha256']:
        raise ValueError('coupled foreign original source proposal changed')
    proposal=pipeline.read_json_file(path)
    if source_bound_game:
        from scripts import season_foreign_fixed_roster_delta_v1 as foreign
        if receipt['schema_version']!=foreign.SCHEMA or registry.sha256_file(candidate/foreign.FILENAME)!=receipt['plan_sha256']:
            raise ValueError('coupled complete-game descriptor changed')
        foreign.verify_plan(pipeline.read_json_file(candidate/foreign.FILENAME))
    with tempfile.TemporaryDirectory(prefix='pm99-coupled-native-readback-') as temporary:
        if inputs.prepare(Path(temporary)/'source.json')!=proposal:
            raise ValueError('coupled source claims do not reparse from originals')
    baseline=registry.load_registered_release('2015-16',receipt['baseline_release_id'])
    package=pipeline.read_json_file(candidate/'season-package.json')
    if registry.sha256_file(candidate/'season-package.json')!=receipt['recipe_sha256']:
        raise ValueError('coupled native recipe changed')
    native.package_v2.validate_package(package)
    data={}
    for name,sha in receipt['native_hashes'].items():
        data_root=candidate/('game/DBDAT' if source_bound_game else 'DBDAT')
        if registry.sha256_file(data_root/name)!=sha or registry.sha256_file(baseline.game_path/'DBDAT'/name)!=receipt['before_hashes'][name]:
            raise ValueError('coupled native input/output hash changed')
        data[name]=(data_root/name).read_bytes()
    players={p['carrier_id']:p for p in package['players']}
    corrected=set(receipt['detail']['corrected_native_carriers'])
    original=pipeline.read_json_file(baseline.package_path)
    if any(players[p['carrier_id']]!=p for p in original['players'] if p['carrier_id'] not in corrected):
        raise ValueError('coupled source changed an unselected recipe person')
    wanted={r['carrier_id']:r for r in proposal['allocation']}
    wanted.update({r['carrier_id']:r for r in proposal['coupled_Celta_allocation']+proposal['coupled_OFK_transferred_allocation']})
    if set(wanted)!=corrected or len(corrected)!=19:raise ValueError('coupled corrected native carrier set differs')
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(data['JUG98030.FDI']).entries}
    codes=native.delta.compiler._extract_country_codes_from_textos(baseline.game_path/'DBDAT/TEXTOS.PKF')
    readbacks=[]
    for id,row in sorted(wanted.items()):
        player=players[id];desired=row['replacement'];person=desired['source_person'];facts=desired['source_player']
        raw=entries[id].decode_payload(data['JUG98030.FDI'])
        actual=native.source.roster.native_player(raw,id)
        field=_read_native_dd6360_fields(raw,actual['name_end'])
        date=f"{field['birth_year']:04d}-{field['birth_month']:02d}-{field['birth_day']:02d}"
        if (player['source_name']!=person['name'] or player['person_id']!='person-transfermarkt-'+str(person['source_player_id'])
                or player['name']!=row['display']['display_name'] or actual['name'].casefold()!=player['name'].casefold()
                or date!=person['birth_date'] or player['facts']['birth_date']!=date
                or actual['position']!=facts['position'] or {r for r in actual['roles'] if r!=98}!=set(player['facts']['fine_roles'])
                or field['visible_nationality_code']!=native.delta.compiler._country_code(facts['nationality'],dict(codes))
                or field['skills']!=[player['ratings']['values'][k] for k in native.delta.compiler.SKILLS]
                or field['handling']!=player['ratings']['values']['handling']
                or (isinstance(facts.get('height_cm'),int) and field['height_cm']!=facts['height_cm'])):
            raise ValueError('actual coupled biography/name/role/nationality/skills differs from source recipe')
        readbacks.append(dict(carrier_id=id,source_player_id=person['source_player_id'],source_name=person['name'],
            club_id=player['club_id'],native_name=actual['name'],birth_date=date,position=actual['position'],
            startup_order=read_initial_order(raw).order,skills=field['skills'],handling=field['handling']))
    rosters={};owners={}
    for e in IndexedFDIFile.from_bytes(data['EQ98030.FDI']).entries:
        raw=data['EQ98030.FDI'][e.payload_offset:e.payload_offset+e.payload_length]
        roster=native.parse_eq_external_team_roster_payload(raw,{})
        if roster is None:
            if len(raw)>=600 and raw[0x29] in (0,1):raise ValueError('unreadable native roster prevents ownership readback')
            continue
        rosters[e.record_id]=roster
        for row in roster.rows:owners.setdefault(row.player_record_id,set()).add(e.record_id)
    target=next(c for c in package['clubs'] if c['carrier_id']==706)
    ordered=[next(p['carrier_id'] for p in package['players'] if p['id']==id) for id in target['roster_player_ids']]
    source_ids=[next(r['source_player_id'] for r in readbacks if r['carrier_id']==id) for id in ordered]
    if (len(ordered)!=18 or source_ids!=[r['source_person']['source_player_id'] for r in proposal['desired_people']]
            or [r.player_record_id for r in rosters[706].rows]!=ordered or any(r.flag for r in rosters[706].rows)
            or [read_initial_order(entries[id].decode_payload(data['JUG98030.FDI'])).order for id in ordered]!=list(range(1,19))
            or any(owners[id]!={706} for id in ordered)
            or rosters[706].short_name!='OFK Beograd' or rosters[706].stadium_name!=proposal['dated_manager_ground']['ground']):
        raise ValueError('native actual OFK18/XI/source order/ownership/ground differs')
    old_eq=(baseline.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    e=next(e for e in IndexedFDIFile.from_bytes(old_eq).entries if e.record_id==48)
    old_celta=native.parse_eq_external_team_roster_payload(old_eq[e.payload_offset:e.payload_offset+e.payload_length],{})
    outgoing=proposal['coupled_native_carrier_exchange']['OFK_to_Celta']
    expected=[(r.flag,outgoing if r.player_record_id==5468 else r.player_record_id) for r in old_celta.rows]
    if ([(r.flag,r.player_record_id) for r in rosters[48].rows]!=expected or owners[outgoing]!={48}
            or len(rosters[48].rows)!=25 or players[outgoing]['club_id']!='club-48'
            or next(r for r in readbacks if r['carrier_id']==outgoing)['source_player_id']!=21297):
        raise ValueError('native Celta fixed carrier exchange/availability/ownership differs')
    manager=next(m for m in package['managers'] if m['id']==target['manager_id'])
    e=next(e for e in IndexedFDIFile.from_bytes(data['ENT98030.FDI']).entries if e.record_id==manager['carrier_id'])
    profile=parse_indexed_ent_manager_profile(data['ENT98030.FDI'][e.payload_offset:e.payload_offset+e.payload_length],record_id=manager['carrier_id'])
    if profile.display_name!='Petrovic' or profile.surname!='Petrovic' or manager['name']!='Vladimir Petrovic':
        raise ValueError('native OFK manager differs from dated original')
    for name,ids in [('JUG98030.FDI',corrected),('EQ98030.FDI',{48,706}),('ENT98030.FDI',{manager['carrier_id']})]:
        native.preserve_other_records((baseline.game_path/'DBDAT'/name).read_bytes(),data[name],ids)
    cleared,_=native.delta.no_photo_archive(data['MINIFOTO.PKF'],corrected)
    if cleared!=data['MINIFOTO.PKF']:raise ValueError('coupled displaced portrait remains')
    if source_bound_game and any((candidate/'game/DBDAT/MINIFOTO'/f'J96{id:05d}.BMP').exists() for id in corrected):
        raise ValueError('coupled displaced loose portrait remains')
    index,snapshot=identities.load_identity_snapshot()
    for filename in ['ofk-2015-original-person-identities-v1.json','celta-2015-madinda-original-person-v1.json']:
        index,review=people.merge(index,pipeline.read_json_file(source.AUDIT/filename))
        if review['refused']:raise ValueError('coupled biographies conflict with pinned identities')
    merged_before={};merged_after={}
    for _,layer,layer_path in planner.package_layers(baseline):
        merged_before.update({p['carrier_id']:p for p in layer['players']})
        chosen=package if layer_path==baseline.package_path else layer
        merged_after.update({p['carrier_id']:p for p in chosen['players']})
    old=groups({'players':list(merged_before.values())},index)
    new=groups({'players':list(merged_after.values())},index)
    if new.keys()-old.keys() or any(any(id in corrected for id,_ in rows) for rows in new.values()):
        raise ValueError('coupled transaction introduces or retains an outside duplicate person')
    proof=dict(schema_version='pm99-private-coupled-foreign-independent-native-v1',season='2015-16',
        candidate_receipt_sha256=registry.sha256_file(receipt_path),
        source_bound_complete_game=source_bound_game,native_hashes=receipt['native_hashes'],
        package_sha256=registry.sha256_file(candidate/'season-package.json'),players=readbacks,
        original_sources_replayed=True,all19_native_identities_and_skills_read_back=True,
        OFK_XI_and_complete18_source_order_verified=True,Celta_fixed25_availability_preserved=True,
        all_unselected_native_records_identical=True,all_unselected_recipe_players_identical=True,
        before_cross_club_groups=len(old),after_cross_club_groups=len(new),introduced_candidate_groups=0,
        replacement_cross_club_candidates=0,identity_snapshot=snapshot,stale_archive_portraits_cleared=True,
        stale_portraits_cleared=source_bound_game,
        native_manager='Petrovic',native_ground=rosters[706].stadium_name,
        registered=False,runtime_verified=False,publication_authorised=False,
        limitations=['Celta XI and opaque foreign tactics not historically certified.',
            'Rounded annual heights, preserved unsourced weights; Cancarevic nationality chronology inference declared.',
            'Kit assets, loose-portrait cleanup, complete replay and genuine runtime not yet proved.'])
    pipeline.write_canonical_json(output,proof)
    return proof


if __name__=='__main__':
    x=verify(source.AUDIT/'ofk-2015-celta-private-native-v2',source.AUDIT/'ofk-2015-celta-independent-native-v2.json')
    print(dict(people=len(x['players']),introduced=x['introduced_candidate_groups'],registered=False),flush=True)
