"""Capture each completed private coach game once under the normal runner FIFO."""
import argparse
from pathlib import Path
import time
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_cached_manager_repairs_20261016 import ROOT, RELEASE
from scripts.capture_cached_manager_repairs_20261016 import main as capture


def main(build_pid):
    for season in registry.supported_seasons():
        if season=='2015-16':continue  # explicitly separate legacy source layout
        root=ROOT/season;deadline=time.monotonic()+14400
        while not (root/'complete-SOURCE-replay.json').exists():
            if (root/'no-native-or-recipe-correction-needed.json').exists():break
            proc=Path('/proc')/str(build_pid)/'cmdline'
            if not proc.exists() or b'scripts.advance_cached_manager_builds_20261016' not in proc.read_bytes():
                raise ValueError('own manager builder stopped; inspect terminal outcome')
            if time.monotonic()>deadline:raise ValueError('bounded own manager build wait expired')
            time.sleep(10)
        if (root/'no-native-or-recipe-correction-needed.json').exists():continue
        transport=root/'startup-transport.json'
        if transport.exists():
            release=registry.load_registered_release(season,RELEASE)
            saved=pipeline.read_json_file(transport)
            if saved['exit_code']!=0 or saved['release_manifest_sha256']!=release.manifest_sha256:
                raise ValueError('prior manager startup failed or belongs to another game')
            print(dict(season=season,reused_exact_completed_manager_startup=True),flush=True)
            continue
        capture([season])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manager-build-pid',type=int,required=True)
    main(parser.parse_args().manager_build_pid)
