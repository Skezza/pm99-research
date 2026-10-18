from datetime import date

from scripts import capture_2015_residual_manager_history_v1 as capture


def test_residual_targets_are_unique_and_keep_the_real_joint_manager() -> None:
    carriers = [int(row["carrier_id"]) for row in capture.TARGETS]
    assert len(carriers) == 26
    assert len(set(carriers)) == 26
    gif = next(row for row in capture.TARGETS if row["carrier_id"] == 961)
    assert gif["manager"] == "Joel Cedergren / Roger Franzén"


def test_residual_targets_are_pinned_to_the_one_snapshot_date() -> None:
    assert capture.AS_OF == date(2015, 9, 1)
