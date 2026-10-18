"""Freeze independently reparsed country adjudications before native corrections.

Not game delivery or blanket source approval. A future native transaction must
also rederive each original typed annual plan and check the actual preimage.
"""
from scripts import season_period_country_resolution_v3 as resolver
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main():
    root = resolver.cgo.CATALOG.parent
    output = root / 'prepared-country-resolutions-v3.json'
    if output.exists():
        raise ValueError('completed original country resolution audit must not repeat')
    sha = resolver.fifa.registry.sha256_file(resolver.fifa.fifa.identity.old.FIFA)
    index = resolver.fifa.load(sha)
    rows = []
    for directory in ('original-country-default-delivery-20261017-v1', 'country-policy-v2-cohort-20261017'):
        for path in sorted((root.parent / directory).glob('*/country-plan.json')):
            plan = resolver.cgo.pipeline.read_json_file(path)
            for row in plan['updates']:
                try:
                    resolution = resolver.resolve(row, plan['season'], index=index, file_sha=sha)
                    result = dict(status='resolved-game-country-source-choice', resolution=resolution)
                except ValueError as exc:
                    result = dict(status='held-not-approved', reason=str(exc))
                rows.append(dict(season=plan['season'], carrier_id=row['carrier_id'],
                    source_person=row['source_person'], proposed_annual_country=row['nationality'],
                    source_plan=resolver.passport.binding(path), **result))
    held = [r for r in rows if r['status'].startswith('held')]
    changes = [r for r in rows if r.get('resolution', {}).get('nationality', r['proposed_annual_country']) != r['proposed_annual_country']]
    retained(output, dict(rows=rows, prepared_rows=len(rows), held=len(held),
        proposed_source_countries_corrected=len(changes), native_writes=0, preferred_writes=0,
        original_typed_source_rederivation_still_required_before_native_delivery=True,
        current_country_flags_not_used=True,
        implementation_bindings=[resolver.passport.binding(p) for p in (
            resolver.fifa.registry.ROOT / 'scripts/season_period_country_resolution_v3.py',
            resolver.fifa.registry.ROOT / 'scripts/season_original_passport_alias_v1.py',
            resolver.fifa.registry.ROOT / 'scripts/season_cgo_disambiguation_v2.py')]))
    print(dict(prepared_rows=len(rows), held=len(held), proposed_countries_corrected=len(changes),
        native_writes=0), flush=True)


if __name__ == '__main__':
    main()
