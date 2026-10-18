"""Declared adjoining-season colour reference, not exact2002 artwork."""
from scripts import prepare_monagas_2003_period_kits_v1 as reference


def catalogue():
    result = reference.catalogue()
    result['season'] = dict(start_year=2002, end_year=2003, label='2002/03')
    source = result['rows'][0]['source']
    source['reference_publication_year'] = 2003
    source['target_season_artwork_verified'] = False
    source['provider'] = 'adjoining-season-original-colour-reference-explicit-editorial-fallback'
    source['limitation'] = ('Target2002 artwork NOT independently verified. Original July2003 '
        'blue/maroon reference is an explicitly declared adjoining-season colour fallback, '
        'not a target-season photo or certified stripe/sponsor/shorts design. ' + source['limitation'])
    return result
