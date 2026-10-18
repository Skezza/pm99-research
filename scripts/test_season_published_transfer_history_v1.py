import copy
import pytest
from scripts import season_published_transfer_history_v1 as history


def fixture():
    return {'success': True, 'data': {'playerId': '10', 'history': {'terminated': [
        {'id': '20', 'transferSource': {'clubId': '1'}, 'transferDestination': {'clubId': '2'},
         'details': {'playerId': '10', 'date': '2005-07-01T00:00:00+02:00', 'isPending': False},
         'relativeUrl': '/player/transfers/spieler/10/transfer_id/20'}], 'pending': []}}}


def test_original_local_transfer_date_is_not_shifted_to_previous_utc_day():
    assert history.parse(fixture(), 10)[0]['date'] == '2005-07-01'


@pytest.mark.parametrize('problem', ['root-person', 'row-person', 'pending', 'timezone', 'url', 'club'])
def test_invalid_original_records_cannot_supply_ownership(problem):
    d = fixture(); row = d['data']['history']['terminated'][0]
    if problem == 'root-person': d['data']['playerId'] = '99'
    if problem == 'row-person': row['details']['playerId'] = '99'
    if problem == 'pending': row['details']['isPending'] = True
    if problem == 'timezone': row['details']['date'] = '2005-07-01T00:00:00'
    if problem == 'url': row['relativeUrl'] = '/other/transfers/spieler/99/transfer_id/20'
    if problem == 'club': row['transferDestination']['clubId'] = None
    with pytest.raises(ValueError): history.parse(d, 10)


def test_same_day_different_transfer_rows_are_not_ordered_or_collapsed():
    d = fixture(); second = copy.deepcopy(d['data']['history']['terminated'][0])
    second.update(id='21', relativeUrl='/player/transfers/spieler/10/transfer_id/21')
    second['transferSource']['clubId'] = '2'; second['transferDestination']['clubId'] = '3'
    d['data']['history']['terminated'].append(second)
    assert len(history.parse(d, 10)) == 2


def test_backdated_pending_transfer_cannot_be_ignored():
    d = fixture(); d['data']['history']['pending'] = [d['data']['history']['terminated'][0]]
    with pytest.raises(ValueError, match='unconfirmed historical'):
        history.parse(d, 10)
