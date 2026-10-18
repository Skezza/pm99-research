from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from scripts import verify_paired_profile_runtime_v1 as runtime


def test_profile_name_matches_runner_punctuation_without_expanding_a_name():
    assert runtime.normalized_profile_name('Marsh-Brown') == runtime.normalized_profile_name('marsh brown')
    assert runtime.normalized_profile_name("N'Gala") == runtime.normalized_profile_name('n gala')
    assert runtime.normalized_profile_name('K Marsh-Brown') != runtime.normalized_profile_name('Keanu Marsh-Brown')
    assert runtime.normalized_profile_name('Brown') != runtime.normalized_profile_name('Marsh-Brown')


def test_unexplained_OCR_suffix_is_not_silently_stripped():
    with pytest.raises(ValueError,match='exact native display'):
        runtime.profile_name_method('Joe Quigley','joe quigley 7 a')
    assert runtime.profile_name_method('Joe Quigley','joe quigley 7 a',{
        'method':'assistant-original-image-visual-review','observed_native_name':'Joe QUIGLEY'
    })=='assistant-original-image-visual-review'
    with pytest.raises(ValueError,match='exact native display'):
        runtime.profile_name_method('Joe Quigley','joe quigley 7 a',{
            'method':'assistant-original-image-visual-review','observed_native_name':'J Quigley'})


def frame(tmp_path, monkeypatch):
    record=SimpleNamespace(width=17,height=20)
    pixels=np.ones((20,17),dtype=np.uint8)
    pixels[0,:]=0;pixels[-1,:]=0;pixels[:,0]=0;pixels[:,-1]=0
    pixels[5:15,7:10]=2
    palette=[(0,0,0),(220,40,30),(240,240,240)]
    monkeypatch.setattr(runtime,'read_top_down_bitmap_rows',lambda _:pixels)
    monkeypatch.setattr(runtime,'bitmap_row_stride',lambda _:20)
    rgb=np.zeros((480,640,3),dtype=np.uint8)
    rgb[162:182,20:37]=runtime.rgb565(palette)[pixels]
    path=tmp_path/'profile.png';Image.fromarray(rgb).save(path)
    return record,palette,path,rgb


def test_named_profile_kit_checks_padded_geometry_and_actual_colours(tmp_path,monkeypatch):
    record,palette,path,_=frame(tmp_path,monkeypatch)
    result=runtime.compare(record,palette,path)
    assert result['passed'] and result['row_stride']==20
    assert result['position']==[20,162]
    assert result['mean_channel_error']==0 and result['maximum_channel_error']==0
    assert result['compared_interior_pixels']>20


def test_profile_kit_does_not_accept_a_wrong_interior_colour(tmp_path,monkeypatch):
    record,palette,path,rgb=frame(tmp_path,monkeypatch)
    rgb[164:180,22:35]=(30,220,40)
    Image.fromarray(rgb).save(path)
    result=runtime.compare(record,palette,path)
    assert not result['passed'] and result['maximum_channel_error']>4


def test_profile_geometry_is_not_silently_rescaled(tmp_path,monkeypatch):
    record,palette,path,_=frame(tmp_path,monkeypatch)
    Image.new('RGB',(1280,960)).save(path)
    with pytest.raises(ValueError,match='runner geometry'):
        runtime.compare(record,palette,path)
    record.width=18
    with pytest.raises(ValueError,match='kit shape'):
        runtime.compare(record,palette,path)
