import hashlib
import json

import pytest

from scripts.compose_historical_photo_materialisation_v1 import compose
from scripts.compose_historical_photo_materialisation_v1 import rebind_unchanged_club_qa


def make_input(tmp_path):
    fifa = tmp_path / 'fifa.json'
    fifa.write_text(json.dumps({'season': '2014-15', 'coverage': {},
                                'players': [{'carrier_id': i, 'name': f'Player {i}',
                                             'target_club': 'Stoke City', 'status': 'native-no-photo'}
                                            for i in range(1, 26)]}))
    qa = tmp_path / 'qa.json'
    document = {'season': '2014-15', 'club': 'Stoke City',
                'schema_version': 'pm99-historical-photo-qa-v1',
                'counts': {'photo-candidate': 0},
                'input_hashes': {'fifa_manifest': hashlib.sha256(fifa.read_bytes()).hexdigest()},
                'players': [{'carrier_id': i, 'status': 'no-photo'} for i in range(1, 26)]}
    qa.write_text(json.dumps(document))
    return fifa, qa, document


def test_matching_hash_and_complete_squad_are_accepted(tmp_path):
    fifa, qa, _ = make_input(tmp_path)
    assert compose(fifa, qa)['coverage']['historical_photo_count'] == 0


def test_stale_input_hash_is_rejected(tmp_path):
    fifa, qa, document = make_input(tmp_path)
    document['input_hashes']['fifa_manifest'] = '0' * 64
    qa.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='different FIFA'):
        compose(fifa, qa)


def test_duplicated_player_cannot_satisfy_squad_count(tmp_path):
    fifa, qa, document = make_input(tmp_path)
    document['players'][-1]['carrier_id'] = 1
    qa.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='duplicate'):
        compose(fifa, qa)


def test_another_clubs_receipt_is_rejected(tmp_path):
    fifa, qa, document = make_input(tmp_path)
    document['club'] = 'Bayern Munich'
    qa.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='declared club'):
        compose(fifa, qa)


def test_composer_accepts_other_club_squad_sizes(tmp_path):
    fifa, qa, document = make_input(tmp_path)
    value = json.loads(fifa.read_text())
    value['players'] = value['players'][:18]
    fifa.write_text(json.dumps(value))
    document['players'] = document['players'][:18]
    document['input_hashes']['fifa_manifest'] = hashlib.sha256(fifa.read_bytes()).hexdigest()
    qa.write_text(json.dumps(document))
    assert len(compose(fifa, qa)['players']) == 18


def test_historical_replacement_has_correct_preview_and_provenance(tmp_path):
    fifa, qa, document = make_input(tmp_path)
    bitmap, preview = tmp_path / 'photo.bmp', tmp_path / 'photo.png'
    bitmap.write_bytes(b'example-bitmap')
    preview.write_bytes(b'example-preview')
    value = json.loads(fifa.read_text())
    value['players'][0].update({'preview_path': 'old-fifa.png', 'sofifa_id': 123,
                               'source_edition': 15, 'era_grade': 'exact-target-edition'})
    fifa.write_text(json.dumps(value))
    document['input_hashes']['fifa_manifest'] = hashlib.sha256(fifa.read_bytes()).hexdigest()
    document['counts']['photo-candidate'] = 1
    document['players'][0].update({'name': 'Player 1', 'status': 'photo-candidate', 'selected': {
        'bitmap': str(bitmap), 'bitmap_sha256': hashlib.sha256(bitmap.read_bytes()).hexdigest(),
        'preview': str(preview), 'source_page': 'https://commons.wikimedia.org/wiki/File:Example',
        'image_url': 'https://upload.wikimedia.org/example.jpg', 'source_sha256': 'a' * 64,
        'photo_date': '2014-08-01', 'licence': 'CC BY', 'artist': 'Example'}})
    qa.write_text(json.dumps(document))
    result = compose(fifa, qa)
    player = result['players'][0]
    assert player['preview_path'] == str(preview)
    assert 'sofifa_id' not in player and 'source_edition' not in player
    assert player['fifa_fallback']['sofifa_id'] == 123
    assert player['photograph_provenance']['artist'] == 'Example'
    assert result['coverage']['era_grade_counts']['dated-historical-photograph'] == 1


def test_completed_face_review_can_be_rebound_only_for_unchanged_club(tmp_path):
    fifa, qa, document = make_input(tmp_path)
    discovery = tmp_path / 'discovery.json'
    discovery.write_text(json.dumps({'players': []}))
    document['input_hashes']['discovery_receipt'] = hashlib.sha256(discovery.read_bytes()).hexdigest()
    qa.write_text(json.dumps(document))
    revised = tmp_path / 'revised.json'
    value = json.loads(fifa.read_text())
    value['players'].append({'carrier_id': 99, 'name': 'Other Club Player', 'target_club': 'Other Club'})
    revised.write_text(json.dumps(value))
    output = tmp_path / 'qa-rebound.json'
    rebind_unchanged_club_qa(fifa, revised, qa, discovery, output)
    assert json.loads(output.read_text())['input_hashes']['fifa_manifest'] == hashlib.sha256(revised.read_bytes()).hexdigest()
    value['players'][0]['name'] = 'Changed Stoke Player'
    revised.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='fresh face review'):
        rebind_unchanged_club_qa(fifa, revised, qa, discovery, tmp_path / 'bad.json')
