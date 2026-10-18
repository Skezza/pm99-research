"""Extend a registered kit chain with a bounded source-reviewed design change.

Only declared carrier pixel lanes change. Existing all-record approval bindings
are checked and preserved; historical review is narrow, never global approval.
"""
import copy
import os
from pathlib import Path

from scripts import build_registered_quality_release_v1 as build
from scripts import cascade_compact_kit_v6 as cascade
from scripts import season_kit_render_bindings_v1 as render
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import probe_sourced_factory_kit_v1 as probe


def extend_complete_receipt(release, catalogue_path, patch_root, output):
    catalogue = pipeline.read_json_file(catalogue_path)
    rows = {int(row['carrier_id']): row for row in catalogue['rows']}
    if len(rows) != len(catalogue['rows']) or not rows:
        raise ValueError('empty or duplicate reviewed kit scope')
    previous = build._kit_receipt(release.season, source_release=release)
    complete = pipeline.read_json_file(previous)
    audit_path = Path(complete['audit_path'])
    if registry.sha256_file(audit_path) != complete['audit_sha256']:
        raise ValueError('previous all-record kit audit changed')
    audit = copy.deepcopy(pipeline.read_json_file(audit_path))
    if (audit['blockers'] or audit['all_records'] != 544 or len(audit['records']) != 544
            or len({row['carrier_id'] for row in audit['records']}) != 544):
        raise ValueError('previous all-record kit audit is incomplete')
    # Protect all three sizes, not just TEAM RATING's NANOESC record.
    for archive in render.ARCHIVES:
        before = render._record_index(release.game_path / 'DBDAT' / archive)
        after = render._record_index(patch_root / 'DBDAT' / archive)
        if set(before) != set(after) or not set(rows) <= set(before):
            raise ValueError('kit archive carrier set changed')
        if any(before[c].raw_bitmap != after[c].raw_bitmap for c in before if c not in rows):
            raise ValueError('kit changed an unselected club')
    before = render._record_index(release.game_path / 'DBDAT/NANOESC.PKF')
    after = render._record_index(patch_root / 'DBDAT/NANOESC.PKF')
    for row in audit['records']:
        carrier = row['carrier_id']
        if row['after_sha256'] != render.sha256_bytes(before[carrier].raw_bitmap):
            raise ValueError('previous kit bitmap audit is stale')
        if carrier not in rows:
            continue
        source = rows[carrier]
        if row['club'] != source['club_name']:
            raise ValueError('reviewed source describes another club')
        row.update(before_sha256=render.sha256_bytes(before[carrier].raw_bitmap),
            after_sha256=render.sha256_bytes(after[carrier].raw_bitmap),
            status='source-bound-rerendered', renderer=cascade.factory.RENDERER_ID,
            source=dict(club=source['club_name'], contract=source['render_contract'],
                receipt=str(catalogue_path.resolve()), receipt_sha256=registry.sha256_file(catalogue_path)))
    audit.update(release_id=release.release_id, renderer=cascade.factory.RENDERER_ID,
        historical_accuracy_certified=False, runtime_verified=False,
        reviewed_design_carriers=sorted(rows),
        prior_audit=dict(path=str(audit_path), sha256=registry.sha256_file(audit_path)))
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'complete-kit-audit.json'
    pipeline.write_canonical_json(target, audit)
    complete.update(audit_path=str(target.resolve()), audit_sha256=registry.sha256_file(target),
        renderer=cascade.factory.RENDERER_ID,
        archives={name: dict(sha256_after=registry.sha256_file(patch_root / 'DBDAT' / name))
                  for name in render.ARCHIVES},
        prior_receipt=dict(path=str(previous), sha256=registry.sha256_file(previous)),
        scope='reviewed declared carriers only; every other installed bitmap preserved')
    target = output / 'complete-kit-receipt.json'
    pipeline.write_canonical_json(target, complete)
    receipt = pipeline.read_json_file(patch_root / 'receipt.json')
    receipt.update(complete_kit_receipt_path=str(target.resolve()),
        complete_kit_receipt_sha256=registry.sha256_file(target))
    # prepare_batch's original evidence is immutable. Extend into a new
    # materialisation rather than overwriting its original receipt.
    completed = output / 'complete-patch'
    for archive in render.ARCHIVES:
        target = completed / 'DBDAT' / archive
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(patch_root / 'DBDAT' / archive, target)
    pipeline.write_canonical_json(completed / 'receipt.json', receipt)
    return completed


def verify_sources(catalogue):
    for row in catalogue['rows']:
        if row['status'] != 'source-ready' or row['source'].get('reviewed') is not True:
            raise ValueError('period design is not explicitly reviewed')
        evidence = row['source'].get('evidence', [])
        if not evidence:
            raise ValueError('review has no original evidence')
        for source in evidence:
            path = registry.ROOT / source['path']
            path.resolve().relative_to(registry.ROOT.resolve())
            receipt = pipeline.read_json_file(path.with_name(path.name + '.source.json'))
            if {k: receipt.get(k) for k in ('url', 'sha256')} != dict(url=source['url'], sha256=source['sha256']):
                raise ValueError('period source receipt differs')
            if registry.sha256_file(path) != source['sha256']:
                raise ValueError('period source bytes changed')


def prepare(season, catalogue_path, output, *, source_release=None):
    if output.exists():
        raise ValueError('reviewed kit delta is immutable')
    catalogue = pipeline.read_json_file(catalogue_path)
    verify_sources(catalogue)
    release = source_release if source_release is not None else registry.load_preferred_release(season)
    if release.season != season:
        raise ValueError('kit source release belongs to another season')
    clubs = {int(c['carrier_id']): c['name'] for c in pipeline.read_json_file(release.package_path)['clubs']}
    if catalogue['season']['label'].replace('/', '-') != season:
        raise ValueError('kit source season differs')
    for row in catalogue['rows']:
        if clubs.get(int(row['carrier_id'])) != row['club_name']:
            raise ValueError('reviewed kit does not match current recipe carrier')
    output.mkdir(parents=True)
    binding, receipt = render.render_catalogue(catalogue, dbdat=cascade.BASE,
        output_dir=output / 'renders', pattern_cache_dir=cascade.CACHE, allow_network=False)
    if receipt['coverage']['bound_club_count'] != len(catalogue['rows']):
        raise ValueError('reviewed kit has unrendered gaps')
    pipeline.write_canonical_json(output / 'renders/kit-render-bindings-v1.json', binding)
    pipeline.write_canonical_json(output / 'renders/kit-render-receipt-v1.json', receipt)
    # Independently rerender from original source contracts and factory inputs.
    again, repeated = render.render_catalogue(catalogue, dbdat=cascade.BASE,
        output_dir=output / 'replay-renders', pattern_cache_dir=cascade.CACHE, allow_network=False)
    if binding != again or receipt != repeated:
        raise ValueError('reviewed kit rendering is not deterministic')
    result = probe.prepare_batch(season, catalogue_path, output / 'renders', output / 'delta',
                                 source_release=release)
    if result['clubs'] != len(catalogue['rows']) or result['skipped']:
        raise ValueError('reviewed source did not apply to its exact carrier')
    extend_complete_receipt(release, catalogue_path, output / 'delta/patch', output / 'delta')
    pipeline.write_canonical_json(output / 'render-replay-proof.json', dict(
        season=season, source_release_id=release.release_id,
        catalogue_sha256=registry.sha256_file(catalogue_path),
        render_binding_sha256=registry.sha256_file(output / 'renders/kit-render-bindings-v1.json'),
        all_three_sizes_reproduced=True, unselected_carriers_byte_identical=True,
        registered=False, runtime_verified=False))
    return result
