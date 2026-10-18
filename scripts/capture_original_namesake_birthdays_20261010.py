"""Serialize original namesake factual proof after the preceding final profile."""
from scripts.capture_original_secondary_facts_20261010 import main
from scripts.build_original_namesake_birthdays_20261010 import ROOT, CASES


if __name__ == '__main__':
    main(root=ROOT, cases=CASES, profiles={'2025-26': ('Dylan Lawlor', 'lawlor', 10666)},
        preceding=ROOT.parent / 'compact-original-person-birth-years-v1/mubama-profile-transport.json',
        proof_suffix='-independent-proof.json')
