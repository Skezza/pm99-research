import pytest

from scripts import apply_stock_kit_seed_remap_v1 as stock


def source(carrier_id, name):
    return {"carrier_id": carrier_id, "record_mode": 1,
            "baseline_club": {"name": name, "full_name": name}}


def target(carrier_id, name):
    return {"carrier_id": carrier_id, "division": "preserve-existing-mode1-membership",
            "name": name, "full_name": name}


def test_identical_nacional_names_do_not_join_uruguay_to_portugal():
    with pytest.raises(stock.StockKitRemapError, match="matching short names"):
        stock._check_stock_country_identity(source(2901, "Nacional"), target(609, "Nacional"))


@pytest.mark.parametrize("seed, recipient", [
    (source(1107, "Basel"), target(1104, "Basel")),
    (source(1805, "Vaduz"), target(1109, "Vaduz")),
    (source(3331, "Colwyn Bay"), target(2060, "Colwyn Bay")),
    (source(3331, "Colwyn Bay"), target(2055, "Colwyn B.")),
])
def test_same_country_or_explicit_same_club_competition_bridge(seed, recipient):
    stock._check_stock_country_identity(seed, recipient)


def test_exception_cannot_apply_to_a_different_club_or_country():
    with pytest.raises(stock.StockKitRemapError):
        stock._check_stock_country_identity(source(1805, "Vaduz"), target(1109, "Nacional"))
    with pytest.raises(stock.StockKitRemapError):
        stock._check_stock_country_identity(source(1805, "Vaduz"), target(609, "Vaduz"))


def test_unknown_country_is_not_an_identity_match():
    with pytest.raises(stock.StockKitRemapError, match="known source and target"):
        stock._check_stock_country_identity(source(999999, "Nacional"), target(609, "Nacional"))
