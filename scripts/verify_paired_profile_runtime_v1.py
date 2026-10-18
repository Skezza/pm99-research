"""Bind an actual profile's person, club and padded kit pixels to the candidate."""
import argparse
import io
import json
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from PIL import Image
from scripts import season_kit_render_bindings_v1 as renderer
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.verify_compact_kit_runtime_v6 import rgb565
from app.bitmap_pixel_rows import read_top_down_bitmap_rows,bitmap_row_stride


def normalized_profile_name(name):
    """Match the runner's OCR punctuation normalisation, never expand initials."""
    return re.sub(r'[^a-z0-9]+',' ',name.lower()).strip().split()


def profile_name_method(expected, observed, reviewed=None):
    if normalized_profile_name(expected)==normalized_profile_name(observed):
        return 'runner-OCR-exact-native-name'
    # The caller first verifies this review's original-frame SHA. Never strip
    # unexplained OCR suffixes or silently accept a substring/expanded initial.
    if (reviewed is not None and reviewed.get('method')=='assistant-original-image-visual-review'
            and reviewed.get('observed_native_name','').casefold()==expected.casefold()):
        return reviewed['method']
    raise ValueError('actual profile name differs from the exact native display')


def compare(record,palette,screenshot):
    if (record.width,record.height)!=(17,20):raise ValueError('unexpected profile kit shape')
    full=np.asarray(read_top_down_bitmap_rows(record));opaque=full!=0;mask=opaque.copy();padded=np.pad(opaque,1)
    for dy in range(3):
        for dx in range(3):mask &= padded[dy:dy+20,dx:dx+17]
    if mask.sum()<20:raise ValueError('too few unblended profile-kit pixels')
    expected=rgb565(palette)[full];observed=np.asarray(Image.open(screenshot).convert('RGB'),dtype=np.int16)
    if observed.shape!=(480,640,3):raise ValueError('unsupported actual runner geometry')
    best=None
    for y in range(155,174):
        for x in range(14,28):
            errors=np.abs(observed[y:y+20,x:x+17]-expected)[mask]
            row=(float(errors.mean()),x,y,int(errors.max()))
            if best is None or row<best:best=row
    mean,x,y,maximum=best
    return {'passed':maximum<=4,'position':[x,y],'row_stride':bitmap_row_stride(record),
        'compared_interior_pixels':int(mask.sum()),'mean_channel_error':mean,'maximum_channel_error':maximum,
        'excluded':['transparent zero','one-pixel blended silhouette boundary','scanline padding']}


def verify(candidate,evidence,carrier,output,visual_review=None):
    if output.exists():raise ValueError('paired runtime proof is immutable')
    receipt=candidate/'candidate-receipt.json';provenance=evidence/'input-provenance.json'
    if registry.sha256_file(receipt)!=registry.sha256_file(provenance):raise ValueError('profile launched another candidate')
    package=json.loads((candidate/'season-package.json').read_text());players={p['carrier_id']:p for p in package['players']}
    player=players[carrier];club=next(c for c in package['clubs'] if c['id']==player['club_id'])
    summary=json.loads((evidence/'summary.json').read_text());profile=summary.get('player_profile',{})
    if not summary.get('success') or not profile.get('expected_name_token_satisfied'):
        raise ValueError('runner did not complete the named profile')
    launched={line.split()[1]:line.split()[0] for line in (evidence/'dbdat_override.sha256').read_text().splitlines() if line and not line.startswith('#')}
    for name,sha in json.loads(receipt.read_text())['native_hashes'].items():
        if launched.get('DBDAT/'+name)!=sha or registry.sha256_file(candidate/'game/DBDAT'/name)!=sha:
            raise ValueError('profile actual native/archive hash differs from candidate')
    screenshot=evidence/'screens'/Path(profile['screenshot']).name
    reviewed=None
    if visual_review is not None:
        reviewed=json.loads(visual_review.read_text())
        if (reviewed.get('method')!='assistant-original-image-visual-review'
                or reviewed.get('screenshot_sha256')!=registry.sha256_file(screenshot)):
            raise ValueError('visual club review does not bind the original runner frame')
    name_method=profile_name_method(player['name'],profile['player_name_ocr_normalized'],reviewed)
    with Image.open(screenshot) as image:
        buffer=io.BytesIO();image.crop((38,161,226,182)).resize((752,84)).save(buffer,format='PNG')
    if visual_review is None:
        text=subprocess.run(['tesseract','stdin','stdout','--psm','7'],input=buffer.getvalue(),capture_output=True,check=True).stdout.decode().strip()
        method='local-tesseract'
    else:
        text=reviewed['observed_club'];method=reviewed['method']
    if text.casefold()!=club['name'].casefold():raise ValueError('actual profile shows another club: '+text)
    dbdat=candidate/'game/DBDAT';palette,source=renderer._palette(dbdat)
    record=renderer._record_index(dbdat/'RIDIESC.PKF')[club['carrier_id']]
    pixels=compare(record,palette,screenshot)
    if not pixels['passed']:raise ValueError('actual kit pixels do not match padded native bitmap')
    proof={'schema_version':'pm99-paired-named-profile-and-kit-runtime-v1','candidate_receipt_sha256':registry.sha256_file(receipt),
        'evidence':registry.relative_workspace_path(evidence),'summary_sha256':registry.sha256_file(evidence/'summary.json'),
        'screenshot':registry.relative_workspace_path(screenshot),'screenshot_sha256':registry.sha256_file(screenshot),
        'player_carrier_id':carrier,'source_name':player['source_name'],'native_name':player['name'],'club':club['name'],
        'observed_club':text,'club_verification_method':method,'name_verification_method':name_method,
        'runner_name_OCR':profile['player_name_ocr_normalized'],
        'native_inputs_hash_verified':True,'kit_pixels':pixels,'runtime_palette':source,
        'scope':'actual named-player membership and small displayed kit; not complete mode1 tactical deployment or portrait approval'}
    pipeline.write_canonical_json(output,proof);return proof


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','evidence','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--carrier',type=int,required=True);p.add_argument('--visual-review',type=Path)
    a=p.parse_args();r=verify(a.candidate,a.evidence,a.carrier,a.output,a.visual_review)
    print(json.dumps({'club':r['club'],'name':r['native_name'],'kit_pixels':r['kit_pixels']}),flush=True)
