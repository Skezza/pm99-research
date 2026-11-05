"""Actual-parent mechanics: source packet here is not historical approval."""
import copy
import json
from pathlib import Path
import sys
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'upstream/pm99-skezmod-db-editor')]
from scripts import season_roster_membership_payload_core_v1 as subject
from scripts import season_release_registry_v1 as registry


def inputs():
    packet = ROOT/'.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/source701-mode0-roster-order-packet-v1.json'
    if not packet.is_file():
        pytest.skip('retained actual-parent corpus unavailable')
    parent = registry.load_registered_release('2022-23', 'sourced-casemiro-tuanzebe-sparrow-opening-2022-23-20261105-r705a')
    raw = (parent.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    doc = json.loads(packet.read_bytes())
    claims = doc['approved_membership_changes']
    moves = [dict(player_record_id=x['carrier_id'], from_club_carrier_id=x['from_club'], to_club_carrier_id=x['to_club']) for x in claims['moves']]
    removals = [dict(player_record_id=x['carrier_id'], from_club_carrier_id=x['from_club']) for x in claims['remove_false_or_unowned_links']]
    desired = {cid: [(x['flag'], x['carrier_id']) for x in doc['clubs'][str(cid)]['after_rows']] for cid in [344,333,346,345,324]}
    return raw, moves, removals, desired


def test_capacity_neutral_transaction_preserves_every_other_owner_and_payload():
    raw, moves, removals, desired = inputs()
    before_hash = subject.hashlib.sha256(raw).hexdigest()
    result, proof = subject.rewrite_membership_transaction(raw, moves=moves, removals=removals, desired_rosters=desired)
    _, _, rosters, owners = subject._read_rosters(result)
    assert {cid: len(rosters[cid].rows) for cid in desired} == {344:22,333:25,346:25,345:24,324:23}
    for pid, club in [(10343,333),(10455,344),(10414,346),(9593,345)]:
        assert owners[pid] == {club}
    for pid in [10357,10369,10373,9928]:
        assert pid not in owners
    assert owners[8378] == {803} and owners[1852] == {301} and owners[10538] == {348}
    assert proof['full_native_owner_graph_verified'] and proof['unselected_eq_payloads_byte_identical']
    assert subject.hashlib.sha256(raw).hexdigest() == before_hash


@pytest.mark.parametrize('mutation', ['wrong_owner','duplicate_claim','missing_postimage','extra_postimage','extra_player','dropped_player','nonzero_flag','duplicate_row','empty','foreign_club'])
def test_reject_stale_ambiguous_or_unapproved_transaction(mutation):
    raw, moves, removals, desired = inputs()
    moves, removals, desired = copy.deepcopy((moves, removals, desired))
    if mutation == 'empty': moves, removals, desired = [], [], {}
    elif mutation == 'foreign_club': moves[0]['to_club_carrier_id'] = 4
    elif mutation == 'wrong_owner': moves[0]['from_club_carrier_id'] = 301
    elif mutation == 'duplicate_claim': removals.append(dict(moves[0]))
    elif mutation == 'missing_postimage': desired.pop(324)
    elif mutation == 'extra_postimage': desired[301] = []
    elif mutation == 'extra_player': desired[344].append((0, 1852))
    elif mutation == 'dropped_player': desired[344].pop()
    elif mutation == 'nonzero_flag': desired[344][0] = (1, desired[344][0][1])
    elif mutation == 'duplicate_row': desired[344][-1] = desired[344][0]
    with pytest.raises(subject.MembershipPayloadError):
        subject.rewrite_membership_transaction(raw, moves=moves, removals=removals, desired_rosters=desired)
