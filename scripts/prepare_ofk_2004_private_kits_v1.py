"""Render the reviewed 2004 OFK photograph through the factory kit renderer.

Private three-size pixel-only patch. The source photograph is retained for
inspection, not copied into a distributed game; logos/sponsors are simplified.
"""
from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_kit_render_bindings_v1 as render
from scripts import cascade_compact_kit_v6 as cascade
from scripts.prepare_paired_club_assets_v1 import pixel_payload
from scripts.season_art_transaction_v1 import atomic_bytes
from app.bitmap_pixel_rows import bitmap_pixel_ranges


def catalogue():
    name = 'ofk-2004-intertoto-official-retrospective'
    page_raw, page_binding = source.original(name)
    photograph = source.AUDIT / 'ofk-2004-kit-originals' / (name + '-1.jpg')
    photo_receipt = pipeline.read_json_file(photograph.with_name(photograph.name + '.source.json'))
    if registry.sha256_file(photograph) != photo_receipt['sha256']:
        raise ValueError('reviewed original photograph changed')
    if photo_receipt['url'] != 'https://ofkbeograd.com/wp-content/uploads/2024/07/1A_0038.jpg':
        raise ValueError('photograph does not identify the reviewed original')
    from bs4 import BeautifulSoup
    page = BeautifulSoup(page_raw, 'html.parser')
    if (page.select_one('meta[property="og:image"]').get('content') != photo_receipt['url']
            or '2004. GODINE' not in page.title.get_text()):
        raise ValueError('reviewed photograph is not linked by the dated official retrospective')
    # This is a root visual review of the exact original, not sampled colours
    # from a present-day club crest or an uninspected generated kit.
    evidence = [dict(path=registry.relative_workspace_path(photograph), **photo_receipt),
        dict(path=page_binding['path'], url=page_binding['url'], sha256=page_binding['sha256'])]
    return dict(schema_version='pm99-season-kit-catalogue-v1',
        season=dict(start_year=2004, end_year=2005, label='2004/05'),
        rows=[dict(carrier_id=706, club_name='OFK Beograd', status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style', style=dict(pattern='vertical_stripes',
                colors=['white', [35, 66, 173]], shorts=[35, 66, 173],
                sleeves=[35, 66, 173], trim='white', stripe_count=5)),
            source=dict(provider='official-club-original-period-match-photograph', reviewed=True,
                evidence=evidence, exact_artwork=False,
                review='ROOT inspected original2004 OFK/Atletico handshake photograph: white/royal-blue vertical stripes, blue sleeves, blue shorts with white side trim. Stripes/colours and shorts are period evidence; precise stripe panels, piping, badges, sponsors and numerals are simplified. Not a claim about every subsequent match kit.',
                attribution='OFK Beograd official 2004 Intertoto retrospective (published2024). Photograph retained only as research/design evidence.'))])


def prepare(output, *, source_catalogue=None, season='2004-05', baseline_release_id=None,
            carrier=706, club_name='OFK Beograd'):
    if output.exists(): raise ValueError('private kit candidate is immutable')
    doc = catalogue() if source_catalogue is None else source_catalogue
    if (doc['season']['start_year'] != int(season[:4]) or len(doc['rows']) != 1
            or doc['rows'][0]['carrier_id'] != carrier or doc['rows'][0]['club_name'] != club_name):
        raise ValueError('private OFK kit catalogue has another season/carrier/club')
    for binding in doc['rows'][0]['source']['evidence']:
        if registry.sha256_file(registry.ROOT / binding['path']) != binding['sha256']:
            raise ValueError('private period kit original evidence changed')
    # General kit verifier expects its own compact URL/hash receipts. The
    # acquisition page has a richer audit receipt, so replay originals above
    # and verify the photograph's compact receipt directly; do not replace it.
    release = (registry.load_registered_release(season,baseline_release_id) if baseline_release_id
        else registry.load_preferred_release(season))
    output.mkdir(parents=True)
    pipeline.write_canonical_json(output / 'kit-catalogue.json', doc)
    binding, receipt = render.render_catalogue(doc, dbdat=cascade.BASE,
        output_dir=output / 'renders', pattern_cache_dir=cascade.CACHE, allow_network=False)
    again, repeated = render.render_catalogue(doc, dbdat=cascade.BASE,
        output_dir=output / 'replay-renders', pattern_cache_dir=cascade.CACHE, allow_network=False)
    if binding != again or receipt != repeated or receipt['coverage']['bound_club_count'] != 1:
        raise ValueError('private three-size kit did not reproduce exactly')
    changes = []
    for archive in render.ARCHIVES:
        before = (release.game_path / 'DBDAT' / archive).read_bytes()
        records = render._record_index(release.game_path / 'DBDAT' / archive)
        record = records[carrier]
        artifact = next(a for a in binding['clubs'][0]['artifacts'] if a['id'].endswith('-' + archive[:-4].lower()))
        path = output / 'renders' / artifact['relative_path']
        if registry.sha256_file(path) != artifact['sha256']: raise ValueError('rendered kit bytes changed')
        payload = pixel_payload(record, path.read_bytes())
        after = bytearray(before)
        after[record.bitmap_offset:record.bitmap_offset + record.bitmap_length] = payload
        intervals = [(record.bitmap_offset + lo, record.bitmap_offset + hi) for lo, hi in bitmap_pixel_ranges(record)]
        if len(before) != len(after) or any(not any(lo <= i < hi for lo, hi in intervals)
                for i, (a, b) in enumerate(zip(before, after)) if a != b):
            raise ValueError('private kit changed a wrapper/palette/other club')
        atomic_bytes(output / 'DBDAT' / archive, bytes(after))
        changes.append(dict(archive=archive, carrier_id=carrier,
            before_sha256=render.sha256_bytes(before), after_sha256=render.sha256_bytes(bytes(after)),
            bitmap_before_sha256=render.sha256_bytes(record.raw_bitmap), bitmap_after_sha256=render.sha256_bytes(payload),
            only_target_pixel_lane_changed=True))
    pipeline.write_canonical_json(output / 'render-bindings.json', binding)
    pipeline.write_canonical_json(output / 'render-receipt.json', receipt)
    proof = dict(season=season, club=club_name, source_baseline_release_id=release.release_id,
        three_sizes_replayed_exactly=True, changes=changes, registered=False, runtime_verified=False,
        historical_artwork_exact=False, source_photo_sha256=doc['rows'][0]['source']['evidence'][0]['sha256'])
    pipeline.write_canonical_json(output / 'private-kit-proof.json', proof)
    return proof


if __name__ == '__main__': prepare(source.AUDIT / 'ofk-2004-private-kits-v1')
