#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <ddraw.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

typedef HRESULT (WINAPI *PFN_DirectDrawCreate)(GUID *, LPDIRECTDRAW *, IUnknown *);
typedef HRESULT (WINAPI *PFN_DirectDrawCreateEx)(GUID *, LPVOID *, REFIID, IUnknown *);
typedef HRESULT (WINAPI *PFN_DirectDrawEnumerateA)(LPDDENUMCALLBACKA, LPVOID);
typedef HRESULT (WINAPI *PFN_DirectDrawEnumerateExA)(LPDDENUMCALLBACKEXA, LPVOID, DWORD);
typedef HRESULT (WINAPI *PFN_DirectDrawSurface4Blt)(
    LPDIRECTDRAWSURFACE4,
    LPRECT,
    LPDIRECTDRAWSURFACE4,
    LPRECT,
    DWORD,
    LPDDBLTFX
);
typedef HRESULT (WINAPI *PFN_DirectDrawSurface4QueryInterface)(
    LPDIRECTDRAWSURFACE4,
    REFIID,
    LPVOID *
);
typedef HRESULT (WINAPI *PFN_DirectDrawSurface4Flip)(
    LPDIRECTDRAWSURFACE4,
    LPDIRECTDRAWSURFACE4,
    DWORD
);
typedef HRESULT (WINAPI *PFN_DirectDrawSurface4Lock)(
    LPDIRECTDRAWSURFACE4,
    LPRECT,
    LPDDSURFACEDESC2,
    DWORD,
    HANDLE
);
typedef HRESULT (WINAPI *PFN_DirectDrawSurface4Unlock)(
    LPDIRECTDRAWSURFACE4,
    LPRECT
);
typedef HRESULT (WINAPI *PFN_DirectDrawClipperSetHWnd)(
    LPDIRECTDRAWCLIPPER,
    DWORD,
    HWND
);

typedef struct TraceDirectDraw {
    IDirectDraw iface;
    LPDIRECTDRAW real;
    LONG refs;
} TraceDirectDraw;

typedef struct TraceDirectDraw4 {
    IDirectDraw4 iface;
    LPDIRECTDRAW4 real;
    LONG refs;
} TraceDirectDraw4;

typedef struct EnumModesContext {
    LPDDENUMMODESCALLBACK callback;
    LPVOID context;
    DWORD seen;
    DWORD passed;
    DWORD filtered;
    const char *source;
} EnumModesContext;

typedef struct EnumModes2Context {
    LPDDENUMMODESCALLBACK2 callback;
    LPVOID context;
    DWORD seen;
    DWORD passed;
    DWORD filtered;
    const char *source;
} EnumModes2Context;

static const GUID PM99_IID_IDirectDraw4 = {
    0x9c59509a,
    0x39bd,
    0x11d1,
    {0x8c, 0x4a, 0x00, 0xc0, 0x4f, 0xd9, 0x30, 0xc5}
};

static HMODULE real_ddraw_module;
static PFN_DirectDrawCreate real_DirectDrawCreate;
static PFN_DirectDrawCreateEx real_DirectDrawCreateEx;
static PFN_DirectDrawEnumerateA real_DirectDrawEnumerateA;
static PFN_DirectDrawEnumerateExA real_DirectDrawEnumerateExA;
static PFN_DirectDrawSurface4Blt real_DirectDrawSurface4_Blt;
static PFN_DirectDrawSurface4QueryInterface real_DirectDrawSurface4_QueryInterface;
static PFN_DirectDrawSurface4Flip real_DirectDrawSurface4_Flip;
static PFN_DirectDrawSurface4Lock real_DirectDrawSurface4_Lock;
static PFN_DirectDrawSurface4Unlock real_DirectDrawSurface4_Unlock;
static PFN_DirectDrawClipperSetHWnd real_DirectDrawClipper_SetHWnd;
static LPDIRECTDRAWSURFACE4 primary_surface4;
static DWORD primary_surface4_width;
static DWORD primary_surface4_height;
static DWORD primary_presentation_width;
static DWORD primary_presentation_height;
static DWORD primary_presentation_x;
static DWORD primary_presentation_y;
static HWND primary_game_window;
static HWND primary_presentation_overlay;
static HWND primary_clipper_presentation_window;
static LONG primary_surface4_blt_hook_installed;
static LPVOID primary_locked_pixels;
static LONG primary_locked_pitch;
static DWORD primary_locked_width;
static DWORD primary_locked_height;
static DWORD primary_locked_rgbbits;
static LONG primary_surface4_locked;
static LONG primary_frame_source_locked;
static LONG primary_unlock_pending;
static RECT primary_pending_unlock_rect;
static int primary_pending_unlock_rect_present;
static WORD *primary_upscale_source;
static LONG primary_gdi_presentation_logged;
static DWORD primary_frame_last_written_tick;
static LONG directdraw_clipper_hook_installed;

static const char primary_presentation_overlay_class_name[] = "PM99DirectDrawPresentationOverlay";

static HRESULT WINAPI trace_surface4_Blt(
    LPDIRECTDRAWSURFACE4 destination,
    LPRECT destination_rect,
    LPDIRECTDRAWSURFACE4 source,
    LPRECT source_rect,
    DWORD flags,
    LPDDBLTFX effects
);
static HRESULT WINAPI trace_surface4_QueryInterface(
    LPDIRECTDRAWSURFACE4 surface,
    REFIID riid,
    LPVOID *out
);
static HRESULT WINAPI trace_surface4_Flip(
    LPDIRECTDRAWSURFACE4 surface,
    LPDIRECTDRAWSURFACE4 target_override,
    DWORD flags
);
static HRESULT WINAPI trace_surface4_Lock(
    LPDIRECTDRAWSURFACE4 surface,
    LPRECT rect,
    LPDDSURFACEDESC2 desc,
    DWORD flags,
    HANDLE event
);
static HRESULT WINAPI trace_surface4_Unlock(
    LPDIRECTDRAWSURFACE4 surface,
    LPRECT rect
);
static HRESULT WINAPI trace_clipper_SetHWnd(
    LPDIRECTDRAWCLIPPER clipper,
    DWORD flags,
    HWND hwnd
);
static void guid_to_text(const GUID *guid, char *out, size_t out_size);

typedef struct PrimaryPresentationInputSearch {
    HWND window;
    LONG area;
} PrimaryPresentationInputSearch;

static BOOL CALLBACK find_primary_presentation_input_window(HWND hwnd, LPARAM context_value)
{
    PrimaryPresentationInputSearch *context = (PrimaryPresentationInputSearch *)context_value;
    RECT rect;
    LONG width;
    LONG height;
    LONG area;

    if (!context || !IsWindowVisible(hwnd) || !GetWindowRect(hwnd, &rect)) {
        return TRUE;
    }
    width = rect.right - rect.left;
    height = rect.bottom - rect.top;
    if (width <= 0 || height <= 0) {
        return TRUE;
    }
    area = width * height;
    if (area > context->area) {
        context->area = area;
        context->window = hwnd;
    }
    return TRUE;
}

static HWND primary_presentation_input_window(void)
{
    PrimaryPresentationInputSearch context;

    if (!primary_game_window || !IsWindow(primary_game_window)) {
        return NULL;
    }
    ZeroMemory(&context, sizeof(context));
    EnumChildWindows(
        primary_game_window,
        find_primary_presentation_input_window,
        (LPARAM)&context
    );
    return context.window ? context.window : primary_game_window;
}

static LPARAM primary_presentation_overlay_input_lparam(LPARAM input)
{
    int x = (int)(short)LOWORD(input);
    int y = (int)(short)HIWORD(input);

    /* Existing PM99 automation injects logical 640x480 coordinates. */
    if (x >= 0 && x < 640 && y >= 0 && y < 480) {
        return input;
    }
    if (primary_presentation_width) {
        x = ((x - (int)primary_presentation_x) * 640) / (int)primary_presentation_width;
    }
    if (primary_presentation_height) {
        y = ((y - (int)primary_presentation_y) * 480) / (int)primary_presentation_height;
    }
    if (x < 0) {
        x = 0;
    } else if (x > 639) {
        x = 639;
    }
    if (y < 0) {
        y = 0;
    } else if (y > 479) {
        y = 479;
    }
    return MAKELPARAM((WORD)x, (WORD)y);
}

static LRESULT CALLBACK primary_presentation_overlay_proc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam)
{
    (void)hwnd;
    switch (message) {
        case WM_MOUSEMOVE:
        case WM_LBUTTONDOWN:
        case WM_LBUTTONUP:
        case WM_LBUTTONDBLCLK:
        case WM_RBUTTONDOWN:
        case WM_RBUTTONUP:
        case WM_RBUTTONDBLCLK:
        case WM_MBUTTONDOWN:
        case WM_MBUTTONUP:
        case WM_MBUTTONDBLCLK:
        {
            HWND input_window = primary_presentation_input_window();
            if (input_window) {
                SendMessageA(
                    input_window,
                    message,
                    wparam,
                    primary_presentation_overlay_input_lparam(lparam)
                );
            }
            return 0;
        }
        case WM_MOUSEACTIVATE:
            return MA_NOACTIVATE;
        default:
            break;
    }
    if (message == WM_NCHITTEST) {
        return HTCLIENT;
    }
    if (message == WM_ERASEBKGND) {
        return 1;
    }
    return DefWindowProcA(hwnd, message, wparam, lparam);
}

static void trace_log(const char *fmt, ...)
{
    char path[MAX_PATH * 2];
    const char *env_path = getenv("PM99_DDRAW_TRACE_LOG");
    FILE *fh;
    va_list ap;

    if (env_path && env_path[0]) {
        lstrcpynA(path, env_path, sizeof(path));
    } else {
        lstrcpynA(path, "pm99-ddraw.log", sizeof(path));
    }

    fh = fopen(path, "a");
    if (!fh) {
        return;
    }

    fprintf(fh, "[%lu][tid=%lu] ", GetTickCount(), GetCurrentThreadId());
    va_start(ap, fmt);
    vfprintf(fh, fmt, ap);
    va_end(ap);
    fputc('\n', fh);
    fclose(fh);
}

static const char *hr_state(HRESULT hr)
{
    return SUCCEEDED(hr) ? "ok" : "fail";
}

static int env_flag_enabled(const char *name)
{
    const char *value = getenv(name);
    if (!value || !value[0]) {
        return 0;
    }
    return lstrcmpiA(value, "1") == 0
        || lstrcmpiA(value, "true") == 0
        || lstrcmpiA(value, "yes") == 0
        || lstrcmpiA(value, "on") == 0;
}

static int enum_mode_filter_enabled(void)
{
    return env_flag_enabled("PM99_DDRAW_FILTER_ENUM_MODES_640");
}

static int enum_mode_injection_enabled(void)
{
    return env_flag_enabled("PM99_DDRAW_INJECT_ENUM_MODE_640");
}

static int force_set_display_mode_ok_enabled(void)
{
    return env_flag_enabled("PM99_DDRAW_FORCE_SET_DISPLAY_MODE_OK");
}

static int managed_texture_fallback_enabled(void)
{
    return env_flag_enabled("PM99_DDRAW_FALLBACK_MANAGED_TEXTURES");
}

static int upscale_primary_enabled(void)
{
    return env_flag_enabled("PM99_DDRAW_UPSCALE_PRIMARY");
}

static int disable_clipper_binding_enabled(void)
{
    return env_flag_enabled("PM99_DDRAW_DISABLE_CLIPPER_BINDING");
}

static int root_presentation_enabled(void)
{
    return env_flag_enabled("PM99_DDRAW_ROOT_PRESENTATION");
}

static int click_through_overlay_enabled(void)
{
    return env_flag_enabled("PM99_DDRAW_CLICK_THROUGH_OVERLAY");
}

static int redirect_clipper_enabled(void)
{
    return env_flag_enabled("PM99_DDRAW_REDIRECT_CLIPPER");
}

static int keep_native_window_enabled(void)
{
    return env_flag_enabled("PM99_DDRAW_KEEP_NATIVE_WINDOW");
}

static HWND ensure_primary_presentation_overlay(void)
{
    WNDCLASSA window_class;
    HINSTANCE instance;

    if (!root_presentation_enabled() || !click_through_overlay_enabled()) {
        return NULL;
    }
    if (primary_presentation_overlay && IsWindow(primary_presentation_overlay)) {
        SetWindowPos(
            primary_presentation_overlay,
            HWND_TOPMOST,
            0,
            0,
            (int)primary_surface4_width,
            (int)primary_surface4_height,
            SWP_NOACTIVATE | SWP_SHOWWINDOW
        );
        return primary_presentation_overlay;
    }

    instance = GetModuleHandleA(NULL);
    ZeroMemory(&window_class, sizeof(window_class));
    window_class.lpfnWndProc = primary_presentation_overlay_proc;
    window_class.hInstance = instance;
    window_class.hCursor = LoadCursor(NULL, IDC_ARROW);
    window_class.lpszClassName = primary_presentation_overlay_class_name;
    if (!RegisterClassA(&window_class) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
        trace_log("IDirectDrawSurface4 overlay class registration failed last_error=0x%08lX", GetLastError());
        return NULL;
    }

    primary_presentation_overlay = CreateWindowExA(
        WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
        primary_presentation_overlay_class_name,
        "",
        WS_POPUP,
        0,
        0,
        (int)primary_surface4_width,
        (int)primary_surface4_height,
        NULL,
        NULL,
        instance,
        NULL
    );
    if (!primary_presentation_overlay) {
        trace_log("IDirectDrawSurface4 overlay creation failed last_error=0x%08lX", GetLastError());
        return NULL;
    }
    SetWindowPos(
        primary_presentation_overlay,
        HWND_TOPMOST,
        0,
        0,
        (int)primary_surface4_width,
        (int)primary_surface4_height,
        SWP_NOACTIVATE | SWP_SHOWWINDOW
    );
    trace_log(
        "IDirectDrawSurface4 overlay created hwnd=%p host=%lux%lu",
        primary_presentation_overlay,
        primary_surface4_width,
        primary_surface4_height
    );
    return primary_presentation_overlay;
}

static HWND ensure_primary_clipper_presentation_window(void)
{
    WNDCLASSA window_class;
    HINSTANCE instance;

    if (!redirect_clipper_enabled() || !primary_surface4_width || !primary_surface4_height) {
        return NULL;
    }
    if (primary_clipper_presentation_window && IsWindow(primary_clipper_presentation_window)) {
        SetWindowPos(
            primary_clipper_presentation_window,
            HWND_TOPMOST,
            (int)primary_presentation_x,
            (int)primary_presentation_y,
            (int)primary_presentation_width,
            (int)primary_presentation_height,
            SWP_NOACTIVATE | SWP_SHOWWINDOW
        );
        return primary_clipper_presentation_window;
    }

    instance = GetModuleHandleA(NULL);
    ZeroMemory(&window_class, sizeof(window_class));
    window_class.lpfnWndProc = primary_presentation_overlay_proc;
    window_class.hInstance = instance;
    window_class.hCursor = LoadCursor(NULL, IDC_ARROW);
    window_class.lpszClassName = primary_presentation_overlay_class_name;
    if (!RegisterClassA(&window_class) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
        trace_log("IDirectDrawSurface4 clipper presentation class registration failed last_error=0x%08lX", GetLastError());
        return NULL;
    }

    primary_clipper_presentation_window = CreateWindowExA(
        WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
        primary_presentation_overlay_class_name,
        "",
        WS_POPUP,
        (int)primary_presentation_x,
        (int)primary_presentation_y,
        (int)primary_presentation_width,
        (int)primary_presentation_height,
        NULL,
        NULL,
        instance,
        NULL
    );
    if (!primary_clipper_presentation_window) {
        trace_log("IDirectDrawSurface4 clipper presentation creation failed last_error=0x%08lX", GetLastError());
        return NULL;
    }
    SetWindowPos(
        primary_clipper_presentation_window,
        HWND_TOPMOST,
        (int)primary_presentation_x,
        (int)primary_presentation_y,
        (int)primary_presentation_width,
        (int)primary_presentation_height,
        SWP_NOACTIVATE | SWP_SHOWWINDOW
    );
    trace_log(
        "IDirectDrawSurface4 clipper presentation created hwnd=%p target=%lux%lu offset=%lu,%lu",
        primary_clipper_presentation_window,
        primary_presentation_width,
        primary_presentation_height,
        primary_presentation_x,
        primary_presentation_y
    );
    return primary_clipper_presentation_window;
}

static void install_directdraw_clipper_hook(LPDIRECTDRAWCLIPPER clipper)
{
    IDirectDrawClipperVtbl *vtbl;
    DWORD old_protect;

    if (!clipper) {
        return;
    }
    if (InterlockedCompareExchange(&directdraw_clipper_hook_installed, 1, 0) != 0) {
        return;
    }

    vtbl = (IDirectDrawClipperVtbl *)clipper->lpVtbl;
    if (!vtbl || !vtbl->SetHWnd) {
        trace_log("IDirectDrawClipper unable to install SetHWnd hook: missing vtable");
        InterlockedExchange(&directdraw_clipper_hook_installed, 0);
        return;
    }
    if (!VirtualProtect(vtbl, sizeof(*vtbl), PAGE_EXECUTE_READWRITE, &old_protect)) {
        trace_log("IDirectDrawClipper unable to make vtable writable last_error=0x%08lX", GetLastError());
        InterlockedExchange(&directdraw_clipper_hook_installed, 0);
        return;
    }
    real_DirectDrawClipper_SetHWnd = vtbl->SetHWnd;
    vtbl->SetHWnd = trace_clipper_SetHWnd;
    VirtualProtect(vtbl, sizeof(*vtbl), old_protect, &old_protect);
    FlushInstructionCache(GetCurrentProcess(), vtbl, sizeof(*vtbl));
    trace_log(
        "IDirectDrawClipper installed SetHWnd hook vtable=%p real_sethwnd=%p",
        vtbl,
        real_DirectDrawClipper_SetHWnd
    );
}

static HRESULT WINAPI trace_clipper_SetHWnd(
    LPDIRECTDRAWCLIPPER clipper,
    DWORD flags,
    HWND hwnd
)
{
    HRESULT hr;
    HWND presentation_window;

    if (!real_DirectDrawClipper_SetHWnd) {
        return DDERR_GENERIC;
    }
    if (disable_clipper_binding_enabled()) {
        trace_log(
            "IDirectDrawClipper::SetHWnd suppressed clipper=%p flags=0x%08lX hwnd=%p",
            clipper,
            flags,
            hwnd
        );
        return DD_OK;
    }
    presentation_window = ensure_primary_clipper_presentation_window();
    if (presentation_window) {
        hr = real_DirectDrawClipper_SetHWnd(clipper, flags, presentation_window);
        trace_log(
            "IDirectDrawClipper::SetHWnd redirected clipper=%p flags=0x%08lX game_hwnd=%p presentation_hwnd=%p hr=0x%08lX %s",
            clipper,
            flags,
            hwnd,
            presentation_window,
            (unsigned long)hr,
            hr_state(hr)
        );
        return hr;
    }
    hr = real_DirectDrawClipper_SetHWnd(clipper, flags, hwnd);
    trace_log(
        "IDirectDrawClipper::SetHWnd clipper=%p flags=0x%08lX hwnd=%p hr=0x%08lX %s",
        clipper,
        flags,
        hwnd,
        (unsigned long)hr,
        hr_state(hr)
    );
    return hr;
}

static int rect_is_pm99_logical_viewport(const RECT *rect)
{
    if (!rect) {
        return 1;
    }
    return rect->left >= 0
        && rect->top >= 0
        && rect->right > rect->left
        && rect->bottom > rect->top
        && rect->right <= 640
        && rect->bottom <= 480;
}

static void scale_pm99_logical_rect_to_primary(const RECT *input, RECT *output)
{
    RECT logical_rect;
    DWORD content_width;
    DWORD content_height;
    LONG offset_x;
    LONG offset_y;

    if (input) {
        logical_rect = *input;
    } else {
        logical_rect.left = 0;
        logical_rect.top = 0;
        logical_rect.right = 640;
        logical_rect.bottom = 480;
    }

    content_width = primary_presentation_width ? primary_presentation_width : primary_surface4_width;
    content_height = primary_presentation_height ? primary_presentation_height : primary_surface4_height;
    offset_x = 0;
    offset_y = 0;
    output->left = offset_x + MulDiv(logical_rect.left, (int)content_width, 640);
    output->top = offset_y + MulDiv(logical_rect.top, (int)content_height, 480);
    output->right = offset_x + MulDiv(logical_rect.right, (int)content_width, 640);
    output->bottom = offset_y + MulDiv(logical_rect.bottom, (int)content_height, 480);
}

static void configure_upscale_presentation(void)
{
    DWORD host_offset_x;
    DWORD host_offset_y;
    RECT client_rect;

    primary_presentation_width = primary_surface4_width;
    primary_presentation_height = (primary_surface4_width * 3) / 4;
    if (primary_presentation_height > primary_surface4_height) {
        primary_presentation_height = primary_surface4_height;
        primary_presentation_width = (primary_surface4_height * 4) / 3;
    }
    if (!upscale_primary_enabled() || !primary_game_window) {
        return;
    }

    host_offset_x = (primary_surface4_width - primary_presentation_width) / 2;
    host_offset_y = (primary_surface4_height - primary_presentation_height) / 2;
    primary_presentation_x = host_offset_x;
    primary_presentation_y = host_offset_y;
    if (root_presentation_enabled()) {
        if (click_through_overlay_enabled()) {
            if (!ensure_primary_presentation_overlay()) {
                trace_log("IDirectDrawSurface4 root presentation overlay unavailable");
                return;
            }
            trace_log(
                "IDirectDrawSurface4 root presentation overlay active target=%lux%lu offset=%lu,%lu",
                primary_presentation_width,
                primary_presentation_height,
                primary_presentation_x,
                primary_presentation_y
            );
            return;
        }
        if (!SetWindowPos(
                primary_game_window,
                NULL,
                -(int)primary_surface4_width,
                0,
                640,
                480,
                SWP_NOACTIVATE | SWP_NOOWNERZORDER | SWP_NOZORDER
            )) {
            trace_log("IDirectDrawSurface4 root presentation move failed hwnd=%p last_error=0x%08lX", primary_game_window, GetLastError());
            return;
        }
        trace_log(
            "IDirectDrawSurface4 root presentation moved legacy hwnd=%p offscreen target=%lux%lu offset=%lu,%lu",
            primary_game_window,
            primary_presentation_width,
            primary_presentation_height,
            primary_presentation_x,
            primary_presentation_y
        );
        return;
    }
    if (redirect_clipper_enabled()) {
        trace_log(
            "IDirectDrawSurface4 clipper presentation prepared target=%lux%lu offset=%lu,%lu",
            primary_presentation_width,
            primary_presentation_height,
            primary_presentation_x,
            primary_presentation_y
        );
        return;
    }
    if (keep_native_window_enabled()) {
        trace_log("IDirectDrawSurface4 retained native input window for external presentation");
        return;
    }
    if (!SetWindowPos(
            primary_game_window,
            NULL,
            (int)host_offset_x,
            (int)host_offset_y,
            (int)primary_presentation_width,
            (int)primary_presentation_height,
            SWP_NOACTIVATE | SWP_NOOWNERZORDER | SWP_NOZORDER
        )) {
        trace_log("IDirectDrawSurface4 primary resize failed hwnd=%p last_error=0x%08lX", primary_game_window, GetLastError());
        return;
    }
    ZeroMemory(&client_rect, sizeof(client_rect));
    GetClientRect(primary_game_window, &client_rect);
    trace_log(
        "IDirectDrawSurface4 primary resize hwnd=%p host_offset=%lu,%lu requested=%lux%lu client=%ldx%ld",
        primary_game_window,
        host_offset_x,
        host_offset_y,
        primary_presentation_width,
        primary_presentation_height,
        client_rect.right - client_rect.left,
        client_rect.bottom - client_rect.top
    );
}

static void upscale_locked_primary_640x480(void)
{
    BYTE *pixels = (BYTE *)primary_locked_pixels;
    DWORD content_width;
    DWORD content_height;
    DWORD offset_x;
    DWORD offset_y;
    DWORD target_y;
    DWORD target_x;

    if (
        !pixels
        || primary_locked_width != primary_surface4_width
        || primary_locked_height != primary_surface4_height
        || primary_locked_rgbbits != 16
        || primary_locked_pitch < 1280
    ) {
        trace_log(
            "IDirectDrawSurface4 primary upscale skipped pixels=%p locked=%lux%lu pitch=%ld rgbbits=%lu",
            pixels,
            primary_locked_width,
            primary_locked_height,
            primary_locked_pitch,
            primary_locked_rgbbits
        );
        return;
    }

    if (!primary_upscale_source) {
        primary_upscale_source = (WORD *)HeapAlloc(GetProcessHeap(), 0, 640 * 480 * sizeof(WORD));
        if (!primary_upscale_source) {
            trace_log("IDirectDrawSurface4 primary upscale skipped: scratch allocation failed");
            return;
        }
    }

    for (target_y = 0; target_y < 480; ++target_y) {
        CopyMemory(
            primary_upscale_source + (target_y * 640),
            pixels + ((size_t)target_y * (size_t)primary_locked_pitch),
            640 * sizeof(WORD)
        );
    }

    content_width = primary_presentation_width ? primary_presentation_width : primary_surface4_width;
    content_height = primary_presentation_height ? primary_presentation_height : primary_surface4_height;
    offset_x = 0;
    offset_y = 0;

    ZeroMemory(pixels, (size_t)primary_locked_pitch * (size_t)primary_locked_height);
    for (target_y = 0; target_y < content_height; ++target_y) {
        WORD *destination = (WORD *)(pixels + ((size_t)(offset_y + target_y) * (size_t)primary_locked_pitch));
        WORD *source = primary_upscale_source + ((target_y * 480 / content_height) * 640);
        for (target_x = 0; target_x < content_width; ++target_x) {
            destination[offset_x + target_x] = source[target_x * 640 / content_width];
        }
    }
    trace_log(
        "IDirectDrawSurface4 primary upscale applied source=640x480 target=%lux%lu offset=%lu,%lu",
        content_width,
        content_height,
        offset_x,
        offset_y
    );
}

static void publish_primary_upscale_frame(void)
{
    const char *path = getenv("PM99_DDRAW_FRAME_PATH");
    DWORD now;
    FILE *frame;
    char temporary_path[MAX_PATH];
    int written;

    if (!path || !path[0] || !primary_upscale_source) {
        return;
    }
    now = GetTickCount();
    if ((DWORD)(now - primary_frame_last_written_tick) < 33) {
        return;
    }
    written = _snprintf(temporary_path, sizeof(temporary_path), "%s.tmp", path);
    if (written < 0 || (size_t)written >= sizeof(temporary_path)) {
        return;
    }
    frame = fopen(temporary_path, "wb");
    if (!frame) {
        return;
    }
    if (fwrite(primary_upscale_source, sizeof(WORD), 640 * 480, frame) == 640 * 480) {
        if (fclose(frame) == 0 && MoveFileExA(
                temporary_path,
                path,
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH
            )) {
            primary_frame_last_written_tick = now;
            return;
        }
    } else {
        fclose(frame);
    }
    DeleteFileA(temporary_path);
}

static void draw_upscaled_primary_with_gdi(void)
{
    struct {
        BITMAPINFOHEADER header;
        DWORD masks[3];
    } bitmap_info;
    HDC dc;
    HWND presentation_window;
    RECT overlay_rect;
    int lines;

    if (!primary_game_window || !primary_upscale_source || !primary_presentation_width || !primary_presentation_height) {
        return;
    }
    ZeroMemory(&bitmap_info, sizeof(bitmap_info));
    bitmap_info.header.biSize = sizeof(bitmap_info.header);
    bitmap_info.header.biWidth = 640;
    bitmap_info.header.biHeight = -480;
    bitmap_info.header.biPlanes = 1;
    bitmap_info.header.biBitCount = 16;
    bitmap_info.header.biCompression = BI_BITFIELDS;
    bitmap_info.masks[0] = 0x0000F800;
    bitmap_info.masks[1] = 0x000007E0;
    bitmap_info.masks[2] = 0x0000001F;

    presentation_window = root_presentation_enabled() && click_through_overlay_enabled()
        ? ensure_primary_presentation_overlay()
        : (root_presentation_enabled() ? NULL : primary_game_window);
    if (!presentation_window && !root_presentation_enabled()) {
        trace_log("IDirectDrawSurface4 GDI presentation skipped: target window unavailable");
        return;
    }
    dc = GetDC(presentation_window);
    if (!dc) {
        trace_log("IDirectDrawSurface4 GDI presentation skipped: GetDC failed last_error=0x%08lX", GetLastError());
        return;
    }
    if (root_presentation_enabled() && click_through_overlay_enabled()) {
        SetRect(&overlay_rect, 0, 0, (int)primary_surface4_width, (int)primary_surface4_height);
        FillRect(dc, &overlay_rect, (HBRUSH)GetStockObject(BLACK_BRUSH));
    }
    SetStretchBltMode(dc, COLORONCOLOR);
    lines = StretchDIBits(
        dc,
        root_presentation_enabled() ? (int)primary_presentation_x : 0,
        root_presentation_enabled() ? (int)primary_presentation_y : 0,
        (int)primary_presentation_width,
        (int)primary_presentation_height,
        0,
        0,
        640,
        480,
        primary_upscale_source,
        (const BITMAPINFO *)&bitmap_info,
        DIB_RGB_COLORS,
        SRCCOPY
    );
    ReleaseDC(presentation_window, dc);
    if (lines == (int)GDI_ERROR) {
        trace_log("IDirectDrawSurface4 GDI presentation failed last_error=0x%08lX", GetLastError());
    } else if (InterlockedCompareExchange(&primary_gdi_presentation_logged, 1, 0) == 0) {
        trace_log(
            "IDirectDrawSurface4 GDI presentation active root=%d target=%lux%lu offset=%lu,%lu lines=%d",
            root_presentation_enabled(),
            primary_presentation_width,
            primary_presentation_height,
            primary_presentation_x,
            primary_presentation_y,
            lines
        );
    }
}

static HRESULT finish_delayed_primary_unlock(void)
{
    LPRECT pending_rect = NULL;
    HRESULT hr;

    if (InterlockedCompareExchange(&primary_unlock_pending, 0, 1) != 1) {
        return DD_OK;
    }
    if (primary_pending_unlock_rect_present) {
        pending_rect = &primary_pending_unlock_rect;
    }
    upscale_locked_primary_640x480();
    publish_primary_upscale_frame();
    hr = real_DirectDrawSurface4_Unlock(primary_surface4, pending_rect);
    if (SUCCEEDED(hr)) {
        draw_upscaled_primary_with_gdi();
    }
    InterlockedExchange(&primary_surface4_locked, 0);
    InterlockedExchange(&primary_frame_source_locked, 0);
    primary_locked_pixels = NULL;
    trace_log(
        "IDirectDrawSurface4 delayed primary unlock rect=%p hr=0x%08lX %s",
        pending_rect,
        (unsigned long)hr,
        hr_state(hr)
    );
    return hr;
}

static int surface4_matches_primary_extent(LPDIRECTDRAWSURFACE4 surface)
{
    if (!surface || !primary_surface4_width || !primary_surface4_height) {
        return 0;
    }
    return surface == primary_surface4;
}

static void install_primary_surface4_blt_hook(LPDIRECTDRAWSURFACE4 surface)
{
    IDirectDrawSurface4Vtbl *vtbl;
    DDSURFACEDESC2 surface_desc;
    DWORD old_protect;

    if (!surface) {
        return;
    }

    primary_surface4 = surface;
    ZeroMemory(&surface_desc, sizeof(surface_desc));
    surface_desc.dwSize = sizeof(surface_desc);
    if (SUCCEEDED(surface->lpVtbl->GetSurfaceDesc(surface, &surface_desc))) {
        primary_surface4_width = surface_desc.dwWidth;
        primary_surface4_height = surface_desc.dwHeight;
    }
    if (!primary_surface4_width || !primary_surface4_height) {
        primary_surface4_width = (DWORD)GetSystemMetrics(SM_CXSCREEN);
        primary_surface4_height = (DWORD)GetSystemMetrics(SM_CYSCREEN);
    }
    trace_log(
        "IDirectDrawSurface4 primary surface=%p width=%lu height=%lu upscale_primary=%d",
        surface,
        primary_surface4_width,
        primary_surface4_height,
        upscale_primary_enabled()
    );
    configure_upscale_presentation();

    if (InterlockedCompareExchange(&primary_surface4_blt_hook_installed, 1, 0) != 0) {
        return;
    }

    vtbl = (IDirectDrawSurface4Vtbl *)surface->lpVtbl;
    if (!vtbl || !vtbl->Blt) {
        trace_log("IDirectDrawSurface4 unable to install Blt hook: missing vtable");
        InterlockedExchange(&primary_surface4_blt_hook_installed, 0);
        return;
    }
    if (!VirtualProtect(vtbl, sizeof(*vtbl), PAGE_EXECUTE_READWRITE, &old_protect)) {
        trace_log("IDirectDrawSurface4 unable to make vtable writable last_error=0x%08lX", GetLastError());
        InterlockedExchange(&primary_surface4_blt_hook_installed, 0);
        return;
    }
    real_DirectDrawSurface4_Blt = vtbl->Blt;
    real_DirectDrawSurface4_QueryInterface = vtbl->QueryInterface;
    real_DirectDrawSurface4_Flip = vtbl->Flip;
    real_DirectDrawSurface4_Lock = vtbl->Lock;
    real_DirectDrawSurface4_Unlock = vtbl->Unlock;
    vtbl->Blt = trace_surface4_Blt;
    vtbl->QueryInterface = trace_surface4_QueryInterface;
    vtbl->Flip = trace_surface4_Flip;
    vtbl->Lock = trace_surface4_Lock;
    vtbl->Unlock = trace_surface4_Unlock;
    VirtualProtect(vtbl, sizeof(*vtbl), old_protect, &old_protect);
    FlushInstructionCache(GetCurrentProcess(), vtbl, sizeof(*vtbl));
    trace_log(
        "IDirectDrawSurface4 installed Blt/Flip/Lock/Unlock/QueryInterface hooks vtable=%p real_blt=%p real_flip=%p real_lock=%p real_unlock=%p real_query=%p",
        vtbl,
        real_DirectDrawSurface4_Blt,
        real_DirectDrawSurface4_Flip,
        real_DirectDrawSurface4_Lock,
        real_DirectDrawSurface4_Unlock,
        real_DirectDrawSurface4_QueryInterface
    );
}

static HRESULT WINAPI trace_surface4_QueryInterface(
    LPDIRECTDRAWSURFACE4 surface,
    REFIID riid,
    LPVOID *out
)
{
    char riid_text[64];
    HRESULT hr;

    if (!real_DirectDrawSurface4_QueryInterface) {
        return E_NOINTERFACE;
    }
    guid_to_text(riid, riid_text, sizeof(riid_text));
    hr = real_DirectDrawSurface4_QueryInterface(surface, riid, out);
    trace_log(
        "IDirectDrawSurface4::QueryInterface surface=%p riid=%s hr=0x%08lX %s out=%p",
        surface,
        riid_text,
        (unsigned long)hr,
        hr_state(hr),
        out ? *out : NULL
    );
    return hr;
}

static HRESULT WINAPI trace_surface4_Flip(
    LPDIRECTDRAWSURFACE4 surface,
    LPDIRECTDRAWSURFACE4 target_override,
    DWORD flags
)
{
    HRESULT hr;

    if (!real_DirectDrawSurface4_Flip) {
        return DDERR_GENERIC;
    }
    hr = real_DirectDrawSurface4_Flip(surface, target_override, flags);
    trace_log(
        "IDirectDrawSurface4::Flip surface=%p target_override=%p flags=0x%08lX hr=0x%08lX %s",
        surface,
        target_override,
        flags,
        (unsigned long)hr,
        hr_state(hr)
    );
    return hr;
}

static HRESULT WINAPI trace_surface4_Lock(
    LPDIRECTDRAWSURFACE4 surface,
    LPRECT rect,
    LPDDSURFACEDESC2 desc,
    DWORD flags,
    HANDLE event
)
{
    HRESULT hr;

    if (!real_DirectDrawSurface4_Lock) {
        return DDERR_GENERIC;
    }
    if (
        surface == primary_surface4
        && InterlockedCompareExchange(&primary_unlock_pending, 0, 0) == 1
    ) {
        HRESULT delayed_hr = finish_delayed_primary_unlock();
        trace_log(
            "IDirectDrawSurface4::Lock completed pending primary unlock before relock hr=0x%08lX %s",
            (unsigned long)delayed_hr,
            hr_state(delayed_hr)
        );
        if (FAILED(delayed_hr)) {
            return delayed_hr;
        }
    }
    hr = real_DirectDrawSurface4_Lock(surface, rect, desc, flags, event);
    if (hr == DDERR_SURFACELOST && upscale_primary_enabled()) {
        HRESULT restore_hr = surface->lpVtbl->Restore(surface);
        trace_log(
            "IDirectDrawSurface4::Lock surface-lost recovery surface=%p primary=%p restore hr=0x%08lX %s",
            surface,
            primary_surface4,
            (unsigned long)restore_hr,
            hr_state(restore_hr)
        );
        if (SUCCEEDED(restore_hr)) {
            hr = real_DirectDrawSurface4_Lock(surface, rect, desc, flags, event);
            trace_log(
                "IDirectDrawSurface4::Lock surface-lost recovery retry hr=0x%08lX %s",
                (unsigned long)hr,
                hr_state(hr)
            );
        }
    }
    if (
        SUCCEEDED(hr)
        && surface == primary_surface4
        && desc
    ) {
        primary_locked_pixels = desc->lpSurface;
        primary_locked_pitch = desc->lPitch;
        primary_locked_width = desc->dwWidth;
        primary_locked_height = desc->dwHeight;
        primary_locked_rgbbits = desc->ddpfPixelFormat.dwRGBBitCount;
        InterlockedExchange(&primary_surface4_locked, 1);
        InterlockedExchange(&primary_frame_source_locked, 0);
    } else if (
        SUCCEEDED(hr)
        && InterlockedCompareExchange(&primary_surface4_locked, 0, 0) == 1
        && desc
        && desc->dwWidth == 640
        && desc->dwHeight == 480
        && desc->ddpfPixelFormat.dwRGBBitCount == 8
    ) {
        InterlockedExchange(&primary_frame_source_locked, 1);
    }
    trace_log(
        "IDirectDrawSurface4::Lock surface=%p rect=%p flags=0x%08lX event=%p hr=0x%08lX %s width=%lu height=%lu pitch=%ld rgbbits=%lu pixels=%p",
        surface,
        rect,
        flags,
        event,
        (unsigned long)hr,
        hr_state(hr),
        SUCCEEDED(hr) && desc ? desc->dwWidth : 0,
        SUCCEEDED(hr) && desc ? desc->dwHeight : 0,
        SUCCEEDED(hr) && desc ? desc->lPitch : 0,
        SUCCEEDED(hr) && desc ? desc->ddpfPixelFormat.dwRGBBitCount : 0,
        SUCCEEDED(hr) && desc ? desc->lpSurface : NULL
    );
    return hr;
}

static HRESULT WINAPI trace_surface4_Unlock(
    LPDIRECTDRAWSURFACE4 surface,
    LPRECT rect
)
{
    HRESULT hr;

    if (!real_DirectDrawSurface4_Unlock) {
        return DDERR_GENERIC;
    }
    if (surface == primary_surface4 && InterlockedCompareExchange(&primary_surface4_locked, 0, 0) == 1) {
        if (
            upscale_primary_enabled()
            && InterlockedCompareExchange(&primary_frame_source_locked, 0, 0) == 1
        ) {
            if (rect) {
                primary_pending_unlock_rect = *rect;
                primary_pending_unlock_rect_present = 1;
            } else {
                primary_pending_unlock_rect_present = 0;
            }
            InterlockedExchange(&primary_unlock_pending, 1);
            trace_log("IDirectDrawSurface4 primary unlock delayed pending source release");
            return DD_OK;
        }
        hr = real_DirectDrawSurface4_Unlock(surface, rect);
        InterlockedExchange(&primary_surface4_locked, 0);
        InterlockedExchange(&primary_frame_source_locked, 0);
        primary_locked_pixels = NULL;
        trace_log(
            "IDirectDrawSurface4::Unlock surface=%p rect=%p hr=0x%08lX %s",
            surface,
            rect,
            (unsigned long)hr,
            hr_state(hr)
        );
        return hr;
    }

    hr = real_DirectDrawSurface4_Unlock(surface, rect);
    if (InterlockedCompareExchange(&primary_unlock_pending, 0, 0) == 1) {
        HRESULT delayed_hr = finish_delayed_primary_unlock();
        if (SUCCEEDED(hr) && FAILED(delayed_hr)) {
            hr = delayed_hr;
        }
    }
    trace_log(
        "IDirectDrawSurface4::Unlock surface=%p rect=%p hr=0x%08lX %s",
        surface,
        rect,
        (unsigned long)hr,
        hr_state(hr)
    );
    return hr;
}

static HRESULT WINAPI trace_surface4_Blt(
    LPDIRECTDRAWSURFACE4 destination,
    LPRECT destination_rect,
    LPDIRECTDRAWSURFACE4 source,
    LPRECT source_rect,
    DWORD flags,
    LPDDBLTFX effects
)
{
    RECT scaled_destination;
    LPRECT effective_destination = destination_rect;
    int host_sized_destination = surface4_matches_primary_extent(destination);
    HRESULT hr;

    if (!real_DirectDrawSurface4_Blt) {
        return DDERR_GENERIC;
    }

    if (
        host_sized_destination
        && upscale_primary_enabled()
        && primary_surface4_width >= 640
        && primary_surface4_height >= 480
        && rect_is_pm99_logical_viewport(destination_rect)
    ) {
        scale_pm99_logical_rect_to_primary(destination_rect, &scaled_destination);
        effective_destination = &scaled_destination;
        trace_log(
            "IDirectDrawSurface4::Blt host-sized upscale dst_surface=%p src=%p dst=(%ld,%ld,%ld,%ld) scaled=(%ld,%ld,%ld,%ld) flags=0x%08lX",
            destination,
            source,
            destination_rect ? destination_rect->left : 0,
            destination_rect ? destination_rect->top : 0,
            destination_rect ? destination_rect->right : 640,
            destination_rect ? destination_rect->bottom : 480,
            scaled_destination.left,
            scaled_destination.top,
            scaled_destination.right,
            scaled_destination.bottom,
            flags
        );
    } else if (host_sized_destination) {
        trace_log(
            "IDirectDrawSurface4::Blt host-sized passthrough dst_surface=%p src=%p dst=%p flags=0x%08lX",
            destination,
            source,
            destination_rect,
            flags
        );
    }

    hr = real_DirectDrawSurface4_Blt(
        destination,
        effective_destination,
        source,
        source_rect,
        flags,
        effects
    );
    if (host_sized_destination) {
        trace_log("IDirectDrawSurface4::Blt host-sized hr=0x%08lX %s", (unsigned long)hr, hr_state(hr));
    }
    return hr;
}

static int mode_desc_matches_640x480x16(LPDDSURFACEDESC desc)
{
    if (!desc) {
        return 0;
    }
    return desc->dwWidth == 640
        && desc->dwHeight == 480
        && desc->ddpfPixelFormat.dwRGBBitCount == 16;
}

static int mode_desc2_matches_640x480x16(LPDDSURFACEDESC2 desc)
{
    if (!desc) {
        return 0;
    }
    return desc->dwWidth == 640
        && desc->dwHeight == 480
        && desc->ddpfPixelFormat.dwRGBBitCount == 16;
}

static void fill_synthetic_640x480x16_desc(LPDDSURFACEDESC desc)
{
    ZeroMemory(desc, sizeof(*desc));
    desc->dwSize = sizeof(*desc);
    desc->dwFlags = DDSD_WIDTH | DDSD_HEIGHT | DDSD_PITCH | DDSD_PIXELFORMAT;
    desc->dwWidth = 640;
    desc->dwHeight = 480;
    desc->lPitch = 1280;
    desc->ddpfPixelFormat.dwSize = sizeof(DDPIXELFORMAT);
    desc->ddpfPixelFormat.dwFlags = DDPF_RGB;
    desc->ddpfPixelFormat.dwRGBBitCount = 16;
    desc->ddpfPixelFormat.dwRBitMask = 0x0000F800;
    desc->ddpfPixelFormat.dwGBitMask = 0x000007E0;
    desc->ddpfPixelFormat.dwBBitMask = 0x0000001F;
}

static void fill_synthetic_640x480x16_desc2(LPDDSURFACEDESC2 desc)
{
    ZeroMemory(desc, sizeof(*desc));
    desc->dwSize = sizeof(*desc);
    desc->dwFlags = DDSD_WIDTH | DDSD_HEIGHT | DDSD_PITCH | DDSD_PIXELFORMAT;
    desc->dwWidth = 640;
    desc->dwHeight = 480;
    desc->lPitch = 1280;
    desc->ddpfPixelFormat.dwSize = sizeof(DDPIXELFORMAT);
    desc->ddpfPixelFormat.dwFlags = DDPF_RGB;
    desc->ddpfPixelFormat.dwRGBBitCount = 16;
    desc->ddpfPixelFormat.dwRBitMask = 0x0000F800;
    desc->ddpfPixelFormat.dwGBitMask = 0x000007E0;
    desc->ddpfPixelFormat.dwBBitMask = 0x0000001F;
}

static HRESULT maybe_force_set_display_mode_ok(HRESULT real_hr, DWORD width, DWORD height, DWORD bpp, const char *source)
{
    if (
        FAILED(real_hr)
        && force_set_display_mode_ok_enabled()
        && width == 640
        && height == 480
        && bpp == 16
    ) {
        trace_log("%s force_set_display_mode_ok real_hr=0x%08lX returning DD_OK", source, (unsigned long)real_hr);
        return DD_OK;
    }
    return real_hr;
}

static HRESULT set_display_mode_with_upscale(
    LPDIRECTDRAW4 ddraw,
    DWORD width,
    DWORD height,
    DWORD bpp,
    DWORD refresh,
    DWORD flags
)
{
    DWORD host_width;
    DWORD host_height;
    HRESULT hr;

    if (
        !upscale_primary_enabled()
        || width != 640
        || height != 480
        || bpp != 16
    ) {
        return ddraw->lpVtbl->SetDisplayMode(ddraw, width, height, bpp, refresh, flags);
    }

    host_width = (DWORD)GetSystemMetrics(SM_CXSCREEN);
    host_height = (DWORD)GetSystemMetrics(SM_CYSCREEN);
    hr = ddraw->lpVtbl->SetDisplayMode(ddraw, host_width, host_height, bpp, refresh, flags);
    trace_log(
        "IDirectDraw4::SetDisplayMode upscale real_target=%lux%lux%lu requested=%lux%lux%lu hr=0x%08lX %s",
        host_width,
        host_height,
        bpp,
        width,
        height,
        bpp,
        (unsigned long)hr,
        hr_state(hr)
    );
    return hr;
}

static void normalize_display_mode_desc(LPDDSURFACEDESC desc, const char *source)
{
    if (!desc || !env_flag_enabled("PM99_DDRAW_NORMALIZE_DISPLAY_MODE")) {
        return;
    }
    trace_log(
        "%s normalize_display_mode before width=%lu height=%lu pitch=%ld rgbbits=%lu flags=0x%08lX",
        source,
        desc->dwWidth,
        desc->dwHeight,
        desc->lPitch,
        desc->ddpfPixelFormat.dwRGBBitCount,
        desc->dwFlags
    );
    desc->dwFlags |= DDSD_WIDTH | DDSD_HEIGHT | DDSD_PITCH | DDSD_PIXELFORMAT;
    desc->dwWidth = 640;
    desc->dwHeight = 480;
    desc->lPitch = 1280;
    desc->ddpfPixelFormat.dwSize = sizeof(DDPIXELFORMAT);
    desc->ddpfPixelFormat.dwFlags = DDPF_RGB;
    desc->ddpfPixelFormat.dwRGBBitCount = 16;
    desc->ddpfPixelFormat.dwRBitMask = 0x0000F800;
    desc->ddpfPixelFormat.dwGBitMask = 0x000007E0;
    desc->ddpfPixelFormat.dwBBitMask = 0x0000001F;
    trace_log(
        "%s normalize_display_mode after width=%lu height=%lu pitch=%ld rgbbits=%lu flags=0x%08lX",
        source,
        desc->dwWidth,
        desc->dwHeight,
        desc->lPitch,
        desc->ddpfPixelFormat.dwRGBBitCount,
        desc->dwFlags
    );
}

static void clamp_huge_surface_desc(LPDDSURFACEDESC desc, const char *source)
{
    if (!desc || !env_flag_enabled("PM99_DDRAW_CLAMP_HUGE_SURFACES")) {
        return;
    }
    if (desc->dwWidth <= 10000 && desc->dwHeight <= 10000) {
        return;
    }
    trace_log(
        "%s clamp_huge_surface before width=%lu height=%lu pitch=%ld flags=0x%08lX caps=0x%08lX pixelflags=0x%08lX rgbbits=%lu",
        source,
        desc->dwWidth,
        desc->dwHeight,
        desc->lPitch,
        desc->dwFlags,
        desc->ddsCaps.dwCaps,
        desc->ddpfPixelFormat.dwFlags,
        desc->ddpfPixelFormat.dwRGBBitCount
    );
    desc->dwWidth = 640;
    desc->dwHeight = 480;
    desc->lPitch = 0;
    desc->dwFlags |= DDSD_WIDTH | DDSD_HEIGHT;
    trace_log(
        "%s clamp_huge_surface after width=%lu height=%lu pitch=%ld flags=0x%08lX caps=0x%08lX pixelflags=0x%08lX rgbbits=%lu",
        source,
        desc->dwWidth,
        desc->dwHeight,
        desc->lPitch,
        desc->dwFlags,
        desc->ddsCaps.dwCaps,
        desc->ddpfPixelFormat.dwFlags,
        desc->ddpfPixelFormat.dwRGBBitCount
    );
}

static void normalize_display_mode_desc2(LPDDSURFACEDESC2 desc, const char *source)
{
    if (!desc || !env_flag_enabled("PM99_DDRAW_NORMALIZE_DISPLAY_MODE")) {
        return;
    }
    trace_log(
        "%s normalize_display_mode before width=%lu height=%lu pitch=%ld rgbbits=%lu flags=0x%08lX",
        source,
        desc->dwWidth,
        desc->dwHeight,
        desc->lPitch,
        desc->ddpfPixelFormat.dwRGBBitCount,
        desc->dwFlags
    );
    desc->dwFlags |= DDSD_WIDTH | DDSD_HEIGHT | DDSD_PITCH | DDSD_PIXELFORMAT;
    desc->dwWidth = 640;
    desc->dwHeight = 480;
    desc->lPitch = 1280;
    desc->ddpfPixelFormat.dwSize = sizeof(DDPIXELFORMAT);
    desc->ddpfPixelFormat.dwFlags = DDPF_RGB;
    desc->ddpfPixelFormat.dwRGBBitCount = 16;
    desc->ddpfPixelFormat.dwRBitMask = 0x0000F800;
    desc->ddpfPixelFormat.dwGBitMask = 0x000007E0;
    desc->ddpfPixelFormat.dwBBitMask = 0x0000001F;
    trace_log(
        "%s normalize_display_mode after width=%lu height=%lu pitch=%ld rgbbits=%lu flags=0x%08lX",
        source,
        desc->dwWidth,
        desc->dwHeight,
        desc->lPitch,
        desc->ddpfPixelFormat.dwRGBBitCount,
        desc->dwFlags
    );
}

static void clamp_huge_surface_desc2(LPDDSURFACEDESC2 desc, const char *source)
{
    if (!desc || !env_flag_enabled("PM99_DDRAW_CLAMP_HUGE_SURFACES")) {
        return;
    }
    if (desc->dwWidth <= 10000 && desc->dwHeight <= 10000) {
        return;
    }
    trace_log(
        "%s clamp_huge_surface before width=%lu height=%lu pitch=%ld flags=0x%08lX caps=0x%08lX caps2=0x%08lX pixelflags=0x%08lX rgbbits=%lu",
        source,
        desc->dwWidth,
        desc->dwHeight,
        desc->lPitch,
        desc->dwFlags,
        desc->ddsCaps.dwCaps,
        desc->ddsCaps.dwCaps2,
        desc->ddpfPixelFormat.dwFlags,
        desc->ddpfPixelFormat.dwRGBBitCount
    );
    desc->dwWidth = 640;
    desc->dwHeight = 480;
    desc->lPitch = 0;
    desc->dwFlags |= DDSD_WIDTH | DDSD_HEIGHT;
    trace_log(
        "%s clamp_huge_surface after width=%lu height=%lu pitch=%ld flags=0x%08lX caps=0x%08lX caps2=0x%08lX pixelflags=0x%08lX rgbbits=%lu",
        source,
        desc->dwWidth,
        desc->dwHeight,
        desc->lPitch,
        desc->dwFlags,
        desc->ddsCaps.dwCaps,
        desc->ddsCaps.dwCaps2,
        desc->ddpfPixelFormat.dwFlags,
        desc->ddpfPixelFormat.dwRGBBitCount
    );
}

static void guid_to_text(const GUID *guid, char *out, size_t out_size)
{
    if (!guid) {
        lstrcpynA(out, "NULL", (int)out_size);
        return;
    }
    snprintf(
        out,
        out_size,
        "{%08lX-%04X-%04X-%02X%02X-%02X%02X%02X%02X%02X%02X}",
        (unsigned long)guid->Data1,
        guid->Data2,
        guid->Data3,
        guid->Data4[0],
        guid->Data4[1],
        guid->Data4[2],
        guid->Data4[3],
        guid->Data4[4],
        guid->Data4[5],
        guid->Data4[6],
        guid->Data4[7]
    );
}

static int ensure_real_ddraw(void)
{
    char system_dir[MAX_PATH];
    char dll_path[MAX_PATH * 2];

    if (real_ddraw_module) {
        return 1;
    }

    if (!GetSystemDirectoryA(system_dir, sizeof(system_dir))) {
        trace_log("load_real_ddraw GetSystemDirectoryA failed last_error=0x%08lX", GetLastError());
        return 0;
    }

    snprintf(dll_path, sizeof(dll_path), "%s\\ddraw.dll", system_dir);
    real_ddraw_module = LoadLibraryA(dll_path);
    if (!real_ddraw_module) {
        trace_log("load_real_ddraw LoadLibraryA path=%s failed last_error=0x%08lX", dll_path, GetLastError());
        return 0;
    }

    real_DirectDrawCreate = (PFN_DirectDrawCreate)GetProcAddress(real_ddraw_module, "DirectDrawCreate");
    real_DirectDrawCreateEx = (PFN_DirectDrawCreateEx)GetProcAddress(real_ddraw_module, "DirectDrawCreateEx");
    real_DirectDrawEnumerateA = (PFN_DirectDrawEnumerateA)GetProcAddress(real_ddraw_module, "DirectDrawEnumerateA");
    real_DirectDrawEnumerateExA = (PFN_DirectDrawEnumerateExA)GetProcAddress(real_ddraw_module, "DirectDrawEnumerateExA");

    trace_log(
        "load_real_ddraw path=%s create=%p create_ex=%p enum_a=%p enum_ex_a=%p",
        dll_path,
        real_DirectDrawCreate,
        real_DirectDrawCreateEx,
        real_DirectDrawEnumerateA,
        real_DirectDrawEnumerateExA
    );

    return real_DirectDrawCreate && real_DirectDrawEnumerateA;
}

static TraceDirectDraw *trace_from_iface(LPDIRECTDRAW iface)
{
    return (TraceDirectDraw *)iface;
}

static TraceDirectDraw4 *trace4_from_iface(LPDIRECTDRAW4 iface)
{
    return (TraceDirectDraw4 *)iface;
}

static HRESULT wrap_directdraw4(LPDIRECTDRAW4 real, LPVOID *out);

static void log_surface_desc(const char *prefix, LPDDSURFACEDESC desc)
{
    if (!desc) {
        trace_log("%s desc=NULL", prefix);
        return;
    }

    trace_log(
        "%s size=%lu flags=0x%08lX width=%lu height=%lu pitch=%ld backbuffers=%lu caps=0x%08lX pixelflags=0x%08lX rgbbits=%lu",
        prefix,
        desc->dwSize,
        desc->dwFlags,
        desc->dwWidth,
        desc->dwHeight,
        desc->lPitch,
        desc->dwBackBufferCount,
        desc->ddsCaps.dwCaps,
        desc->ddpfPixelFormat.dwFlags,
        desc->ddpfPixelFormat.dwRGBBitCount
    );
}

static void log_surface_desc2(const char *prefix, LPDDSURFACEDESC2 desc)
{
    if (!desc) {
        trace_log("%s desc=NULL", prefix);
        return;
    }

    trace_log(
        "%s size=%lu flags=0x%08lX width=%lu height=%lu pitch=%ld backbuffers=%lu caps=0x%08lX caps2=0x%08lX pixelflags=0x%08lX rgbbits=%lu",
        prefix,
        desc->dwSize,
        desc->dwFlags,
        desc->dwWidth,
        desc->dwHeight,
        desc->lPitch,
        desc->dwBackBufferCount,
        desc->ddsCaps.dwCaps,
        desc->ddsCaps.dwCaps2,
        desc->ddpfPixelFormat.dwFlags,
        desc->ddpfPixelFormat.dwRGBBitCount
    );
}

static HRESULT WINAPI trace_enum_display_mode_callback(LPDDSURFACEDESC desc, LPVOID context)
{
    EnumModesContext *ctx = (EnumModesContext *)context;
    HRESULT callback_result;

    ctx->seen++;
    trace_log(
        "%s callback mode #%lu width=%lu height=%lu pitch=%ld flags=0x%08lX pixelflags=0x%08lX rgbbits=%lu",
        ctx->source,
        ctx->seen,
        desc ? desc->dwWidth : 0,
        desc ? desc->dwHeight : 0,
        desc ? desc->lPitch : 0,
        desc ? desc->dwFlags : 0,
        desc ? desc->ddpfPixelFormat.dwFlags : 0,
        desc ? desc->ddpfPixelFormat.dwRGBBitCount : 0
    );

    if (enum_mode_filter_enabled() && !mode_desc_matches_640x480x16(desc)) {
        ctx->filtered++;
        trace_log("%s callback mode #%lu filtered", ctx->source, ctx->seen);
        return DDENUMRET_OK;
    }

    ctx->passed++;
    callback_result = ctx->callback(desc, ctx->context);
    trace_log("%s callback mode #%lu game_result=0x%08lX", ctx->source, ctx->seen, (unsigned long)callback_result);
    return callback_result;
}

static HRESULT WINAPI trace_enum_display_mode2_callback(LPDDSURFACEDESC2 desc, LPVOID context)
{
    EnumModes2Context *ctx = (EnumModes2Context *)context;
    HRESULT callback_result;

    ctx->seen++;
    trace_log(
        "%s callback mode #%lu width=%lu height=%lu pitch=%ld flags=0x%08lX pixelflags=0x%08lX rgbbits=%lu",
        ctx->source,
        ctx->seen,
        desc ? desc->dwWidth : 0,
        desc ? desc->dwHeight : 0,
        desc ? desc->lPitch : 0,
        desc ? desc->dwFlags : 0,
        desc ? desc->ddpfPixelFormat.dwFlags : 0,
        desc ? desc->ddpfPixelFormat.dwRGBBitCount : 0
    );

    if (enum_mode_filter_enabled() && !mode_desc2_matches_640x480x16(desc)) {
        ctx->filtered++;
        trace_log("%s callback mode #%lu filtered", ctx->source, ctx->seen);
        return DDENUMRET_OK;
    }

    ctx->passed++;
    callback_result = ctx->callback(desc, ctx->context);
    trace_log("%s callback mode #%lu game_result=0x%08lX", ctx->source, ctx->seen, (unsigned long)callback_result);
    return callback_result;
}

static void inject_synthetic_enum_mode_if_needed(EnumModesContext *ctx)
{
    DDSURFACEDESC synthetic_desc;
    HRESULT callback_result;

    if (!enum_mode_injection_enabled() || !ctx || ctx->passed != 0) {
        return;
    }

    fill_synthetic_640x480x16_desc(&synthetic_desc);
    ctx->seen++;
    ctx->passed++;
    trace_log(
        "%s callback mode #%lu synthetic width=%lu height=%lu pitch=%ld flags=0x%08lX pixelflags=0x%08lX rgbbits=%lu",
        ctx->source,
        ctx->seen,
        synthetic_desc.dwWidth,
        synthetic_desc.dwHeight,
        synthetic_desc.lPitch,
        synthetic_desc.dwFlags,
        synthetic_desc.ddpfPixelFormat.dwFlags,
        synthetic_desc.ddpfPixelFormat.dwRGBBitCount
    );
    callback_result = ctx->callback(&synthetic_desc, ctx->context);
    trace_log("%s callback synthetic game_result=0x%08lX", ctx->source, (unsigned long)callback_result);
}

static void inject_synthetic_enum_mode2_if_needed(EnumModes2Context *ctx)
{
    DDSURFACEDESC2 synthetic_desc;
    HRESULT callback_result;

    if (!enum_mode_injection_enabled() || !ctx || ctx->passed != 0) {
        return;
    }

    fill_synthetic_640x480x16_desc2(&synthetic_desc);
    ctx->seen++;
    ctx->passed++;
    trace_log(
        "%s callback mode #%lu synthetic width=%lu height=%lu pitch=%ld flags=0x%08lX pixelflags=0x%08lX rgbbits=%lu",
        ctx->source,
        ctx->seen,
        synthetic_desc.dwWidth,
        synthetic_desc.dwHeight,
        synthetic_desc.lPitch,
        synthetic_desc.dwFlags,
        synthetic_desc.ddpfPixelFormat.dwFlags,
        synthetic_desc.ddpfPixelFormat.dwRGBBitCount
    );
    callback_result = ctx->callback(&synthetic_desc, ctx->context);
    trace_log("%s callback synthetic game_result=0x%08lX", ctx->source, (unsigned long)callback_result);
}

static HRESULT WINAPI trace_ddraw_QueryInterface(LPDIRECTDRAW iface, REFIID riid, LPVOID *out)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    char riid_text[64];
    HRESULT hr;

    guid_to_text(riid, riid_text, sizeof(riid_text));
    hr = self->real->lpVtbl->QueryInterface(self->real, riid, out);
    trace_log("IDirectDraw::QueryInterface riid=%s hr=0x%08lX %s out=%p", riid_text, (unsigned long)hr, hr_state(hr), out ? *out : NULL);
    if (SUCCEEDED(hr) && out && *out && IsEqualGUID(riid, &PM99_IID_IDirectDraw4)) {
        hr = wrap_directdraw4((LPDIRECTDRAW4)*out, out);
        trace_log("IDirectDraw::QueryInterface wrapped IDirectDraw4 hr=0x%08lX %s out=%p", (unsigned long)hr, hr_state(hr), out ? *out : NULL);
    }
    return hr;
}

static ULONG WINAPI trace_ddraw_AddRef(LPDIRECTDRAW iface)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    ULONG real_refs = self->real->lpVtbl->AddRef(self->real);
    LONG refs = InterlockedIncrement(&self->refs);
    trace_log("IDirectDraw::AddRef wrapper_refs=%ld real_refs=%lu", refs, real_refs);
    return (ULONG)refs;
}

static ULONG WINAPI trace_ddraw_Release(LPDIRECTDRAW iface)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    ULONG real_refs = self->real->lpVtbl->Release(self->real);
    LONG refs = InterlockedDecrement(&self->refs);
    trace_log("IDirectDraw::Release wrapper_refs=%ld real_refs=%lu", refs, real_refs);
    if (refs <= 0) {
        HeapFree(GetProcessHeap(), 0, self);
        return 0;
    }
    return (ULONG)refs;
}

static HRESULT WINAPI trace_ddraw_Compact(LPDIRECTDRAW iface)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->Compact(self->real);
    trace_log("IDirectDraw::Compact hr=0x%08lX %s", (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw_CreateClipper(LPDIRECTDRAW iface, DWORD flags, LPDIRECTDRAWCLIPPER *clipper, IUnknown *outer)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->CreateClipper(self->real, flags, clipper, outer);
    trace_log("IDirectDraw::CreateClipper flags=0x%08lX hr=0x%08lX %s clipper=%p", flags, (unsigned long)hr, hr_state(hr), clipper ? *clipper : NULL);
    if (SUCCEEDED(hr) && clipper && *clipper) {
        install_directdraw_clipper_hook(*clipper);
    }
    return hr;
}

static HRESULT WINAPI trace_ddraw_CreatePalette(LPDIRECTDRAW iface, DWORD flags, LPPALETTEENTRY entries, LPDIRECTDRAWPALETTE *palette, IUnknown *outer)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->CreatePalette(self->real, flags, entries, palette, outer);
    trace_log("IDirectDraw::CreatePalette flags=0x%08lX entries=%p hr=0x%08lX %s palette=%p", flags, entries, (unsigned long)hr, hr_state(hr), palette ? *palette : NULL);
    return hr;
}

static HRESULT WINAPI trace_ddraw_CreateSurface(LPDIRECTDRAW iface, LPDDSURFACEDESC desc, LPDIRECTDRAWSURFACE *surface, IUnknown *outer)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr;
    log_surface_desc("IDirectDraw::CreateSurface input", desc);
    clamp_huge_surface_desc(desc, "IDirectDraw::CreateSurface");
    hr = self->real->lpVtbl->CreateSurface(self->real, desc, surface, outer);
    trace_log("IDirectDraw::CreateSurface hr=0x%08lX %s surface=%p", (unsigned long)hr, hr_state(hr), surface ? *surface : NULL);
    return hr;
}

static HRESULT WINAPI trace_ddraw_DuplicateSurface(LPDIRECTDRAW iface, LPDIRECTDRAWSURFACE source, LPDIRECTDRAWSURFACE *target)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->DuplicateSurface(self->real, source, target);
    trace_log("IDirectDraw::DuplicateSurface source=%p hr=0x%08lX %s target=%p", source, (unsigned long)hr, hr_state(hr), target ? *target : NULL);
    return hr;
}

static HRESULT WINAPI trace_ddraw_EnumDisplayModes(LPDIRECTDRAW iface, DWORD flags, LPDDSURFACEDESC desc, LPVOID context, LPDDENUMMODESCALLBACK callback)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    EnumModesContext wrapped_context;
    HRESULT hr;
    log_surface_desc("IDirectDraw::EnumDisplayModes filter", desc);
    if (callback) {
        ZeroMemory(&wrapped_context, sizeof(wrapped_context));
        wrapped_context.callback = callback;
        wrapped_context.context = context;
        wrapped_context.source = "IDirectDraw::EnumDisplayModes";
        hr = self->real->lpVtbl->EnumDisplayModes(self->real, flags, desc, &wrapped_context, trace_enum_display_mode_callback);
        if (SUCCEEDED(hr)) {
            inject_synthetic_enum_mode_if_needed(&wrapped_context);
        }
        trace_log(
            "IDirectDraw::EnumDisplayModes flags=0x%08lX callback=%p seen=%lu passed=%lu filtered=%lu hr=0x%08lX %s",
            flags,
            callback,
            wrapped_context.seen,
            wrapped_context.passed,
            wrapped_context.filtered,
            (unsigned long)hr,
            hr_state(hr)
        );
    } else {
        hr = self->real->lpVtbl->EnumDisplayModes(self->real, flags, desc, context, callback);
        trace_log("IDirectDraw::EnumDisplayModes flags=0x%08lX callback=NULL hr=0x%08lX %s", flags, (unsigned long)hr, hr_state(hr));
    }
    return hr;
}

static HRESULT WINAPI trace_ddraw_EnumSurfaces(LPDIRECTDRAW iface, DWORD flags, LPDDSURFACEDESC desc, LPVOID context, LPDDENUMSURFACESCALLBACK callback)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr;
    log_surface_desc("IDirectDraw::EnumSurfaces filter", desc);
    hr = self->real->lpVtbl->EnumSurfaces(self->real, flags, desc, context, callback);
    trace_log("IDirectDraw::EnumSurfaces flags=0x%08lX callback=%p hr=0x%08lX %s", flags, callback, (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw_FlipToGDISurface(LPDIRECTDRAW iface)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->FlipToGDISurface(self->real);
    trace_log("IDirectDraw::FlipToGDISurface hr=0x%08lX %s", (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw_GetCaps(LPDIRECTDRAW iface, LPDDCAPS driver_caps, LPDDCAPS hel_caps)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetCaps(self->real, driver_caps, hel_caps);
    trace_log("IDirectDraw::GetCaps hr=0x%08lX %s driver=%p hel=%p", (unsigned long)hr, hr_state(hr), driver_caps, hel_caps);
    return hr;
}

static HRESULT WINAPI trace_ddraw_GetDisplayMode(LPDIRECTDRAW iface, LPDDSURFACEDESC desc)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetDisplayMode(self->real, desc);
    trace_log("IDirectDraw::GetDisplayMode hr=0x%08lX %s", (unsigned long)hr, hr_state(hr));
    if (SUCCEEDED(hr)) {
        normalize_display_mode_desc(desc, "IDirectDraw::GetDisplayMode");
    }
    log_surface_desc("IDirectDraw::GetDisplayMode output", SUCCEEDED(hr) ? desc : NULL);
    return hr;
}

static HRESULT WINAPI trace_ddraw_GetFourCCCodes(LPDIRECTDRAW iface, LPDWORD count, LPDWORD codes)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetFourCCCodes(self->real, count, codes);
    trace_log("IDirectDraw::GetFourCCCodes count=%lu hr=0x%08lX %s", count ? *count : 0, (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw_GetGDISurface(LPDIRECTDRAW iface, LPDIRECTDRAWSURFACE *surface)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetGDISurface(self->real, surface);
    trace_log("IDirectDraw::GetGDISurface hr=0x%08lX %s surface=%p", (unsigned long)hr, hr_state(hr), surface ? *surface : NULL);
    return hr;
}

static HRESULT WINAPI trace_ddraw_GetMonitorFrequency(LPDIRECTDRAW iface, LPDWORD frequency)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetMonitorFrequency(self->real, frequency);
    trace_log("IDirectDraw::GetMonitorFrequency frequency=%lu hr=0x%08lX %s", frequency ? *frequency : 0, (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw_GetScanLine(LPDIRECTDRAW iface, LPDWORD scanline)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetScanLine(self->real, scanline);
    trace_log("IDirectDraw::GetScanLine scanline=%lu hr=0x%08lX %s", scanline ? *scanline : 0, (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw_GetVerticalBlankStatus(LPDIRECTDRAW iface, LPBOOL status)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetVerticalBlankStatus(self->real, status);
    trace_log("IDirectDraw::GetVerticalBlankStatus status=%d hr=0x%08lX %s", status ? *status : 0, (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw_Initialize(LPDIRECTDRAW iface, GUID *guid)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    char guid_text[64];
    HRESULT hr;
    guid_to_text(guid, guid_text, sizeof(guid_text));
    hr = self->real->lpVtbl->Initialize(self->real, guid);
    trace_log("IDirectDraw::Initialize guid=%s hr=0x%08lX %s", guid_text, (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw_RestoreDisplayMode(LPDIRECTDRAW iface)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->RestoreDisplayMode(self->real);
    trace_log("IDirectDraw::RestoreDisplayMode hr=0x%08lX %s", (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw_SetCooperativeLevel(LPDIRECTDRAW iface, HWND hwnd, DWORD flags)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->SetCooperativeLevel(self->real, hwnd, flags);
    trace_log("IDirectDraw::SetCooperativeLevel hwnd=%p flags=0x%08lX hr=0x%08lX %s", hwnd, flags, (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw_SetDisplayMode(LPDIRECTDRAW iface, DWORD width, DWORD height, DWORD bpp)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->SetDisplayMode(self->real, width, height, bpp);
    trace_log("IDirectDraw::SetDisplayMode width=%lu height=%lu bpp=%lu hr=0x%08lX %s", width, height, bpp, (unsigned long)hr, hr_state(hr));
    hr = maybe_force_set_display_mode_ok(hr, width, height, bpp, "IDirectDraw::SetDisplayMode");
    return hr;
}

static HRESULT WINAPI trace_ddraw_WaitForVerticalBlank(LPDIRECTDRAW iface, DWORD flags, HANDLE event)
{
    TraceDirectDraw *self = trace_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->WaitForVerticalBlank(self->real, flags, event);
    trace_log("IDirectDraw::WaitForVerticalBlank flags=0x%08lX event=%p hr=0x%08lX %s", flags, event, (unsigned long)hr, hr_state(hr));
    return hr;
}

static IDirectDrawVtbl trace_ddraw_vtbl = {
    trace_ddraw_QueryInterface,
    trace_ddraw_AddRef,
    trace_ddraw_Release,
    trace_ddraw_Compact,
    trace_ddraw_CreateClipper,
    trace_ddraw_CreatePalette,
    trace_ddraw_CreateSurface,
    trace_ddraw_DuplicateSurface,
    trace_ddraw_EnumDisplayModes,
    trace_ddraw_EnumSurfaces,
    trace_ddraw_FlipToGDISurface,
    trace_ddraw_GetCaps,
    trace_ddraw_GetDisplayMode,
    trace_ddraw_GetFourCCCodes,
    trace_ddraw_GetGDISurface,
    trace_ddraw_GetMonitorFrequency,
    trace_ddraw_GetScanLine,
    trace_ddraw_GetVerticalBlankStatus,
    trace_ddraw_Initialize,
    trace_ddraw_RestoreDisplayMode,
    trace_ddraw_SetCooperativeLevel,
    trace_ddraw_SetDisplayMode,
    trace_ddraw_WaitForVerticalBlank
};

static HRESULT WINAPI trace_ddraw4_QueryInterface(LPDIRECTDRAW4 iface, REFIID riid, LPVOID *out)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    char riid_text[64];
    HRESULT hr;

    guid_to_text(riid, riid_text, sizeof(riid_text));
    hr = self->real->lpVtbl->QueryInterface(self->real, riid, out);
    trace_log("IDirectDraw4::QueryInterface riid=%s hr=0x%08lX %s out=%p", riid_text, (unsigned long)hr, hr_state(hr), out ? *out : NULL);
    if (SUCCEEDED(hr) && out && *out && IsEqualGUID(riid, &PM99_IID_IDirectDraw4)) {
        hr = wrap_directdraw4((LPDIRECTDRAW4)*out, out);
        trace_log("IDirectDraw4::QueryInterface wrapped IDirectDraw4 hr=0x%08lX %s out=%p", (unsigned long)hr, hr_state(hr), out ? *out : NULL);
    }
    return hr;
}

static ULONG WINAPI trace_ddraw4_AddRef(LPDIRECTDRAW4 iface)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    ULONG real_refs = self->real->lpVtbl->AddRef(self->real);
    LONG refs = InterlockedIncrement(&self->refs);
    trace_log("IDirectDraw4::AddRef wrapper_refs=%ld real_refs=%lu", refs, real_refs);
    return (ULONG)refs;
}

static ULONG WINAPI trace_ddraw4_Release(LPDIRECTDRAW4 iface)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    ULONG real_refs = self->real->lpVtbl->Release(self->real);
    LONG refs = InterlockedDecrement(&self->refs);
    trace_log("IDirectDraw4::Release wrapper_refs=%ld real_refs=%lu", refs, real_refs);
    if (refs <= 0) {
        HeapFree(GetProcessHeap(), 0, self);
        return 0;
    }
    return (ULONG)refs;
}

static HRESULT WINAPI trace_ddraw4_Compact(LPDIRECTDRAW4 iface)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->Compact(self->real);
    trace_log("IDirectDraw4::Compact hr=0x%08lX %s", (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw4_CreateClipper(LPDIRECTDRAW4 iface, DWORD flags, LPDIRECTDRAWCLIPPER *clipper, IUnknown *outer)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->CreateClipper(self->real, flags, clipper, outer);
    trace_log("IDirectDraw4::CreateClipper flags=0x%08lX hr=0x%08lX %s clipper=%p", flags, (unsigned long)hr, hr_state(hr), clipper ? *clipper : NULL);
    if (SUCCEEDED(hr) && clipper && *clipper) {
        install_directdraw_clipper_hook(*clipper);
    }
    return hr;
}

static HRESULT WINAPI trace_ddraw4_CreatePalette(LPDIRECTDRAW4 iface, DWORD flags, LPPALETTEENTRY entries, LPDIRECTDRAWPALETTE *palette, IUnknown *outer)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->CreatePalette(self->real, flags, entries, palette, outer);
    trace_log("IDirectDraw4::CreatePalette flags=0x%08lX entries=%p hr=0x%08lX %s palette=%p", flags, entries, (unsigned long)hr, hr_state(hr), palette ? *palette : NULL);
    return hr;
}

static HRESULT WINAPI trace_ddraw4_CreateSurface(LPDIRECTDRAW4 iface, LPDDSURFACEDESC2 desc, LPDIRECTDRAWSURFACE4 *surface, IUnknown *outer)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr;
    DDSURFACEDESC2 fallback_desc;
    log_surface_desc2("IDirectDraw4::CreateSurface input", desc);
    clamp_huge_surface_desc2(desc, "IDirectDraw4::CreateSurface");
    hr = self->real->lpVtbl->CreateSurface(self->real, desc, surface, outer);
    trace_log("IDirectDraw4::CreateSurface hr=0x%08lX %s surface=%p", (unsigned long)hr, hr_state(hr), surface ? *surface : NULL);
    if (
        FAILED(hr)
        && managed_texture_fallback_enabled()
        && desc
        && (desc->ddsCaps.dwCaps & DDSCAPS_TEXTURE)
        && (desc->ddsCaps.dwCaps2 & DDSCAPS2_TEXTUREMANAGE)
    ) {
        fallback_desc = *desc;
        fallback_desc.ddsCaps.dwCaps2 &= ~DDSCAPS2_TEXTUREMANAGE;
        log_surface_desc2("IDirectDraw4::CreateSurface managed-texture fallback", &fallback_desc);
        if (surface) {
            *surface = NULL;
        }
        hr = self->real->lpVtbl->CreateSurface(self->real, &fallback_desc, surface, outer);
        trace_log(
            "IDirectDraw4::CreateSurface managed-texture fallback hr=0x%08lX %s surface=%p",
            (unsigned long)hr,
            hr_state(hr),
            surface ? *surface : NULL
        );
    }
    if (
        SUCCEEDED(hr)
        && desc
        && (desc->ddsCaps.dwCaps & DDSCAPS_PRIMARYSURFACE)
        && surface
        && *surface
    ) {
        install_primary_surface4_blt_hook(*surface);
    }
    return hr;
}

static HRESULT WINAPI trace_ddraw4_DuplicateSurface(LPDIRECTDRAW4 iface, LPDIRECTDRAWSURFACE4 source, LPDIRECTDRAWSURFACE4 *target)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->DuplicateSurface(self->real, source, target);
    trace_log("IDirectDraw4::DuplicateSurface source=%p hr=0x%08lX %s target=%p", source, (unsigned long)hr, hr_state(hr), target ? *target : NULL);
    return hr;
}

static HRESULT WINAPI trace_ddraw4_EnumDisplayModes(LPDIRECTDRAW4 iface, DWORD flags, LPDDSURFACEDESC2 desc, LPVOID context, LPDDENUMMODESCALLBACK2 callback)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    EnumModes2Context wrapped_context;
    HRESULT hr;
    log_surface_desc2("IDirectDraw4::EnumDisplayModes filter", desc);
    if (callback) {
        ZeroMemory(&wrapped_context, sizeof(wrapped_context));
        wrapped_context.callback = callback;
        wrapped_context.context = context;
        wrapped_context.source = "IDirectDraw4::EnumDisplayModes";
        hr = self->real->lpVtbl->EnumDisplayModes(self->real, flags, desc, &wrapped_context, trace_enum_display_mode2_callback);
        if (SUCCEEDED(hr)) {
            inject_synthetic_enum_mode2_if_needed(&wrapped_context);
        }
        trace_log(
            "IDirectDraw4::EnumDisplayModes flags=0x%08lX callback=%p seen=%lu passed=%lu filtered=%lu hr=0x%08lX %s",
            flags,
            callback,
            wrapped_context.seen,
            wrapped_context.passed,
            wrapped_context.filtered,
            (unsigned long)hr,
            hr_state(hr)
        );
    } else {
        hr = self->real->lpVtbl->EnumDisplayModes(self->real, flags, desc, context, callback);
        trace_log("IDirectDraw4::EnumDisplayModes flags=0x%08lX callback=NULL hr=0x%08lX %s", flags, (unsigned long)hr, hr_state(hr));
    }
    return hr;
}

static HRESULT WINAPI trace_ddraw4_EnumSurfaces(LPDIRECTDRAW4 iface, DWORD flags, LPDDSURFACEDESC2 desc, LPVOID context, LPDDENUMSURFACESCALLBACK2 callback)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr;
    log_surface_desc2("IDirectDraw4::EnumSurfaces filter", desc);
    hr = self->real->lpVtbl->EnumSurfaces(self->real, flags, desc, context, callback);
    trace_log("IDirectDraw4::EnumSurfaces flags=0x%08lX callback=%p hr=0x%08lX %s", flags, callback, (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw4_FlipToGDISurface(LPDIRECTDRAW4 iface)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->FlipToGDISurface(self->real);
    trace_log("IDirectDraw4::FlipToGDISurface hr=0x%08lX %s", (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw4_GetCaps(LPDIRECTDRAW4 iface, LPDDCAPS driver_caps, LPDDCAPS hel_caps)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetCaps(self->real, driver_caps, hel_caps);
    trace_log("IDirectDraw4::GetCaps hr=0x%08lX %s driver=%p hel=%p", (unsigned long)hr, hr_state(hr), driver_caps, hel_caps);
    return hr;
}

static HRESULT WINAPI trace_ddraw4_GetDisplayMode(LPDIRECTDRAW4 iface, LPDDSURFACEDESC2 desc)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetDisplayMode(self->real, desc);
    trace_log("IDirectDraw4::GetDisplayMode hr=0x%08lX %s", (unsigned long)hr, hr_state(hr));
    if (SUCCEEDED(hr)) {
        normalize_display_mode_desc2(desc, "IDirectDraw4::GetDisplayMode");
    }
    log_surface_desc2("IDirectDraw4::GetDisplayMode output", SUCCEEDED(hr) ? desc : NULL);
    return hr;
}

static HRESULT WINAPI trace_ddraw4_GetFourCCCodes(LPDIRECTDRAW4 iface, LPDWORD count, LPDWORD codes)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetFourCCCodes(self->real, count, codes);
    trace_log("IDirectDraw4::GetFourCCCodes count=%lu hr=0x%08lX %s", count ? *count : 0, (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw4_GetGDISurface(LPDIRECTDRAW4 iface, LPDIRECTDRAWSURFACE4 *surface)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetGDISurface(self->real, surface);
    trace_log("IDirectDraw4::GetGDISurface hr=0x%08lX %s surface=%p", (unsigned long)hr, hr_state(hr), surface ? *surface : NULL);
    return hr;
}

static HRESULT WINAPI trace_ddraw4_GetMonitorFrequency(LPDIRECTDRAW4 iface, LPDWORD frequency)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetMonitorFrequency(self->real, frequency);
    trace_log("IDirectDraw4::GetMonitorFrequency frequency=%lu hr=0x%08lX %s", frequency ? *frequency : 0, (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw4_GetScanLine(LPDIRECTDRAW4 iface, LPDWORD scanline)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetScanLine(self->real, scanline);
    trace_log("IDirectDraw4::GetScanLine scanline=%lu hr=0x%08lX %s", scanline ? *scanline : 0, (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw4_GetVerticalBlankStatus(LPDIRECTDRAW4 iface, LPBOOL status)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetVerticalBlankStatus(self->real, status);
    trace_log("IDirectDraw4::GetVerticalBlankStatus status=%d hr=0x%08lX %s", status ? *status : 0, (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw4_Initialize(LPDIRECTDRAW4 iface, GUID *guid)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    char guid_text[64];
    HRESULT hr;
    guid_to_text(guid, guid_text, sizeof(guid_text));
    hr = self->real->lpVtbl->Initialize(self->real, guid);
    trace_log("IDirectDraw4::Initialize guid=%s hr=0x%08lX %s", guid_text, (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw4_RestoreDisplayMode(LPDIRECTDRAW4 iface)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->RestoreDisplayMode(self->real);
    trace_log("IDirectDraw4::RestoreDisplayMode hr=0x%08lX %s", (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw4_SetCooperativeLevel(LPDIRECTDRAW4 iface, HWND hwnd, DWORD flags)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->SetCooperativeLevel(self->real, hwnd, flags);
    if (SUCCEEDED(hr) && hwnd) {
        primary_game_window = hwnd;
    }
    trace_log("IDirectDraw4::SetCooperativeLevel hwnd=%p flags=0x%08lX hr=0x%08lX %s", hwnd, flags, (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw4_SetDisplayMode(LPDIRECTDRAW4 iface, DWORD width, DWORD height, DWORD bpp, DWORD refresh, DWORD flags)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = set_display_mode_with_upscale(self->real, width, height, bpp, refresh, flags);
    trace_log("IDirectDraw4::SetDisplayMode width=%lu height=%lu bpp=%lu refresh=%lu flags=0x%08lX hr=0x%08lX %s", width, height, bpp, refresh, flags, (unsigned long)hr, hr_state(hr));
    hr = maybe_force_set_display_mode_ok(hr, width, height, bpp, "IDirectDraw4::SetDisplayMode");
    return hr;
}

static HRESULT WINAPI trace_ddraw4_WaitForVerticalBlank(LPDIRECTDRAW4 iface, DWORD flags, HANDLE event)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->WaitForVerticalBlank(self->real, flags, event);
    trace_log("IDirectDraw4::WaitForVerticalBlank flags=0x%08lX event=%p hr=0x%08lX %s", flags, event, (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw4_GetAvailableVidMem(LPDIRECTDRAW4 iface, LPDDSCAPS2 caps, LPDWORD total, LPDWORD free_mem)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetAvailableVidMem(self->real, caps, total, free_mem);
    trace_log(
        "IDirectDraw4::GetAvailableVidMem caps=0x%08lX caps2=0x%08lX total=%lu free=%lu hr=0x%08lX %s",
        caps ? caps->dwCaps : 0,
        caps ? caps->dwCaps2 : 0,
        total ? *total : 0,
        free_mem ? *free_mem : 0,
        (unsigned long)hr,
        hr_state(hr)
    );
    return hr;
}

static HRESULT WINAPI trace_ddraw4_GetSurfaceFromDC(LPDIRECTDRAW4 iface, HDC dc, LPDIRECTDRAWSURFACE4 *surface)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetSurfaceFromDC(self->real, dc, surface);
    trace_log("IDirectDraw4::GetSurfaceFromDC dc=%p hr=0x%08lX %s surface=%p", dc, (unsigned long)hr, hr_state(hr), surface ? *surface : NULL);
    return hr;
}

static HRESULT WINAPI trace_ddraw4_RestoreAllSurfaces(LPDIRECTDRAW4 iface)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->RestoreAllSurfaces(self->real);
    trace_log("IDirectDraw4::RestoreAllSurfaces hr=0x%08lX %s", (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw4_TestCooperativeLevel(LPDIRECTDRAW4 iface)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->TestCooperativeLevel(self->real);
    trace_log("IDirectDraw4::TestCooperativeLevel hr=0x%08lX %s", (unsigned long)hr, hr_state(hr));
    return hr;
}

static HRESULT WINAPI trace_ddraw4_GetDeviceIdentifier(LPDIRECTDRAW4 iface, LPDDDEVICEIDENTIFIER identifier, DWORD flags)
{
    TraceDirectDraw4 *self = trace4_from_iface(iface);
    HRESULT hr = self->real->lpVtbl->GetDeviceIdentifier(self->real, identifier, flags);
    trace_log("IDirectDraw4::GetDeviceIdentifier flags=0x%08lX hr=0x%08lX %s", flags, (unsigned long)hr, hr_state(hr));
    return hr;
}

static IDirectDraw4Vtbl trace_ddraw4_vtbl = {
    trace_ddraw4_QueryInterface,
    trace_ddraw4_AddRef,
    trace_ddraw4_Release,
    trace_ddraw4_Compact,
    trace_ddraw4_CreateClipper,
    trace_ddraw4_CreatePalette,
    trace_ddraw4_CreateSurface,
    trace_ddraw4_DuplicateSurface,
    trace_ddraw4_EnumDisplayModes,
    trace_ddraw4_EnumSurfaces,
    trace_ddraw4_FlipToGDISurface,
    trace_ddraw4_GetCaps,
    trace_ddraw4_GetDisplayMode,
    trace_ddraw4_GetFourCCCodes,
    trace_ddraw4_GetGDISurface,
    trace_ddraw4_GetMonitorFrequency,
    trace_ddraw4_GetScanLine,
    trace_ddraw4_GetVerticalBlankStatus,
    trace_ddraw4_Initialize,
    trace_ddraw4_RestoreDisplayMode,
    trace_ddraw4_SetCooperativeLevel,
    trace_ddraw4_SetDisplayMode,
    trace_ddraw4_WaitForVerticalBlank,
    trace_ddraw4_GetAvailableVidMem,
    trace_ddraw4_GetSurfaceFromDC,
    trace_ddraw4_RestoreAllSurfaces,
    trace_ddraw4_TestCooperativeLevel,
    trace_ddraw4_GetDeviceIdentifier
};

static HRESULT wrap_directdraw(LPDIRECTDRAW real, LPDIRECTDRAW *out)
{
    TraceDirectDraw *wrapped;

    if (!real || !out) {
        return DDERR_INVALIDPARAMS;
    }

    wrapped = (TraceDirectDraw *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*wrapped));
    if (!wrapped) {
        real->lpVtbl->Release(real);
        return E_OUTOFMEMORY;
    }

    wrapped->iface.lpVtbl = &trace_ddraw_vtbl;
    wrapped->real = real;
    wrapped->refs = 1;
    *out = &wrapped->iface;
    trace_log("wrap IDirectDraw real=%p wrapper=%p", real, *out);
    return DD_OK;
}

static HRESULT wrap_directdraw4(LPDIRECTDRAW4 real, LPVOID *out)
{
    TraceDirectDraw4 *wrapped;

    if (!real || !out) {
        return DDERR_INVALIDPARAMS;
    }

    wrapped = (TraceDirectDraw4 *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*wrapped));
    if (!wrapped) {
        real->lpVtbl->Release(real);
        *out = NULL;
        return E_OUTOFMEMORY;
    }

    wrapped->iface.lpVtbl = &trace_ddraw4_vtbl;
    wrapped->real = real;
    wrapped->refs = 1;
    *out = &wrapped->iface;
    trace_log("wrap IDirectDraw4 real=%p wrapper=%p", real, *out);
    return DD_OK;
}

typedef struct EnumAContext {
    LPDDENUMCALLBACKA callback;
    LPVOID context;
} EnumAContext;

static BOOL WINAPI trace_enum_a_callback(GUID *guid, LPSTR description, LPSTR name, LPVOID context)
{
    EnumAContext *ctx = (EnumAContext *)context;
    char guid_text[64];
    BOOL keep_going;

    guid_to_text(guid, guid_text, sizeof(guid_text));
    trace_log("DirectDrawEnumerateA device guid=%s description=\"%s\" name=\"%s\"", guid_text, description ? description : "", name ? name : "");
    keep_going = ctx->callback(guid, description, name, ctx->context);
    trace_log("DirectDrawEnumerateA callback result=%d", keep_going);
    return keep_going;
}

HRESULT WINAPI DirectDrawCreate(GUID *guid, LPDIRECTDRAW *out, IUnknown *outer)
{
    LPDIRECTDRAW real = NULL;
    char guid_text[64];
    HRESULT hr;

    guid_to_text(guid, guid_text, sizeof(guid_text));
    trace_log("DirectDrawCreate enter guid=%s out=%p outer=%p", guid_text, out, outer);

    if (!ensure_real_ddraw()) {
        return DDERR_GENERIC;
    }

    hr = real_DirectDrawCreate(guid, &real, outer);
    trace_log("DirectDrawCreate real hr=0x%08lX %s real=%p", (unsigned long)hr, hr_state(hr), real);
    if (FAILED(hr)) {
        if (out) {
            *out = NULL;
        }
        return hr;
    }

    hr = wrap_directdraw(real, out);
    trace_log("DirectDrawCreate wrap hr=0x%08lX %s out=%p", (unsigned long)hr, hr_state(hr), out ? *out : NULL);
    return hr;
}

HRESULT WINAPI DirectDrawCreateEx(GUID *guid, LPVOID *out, REFIID iid, IUnknown *outer)
{
    char guid_text[64];
    char iid_text[64];
    HRESULT hr;

    guid_to_text(guid, guid_text, sizeof(guid_text));
    guid_to_text(iid, iid_text, sizeof(iid_text));
    trace_log("DirectDrawCreateEx enter guid=%s iid=%s out=%p outer=%p", guid_text, iid_text, out, outer);

    if (!ensure_real_ddraw() || !real_DirectDrawCreateEx) {
        return DDERR_UNSUPPORTED;
    }

    hr = real_DirectDrawCreateEx(guid, out, iid, outer);
    trace_log("DirectDrawCreateEx hr=0x%08lX %s out=%p", (unsigned long)hr, hr_state(hr), out ? *out : NULL);
    if (SUCCEEDED(hr) && out && *out && IsEqualGUID(iid, &PM99_IID_IDirectDraw4)) {
        hr = wrap_directdraw4((LPDIRECTDRAW4)*out, out);
        trace_log("DirectDrawCreateEx wrapped IDirectDraw4 hr=0x%08lX %s out=%p", (unsigned long)hr, hr_state(hr), out ? *out : NULL);
    }
    return hr;
}

HRESULT WINAPI DirectDrawEnumerateA(LPDDENUMCALLBACKA callback, LPVOID context)
{
    EnumAContext wrapped_context;
    HRESULT hr;

    trace_log("DirectDrawEnumerateA enter callback=%p context=%p", callback, context);
    if (!ensure_real_ddraw()) {
        return DDERR_GENERIC;
    }
    if (!callback) {
        return real_DirectDrawEnumerateA(callback, context);
    }

    wrapped_context.callback = callback;
    wrapped_context.context = context;
    hr = real_DirectDrawEnumerateA(trace_enum_a_callback, &wrapped_context);
    trace_log("DirectDrawEnumerateA hr=0x%08lX %s", (unsigned long)hr, hr_state(hr));
    return hr;
}

HRESULT WINAPI DirectDrawEnumerateExA(LPDDENUMCALLBACKEXA callback, LPVOID context, DWORD flags)
{
    HRESULT hr;

    trace_log("DirectDrawEnumerateExA enter callback=%p context=%p flags=0x%08lX", callback, context, flags);
    if (!ensure_real_ddraw() || !real_DirectDrawEnumerateExA) {
        return DDERR_UNSUPPORTED;
    }

    hr = real_DirectDrawEnumerateExA(callback, context, flags);
    trace_log("DirectDrawEnumerateExA hr=0x%08lX %s", (unsigned long)hr, hr_state(hr));
    return hr;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved)
{
    (void)instance;
    (void)reserved;

    if (reason == DLL_PROCESS_ATTACH) {
        trace_log("pm99 ddraw trace proxy attached");
    } else if (reason == DLL_PROCESS_DETACH) {
        trace_log("pm99 ddraw trace proxy detached");
        if (real_ddraw_module) {
            FreeLibrary(real_ddraw_module);
            real_ddraw_module = NULL;
        }
    }
    return TRUE;
}
