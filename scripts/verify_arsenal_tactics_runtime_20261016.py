"""Check all880 live Arsenal phase coordinates against the published recipe."""
import os
import json
from pathlib import Path
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_contextual_tactics_v1 as tactics
from scripts.verify_contextual_tactics_runtime_v1 import verify
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.build_arsenal_owned_opening_20261016 import ROOT,SEASON,RELEASE
from scripts.capture_arsenal_owned_opening_20261016 import TAG


def main():
    release=registry.load_registered_release(SEASON,RELEASE)
    package=pipeline.read_json_file(release.package_path)
    club=next(c for c in package['clubs'] if c['carrier_id']==309)
    candidate=ROOT/'tactics-verification-input-v2';(candidate/'DBDAT').mkdir(parents=True,exist_ok=True)
    for name in ('JUG98030.FDI','EQ98030.FDI'):
        original=release.game_path/'DBDAT'/name;target=candidate/'DBDAT'/name
        if target.exists():
            if target.is_symlink() or registry.sha256_file(target)!=registry.sha256_file(original):
                raise ValueError('Arsenal tactics verification input changed')
        else:os.link(original,target)
    retained(candidate/'contextual-tactics.json',dict(schema_version=tactics.SCHEMA,season=SEASON,
        clubs=[dict(carrier_id=309,name='Arsenal',formation='4-2-3-1',context=club['opening']['tactics_context'])]))
    run=registry.ROOT/'.local/runlogs/pm99_runner'/TAG
    transport=pipeline.read_json_file(ROOT/'Arsenal-startup-tactics-transport.json')
    summary=pipeline.read_json_file(run/'summary.json')
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256
        or summary.get('success') is not True or summary.get('crash_detected')
        or summary.get('release_manifest_sha256')!=release.manifest_sha256
        or summary.get('output_inventory_fingerprint')!=release.locator['game_inventory_fingerprint']):
        raise ValueError('actual Arsenal runner transport not bound to exact game')
    proof=verify(candidate,run,309,header_review=ROOT/'Arsenal-header-visual-review.json'
        if (ROOT/'Arsenal-header-visual-review.json').exists() else None)
    # The pixel verifier returns coordinate tuples; stored JSON contains
    # lists. Compare the same JSON-native representation on repeat checks.
    proof=json.loads(pipeline.canonical_json_bytes(proof))
    retained(ROOT/'actual-Arsenal-tactics-runtime-proof.json',dict(proof,
        season=SEASON,release_id=RELEASE,release_manifest_sha256=release.manifest_sha256,
        exact_game_EQ_sha256=registry.sha256_file(release.game_path/'DBDAT/EQ98030.FDI'),
        exact_game_JUG_sha256=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
        source_recipe_sha256=registry.sha256_file(release.package_path)))
    print(dict(actual_Arsenal_all880_live_coordinates_verified=True,original_visual_review_still_required=True),flush=True)


if __name__=='__main__':main()
