"""Build/capture the nine exact-edition seasons, keeping all other games fixed."""
import os
import shutil
import time
from pathlib import Path
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_exact_fifa_role_delta_v2 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.capture_city_opening_exchange_20261011 import captured
from scripts import capture_registered_season_runtime_v1 as capture
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/exact-fifa-roles-20261015-v2'
SEASONS = tuple(f'{y}-{str(y+1)[-2:]}' for y in range(2014,2023))
RELEASE = 'sourced-exact-fifa-roles-20261015-r104a'
REPLAY = 'replayed-exact-fifa-roles-20261015-r104b'
PROFILES = (('2014-15',9254,'pieters','Pieters'),('2014-15',9278,'wilkinson','Wilkinson'),
            ('2015-16',1790,'messi','Messi'))


def tag(season):
    return 'exact_fifa_roles_' + season.replace('-','_') + '_r104a_20261015'


def build(season, *, batch_root=ROOT, release_id=RELEASE, replay_id=REPLAY, source_module=source,
          require_preferred=True, allow_declared_country_bytes=False):
    RELEASE=release_id;REPLAY=replay_id;source=source_module
    root = batch_root / season
    root.mkdir(parents=True, exist_ok=True)
    if (root/'complete-SOURCE-replay.json').exists():
        print(dict(season=season,reused_complete_build=True),flush=True)
        return
    pin = pipeline.read_json_file(batch_root/'baseline.json')
    row = next(r for r in pin if r['season']==season)
    base = registry.load_registered_release(season,row['release_id'])
    if require_preferred and registry.load_preferred_release(season).release_id!=base.release_id:
        raise ValueError('role baseline moved outside owned batch')
    if shutil.disk_usage(root).free < 8.3*1024**3:
        raise ValueError('role build stops before8GiB reserve is threatened')
    path = root/'role-plan.json'
    if path.exists():
        plan=pipeline.read_json_file(path)
    else:
        plan=source.prepare(base)
        if not plan['updates']:raise ValueError('no exact-source role corrections')
        retained(path,plan)
    inert=root/'inert.json'
    retained(inert,dict(season=season,release_id=base.release_id,package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    if not registry.locator_path(season,RELEASE).exists():
        publisher.publish(season,inert,release_id=RELEASE,source_release_id=base.release_id,
            profile_assignment_plan_path=path,resume_unregistered_assignment=allow_declared_country_bytes)
    actual=registry.load_registered_release(season,RELEASE)
    if not (root/'native-byte-proof.json').exists():
        left=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        right=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
        if source.apply(left,eq,plan)!=(right,eq) or source.apply(right,eq,plan)!=(right,eq):
            raise ValueError('role native patch/replay differs')
        old={e.record_id:e for e in IndexedFDIFile.from_bytes(left).entries}
        new={e.record_id:e for e in IndexedFDIFile.from_bytes(right).entries}
        if allow_declared_country_bytes:
            from scripts import season_package_compiler_v2 as compiler
            countries=compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
        allowed=set();observed=[]
        for update in plan['updates']:
            carrier=update['carrier_id'];a=old[carrier].decode_payload(left);b=new[carrier].decode_payload(right)
            end,roles=read_indexed_native_roles(b,carrier)
            after_roles=update['fine_roles']
            expected=(after_roles+[98]*(6-len(after_roles)) if after_roles is not None
                else update['before_native_roles'])
            country_change=allow_declared_country_bytes and update.get('nationality') is not None
            suffix=end+9 if country_change else end+8
            if roles!=expected or a[:end+2]!=b[:end+2] or a[suffix:]!=b[suffix:]:
                raise ValueError('independent native role-only readback differs')
            if after_roles is not None:
                allowed.update(range(old[carrier].payload_offset+end+2,old[carrier].payload_offset+end+8))
            if country_change:
                expected_country=compiler._country_code(update['nationality'],dict(countries))
                if (b[end+8]^0x61)!=expected_country:
                    raise ValueError('independent declared native nationality readback differs')
                allowed.add(old[carrier].payload_offset+end+8)
            row=dict(carrier_id=carrier,actual_native_roles=roles)
            if allow_declared_country_bytes:
                row.update(actual_native_country=b[end+8]^0x61,nationality=update.get('nationality'))
            observed.append(row)
        if len(left)!=len(right) or any(a!=b and i not in allowed for i,(a,b) in enumerate(zip(left,right))):
            raise ValueError('role-only delta changed another record/directory/unknown byte')
        before={f['path']:f['sha256'] for f in pipeline.read_json_file(base.inventory_path)['files']}
        after={f['path']:f['sha256'] for f in pipeline.read_json_file(actual.inventory_path)['files']}
        if any(before.get(k)!=after.get(k) for k in set(before)|set(after) if k!='DBDAT/JUG98030.FDI'):
            raise ValueError('role edit changed an unrelated game file')
        if source.bind(pipeline.read_json_file(base.package_path),plan)!=pipeline.read_json_file(actual.package_path):
            raise ValueError('role recipe reconstruction differs')
        retained(root/'native-byte-proof.json',dict(season=season,release_id=RELEASE,baseline=base.release_id,
            manifest_sha256=actual.manifest_sha256,plan_sha256=registry.sha256_file(path),
            jug_sha256=registry.sha256_file(actual.game_path/'DBDAT/JUG98030.FDI'),
            corrected_players=len(observed),rows=observed,all_six_roles_verified=True,
            all_non_role_native_bytes_identical=not allow_declared_country_bytes,all_other_game_files_identical=True,
            recipe_only_fine_roles_and_source_artifact_changed=not allow_declared_country_bytes,
            **(dict(all_non_role_or_declared_country_native_bytes_identical=True,
                recipe_only_selected_roles_declared_countries_fallback_receipts_and_source_artifact_changed=True)
                if allow_declared_country_bytes else {}),full_source_runtime_pending=True))
    if registry.locator_path(season,REPLAY).exists():
        raise ValueError('unreceipted full SOURCE replay exists; inspect before retry')
    retained(root/'complete-SOURCE-replay.json',source.reconstruction(actual,REPLAY))
    replay=registry.load_registered_release(season,REPLAY)
    sharing=[]
    for a,b in ((actual.package_path,replay.package_path),
                (actual.game_path/'DBDAT/JUG98030.FDI',replay.game_path/'DBDAT/JUG98030.FDI')):
        if registry.sha256_file(a)!=registry.sha256_file(b):raise ValueError('owned replay bytes differ')
        if a.stat().st_ino!=b.stat().st_ino:
            temp=b.with_name(b.name+'.verified-link')
            if temp.exists():raise ValueError('unreceipted sharing temporary exists')
            os.link(a,temp);os.replace(temp,b)
        sharing.append(dict(source=str(a),target=str(b),sha256=registry.sha256_file(b)))
    retained(root/'owned-identical-content-sharing.json',sharing)
    print(dict(season=season,corrected_players=len(plan['updates']),built_SOURCE_exact=True,preferred_unchanged=True),flush=True)


def captures():
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    for season in SEASONS:
        root=ROOT/season;deadline=time.monotonic()+7200
        while not (root/'complete-SOURCE-replay.json').exists():
            if time.monotonic()>deadline:raise ValueError('bounded own build wait expired')
            time.sleep(10)
        release=registry.load_registered_release(season,RELEASE)
        command,evidence=capture.capture_command(season=season,worker='default',run_tag=tag(season),
            compact_evidence=True,release_id=RELEASE)
        captured(command,evidence,root/'startup-transport.json',release,env)
        for s,carrier,label,token in PROFILES:
            if s!=season:continue
            package=pipeline.read_json_file(release.package_path)
            person=next(p for p in package['players'] if p['carrier_id']==carrier)
            target=root/'runtime'/label
            command=[str(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
                '--worker','default','--run-tag',tag(season)+'_'+label,'--local-game-dir',str(release.game_path),
                '--local-artifact-dir',str(target),'--player-search',person['name'],'--player-label',label,
                '--profile-name-token',token,'--profile-only','--provenance-file',str(release.compiler_receipt_path)]
            captured(command,target,root/(label+'-profile-transport.json'),release,env)
        print(dict(season=season,transport_complete=True,original_visual_review_pending=True),flush=True)


if __name__=='__main__':
    import sys
    ROOT.mkdir(parents=True,exist_ok=True)
    if len(sys.argv)>1 and sys.argv[1]=='capture':captures()
    else:
        path=ROOT/'baseline.json'
        if not path.exists():
            retained(path,[dict(season=s,release_id=registry.load_preferred_release(s).release_id) for s in SEASONS])
        for season in SEASONS:build(season)
