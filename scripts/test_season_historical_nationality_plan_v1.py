import json
from types import SimpleNamespace
import pytest
from scripts import season_historical_nationality_plan_v1 as nationality


def fixture(tmp_path, monkeypatch, source_values=('POR',), declared='ENG'):
    package = {'players': [{'id': 'p', 'carrier_id': 7, 'name': 'Cristiano Ronaldo',
        'facts': {'birth_date': '1985-02-05', 'nationality': declared}}]}
    game = tmp_path / 'game'; (game / 'DBDAT').mkdir(parents=True)
    (game / 'DBDAT/JUG98030.FDI').write_bytes(b'test')
    path = tmp_path / 'package.json'; path.write_text(json.dumps(package))
    release = SimpleNamespace(release_id='current', game_path=game, package_path=path)
    monkeypatch.setattr(nationality.registry, 'load_preferred_release', lambda s: release)
    monkeypatch.setattr(nationality.compiler, '_extract_country_codes_from_textos', lambda p: {'ENGLAND': 30, 'PORTUGAL': 61, 'XXX': 0, 'LATVIA': 72})
    monkeypatch.setattr(nationality.registry, 'relative_workspace_path', lambda p: str(p))
    report = {'schema_version': 'pm99-historical-player-facts-audit-v1', 'season': '2005-06',
        'bindings': {'package_sha256': nationality.registry.sha256_file(path)},
        'players': [{'player_id': 'p', 'carrier_id': 7, 'name': 'Cristiano Ronaldo', 'birth_date': '1985-02-05',
            'fields': {'nationality': {'status': 'conflict', 'recipe_value': declared, 'source_values': list(source_values)}},
            'evidence': [{'source_url': 'https://www.national-football-teams.com/test'}]}]}
    audit = tmp_path / 'audit.json'; audit.write_text(json.dumps(report))
    return audit, report


def test_country_default_is_corrected_only_by_exact_bound_evidence(tmp_path, monkeypatch):
    path, _ = fixture(tmp_path, monkeypatch)
    result = nationality.plan('2005-06', path)
    assert result['updates'][0]['after'] == 'POR'
    assert result['updates'][0]['native_country_code'] == 61


def test_dual_flags_are_not_chosen(tmp_path, monkeypatch):
    path, _ = fixture(tmp_path, monkeypatch, ('POR', 'FRA'))
    assert nationality.plan('2005-06', path)['updates'] == []


def test_alias_is_not_a_change(tmp_path, monkeypatch):
    path, _ = fixture(tmp_path, monkeypatch, ('LVA',), 'LAT')
    assert nationality.plan('2005-06', path)['updates'] == []


def test_stale_or_wrong_schema_audit_is_rejected(tmp_path, monkeypatch):
    path, report = fixture(tmp_path, monkeypatch)
    report['bindings']['package_sha256'] = 'a' * 64; path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='current recipe'):
        nationality.plan('2005-06', path)
    report['schema_version'] = 'random-json'; path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='schema'):
        nationality.plan('2005-06', path)
