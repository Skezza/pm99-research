"""Record an inspected original frame with independently decoded skill digits.

The caller must actually inspect and explicitly supply the frame path and
literal identity/club/country/role observations. This never auto-approves an
image and never reads expected recipe ratings to manufacture observations.
"""
from pathlib import Path
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import read_profile_skill_digits_v1 as digits,read_profile_age_digits_v1 as ages
from scripts.review_rating_frames_20261011 import profile_for


def record(root,label,*,inspected_original,observed):
    root=Path(root);inspected_original=Path(inspected_original).resolve()
    required={'observed_native_name','observed_club','observed_age','observed_nationality','observed_position','observed_fine_position'}
    if not required<=observed.keys() or 'observed_skills' in observed or 'expected_age' in observed:
        raise ValueError('explicit literal visual fields required; supplied expected skill/age values forbidden')
    transport=pipeline.read_json_file(root/(label+'-profile-transport.json'))
    if transport['exit_code']!=0:raise ValueError('cannot review failed profile transport')
    summaries=list((registry.ROOT/transport['evidence']).rglob('summary.json'))
    if len(summaries)!=1:raise ValueError('one actual completed original profile required')
    summary=pipeline.read_json_file(summaries[0])
    actual=summaries[0].parent/'screens'/Path(summary['player_profile']['screenshot']).name
    if actual.resolve()!=inspected_original or not actual.is_file() or summary.get('success') is not True:
        raise ValueError('inspected original differs from completed profile frame')
    decoded=digits.read(actual);age=ages.read(actual)
    if age['observed_age']!=observed['observed_age']:raise ValueError('literal visual age differs from independent actual font digits')
    profile_for(root,label,dict(**observed,observed_skills=decoded['observed_skills'],
        skill_transcription_basis='independent-original-bitmap-font-digits-not-recipe',
        original_digit_readback_method=decoded.get('method'),independent_digit_screenshot_sha256=decoded['screenshot_sha256']))
