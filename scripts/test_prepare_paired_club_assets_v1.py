import json
from pathlib import Path
import pytest
from scripts import prepare_paired_club_assets_v1 as assets


@pytest.mark.parametrize('club_count', [1, 2, 3, 5])
def test_comparison_sheet_does_not_crop_any_replacement_club(club_count):
    width, height = assets.comparison_sheet_size(club_count)
    assert width == 320 * club_count
    assert height == 560
    assert (club_count - 1) * 320 + 320 <= width


def test_comparison_sheet_rejects_empty_scope():
    with pytest.raises(ValueError, match='at least one club'):
        assets.comparison_sheet_size(0)


def source(cache, carrier, body):
    _, _, name, url, _ = assets.GROUNDS[carrier]
    path=cache/name;path.write_text(body)
    path.with_name(name+'.source.json').write_text(json.dumps({'url':url,'sha256':assets.registry.sha256_file(path)}))
    return path


@pytest.mark.parametrize('carrier',[3323,3329])
def test_ground_requires_original_url_hash_date_and_club(tmp_path,carrier):
    club,ground,name,url,anchors=assets.GROUNDS[carrier]
    body='<article>'+ground+' '+' '.join(anchors)+'</article>'
    path=source(tmp_path,carrier,body)
    assert assets.ground_source(tmp_path,carrier)[1]['ground']==ground
    path.write_text(body+' tampered')
    with pytest.raises(ValueError,match='SHA mismatch'):assets.ground_source(tmp_path,carrier)
    for omitted in (ground,*anchors):
        source(tmp_path,carrier,body.replace(omitted,''))
        with pytest.raises(ValueError,match='dated'):assets.ground_source(tmp_path,carrier)


def test_kit_transfer_changes_only_pixels_and_retains_installed_wrapper():
    path=assets.ROOT/'.local/season-pipeline-v2/pm99-base-clean/DBDAT/MINIESC.PKF'
    if not path.exists():pytest.skip('native corpus absent')
    record=assets.render._record_index(path)[3323]
    payload=bytearray(record.raw_bitmap);payload[6]^=1
    payload[record.pixel_offset+4]^=1
    result=assets.pixel_payload(record,bytes(payload))
    assert result[:record.pixel_offset]==record.raw_bitmap[:record.pixel_offset]
    assert result[record.pixel_offset+4]==payload[record.pixel_offset+4]
    payload[record.pixel_offset-1]^=1
    with pytest.raises(ValueError):assets.pixel_payload(record,bytes(payload))


def test_private_asset_output_is_never_overwritten(tmp_path):
    output=tmp_path/'complete';output.mkdir()
    with pytest.raises(ValueError,match='immutable'):assets.prepare(tmp_path/'missing',tmp_path/'assets',output)


def test_explicit_ground_specs_bind_another_season_without_default_clubs(tmp_path):
    specs={3313:('Dartford','Princes Park','dated.html','https://example.test/2014-opening',
                 ('August 9th, 2014','Dartford 1 - 2 Wrexham'))}
    path=tmp_path/'dated.html'
    path.write_text('<article>Princes Park August 9th, 2014 Dartford 1 - 2 Wrexham</article>')
    receipt=path.with_name('dated.html.source.json')
    receipt.write_text(json.dumps({'url':specs[3313][3],'sha256':assets.registry.sha256_file(path)}))
    assert assets.ground_source(tmp_path,3313,specs)[1]['club']=='Dartford'
    assert assets.ground_source(tmp_path,3313,specs)[1]['ground']=='Princes Park'
    changed=dict(specs);changed[3313]=(*specs[3313][:4],('August 9th, 2015',))
    with pytest.raises(ValueError,match='dated'):
        assets.ground_source(tmp_path,3313,changed)
    receipt.write_text(json.dumps({'url':'https://example.test/current','sha256':assets.registry.sha256_file(path)}))
    with pytest.raises(ValueError,match='URL/SHA'):
        assets.ground_source(tmp_path,3313,specs)


def test_explicit_asset_scope_cannot_replace_an_unselected_club(tmp_path):
    candidate=tmp_path/'candidate';candidate.mkdir()
    (candidate/'candidate-receipt.json').write_text(json.dumps({'registered':False,
        'publication_authorised':False,'managers':[{'carrier_id':3313}],'season':'2014-15'}))
    (candidate/'season-package.json').write_text(json.dumps({'clubs':[{'carrier_id':3313,'name':'Dartford'}]}))
    with pytest.raises(ValueError,match='scope differs'):
        assets.prepare(candidate,tmp_path/'assets',tmp_path/'out',ground_specs={3317:('Barnet',)})
    with pytest.raises(ValueError,match='identity differs'):
        assets.prepare(candidate,tmp_path/'assets',tmp_path/'out',ground_specs={3313:('Barnet',)})


def test_asset_catalogue_must_match_target_season(tmp_path):
    candidate=tmp_path/'candidate';candidate.mkdir();art=tmp_path/'assets';art.mkdir()
    (candidate/'candidate-receipt.json').write_text(json.dumps({'registered':False,
        'publication_authorised':False,'managers':[{'carrier_id':3313}],'season':'2014-15'}))
    (candidate/'season-package.json').write_text(json.dumps({'clubs':[{'carrier_id':3313,'name':'Dartford'}]}))
    (art/'render-bindings.json').write_text('{}')
    (art/'kit-catalogue.json').write_text(json.dumps({'season':{'label':'2021/22'}}))
    with pytest.raises(ValueError,match='another target season'):
        assets.prepare(candidate,art,tmp_path/'out',ground_specs={3313:('Dartford',)})
