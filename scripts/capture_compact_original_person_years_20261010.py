"""Serialize two compact-year candidate checks after the preceding physical run."""
from scripts.capture_original_secondary_facts_20261010 import main
from scripts.build_compact_original_person_years_20261010 import ROOT, CASES


if __name__ == '__main__':
    main(root=ROOT, cases=CASES, profiles={
        '2024-25': ('Shade', 'shade', 10958),
        '2025-26': ('Hubbard', 'hubbard', 10958),
    }, preceding=ROOT.parent / 'original-secondary-facts-v1/otegbayo-profile-transport.json',
        proof_suffix='-independent-proof.json')
