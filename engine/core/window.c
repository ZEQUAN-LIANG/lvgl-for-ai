/**
 * @file window.c
 * Win32 GDI window and real-input source; stubs for other platforms.
 *
 * The window owns no LVGL state. It paints the engine's full framebuffer and
 * turns WM_* input into window_event_t callbacks, so every LVGL call
 * stays on the pumping thread.
 */

#include "window.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif

#include <windows.h>

#define WINDOW_CLASS      L"engine_window"
#define WINDOW_CLASS_UTF8 "engine_window"

struct window {
    HWND hwnd;
    uint32_t width;
    uint32_t height;
    const uint8_t * framebuffer;
    window_input_cb callback;
    void * user;
    bool closed;
    bool pointer_down;
    int32_t pointer_x;
    int32_t pointer_y;
};

static volatile LONG ctrl_interrupted = 0;

static BOOL WINAPI ctrl_handler(DWORD type)
{
    if(type == CTRL_C_EVENT || type == CTRL_BREAK_EVENT) {
        InterlockedExchange(&ctrl_interrupted, 1);
        return TRUE;
    }
    /* CTRL_CLOSE_EVENT still gets the default termination; the console cannot
     * wait for a graceful session close on that path. */
    return FALSE;
}

void window_install_ctrl_handler(void)
{
    SetConsoleCtrlHandler(ctrl_handler, TRUE);
}

bool window_console_interrupted(void)
{
    return InterlockedCompareExchange(&ctrl_interrupted, 0, 0) != 0;
}

static void window_draw(window_t * window, HDC dc)
{
    if(window == NULL || window->framebuffer == NULL) return;

    BITMAPINFO info;
    memset(&info, 0, sizeof(info));
    info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth = (LONG)window->width;
    info.bmiHeader.biHeight = -(LONG)window->height; /* top-down, like LVGL */
    info.bmiHeader.biPlanes = 1;
    info.bmiHeader.biBitCount = 32;
    info.bmiHeader.biCompression = BI_RGB;

    SetDIBitsToDevice(dc, 0, 0, window->width, window->height, 0, 0, 0,
                      window->height, window->framebuffer, &info,
                      DIB_RGB_COLORS);
}

static int32_t clamp(int32_t value, uint32_t limit)
{
    if(value < 0) return 0;
    if(limit == 0) return 0;
    if((uint32_t)value >= limit) return (int32_t)(limit - 1u);
    return value;
}

typedef struct {
    UINT vk;
    uint32_t key;
    const char * name;
} key_map_t;

/* LVGL key codes from lv_key_t; names match tool.control.keys. */
static const key_map_t key_map[] = {
    {VK_UP, 17, "UP"},         {VK_DOWN, 18, "DOWN"},
    {VK_RIGHT, 19, "RIGHT"},   {VK_LEFT, 20, "LEFT"},
    {VK_ESCAPE, 27, "ESC"},    {VK_DELETE, 127, "DEL"},
    {VK_BACK, 8, "BACKSPACE"}, {VK_RETURN, 10, "ENTER"},
    {VK_NEXT, 9, "NEXT"},      {VK_PRIOR, 11, "PREV"},
    {VK_HOME, 2, "HOME"},      {VK_END, 3, "END"},
};

static const key_map_t * lookup_key(UINT vk)
{
    for(size_t i = 0; i < sizeof(key_map) / sizeof(key_map[0]); i++) {
        if(key_map[i].vk == vk) return &key_map[i];
    }
    return NULL;
}

static void emit_pointer_at(window_t * window, window_pointer_action_t action,
                            int32_t x, int32_t y, bool pressed)
{
    window_event_t event;
    memset(&event, 0, sizeof(event));
    event.kind = WINDOW_EVENT_POINTER;
    event.x = clamp(x, window->width);
    event.y = clamp(y, window->height);
    event.action = action;
    event.pressed = pressed;
    if(window->callback != NULL) window->callback(window->user, &event);
}

static void emit_key(window_t * window, const key_map_t * key, bool pressed)
{
    window_event_t event;
    memset(&event, 0, sizeof(event));
    event.kind = WINDOW_EVENT_KEY;
    event.pressed = pressed;
    event.key = key->key;
    event.key_name = key->name;
    if(window->callback != NULL) window->callback(window->user, &event);
}

static LRESULT CALLBACK window_proc(HWND hwnd, UINT message, WPARAM wparam,
                                    LPARAM lparam)
{
    window_t * window = (window_t *)GetWindowLongPtrW(hwnd, GWLP_USERDATA);

    switch(message) {
        case WM_NCCREATE: {
            CREATESTRUCTW * create = (CREATESTRUCTW *)lparam;
            window = (window_t *)create->lpCreateParams;
            window->hwnd = hwnd;
            SetWindowLongPtrW(hwnd, GWLP_USERDATA, (LONG_PTR)window);
            /* DefWindowProc stores the CreateWindowExW title; returning TRUE
             * here without it leaves the window with an empty caption. */
            return DefWindowProcW(hwnd, message, wparam, lparam);
        }
        case WM_CLOSE:
            if(window != NULL) window->closed = true;
            return 0;
        case WM_DESTROY:
            PostQuitMessage(0);
            return 0;
        case WM_ERASEBKGND:
            return 1;
        case WM_PAINT: {
            PAINTSTRUCT paint;
            HDC dc = BeginPaint(hwnd, &paint);
            window_draw(window, dc);
            EndPaint(hwnd, &paint);
            return 0;
        }
        case WM_PRINTCLIENT:
            /* PrintWindow(PW_CLIENTONLY) reaches this path even when the
             * window is occluded, which keeps screenshot evidence honest. */
            window_draw(window, (HDC)wparam);
            return 0;
        case WM_MOUSEMOVE:
            if(window != NULL) {
                window->pointer_x =
                    clamp((int32_t)(short)LOWORD(lparam), window->width);
                window->pointer_y =
                    clamp((int32_t)(short)HIWORD(lparam), window->height);
                emit_pointer_at(window, WINDOW_POINTER_MOVE, window->pointer_x,
                                window->pointer_y, (wparam & MK_LBUTTON) != 0);
            }
            return 0;
        case WM_LBUTTONDOWN:
            if(window != NULL) {
                window->pointer_down = true;
                window->pointer_x =
                    clamp((int32_t)(short)LOWORD(lparam), window->width);
                window->pointer_y =
                    clamp((int32_t)(short)HIWORD(lparam), window->height);
                SetCapture(hwnd);
                emit_pointer_at(window, WINDOW_POINTER_DOWN, window->pointer_x,
                                window->pointer_y, true);
            }
            return 0;
        case WM_LBUTTONUP:
            if(window != NULL) {
                window->pointer_down = false;
                window->pointer_x =
                    clamp((int32_t)(short)LOWORD(lparam), window->width);
                window->pointer_y =
                    clamp((int32_t)(short)HIWORD(lparam), window->height);
                ReleaseCapture();
                emit_pointer_at(window, WINDOW_POINTER_UP, window->pointer_x,
                                window->pointer_y, false);
            }
            return 0;
        case WM_CAPTURECHANGED:
            /* Capture can vanish on alt-tab; release the LVGL pointer so the
             * next real click does not start from a stuck pressed state. */
            if(window != NULL && window->pointer_down) {
                window->pointer_down = false;
                emit_pointer_at(window, WINDOW_POINTER_UP, window->pointer_x,
                                window->pointer_y, false);
            }
            return 0;
        case WM_KEYDOWN:
        case WM_SYSKEYDOWN: {
            if(window == NULL || (lparam & (1L << 30)) != 0) return 0;
            const key_map_t * key = lookup_key((UINT)wparam);
            if(key != NULL) emit_key(window, key, true);
            return 0;
        }
        case WM_KEYUP:
        case WM_SYSKEYUP: {
            if(window == NULL) return 0;
            const key_map_t * key = lookup_key((UINT)wparam);
            if(key != NULL) emit_key(window, key, false);
            return 0;
        }
        default:
            return DefWindowProcW(hwnd, message, wparam, lparam);
    }
}

bool window_available(void)
{
    return true;
}

window_t * window_create(uint32_t width, uint32_t height, const char * title,
                         window_input_cb callback, void * user)
{
    if(width == 0 || height == 0) return NULL;

    window_t * window = (window_t *)calloc(1, sizeof(*window));
    if(window == NULL) return NULL;
    window->width = width;
    window->height = height;
    window->callback = callback;
    window->user = user;

    /* Fixed client size in physical pixels. */
    SetProcessDPIAware();

    HINSTANCE instance = GetModuleHandleW(NULL);
    WNDCLASSEXW window_class;
    memset(&window_class, 0, sizeof(window_class));
    window_class.cbSize = sizeof(window_class);
    window_class.style = CS_HREDRAW | CS_VREDRAW;
    window_class.lpfnWndProc = window_proc;
    window_class.hInstance = instance;
    window_class.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
    window_class.hbrBackground = NULL;
    window_class.lpszClassName = WINDOW_CLASS;
    if(RegisterClassExW(&window_class) == 0 &&
       GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
        fprintf(stderr, "[engine] cannot register the window class\n");
        free(window);
        return NULL;
    }

    DWORD style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX;
    RECT rect = {0, 0, (LONG)width, (LONG)height};
    AdjustWindowRectEx(&rect, style, FALSE, 0);

    wchar_t wide_title[512];
    wide_title[0] = L'\0';
    MultiByteToWideChar(CP_UTF8, 0, title != NULL ? title : WINDOW_CLASS_UTF8,
                        -1, wide_title,
                        (int)(sizeof(wide_title) / sizeof(wide_title[0])));

    HWND hwnd = CreateWindowExW(0, WINDOW_CLASS, wide_title, style, 100, 100,
                                rect.right - rect.left, rect.bottom - rect.top,
                                NULL, NULL, instance, window);
    if(hwnd == NULL) {
        fprintf(stderr, "[engine] cannot create the window (error %lu)\n",
                (unsigned long)GetLastError());
        free(window);
        return NULL;
    }
    window->hwnd = hwnd;

    ShowWindow(hwnd, SW_SHOWNORMAL);
    UpdateWindow(hwnd);
    SetForegroundWindow(hwnd);
    return window;
}

void window_destroy(window_t * window)
{
    if(window == NULL) return;
    if(window->hwnd != NULL) {
        SetWindowLongPtrW(window->hwnd, GWLP_USERDATA, 0);
        DestroyWindow(window->hwnd);
        window->hwnd = NULL;
    }
    free(window);
}

bool window_pump(window_t * window)
{
    if(window == NULL || window->closed) return false;

    MSG message;
    while(PeekMessageW(&message, NULL, 0, 0, PM_REMOVE)) {
        if(message.message == WM_QUIT) {
            window->closed = true;
            break;
        }
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }
    return !window->closed;
}

void window_present(window_t * window, const uint8_t * framebuffer)
{
    if(window == NULL || window->hwnd == NULL || window->closed) return;
    window->framebuffer = framebuffer;
    InvalidateRect(window->hwnd, NULL, FALSE);
    UpdateWindow(window->hwnd);
}

#else

struct window {
    int unused;
};

bool window_available(void)
{
    return false;
}

window_t * window_create(uint32_t width, uint32_t height, const char * title,
                         window_input_cb callback, void * user)
{
    (void)width;
    (void)height;
    (void)title;
    (void)callback;
    (void)user;
    fprintf(stderr, "[engine] window mode is only implemented on Windows; "
                    "continuing headless\n");
    return NULL;
}

void window_destroy(window_t * window)
{
    (void)window;
}

bool window_pump(window_t * window)
{
    (void)window;
    return false;
}

void window_present(window_t * window, const uint8_t * framebuffer)
{
    (void)window;
    (void)framebuffer;
}

void window_install_ctrl_handler(void)
{
}

bool window_console_interrupted(void)
{
    return false;
}

#endif
