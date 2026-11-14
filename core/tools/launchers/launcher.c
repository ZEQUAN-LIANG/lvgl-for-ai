#include <windows.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#include "config.h"

#ifndef LAUNCHER_TARGET
#error "LAUNCHER_TARGET is not defined"
#endif

#ifndef LAUNCHER_CWD
#error "LAUNCHER_CWD is not defined"
#endif

#ifndef LAUNCHER_ARGS
#define LAUNCHER_ARGS L""
#endif

#ifndef LAUNCHER_TITLE
#define LAUNCHER_TITLE L"Launcher"
#endif

#ifndef LAUNCHER_PYTHON
#define LAUNCHER_PYTHON L""
#endif

#define BUFFER_SIZE 32768U
#define COMMAND_SIZE 65536U

#define CH_BACKSLASH ((wchar_t)L'\\')
#define CH_COLON ((wchar_t)L':')
#define CH_NUL ((wchar_t)L'\0')
#define CH_QUOTE ((wchar_t)L'"')
#define CH_SEMICOLON ((wchar_t)L';')
#define CH_SPACE ((wchar_t)L' ')
#define CH_TAB ((wchar_t)L'\t')
#define CH_SLASH ((wchar_t)L'/')

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command_line, int show);

static void show_error(const wchar_t *message) {
    MessageBoxW(NULL, message, LAUNCHER_TITLE, MB_ICONERROR | MB_OK | MB_SETFOREGROUND);
}

static int append_text(wchar_t *dst, size_t capacity, const wchar_t *src) {
    size_t used = wcslen(dst);
    size_t needed = wcslen(src);
    if ((used + needed + 1U) > capacity) {
        return 0;
    }
    memcpy(&dst[used], src, (needed + 1U) * sizeof(wchar_t));
    return 1;
}

static int join_path(wchar_t *out, size_t capacity, const wchar_t *dir, const wchar_t *name) {
    size_t dir_len = wcslen(dir);
    size_t name_len = wcslen(name);
    int separator = 0;
    if (dir_len > 0U) {
        if ((dir[dir_len - 1U] != CH_BACKSLASH) && (dir[dir_len - 1U] != CH_SLASH)) {
            separator = 1;
        }
    }
    if ((dir_len + (size_t)separator + name_len + 1U) > capacity) {
        return 0;
    }
    memcpy(out, dir, dir_len * sizeof(wchar_t));
    size_t pos = dir_len;
    if (separator != 0) {
        out[pos] = CH_BACKSLASH;
        pos++;
    }
    memcpy(&out[pos], name, (name_len + 1U) * sizeof(wchar_t));
    return 1;
}

static int parent_dir(const wchar_t *path, wchar_t *out, size_t capacity) {
    size_t len = wcslen(path);
    while ((len > 0U) && (path[len - 1U] != CH_BACKSLASH) && (path[len - 1U] != CH_SLASH)) {
        len--;
    }
    if ((len == 0U) || (len >= capacity)) {
        return 0;
    }
    memcpy(out, path, len * sizeof(wchar_t));
    out[len] = CH_NUL;
    return 1;
}

static int is_absolute_entry(const wchar_t *entry, size_t length) {
    int absolute = 0;
    if (length >= 2U) {
        absolute = ((entry[1] == CH_COLON) ||
                    ((entry[0] == CH_BACKSLASH) && (entry[1] == CH_BACKSLASH))) ? 1 : 0;
    }
    return absolute;
}

static int find_in_path(const wchar_t *name, wchar_t *out, size_t capacity) {
    DWORD needed = GetEnvironmentVariableW(L"PATH", NULL, 0UL);
    if (needed == 0UL) {
        return 0;
    }
    wchar_t *path = (wchar_t *)malloc(needed * sizeof(wchar_t));
    if (path == NULL) {
        return 0;
    }
    if (GetEnvironmentVariableW(L"PATH", path, needed) == 0UL) {
        free(path);
        return 0;
    }
    int found = 0;
    size_t cursor = 0U;
    int searching = 1;
    while ((path[cursor] != CH_NUL) && (searching != 0)) {
        size_t end = cursor;
        while ((path[end] != CH_NUL) && (path[end] != CH_SEMICOLON)) {
            end++;
        }
        int has_separator = 0;
        if (path[end] == CH_SEMICOLON) {
            path[end] = CH_NUL;
            has_separator = 1;
        }
        size_t entry_pos = cursor;
        while ((path[entry_pos] == CH_SPACE) || (path[entry_pos] == CH_TAB) ||
               (path[entry_pos] == CH_QUOTE)) {
            entry_pos++;
        }
        size_t entry_len = end - entry_pos;
        while (entry_len > 0U) {
            wchar_t last = path[entry_pos + entry_len - 1U];
            if ((last != CH_SPACE) && (last != CH_TAB) && (last != CH_QUOTE)) {
                break;
            }
            entry_len--;
            path[entry_pos + entry_len] = CH_NUL;
        }
        int absolute = is_absolute_entry(&path[entry_pos], entry_len);
        if ((absolute != 0) && (join_path(out, capacity, &path[entry_pos], name) != 0)) {
            DWORD attributes = GetFileAttributesW(out);
            if ((attributes != INVALID_FILE_ATTRIBUTES) &&
                ((attributes & (DWORD)FILE_ATTRIBUTE_DIRECTORY) == 0UL)) {
                found = 1;
                searching = 0;
            }
        }
        if (found == 0) {
            if (has_separator != 0) {
                cursor = end + 1U;
            } else {
                searching = 0;
            }
        }
    }
    free(path);
    return found;
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command_line, int show) {
    (void)instance;
    (void)previous;
    (void)command_line;
    (void)show;

    wchar_t exe_path[BUFFER_SIZE];
    DWORD exe_length = GetModuleFileNameW(NULL, exe_path, (DWORD)BUFFER_SIZE);
    if ((exe_length == 0UL) || (exe_length >= (DWORD)BUFFER_SIZE)) {
        show_error(L"Cannot locate the launcher executable.");
        return 1;
    }

    wchar_t exe_dir[BUFFER_SIZE];
    if (parent_dir(exe_path, exe_dir, (size_t)BUFFER_SIZE) == 0) {
        show_error(L"Cannot locate the launcher directory.");
        return 1;
    }

    wchar_t combined[BUFFER_SIZE];
    wchar_t target[BUFFER_SIZE];
    if ((join_path(combined, (size_t)BUFFER_SIZE, exe_dir, LAUNCHER_TARGET) == 0) ||
        (GetFullPathNameW(combined, (DWORD)BUFFER_SIZE, target, NULL) == 0UL)) {
        show_error(L"Cannot resolve the launcher target.");
        return 1;
    }

    DWORD target_attributes = GetFileAttributesW(target);
    if ((target_attributes == INVALID_FILE_ATTRIBUTES) ||
        ((target_attributes & (DWORD)FILE_ATTRIBUTE_DIRECTORY) != 0UL)) {
        wchar_t message[1024];
        wsprintfW(message, L"Launcher target not found:\n%s", target);
        show_error(message);
        return 1;
    }

    wchar_t cwd_combined[BUFFER_SIZE];
    wchar_t working_dir[BUFFER_SIZE];
    if ((join_path(cwd_combined, (size_t)BUFFER_SIZE, exe_dir, LAUNCHER_CWD) == 0) ||
        (GetFullPathNameW(cwd_combined, (DWORD)BUFFER_SIZE, working_dir, NULL) == 0UL)) {
        show_error(L"Cannot resolve the launcher working directory.");
        return 1;
    }

    DWORD cwd_attributes = GetFileAttributesW(working_dir);
    if ((cwd_attributes == INVALID_FILE_ATTRIBUTES) ||
        ((cwd_attributes & (DWORD)FILE_ATTRIBUTE_DIRECTORY) == 0UL)) {
        wchar_t message[1024];
        wsprintfW(message, L"Launcher working directory not found:\n%s", working_dir);
        show_error(message);
        return 1;
    }

    wchar_t python[BUFFER_SIZE];
    int use_pyw = 0;
    int use_bundled = 0;
    if (LAUNCHER_PYTHON[0] != CH_NUL) {
        wchar_t bundled[BUFFER_SIZE];
        if (join_path(bundled, (size_t)BUFFER_SIZE, exe_dir, LAUNCHER_PYTHON) != 0) {
            DWORD attributes = GetFileAttributesW(bundled);
            if ((attributes != INVALID_FILE_ATTRIBUTES) &&
                ((attributes & (DWORD)FILE_ATTRIBUTE_DIRECTORY) == 0UL)) {
                wcscpy(python, bundled);
                use_bundled = 1;
            }
        }
    }
    if (use_bundled == 0) {
        if (find_in_path(L"pythonw.exe", python, (size_t)BUFFER_SIZE) == 0) {
            if (find_in_path(L"pyw.exe", python, (size_t)BUFFER_SIZE) != 0) {
                use_pyw = 1;
            } else {
                show_error(
                    L"pythonw.exe was not found in the package runtime or PATH.\n"
                    L"Install Python 3.9+ and add its install directory to PATH.");
                return 1;
            }
        }
    }

    wchar_t command[COMMAND_SIZE];
    command[0] = CH_NUL;
    int built = append_text(command, (size_t)COMMAND_SIZE, L"\"");
    if (built != 0) {
        built = append_text(command, (size_t)COMMAND_SIZE, python);
    }
    if (built != 0) {
        built = append_text(command, (size_t)COMMAND_SIZE, L"\"");
    }
    if ((use_pyw != 0) && (built != 0)) {
        built = append_text(command, (size_t)COMMAND_SIZE, L" -3");
    }
    if (built != 0) {
        built = append_text(command, (size_t)COMMAND_SIZE, L" -I \"");
    }
    if (built != 0) {
        built = append_text(command, (size_t)COMMAND_SIZE, target);
    }
    if (built != 0) {
        built = append_text(command, (size_t)COMMAND_SIZE, L"\"");
    }
    if (built != 0) {
        built = append_text(command, (size_t)COMMAND_SIZE, LAUNCHER_ARGS);
    }
    if (built == 0) {
        show_error(L"Launcher command is too long.");
        return 1;
    }

    STARTUPINFOW startup;
    PROCESS_INFORMATION process;
    ZeroMemory(&startup, sizeof(startup));
    startup.cb = (DWORD)sizeof(startup);
    ZeroMemory(&process, sizeof(process));
    if (CreateProcessW(python, command, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL,
                       working_dir, &startup, &process) == 0) {
        wchar_t message[1024];
        wsprintfW(message, L"Failed to start the launcher (error %lu).",
                  (unsigned long)GetLastError());
        show_error(message);
        return 1;
    }
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return 0;
}
