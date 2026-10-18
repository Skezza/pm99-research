#!/usr/bin/env bash
set -euo pipefail

resize_legacy_window="${PM99_DDRAW_X11_RESIZE:-0}"
hide_legacy_window="${PM99_DDRAW_X11_HIDE_LEGACY:-0}"
x11_compositor="${PM99_DDRAW_X11_UPSCALE_OVERLAY:-0}"
compositor_raise_delay_seconds="${PM99_DDRAW_X11_OVERLAY_RAISE_DELAY_SECONDS:-0}"
compositor_start_delay_seconds="${PM99_DDRAW_X11_OVERLAY_START_DELAY_SECONDS:-0}"
driver_dir="${PM99_DDRAW_DRIVER_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
overlay_script="${PM99_DDRAW_X11_OVERLAY_SCRIPT:-${driver_dir}/pm99_x11_upscale_overlay.py}"

if [[ "${resize_legacy_window}" != "1" && "${hide_legacy_window}" != "1" && "${x11_compositor}" != "1" ]]; then
  exec "$@"
fi

if [[ "${hide_legacy_window}" == "1" ]]; then
  presentation_mode=hide
  target_width=640
  target_height=480
  target_x="${PM99_DDRAW_LEGACY_HIDE_X:--640}"
  target_y="${PM99_DDRAW_LEGACY_HIDE_Y:-0}"
  hide_delay_seconds="${PM99_DDRAW_LEGACY_HIDE_DELAY_SECONDS:-10}"
else
  presentation_mode=resize
  target_width="${PM99_DDRAW_PRESENTATION_WIDTH:?PM99_DDRAW_PRESENTATION_WIDTH is required}"
  target_height="${PM99_DDRAW_PRESENTATION_HEIGHT:?PM99_DDRAW_PRESENTATION_HEIGHT is required}"
  target_x="${PM99_DDRAW_PRESENTATION_X:-0}"
  target_y="${PM99_DDRAW_PRESENTATION_Y:-0}"
  hide_delay_seconds=0
fi
resize_log="${PM99_DDRAW_X11_RESIZE_LOG:-/workspace/artifacts/pm99-ddraw-window-resize.log}"
compositor_pid=""
compositor_raise_pid=""

if [[ "${x11_compositor}" == "1" ]]; then
  compositor_log="${PM99_DDRAW_X11_UPSCALE_OVERLAY_LOG:-/workspace/artifacts/pm99-ddraw-x11-overlay.log}"
  compositor_args=(
    --frame-path "${PM99_DDRAW_FRAME_PATH:?PM99_DDRAW_FRAME_PATH is required}"
    --screen-width "${PM99_DDRAW_HOST_WIDTH:?PM99_DDRAW_HOST_WIDTH is required}"
    --screen-height "${PM99_DDRAW_HOST_HEIGHT:?PM99_DDRAW_HOST_HEIGHT is required}"
    --presentation-width "${PM99_DDRAW_PRESENTATION_WIDTH:?PM99_DDRAW_PRESENTATION_WIDTH is required}"
    --presentation-height "${PM99_DDRAW_PRESENTATION_HEIGHT:?PM99_DDRAW_PRESENTATION_HEIGHT is required}"
    --presentation-x "${PM99_DDRAW_PRESENTATION_X:-0}"
    --presentation-y "${PM99_DDRAW_PRESENTATION_Y:-0}"
    --upscale-filter "${PM99_DDRAW_X11_UPSCALE_FILTER:-nearest}"
  )
  if [[ "${PM99_DDRAW_X11_MATCH_ONLY_ADAPTIVE:-0}" == "1" ]]; then
    compositor_args+=(--match-only-adaptive)
  fi
  if [[ -n "${PM99_DDRAW_X11_MATCH_COMPARISON_DIR:-}" ]]; then
    compositor_args+=(--comparison-dir "${PM99_DDRAW_X11_MATCH_COMPARISON_DIR}")
  fi
  if [[ -n "${PM99_DDRAW_X11_MENU_COMPARISON_DIR:-}" ]]; then
    compositor_args+=(--menu-comparison-dir "${PM99_DDRAW_X11_MENU_COMPARISON_DIR}")
  fi
  if [[ "${PM99_DDRAW_X11_MENU_COMPARISON_FINAL_FRAME:-0}" == "1" ]]; then
    compositor_args+=(--menu-comparison-final-frame)
  fi
  if [[ "${PM99_DDRAW_X11_CAPTURE_NATIVE_WINDOW:-1}" == "1" ]]; then
    compositor_args+=(--capture-native-window)
  fi
  if [[ -n "${PM99_DDRAW_X11_SOURCE_MODE:-}" ]]; then
    compositor_args+=(--source-mode "${PM99_DDRAW_X11_SOURCE_MODE}")
  fi
  if [[ -n "${PM99_DDRAW_X11_NATIVE_CAPTURE_HZ:-}" ]]; then
    compositor_args+=(--native-capture-hz "${PM99_DDRAW_X11_NATIVE_CAPTURE_HZ}")
  fi
  if [[ -n "${PM99_DDRAW_X11_PRESENTATION_HZ:-}" ]]; then
    compositor_args+=(--presentation-hz "${PM99_DDRAW_X11_PRESENTATION_HZ}")
  fi
  if [[ "${PM99_DDRAW_X11_INTERACTIVE_INPUT:-0}" == "1" ]]; then
    compositor_args+=(--interactive-input)
  fi
fi

start_compositor() {
  python3 "${overlay_script}" "${compositor_args[@]}" \
    > "${compositor_log}" 2>&1 &
  compositor_pid=$!
}

start_delayed_compositor() {
  sleep "${compositor_start_delay_seconds}"
  if kill -0 "${driver_pid}" >/dev/null 2>&1; then
    # Replace the lightweight timer with the compositor so the parent can
    # still terminate and wait for one known PID during cleanup.
    exec python3 "${overlay_script}" "${compositor_args[@]}" \
      > "${compositor_log}" 2>&1
  fi
}

if [[ "${x11_compositor}" == "1" && "${compositor_start_delay_seconds}" == "0" ]]; then
  start_compositor
fi

"$@" &
driver_pid=$!

if [[ "${x11_compositor}" == "1" && "${compositor_start_delay_seconds}" != "0" ]]; then
  start_delayed_compositor &
  compositor_pid=$!
fi

keep_compositor_above() {
  # The Wine window is mapped after the compositor.  Fluxbox then gives the
  # newly mapped native window the top stacking position, even though the
  # compositor asks for _NET_WM_STATE_ABOVE.  Keep the input-transparent
  # presentation window above it without focusing either window; X Shape has
  # already removed the compositor's input region, so PM99 continues to get
  # the runner's native clicks.
  if [[ "${compositor_raise_delay_seconds}" != "0" ]]; then
    sleep "${compositor_raise_delay_seconds}"
  fi
  while kill -0 "${driver_pid}" >/dev/null 2>&1; do
    compositor_window_id="$(xdotool search --onlyvisible --name '^PM99UpscaleOverlay$' 2>/dev/null | tail -n 1 || true)"
    if [[ -n "${compositor_window_id}" ]]; then
      xdotool windowraise "${compositor_window_id}" >/dev/null 2>&1 || true
    fi
    sleep 0.25
  done
}

if [[ "${x11_compositor}" == "1" \
  && "${PM99_DDRAW_X11_INTERACTIVE_INPUT:-0}" != "1" \
  && "${PM99_DDRAW_X11_KEEP_ABOVE:-1}" == "1" ]]; then
  keep_compositor_above &
  compositor_raise_pid=$!
fi

resize_game_window() {
  if [[ "${hide_delay_seconds}" != "0" ]]; then
    sleep "${hide_delay_seconds}"
  fi
  while kill -0 "${driver_pid}" >/dev/null 2>&1; do
    window_id="$(xdotool search --onlyvisible --name 'PREMIER MANAGER 99' 2>/dev/null | tail -n 1 || true)"
    if [[ -n "${window_id}" ]]; then
      xdotool windowmove "${window_id}" "${target_x}" "${target_y}" >/dev/null 2>&1 || true
      xdotool windowsize "${window_id}" "${target_width}" "${target_height}" >/dev/null 2>&1 || true
      printf '%s window=%s mode=%s target=%sx%s+%s+%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        "${window_id}" \
        "${presentation_mode}" \
        "${target_width}" \
        "${target_height}" \
        "${target_x}" \
        "${target_y}" >> "${resize_log}"
    fi
    sleep 0.25
  done
}

resize_pid=""
if [[ "${resize_legacy_window}" == "1" || "${hide_legacy_window}" == "1" ]]; then
  resize_game_window &
  resize_pid=$!
fi

set +e
wait "${driver_pid}"
driver_status=$?
set -e
if [[ -n "${resize_pid}" ]]; then
  kill "${resize_pid}" >/dev/null 2>&1 || true
  wait "${resize_pid}" >/dev/null 2>&1 || true
fi
if [[ -n "${compositor_raise_pid}" ]]; then
  kill "${compositor_raise_pid}" >/dev/null 2>&1 || true
  wait "${compositor_raise_pid}" >/dev/null 2>&1 || true
fi
if [[ -n "${compositor_pid}" ]]; then
  kill "${compositor_pid}" >/dev/null 2>&1 || true
  wait "${compositor_pid}" >/dev/null 2>&1 || true
fi
exit "${driver_status}"
