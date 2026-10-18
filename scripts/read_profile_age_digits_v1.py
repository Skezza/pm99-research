"""Read white native age digits using the already-bound exact PM99 font.

Pure pixel analysis, no image output and no recipe values used for decoding.
"""
from pathlib import Path
from PIL import Image

from scripts import read_profile_skill_digits_v1 as digits
from scripts import season_release_registry_v1 as registry


def decode(image, font):
    if image.size != (640,480):
        raise ValueError('unsupported original profile age geometry')
    crop=image.crop((40,74,60,85)).convert('RGB')
    mask=Image.new('RGB',crop.size,'white')
    mask.putdata([(0,0,0) if min(pixel)>200 else (255,255,255) for pixel in crop.getdata()])
    glyphs=digits.signatures(mask,(0,0,*mask.size))
    if not 1<=len(glyphs)<=2 or any(g not in font for g in glyphs):
        raise ValueError('unknown, clipped or altered original age glyph')
    text=''.join(font[g] for g in glyphs)
    if text.startswith('0'):
        raise ValueError('unexpected original age leading zero')
    return int(text)


def read(screenshot):
    font,references=digits.build_font()
    with Image.open(screenshot) as image:
        age=decode(image,font)
    return dict(schema='pm99-exact-original-profile-age-digit-readback-v1',
        screenshot=registry.relative_workspace_path(screenshot),screenshot_sha256=registry.sha256_file(screenshot),
        observed_age=age,reference_font_sources=references,recipe_values_used_for_decoding=False,
        implementation_sha256=registry.sha256_file(Path(__file__)),
        reference_font_reader_sha256=registry.sha256_file(Path(digits.__file__)),
        historical_birthday_or_identity_approved=False)
