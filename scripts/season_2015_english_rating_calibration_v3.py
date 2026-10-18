"""Calibrate the separately bound 2015 English layer without touching foreign rows.

The legacy layer is not present in main.players. Bind its exact artifact, reject
shared carriers, use the unchanged v3 policy and publish its edited recipe too.
"""
import copy
from dataclasses import replace
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_package_v2 as packages,season_rating_calibration_v3 as ratings
from scripts import season_quality_only_delta_v1 as quality

KIND='season-rating-calibration-2015-english-v3'
SOURCE_ID='source-bound-rating-calibration-2015-english-v3'
ARTIFACT='english-contextual-package-2015-16'

def overlay(base):
    if base.season!='2015-16':raise ValueError('English rating overlay only exists in 2015/16')
    main=pipeline.read_json_file(base.package_path)
    artifacts=[a for a in main['artifacts'] if a['id']==ARTIFACT]
    if len(artifacts)!=1:raise ValueError('one exact English rating overlay required')
    artifact=artifacts[0];path=base.package_path.parent/artifact['relative_path']
    if path.parent.resolve()!=base.package_path.parent.resolve():raise ValueError('English rating overlay must be recipe-local')
    if registry.sha256_file(path)!=artifact['sha256']:raise ValueError('English rating overlay preimage/hash differs')
    document=pipeline.read_json_file(path);packages.validate_package(document)
    if {p['carrier_id'] for p in main['players']} & {p['carrier_id'] for p in document['players']}:
        raise ValueError('English rating overlay cannot share a native carrier with main')
    return document,path

def rows(base):
    document,path=overlay(base)
    updates,bindings=ratings.rows(replace(base,package_path=path))
    for row in updates:
        row['layer']='english'
        row['ratings']['provenance']['source_ids']=[SOURCE_ID]
    bindings.extend(dict(path=registry.relative_workspace_path(p),sha256=registry.sha256_file(p))
        for p in (path,registry.ROOT/'scripts/season_2015_english_rating_calibration_v3.py'))
    return updates,bindings

def updated_english(plan):
    if plan['kind']!=KIND:raise ValueError('not an English rating-only plan')
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    document,_=overlay(base);result=copy.deepcopy(document)
    players={p['carrier_id']:p for p in result['players']}
    for row in plan['updates']:
        if row.get('layer')!='english':raise ValueError('mixed English/main rating transaction')
        player=players[row['carrier_id']]
        if quality.digest(packages.canonical_json_bytes(player))!=row['before_sha256']:
            raise ValueError('English rating identity/preimage differs')
        player['ratings']=copy.deepcopy(row['ratings'])
    evidence=dict(id=quality.artifact_id(plan),kind='season-input',relative_path=quality.filename(plan),
        sha256=quality.digest(packages.canonical_json_bytes(plan)),media_type='application/json')
    result['artifacts'].append(evidence)
    result['sources'].append(dict(id=SOURCE_ID,title='2015 English ability-only calibration using the pinned v3 FIFA/editorial policy',
        proof_grade='reviewed-editorial',evidence_artifact_id=evidence['id']))
    result['artifacts'].sort(key=lambda a:a['id']);result['sources'].sort(key=lambda s:s['id'])
    packages.validate_package(result)
    return result

def bind(package,plan):
    english=updated_english(plan);result=copy.deepcopy(package)
    artifact=next(a for a in result['artifacts'] if a['id']==ARTIFACT)
    artifact['sha256']=quality.digest(packages.canonical_json_bytes(english))
    result['artifacts'].append(dict(id=quality.artifact_id(plan),kind='season-input',relative_path=quality.filename(plan),
        sha256=quality.digest(packages.canonical_json_bytes(plan)),media_type='application/json'))
    result['artifacts'].sort(key=lambda a:a['id']);packages.validate_package(result)
    return result
