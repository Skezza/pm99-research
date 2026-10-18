"""Admit period-country policy repairs across all years, without game writes.

Re-evaluate every recipe CGO occurrence against exact-DOB original annuals;
never blindly change all Congo labels. Include proven unsupported-country
defaults from the bound country discovery. Existing private r127/r128 parents
are explicitly preferred when SOURCE-complete, not regenerated.
"""
from datetime import UTC,datetime

from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_original_country_policy_v2 as source
from scripts import build_original_country_defaults_20261017 as initial
from scripts import build_original_country_policy_v2_20261017 as policy
from scripts.build_2015_english92_release import UNREPRESENTABLE_NATIONALITY
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=initial.ROOT.parent/'original-country-policy-v2-discovery-20261017'


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    if (ROOT/'discovery.json').exists():
        raise ValueError('completed policy source discovery must not repeat')
    original_path=initial.discovery.ROOT/'discovery.json'
    original=pipeline.read_json_file(original_path)
    by_year={r['season']:r for r in original['seasons']}
    rows=[]
    for season in registry.supported_seasons():
        saved=ROOT/(season+'.json')
        if saved.exists():
            rows.append(pipeline.read_json_file(saved));continue
        base=registry.load_preferred_release(season)
        parent_source='current-preferred'
        if (initial.ROOT/season/'complete-SOURCE-replay.json').exists():
            base=registry.load_registered_release(season,initial.RELEASE);parent_source='existing-source-complete-r127'
        if (policy.ROOT/season/'complete-SOURCE-replay.json').exists():
            base=registry.load_registered_release(season,policy.RELEASE);parent_source='existing-source-complete-r128'
        package=pipeline.read_json_file(base.package_path)
        actors={p['carrier_id']:p for p in package['players']}
        targets={str(p['carrier_id']):['nationality'] for p in package['players']
            if p['facts'].get('nationality')=='CGO' and p.get('policy')!='preserve-existing-mode1'}
        for candidate in by_year[season]['candidates']:
            if candidate['source_country'] in UNREPRESENTABLE_NATIONALITY or candidate['source_country']=='CGO':
                actor=actors[candidate['carrier_id']]
                if actor['facts'].get('birth_date')!=candidate['birth_date']:
                    raise ValueError('country policy target identity changed; do not silently reassign')
                targets[str(candidate['carrier_id'])]=['nationality']
        result=dict(season=season,release_id=base.release_id,manifest_sha256=base.manifest_sha256,
            package_sha256=registry.sha256_file(base.package_path),parent_source=parent_source,
            rebase_on_r127_required=bool(by_year[season]['candidates']) and parent_source=='current-preferred',
            main_layer_only=True,targets=targets,native_writes=0,cross_club_cases_closed=0)
        if not targets:
            result.update(admitted=[],unresolved=[])
        else:
            try:
                admission=source.prepare(base,policy.PEOPLE,targets)
                path=ROOT/(season+'-source-admission.json');retained(path,admission)
                result.update(admission=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)),
                    admitted=[dict(carrier_id=r['carrier_id'],name=r['before_player']['name'],
                        before_country=r['before_player']['facts']['nationality'],source_country=r['nationality'],
                        before_native_country_code=r['before_nationality_code'],native_country_code=r['native_country_code'],
                        native_label=r['native_label']) for r in admission['updates']],unresolved=admission['unresolved'])
            except (ValueError,KeyError,pipeline.PipelineError) as exc:
                result.update(admitted=[],unresolved=[],admission_error=type(exc).__name__+': '+str(exc))
        retained(saved,result);rows.append(result)
        print(dict(season=season,source_admitted=len(result['admitted']),
            unresolved=len(result['unresolved']),error=result.get('admission_error')),flush=True)
    retained(ROOT/'discovery.json',dict(utc=datetime.now(UTC).isoformat(),seasons=rows,
        original_country_discovery=dict(path=registry.relative_workspace_path(original_path),sha256=registry.sha256_file(original_path)),
        admitted=sum(len(r['admitted']) for r in rows),native_writes=0,cross_club_cases_closed=0,
        source_parent_reconciliation_required=True,main_layer_only_not_2015_english_overlay_approval=True,
        machine='joe-Vostro-3350',source_session='01a0592d-fcd5-7262-a637-743a8253d9b4'))


if __name__=='__main__':
    main()
