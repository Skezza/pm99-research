"""Build both2002 actor corrections without changing default season bindings."""
import os
import shutil
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_shtanyuk_2002_coupled_alias_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.closeout_duplicate_ownership_batch_v1 import verify_native_batch

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/Shtanyuk2002-coupled-delivery-v1'
SEASON='2002-03'
BASE='sourced-remaining-manager-tenures-20261016-r116a'
RELEASE='sourced-shtanyuk-coupled-owners-20261016-r119a'
REPLAY='replayed-shtanyuk-coupled-owners-20261016-r119b'


def main():
    if (ROOT/'complete-SOURCE-replay.json').exists():raise ValueError('completed coupled build must not repeat')
    if shutil.disk_usage(registry.ROOT).free<8.3*1024**3:raise ValueError('coupled build refuses to threaten8GiB reserve')
    base=registry.load_registered_release(SEASON,BASE);plan=source.prepare(base)
    folder=ROOT/SEASON;folder.mkdir(parents=True,exist_ok=True)
    path=folder/'ownership-plan.json';retained(path,plan)
    descriptor=folder/'inert.json'
    retained(descriptor,dict(season=SEASON,release_id=BASE,package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    if not registry.locator_path(SEASON,RELEASE).exists():
        publisher.publish(SEASON,descriptor,release_id=RELEASE,source_release_id=BASE,ownership_plan_path=path)
    actual=registry.load_registered_release(SEASON,RELEASE)
    proof=ROOT/'native-byte-proof.json'
    if not proof.exists():verify_native_batch(ROOT,RELEASE,proof,seasons=[SEASON])
    if registry.locator_path(SEASON,REPLAY).exists():raise ValueError('unreceipted coupled SOURCE exists; inspect instead of rerun')
    replay=source.reconstruction(actual,REPLAY)
    retained(ROOT/'complete-SOURCE-replay.json',dict(replay,season=SEASON,source_release_id=RELEASE,
        manifest_sha256=actual.manifest_sha256,native_proof_sha256=registry.sha256_file(proof),preferred_unchanged=True))
    rebuilt=registry.load_registered_release(SEASON,REPLAY)
    for a,b in ((actual.package_path,rebuilt.package_path),
            (actual.game_path/'DBDAT/JUG98030.FDI',rebuilt.game_path/'DBDAT/JUG98030.FDI')):
        if registry.sha256_file(a)!=registry.sha256_file(b):raise ValueError('new coupled SOURCE bytes differ before content sharing')
        if a.stat().st_ino!=b.stat().st_ino:
            temporary=b.with_name(b.name+'.verified-link')
            if temporary.exists():raise ValueError('unreceipted sharing temporary')
            os.link(a,temporary);os.replace(temporary,b)
    print(dict(actual_two_club_corrections_built=True,complete_SOURCE_exact=True,
        selected_starter_change_explicit=True,preferred_unchanged=True,runner_review_pending=True),flush=True)


if __name__=='__main__':main()
