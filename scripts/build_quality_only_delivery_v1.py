"""Materialise a narrow quality delta, byte-prove it and replay full SOURCE."""
import os
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_quality_only_delta_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

def deduplicate_owned_replay(base,release,replay,root,plan):
    """Keep all proof/replay paths, sharing only newly produced identical bytes.

    Never modify the baseline or a previous release. Atomic link replacement
    preserves content, registrations and inventories; later publishers already
    use replace-on-write for hardlinked native files.
    """
    pairs=[(release.package_path,replay.package_path),
        (release.game_path/'DBDAT/JUG98030.FDI',replay.game_path/'DBDAT/JUG98030.FDI'),
        (root/'quality-plan.json',release.package_path.parent/source.filename(plan)),
        (root/'quality-plan.json',replay.package_path.parent/source.filename(plan))]
    evidence=[]
    allowed={release.package_path.parent.resolve(),replay.package_path.parent.resolve()}
    for original,target in pairs:
        if not any(target.resolve().is_relative_to(parent) for parent in allowed):raise ValueError('quality dedup target not owned')
        if registry.sha256_file(original)!=registry.sha256_file(target):raise ValueError('quality dedup unequal bytes')
        if original.stat().st_ino!=target.stat().st_ino:
            temporary=target.with_name(target.name+'.verified-link')
            if temporary.exists():raise ValueError('unreceipted dedup temporary')
            os.link(original,temporary);os.replace(temporary,target)
        evidence.append(dict(source=registry.relative_workspace_path(original),target=registry.relative_workspace_path(target),
            sha256=registry.sha256_file(target),content_preserved=True))
    retained(root/'owned-identical-content-sharing.json',evidence)


def build(base,kind,root,release_id,replay_id):
    root.mkdir(parents=True,exist_ok=True)
    path=root/'quality-plan.json'
    if path.exists():plan=pipeline.read_json_file(path)
    else:plan=source.prepare(base,kind);retained(path,plan)
    descriptor=root/'inert.json'
    retained(descriptor,dict(season=base.season,release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),
        updates=[],unresolved=[]))
    if not registry.locator_path(base.season,release_id).exists():
        publisher.publish(base.season,descriptor,release_id=release_id,source_release_id=base.release_id,profile_assignment_plan_path=path)
    release=registry.load_registered_release(base.season,release_id)
    if not (root/'native-byte-proof.json').exists():
        original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
        actual=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        if source.apply(original,eq,plan)!=(actual,eq) or source.apply(actual,eq,plan)!=(actual,eq):
            raise ValueError('actual quality native result/replay/idempotence differs')
        if pipeline.read_json_file(release.package_path)!=source.bind(pipeline.read_json_file(base.package_path),plan):
            raise ValueError('actual quality recipe differs')
        left={f['path']:f['sha256'] for f in pipeline.read_json_file(base.inventory_path)['files']}
        right={f['path']:f['sha256'] for f in pipeline.read_json_file(release.inventory_path)['files']}
        if any(left.get(k)!=right.get(k) for k in set(left)|set(right) if k!='DBDAT/JUG98030.FDI'):
            raise ValueError('quality delta changed an unrelated game file')
        retained(root/'native-byte-proof.json',dict(season=base.season,release_id=release_id,baseline=base.release_id,
            actual_manifest_sha256=release.manifest_sha256,actual_jug_sha256=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
            package_sha256=registry.sha256_file(release.package_path),plan_sha256=registry.sha256_file(path),
            changed_carriers=[r['carrier_id'] for r in plan['updates']],exact_native_reproduction=True,idempotent=True,
            all_other_record_bytes='identical outside selected nationality/ability bytes',all_other_game_files='byte-identical',
            skills_changed=kind.startswith('season-rating-calibration'),nationalities_changed=kind=='woking-original-nationalities',
            fixed_rosters_roles_tactics_managers_assets_EXE=True))
    if not (root/'complete-SOURCE-replay.json').exists():
        if registry.locator_path(base.season,replay_id).exists():raise ValueError('unreceipted quality replay exists')
        retained(root/'complete-SOURCE-replay.json',source.reconstruction(release,replay_id))
    deduplicate_owned_replay(base,release,registry.load_registered_release(base.season,replay_id),root,plan)
    print(dict(season=base.season,release_id=release_id,built=True,complete_SOURCE_exact=True,runtime_pending=True),flush=True)


if __name__=='__main__':
    build(registry.load_registered_release('2003-04','sourced-woking-owned-opening-20261011-r98a'),
        'woking-original-nationalities',registry.ROOT/'.local/consolidated-audit-20261009/woking-nationalities-v1',
        'sourced-woking-nationalities-20261011-r99a','replayed-woking-nationalities-20261011-r99b')
