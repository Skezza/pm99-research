#!/usr/bin/env python3
"""Evidence-only adapter: inspect opponent statistics at the first half-time.

No database writes, no production-driver edits. A captured statistics screen is
not automatically proof of the starting XI: its rows must be inspected first.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def install_probe(driver):
    original = driver._derive_auto_continue_step
    state = {"clicked": False, "captured": False}

    def derive(*, current_screen, last_label):
        if last_label == "opponent_xi_statistics_probe":
            state["captured"] = True
            return None
        if current_screen == "match_halftime_screen" and not state["clicked"]:
            state["clicked"] = True
            return driver.StepSpec(
                label="opponent_xi_statistics_probe",
                action="native_input_click",
                value="381,319,1",
                delay_seconds=1.5,
            )
        return original(current_screen=current_screen, last_label=last_label)

    driver._derive_auto_continue_step = derive
    return state


def main():
    runner_dir = Path("/workspace/repo/scripts/pm99_runner")
    if not runner_dir.is_dir():
        runner_dir = Path(__file__).resolve().parents[1] / "upstream/pm99-runner/scripts/pm99_runner"
    sys.path.insert(0, str(runner_dir))
    import premier_offer_capture_driver as driver

    state = install_probe(driver)
    result = driver.main()
    artifact_arg = sys.argv.index("--artifacts-dir") + 1
    output = Path(sys.argv[artifact_arg]) / "opponent_xi_probe.json"
    output.write_text(json.dumps({
        "schema": "pm99-opponent-halftime-statistics-discovery-v1",
        **state,
        "scope": "Screen discovery only; XI acceptance requires independent row inspection.",
        "driver_exit_code": result,
    }, indent=2) + "\n")
    return result if state["captured"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
