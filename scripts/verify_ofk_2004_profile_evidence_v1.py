"""Bind the inspected private OFK profile to its actual uploaded game inputs."""
from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_kit_render_bindings_v1 as renderer
from scripts.verify_paired_profile_runtime_v1 import compare


def verify(candidate, evidence, output, *, screenshot_sha256):
    if output.exists(): raise ValueError('OFK runtime evidence is immutable')
    receipt_path = candidate / 'candidate-receipt.json'
    receipt = pipeline.read_json_file(receipt_path)
    if registry.sha256_file(receipt_path) != registry.sha256_file(evidence / 'input-provenance.json'):
        raise ValueError('OFK profile launched another candidate')
    summary = pipeline.read_json_file(evidence / 'summary.json')
    if not summary.get('success') or not summary['player_profile']['expected_name_token_satisfied']:
        raise ValueError('OFK profile did not complete')
    frame = evidence / 'screens/47_profile_only_damjanac_done.png'
    if registry.sha256_file(frame) != screenshot_sha256:
        raise ValueError('OFK visual review does not bind the inspected original frame')
    uploaded = {line.split()[1]: line.split()[0] for line in
        (evidence / 'dbdat_override.sha256').read_text().splitlines() if line and not line.startswith('#')}
    for relative, digest in receipt['game_hashes'].items():
        if registry.sha256_file(candidate / 'game' / relative) != digest:
            raise ValueError('OFK local candidate input differs')
        if relative.startswith('DBDAT/') and uploaded.get(relative) != digest:
            raise ValueError('OFK actual uploaded game input differs')
    package = pipeline.read_json_file(candidate / 'season-package.json')
    player = next(p for p in package['players'] if p['carrier_id'] == 14605)
    club = next(c for c in package['clubs'] if c['id'] == player['club_id'])
    observed = {'speed':38, 'stamina':46, 'aggression':49, 'quality':59, 'handling':57,
        'passing':49, 'dribbling':28, 'heading':34, 'tackling':34, 'shooting':22}
    if (player['source_name'] != 'Nikola Damjanac' or player['name'] != 'Damjanac'
            or club['name'] != 'OFK Beograd' or player['facts']['nationality'] != 'SRB'
            or player['facts']['height_cm'] != 191 or player['ratings']['values'] != observed):
        raise ValueError('OFK actual visual facts/skills differ from the source recipe')
    dbdat = candidate / 'game/DBDAT'
    palette, palette_source = renderer._palette(dbdat)
    pixels = compare(renderer._record_index(dbdat / 'RIDIESC.PKF')[706], palette, frame)
    if not pixels['passed']: raise ValueError('OFK displayed kit differs from native pixels')
    proof = dict(schema_version='pm99-ofk-original-profile-runtime-proof-v1',
        candidate_receipt_sha256=registry.sha256_file(receipt_path),
        screenshot=registry.relative_workspace_path(frame), screenshot_sha256=screenshot_sha256,
        summary_sha256=registry.sha256_file(evidence / 'summary.json'),
        method='assistant-original-image-visual-review', carrier_id=14605,
        observed_native_name='Damjanac', observed_club='OFK Beograd',
        observed_nationality='YUGOSLAVIA', observed_height="6 feet 3 inches", observed_age=33,
        observed_skills=observed, uploaded_DBDAT_hashes_verified=True,
        local_executable_sha256=receipt['game_hashes']['MANAGPRE.EXE'],
        uploaded_executable_independently_verified=False,
        kit_pixels=pixels, palette_source=palette_source,
        limitations=['Missing portrait allowed; inherited weight not source certified.',
            'Observed age33 recorded; precise month-based engine age algorithm not proved.',
            'TM original annual/feed DOB1971-10-27 differs from Wikipedia1971-10-21; conflict retained.',
            'One actual profile and small kit only, not whole-roster tactical or portrait approval.'])
    pipeline.write_canonical_json(output, proof)
    return proof
