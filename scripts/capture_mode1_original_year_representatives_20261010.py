"""Retain failed NPC search; test actual modern ages in each exact candidate.

These are representative loader checks, not direct Shade/Hubbard profiles.
The selected NPC dates themselves are checked independently in native bytes.
"""
from scripts.capture_original_secondary_facts_20261010 import main
from scripts.build_compact_original_person_years_20261010 import ROOT, CASES


if __name__ == '__main__':
    main(root=ROOT, cases=CASES, profiles={
        '2024-25': ('Tezgel', 'tezgel', 10744),
        '2025-26': ('Mubama', 'mubama', 10341),
    }, preceding=ROOT.parent / 'original-secondary-facts-v1/otegbayo-profile-transport.json',
        proof_suffix='-independent-proof.json')
