#!/usr/bin/env python3
"""Bounded evidence-only opponent statistics probe with a reviewed image gate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HALFTIME_REFERENCE = "palermo_r55_opponent_xi_discovery_20261008/screens/78_autocontinue_inspect_013.png"
HALFTIME_REFERENCE_SHA256 = "01a705ff6f351fe97a33bc587daa68288f7accf49954509e1258ecebe8f21102"
HALFTIME_AHASH = int("8ffc8f80ff80ffff80720000ffffffffffffffff9f9f3c3e0000000018001807", 16)


def halftime_distance(path):
    from PIL import Image
    with Image.open(path) as image:
        if image.size != (640, 480):
            return 256
        pixels = list(image.convert("L").resize((16, 16)).getdata())
    mean = sum(pixels) / len(pixels)
    value = sum((pixel > mean) << index for index, pixel in enumerate(pixels))
    return (value ^ HALFTIME_AHASH).bit_count()


def install_probe(driver):
    original_record = driver._record_step
    original_auto = driver._derive_auto_continue_step
    original_recovery = driver._derive_dashboard_recovery_step
    state = {"clicked": False, "captured": False, "latest_half_distance": 256}

    def record(**kwargs):
        result = original_record(**kwargs)
        step = kwargs["step"]
        if step.label.startswith("autocontinue_inspect_") and result.get("screenshot"):
            state["latest_half_distance"] = halftime_distance(result["screenshot"])
            result["opponent_xi_half_layout_probe"] = {
                "reference": HALFTIME_REFERENCE,
                "reference_sha256": HALFTIME_REFERENCE_SHA256,
                "ahash_hamming_distance": state["latest_half_distance"],
                "threshold": 4,
            }
        return result

    def choose(candidate, last_label):
        if last_label == "opponent_xi_statistics_probe":
            state["captured"] = True
            return None
        if (not state["clicked"] and state["latest_half_distance"] <= 4
                and candidate is not None
                and candidate.label in {"halftime_continue_fallback", "halftime_continue"}):
            state["clicked"] = True
            return driver.StepSpec("opponent_xi_statistics_probe", "native_input_click", "381,319,1", 1.5)
        return candidate

    def auto(*, current_screen, last_label):
        return choose(original_auto(current_screen=current_screen, last_label=last_label), last_label)

    def recovery(*, current_screen, last_label):
        candidate, done = original_recovery(current_screen=current_screen, last_label=last_label)
        selected = choose(candidate, last_label)
        return selected, done if selected is candidate else False

    driver._record_step = record
    driver._derive_auto_continue_step = auto
    driver._derive_dashboard_recovery_step = recovery
    return state


def main():
    runner_dir = Path("/workspace/repo/scripts/pm99_runner")
    if not runner_dir.is_dir():
        runner_dir = Path(__file__).resolve().parents[1] / "upstream/pm99-runner/scripts/pm99_runner"
    sys.path.insert(0, str(runner_dir))
    import premier_offer_capture_driver as driver
    state = install_probe(driver)
    result = driver.main()
    output = Path(sys.argv[sys.argv.index("--artifacts-dir") + 1]) / "opponent_xi_probe.json"
    output.write_text(json.dumps({
        "schema": "pm99-opponent-halftime-statistics-discovery-v2",
        **state, "reference": HALFTIME_REFERENCE,
        "reference_sha256": HALFTIME_REFERENCE_SHA256,
        "scope": "Layout-gated screen discovery; XI acceptance requires independent row inspection.",
        "driver_exit_code": result,
    }, indent=2) + "\n")
    return result if state["captured"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
