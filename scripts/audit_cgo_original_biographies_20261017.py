"""Reparse independent Congo biographies against every retained country plan."""
from scripts import season_cgo_disambiguation_v2 as country
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main():
    root = country.CATALOG.parent
    output = root / 'independent-prior-country-association-v2.json'
    if output.exists():
        raise ValueError('retained independent biography audit must not repeat')
    rows = []
    for path in sorted((root.parent / 'country-policy-v2-cohort-20261017').glob('*/country-plan.json')):
        plan = country.pipeline.read_json_file(path)
        for row in plan['updates']:
            if row['nationality'] != 'CGO':
                continue
            try:
                result = dict(status='independently-disambiguated-for-target-year',
                    proof=country.verify(row, plan['season']))
            except ValueError as exc:
                result = dict(status='held-not-approved', reason=str(exc))
            rows.append(dict(season=plan['season'], carrier_id=row['carrier_id'],
                name=row['source_person']['name'], source_plan=dict(
                    path=country.registry.relative_workspace_path(path),
                    sha256=country.registry.sha256_file(path)), **result))
    retained(output, dict(rows=rows, native_writes=0, preferred_writes=0,
        future_debuts_not_extrapolated_backwards=True, undated_flags_not_used=True,
        source_catalog_sha256=country.registry.sha256_file(country.CATALOG),
        independently_admitted=sum(r['status'].startswith('independently') for r in rows),
        held=sum(r['status'].startswith('held') for r in rows),
        no_historical_caps_or_exclusive_citizenship_claim=True))
    print(dict(rows=len(rows), admitted=sum(r['status'].startswith('independently') for r in rows),
        held=sum(r['status'].startswith('held') for r in rows)), flush=True)


if __name__ == '__main__':
    main()
