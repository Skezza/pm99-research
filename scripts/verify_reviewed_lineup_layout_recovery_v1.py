"""Attest an original lineup frame rejected solely as an unknown screen.

Keep the original failure unchanged. This read-only verifier requires a valid
club identity, exact native input bindings, a reviewed source-XI match, and four
pixel-identical UI regions from a separately successful native lineup capture.
It neither changes runner success nor certifies historical facts by itself.
"""
from pathlib import Path
import hashlib
from PIL import Image
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.capture_registered_season_local_v1 import summary_matches

REGIONS = {
    'lineup-title': (200, 14, 430, 42),
    'player-skill-column-header': (28, 68, 470, 86),
    'training-controls': (480, 368, 629, 438),
    'substitutes-header': (30, 270, 470, 285),
}
NOTE = 'Route capture for line_up expected lineup_screen but saw unknown.'


def require_eligible_summary(summary, release, selector):
    route = summary.get('route_summaries', {}).get('line_up', {})
    identity = route.get('team_identity', {})
    coords = {key: selector[key] for key in ('team_select_x', 'team_select_y',
              'division_select_x', 'division_select_y')}
    if (summary.get('success') is not False
            or summary.get('mode') != 'generic-club-route-capture'
            or summary.get('release_manifest_sha256') != release.manifest_sha256
            or summary.get('output_inventory_fingerprint') != release.locator['game_inventory_fingerprint']
            or summary.get('phase_reached') != 'return_from_line_up'
            or summary.get('dashboard_reached') is not True
            or summary.get('requested_routes') != ['line_up']
            or summary.get('team_name') != selector['team_name']
            or summary.get('team_selection') != coords
            or summary.get('confidence_notes') != [NOTE]
            or summary.get('crash_detected') is not False
            or summary.get('wine_debugger_detected') is not False
            or summary.get('process_exit_code') not in (None, 0)
            or route.get('screen') != 'unknown'
            or route.get('expected_screen') != 'lineup_screen'
            or route.get('return_screen') != 'club_dashboard_screen'
            or identity.get('matched') is not True
            or identity.get('expected') != selector['team_name']
            or not identity.get('expected_normalized')
            or identity.get('observed_normalized') != identity.get('expected_normalized')):
        raise ValueError('lineup recovery is limited to an otherwise valid unknown-screen classification')


def compare_regions(reference_frame, frame):
    result = []
    with Image.open(reference_frame) as ref_image, Image.open(frame) as image:
        if ref_image.size != (640, 480) or image.size != (640, 480):
            raise ValueError('lineup layout needs two original 640x480 client frames')
        ref_image, image = ref_image.convert('RGB'), image.convert('RGB')
        for name, box in REGIONS.items():
            expected, observed = ref_image.crop(box).tobytes(), image.crop(box).tobytes()
            if observed != expected:
                raise ValueError('original lineup static region differs: ' + name)
            result.append(dict(name=name, box=list(box), compared_RGB_bytes=len(expected),
                               sha256=hashlib.sha256(observed).hexdigest(), exact=True))
    return result


def verify(release, evidence, selector, review, reference_release,
           reference_evidence, reference_selector, reference_review):
    evidence, reference_evidence = Path(evidence), Path(reference_evidence)
    summary = pipeline.read_json_file(evidence / 'summary.json')
    transport = pipeline.read_json_file(evidence / 'local-transport.json')
    require_eligible_summary(summary, release, selector)
    if (transport.get('exit_code') != 1 or transport.get('summary_validation_passed') is not False
            or transport.get('release_manifest_sha256') != release.manifest_sha256
            or transport.get('source_inventory_preserved') is not True):
        raise ValueError('recovery needs the unchanged classification-failure transport')
    reference_summary = pipeline.read_json_file(reference_evidence / 'summary.json')
    reference_transport = pipeline.read_json_file(reference_evidence / 'local-transport.json')
    if (not summary_matches(reference_summary, reference_release, selector=reference_selector)
            or reference_transport.get('exit_code') != 0
            or reference_transport.get('summary_validation_passed') is not True):
        raise ValueError('layout reference must independently pass the original runtime gate')
    for item, expected_club in ((review, selector['team_name']),
                                (reference_review, reference_selector['team_name'])):
        if (item.get('original_frame_visually_inspected') is not True
                or item.get('eleven_source_names_match') is not True
                or item.get('observed_club') != expected_club):
            raise ValueError('original frame and source XI need explicit lead review')
    frame = registry.ROOT / review['screenshot']
    reference_frame = registry.ROOT / reference_review['screenshot']
    if (frame.parent.parent != evidence or reference_frame.parent.parent != reference_evidence
            or registry.sha256_file(frame) != review['screenshot_sha256']
            or registry.sha256_file(reference_frame) != reference_review['screenshot_sha256']):
        raise ValueError('reviewed frames must be unchanged originals from their exact capture')
    for native_release, root in ((release, evidence), (reference_release, reference_evidence)):
        if registry.sha256_file(root / 'input-provenance.json') != registry.sha256_file(native_release.compiler_receipt_path):
            raise ValueError('native capture compiler input binding differs')
        hashes = {line.split()[1]: line.split()[0]
                  for line in (root / 'dbdat_override.sha256').read_text().splitlines()
                  if line and not line.startswith('#')}
        for name in ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF',
                     'RIDIESC.PKF', 'MINIESC.PKF', 'NANOESC.PKF'):
            if hashes.get('DBDAT/' + name) != registry.sha256_file(native_release.game_path / 'DBDAT' / name):
                raise ValueError('actual lineup database/asset input differs')
    if registry.sha256_file(release.game_path / 'DAT.PKF') != registry.sha256_file(reference_release.game_path / 'DAT.PKF'):
        raise ValueError('static lineup reference uses another native UI resource')
    regions = compare_regions(reference_frame, frame)
    return dict(schema='pm99-reviewed-original-lineup-layout-recovery-v1',
                verifier_path=registry.relative_workspace_path(Path(__file__)),
                verifier_sha256=registry.sha256_file(Path(__file__)),
                reference_release_id=reference_release.release_id,
                reference_manifest_sha256=reference_release.manifest_sha256,
                season=release.season, release_id=release.release_id,
                manifest_sha256=release.manifest_sha256,
                original_runner_success=False, original_transport_exit_code=1,
                recovery_scope='screen-classification-false-negative-only',
                original_summary_sha256=registry.sha256_file(evidence / 'summary.json'),
                original_transport_sha256=registry.sha256_file(evidence / 'local-transport.json'),
                screenshot_sha256=registry.sha256_file(frame),
                reference_summary_sha256=registry.sha256_file(reference_evidence / 'summary.json'),
                reference_screenshot_sha256=registry.sha256_file(reference_frame),
                native_input_hashes_verified=True, source_XI_lead_review_required=True,
                four_static_regions_exact=regions, independently_verified_lineup_layout=True,
                original_failure_records_preserved=True)
