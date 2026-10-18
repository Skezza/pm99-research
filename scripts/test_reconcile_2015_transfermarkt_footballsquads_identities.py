from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import reconcile_2015_transfermarkt_footballsquads_identities as reconciliation  # noqa: E402


def test_override_table_covers_the_125_review_rows_without_duplicate_keys() -> None:
    assert len(reconciliation.EXPLICIT_OVERRIDES) == 125
    assert len(set(reconciliation.EXPLICIT_OVERRIDES)) == 125
    assert all(country and name and target for (country, name), target in reconciliation.EXPLICIT_OVERRIDES.items())


def test_historical_and_non_latin_names_are_explicit_not_fuzzy() -> None:
    assert reconciliation.EXPLICIT_OVERRIDES[("russia", 'Футбольный клуб "Локомотив" Москва')] == "Lokomotiv Moscow"
    assert reconciliation.EXPLICIT_OVERRIDES[("turkey", "Ankaraspor")] == "Osmanlıspor"
    assert reconciliation.EXPLICIT_OVERRIDES[("ukraine", "PFK Stal Kamyanske (-2018)")] == "Stal Dniprodzerzhynsk"


def test_override_keys_are_country_scoped() -> None:
    # The same display name can occur in different national source families;
    # the country key is part of every decision.
    assert all(len(key) == 2 for key in reconciliation.EXPLICIT_OVERRIDES)
    assert ("italy", "AC Milan") in reconciliation.EXPLICIT_OVERRIDES
    assert ("spain", "Atlético de Madrid") in reconciliation.EXPLICIT_OVERRIDES
