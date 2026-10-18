"""Runner numbering can vary; missing or ambiguous original frames refuse."""
import pytest
from scripts.review_rating_frames_20261011 import lineup_frame

@pytest.mark.parametrize('number',['022','024','031'])
def test_unique_actual_lineup_frame_with_variable_number(tmp_path,number):
    screens=tmp_path/'screens';screens.mkdir()
    frame=screens/(number+'_line_up_inspect.png');frame.touch()
    (screens/'025_return_from_line_up.png').touch()
    assert lineup_frame(tmp_path)==frame

def test_missing_original_lineup_frame_refuses(tmp_path):
    with pytest.raises(ValueError,match='one exact original'):
        lineup_frame(tmp_path)

def test_multiple_original_lineup_frames_refuse(tmp_path):
    screens=tmp_path/'screens';screens.mkdir()
    for number in ['022','024']:(screens/(number+'_line_up_inspect.png')).touch()
    with pytest.raises(ValueError,match='one exact original'):
        lineup_frame(tmp_path)
