"""Resume ONLY the failed accented token profile and later missing countries.

No database build or successful startup/profile is repeated. Original failed
summary and transport remain untouched. A new ASCII comparison token does not
rename the player; exact native identity/club/digits still gate publication.
"""
import unicodedata
from scripts import build_original_country_defaults_20261017 as build
from scripts.capture_original_country_defaults_20261017 import tag
from scripts.capture_shinnie_country_20261017 import main as capture
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=build.ROOT.parent/'original-country-runtime-resume-20261017'


def ascii_token(search):
    value=unicodedata.normalize('NFKD',search.split()[-1]).translate(str.maketrans({'Ł':'L','ł':'l','Ø':'O','ø':'o','Đ':'D','đ':'d','ß':'ss'}))
    token=''.join(char for char in value if not unicodedata.combining(char)).encode('ascii','ignore').decode()
    if not token.isalpha() or len(token)<3:
        raise ValueError('profile comparison token needs an explicit reviewed ASCII word')
    return token


def main():
    if ROOT.exists():raise ValueError('existing runtime resume needs inspection; never repeat successful captures')
    folder=build.ROOT/'2017-18';old=pipeline.read_json_file(folder/'runtime-profile-spec.json')
    transport=folder/'country_3362-profile-transport.json'
    failed=pipeline.read_json_file(transport)
    summaries=list((registry.ROOT/failed['evidence']).rglob('summary.json'))
    if len(summaries)!=1:raise ValueError('one original failed token summary required')
    summary=pipeline.read_json_file(summaries[0])
    if (failed['exit_code']!=1 or summary['player_profile']['expected_name_token_satisfied'] is not False
            or summary['player_profile']['expected_name_token']!='ram rez'
            or 'sandro ramirez' not in summary['player_profile']['player_name_ocr_normalized']
            or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or old['profiles'][0]['carrier_id']!=3362):
        raise ValueError('runtime resume does not match the inspected accented-token-only refusal')
    ROOT.mkdir()
    retained(ROOT/'input.json',dict(original_controller_exit=1,
        original_transport=dict(path=registry.relative_workspace_path(transport),sha256=registry.sha256_file(transport)),
        original_summary=dict(path=registry.relative_workspace_path(summaries[0]),sha256=registry.sha256_file(summaries[0])),
        cause='Expected Ramírez became ram rez; original OCR read Sandro Ramirez. Failed profile alone gets a new token/tag.',
        no_game_builds=True,no_successful_captures_repeated=True,visual_approval=False))
    rows=pipeline.read_json_file(build.ROOT/'batch-input.json')['rows']
    for row in rows:
        season=row['season']
        if season<'2017-18':continue
        folder=build.ROOT/season;actual=registry.load_registered_release(season,build.RELEASE)
        if not (folder/'complete-SOURCE-replay.json').is_file():raise ValueError('missing complete SOURCE; inspect existing build')
        if season=='2017-18':
            saved=folder/'runtime-profile-spec-rejected-accent-token-v1.json'
            if saved.exists():raise ValueError('accent retry already prepared; inspect before rerun')
            (folder/'runtime-profile-spec.json').rename(saved)
            profile=dict(old['profiles'][0],label='country_3362_ascii_name',token='Ramirez')
        else:
            if (folder/'runtime-profile-spec.json').exists():raise ValueError('later runtime spec already exists; inspect before capture')
            plan=pipeline.read_json_file(folder/'country-plan.json')
            actor=min(plan['updates'],key=lambda r:r['carrier_id'])['before_player']
            search=build.source.original.names.undecorated(actor['name'])
            profile=dict(carrier_id=actor['carrier_id'],label='country_'+str(actor['carrier_id']),
                search=search,token=ascii_token(search),expected_native_name=actor['name'])
        retained(folder/'runtime-profile-spec.json',dict(season=season,release_id=build.RELEASE,
            manifest_sha256=actual.manifest_sha256,profiles=[profile],visual_approval=False,
            all_changed_countries_native_readback_required=True,independent_country_conflicts_still_require_resolution=True))
        capture(0,0,folder=folder,release_id=build.RELEASE,run_tag=tag(season),season=season,profile=profile)
        retained(ROOT/(season+'-captured.json'),dict(season=season,release_id=build.RELEASE,
            original_visual_review_pending=True,default_changed=False))


if __name__=='__main__':main()
