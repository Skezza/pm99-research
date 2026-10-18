"""Record built, SOURCE-reproduced games separately from runtime delivery."""
from datetime import UTC, datetime
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import build_remaining_manager_tenures_20261016 as batch
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding


def main():
    output=batch.ROOT/'all25-private-builds-complete.json'
    if output.exists():
        raise ValueError('completed build summary must not repeat')
    path=batch.ROOT/'source-admission-summary.json'
    admission=pipeline.read_json_file(path); rows=[]
    for row in admission['seasons']:
        if not row['corrections']:
            continue
        season=row['season']; root=batch.ROOT/season
        actual=registry.load_registered_release(season,batch.RELEASE)
        replay=registry.load_registered_release(season,batch.REPLAY)
        native=pipeline.read_json_file(root/'native-byte-proof.json')
        proof=pipeline.read_json_file(root/'complete-SOURCE-replay.json')
        if (native['manifest_sha256']!=actual.manifest_sha256
                or native['plan_sha256']!=registry.sha256_file(root/'manager-plan.json')
                or native['ENT_sha256']!=registry.sha256_file(actual.game_path/'DBDAT/ENT98030.FDI')
                or not all(native[k] for k in ('all_unselected_ENT_records_identical',
                    'all_other_game_files_identical','complete_recipe_exact','original_source_reparsed'))
                or not proof['complete_game_inventory_identical'] or not proof['complete_recipe_identical']
                or pipeline.read_json_file(actual.inventory_path)!=pipeline.read_json_file(replay.inventory_path)
                or registry.sha256_file(actual.package_path)!=registry.sha256_file(replay.package_path)):
            raise ValueError('built/SOURCE evidence no longer binds exact games')
        if native['canonical_manager_corrections']!=row['corrections']:
            raise ValueError('native correction count differs from source admission')
        preferred=registry.load_preferred_release(season)
        parent=registry.load_registered_release(season,row['source_parent'])
        if (preferred.release_id,preferred.manifest_sha256)!=(parent.release_id,parent.manifest_sha256):
            raise ValueError('prepublication preferred parent changed')
        rows.append(dict(season=season,release_id=batch.RELEASE,manifest_sha256=actual.manifest_sha256,
            canonical_updates=native['canonical_manager_corrections'],native_name_changes=native['native_manager_name_changes'],
            native_proof=binding(root/'native-byte-proof.json'),SOURCE_proof=binding(root/'complete-SOURCE-replay.json')))
    if len(rows)!=25 or sum(r['canonical_updates'] for r in rows)!=109:
        raise ValueError('exact admitted25/109 build scope changed')
    retained(output,dict(utc=datetime.now(UTC).isoformat(),machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',state='built-private-SOURCE-complete-not-delivered',
        source_admission=binding(path),seasons=rows,canonical_updates=109,original_deferred36_not_yet_closed=True,
        preferred_catalog_unchanged=True,original2015_backup_untouched=True,
        remaining='All25 original runner reviews, independent source/native/runtime readbacks, publication and playable attestations.',
        global_historical_RC=False))
    print(dict(private_seasons_built=25,canonical_updates=109,preferred_unchanged=True,
        not_runtime_delivery=True,summary=binding(output)),flush=True)


if __name__=='__main__':
    main()
