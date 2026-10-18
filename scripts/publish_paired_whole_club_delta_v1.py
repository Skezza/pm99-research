"""Register metadata for an independently proved coupled correction, no rebuild.

Creating a locator is not promotion. The normal preferred-release registration
and fresh runtime attestation remain separate, explicit operations.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_package_v2 as packages
from scripts import prepare_duplicate_whole_club_native_v1 as native
from scripts.publish_contextual_tactics_delta_v1 import verify_recipe_artifact
from scripts.season_visual_patch_v1 import source_inventory


def attach_pair_kit_receipts(source,candidate,destination,receipt,native_proof,identity_proof,difference):
    """Extend the actual artwork chain; never inherit a now-stale receipt."""
    from scripts.build_registered_quality_release_v1 import _kit_receipt
    from scripts import season_kit_render_bindings_v1 as renderer
    previous=_kit_receipt(source.season,source_release=source)
    complete=json.loads(previous.read_text());old_audit=Path(complete['audit_path'])
    if registry.sha256_file(old_audit)!=complete['audit_sha256']:raise ValueError('previous kit audit changed')
    audit=json.loads(old_audit.read_text());audit=copy.deepcopy(audit)
    before=renderer._record_index(source.game_path/'DBDAT/NANOESC.PKF')
    after=renderer._record_index(candidate/'game/DBDAT/NANOESC.PKF')
    carriers={r['carrier_id'] for r in receipt['paired_asset_stage']['grounds']}
    if len(audit['records'])!=544 or set(before)!=set(after):raise ValueError('paired kit audit has incomplete carrier set')
    if any(before[id].raw_bitmap!=after[id].raw_bitmap for id in before if id not in carriers):
        raise ValueError('paired artwork changed another club')
    for row in audit['records']:
        id=row['carrier_id']
        if row['after_sha256']!=renderer.sha256_bytes(before[id].raw_bitmap):
            raise ValueError('previous kit bitmap source binding is stale')
        if id not in carriers:continue
        path=candidate/f'kit-source-{id}.json';document=json.loads(path.read_text());source_row=document['catalogue_row']
        row.update(club=source_row['club_name'],before_sha256=renderer.sha256_bytes(before[id].raw_bitmap),
            after_sha256=renderer.sha256_bytes(after[id].raw_bitmap),status='source-bound-rerendered',
            source={'club':source_row['club_name'],'contract':source_row['render_contract'],
                'receipt':str(path.resolve()),'receipt_sha256':registry.sha256_file(path),
                'expected':renderer.sha256_bytes(before[id].raw_bitmap)},
            renderer=document['render_row']['renderer'])
    audit.update(release_id=source.release_id,historical_accuracy_certified=False,runtime_verified=False,
        bounded_pair_only=True,scanline_padding_fixed_carriers=sorted(carriers),
        prior_audit={'path':registry.relative_workspace_path(old_audit),'sha256':registry.sha256_file(old_audit)})
    audit_path=destination/'paired-kit-audit.json';pipeline.write_canonical_json(audit_path,audit)
    complete=copy.deepcopy(complete)
    complete.update(audit_path=str(audit_path.resolve()),audit_sha256=registry.sha256_file(audit_path),
        archives={name:{'sha256_after':registry.sha256_file(candidate/'game/DBDAT'/name)} for name in renderer.ARCHIVES},
        padding_fix_scope='declared replacement clubs only; not an all-season/all-club padding-fix claim',
        prior_receipt={'path':registry.relative_workspace_path(previous),'sha256':registry.sha256_file(previous)})
    complete_path=destination/'complete-kit-receipt.json';pipeline.write_canonical_json(complete_path,complete)
    material_path=destination/'paired-kit-materialisation.json'
    pipeline.write_canonical_json(material_path,{'complete_kit_receipt_path':str(complete_path.resolve()),
        'complete_kit_receipt_sha256':registry.sha256_file(complete_path),'scope':'declared complete-club transaction assets'})
    application_path=destination/'paired-kit-application.json'
    pipeline.write_canonical_json(application_path,{'schema_version':'pm99-coupled-club-kit-application-v1',
        'season':source.season,'source_release_id':source.release_id,
        'source_build_chain_sha256':registry.sha256_file(source.build_chain_path),
        'materialisation_path':str(material_path.resolve()),'materialisation_sha256':registry.sha256_file(material_path),
        'candidate_receipt':{'path':registry.relative_workspace_path(candidate/'candidate-receipt.json'),
            'sha256':registry.sha256_file(candidate/'candidate-receipt.json')},
        'native_proof':{'path':registry.relative_workspace_path(native_proof),'sha256':registry.sha256_file(native_proof)},
        'identity_proof':{'path':registry.relative_workspace_path(identity_proof),'sha256':registry.sha256_file(identity_proof)},
        'difference':{'changed':[r for r in difference['changed'] if r['path'] in {'DBDAT/'+n for n in renderer.ARCHIVES}]},
        'scope':'kit portion of a separately proved coupled database/ground/manager correction; not a kit-only whole-game patch'})
    return application_path,complete_path


def publish(candidate,native_proof,identity_proof,release_id, *, source_release_id=None):
    receipt_path=candidate/'candidate-receipt.json';receipt=json.loads(receipt_path.read_text())
    digest=registry.sha256_file(receipt_path)
    readback=json.loads(native_proof.read_text());identities=json.loads(identity_proof.read_text())
    if (readback['candidate_receipt_sha256']!=digest or identities['candidate_receipt_sha256']!=digest
            or not readback['all_unselected_native_records_identical']
            or identities['introduced_candidate_groups'] or identities['replacement_cross_club_candidates']
            or not identities['stale_portraits_cleared'] or not identities['keeper_recipe_replay_idempotent']):
        raise ValueError('paired publication needs independent exact native and no-new-copy proof')
    pair=json.loads(native.original(receipt['source_pair']).read_text())
    source=(registry.load_registered_release(pair['season'],source_release_id)
            if source_release_id is not None else registry.load_preferred_release(pair['season']))
    if source.release_id!=pair['release_id']:raise ValueError('paired publication baseline no longer preferred')
    original=json.loads(source.package_path.read_text())
    package_path=candidate/'season-package.json';package=json.loads(package_path.read_text())
    if registry.sha256_file(package_path)!=identities['package_sha256']:
        raise ValueError('independent identity proof is stale')
    packages.validate_package(package)
    for artifact in package['artifacts']:
        if artifact.get('relative_path'):verify_recipe_artifact(candidate/artifact['relative_path'],artifact['sha256'])
    proposals=[json.loads(native.original(b).read_text()) for b in pair['proposals']]
    # Publication rechecks the current source guard even when an earlier
    # private native/identity proof predates a newly discovered QA defect.
    from scripts.prepare_paired_whole_club_dispositions_v1 import source_guard
    if source_guard(pair,proposals)!=pair['source_guard']:
        raise ValueError('complete-club source guard changed before publication')
    allowed_clubs={p['before_club']['id'] for p in proposals};allowed_managers={original_club['manager_id']
        for original_club in original['clubs'] if original_club['id'] in allowed_clubs}
    for collection,allowed in (('clubs',allowed_clubs),('managers',allowed_managers)):
        new={r['id']:r for r in package[collection]}
        if {r['id'] for r in original[collection]}!=set(new) or any(new[r['id']]!=r for r in original[collection] if r['id'] not in allowed):
            raise ValueError('paired recipe changed another club or manager')
    before,drift=source_inventory(source);game=candidate/'game';after=pipeline.build_tree_inventory(game)
    difference=pipeline.inventory_difference(before,after)
    corrected=set(identities['corrected_slots'])
    removed={f'DBDAT/MINIFOTO/J96{id:05d}.BMP' for id in corrected}
    allowed_files={f'DBDAT/{name}' for name in receipt['native_hashes']}
    if difference['only_right'] or set(difference['only_left'])-removed or any(r['path'] not in allowed_files for r in difference['changed']):
        raise ValueError('paired game changed unrelated files')
    if any(registry.sha256_file(game/'DBDAT'/name)!=sha for name,sha in receipt['native_hashes'].items()):
        raise ValueError('paired native outputs differ from proved candidate')
    destination=registry.locator_path(pair['season'],release_id).parent
    if destination.exists():raise ValueError('paired registered metadata is immutable')
    outputs=[{'path':'DBDAT/'+name,'sha256':sha,'size':(game/'DBDAT'/name).stat().st_size}
        for name,sha in sorted(receipt['native_hashes'].items())]
    compiler={'schema':'pm99-native-coupled-whole-club-delta-v1','season':pair['season'],
        'season_package_sha256':registry.canonical_document_sha256(package_path),
        'source_season_package_sha256':registry.canonical_document_sha256(source.package_path),
        'source_compiler_receipt_sha256':registry.sha256_file(source.compiler_receipt_path),
        'source_build_chain_sha256':registry.sha256_file(source.build_chain_path),
        'source_game_inventory_fingerprint':before['files_fingerprint'],
        'compilation_mode':'known-good-baseline-complete-coupled-roster-manager-ground-and-kit-delta',
        'players_written':len(corrected),'clubs_written':len(allowed_clubs),'managers_written':len(allowed_managers),
        'outputs':outputs,'difference':difference,'existing_runtime_config_difference':drift,
        'independent_native_proof_sha256':registry.sha256_file(native_proof),
        'independent_identity_proof_sha256':registry.sha256_file(identity_proof),
        'candidate_receipt_sha256':digest,'historical_verification_complete':False,
        'native_XI_scope':'full sourced XI membership and broad positions; opaque mode1 deployment not proved',
        'portrait_policy':'stale inherited faces cleared; no new portrait claim',
        'kit_policy':'source-backed reviewed colours, factory tone; sponsor/fine-pattern simplification declared'}
    destination.mkdir(parents=True);compiler_path=destination/'paired-delta-compiler.json'
    application_path,complete_path=attach_pair_kit_receipts(source,candidate,destination,receipt,native_proof,identity_proof,difference)
    pipeline.write_canonical_json(compiler_path,compiler)
    output_paths={r['path'] for r in outputs}
    chain={'schema_version':'pm99-season-build-chain-v1','season':pair['season'],
        'package_canonical_sha256':compiler['season_package_sha256'],'stages':[
            {'id':'database','receipt_sha256':registry.sha256_file(compiler_path),
             'outputs':{r['path']:r['sha256'] for r in outputs}},
            {'id':'inherited-known-good-files','source_build_chain_sha256':compiler['source_build_chain_sha256'],
             'outputs':{r['path']:r['sha256'] for r in after['files'] if r['path'] not in output_paths}}]}
    chain_path=destination/'build-chain.json';pipeline.write_canonical_json(chain_path,chain)
    manifest=pipeline.read_json_file(source.release_manifest_path)
    manifest['season_document']=pipeline.canonical_json_document_descriptor(package_path,document_id='season-package')
    manifest['output']={'file_count':after['file_count'],'total_bytes':after['total_bytes'],'inventory_fingerprint':after['files_fingerprint']}
    artifacts=[pipeline.external_artifact_descriptor(artifact_id=id,path=path,role='input') for id,path in (
        ('paired-source-receipt',receipt_path),('paired-native-independent-proof',native_proof),
        ('paired-identity-independent-proof',identity_proof),('paired-delta-compiler',compiler_path),
        ('previous-recipe',source.package_path),('previous-build-chain',source.build_chain_path),
        ('previous-compiler-receipt',source.compiler_receipt_path),('build-chain',chain_path))]
    artifacts += [pipeline.external_artifact_descriptor(artifact_id=id,path=path,role='input') for id,path in (
        ('paired-kit-application',application_path),('paired-complete-kit-receipt',complete_path))]
    replaced={a['id'] for a in artifacts}
    manifest['external_artifacts']=sorted([a for a in manifest['external_artifacts'] if a['id'] not in replaced]+artifacts,key=lambda a:a['id'])
    manifest['stages'].append(pipeline.make_stage_record(stage_id='paired-whole-club-'+release_id,
        implementation_path=Path(__file__),input_fingerprints={'previous-release':source.manifest_sha256},
        parameters={'corrected_slots':len(corrected),'clubs':len(allowed_clubs),'no_new_cross_club_candidates':True,
                    'historical_verification_complete':False},external_artifacts=artifacts))
    manifest['stages'].sort(key=lambda s:s['id']);pipeline.validate_release_manifest(manifest)
    metadata=destination/'metadata';metadata.mkdir();manifest_path=metadata/'season-manifest.json';inventory_path=metadata/'output.inventory.json'
    pipeline.write_canonical_json(manifest_path,manifest);pipeline.write_canonical_json(inventory_path,after)
    locator=copy.deepcopy(source.locator)
    for name in ('qa_report_path','qa_report_sha256','historical_role_plan_path','historical_role_delta_path','ownership_plan_path','ownership_delta_path'):
        locator.pop(name,None)
    locator.update(release_id=release_id,game_path=registry.relative_workspace_path(game),
        package_path=registry.relative_workspace_path(package_path),package_canonical_sha256=compiler['season_package_sha256'],
        compiler_receipt_path=registry.relative_workspace_path(compiler_path),build_chain_path=registry.relative_workspace_path(chain_path),
        inventory_path=registry.relative_workspace_path(inventory_path),release_manifest_path=registry.relative_workspace_path(manifest_path),
        game_inventory_fingerprint=after['files_fingerprint'],attestation_path=None,runtime_evidence_path=None,
        technical_status='playable-unverified',qa_status='not-recorded')
    locator['paired_whole_club_candidate_receipt_path']=registry.relative_workspace_path(receipt_path)
    locator['paired_whole_club_candidate_receipt_sha256']=digest
    locator['kit_patch_application_path']=registry.relative_workspace_path(application_path)
    locator['required_file_hashes']={name:registry.sha256_file(game/name) for name in registry.REQUIRED_GAME_FILES}
    visual={name:sha for name,sha in locator.get('required_visual_file_hashes',{}).items() if name not in removed}
    visual.update({r['path']:r['sha256'] for r in outputs if not r['path'].endswith('.FDI')})
    locator['required_visual_file_hashes']=visual
    locator['required_visual_absent_paths']=sorted(set(locator.get('required_visual_absent_paths',[]))|removed)
    pipeline.write_canonical_json(destination/'locator.json',locator)
    pipeline.assert_tree_matches_inventory(source.game_path,before)
    return {'season':pair['season'],'release_id':release_id,'corrected_slots':len(corrected),'registered':False,
            'status':'locator-created; preferred promotion and fresh attestation still required'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','native-proof','identity-proof'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--release-id',required=True);a=p.parse_args()
    print(json.dumps(publish(a.candidate,a.native_proof,a.identity_proof,a.release_id)),flush=True)
