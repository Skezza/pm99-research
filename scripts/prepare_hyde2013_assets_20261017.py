"""Attach source-bound Hyde colours and Ewen Fields using unchanged asset APIs."""
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import season_kit_render_bindings_v1 as render
from scripts import prepare_paired_club_assets_v1 as assets
from scripts import verify_paired_whole_club_native_v1 as readback
from scripts import verify_paired_club_identity_v1 as identity
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.prepare_hyde2013_sources_20261017 import ROOT

BASE=ROOT.parent;ART=BASE/'Hyde2013-assets-v1';NATIVE=ROOT/'native';COMPLETE=BASE/'Hyde2013-complete-v1'
SPECS={3319:('Hyde','Ewen Fields','ground-original-3319.html',
    'https://en.wikipedia.org/wiki/2013%E2%80%9314_Football_Conference',
    ('2013–14 Football Conference','Hyde','Stadia and locations'))}

def run():
    if COMPLETE.exists():raise ValueError('completed assets must not repeat')
    cache=ART/'source-cache';cache.mkdir(parents=True,exist_ok=True)
    original=ROOT/'source-cache/ground-2013-conference.html';ground=cache/'ground-original-3319.html'
    if ground.exists():raise ValueError('inspect previous source preparation before repeating')
    import os
    os.link(original,ground)
    retained(ground.with_name(ground.name+'.source.json'),pipeline.read_json_file(original.with_name(original.name+'.source.json')))
    assets.ground_source(cache,3319,SPECS)
    evidence=[]
    for name in ('programme-2013-hyde-luton.pdf','programme-page-01.png','programme-page-02.png','programme-page-03.png'):
        path=ROOT/'source-cache'/name
        evidence.append(dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)))
    doc=dict(schema_version='pm99-season-kit-catalogue-v1',season=dict(start_year=2013,end_year=2014,label='2013/14'),
        rows=[dict(carrier_id=3319,club_name='Hyde',status='source-ready',render_contract=dict(kind='reviewed-pm99-style',
            style=dict(pattern='solid',colors=['red'],shorts='navy',sleeves='red',trim='white')),
            source=dict(provider='original-club-season-programme-reviewed-photograph',
                attribution='Hyde FC official programme v Luton Town, 26 April 2014; scan courtesy of Hatters Heritage',
                url=pipeline.read_json_file(ROOT/'source-cache/programme-2013-hyde-luton.pdf.source.json')['url'],
                evidence=evidence,exact_artwork=False,shorts_source_verified=True,
                review='ROOT directly viewed original PDF pages1–3 rendered by pdftoppm. Dated cover26April2014; page2 club addressEwenFields and managerScottMcNiven; page2 contents action photograph shows red shirt/white trim and dark navy shorts. Cover mascot is not used as sole player-strip evidence. Reproduce colour families only; exact shade/piping/logo and August match variant not certified.'))],
        limitations=['Season programme colour approximation, not exact sponsor/manufacturer/piping artwork.',
            'The small action photograph supports dark navy shorts; precise shades and opening-day variant are not independently certified.'])
    retained(ART/'kit-catalogue.json',doc);retained(ART/'ground-specs.json',SPECS)
    bindings,receipt=render.render_catalogue(doc,dbdat=NATIVE/'game/DBDAT',output_dir=ART/'renders',
        pattern_cache_dir=ART/'pattern-cache',allow_network=False)
    if receipt['coverage']['bound_club_count']!=1 or receipt['coverage']['artifact_count']!=3:
        raise ValueError('all three Hyde kit sizes required')
    retained(ART/'render-bindings.json',bindings);retained(ART/'render-receipt.json',receipt)
    assets.prepare(NATIVE,ART,COMPLETE,ground_specs=SPECS)
    readback.verify(COMPLETE,BASE/'Hyde2013-native-readback.json')
    result=identity.verify(COMPLETE,registry.ROOT/'.local/duplicate-ownership-v3/published-person-identities-r2.json',
        BASE/'Hyde2013-identity-readback.json')
    print(dict(Hyde_assets_complete=True,introduced_duplicates=result['introduced_candidate_groups'],preferred_changed=False),flush=True)

if __name__=='__main__':run()
