"""Native Windows sampler for the optional local-machine panel.

The module intentionally uses Windows APIs directly: invoking PowerShell, WMIC
or tasklist would create extra processes and makes collection depend on their
locale and availability.  Importing it remains harmless on non-Windows hosts.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import platform
import shutil
import socket
import time
from typing import Any


_IS_WINDOWS = os.name == "nt"
_SIZE_T = ctypes.c_size_t
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_TH32CS_SNAPPROCESS = 0x00000002
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_VM_READ = 0x0010
_MAX_PATH = 260


class _FILETIME(ctypes.Structure):
    _fields_ = (("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD))


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = (("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong))


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = (("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", _SIZE_T),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * _MAX_PATH))


class _PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = (("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", _SIZE_T), ("WorkingSetSize", _SIZE_T),
                ("QuotaPeakPagedPoolUsage", _SIZE_T), ("QuotaPagedPoolUsage", _SIZE_T),
                ("QuotaPeakNonPagedPoolUsage", _SIZE_T), ("QuotaNonPagedPoolUsage", _SIZE_T),
                ("PagefileUsage", _SIZE_T), ("PeakPagefileUsage", _SIZE_T),
                ("PrivateUsage", _SIZE_T))


class _ENUM_PAGE_FILE_INFORMATION(ctypes.Structure):
    _fields_ = (("cb", wintypes.DWORD), ("Reserved", wintypes.DWORD),
                ("TotalSize", _SIZE_T), ("TotalInUse", _SIZE_T), ("PeakUsage", _SIZE_T))


class _SYSTEM_INFO(ctypes.Structure):
    _fields_ = (("wProcessorArchitecture", wintypes.WORD), ("wReserved", wintypes.WORD),
                ("dwPageSize", wintypes.DWORD), ("lpMinimumApplicationAddress", ctypes.c_void_p),
                ("lpMaximumApplicationAddress", ctypes.c_void_p), ("dwActiveProcessorMask", _SIZE_T),
                ("dwNumberOfProcessors", wintypes.DWORD), ("dwProcessorType", wintypes.DWORD),
                ("dwAllocationGranularity", wintypes.DWORD), ("wProcessorLevel", wintypes.WORD),
                ("wProcessorRevision", wintypes.WORD))


def _filetime_value(value: _FILETIME) -> int:
    return (value.dwHighDateTime << 32) | value.dwLowDateTime


def _cpu_percent(previous: tuple[int, int] | None,
                 current: tuple[int, int] | None) -> float | None:
    """Return busy percentage from ``(idle, total)`` 100-ns counters."""
    if previous is None or current is None:
        return None
    idle = current[0] - previous[0]
    total = current[1] - previous[1]
    if idle < 0 or total <= 0 or idle > total:
        return None
    return round((total - idle) / total * 100.0, 1)


class WindowsSampler:
    """Collect one API-compatible sample from the Windows host.

    CPU is an interval metric, so the first sample deliberately reports it as
    unknown. Process CPU is the process-lifetime average, matching the remote
    sampler's ``ps`` semantics.
    """

    def __init__(self, disk_path: str | None = None) -> None:
        if not _IS_WINDOWS:
            raise OSError("WindowsSampler is available only on Windows")
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._psapi = ctypes.WinDLL("psapi", use_last_error=True)
        self._configure_api()
        self._disk_path = disk_path or self._system_drive()
        self._previous_cpu: tuple[int, int] | None = None
        self._disk_cache: dict[str, Any] | None = None
        self._next_disk_due = 0.0
        self._hostname = socket.gethostname() or None
        self._os = " ".join(part for part in (platform.system(), platform.release()) if part) or None
        self._kernel = platform.version() or None
        self._arch = platform.machine() or None
        self._cores = os.cpu_count()
        self._model, self._mhz = self._processor_info()
        info = _SYSTEM_INFO()
        self._kernel32.GetSystemInfo(ctypes.byref(info))
        self._page_size = int(info.dwPageSize) or None
        self._cpu_times_supported = self._kernel32.GetActiveProcessorGroupCount() == 1

    def _configure_api(self) -> None:
        kernel = self._kernel32
        kernel.GetSystemTimes.argtypes = (ctypes.POINTER(_FILETIME), ctypes.POINTER(_FILETIME),
                                          ctypes.POINTER(_FILETIME))
        kernel.GetSystemTimes.restype = wintypes.BOOL
        kernel.GetActiveProcessorGroupCount.argtypes = ()
        kernel.GetActiveProcessorGroupCount.restype = wintypes.WORD
        kernel.GlobalMemoryStatusEx.argtypes = (ctypes.POINTER(_MEMORYSTATUSEX),)
        kernel.GlobalMemoryStatusEx.restype = wintypes.BOOL
        kernel.GetTickCount64.argtypes = ()
        kernel.GetTickCount64.restype = ctypes.c_ulonglong
        kernel.GetSystemTimeAsFileTime.argtypes = (ctypes.POINTER(_FILETIME),)
        kernel.GetSystemTimeAsFileTime.restype = None
        kernel.GetSystemInfo.argtypes = (ctypes.POINTER(_SYSTEM_INFO),)
        kernel.GetSystemInfo.restype = None
        kernel.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W))
        kernel.Process32FirstW.restype = wintypes.BOOL
        kernel.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W))
        kernel.Process32NextW.restype = wintypes.BOOL
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.restype = wintypes.BOOL
        kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, ctypes.POINTER(_FILETIME),
                                           ctypes.POINTER(_FILETIME), ctypes.POINTER(_FILETIME),
                                           ctypes.POINTER(_FILETIME))
        kernel.GetProcessTimes.restype = wintypes.BOOL
        callback = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p,
                                      ctypes.POINTER(_ENUM_PAGE_FILE_INFORMATION), wintypes.LPCWSTR)
        self._pagefile_callback_type = callback
        self._psapi.EnumPageFilesW.argtypes = (callback, ctypes.c_void_p)
        self._psapi.EnumPageFilesW.restype = wintypes.BOOL
        self._psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE,
                                                       ctypes.POINTER(_PROCESS_MEMORY_COUNTERS_EX),
                                                       wintypes.DWORD)
        self._psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    @staticmethod
    def _system_drive() -> str:
        drive = os.environ.get("SystemDrive")
        if drive and len(drive) == 2 and drive[1] == ":":
            return drive + "\\"
        drive = os.path.splitdrive(os.getcwd())[0]
        return (drive + "\\") if drive else "\\"

    @staticmethod
    def _processor_info() -> tuple[str | None, int | None]:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                model = winreg.QueryValueEx(key, "ProcessorNameString")[0]
                mhz = winreg.QueryValueEx(key, "~MHz")[0]
        except (OSError, ImportError):
            return None, None
        return (model.strip() if isinstance(model, str) and model.strip() else None,
                mhz if isinstance(mhz, int) and mhz > 0 else None)

    def _system_times(self) -> tuple[int, int] | None:
        # GetSystemTimes reports only the caller's primary processor group;
        # returning that value as whole-host CPU would be misleading.
        if not self._cpu_times_supported:
            return None
        idle, kernel, user = _FILETIME(), _FILETIME(), _FILETIME()
        if not self._kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        idle_value = _filetime_value(idle)
        return idle_value, _filetime_value(kernel) + _filetime_value(user)

    def _memory(self) -> tuple[dict[str, Any], dict[str, Any]]:
        state = _MEMORYSTATUSEX()
        state.dwLength = ctypes.sizeof(state)
        memory = {"percent": None, "used": None, "total": None, "available": None}
        if not self._kernel32.GlobalMemoryStatusEx(ctypes.byref(state)) or not state.ullTotalPhys:
            return memory, {"percent": None, "used": None, "total": None, "enabled": None}
        total = int(state.ullTotalPhys)
        available = min(total, int(state.ullAvailPhys))
        used = total - available
        memory.update(percent=round(used / total * 100.0, 1), used=used, total=total, available=available)
        return memory, self._pagefiles()

    def _pagefiles(self) -> dict[str, Any]:
        values: list[tuple[int, int]] = []

        @self._pagefile_callback_type
        def collect(_context: int, info: ctypes.POINTER(_ENUM_PAGE_FILE_INFORMATION), _name: str) -> bool:
            if info:
                values.append((int(info.contents.TotalSize), int(info.contents.TotalInUse)))
            return True

        if not self._psapi.EnumPageFilesW(collect, None):
            return {"percent": None, "used": None, "total": None, "enabled": None}
        if not values:
            return {"percent": 0.0, "used": 0, "total": 0, "enabled": False}
        if self._page_size is None:
            return {"percent": None, "used": None, "total": None, "enabled": None}
        # EnumPageFiles reports pages, not commit charge.
        total = sum(item[0] for item in values) * self._page_size
        used = sum(item[1] for item in values) * self._page_size
        used = min(total, used)
        return {"percent": round(used / total * 100.0, 1) if total else 0.0,
                "used": used, "total": total, "enabled": total > 0}

    def _disk(self, now: float) -> dict[str, Any]:
        if self._disk_cache is not None and now < self._next_disk_due:
            return dict(self._disk_cache)
        result = {"percent": None, "used": None, "total": None, "available": None,
                  "path": self._disk_path, "device": self._disk_path}
        try:
            usage = shutil.disk_usage(self._disk_path)
        except OSError:
            pass
        else:
            result.update(total=usage.total, used=usage.used, available=usage.free,
                          percent=round(usage.used / usage.total * 100.0, 1) if usage.total else None)
        self._disk_cache = result
        self._next_disk_due = now + 10.0
        return dict(result)

    def _processes(self) -> list[dict[str, Any]] | None:
        snapshot = self._kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if snapshot == _INVALID_HANDLE_VALUE:
            return None
        records: list[dict[str, Any]] = []
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        now = _FILETIME()
        self._kernel32.GetSystemTimeAsFileTime(ctypes.byref(now))
        now_value = _filetime_value(now)
        try:
            present = self._kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while present:
                pid = int(entry.th32ProcessID)
                if pid:
                    records.append(self._process_record(pid, entry.szExeFile, now_value))
                entry.dwSize = ctypes.sizeof(entry)
                present = self._kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            self._kernel32.CloseHandle(snapshot)
        by_cpu = sorted((item for item in records if item["cpu_percent"] is not None),
                        key=lambda item: (-item["cpu_percent"], item["pid"]))[:5]
        by_memory = sorted((item for item in records if item["memory_bytes"] is not None),
                           key=lambda item: (-item["memory_bytes"], item["pid"]))[:5]
        chosen = {item["pid"]: item for item in by_cpu + by_memory}
        return sorted(chosen.values(), key=lambda item: item["pid"])

    def _process_record(self, pid: int, name: str, now: int) -> dict[str, Any]:
        record = {"pid": pid, "name": name or "unknown", "cpu_percent": None, "memory_bytes": None}
        handle = self._kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION | _PROCESS_VM_READ, False, pid)
        if not handle:
            # Protected processes commonly reject VM_READ but still permit
            # their lifetime CPU counters to be queried.
            handle = self._kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return record
        try:
            created, exited, kernel, user = _FILETIME(), _FILETIME(), _FILETIME(), _FILETIME()
            if self._kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                              ctypes.byref(kernel), ctypes.byref(user)):
                lifetime = now - _filetime_value(created)
                if lifetime > 0:
                    cpu_time = _filetime_value(kernel) + _filetime_value(user)
                    record["cpu_percent"] = round(cpu_time / lifetime * 100.0, 1)
            counters = _PROCESS_MEMORY_COUNTERS_EX()
            counters.cb = ctypes.sizeof(counters)
            if self._psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                record["memory_bytes"] = int(counters.WorkingSetSize)
        finally:
            self._kernel32.CloseHandle(handle)
        return record

    def sample(self) -> dict[str, Any]:
        """Collect a best-effort JSON-safe snapshot without starting a process."""
        received = time.time()
        monotonic = time.monotonic()
        current_cpu = self._system_times()
        cpu_percent = _cpu_percent(self._previous_cpu, current_cpu)
        self._previous_cpu = current_cpu
        memory, swap = self._memory()
        return {
            "ts": round(received * 1000),
            "cpu": {"percent": cpu_percent, "cores": self._cores, "mhz": self._mhz,
                    "model": self._model, "iowait": None, "steal": None},
            "memory": memory, "swap": swap, "disk": self._disk(monotonic),
            "processes": self._processes(), "traffic": None,
            "host": {"hostname": self._hostname, "os": self._os, "kernel": self._kernel,
                     "arch": self._arch, "uptime": self._kernel32.GetTickCount64() / 1000.0,
                     "load": None},
        }
