"""Count remaining recipe name prefixes against explicit release snapshots.

Discovery only, not native approval or a second counting of the546 delivered
name repairs. Existing source-bound name policy can prepare the actual fixes.
"""
from scripts import season_number_label_names_v2 as names
from scripts import season_duplicate_ownership_plan_v1 as layers
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=names.registry.ROOT/'.local/consolidated-audit-20261009/remaining-numeric-names-20261017'


def main():
    output=ROOT/'explicit-release-recipe-census.json'
    if output.exists():raise ValueError('existing numeric-name census must not repeat')
    ROOT.mkdir(parents=True,exist_ok=True)
    releases=[names.registry.load_preferred_release(season) for season in names.registry.supported_seasons()]
    rows=[]
    for release in releases:
        found=[]
        for label,package,path in layers.package_layers(release):
            clubs={c['id']:c for c in package['clubs']}
            for player in package['players']:
                if not names.NUMBER.match(player['name']):continue
                found.append(dict(layer=label,carrier_id=player['carrier_id'],name=player['name'],
                    source_name=player.get('source_name'),birth_date=player['facts'].get('birth_date'),
                    club=clubs[player['club_id']]['name'],policy=player.get('policy'),
                    recipe_path=names.registry.relative_workspace_path(path)))
        rows.append(dict(season=release.season,release_id=release.release_id,
            manifest_sha256=release.manifest_sha256,candidates=found,count=len(found)))
    advanced=[r.season for r in releases
        if names.registry.load_preferred_release(r.season).manifest_sha256!=r.manifest_sha256]
    retained(output,dict(seasons=rows,total=sum(r['count'] for r in rows),
        scope='Literal leading numeric labels in explicit registered recipe snapshots; not a native/source truth verdict.',
        default_advances_during_read=advanced,native_writes=0,preferred_writes=0,
        prior_546_source_backed_repairs_not_recounted=True))
    print(dict(recipe_prefix_candidates=sum(r['count'] for r in rows),
        by_season={r['season']:r['count'] for r in rows if r['count']},
        default_advances_during_read=advanced),flush=True)


if __name__=='__main__':main()
