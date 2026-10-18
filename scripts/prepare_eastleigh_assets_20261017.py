"""Bind the dated launch/ground to the private complete Eastleigh squad."""
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_kit_render_bindings_v1 as render
from scripts import prepare_paired_club_assets_v1 as assets
from scripts import verify_paired_whole_club_native_v1 as readback
from scripts import verify_paired_club_identity_v1 as identity

BASE=registry.ROOT/'.local/consolidated-audit-20261009'
ROOT=BASE/'Eastleigh2014-assets-v1'
NATIVE=BASE/'Eastleigh2014-native-delivery-v1/native'
COMPLETE=BASE/'Eastleigh2014-complete-v1'
SPECS={3322:('Eastleigh','Silverlake Stadium','ground-original-3322.html',
    'https://www.skysports.com/football/eastleigh-vs-aldershot-town/319716',
    ('Eastleigh','Aldershot Town','14th August 2014'))}


def main():
    if (ROOT/'kit-catalogue.json').exists():raise ValueError('completed asset preparation must not repeat')
    capture=pipeline.read_json_file(ROOT/'capture-summary.json')
    evidence=[]
    for name in ('kit-launch.html','home-2014-15.jpg'):
        path=ROOT/'source-cache'/name;receipt=path.with_name(name+'.source.json')
        source=pipeline.read_json_file(receipt)
        if registry.sha256_file(path)!=source['sha256']:raise ValueError('original dated launch changed')
        evidence.append(dict(path=registry.relative_workspace_path(path),**source))
    assets.ground_source(ROOT/'source-cache',3322,SPECS)
    doc=dict(schema_version='pm99-season-kit-catalogue-v1',season=dict(start_year=2014,end_year=2015,label='2014/15'),
        rows=[dict(carrier_id=3322,club_name='Eastleigh',status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style',
                style=dict(pattern='solid',colors=['blue'],shorts='white',sleeves='blue',trim='white')),
            source=dict(provider='original-dated-launch-and-image-reviewed',
                attribution='Eastleigh FC blog / Jamie Montigue, June19 2014 Joma launch',evidence=evidence,
                review='ROOT viewed the original home shirt image: royal blue body and sleeves, white V collar and curved shoulder piping. Sponsor, badge and shoulder piping simplified in factory-tone native art. White shorts are an explicit editorial blue/white pairing: the retained launch photograph shows only the shirt, so exact period shorts are NOT certified.',
                exact_artwork=False,shorts_source_verified=False))],
        limitations=['No exact sponsor/badge/piping reproduction','White shorts editorial choice, not independently verified from shirt-only launch image'],
        original_capture_summary=dict(path=registry.relative_workspace_path(ROOT/'capture-summary.json'),sha256=registry.sha256_file(ROOT/'capture-summary.json')))
    pipeline.write_canonical_json(ROOT/'kit-catalogue.json',doc)
    pipeline.write_canonical_json(ROOT/'ground-specs.json',SPECS)
    bindings,receipt=render.render_catalogue(doc,dbdat=NATIVE/'game/DBDAT',output_dir=ROOT/'renders',
        pattern_cache_dir=ROOT/'pattern-cache',allow_network=False)
    if receipt['coverage']['bound_club_count']!=1 or receipt['coverage']['artifact_count']!=3:
        raise ValueError('replacement asset sizes incomplete')
    pipeline.write_canonical_json(ROOT/'render-bindings.json',bindings)
    pipeline.write_canonical_json(ROOT/'render-receipt.json',receipt)
    assets.prepare(NATIVE,ROOT,COMPLETE,ground_specs=SPECS)
    native_proof=BASE/'Eastleigh2014-native-readback.json'
    result=readback.verify(COMPLETE,native_proof)
    print(dict(native_actors_verified=len(result['players']),unrelated_native_records_preserved=True),flush=True)
    result=identity.verify(COMPLETE,registry.ROOT/'.local/duplicate-ownership-v3/published-person-identities-r2.json',
        BASE/'Eastleigh2014-identity-readback.json')
    print(dict(before=result['before_cross_club_candidate_groups'],after=result['after_cross_club_candidate_groups'],
        new_duplicates=result['introduced_candidate_groups'],stale_portraits_cleared=result['stale_portraits_cleared']),flush=True)


if __name__=='__main__':main()
