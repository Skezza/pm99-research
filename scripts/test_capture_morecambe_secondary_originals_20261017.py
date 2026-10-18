import pytest
from scripts import capture_morecambe_secondary_originals_20261017 as subject

URL = 'https://www.southportcentral.co.uk/players/player-details/?id=696'


def test_security_challenge_alone_is_not_a_player_biography():
    with pytest.raises(ValueError, match='body absent'):
        subject.validate_source(b'<html>challenge-platform</html>' * 100, URL)


def test_another_publishers_challenge_still_uses_the_general_guard():
    with pytest.raises(Exception, match='access-control'):
        subject.validate_source(b'<html>challenge-platform</html>' * 100, 'https://www.11v11.com/players/john-norman-9941/')


def test_original_complete_southport_profile_is_not_a_footer_false_positive():
    path = subject.old.ROOT / 'morecambe2000-kenny-official-club-archive-literal-body-v2.html'
    if not path.exists():
        pytest.skip('local original Southport profile unavailable')
    raw = path.read_bytes()
    assert b'challenge-platform' in raw
    subject.validate_source(raw, URL)
    with pytest.raises(ValueError):
        subject.validate_source(raw.replace(b'1976-09-30', b'1976-09-29'), URL)
