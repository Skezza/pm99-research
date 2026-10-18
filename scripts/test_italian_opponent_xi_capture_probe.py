"""Bounded research adapter tests; no GUI or native database required."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def test_dedicated_v3_wrapper_defaults_to_its_private_statistics_adapter():
    root = Path(__file__).resolve().parents[1]
    shell = (root / 'experiments/run_italian_opponent_xi_private_probe_v3.sh').read_text()
    assert '${PM99_ITALIAN_OPPONENT_XI_PROBE:-1}' in shell
    assert 'ITALIAN_DRIVER_PATH=/workspace/artifacts/italian_opponent_xi_capture_driver_v3.py' in shell
    assert '"${ITALIAN_DRIVER_PATH}"' in shell


def test_halftime_opponent_probe_is_single_bounded_read_only_click():
    path = Path(__file__).resolve().parents[1] / "experiments/italian_opponent_xi_capture_driver.py"
    spec = importlib.util.spec_from_file_location("opponent_xi_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    driver = SimpleNamespace(
        _derive_auto_continue_step=lambda **kwargs: calls.append(kwargs) or "original",
        StepSpec=lambda **kwargs: kwargs,
    )
    state = module.install_probe(driver)
    assert driver._derive_auto_continue_step(
        current_screen="club_dashboard_screen", last_label=None,
    ) == "original"
    step = driver._derive_auto_continue_step(
        current_screen="match_halftime_screen", last_label=None,
    )
    assert step == {
        "label": "opponent_xi_statistics_probe",
        "action": "native_input_click",
        "value": "381,319,1",
        "delay_seconds": 1.5,
    }
    assert state == {"clicked": True, "captured": False}
    assert driver._derive_auto_continue_step(
        current_screen="unknown", last_label=step["label"],
    ) is None
    assert state == {"clicked": True, "captured": True}
    assert driver._derive_auto_continue_step(
        current_screen="match_halftime_screen", last_label=None,
    ) == "original"
    assert len(calls) == 2


def test_v2_requires_reviewed_layout_and_halftime_transition_and_stops_both_routes():
    path = Path(__file__).resolve().parents[1] / "experiments/italian_opponent_xi_capture_driver_v2.py"
    spec = importlib.util.spec_from_file_location("opponent_xi_probe_v2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    candidate = SimpleNamespace(label="halftime_continue_fallback")
    driver = SimpleNamespace(
        _record_step=lambda **kwargs: {},
        _derive_auto_continue_step=lambda **kwargs: candidate,
        _derive_dashboard_recovery_step=lambda **kwargs: (candidate, False),
        StepSpec=lambda *args: SimpleNamespace(label=args[0], value=args[2]),
    )
    state = module.install_probe(driver)
    assert driver._derive_auto_continue_step(current_screen="match_intro_screen", last_label=None) is candidate
    state["latest_half_distance"] = 1
    candidate.label = "dashboard_continue"
    assert driver._derive_auto_continue_step(current_screen="club_dashboard_screen", last_label=None) is candidate
    candidate.label = "halftime_continue_fallback"
    action = driver._derive_auto_continue_step(current_screen="match_intro_screen", last_label=None)
    assert action.label == "opponent_xi_statistics_probe" and action.value == "381,319,1"
    assert driver._derive_dashboard_recovery_step(current_screen="unknown", last_label=action.label) == (None, False)
    assert state["captured"]
    assert driver._derive_auto_continue_step(current_screen="unknown", last_label=action.label) is None


def test_v2_real_retained_screen_gate_when_corpus_available():
    import pytest
    root = Path(__file__).resolve().parents[1]
    runtime = root / ".local/italian-delivery/runtime"
    if not (runtime / "palermo_r55_opponent_xi_discovery_20261008").is_dir():
        pytest.skip("Local-only proprietary runtime screenshot corpus unavailable")
    spec = importlib.util.spec_from_file_location("opponent_xi_probe_v2_images", root / "experiments/italian_opponent_xi_capture_driver_v2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for tag in ["milan_r54_actual_matchplay_20261008", "palermo_r55_actual_matchplay_20261008", "palermo_r55_opponent_xi_discovery_20261008"]:
        for number, expected in [(76, False), (78, True), (82, False), (52, False), (0, False)]:
            image = next((runtime / tag / "screens").glob(f"{number:02d}_*.png"))
            assert (module.halftime_distance(image) <= 4) is expected, image


def test_v3_activates_statistics_with_double_click_after_same_strict_gate():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("opponent_xi_probe_v3", root / "experiments/italian_opponent_xi_capture_driver_v3.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    candidate = SimpleNamespace(label="halftime_continue_fallback")
    driver = SimpleNamespace(
        _record_step=lambda **kwargs: {},
        _derive_auto_continue_step=lambda **kwargs: candidate,
        _derive_dashboard_recovery_step=lambda **kwargs: (candidate, False),
        StepSpec=lambda *args: SimpleNamespace(label=args[0], action=args[1], value=args[2]),
    )
    state = module.install_probe(driver)
    assert driver._derive_auto_continue_step(current_screen="match_intro_screen", last_label=None) is candidate
    state["latest_half_distance"] = 1
    step = driver._derive_auto_continue_step(current_screen="match_intro_screen", last_label=None)
    assert (step.label, step.action, step.value) == ("opponent_xi_statistics_probe", "native_double_click", "381,319,1")
    assert driver._derive_auto_continue_step(current_screen="unknown", last_label=step.label) is None
    assert state["captured"]
