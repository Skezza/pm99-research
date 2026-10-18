"""Retain the dated Genoa launch photograph and actual installed icon evidence.

No game or preferred release is modified. Photographs are research references,
not game artwork. Existing captures are reused only after URL/SHA verification.
"""
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw

from scripts.capture_italian_period_kits_20261010 import capture
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_kit_render_bindings_v1 as render
from scripts.probe_sourced_factory_kit_v1 import kit_image

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/genoa-kit-2021-v1'
URL = 'https://www.footyheadlines.com/2021/07/genoa-21-22-home-kit-released.html'


def main():
    primary = ROOT / 'source-cache/Kappa-launch.html'
    primary_url = 'https://media.basicpress.com/contenuti/media/resultMedia.asp?ID=160831'
    capture(primary_url, primary)
    original = BeautifulSoup(primary.read_bytes(), 'html.parser')
    original_text = original.get_text(' ', strip=True)
    original_photo_url = 'https://media.basicpress.com/media/media/160/160831_001.JPG'
    if ('16/07/2021' not in original_text or '2021-2022 sports season' not in original_text
            or not original.find('img', src=original_photo_url)):
        raise ValueError('original Kappa launch date/season/photograph linkage differs')
    capture(original_photo_url, ROOT / 'source-cache/Kappa-original.jpg')
    page = ROOT / 'source-cache/launch.html'
    capture(URL, page)
    soup = BeautifulSoup(page.read_bytes(), 'html.parser')
    heading = soup.find('h1')
    text = soup.get_text(' ', strip=True)
    if (not heading or heading.get_text(strip=True) != 'Genoa 21-22 Home Kit Released'
            or 'Jul 16, 2021' not in text
            or 'classic red and blue four-quarter design' not in text):
        raise ValueError('original dated target-season launch identity differs')
    images = sorted({urljoin(URL, i['src']) for i in soup.find_all('img', src=True)
                     if 'new-genoa-cfc-21-22-home-kit' in i['src']})
    if len(images) != 1:
        raise ValueError('original launch no longer links one exact home photograph')
    photo = ROOT / 'source-cache/home.jpg'
    capture(images[0], photo)
    release = registry.load_preferred_release('2021-22')
    package = pipeline.read_json_file(release.package_path)
    if next(c['name'] for c in package['clubs'] if int(c['carrier_id']) == 207) != 'Genoa':
        raise ValueError('current carrier no longer identifies Genoa')
    palette, palette_source = render._palette(release.game_path / 'DBDAT')
    sheet = Image.new('RGB', (900, 340), '#18212a')
    draw = ImageDraw.Draw(sheet)
    records = []
    for index, archive in enumerate(render.ARCHIVES):
        record = render._record_index(release.game_path / 'DBDAT' / archive)[207]
        img = kit_image(record, palette, scale=4)
        sheet.paste(img, (20 + index * 290, 40))
        draw.text((20 + index * 290, 15), archive + ' / Genoa207', fill='white')
        records.append(dict(archive=archive, width=record.width, height=record.height,
                            bitmap_sha256=render.sha256_bytes(record.raw_bitmap)))
    image_path = ROOT / 'installed-three-sizes.png'
    sheet.save(image_path)
    output = ROOT / 'source-and-installed-evidence.json'
    evidence = dict(season='2021-22', carrier_id=207, club='Genoa',
        release_id=release.release_id, manifest_sha256=release.manifest_sha256,
        source_launch=pipeline.read_json_file(page.with_name(page.name + '.source.json')),
        source_photo=pipeline.read_json_file(photo.with_name(photo.name + '.source.json')),
        installed_records=records, palette=palette_source,
        comparison_path=registry.relative_workspace_path(image_path),
        comparison_sha256=registry.sha256_file(image_path),
        source_visual_review_pending=True, game_modified=False)
    if output.exists() and pipeline.read_json_file(output) != evidence:
        raise ValueError('retained evidence belongs to different source/game bytes')
    if not output.exists():
        pipeline.write_canonical_json(output, evidence)
    print(dict(evidence=str(output), game_modified=False), flush=True)


if __name__ == '__main__':
    main()
