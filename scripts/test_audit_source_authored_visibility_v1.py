import hashlib
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import audit_source_authored_visibility_v1 as gate
from scripts import season_tempofradi_whole_roster_v1 as ftc_roster


def owner(club, flag):
    return {'club_carrier_id': club, 'flag': flag, 'mode_byte': 1,
            'row_flag_offset': club * 100 + flag}


class VisibilityGateTests(unittest.TestCase):
    def test_module_imports_at_canonical_scripts_namespace(self):
        self.assertEqual(gate.__name__, 'scripts.audit_source_authored_visibility_v1')
        self.assertTrue((gate.ROOT / 'scripts').is_dir())
        self.assertTrue((gate.ROOT / 'upstream/pm99-skezmod-db-editor').is_dir())

    def test_stale_artifact_identity_is_not_current(self):
        stale = {'name': 'Old Person', 'source_name': 'Old Person',
                 'facts': {'birth_date': '1980-01-02'},
                 'person_id': 'person-transfermarkt-12'}
        self.assertFalse(gate._matches_person(stale, {'name': 'New Person',
            'birth_date': '1980-01-02', 'source_provider': 'transfermarkt',
            'source_player_id': 11}))

    def test_provider_identity_allows_roster_display_alias(self):
        current = {'name': 'Siggi Eyjolfsson', 'source_name': 'Siggi Eyjolfsson',
            'facts': {'birth_date': '1973-12-01'},
            'person_id': 'person-wikipedia-896de5acb7db519d8e6b2e88'}
        self.assertTrue(gate._matches_person(current, {'name': 'Sigurður Ragnar Eyjólfsson',
            'birth_date': '1973-12-01', 'source_provider': 'wikipedia',
            'source_player_id': 'wikipedia:Sigur%C3%B0ur_Ragnar_Eyj%C3%B3lfsson'}))

    def test_hlsz_key_url_and_shared_person_namespace(self):
        url = 'https://hlsz.wsg.hu/1977-09-17/rob-kornel'
        identity = {'name': 'Rob Kornél', 'birth_date': '1977-09-17',
            'source_provider': 'hlsz',
            'source_player_id': 'hlsz:' + hashlib.sha256(url.encode()).hexdigest()[:24],
            'source_profile_url': url, 'source_profile_sha256': 'a' * 64,
            'identity_policy': 'tempofradi-profile-plus-dated-match-archive-identity-v1'}
        expected_id = 'person-tempofradi-e786512c7a8b2b37783d1a72'
        self.assertEqual(ftc_roster.person_key(identity), expected_id)
        current = {'name': 'Rob', 'source_name': 'Rob Kornél',
            'facts': {'birth_date': '1977-09-17'}, 'person_id': expected_id}
        self.assertTrue(gate._matches_person(current, identity))
        wrong_url = copy.deepcopy(identity)
        wrong_url['source_profile_url'] = 'https://hlsz.wsg.hu/1977-09-17/not-rob'
        with self.assertRaisesRegex(ValueError, 'local identity key'):
            gate._matches_person(current, wrong_url)

    def test_wrong_source_body_sha_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = root / 'body.html'
            body.write_bytes(b'actual body')
            old_root = gate.ROOT
            gate.ROOT = root
            try:
                with self.assertRaisesRegex(ValueError, 'SHA-256 differs'):
                    gate._verify_source_bodies({'body': {
                        'path': 'body.html', 'sha256': hashlib.sha256(b'wrong').hexdigest()}}, [])
            finally:
                gate.ROOT = old_root

    def test_flag_one_only_requires_runner_confirmation(self):
        result = gate.classify_owners([], [owner(4, 1)], 4)
        self.assertEqual(result['status'], 'runner-confirmation-required-flagged-declared-owner')
        self.assertEqual(result['active_owners'], [])

    def test_flag_zero_declared_owner_is_visible(self):
        result = gate.classify_owners([owner(4, 0)], [], 4)
        self.assertEqual(result['status'], 'visible-single-active-declared-owner')

    def test_additional_active_owner_is_conflict(self):
        result = gate.classify_owners([owner(4, 0), owner(8, 0)], [], 4)
        self.assertEqual(result['status'], 'active-owner-conflict-or-duplicate')

    def test_flagged_source_parent_is_not_double_active(self):
        # The consumed/source carrier can retain a dormant row after a move.
        result = gate.classify_owners([owner(8, 0)], [owner(4, 1)], 8)
        self.assertEqual(result['status'], 'visible-single-active-declared-owner')
        self.assertEqual([r['club_carrier_id'] for r in result['active_owners']], [8])
        self.assertEqual([r['club_carrier_id'] for r in result['flagged_owners']], [4])

    def test_unknown_prefixed_schema_is_reported_only_after_sha_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release_dir, game_dir = root / 'release', root / 'game'
            release_dir.mkdir(); (game_dir / 'DBDAT').mkdir(parents=True)
            plan_path = release_dir / 'unknown-opening-exchange.json'
            raw = b'{"schema":"pm99-unrecognized-opening-exchange-v99"}'
            plan_path.write_bytes(raw)
            package_path = release_dir / 'season-package.json'
            package_path.write_text(json.dumps({'artifacts': [{
                'id': 'opening-identity-exchange-unknown',
                'relative_path': plan_path.name,
                'sha256': hashlib.sha256(raw).hexdigest()}]}))
            (game_dir / 'DBDAT/EQ98030.FDI').write_bytes(b'eq')
            (game_dir / 'DBDAT/JUG98030.FDI').write_bytes(b'jug')
            release = SimpleNamespace(season='2000-01',
                release_id='test-unknown-schema', package_path=package_path,
                game_path=game_dir, manifest_sha256='0' * 64)
            old_root = gate.ROOT
            gate.ROOT = root
            try:
                with patch.object(gate.registry, 'load_registered_release', return_value=release):
                    result = gate.audit_release('2000-01', 'test-unknown-schema')
                    self.assertEqual(result['coverage']['coverage_status'], 'unsupported-schema-present')
                    self.assertFalse(result['coverage']['whole_workspace_complete'])
                    self.assertEqual(result['coverage']['unsupported_prefixed_artifacts'][0]['observed_schema'],
                        'pm99-unrecognized-opening-exchange-v99')
                    plan_path.write_bytes(b'{"schema":"pm99-unrecognized-opening-exchange-v99","changed":true}')
                    with self.assertRaisesRegex(ValueError, 'artifact hash differs'):
                        gate.audit_release('2000-01', 'test-unknown-schema')
            finally:
                gate.ROOT = old_root

    def test_cli_requires_one_explicit_release_and_output(self):
        with self.assertRaises(SystemExit) as exc:
            gate.main([])
        self.assertEqual(exc.exception.code, 2)

    def test_cli_writes_one_explicit_release_report(self):
        with tempfile.TemporaryDirectory(dir=gate.ROOT) as tmp:
            directory = Path(tmp)
            output = directory / 'one-release.json'
            relative = output.relative_to(gate.ROOT).as_posix()
            report = {'season': '2000-01', 'release_id': 'exact-r1',
                'matched_current_people': 0,
                'coverage': {'coverage_status': 'scoped-complete-not-global',
                    'unsupported_prefixed_artifacts': []}}
            with patch.object(gate, 'audit_release', return_value=report) as audit:
                code = gate.main(['--season', '2000-01', '--release-id', 'exact-r1',
                                  '--output', relative])
            audit.assert_called_once_with('2000-01', 'exact-r1')
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.read_text()), report)


if __name__ == '__main__':
    unittest.main()
