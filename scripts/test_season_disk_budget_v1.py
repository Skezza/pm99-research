from types import SimpleNamespace

import pytest

from scripts import season_disk_budget_v1 as budget


@pytest.mark.parametrize("reserve", [budget.DEFAULT_RESERVE, budget.MINIMUM_RESERVE])
def test_budget_includes_output_and_accepts_exact_boundary(monkeypatch, reserve):
    output = 256 * 1024**2
    monkeypatch.setattr(budget.shutil, "disk_usage",
                        lambda _: SimpleNamespace(free=reserve + output))
    result = budget.require_space("unused", output, minimum_free_bytes=reserve)
    assert result["minimum_free_bytes"] == reserve
    with pytest.raises(ValueError, match="reserve"):
        budget.require_space("unused", output + 1, minimum_free_bytes=reserve)


def test_default_retains_eight_gib_and_six_requires_explicit_selection(monkeypatch):
    monkeypatch.setattr(budget.shutil, "disk_usage",
                        lambda _: SimpleNamespace(free=7 * 1024**3))
    with pytest.raises(ValueError, match="8 GiB"):
        budget.require_space("unused", 0)
    budget.require_space("unused", 0, minimum_free_bytes=budget.MINIMUM_RESERVE)


@pytest.mark.parametrize("value", [True, 0, -1, 6.0, 6 * 1024**3 - 1])
def test_unsafe_or_noninteger_reserve_is_rejected(value):
    with pytest.raises(ValueError, match="at least 6 GiB"):
        budget.validate_reserve(value)


@pytest.mark.parametrize("value", [True, -1, 1.5])
def test_invalid_output_budget_is_rejected(value):
    with pytest.raises(ValueError, match="nonnegative integer"):
        budget.require_space("unused", value)
