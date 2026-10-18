"""Save ROOT's observed original frames, not OCR-derived approvals."""
import argparse
from pathlib import Path
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts.capture_woking_nationalities_20261011 import ROOT,RELEASE,TAG
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

OBSERVED={
    'louis':dict(observed_native_name='J Louis',observed_club='Woking',observed_age=24,expected_age=24,
        observed_nationality='DOMINICA',observed_skills=dict(speed=55,stamina=53,aggression=52,quality=50,
            handling=10,passing=51,dribbling=53,heading=56,tackling=29,shooting=61)),
    'bayes':dict(observed_native_name='Ashley Bayes',observed_club='Woking',observed_age=31,expected_age=31,
        observed_nationality='ENGLAND',observed_skills=dict(speed=43,stamina=51,aggression=51,quality=64,
            handling=67,passing=56,dribbling=36,heading=33,tackling=36,shooting=26)),
    'nade':dict(observed_native_name='Raphael Nade',observed_club='Woking',observed_age=23,expected_age=23,
        observed_nationality='FRANCE',observed_skills=dict(speed=60,stamina=65,aggression=71,quality=66,
            handling=6,passing=59,dribbling=53,heading=71,tackling=74,shooting=46)),
}

def save(label):
    release=registry.load_registered_release('2003-04',RELEASE)
    if label=='startup':
        screenshot=registry.ROOT/'.local/runlogs/pm99_runner'/TAG/'screens/022_line_up_inspect.png'
        observed=dict(observed_team='Stoke City',observed_date='2003-08-01',lineup_legible=True,
            release_manifest_sha256=release.manifest_sha256)
        target=ROOT/'startup-visual-review.json'
    else:
        transport=pipeline.read_json_file(ROOT/(label+'-profile-transport.json'))
        summaries=list((registry.ROOT/transport['evidence']).rglob('summary.json'))
        if len(summaries)!=1:raise ValueError('one completed actual profile required')
        summary=pipeline.read_json_file(summaries[0])
        screenshot=summaries[0].parent/'screens'/Path(summary['player_profile']['screenshot']).name
        observed=OBSERVED[label]|dict(all_ten_visible_skills_inspected=True,visible_skills_match_native_baseline=True)
        target=ROOT/(label+'-profile-visual-review.json')
    retained(target,dict(method='assistant-original-image-visual-review',original_frame_visually_inspected=True,
        screenshot=registry.relative_workspace_path(screenshot),screenshot_sha256=registry.sha256_file(screenshot),
        reviewer='ROOT',machine='joe-Vostro-3350',source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',**observed))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('label',choices=['startup',*OBSERVED]);save(parser.parse_args().label)
