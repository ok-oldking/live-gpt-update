"""Read Windows process elevation without requesting additional privileges."""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes as w
from dataclasses import dataclass


@dataclass(frozen=True)
class AdministratorWindow:
    hwnd: int
    title: str


def foreground_administrator_window() -> AdministratorWindow | None:
    if sys.platform != "win32":
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    advapi.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD)]
    user.GetForegroundWindow.restype = w.HWND
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.GetWindowTextLengthW.argtypes = [w.HWND]
    user.GetWindowTextLengthW.restype = ctypes.c_int
    user.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    user.GetWindowTextW.restype = ctypes.c_int

    def elevated(pid: int) -> bool | None:
        process = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not process:
            return None
        token = w.HANDLE()
        try:
            if not advapi.OpenProcessToken(process, 8, ctypes.byref(token)):  # TOKEN_QUERY
                return None
            value, size = w.DWORD(), w.DWORD()
            if not advapi.GetTokenInformation(token, 20, ctypes.byref(value),
                                              ctypes.sizeof(value), ctypes.byref(size)):
                return None
            return bool(value.value)
        finally:
            if token:
                kernel.CloseHandle(token)
            kernel.CloseHandle(process)

    # Unknown/access-denied is not evidence that a process is elevated.
    if elevated(os.getpid()) is not False:
        return None
    hwnd = user.GetForegroundWindow()
    pid = w.DWORD()
    if not hwnd or not user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
        return None
    if pid.value == os.getpid() or elevated(pid.value) is not True:
        return None
    title = ctypes.create_unicode_buffer(user.GetWindowTextLengthW(hwnd) + 1)
    user.GetWindowTextW(hwnd, title, len(title))
    return AdministratorWindow(hwnd, title.value)
