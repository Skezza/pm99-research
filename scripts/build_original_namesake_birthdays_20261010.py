"""Use independently corroborated identities, not youngest namesake guesses."""
from scripts import season_release_registry_v1 as registry
from scripts.build_compact_original_person_years_20261010 import main

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/original-namesake-birthdays-v1'
SOURCE = ROOT.parent / 'stock-club-history-v1'
CASES = {'2025-26': dict(base='sourced-original-secondary-facts-20261010-r82a',
    release='sourced-original-secondary-facts-20261010-r83a',
    replay='replayed-original-secondary-facts-20261010-r83b',
    targets={'10125': ['birth_date'], '10666': ['birth_date']}, count=2)}


if __name__ == '__main__':
    main(root=ROOT, cases=CASES, source=SOURCE / 'remaining-birthday-original-additional-people-v1.json',
        identity_document_path=SOURCE / 'namesake-birthday-independent-biographies-v1.json')
