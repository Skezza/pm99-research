/* Research-only forwarding DirectDraw DLL. Trace native shutdown callers. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <unknwn.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static void (WINAPI *real_quit)(int);
static BOOL (WINAPI *real_destroy)(HWND);
static BOOL (WINAPI *real_end_dialog)(HWND, INT_PTR);
static int (WINAPI *real_message_box)(HWND, LPCSTR, LPCSTR, UINT);
static HMODULE system_ddraw;
static void (__cdecl *real_srand)(unsigned int);
static void trace(const char *event, uintptr_t argument, const uintptr_t *stack);
typedef BOOL (__attribute__((thiscall)) *PlayerParser)(void *, DWORD *);
static PlayerParser real_parser;

static BOOL __attribute__((thiscall)) traced_parser(void *player, DWORD *stream) {
    BYTE *start = (BYTE *)(uintptr_t)stream[0];
    WORD declared = *(WORD *)start, id = *(WORD *)(start + 5);
    BOOL result = real_parser(player, stream);
    if (!(result & 255)) {
        const char *path = getenv("PM99_QUIT_TRACE_LOG");
        FILE *file;
        if (!path) path = "Z:\\workspace\\artifacts\\native_quit_trace.log";
        file = fopen(path, "a");
        if (file) {
            fprintf(file, "loader_rejected id=%u declared=%u consumed=%lu available=%lu parsed_id=%lu\n",
                    id, declared, (unsigned long)(stream[0] - (uintptr_t)start),
                    (unsigned long)stream[2], *(DWORD *)player);
            fclose(file);
        }
    }
    return result;
}

static void install_parser_trace(void) {
    BYTE *entry = (BYTE *)0x4afc90;
    BYTE expected[] = {0x81, 0xec, 0x0c, 0x02, 0, 0};
    BYTE *trampoline;
    DWORD protection, ignored;
    int32_t displacement;
    if (memcmp(entry, expected, sizeof(expected))) return;
    trampoline = VirtualAlloc(NULL, 16, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!trampoline) return;
    memcpy(trampoline, entry, sizeof(expected));
    trampoline[6] = 0xe9;
    displacement = (int32_t)((uintptr_t)(entry + 6) - (uintptr_t)(trampoline + 11));
    memcpy(trampoline + 7, &displacement, 4);
    real_parser = (PlayerParser)(void *)trampoline;
    if (!VirtualProtect(entry, sizeof(expected), PAGE_EXECUTE_READWRITE, &protection)) return;
    entry[0] = 0xe9;
    displacement = (int32_t)((uintptr_t)traced_parser - (uintptr_t)(entry + 5));
    memcpy(entry + 1, &displacement, 4);
    entry[5] = 0x90;
    VirtualProtect(entry, sizeof(expected), protection, &ignored);
    FlushInstructionCache(GetCurrentProcess(), entry, sizeof(expected));
}

static LONG CALLBACK exception_trace(EXCEPTION_POINTERS *exception) {
    CONTEXT *context = exception->ContextRecord;
    FILE *file;
    const char *path = getenv("PM99_QUIT_TRACE_LOG");
    if (exception->ExceptionRecord->ExceptionCode != EXCEPTION_ACCESS_VIOLATION)
        return EXCEPTION_CONTINUE_SEARCH;
    if (!path) path = "Z:\\workspace\\artifacts\\native_quit_trace.log";
    trace("ACCESS_VIOLATION", context->Eip, (uintptr_t *)(uintptr_t)context->Esp);
    file = fopen(path, "a");
    if (file) {
        fprintf(file, "eip=%08lx eax=%08lx ecx=%08lx esi=%08lx edi=%08lx\n",
                context->Eip, context->Eax, context->Ecx, context->Esi, context->Edi);
        if (context->Eip == 0x4b7867 && context->Edi == 0x754c80) {
            DWORD *list = (DWORD *)(uintptr_t)context->Edi;
            DWORD *ids = (DWORD *)(uintptr_t)list[0];
            unsigned int i;
            fprintf(file, "pool_count=%lu missing_id=%lu pool=", list[2], ids[context->Esi]);
            for (i = 0; i < list[2] && i < 256; ++i) fprintf(file, " %lu", ids[i]);
            fprintf(file, "\n");
            {
                DWORD *map = (DWORD *)0x754c60;
                DWORD *pairs = (DWORD *)(uintptr_t)map[0];
                DWORD missing = ids[context->Esi];
                fprintf(file, "map_count=%lu next_id=%lu anomalies=", map[1], map[2]);
                for (i = 0; i < map[1] && i < 30000; ++i) {
                    if (pairs[i * 2] == missing || (i && pairs[(i - 1) * 2] >= pairs[i * 2]))
                        fprintf(file, " [%u:%lu:ptr=%08lx:previous=%lu]", i,
                                pairs[i * 2], pairs[i * 2 + 1], i ? pairs[(i - 1) * 2] : 0);
                }
                fprintf(file, "\n");
            }
        }
        fclose(file);
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

static void trace(const char *event, uintptr_t argument, const uintptr_t *stack) {
    const char *path = getenv("PM99_QUIT_TRACE_LOG");
    FILE *file;
    unsigned int i;
    if (!path) path = "Z:\\workspace\\artifacts\\native_quit_trace.log";
    file = fopen(path, "a");
    if (!file) return;
    fprintf(file, "%lu %s argument=0x%lx thread=%lu native_stack=",
            (unsigned long)GetTickCount(), event, (unsigned long)argument,
            (unsigned long)GetCurrentThreadId());
    for (i = 0; i < 160; ++i) {
        uintptr_t value = stack[i];
        if (value >= 0x401000 && value < 0x6e5100)
            fprintf(file, " 0x%08lx", (unsigned long)value);
    }
    fprintf(file, "\n");
    fclose(file);
}

static void __cdecl traced_srand(unsigned int seed) {
    const char *fixed = getenv("PM99_QUIT_TRACE_SEED");
    trace("srand", seed, (uintptr_t *)__builtin_frame_address(0) + 1);
    if (fixed) seed = (unsigned int)strtoul(fixed, NULL, 0);
    real_srand(seed);
}

static void WINAPI traced_quit(int code) {
    trace("PostQuitMessage", (uintptr_t)code, (uintptr_t *)__builtin_frame_address(0) + 1);
    real_quit(code);
}

static BOOL WINAPI traced_destroy(HWND window) {
    trace("DestroyWindow", (uintptr_t)window, (uintptr_t *)__builtin_frame_address(0) + 1);
    return real_destroy(window);
}

static BOOL WINAPI traced_end_dialog(HWND window, INT_PTR result) {
    trace("EndDialog", (uintptr_t)result, (uintptr_t *)__builtin_frame_address(0) + 1);
    return real_end_dialog(window, result);
}

static int WINAPI traced_message_box(HWND window, LPCSTR text, LPCSTR title, UINT flags) {
    trace(text ? text : "MessageBoxA", (uintptr_t)flags, (uintptr_t *)__builtin_frame_address(0) + 1);
    return real_message_box(window, text, title, flags);
}

static void hook(HMODULE module, const char *name, FARPROC replacement, FARPROC *original) {
    BYTE *base = (BYTE *)module;
    if (!base) return;
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)base;
    IMAGE_NT_HEADERS32 *pe = (IMAGE_NT_HEADERS32 *)(base + dos->e_lfanew);
    DWORD rva = pe->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress;
    IMAGE_IMPORT_DESCRIPTOR *descriptor;
    if (!rva) return;
    for (descriptor = (IMAGE_IMPORT_DESCRIPTOR *)(base + rva); descriptor->Name; ++descriptor) {
        IMAGE_THUNK_DATA32 *names, *slots;
        if (!descriptor->OriginalFirstThunk) continue;
        names = (IMAGE_THUNK_DATA32 *)(base + descriptor->OriginalFirstThunk);
        slots = (IMAGE_THUNK_DATA32 *)(base + descriptor->FirstThunk);
        for (; names->u1.AddressOfData; ++names, ++slots) {
            IMAGE_IMPORT_BY_NAME *entry;
            DWORD protection, ignored;
            if (IMAGE_SNAP_BY_ORDINAL32(names->u1.Ordinal)) continue;
            entry = (IMAGE_IMPORT_BY_NAME *)(base + names->u1.AddressOfData);
            if (strcmp((char *)entry->Name, name)) continue;
            if (slots->u1.Function == (DWORD)(uintptr_t)replacement) continue;
            if (!VirtualProtect(&slots->u1.Function, sizeof(DWORD), PAGE_READWRITE, &protection)) continue;
            *original = (FARPROC)(uintptr_t)slots->u1.Function;
            slots->u1.Function = (DWORD)(uintptr_t)replacement;
            VirtualProtect(&slots->u1.Function, sizeof(DWORD), protection, &ignored);
        }
    }
}

static void install_hooks(void) {
    HMODULE modules[] = {GetModuleHandleA(NULL), GetModuleHandleA("MFC42.DLL")};
    unsigned int i;
    for (i = 0; i < sizeof(modules) / sizeof(modules[0]); ++i) {
        hook(modules[i], "srand", (FARPROC)(void *)traced_srand, (FARPROC *)&real_srand);
        hook(modules[i], "PostQuitMessage", (FARPROC)(void *)traced_quit, (FARPROC *)&real_quit);
        hook(modules[i], "DestroyWindow", (FARPROC)(void *)traced_destroy, (FARPROC *)&real_destroy);
        hook(modules[i], "EndDialog", (FARPROC)(void *)traced_end_dialog, (FARPROC *)&real_end_dialog);
        hook(modules[i], "MessageBoxA", (FARPROC)(void *)traced_message_box, (FARPROC *)&real_message_box);
    }
}

static FARPROC forward(const char *name) {
    install_hooks();
    if (!system_ddraw) {
        char path[MAX_PATH];
        GetSystemDirectoryA(path, MAX_PATH);
        strcat(path, "\\ddraw.dll");
        system_ddraw = LoadLibraryA(path);
    }
    return system_ddraw ? GetProcAddress(system_ddraw, name) : NULL;
}

HRESULT WINAPI DirectDrawCreate(GUID *guid, void **out, IUnknown *outer) {
    typedef HRESULT (WINAPI *Function)(GUID *, void **, IUnknown *);
    Function function = (Function)(void *)forward("DirectDrawCreate");
    return function ? function(guid, out, outer) : E_FAIL;
}
HRESULT WINAPI DirectDrawCreateEx(GUID *guid, void **out, REFIID iid, IUnknown *outer) {
    typedef HRESULT (WINAPI *Function)(GUID *, void **, REFIID, IUnknown *);
    Function function = (Function)(void *)forward("DirectDrawCreateEx");
    return function ? function(guid, out, iid, outer) : E_FAIL;
}
HRESULT WINAPI DirectDrawEnumerateA(void *callback, void *context) {
    typedef HRESULT (WINAPI *Function)(void *, void *);
    Function function = (Function)(void *)forward("DirectDrawEnumerateA");
    return function ? function(callback, context) : E_FAIL;
}
HRESULT WINAPI DirectDrawEnumerateExA(void *callback, void *context, DWORD flags) {
    typedef HRESULT (WINAPI *Function)(void *, void *, DWORD);
    Function function = (Function)(void *)forward("DirectDrawEnumerateExA");
    return function ? function(callback, context, flags) : E_FAIL;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)instance;
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        AddVectoredExceptionHandler(1, exception_trace);
        install_parser_trace();
        trace("trace_loaded", 0, (uintptr_t *)__builtin_frame_address(0) + 1);
        install_hooks();
    }
    return TRUE;
}
