"""Provider key guards; source-body authenticity is checked by admission."""
import hashlib

import pytest

from scripts.season_soccerbase_duplicate_source_policy_v1 import person_id


def actor():
    return dict(source_player_id='tempofradi:vamos-janos', source_provider='tempofradi',
        source_profile_url='https://tempofradi.hu/vamos-janos',
        identity_policy='tempofradi-profile-plus-dated-match-archive-identity-v1',
        name='Vámos János', birth_date='1972-01-19', source_profile_sha256='a' * 64)


def test_key_tracks_original_identity_not_display_alias():
    original = actor()
    expected = 'person-tempofradi-' + hashlib.sha256(
        b'https://tempofradi.hu/vamos-janos|1972-01-19').hexdigest()[:24]
    assert person_id(original) == expected
    assert person_id(dict(original, name='J. Vamos')) == expected
    assert person_id(dict(original, birth_date='1972-01-20')) != expected


@pytest.mark.parametrize('change', [
    {'source_player_id': 'tempofradi:another-player'},
    {'source_profile_url': 'http://tempofradi.hu/vamos-janos'},
    {'source_profile_url': 'https://example.com/vamos-janos'},
    {'source_profile_url': 'https://tempofradi.hu/vamos-janos?alternate=1'},
    {'source_profile_url': 'https://tempofradi.hu/vamos-janos/'},
    {'source_profile_url': 'https://user@tempofradi.hu/vamos-janos'},
    {'source_profile_sha256': 'not-a-hash'},
    {'birth_date': '1972-02-30'}, {'name': ''}, {'source_provider': 'unverified'}])
def test_unbound_provider_or_identity_is_rejected(change):
    with pytest.raises(ValueError):
        person_id(dict(actor(), **change))


def test_existing_transfermarkt_and_soccerbase_keys_unchanged():
    assert person_id({'source_player_id': 123}) == 'person-transfermarkt-123'
    assert person_id({'source_player_id': 'soccerbase:123', 'source_provider': 'soccerbase'}) == 'person-soccerbase-123'
    with pytest.raises(ValueError, match='unsupported'):
        person_id(dict(actor(), identity_policy='not-reviewed'))
