"""Bind a bench repair's actual named profile to its exact native inputs."""
import json
from pathlib import Path

from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.verify_paired_profile_runtime_v1 import profile_name_method


def verify(release, evidence, visual_review, output, *, carrier=None):
    if output.exists():
        raise ValueError('within-club runtime proof is immutable')
    plan = json.loads((registry.ROOT / release.locator['ownership_plan_path']).read_text())
    from scripts import season_within_club_reserve_repair_v1 as source
    from scripts import season_stoke_original_alias_reserve_v1 as original_alias
    from scripts import season_shtanyuk_2002_coupled_alias_v1 as coupled_alias
    verifier = {source.SCHEMA: source, original_alias.SCHEMA: original_alias,
        coupled_alias.SCHEMA: coupled_alias}.get(plan['schema_version'])
    expected_rows = 2 if verifier is coupled_alias else 1
    if verifier is None or len(plan['updates']) != expected_rows:
        raise ValueError('runtime verifier needs an explicit single within-club repair')
    verifier.verify_plan(registry.load_registered_release(release.season, plan['release_id']), plan)
    selected = [r for r in plan['updates'] if carrier is None or r['carrier_id'] == carrier]
    if len(selected) != 1:
        raise ValueError('runtime profile requires one explicitly selected source-plan actor')
    package = json.loads(release.package_path.read_text())
    player = next(p for p in package['players'] if p['carrier_id'] == selected[0]['carrier_id'])
    club = next(c for c in package['clubs'] if c['id'] == player['club_id'])
    if registry.sha256_file(release.compiler_receipt_path) != registry.sha256_file(evidence / 'input-provenance.json'):
        raise ValueError('runtime launched another repair provenance')
    summary = json.loads((evidence / 'summary.json').read_text())
    profile = summary.get('player_profile', {})
    if (summary.get('success') is not True or summary.get('wine_debugger_detected') or
            summary.get('process_exit_code') not in (None, 0) or
            profile.get('expected_name_token_satisfied') is not True):
        raise ValueError('named reserve profile did not complete successfully')
    launched = {line.split()[1]: line.split()[0] for line in
        (evidence / 'dbdat_override.sha256').read_text().splitlines() if line and not line.startswith('#')}
    for name in ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF',
                 'RIDIESC.PKF', 'MINIESC.PKF', 'NANOESC.PKF'):
        if launched.get('DBDAT/' + name) != registry.sha256_file(release.game_path / 'DBDAT' / name):
            raise ValueError('actual runner native/archive inputs differ from repair')
    shot = evidence / 'screens' / Path(profile['screenshot']).name
    visual = json.loads(visual_review.read_text())
    if (visual.get('method') != 'assistant-original-image-visual-review' or
            visual.get('screenshot_sha256') != registry.sha256_file(shot) or
            visual.get('observed_club') != club['name']):
        raise ValueError('original profile club review is missing or stale')
    name_method = profile_name_method(player['name'], profile['player_name_ocr_normalized'], visual)
    proof = {'schema_version': 'pm99-within-club-reserve-named-runtime-proof-v1',
        'season': release.season, 'release_id': release.release_id,
        'carrier_id': player['carrier_id'], 'source_name': player['source_name'],
        'native_name': player['name'], 'club': club['name'],
        'package_sha256': registry.sha256_file(release.package_path),
        'ownership_plan_sha256': registry.sha256_file(registry.ROOT / release.locator['ownership_plan_path']),
        'compiler_receipt_sha256': registry.sha256_file(release.compiler_receipt_path),
        'evidence': registry.relative_workspace_path(evidence),
        'summary_sha256': registry.sha256_file(evidence / 'summary.json'),
        'screenshot': registry.relative_workspace_path(shot), 'screenshot_sha256': registry.sha256_file(shot),
        'visual_review_sha256': registry.sha256_file(visual_review),
        'name_verification_method': name_method, 'native_inputs_hash_verified': True,
        'scope': 'actual reserve name/club; unchanged kits and no new portrait, not complete historical clearance'}
    pipeline.write_canonical_json(output, proof)
    return proof
