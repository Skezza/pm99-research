"""Deliver two independently read original-period namesake birthdays."""
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import run
from scripts.build_period_namesake_birthdays_20261010 import ROOT, CASES


if __name__ == '__main__':
    run(root=ROOT, cases=CASES, profiles={
        '2025-26': ('webster', 27048, 'Harry Webster', 'Gillingham', 19, None),
    }, prior_version=27, next_version=28, expected_delivered=241, expected_remaining=6,
        expected_new_dates=2, native_readback_version=10, proof_suffix='-independent-proof.json',
        close_ferran_finding=False)
