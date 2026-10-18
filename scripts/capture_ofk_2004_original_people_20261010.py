"""Acquire only OFK original XI plus positively dated reserve biographies."""
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import capture_source_bound_people_v1 as people
from scripts import capture_transfermarkt_opening_lineups_v1 as openings
from scripts.capture_stock_replacement_sources_20261010 import ROOT
from scripts.capture_ofk_2004_reserve_brackets_20261010 import original_ids


def original(key):
    path = ROOT / (key + '.html')
    receipt = pipeline.read_json_file(ROOT / (key + '.source.json'))
    if receipt['status'] != 'original-captured' or registry.sha256_file(path) != receipt['sha256']:
        raise ValueError('original OFK opening source changed')
    return path.read_bytes(), dict(path=registry.relative_workspace_path(path), sha256=receipt['sha256'], url=receipt['url'])


def main():
    annual, annual_binding = original_ids(2004)
    schedule, schedule_binding = original('ofk-beograd-2004-schedule')
    report, report_binding = original('ofk-first-fixture-2004-3142214')
    class Offline:
        def get(self, url, key):
            if url == schedule_binding['url']:
                return schedule
            if url == report_binding['url']:
                return report
            raise ValueError('opening replay requested an unbound source URL')
    ref = openings.TeamRef('OFK Beograd', 'OFK Beograd', 53,
        '/ofk-belgrad/startseite/verein/53', 'exact-original-club-id')
    fixture = openings._first_fixture(ref, season_start_year=2004, competition_code='SER1', cache=Offline())
    if (fixture['match_id'], fixture['date']) != ('3142214', '2004-08-20'):
        raise ValueError('earliest original domestic fixture differs')
    opening = openings._lineup_from_report(ref, fixture, Offline())
    xi = {int(row['source_player_id']) for row in opening['starting_xi']}
    path = ROOT.parent / 'ofk-2004-intersection-history-v1.json'
    history = pipeline.read_json_file(path)
    events, _ = __import__('scripts.season_published_transfer_history_v1', fromlist=['merge']).merge({}, history)
    reserves = []
    for id in sorted(events):
        bracket = transfer.transfer_interval(events[id], fixture['date'])
        if (id not in xi and id in annual and bracket.get('status') == 'recorded-entry-and-exit-bracket-fixture'
                and bracket['source_owner_club_id'] == 53):
            reserves.append(dict(source_player_id=id, annual_name=annual[id], bracket=bracket))
    if len(xi) != 11 or len(reserves) != 7:
        raise ValueError('positive original XI plus strict dated reserves do not fill the fixed18 slots')
    ids = xi | {row['source_player_id'] for row in reserves}
    inputs = [annual_binding, schedule_binding, report_binding,
        dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))]
    claims_path = ROOT.parent / 'ofk-2004-positive-fixed18-source-claims-v1.json'
    pipeline.write_canonical_json(claims_path, dict(season='2004-05', first_fixture=fixture,
        original_opening=opening, opening_xi_ids=sorted(xi), dated_reserves=reserves,
        original_bindings=inputs, native_writes=0, approved_for_native_publication=False,
        scope='Positive18 dated people only. Original unused match bench absent; manager name published in actual fixture. Native identity/assets/replay/runtime proof still required.'))
    people.capture_ids(ids, ROOT.parent / 'ofk-2004-history-originals',
        ROOT.parent / 'ofk-2004-original-person-identities-v1.json',
        inputs + [dict(path=registry.relative_workspace_path(claims_path), sha256=registry.sha256_file(claims_path))])


if __name__ == '__main__':
    main()
