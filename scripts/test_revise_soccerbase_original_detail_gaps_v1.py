import hashlib
import json
import pytest
from scripts import revise_soccerbase_original_detail_gaps_v1 as revision
from scripts import season_release_registry_v1 as registry


def retained(tmp_path):
    raw=tmp_path/'original.html';raw.write_bytes(b'original')
    receipt=tmp_path/'original.source.json'
    digest=hashlib.sha256(raw.read_bytes()).hexdigest()
    receipt.write_text(json.dumps({'url':'https://www.soccerbase.com/players/player.sd?player_id=1','sha256':digest}))
    return {'raw_sources':[{'path':raw.name,'sha256':digest,
        'source_receipt_path':receipt.name,'source_receipt_sha256':hashlib.sha256(receipt.read_bytes()).hexdigest(),
        'url':'https://www.soccerbase.com/players/player.sd?player_id=1'}]}


@pytest.mark.parametrize('problem',['unchanged','changed-bytes','changed-url','forged-sha'])
def test_reused_completed_parses_are_hash_and_original_url_bound(tmp_path,monkeypatch,problem):
    monkeypatch.setattr(revision,'ROOT',tmp_path)
    row=retained(tmp_path)
    if problem=='unchanged':revision.rehash_retained(row);return
    if problem=='changed-bytes':(tmp_path/'original.html').write_bytes(b'changed')
    if problem=='changed-url':(tmp_path/'original.source.json').write_text('{}')
    if problem=='forged-sha':row['raw_sources'][0]['sha256']='fake'
    with pytest.raises(ValueError):revision.rehash_retained(row)
