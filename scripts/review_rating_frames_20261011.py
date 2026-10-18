"""Record ROOT's explicitly observed original runner images, never auto-approve."""
from pathlib import Path
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts.build_all_rating_calibrations_20261011 import ROOT,release_id
from scripts.capture_all_rating_calibrations_20261011 import tag
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

def lineup_frame(evidence):
    frames=list((Path(evidence)/'screens').glob('*line_up_inspect*.png'))
    if len(frames)!=1:raise ValueError('one exact original lineup frame required')
    return frames[0]

def _review(screenshot,observed):
    return dict(method='assistant-original-image-visual-review',original_frame_visually_inspected=True,
        screenshot=registry.relative_workspace_path(screenshot),screenshot_sha256=registry.sha256_file(screenshot),
        reviewer='ROOT',machine='joe-Vostro-3350',source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',**observed)

def startup(season,observed_date):
    return startup_for(ROOT/season,season,release_id(season),tag(season),observed_date)

def startup_for(root,season,release_name,run_tag,observed_date):
    release=registry.load_registered_release(season,release_name)
    if observed_date!=season[:4]+'-08-01':raise ValueError('observed startup date not target season')
    screenshot=lineup_frame(registry.ROOT/'.local/runlogs/pm99_runner'/run_tag)
    retained(root/'startup-visual-review.json',_review(screenshot,dict(observed_team='Stoke City',observed_date=observed_date,
        lineup_legible=True,no_crash_visually_observed=True,release_manifest_sha256=release.manifest_sha256)))

def profile(season,label,observed):
    return profile_for(ROOT/season,label,observed)

def profile_for(root,label,observed):
    transport=pipeline.read_json_file(root/(label+'-profile-transport.json'))
    summaries=list((registry.ROOT/transport['evidence']).rglob('summary.json'))
    if len(summaries)!=1:raise ValueError('one actual completed profile required')
    summary=pipeline.read_json_file(summaries[0]);frame=summary['player_profile']['screenshot']
    screenshot=summaries[0].parent/'screens'/Path(frame).name
    retained(root/(label+'-profile-visual-review.json'),_review(screenshot,dict(**observed,
        all_ten_visible_skills_inspected=True,expected_age=observed['observed_age'])))
