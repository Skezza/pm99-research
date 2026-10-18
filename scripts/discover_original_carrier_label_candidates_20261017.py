"""Read-only all-season discovery using entire source-authored club cohorts.

This is nomination, never manager/ground/kit/roster or native-write authority.
Do not confuse unavailable authored provenance with a confirmed club bug.
"""
from collections import defaultdict
from datetime import UTC,datetime
from scripts import season_original_carrier_label_restoration_v1 as policy
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def scan():
    rows=[];releases=[]
    for season in policy.registry.supported_seasons():
        base=policy.registry.load_preferred_release(season)
        package=policy.pipeline.read_json_file(base.package_path)
        aid='opening-squad-preallocation-'+season
        descriptors=[a for a in package['artifacts'] if a['id']==aid]
        pre=policy.registry.ROOT/'.local/transfermarkt-opening-plans-current-v1'/season/'opening-squad-preallocation.json'
        fixed=policy.registry.ROOT/'seasons'/season/'fixed-carrier-registry.json'
        releases.append(dict(season=season,release_id=base.release_id,manifest_sha256=base.manifest_sha256))
        if len(descriptors)!=1 or not pre.exists() or not fixed.exists():
            rows.append(dict(season=season,state='source-or-registry-unavailable-not-confirmed-fault'));continue
        if policy.registry.sha256_file(pre)!=descriptors[0]['sha256']:
            raise ValueError('current recipe and source preallocation differ: '+season)
        registry=policy.pipeline.read_json_file(fixed)
        if registry['schema_version']!='pm99-world-fixed-carrier-registry-v2':
            raise ValueError('unexpected original fixed registry schema: '+season)
        originals={r['carrier_id']:r for r in registry['carriers']}
        index,sources=policy.old.indexed_claims(policy.pipeline.read_json_file(pre))
        people=defaultdict(list)
        for p in package['players']:people[p['club_id']].append(p)
        for club in package['clubs']:
            original=originals.get(club['carrier_id'])
            if not original or original['record_mode']!=1:continue
            try: source=policy.cohort_source(club,people[club['id']],aid,index,sources)
            except ValueError:continue  # Not positive evidence, never a wrong-club verdict.
            target=source['selector']['club_name']
            normalise=policy.old.builder._normalise_club_name
            if normalise(target)==normalise(club['name']):continue
            rows.append(dict(season=season,carrier_id=club['carrier_id'],club_id=club['id'],
                current_name=club['name'],unanimous_source_name=target,represented_players=len(people[club['id']]),
                original_carrier_name=original['baseline_club']['name'],source_selector=source['selector'],
                original_registry_agrees=normalise(target)==normalise(original['baseline_club']['name']),
                another_target_label_present=any(c['id']!=club['id'] and normalise(c['name'])==normalise(target)
                    and policy.old.roster.club_group(c)==policy.old.roster.club_group(club) for c in package['clubs']),
                state='unanimous-original-source-label-candidate-not-native-or-historical-approval',
                source_input=policy.bind(pre),original_registry=policy.bind(fixed)))
    return dict(schema='pm99-all26-unanimous-original-carrier-label-candidate-discovery-v1',
        utc=datetime.now(UTC).isoformat(),machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',bindings=releases,candidates=rows,
        nominated_label_candidates=sum('carrier_id' in r for r in rows),native_writes=0,
        requires_dated_fixture_manager_ground_duplicate_and_native_checks=True,
        frozen_case_dispositions_changed=0,global_historical_RC=False)


if __name__=='__main__':
    destination=policy.registry.ROOT/'.local/consolidated-audit-20261009/original-carrier-label-restoration-20261017/all26-cohort-label-candidates-v90.json'
    if destination.exists():raise ValueError('existing discovery needs inspection, not regeneration')
    result=scan();retained(destination,result)
    print(dict(seasons=len(result['bindings']),candidates=result['nominated_label_candidates'],native_writes=0),flush=True)
