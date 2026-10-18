#!/usr/bin/env python3
"""Display a PM99 RGB565 frame as a host-sized X11 presentation surface."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np


SOURCE_WIDTH = 640
SOURCE_HEIGHT = 480
SOURCE_BYTES = SOURCE_WIDTH * SOURCE_HEIGHT * 2
SHAPE_INPUT = 2
SHAPE_SET = 0
UNSORTED = 0
WINDOW_NAME = "PM99UpscaleOverlay"


def disable_x11_input(window_id: int) -> bool:
    lib_x11 = ctypes.CDLL("libX11.so.6")
    lib_xext = ctypes.CDLL("libXext.so.6")
    lib_x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    lib_x11.XOpenDisplay.restype = ctypes.c_void_p
    lib_x11.XFlush.argtypes = [ctypes.c_void_p]
    lib_x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    lib_xext.XShapeCombineRectangles.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
    ]
    display = lib_x11.XOpenDisplay(None)
    if not display:
        return False
    try:
        lib_xext.XShapeCombineRectangles(
            display,
            window_id,
            SHAPE_INPUT,
            0,
            0,
            None,
            0,
            SHAPE_SET,
            UNSORTED,
        )
        lib_x11.XFlush(display)
        return True
    finally:
        lib_x11.XCloseDisplay(display)


def find_window_id(title: str) -> int | None:
    result = subprocess.run(
        ["xdotool", "search", "--name", f"^{title}$"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.splitlines()[-1])
    except (IndexError, ValueError):
        return None


def find_native_window_id(primary_title: str) -> int | None:
    """Find the PM99 top-level window across its normal title transitions."""

    for title in (primary_title, "MANAGPRE"):
        window_id = find_window_id(title)
        if window_id is not None:
            return window_id
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame-path", type=Path, required=True)
    parser.add_argument("--screen-width", type=int, required=True)
    parser.add_argument("--screen-height", type=int, required=True)
    parser.add_argument("--presentation-width", type=int, required=True)
    parser.add_argument("--presentation-height", type=int, required=True)
    parser.add_argument("--presentation-x", type=int, required=True)
    parser.add_argument("--presentation-y", type=int, required=True)
    parser.add_argument(
        "--upscale-filter",
        choices=("nearest", "linear", "scale2x", "scale2x-fit"),
        default="nearest",
        help="presentation scaler (default: nearest)",
    )
    parser.add_argument(
        "--match-only-adaptive",
        action="store_true",
        help="use adaptive upscaling/sharpening only for pitch-like live match frames",
    )
    parser.add_argument(
        "--comparison-dir",
        type=Path,
        help="write same-source nearest/adaptive match comparison images here",
    )
    parser.add_argument(
        "--menu-comparison-dir",
        type=Path,
        help="write a same-source nearest/edge-aware menu comparison here",
    )
    parser.add_argument(
        "--menu-comparison-final-frame",
        action="store_true",
        help="write the final eligible PM99 menu frame instead of the first one",
    )
    parser.add_argument(
        "--capture-native-window",
        action="store_true",
        help="sample the displayed native PM99 window instead of only the DirectDraw export",
    )
    parser.add_argument(
        "--source-mode",
        choices=("auto", "native-x11", "directdraw"),
        default="auto",
        help=(
            "frame source policy: auto can fall back to the DirectDraw export; "
            "native-x11 never reads that live export"
        ),
    )
    parser.add_argument(
        "--native-window-title",
        default="PREMIER MANAGER 99",
        help="exact title of the native window sampled by --capture-native-window",
    )
    parser.add_argument(
        "--interactive-input",
        action="store_true",
        help="forward clicks on the enlarged presentation to PM99's native buttons",
    )
    parser.add_argument(
        "--native-capture-hz",
        type=float,
        default=12.0,
        help="maximum completed native-window snapshots per second (default: 12)",
    )
    parser.add_argument(
        "--presentation-hz",
        type=float,
        default=30.0,
        help="maximum presentation updates per second (default: 30)",
    )
    args = parser.parse_args()
    if args.source_mode == "native-x11" and not args.capture_native_window:
        parser.error("--source-mode native-x11 requires --capture-native-window")
    if args.native_capture_hz <= 0 or args.presentation_hz <= 0:
        parser.error("capture and presentation rates must be greater than zero")
    return args


def frame_to_bgr(frame: bytes) -> np.ndarray:
    pixels = np.frombuffer(frame, dtype="<u2").reshape((SOURCE_HEIGHT, SOURCE_WIDTH))
    blue = ((pixels & 0x1F).astype(np.uint8)) << 3
    green = (((pixels >> 5) & 0x3F).astype(np.uint8)) << 2
    red = (((pixels >> 11) & 0x1F).astype(np.uint8)) << 3
    return np.dstack((blue, green, red))


def capture_native_window(window_id: int) -> np.ndarray | None:
    """Capture PM99's displayed 640x480 client without changing its renderer.

    The match engine presents through a different DirectDraw path from the
    management UI.  Sampling its native X11 window gives the presenter the
    same final raster the player sees, while leaving that DirectDraw path and
    the game executable entirely alone.
    """

    try:
        result = subprocess.run(
            ["import", "-window", hex(window_id), "png:-"],
            check=False,
            capture_output=True,
            timeout=1.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    source = cv2.imdecode(np.frombuffer(result.stdout, dtype=np.uint8), cv2.IMREAD_COLOR)
    if source is None or source.shape[:2] != (SOURCE_HEIGHT, SOURCE_WIDTH):
        return None
    return source


def has_visible_content(source: np.ndarray) -> bool:
    """Reject PM99's blank and solid-blue frames while it changes screen."""

    bright_pixels = np.max(source, axis=2) > 16
    if int(np.count_nonzero(bright_pixels)) <= 100:
        return False
    channel_stddev = source.reshape((-1, 3)).std(axis=0)
    # PM99's loading frame is almost entirely one deep-blue value.  Real menu
    # art has meaningful variation in at least its green or red channels.
    return bool(channel_stddev[1] > 15.0 or channel_stddev[2] > 15.0)


def presentation_to_native(x: int, y: int, args: argparse.Namespace) -> tuple[int, int] | None:
    """Map a host-presentation click to PM99's fixed 640x480 input space."""

    relative_x = x - args.presentation_x
    relative_y = y - args.presentation_y
    if not (0 <= relative_x < args.presentation_width and 0 <= relative_y < args.presentation_height):
        return None
    native_x = min(SOURCE_WIDTH - 1, relative_x * SOURCE_WIDTH // args.presentation_width)
    native_y = min(SOURCE_HEIGHT - 1, relative_y * SOURCE_HEIGHT // args.presentation_height)
    return native_x, native_y


def lower_presentation(window_id: int) -> None:
    subprocess.run(["wmctrl", "-ir", hex(window_id), "-b", "remove,above"], check=False)
    subprocess.run(["wmctrl", "-ir", hex(window_id), "-b", "add,hidden"], check=False)


def restore_presentation(window_id: int) -> None:
    subprocess.run(["wmctrl", "-ir", hex(window_id), "-b", "remove,hidden"], check=False)
    subprocess.run(["wmctrl", "-ir", hex(window_id), "-b", "add,above"], check=False)
    subprocess.run(["xdotool", "windowraise", str(window_id)], check=False)


def forward_native_click(x: int, y: int, button: int, args: argparse.Namespace, presentation_window_id: int) -> bool:
    """Deliver one enlarged-presentation click as an ordinary PM99 UI click."""

    mapped = presentation_to_native(x, y, args)
    if mapped is None:
        return False
    native_x, native_y = mapped
    try:
        native_window_id = find_native_window_id(args.native_window_title)
        if native_window_id is None:
            print("input forwarding failed: PM99 native window is unavailable", file=sys.stderr, flush=True)
            return False
        # Place the native 640x480 child on top, then issue the same real X11
        # pointer sequence PM99 receives in its ordinary native presentation.
        # xdotool resolves these coordinates relative to that native window.
        lower_presentation(presentation_window_id)
        subprocess.run(["wmctrl", "-ia", hex(native_window_id)], check=False)
        time.sleep(0.05)
        move_result = subprocess.run(
            ["xdotool", "mousemove", "--window", str(native_window_id), "--sync", str(native_x), str(native_y)],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        result = subprocess.run(
            ["xdotool", "click", str(button)],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"input forwarding failed host={x},{y} native={native_x},{native_y}: {exc}", file=sys.stderr, flush=True)
        return False
    if move_result.returncode != 0 or result.returncode != 0:
        detail = (move_result.stderr or move_result.stdout or result.stderr or result.stdout).strip()
        print(
            f"input forwarding failed host={x},{y} native={native_x},{native_y} {detail}",
            file=sys.stderr,
            flush=True,
        )
        return False
    print(f"forwarded click host={x},{y} native={native_x},{native_y} button={button}", flush=True)
    return True


def install_input_forwarding(
    args: argparse.Namespace,
    presentation_window_id: int,
    request_refresh: callable,
) -> None:
    event_buttons = {
        cv2.EVENT_LBUTTONUP: 1,
        cv2.EVENT_RBUTTONUP: 2,
        cv2.EVENT_MBUTTONUP: 3,
    }

    def on_mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        button = event_buttons.get(event)
        if button is not None:
            if forward_native_click(x, y, button, args, presentation_window_id):
                request_refresh()
            else:
                restore_presentation(presentation_window_id)

    cv2.setMouseCallback(WINDOW_NAME, on_mouse)


def scale2x(source: np.ndarray) -> np.ndarray:
    """Apply the edge-aware Scale2x pixel-art filter to a BGR image.

    PM99 is internally a 640x480 raster.  This does not invent higher-detail
    art, but it avoids turning every diagonal and curved UI edge into a rigid
    2x2 block before the final host-sized presentation.
    """

    padded = np.pad(source, ((1, 1), (1, 1), (0, 0)), mode="edge")
    above = padded[:-2, 1:-1]
    left = padded[1:-1, :-2]
    center = padded[1:-1, 1:-1]
    right = padded[1:-1, 2:]
    below = padded[2:, 1:-1]

    equal = lambda first, second: np.all(first == second, axis=2)
    top_left = np.where(
        (equal(left, above) & ~equal(left, below) & ~equal(above, right))[..., None],
        left,
        center,
    )
    top_right = np.where(
        (equal(above, right) & ~equal(above, left) & ~equal(right, below))[..., None],
        right,
        center,
    )
    bottom_left = np.where(
        (equal(left, below) & ~equal(left, above) & ~equal(below, right))[..., None],
        left,
        center,
    )
    bottom_right = np.where(
        (equal(below, right) & ~equal(left, below) & ~equal(above, right))[..., None],
        right,
        center,
    )

    height, width = source.shape[:2]
    output = np.empty((height * 2, width * 2, 3), dtype=source.dtype)
    output[0::2, 0::2] = top_left
    output[0::2, 1::2] = top_right
    output[1::2, 0::2] = bottom_left
    output[1::2, 1::2] = bottom_right
    return output


def upscale(source: np.ndarray, args: argparse.Namespace) -> np.ndarray:
    if args.upscale_filter == "linear":
        return cv2.resize(
            source,
            (args.presentation_width, args.presentation_height),
            interpolation=cv2.INTER_LINEAR,
        )
    if args.upscale_filter == "scale2x":
        source = scale2x(source)
    if args.upscale_filter == "scale2x-fit":
        return smooth_menu_upscale(source, args)
    return cv2.resize(
        source,
        (args.presentation_width, args.presentation_height),
        interpolation=cv2.INTER_NEAREST,
    )


def smooth_menu_upscale(source: np.ndarray, args: argparse.Namespace) -> np.ndarray:
    """Apply a restrained no-asset menu treatment for the visual A/B POC.

    Scale2x first resolves hard one-pixel UI corners from their immediate
    neighbours.  The remaining 12.5% fit from 1280x960 to a 1440x1080 4:3
    presentation is deliberately bilinear: it removes uneven 2/3-pixel
    blocks without applying a broad blur to the original 640x480 artwork.
    This is a display transformation only; it changes neither PM99 data nor
    hit-testing coordinates.
    """

    return cv2.resize(
        scale2x(source),
        (args.presentation_width, args.presentation_height),
        interpolation=cv2.INTER_LINEAR,
    )


def pitch_mask(source: np.ndarray) -> np.ndarray:
    """Return a mask for pixels that look like the grass pitch."""

    blue, green, red = cv2.split(source)
    return (
        (green > 45)
        & (green.astype(np.int16) > red.astype(np.int16) + 18)
        & (green.astype(np.int16) > blue.astype(np.int16) + 8)
    )


def pitch_ratio(source: np.ndarray) -> float:
    """Return the fraction of an image occupied by grass-like pixels."""

    mask = pitch_mask(source)
    return float(np.count_nonzero(mask)) / float(mask.size)


def looks_like_live_match(source: np.ndarray) -> bool:
    """Recognize a pitch-dominant frame without inspecting PM99's state.

    The compositor only sees RGB pixels, so this deliberately has a conservative
    threshold.  A false negative merely leaves a match frame pixel-exact; a
    false positive would blur a menu, which is the behaviour we must avoid.
    """

    mask = pitch_mask(source)
    foreground = mask[(SOURCE_HEIGHT * 3) // 4 :, :]
    foreground_ratio = float(np.count_nonzero(foreground)) / float(foreground.size)
    # The pre-kick-off tactical board is also a green pitch, but its lower
    # quarter is a blue player-list panel.  The 3D camera's foreground is
    # grass, so this preserves every static match UI element exactly while
    # enabling the adaptive treatment only once the live scene is visible.
    return (
        float(np.count_nonzero(mask)) / float(mask.size) >= 0.18
        and foreground_ratio >= 0.75
    )


def adaptive_match_upscale(source: np.ndarray, args: argparse.Namespace) -> np.ndarray:
    """Use a photographic scaler plus contrast-limited edge sharpening.

    Unlike the UI, the 3D match has gradients and textured geometry.  Lanczos
    reconstruction makes that content less blocky, while the per-pixel gain
    keeps flat grass/crowd areas from receiving the same sharpening as real
    model and pitch-line edges.
    """

    enlarged = cv2.resize(
        source,
        (args.presentation_width, args.presentation_height),
        interpolation=cv2.INTER_LANCZOS4,
    )
    softened = cv2.GaussianBlur(enlarged, (0, 0), sigmaX=0.8, sigmaY=0.8)
    detail = enlarged.astype(np.float32) - softened.astype(np.float32)
    edge_energy = np.max(np.abs(detail), axis=2, keepdims=True)
    gain = 0.12 + 0.34 * np.clip(edge_energy / 28.0, 0.0, 1.0)
    return np.clip(enlarged.astype(np.float32) + detail * gain, 0, 255).astype(np.uint8)


def host_canvas(scaled: np.ndarray, args: argparse.Namespace) -> np.ndarray:
    presentation = np.zeros((args.screen_height, args.screen_width, 3), dtype=np.uint8)
    y_end = args.presentation_y + args.presentation_height
    x_end = args.presentation_x + args.presentation_width
    presentation[args.presentation_y:y_end, args.presentation_x:x_end] = scaled
    return presentation


def write_match_comparison(source: np.ndarray, args: argparse.Namespace) -> None:
    if args.comparison_dir is None:
        return
    args.comparison_dir.mkdir(parents=True, exist_ok=True)
    nearest = host_canvas(
        cv2.resize(
            source,
            (args.presentation_width, args.presentation_height),
            interpolation=cv2.INTER_NEAREST,
        ),
        args,
    )
    adaptive = host_canvas(adaptive_match_upscale(source, args), args)
    cv2.imwrite(str(args.comparison_dir / "match_source_640.png"), source)
    cv2.imwrite(str(args.comparison_dir / "match_before_nearest.png"), nearest)
    cv2.imwrite(str(args.comparison_dir / "match_after_adaptive.png"), adaptive)

    comparison = np.concatenate((nearest, adaptive), axis=1)
    label_y = min(args.screen_height - 24, 48)
    cv2.putText(
        comparison,
        "BEFORE: PIXEL-EXACT NEAREST",
        (24, label_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        comparison,
        "AFTER: ADAPTIVE LANCZOS + EDGE SHARPENING",
        (args.screen_width + 24, label_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.imwrite(str(args.comparison_dir / "match_before_after.png"), comparison)


def write_menu_comparison(source: np.ndarray, source_kind: str, args: argparse.Namespace) -> None:
    """Write a deterministic no-asset A/B from one native PM99 menu raster."""

    if args.menu_comparison_dir is None:
        return
    args.menu_comparison_dir.mkdir(parents=True, exist_ok=True)
    nearest = host_canvas(
        cv2.resize(
            source,
            (args.presentation_width, args.presentation_height),
            interpolation=cv2.INTER_NEAREST,
        ),
        args,
    )
    smooth = host_canvas(smooth_menu_upscale(source, args), args)
    cv2.imwrite(str(args.menu_comparison_dir / "menu_source_640.png"), source)
    cv2.imwrite(str(args.menu_comparison_dir / "menu_before_nearest.png"), nearest)
    cv2.imwrite(str(args.menu_comparison_dir / "menu_after_scale2x_fit.png"), smooth)

    # Put labels in a separate header so neither A nor B has a game pixel
    # obscured by annotation.  The two panels remain byte-for-byte the images
    # written above, positioned beneath the header.
    header_height = 64
    header = np.zeros((header_height, args.screen_width * 2, 3), dtype=np.uint8)
    cv2.putText(
        header,
        "A: PIXEL-EXACT NEAREST",
        (24, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        header,
        "B: SCALE2X + RESTRAINED FINAL FIT (NO NEW ASSETS)",
        (args.screen_width + 24, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    comparison = np.concatenate((nearest, smooth), axis=1)
    cv2.imwrite(
        str(args.menu_comparison_dir / "menu_before_after.png"),
        np.concatenate((header, comparison), axis=0),
    )
    manifest = {
        "kind": "same-source-menu-upscale-ab",
        "source_sha256": hashlib.sha256(source.tobytes()).hexdigest(),
        "source_kind": source_kind,
        "source_dimensions": [SOURCE_WIDTH, SOURCE_HEIGHT],
        "presentation_dimensions": [args.presentation_width, args.presentation_height],
        "host_dimensions": [args.screen_width, args.screen_height],
        "before": "nearest-neighbour from native 640x480",
        "after": "Scale2x, then final bilinear fit to presentation size",
        "assets_modified": False,
        "input_coordinates_modified": False,
    }
    (args.menu_comparison_dir / "menu_ab_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    args = parse_args()
    running = True

    def stop(*_unused: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, args.screen_width, args.screen_height)
    cv2.moveWindow(WINDOW_NAME, 0, 0)
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.imshow(WINDOW_NAME, np.zeros((args.screen_height, args.screen_width, 3), dtype=np.uint8))
    cv2.waitKey(1)
    window_id = find_window_id(WINDOW_NAME)
    if window_id is None:
        print("unable to locate PM99 overlay window", file=sys.stderr, flush=True)
        cv2.destroyAllWindows()
        return 1
    interactive_state = {
        "presentation_visible": not args.interactive_input,
        "refresh_after": 0.0,
        "fresh_native_frame": False,
    }

    def request_interactive_refresh() -> None:
        interactive_state["presentation_visible"] = False
        interactive_state["refresh_after"] = time.monotonic() + 0.20
        interactive_state["fresh_native_frame"] = False

    if args.interactive_input:
        install_input_forwarding(args, window_id, request_interactive_refresh)
        lower_presentation(window_id)
        print("input mode=scaled-click-forwarding", flush=True)
    elif not disable_x11_input(window_id):
        print("unable to make PM99 overlay input-transparent", file=sys.stderr, flush=True)
        cv2.destroyAllWindows()
        return 1
    else:
        subprocess.run(["wmctrl", "-ir", hex(window_id), "-b", "add,above"], check=False)

    print(
        "source policy="
        f"{args.source_mode} native_capture_hz={args.native_capture_hz:g} "
        f"presentation_hz={args.presentation_hz:g}",
        flush=True,
    )
    last_frame = b""
    last_presentation_mode = ""
    comparison_written = False
    menu_comparison_written = False
    last_eligible_menu_source: np.ndarray | None = None
    last_eligible_menu_source_kind = ""
    native_window_id: int | None = None
    latest_native_source: np.ndarray | None = None
    next_native_capture_at = 0.0
    using_native_capture: bool | None = None
    while running:
        source: np.ndarray | None = None
        if args.capture_native_window and args.source_mode != "directdraw":
            now = time.monotonic()
            capture_allowed = (
                not args.interactive_input
                or (
                    not interactive_state["presentation_visible"]
                    and now >= interactive_state["refresh_after"]
                )
            )
            if capture_allowed and now >= next_native_capture_at:
                next_native_capture_at = now + (1.0 / args.native_capture_hz)
                if native_window_id is None:
                    native_window_id = find_native_window_id(args.native_window_title)
                if native_window_id is not None:
                    captured_native_source = capture_native_window(native_window_id)
                    if captured_native_source is None:
                        native_window_id = None
                    elif has_visible_content(captured_native_source):
                        latest_native_source = captured_native_source
                        if args.interactive_input and not interactive_state["presentation_visible"]:
                            interactive_state["fresh_native_frame"] = True
                            last_frame = b""
            source = latest_native_source
        if source is not None:
            frame = source.tobytes()
            if using_native_capture is not True:
                print("frame source=native-x11", flush=True)
                using_native_capture = True
        elif args.source_mode != "native-x11":
            if using_native_capture is not False:
                print("frame source=directdraw-export", flush=True)
                using_native_capture = False
            try:
                frame = args.frame_path.read_bytes()
            except FileNotFoundError:
                frame = b""
            if len(frame) == SOURCE_BYTES:
                source = frame_to_bgr(frame)
        if source is not None and frame != last_frame:
            is_live_match = bool(args.match_only_adaptive and looks_like_live_match(source))
            if is_live_match:
                scaled = adaptive_match_upscale(source, args)
                presentation_mode = "adaptive-match"
            else:
                scaled = upscale(source, args)
                presentation_mode = f"menu-{args.upscale_filter}"
            if presentation_mode != last_presentation_mode:
                print(f"presentation mode={presentation_mode}", flush=True)
                last_presentation_mode = presentation_mode
            if not comparison_written and looks_like_live_match(source):
                write_match_comparison(source, args)
                print("wrote same-source match comparison", flush=True)
                comparison_written = True
            menu_source_ready = has_visible_content(source)
            source_kind = "native-x11" if using_native_capture is True else "directdraw-rgb565"
            if menu_source_ready and not looks_like_live_match(source):
                # Keep a private copy because OpenCV's capture buffer is
                # replaced on the next native X11 sample.  A final-frame A/B
                # is how a scripted route can target a specific menu state
                # without relying on timing or a hand-composited screenshot.
                last_eligible_menu_source = source.copy()
                last_eligible_menu_source_kind = source_kind
            if (
                args.menu_comparison_dir is not None
                and not menu_comparison_written
                and not looks_like_live_match(source)
                and menu_source_ready
                and not args.menu_comparison_final_frame
            ):
                write_menu_comparison(source, source_kind, args)
                print("wrote same-source menu comparison", flush=True)
                menu_comparison_written = True
            if (
                args.interactive_input
                and not interactive_state["presentation_visible"]
                and interactive_state["fresh_native_frame"]
                and using_native_capture is True
            ):
                # Remapping the Qt surface drops its backing pixels, so make it
                # visible first and paint the current PM99 raster immediately
                # afterwards.
                restore_presentation(window_id)
                interactive_state["presentation_visible"] = True
                print("interactive presentation refreshed", flush=True)
            cv2.imshow(WINDOW_NAME, host_canvas(scaled, args))
            last_frame = frame
        cv2.waitKey(1)
        time.sleep(1.0 / args.presentation_hz)
    if (
        args.menu_comparison_dir is not None
        and args.menu_comparison_final_frame
        and last_eligible_menu_source is not None
    ):
        write_menu_comparison(last_eligible_menu_source, last_eligible_menu_source_kind, args)
        print("wrote final same-source menu comparison", flush=True)
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
