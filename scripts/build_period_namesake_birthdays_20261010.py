"""Repair two namesakes using exact original season-row stable identities."""
from scripts import season_release_registry_v1 as registry
from scripts.build_compact_original_person_years_20261010 import main

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/period-namesake-birthdays-v1'
SOURCE = ROOT.parent / 'stock-club-history-v1'
CASES = {'2025-26': dict(base='sourced-original-secondary-facts-20261010-r83a',
    release='sourced-original-secondary-facts-20261010-r84a',
    replay='replayed-original-secondary-facts-20261010-r84b',
    targets={'27048': ['birth_date'], '27079': ['birth_date']}, count=2)}


if __name__ == '__main__':
    main(root=ROOT, cases=CASES, source=SOURCE / 'remaining-birthday-original-additional-people-v1.json',
        identity_document_path=SOURCE / 'period-namesake-independent-birthdays-v1.json')
