"""Build the actual paired Woking/Oxford correction and full SOURCE replay."""
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_woking_2003_owned_opening_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_historical_roster_audit_v1 as roster
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from app.fdi_indexed import IndexedFDIFile

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/woking-owned-opening-v1'
SEASON='2003-04'
BASE='sourced-monagas-opening-20261011-r87a'
RELEASE='sourced-woking-owned-opening-20261011-r98a'
REPLAY='replayed-woking-owned-opening-20261011-r98b'


def skills(data,carrier):
    entry=next(e for e in IndexedFDIFile.from_bytes(data).entries if e.record_id==carrier)
    raw=entry.decode_payload(data)
    if raw[2:5]==bytes.fromhex('dd6360'):
        fields=delta.compiler._read_native_dd6360_fields(raw,roster.native_player(raw,carrier)['name_end'])
        return dict(zip(delta.compiler.SKILLS,fields['skills']),handling=fields['handling'])
    if raw[2:5]!=bytes.fromhex('dd6361'):raise ValueError('unproved native skill family')
    return dict(zip(delta.compiler.SKILLS,[b^0x61 for b in raw[-16:-7]]),handling=raw[-7]^0x61)


def native_proof(base,release,plan):
    original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    ent=(base.game_path/'DBDAT/ENT98030.FDI').read_bytes()
    actual=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    actual_eq=(release.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    actual_ent=(release.game_path/'DBDAT/ENT98030.FDI').read_bytes()
    if source.apply(original,eq,plan)!=(actual,actual_eq) or source.apply_ent(ent,plan)!=actual_ent:
        raise ValueError('actual native paired correction differs')
    if source.apply(actual,actual_eq,plan)!=(actual,actual_eq) or source.apply_ent(actual_ent,plan)!=actual_ent:
        raise ValueError('actual native paired correction is not idempotent')
    before=pipeline.read_json_file(base.package_path);after=pipeline.read_json_file(release.package_path)
    if after!=source.bind(before,plan):raise ValueError('actual recipe differs')
    old={roster.normalise(p.get('source_name') or p['name']):p for p in before['players']
         if p['club_id']=='club-3321' or p['carrier_id']==33060}
    preserved=[]
    for p in after['players']:
        if p['club_id']!='club-3321':continue
        person=old.get(roster.normalise(p['source_name']))
        if person and person['facts']['birth_date']==p['facts']['birth_date']:
            left=skills(original,person['carrier_id']);right=skills(actual,p['carrier_id'])
            if left!=right or right!=p['ratings']['values']:raise ValueError('retained/moved person native skills changed')
            preserved.append(dict(person=p['source_name'],old_carrier=person['carrier_id'],new_carrier=p['carrier_id'],skills=right))
    if len(preserved)!=10:raise ValueError('expected nine residents and Louis native skill preservation')
    selected=source.selected_carriers(plan)
    archive,_=delta.no_photo_archive((base.game_path/'DBDAT/MINIFOTO.PKF').read_bytes(),selected)
    if archive!=(release.game_path/'DBDAT/MINIFOTO.PKF').read_bytes():raise ValueError('portrait clear differs')
    if any((release.game_path/f'DBDAT/MINIFOTO/J96{k:05d}.BMP').exists() for k in selected):raise ValueError('stale slot portrait remains')
    left={r['path']:r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    right={r['path']:r['sha256'] for r in pipeline.read_json_file(release.inventory_path)['files']}
    allowed={'DBDAT/JUG98030.FDI','DBDAT/EQ98030.FDI','DBDAT/ENT98030.FDI','DBDAT/MINIFOTO.PKF'}|{f'DBDAT/MINIFOTO/J96{k:05d}.BMP' for k in selected}
    if any(left.get(k)!=right.get(k) for k in set(left)|set(right) if k not in allowed):raise ValueError('unrelated game file changed')
    retained(ROOT/'native-byte-proof.json',dict(season=SEASON,release_id=RELEASE,baseline=BASE,
        package_sha256=registry.sha256_file(release.package_path),plan_sha256=registry.sha256_file(ROOT/'opening-ownership-plan.json'),
        changed_carriers=sorted(selected),exact_native_reproduction_from_sources=True,idempotent=True,
        all_unrelated_native_records='byte-identical',all_unrelated_game_files='byte-identical',
        Oxford_roster_count_and_XI_preserved=True,Woking_count=16,original_first_XI_retained=True,
        only_manager_changed=818,all_ten_native_skills_preserved_for=preserved,
        exact_portrait_clear=True,opaque_tactic_bytes_preserved=True,
        secondary_facts='source composer values or explicit logged fallbacks; no secondary-fact approval',
        kit='native kit preserved; not historical Woking kit approval'))


def main():
    ROOT.mkdir(exist_ok=True);base=registry.load_registered_release(SEASON,BASE)
    path=ROOT/'opening-ownership-plan.json'
    if path.exists():plan=pipeline.read_json_file(path)
    else:plan=source.prepare(base);retained(path,plan)
    descriptor=ROOT/'inert.json'
    retained(descriptor,dict(season=SEASON,release_id=BASE,package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),updates=[],unresolved=[]))
    if not registry.locator_path(SEASON,RELEASE).exists():
        publisher.publish(SEASON,descriptor,release_id=RELEASE,source_release_id=BASE,profile_assignment_plan_path=path)
    release=registry.load_registered_release(SEASON,RELEASE)
    if not (ROOT/'native-byte-proof.json').exists():native_proof(base,release,plan)
    if not (ROOT/'complete-SOURCE-replay.json').exists():
        if registry.locator_path(SEASON,REPLAY).exists():raise ValueError('unreceipted Woking replay exists')
        retained(ROOT/'complete-SOURCE-replay.json',source.reconstruction(release,REPLAY))
    print(dict(built=True,complete_SOURCE_game_and_recipe_exact=True,runtime_pending=True),flush=True)


if __name__=='__main__':main()
