from types import SimpleNamespace

from scripts.preview_2015_fifa_kit_correction_v1 import _metrics, _top_down


def test_top_down_rows_reverse_the_native_bottom_up_pixel_lane() -> None:
    record = SimpleNamespace(width=2, height=2, pixel_offset=0)
    assert _top_down([3, 4, 1, 2], record) == [[1, 2], [3, 4]]


def test_metrics_count_visible_indices_only() -> None:
    record = SimpleNamespace(width=2, height=2, pixel_offset=0)
    metrics = _metrics(bytes([0, 1, 2, 2]), record, [(0, 0, 0), (100, 0, 0), (200, 0, 0)])
    assert metrics["visible_pixel_count"] == 3
    assert metrics["unique_palette_index_count"] == 2
