import numpy as np

from scripts.season_foreign_photo_selection_v1 import taken_year, identity_title, bounded_tight_crop, candidates, face_view, prominent_faces
from scripts.rollout_foreign_portraits_v1 import match


def test_upload_date_is_not_photo_date():
    assert taken_year({'DateTime': {'value': '2024-01-24', 'source': 'mediawiki-metadata'},
                       'ImageDescription': {'value': 'Zinedine Zidane en 2000.'}}, 'File:Zinedine Zidane.jpg')[:2] == (2000, 'source-caption-declared-year')
    assert taken_year({'DateTime': {'value': '2024-01-24', 'source': 'mediawiki-metadata'}}, 'File:Zidane.jpg')[0] is None


def test_homonym_is_not_two_non_adjacent_name_tokens():
    assert not identity_title('Raul Gonzalez', 'File:Raúl Rojas González.jpg')
    assert identity_title('Cristiano Ronaldo', 'File:Cristiano Ronaldo 2007.jpg')
    assert not identity_title('Ronaldo Nazario', 'File:Cristiano Ronaldo 2002.jpg')


def test_statue_is_not_a_player_photo():
    d = {'pages': [{'title': 'File:Escultura de Cristiano Ronaldo.jpg', 'imageinfo': [{
        'extmetadata': {'DateTimeOriginal': {'value': '2016-08-16'}, 'LicenseShortName': {'value': 'CC BY'},
                        'LicenseUrl': {'value': 'https://example.test'}, 'ImageDescription': {'value': 'Escultura'}}}]}]}
    assert candidates(d, 'Cristiano Ronaldo', 2016) == []


def test_narrow_portrait_crop_keeps_face_without_synthesised_pixels():
    image = np.zeros((330, 214, 3), dtype=np.uint8)
    crop = bounded_tight_crop(image, [40, 30, 120, 150])
    assert crop is not None and crop.width <= 214
    assert bounded_tight_crop(image, [-5, 30, 120, 150]) is None


def test_lifetime_identity_still_requires_unique_name_and_dob():
    player = {'name': 'Lionel Messi', 'facts': {'birth_date': '1987-06-24'}}
    row = {'sofifa_id': 158023, 'short_name': 'L. Messi', 'long_name': 'Lionel Messi'}
    assert match(player, {'1987-06-24': {158023: row}})[1]['sofifa_id'] == 158023
    assert match(player, {'1987-06-25': {158023: row}}) is None
    assert match(player, {'1987-06-24': {158023: row, 42: {**row, 'sofifa_id': 42}}}) is None


def test_background_crowd_does_not_make_single_player_ambiguous():
    foreground = [10, 10, 70, 90]
    crowd = [50, 10, 12, 16]
    assert prominent_faces([foreground, crowd]) == [foreground]
    assert len(prominent_faces([foreground, [100, 10, 60, 80], crowd])) == 2


def test_strong_profile_is_not_front_facing():
    assert face_view([0, 0, 100, 110, 30, 40, 70, 40, 50, 65])['passed']
    assert not face_view([0, 0, 100, 110, 30, 40, 40, 40, 55, 65])['passed']


def test_formalwear_and_non_raster_candidates_are_rejected():
    info = {'extmetadata': {'DateTimeOriginal': {'value': '2025-09-04'},
                           'LicenseShortName': {'value': 'CC BY'},
                           'LicenseUrl': {'value': 'https://example.test'}}}
    for title in ['File:Lamine Yamal in suit 2025.jpg', 'File:Lamine Yamal 2025.svg',
                  'File:Lamine Yamal (2025) (cropped).png']:
        assert candidates({'pages': [{'title': title, 'imageinfo': [info]}]}, 'Lamine Yamal', 2025) == []


def test_original_metadata_labelled_upload_is_not_a_shooting_date():
    assert taken_year({'DateTimeOriginal': {'value': 'uploaded 2025-09-04'}}, 'File:Player.jpg')[0] is None


def test_group_caption_homonym_and_conflicting_dates_are_not_approved():
    info = {'extmetadata': {'DateTimeOriginal': {'value': '2016-03-31'},
                           'LicenseShortName': {'value': 'CC BY'},
                           'LicenseUrl': {'value': 'https://example.test'},
                           'ImageDescription': {'value': 'Andres Iniesta'}}}
    assert candidates({'pages': [{'title': 'File:Andres Iniesta v Uruguay 2013.jpg',
                                 'imageinfo': [info]}]}, 'Andres Iniesta', 2016) == []
    for title, name in [('File:Mbappe Messi Neymar (cropped).jpg', 'Kylian Mbappe'),
                        ('File:Roberto Carlos Sosa.jpg', 'Roberto Carlos'),
                        ('File:Cristiano Ronaldo and Andriy Shevchenko, 2007 (cropped).jpg', 'Cristiano Ronaldo')]:
        assert candidates({'pages': [{'title': title, 'imageinfo': [info]}]}, name, 2016) == []
