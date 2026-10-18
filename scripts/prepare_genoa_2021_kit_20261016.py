"""Project a reviewed original 2021 shirt onto factory geometry, Genoa207 only.

The fixed fabric crops exclude the background, crest and supplier marks. The
photograph supplies colour and fabric detail; the original PM99 art supplies
shadows, silhouette, seams and all three native record wrappers.
"""
from pathlib import Path
from PIL import Image

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_kit_render_bindings_v1 as render
from scripts import cascade_compact_kit_v6 as cascade
from scripts import probe_sourced_factory_kit_v1 as probe
from scripts.prepare_reviewed_kit_delta_v1 import extend_complete_receipt, verify_sources
from scripts.capture_genoa_2021_kit_20261016 import ROOT
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

# Coordinates refer to the complete, SHA-bound 1500x1113 Kappa launch image.
CROPS = ((85, 570, 125, 690), (180, 610, 600, 1080), (645, 575, 680, 675))


def fabric_canvas(image):
    if image.size != (1500, 1113):
        raise ValueError('original Kappa photograph dimensions differ')
    canvas = Image.new('RGB', (100, 100))
    for box, target, size in zip(CROPS, ((0, 0), (31, 0), (69, 0)),
                                 ((31, 100), (38, 100), (31, 100))):
        canvas.paste(image.convert('RGB').crop(box).resize(size, Image.Resampling.LANCZOS), target)
    return canvas


def catalogue():
    evidence = []
    for name in ('Kappa-launch.html', 'Kappa-original.jpg', 'launch.html', 'home.jpg'):
        path = ROOT / 'source-cache' / name
        receipt = pipeline.read_json_file(path.with_name(path.name + '.source.json'))
        evidence.append(dict(path=registry.relative_workspace_path(path), **receipt))
    return dict(schema_version='pm99-season-kit-catalogue-v1',
        season=dict(start_year=2021, end_year=2022, label='2021/22'),
        rows=[dict(carrier_id=207, club_name='Genoa', status='source-ready',
            render_contract=dict(kind='reviewed-original-fabric-planes-v1',
                image_sha256=evidence[1]['sha256'], original_size=[1500, 1113],
                crops=[list(c) for c in CROPS], shorts='FFFFFF',
                shorts_basis='White is one of the home-kit combinations explicitly described in the dated launch report; not a claim about every fixture.'),
            source=dict(provider='Kappa-BasicNet-original-2021-07-16-launch', reviewed=True,
                evidence=evidence, exact_artwork=False,
                review='Original photograph directly reviewed: red viewer-left/navy viewer-right torso, navy left/red right sleeves; original fine map fabric. Current orange native fallback is not this home design. Logos/collar/cuffs simplified at native resolution.',
                attribution='Kappa / BasicNet, original July 16 2021 launch photograph; Footy Headlines contemporary launch report for period identification and shorts alternatives.'))])


def prepare():
    output = ROOT / 'prepared-v1'
    if (output / 'delta').exists():
        raise ValueError('prepared evidence exists; inspect it rather than rerendering')
    doc = catalogue()
    verify_sources(doc)
    release = registry.load_preferred_release('2021-22')
    if release.release_id != 'sourced-arsenal-shirt-numbers-20261016-r112a':
        raise ValueError('Genoa preparation requires the verified Arsenal shirt parent')
    catalogue_path = ROOT / 'kit-catalogue.json'
    if catalogue_path.exists() and pipeline.read_json_file(catalogue_path) != doc:
        raise ValueError('retained Genoa source contract changed')
    if not catalogue_path.exists():
        pipeline.write_canonical_json(catalogue_path, doc)
    palette, _ = render._palette(release.game_path / 'DBDAT')
    artifacts = []
    with Image.open(ROOT / 'source-cache/Kappa-original.jpg') as original:
        canvas = fabric_canvas(original)
    for archive in render.ARCHIVES:
        record = render._record_index(release.game_path / 'DBDAT' / archive)[207]
        template = render._record_index(cascade.BASE / archive)[
            render.factory_tone_renderer.factory_template_carrier(archive, {'pattern': 'solid'})]
        payload = render._wikipedia_payload(record, {}, {'shorts1': 'FFFFFF'}, palette,
            template=template, canvas_override=canvas.copy())
        replay = render._wikipedia_payload(record, {}, {'shorts1': 'FFFFFF'}, palette,
            template=template, canvas_override=canvas.copy())
        if payload != replay:
            raise ValueError('source fabric/factory rendering is not deterministic')
        probe.checked_pixel_replacement(record, payload)
        path, digest = render._write_artifact(payload, output / 'renders')
        artifacts.append(dict(id=f"kit-render-2021-22-207-{archive.lower().replace('.pkf', '')}",
            kind='kit-render', sha256=digest, relative_path=str(path.relative_to(output / 'renders'))))
    canvas.save(output / 'reviewed-source-fabric-plane.png')
    digest = render.sha256_bytes(render.canonical_json_bytes(doc))
    retained(output / 'renders/kit-render-bindings-v1.json',
        dict(schema_version=render.SCHEMA, kit_catalogue_sha256=digest,
             clubs=[dict(carrier_id=207, artifacts=artifacts)]))
    retained(output / 'renders/kit-render-receipt-v1.json',
        dict(schema_version=render.RECEIPT_SCHEMA, kit_catalogue_sha256=digest,
             rows=[dict(carrier_id=207, artifacts=artifacts)],
             renderer=render.factory_tone_renderer.RENDERER_ID,
             source_fabric_implementation_sha256=registry.sha256_file(Path(__file__))))
    result = probe.prepare_batch('2021-22', catalogue_path, output / 'renders', output / 'delta')
    if result['clubs'] != 1 or result['skipped']:
        raise ValueError('Genoa source did not bind to exactly one current club')
    extend_complete_receipt(release, catalogue_path, output / 'delta/patch', output / 'delta')
    pipeline.write_canonical_json(output / 'render-replay-proof.json', dict(
        season='2021-22', release_id=release.release_id, all_three_sizes_reproduced=True,
        unselected_carriers_byte_identical=True, registered=False, runtime_verified=False,
        catalogue_sha256=registry.sha256_file(catalogue_path)))
    print(dict(**result, preferred_unchanged=True, native_candidate_only=True), flush=True)


if __name__ == '__main__':
    prepare()
