"""Pinned, resumable 26-season ability-only delivery; no preferred promotion."""
from collections import Counter
import shutil
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_quality_only_delta_v1 as source
from scripts.build_quality_only_delivery_v1 import build
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/rating-calibration-v3'
def release_id(season):return 'sourced-rating-calibration-20261011-'+season+'-r101a'
def replay_id(season):return 'replayed-rating-calibration-20261011-'+season+'-r101b'

def main():
    ROOT.mkdir(parents=True,exist_ok=True);path=ROOT/'pinned-baselines.json'
    if path.exists():baselines=pipeline.read_json_file(path)
    else:
        baselines=[dict(season=s,release_id=(registry.load_registered_release(s,'sourced-woking-nationalities-20261011-r99a')
            if s=='2003-04' else registry.load_preferred_release(s)).release_id) for s in registry.supported_seasons()]
        retained(path,baselines)
    # Space prediction counts each actual recipe/JUG/plan once because identical
    # replay bytes retain all paths via verified hardlinks. Leave a 100MiB
    # transient allowance in addition to the publisher's existing 8GiB floor.
    need=0
    for b in baselines:
        base=registry.load_registered_release(b['season'],b['release_id'])
        root=ROOT/b['season'];root.mkdir(parents=True,exist_ok=True)
        path=root/'quality-plan.json'
        if not path.exists():retained(path,source.prepare(base,'season-rating-calibration-v3'))
        if not registry.locator_path(b['season'],release_id(b['season'])).exists():
            need+=base.package_path.stat().st_size+(base.game_path/'DBDAT/JUG98030.FDI').stat().st_size+256_000
    from scripts.rating_calibration_benchmarks_v3 import check
    check()
    if shutil.disk_usage(ROOT).free-need-100*1024**2<8*1024**3:
        raise ValueError('26-season retained actual/replay batch would breach 8GiB floor; no games built')
    if not (ROOT/'preflight.json').exists():
        retained(ROOT/'preflight.json',dict(baselines=baselines,space_required_bytes=need,free_at_preflight=shutil.disk_usage(ROOT).free,
            preserved_existing_games=True,no_Pi_or_cleanup_required=True))
    elif pipeline.read_json_file(ROOT/'preflight.json')['baselines']!=baselines:
        raise ValueError('retained preflight baseline set differs')
    # Prove the specifically reported Walker defect first, then the other25.
    for b in sorted(baselines,key=lambda b:(b['season']!='2024-25',b['season'])):
        base=registry.load_registered_release(b['season'],b['release_id']);root=ROOT/b['season']
        build(base,'season-rating-calibration-v3',root,release_id(b['season']),replay_id(b['season']))
        plan=pipeline.read_json_file(root/'quality-plan.json')
        retained(root/'calibration-summary.json',dict(season=b['season'],baseline=b['release_id'],release_id=release_id(b['season']),
            updated_players=len(plan['updates']),methods=dict(Counter(x['ratings']['provenance']['method'] for x in plan['updates'])),
            ratings_only=True,built=True,runtime_verified=False))

if __name__=='__main__':main()
