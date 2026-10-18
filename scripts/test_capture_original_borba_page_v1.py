import pytest
from scripts.capture_original_borba_page_v1 import original_download_url


def document(number=12,limit=12):
    return (f'<title>Borba, 11. 07. 2005., S. {number} — Library</title>'
        f'<script>var lastPage = {limit};</script>'
        f'<form id="download-jpg" method="post" action="https://pretraziva.rs/download/borba--2005-07-11--{number}.jpg"></form>').encode()


def test_exact_public_original_form():
    assert original_download_url(document()).endswith('--12.jpg')


@pytest.mark.parametrize('number',[0,13,14])
def test_outside_original_issue_is_not_a_source_page(number):
    with pytest.raises(ValueError):original_download_url(document(number))


@pytest.mark.parametrize('old,new',[
    (b'2005., S.',b'2006., S.'),(b'method="post"',b'method="get"'),
    (b'https://pretraziva.rs',b'https://other.example'),
    (b'var lastPage = 12;',b'var lastPage = 12; var lastPage = 13;'),
    (b'var lastPage = 12;',b'')])
def test_wrong_issue_endpoint_or_ambiguous_bounds_rejected(old,new):
    with pytest.raises(ValueError):original_download_url(document().replace(old,new))
