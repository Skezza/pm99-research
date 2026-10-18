"""Read ten actual profile numbers using exact PM99 bitmap digit shapes.

No recipe/player values enter decoding. Three previously reviewed, native-bound
original screenshots establish the ten font glyphs. Unknown shapes/geometry
fail rather than guessing. This proves displayed numbers, not historical skill
accuracy or the identity/era of any portrait.
"""
import argparse
from pathlib import Path
from PIL import Image
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline

FIELDS=('speed','stamina','aggression','quality','handling','passing','dribbling','heading','tackling','shooting')
REFERENCE_ROOT=registry.ROOT/'.local/consolidated-audit-20261009/Eastleigh2014-native-delivery-v1'
REFERENCES=tuple(REFERENCE_ROOT/(label+'-profile-visual-review.json') for label in ('flitney','noice','odubade'))


def field_box(index):
    return (335,53+10*index,354,64+10*index) if index<4 else (386,121+13*(index-4),405,132+13*(index-4))


def signatures(image,box):
    crop=image.crop(box).convert('RGB');width,height=crop.size
    def ink(x,y):return max(crop.getpixel((x,y)))<100
    occupied=[x for x in range(width) if any(ink(x,y) for y in range(height))]
    runs=[]
    for x in occupied:
        if not runs or x>runs[-1][-1]+1:runs.append([x])
        else:runs[-1].append(x)
    result=[]
    for run in runs:
        ys=[y for y in range(height) if any(ink(x,y) for x in run)]
        result.append('/'.join(''.join('1' if ink(x,y) else '0' for x in run)
            for y in range(min(ys),max(ys)+1)))
    return result


def build_font(references=REFERENCES):
    font={};proofs=[]
    for path in references:
        review=pipeline.read_json_file(path);screenshot=registry.ROOT/review['screenshot']
        if (review.get('method')!='assistant-original-image-visual-review' or not review.get('original_frame_visually_inspected')
                or not review.get('all_ten_visible_skills_inspected')
                or registry.sha256_file(screenshot)!=review['screenshot_sha256']):
            raise ValueError('font reference must bind a reviewed original profile')
        with Image.open(screenshot) as im:
            if im.size!=(640,480):raise ValueError('unsupported reference geometry')
            for index,field in enumerate(FIELDS):
                value=review['observed_skills'][field]
                if type(value) is not int or not 0<=value<=99:raise ValueError('invalid reference value')
                glyphs=signatures(im,field_box(index));characters=str(value)
                if len(glyphs)!=len(characters):raise ValueError('reference digits do not match their original pixel components')
                for glyph,char in zip(glyphs,characters):
                    if glyph in font and font[glyph]!=char:raise ValueError('conflicting font reference transcription')
                    font[glyph]=char
        proofs.append(dict(review_path=registry.relative_workspace_path(path),review_sha256=registry.sha256_file(path),
            screenshot=review['screenshot'],screenshot_sha256=review['screenshot_sha256']))
    if set(font.values())!=set('0123456789'):raise ValueError('reference font does not cover all ten digits')
    return font,proofs


def decode(image,font):
    if image.size!=(640,480):raise ValueError('unsupported actual profile geometry')
    values={}
    for index,field in enumerate(FIELDS):
        glyphs=signatures(image,field_box(index))
        if not 1<=len(glyphs)<=2 or any(glyph not in font for glyph in glyphs):
            raise ValueError('unknown, clipped or altered actual digit glyph: '+field)
        text=''.join(font[glyph] for glyph in glyphs)
        if len(text)>1 and text.startswith('0'):raise ValueError('unexpected leading-zero skill display')
        value=int(text)
        if not 0<=value<=99:raise ValueError('actual skill outside native range')
        values[field]=value
    return values


def read(screenshot):
    font,references=build_font()
    with Image.open(screenshot) as image:values=decode(image,font)
    return dict(schema='pm99-exact-original-profile-digit-readback-v1',
        screenshot=registry.relative_workspace_path(screenshot),screenshot_sha256=registry.sha256_file(screenshot),
        observed_skills=values,all_ten_exact_glyph_matches=True,reference_font_sources=references,
        implementation_sha256=registry.sha256_file(Path(__file__)),
        recipe_values_used_for_decoding=False,identity_or_historical_rating_approval=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--screenshot',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=read(args.screenshot)
    if args.output:
        if args.output.exists():raise ValueError('original digit proof must not be overwritten')
        pipeline.write_canonical_json(args.output,result)
    print(result['observed_skills'],flush=True)
