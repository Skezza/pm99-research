from scripts.capture_soccerbase_opening_managers_v1 import _manager_at


def test_selects_unique_manager_tenure_covering_fixture_date() -> None:
    payload = b'''<table><tr><td><a href="/managers/manager.sd?manager_id=1">Opening Manager</a></td><td>01 Jul, 2000</td><td>30 Sep, 2001</td></tr>
    <tr><td><a href="/managers/manager.sd?manager_id=2">Next Manager</a></td><td>01 Oct, 2001</td><td>Present</td></tr></table>'''
    assert _manager_at(payload, "2001-08-11") == "Opening Manager"
