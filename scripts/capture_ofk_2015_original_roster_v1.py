"""Re-use retained2015 originals; acquire dated histories, not annual ownership."""
from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import capture_transfermarkt_opening_lineups_v1 as openings
from scripts.capture_ofk_2004_reserve_brackets_20261010 import original_ids
from scripts import season_published_transfer_history_v1 as histories
from scripts import season_pipeline_v2 as pipeline


def capture():
    output = source.AUDIT / 'ofk-2015-original-opening-and-history-v1.json'
    if output.exists(): raise ValueError('completed original review must not be repeated')
    annual, annual_binding = original_ids(2015)
    annual_raw, _ = source.original('ofk-beograd-2015')
    roles = source.annual_roles(annual_raw, expected_year=2015)
    schedule, schedule_binding = source.original('ofk-beograd-2015-schedule')
    report, report_binding = source.original('ofk-first-fixture-2015-2598829')
    class Offline:
        def get(self, url, key):
            if url == schedule_binding['url']: return schedule
            if url == report_binding['url']: return report
            raise ValueError('2015 original source is not bound')
    ref = openings.TeamRef('OFK Beograd', 'OFK Beograd',53,
        '/ofk-belgrad/startseite/verein/53', 'exact-original-club-id')
    fixture = openings._first_fixture(ref, season_start_year=2015, competition_code='SER1', cache=Offline())
    if fixture['match_id'] != '2598829' or fixture['date'] != '2015-07-19':
        raise ValueError('2015 original earliest league fixture changed')
    opening = openings._lineup_from_report(ref, fixture, Offline())
    match_ids = [int(p['source_player_id']) for p in opening['starting_xi'] + opening['substitutes']]
    if len(match_ids) != 14 or len(set(match_ids)) != 14 or not set(match_ids) <= annual.keys():
        raise ValueError('2015 original XI and three published bench people changed')
    inputs = [annual_binding, schedule_binding, report_binding]
    history_path = source.AUDIT / 'ofk-2015-target-annual-history-v1.json'
    if not history_path.exists():
        histories.capture_ids(set(annual), source.AUDIT / 'ofk-2015-history-originals',
            history_path, inputs, 'Original2015/16 annual stable IDs only. Annual appearance NOT approval of opening membership.')
    document = pipeline.read_json_file(history_path)
    if document['input_plans'] != inputs: raise ValueError('2015 history input binding changed')
    events, review = histories.merge({}, document)
    reserves = source.select_reserves(events, annual, fixture['date'], set(match_ids))
    result = dict(season='2015-16', first_fixture=fixture, original_opening=opening,
        original_bindings=inputs, matchday_person_ids=match_ids, annual_broad_roles=roles,
        positive_dated_extra_reserves=reserves, original_history_review=review,
        required_extra_reserves=4, native_writes=0, publication_authorised=False,
        scope='Original XI11 plus published substitutes3. Additional annual people require a strict completed transfer bracket at the original first fixture. No native/player/manager/kit/tactics approval.')
    pipeline.write_canonical_json(output, result)
    return result


if __name__ == '__main__':
    result = capture()
    print({'matchday':len(result['matchday_person_ids']),
        'strict_extra_reserves':len(result['positive_dated_extra_reserves']), 'native_writes':0}, flush=True)
