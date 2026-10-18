"""Trace recorded exact-club source corrections into the actual current XIs.

Discovery only: does not certify whole rosters or mutate any season. Reuses
original reports and independently reparses every recorded source-side repair.
"""
from datetime import UTC, datetime
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_published_person_identity_v1 as people_source
from scripts import season_historical_transfer_review_v1 as identities
from scripts import repair_prefix_selected_opening_sources_v1 as side_source
from scripts import season_contextual_tactics_v1 as native
from scripts import season_duplicate_ownership_plan_v1 as layers
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/duplicate-ownership-v3/exact-side-opening-source-repairs-r4'
OUTPUT=registry.ROOT/'.local/consolidated-audit-20261009/unapplied-wrong-side-repairs-20261016-v2.json'


def native_name_matches(name, canonical):
    # Existing variable-name repairs intentionally retain trailing SPACE padding
    # to preserve the suffix cursor. Never strip digits, initials or surnames.
    return name.rstrip(' ').casefold()==canonical.casefold()


def classify(actual, corrected, rejected):
    if len(actual)!=11 or len(set(actual))!=11 or None in actual:
        return 'unresolved-exact-person-identity'
    if set(actual)==set(corrected):return 'corrected-source-XI-present-in-current-game'
    if set(actual)==set(rejected):return 'confirmed-opponent-XI-still-in-current-game'
    return 'mixed-current-XI-needs-individual-source-review'


def main():
    public_path=registry.ROOT/'.local/duplicate-ownership-v3/published-person-identities-r2.json'
    people,_=people_source.merge({},pipeline.read_json_file(public_path))
    rows=[];scanned=[]
    for season in registry.supported_seasons():
        review_path=ROOT/'opening'/season/'opening-review.json'
        review=pipeline.read_json_file(review_path);scanned.append(dict(season=season,
            source_review_sha256=registry.sha256_file(review_path)))
        repairs=review.get('wrong_side_source_replay',{}).get('corrected',[])
        if not repairs:continue
        release=registry.load_preferred_release(season)
        players={p['carrier_id']:p for _,package,_ in layers.package_layers(release) for p in package['players']}
        jug=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        eq=native.payloads((release.game_path/'DBDAT/EQ98030.FDI').read_bytes())
        for row in repairs:
            path=registry.ROOT/row['repair_path'];repair=pipeline.read_json_file(path)
            original=registry.ROOT/repair['original_capture_path']
            if registry.sha256_file(original)!=repair['original_capture_sha256']:
                raise ValueError('original wrong-side capture changed')
            capture=pipeline.read_json_file(original)
            corrected,evidence,events=side_source.replay(repair['before'],capture,original.parent/'cache')
            if corrected!=repair['after']:raise ValueError('recorded correction does not reparse from original reports')
            actual=[];gap=None
            try:
                xi=native.native_xi(eq[row['carrier_id']],jug)
                for carrier,name in xi:
                    player=players[carrier];record=facts.native_facts(jug,carrier)
                    if not native_name_matches(record['name'],player['name']):
                        raise ValueError('current native name differs from recipe')
                    if record['birth_date']!=player['facts'].get('birth_date'):
                        raise ValueError('current native birthday differs from recipe')
                    person=identities.unique_person(player,people)
                    actual.append(dict(carrier_id=carrier,native_name=name,
                        source_player_id=person['source_player_id'] if person else None))
            except ValueError as exc:
                gap=str(exc)
            wanted=[int(p['source_player_id']) for p in corrected['starting_xi']]
            rejected=[int(p['source_player_id']) for p in repair['before']['starting_xi']]
            actual_ids=[p['source_player_id'] for p in actual]
            rows.append(dict(season=season,club=row['club'],carrier_id=row['carrier_id'],
                release_id=release.release_id,manifest_sha256=release.manifest_sha256,
                package_sha256=registry.sha256_file(release.package_path),
                native_JUG_sha256=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
                source_repair=dict(path=row['repair_path'],sha256=registry.sha256_file(path)),
                corrected_source_XI=wanted,rejected_opponent_XI=rejected,current_native_XI=actual,
                classification='unresolved-native-XI-readback' if gap else classify(actual_ids,wanted,rejected),
                readback_gap=gap,independent_original_source_replay=True))
    result=dict(utc=datetime.now(UTC).isoformat(),machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',
        schema='pm99-recorded-wrong-side-source-to-current-native-XI-audit-v1',
        source_reviews_scanned=scanned,recorded_repairs=len(rows),rows=rows,
        native_writes=0,recipes_modified=0,
        scope='All recorded wrong-side source repairs across26 reviews; NOT all game fixtures or global first-XI certification.')
    retained(OUTPUT,result)
    print(dict(path=registry.relative_workspace_path(OUTPUT),rows=[(r['season'],r['club'],r['classification']) for r in rows]),flush=True)


if __name__=='__main__':main()
