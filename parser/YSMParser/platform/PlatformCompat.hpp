#pragma once

#include <cstdio>
#include <cstdlib>
#include <cstring>

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <io.h>
#include <intrin.h>
#else
#include <csignal>
#if !defined(__EMSCRIPTEN__)
#include <unistd.h>
#endif
#endif

namespace PlatformCompat {

inline void init_console_utf8() {
#ifdef _WIN32
    SetConsoleOutputCP(CP_UTF8);
    SetConsoleCP(CP_UTF8);
#endif
}

inline const char* null_device_path() {
#if defined(_WIN32)
    return "NUL";
#elif defined(__EMSCRIPTEN__)
    return "";
#else
    return "/dev/null";
#endif
}

inline int fileno_of(FILE* stream) {
#if defined(_WIN32)
    return _fileno(stream);
#elif defined(__EMSCRIPTEN__)
    (void)stream;
    return -1;
#else
    return ::fileno(stream);
#endif
}

inline int dup_fd(int fd) {
#if defined(_WIN32)
    return _dup(fd);
#elif defined(__EMSCRIPTEN__)
    (void)fd;
    return -1;
#else
    return ::dup(fd);
#endif
}

inline int dup2_fd(int old_fd, int new_fd) {
#if defined(_WIN32)
    return _dup2(old_fd, new_fd);
#elif defined(__EMSCRIPTEN__)
    (void)old_fd;
    (void)new_fd;
    return -1;
#else
    return ::dup2(old_fd, new_fd);
#endif
}

inline int close_fd(int fd) {
#if defined(_WIN32)
    return _close(fd);
#elif defined(__EMSCRIPTEN__)
    (void)fd;
    return 0;
#else
    return ::close(fd);
#endif
}

inline bool enable_virtual_terminal(FILE* stream) {
#if defined(_WIN32)
    const int fd = fileno_of(stream);
    if (fd < 0) {
        return false;
    }

    const intptr_t os_handle = _get_osfhandle(fd);
    if (os_handle == -1) {
        return false;
    }

    HANDLE handle = reinterpret_cast<HANDLE>(os_handle);
    DWORD mode = 0;
    if (!GetConsoleMode(handle, &mode)) {
        return false;
    }

    if ((mode & ENABLE_VIRTUAL_TERMINAL_PROCESSING) != 0) {
        return true;
    }

    return SetConsoleMode(handle, mode | ENABLE_VIRTUAL_TERMINAL_PROCESSING) != 0;
#elif defined(__EMSCRIPTEN__)
    (void)stream;
    return false;
#else
    if (::isatty(fileno_of(stream)) == 0) {
        return false;
    }

    const char* term = std::getenv("TERM");
    return term != nullptr && std::strcmp(term, "dumb") != 0;
#endif
}

inline void debug_trap() {
#if defined(_MSC_VER)
    __debugbreak();
#elif defined(__clang__) || defined(__GNUC__)
    __builtin_trap();
#else
    std::raise(SIGTRAP);
#endif
}

} // namespace PlatformCompat

#ifndef _MSC_VER
#define __debugbreak() ::PlatformCompat::debug_trap()
#endif
