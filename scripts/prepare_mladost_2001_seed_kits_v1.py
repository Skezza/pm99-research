"""Byte-identical factory carrier kit fallback, NOT historical Mladost artwork."""
import hashlib
from scripts import season_kit_render_bindings_v1 as render
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import cascade_compact_kit_v6 as cascade


def catalogue():
    bindings=[dict(path=registry.relative_workspace_path(cascade.BASE/archive),
        sha256=registry.sha256_file(cascade.BASE/archive)) for archive in render.ARCHIVES]
    return dict(schema_version='pm99-season-kit-catalogue-v1',season=dict(start_year=2001,end_year=2002,label='2001/02'),
        rows=[dict(carrier_id=706,club_name='Mladost Apatin',status='explicit-seed-fallback',
            render_contract=dict(kind='original-factory-native-carrier-bitmap-fallback',carrier_id=706,original_bindings=bindings),
            source=dict(provider='original-PM99-factory-carrier-explicit-fallback',reviewed=False,
                evidence=bindings,exact_artwork=False,target_season_artwork_verified=False,
                limitation='No approved target2001 Mladost kit image. Original factory carrier706 bitmap retained byte-for-byte, not represented as Mladost historical colours.',
                attribution='Original PM99 game asset; local game seed only, no proprietary artwork published.'))])


def render_seed(catalogue_value,output_dir):
    if catalogue_value!=catalogue():raise ValueError('seed kit catalogue or original archives changed')
    artifacts=[]
    for archive in render.ARCHIVES:
        record=render._record_index(cascade.BASE/archive)[706]
        path,digest=render._write_artifact(record.raw_bitmap,output_dir)
        artifacts.append(dict(id='kit-seed-2001-02-706-'+archive[:-4].lower(),kind='kit-render',
            sha256=digest,relative_path=str(path.relative_to(output_dir))))
    digest=hashlib.sha256(pipeline.canonical_json_bytes(catalogue_value)).hexdigest()
    binding=dict(schema_version=render.SCHEMA,kit_catalogue_sha256=digest,clubs=[dict(carrier_id=706,artifacts=artifacts)])
    receipt=dict(schema_version=render.RECEIPT_SCHEMA,season=catalogue_value['season'],kit_catalogue_sha256=digest,
        policy=dict(gaps='explicit-factory-seed-fallback-not-historical-artwork'),
        coverage=dict(catalogue_club_count=1,bound_club_count=1,artifact_count=3,status_counts={'explicit-seed-fallback':1}),
        rows=[dict(carrier_id=706,club_name='Mladost Apatin',status='explicit-seed-fallback',
            renderer='original-factory-native-carrier-bitmap-fallback-v1',artifacts=artifacts)])
    return binding,receipt
