"""Recover a completed TFF delta whose final metadata publication was interrupted.

Never compiles or copies a game, overwrites a locator, or promotes a release.
Accept only the exact saved source plan, recipe, compiler outputs and difference.
Independent verification remains mandatory before promotion.
"""
import json
import re
from pathlib import Path
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_tff_sourced_opening_xi_v1 as source
from scripts import verify_tff_sourced_opening_xi_v1 as verifier
from scripts.season_visual_patch_v1 import source_inventory
from scripts.season_package_compiler_v2 import _extract_country_codes_from_textos


def complete(season, release_id):
    if season!='2009-10' or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,127}',release_id):
        raise ValueError('unsupported pilot season or unsafe recovery release ID')
    locator_path = registry.locator_path(season,release_id)
    destination = locator_path.parent
    if locator_path.exists() or (destination/'metadata').exists():
        raise ValueError('completed metadata is immutable; recovery cannot overwrite it')
    workspace = registry.ROOT/'.local/historical-role-deltas-v1'/season/release_id
    game = workspace/'game'; package_path = workspace/'season-package.json'
    receipt_path = workspace/'role-delta-compiler.json'; saved = workspace/source.FILENAME
    receipt = json.loads(receipt_path.read_text()); plan = json.loads(saved.read_text())
    base = registry.load_preferred_release(season)
    if base.release_id!=plan['source_release_id'] or receipt['compilation_mode']!='known-good-baseline-original-TFF-full-mode1-XI-delta':
        raise ValueError('publication recovery does not extend current exact source baseline')
    source.verify(base,plan)
    package = json.loads(package_path.read_text())
    if package!=source.updated_package(json.loads(base.package_path.read_text()),plan):
        raise ValueError('completed recipe differs from original source plan')
    before,_ = source_inventory(base); after=pipeline.build_tree_inventory(game)
    if (receipt['source_game_inventory_fingerprint']!=before['files_fingerprint']
            or receipt['difference']!=pipeline.inventory_difference(before,after)
            or receipt['season_package_sha256']!=registry.canonical_document_sha256(package_path)
            or receipt['original_opening_plan_sha256']!=registry.sha256_file(saved)
            or receipt['source_compiler_receipt_sha256']!=registry.sha256_file(base.compiler_receipt_path)
            or receipt['source_build_chain_sha256']!=registry.sha256_file(base.build_chain_path)):
        raise ValueError('completed game/recipe/receipt differs from interrupted publication')
    for row in receipt['outputs']:
        if registry.sha256_file(game/row['path'])!=row['sha256']:
            raise ValueError('completed native output changed')
    verifier.verify_players((base.game_path/'DBDAT/JUG98030.FDI').read_bytes(),
        (game/'DBDAT/JUG98030.FDI').read_bytes(),package,plan,
        _extract_country_codes_from_textos(game/'DBDAT/TEXTOS.PKF'))
    chain_path=destination/'build-chain.json';chain=json.loads(chain_path.read_text())
    if chain['stages'][0]['receipt_sha256']!=registry.sha256_file(receipt_path):
        raise ValueError('interrupted build-chain receipt changed')
    manifest=pipeline.read_json_file(base.release_manifest_path)
    manifest['season_document']=pipeline.canonical_json_document_descriptor(package_path,document_id='season-package')
    manifest['output']={'file_count':after['file_count'],'total_bytes':after['total_bytes'],'inventory_fingerprint':after['files_fingerprint']}
    artifacts=[pipeline.external_artifact_descriptor(artifact_id=id,path=path,role='input') for id,path in [
        ('historical-role-plan',workspace/'role-delta-input.json'),('historical-role-delta-compiler',receipt_path),
        ('previous-build-chain',base.build_chain_path),('previous-compiler-receipt',base.compiler_receipt_path),
        ('previous-recipe',base.package_path),('build-chain',chain_path),('original-tff-opening-xi-plan',saved)]]
    replaced={a['id'] for a in artifacts}
    manifest['external_artifacts']=sorted([a for a in manifest['external_artifacts'] if a['id'] not in replaced]+artifacts,key=lambda a:a['id'])
    manifest['stages'].append(pipeline.make_stage_record(stage_id='historical-role-delta-'+release_id,
        implementation_path=Path(__file__),input_fingerprints={'previous-release':base.manifest_sha256},
        parameters={'resumed_metadata_only':True,'changed_role_players':0,'changed_nationality_players':0,
                    'changed_manager_names':0,'changed_club_names':0,'changed_ownership_slots':0,
                    'historical_verification_complete':False},external_artifacts=artifacts))
    manifest['stages'].sort(key=lambda s:s['id']);pipeline.validate_release_manifest(manifest)
    metadata=destination/'metadata';metadata.mkdir()
    manifest_path=metadata/'season-manifest.json'; inventory_path=metadata/'output.inventory.json'
    pipeline.write_canonical_json(manifest_path,manifest);pipeline.write_canonical_json(inventory_path,after)
    locator=dict(base.locator)
    for key in ('qa_report_path','qa_report_sha256'):locator.pop(key,None)
    locator.update(release_id=release_id,game_path=registry.relative_workspace_path(game),
        package_path=registry.relative_workspace_path(package_path),package_canonical_sha256=receipt['season_package_sha256'],
        compiler_receipt_path=registry.relative_workspace_path(receipt_path),inventory_path=registry.relative_workspace_path(inventory_path),
        release_manifest_path=registry.relative_workspace_path(manifest_path),build_chain_path=registry.relative_workspace_path(chain_path),
        game_inventory_fingerprint=after['files_fingerprint'],attestation_path=None,runtime_evidence_path=None,
        technical_status='playable-unverified',qa_status='not-recorded',
        historical_role_plan_path=registry.relative_workspace_path(workspace/'role-delta-input.json'),
        historical_role_delta_path=registry.relative_workspace_path(receipt_path),sourced_mode1_opening_plan_path=registry.relative_workspace_path(saved))
    locator['required_file_hashes']={name:registry.sha256_file(game/name) for name in registry.REQUIRED_GAME_FILES}
    visual=dict(locator.get('required_visual_file_hashes',{}))
    for relative in receipt['ownership_portrait_fallback']['removed_loose_paths']:visual.pop(relative,None)
    visual['DBDAT/MINIFOTO.PKF']=registry.sha256_file(game/'DBDAT/MINIFOTO.PKF')
    locator['required_visual_file_hashes']=visual
    locator['required_visual_absent_paths']=sorted(set(locator.get('required_visual_absent_paths',[]))|
        {f'DBDAT/MINIFOTO/J96{int(k):05d}.BMP' for k in receipt['ownership_portrait_fallback']['directory_offsets']})
    pipeline.write_canonical_json(locator_path,locator)
    pipeline.assert_tree_matches_inventory(base.game_path,before)
    return {'season':season,'release_id':release_id,'resumed_metadata_only':True,'game_rebuilt':False,'registered':False}
