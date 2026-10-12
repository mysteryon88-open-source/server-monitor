"""WindowsSampler arithmetic and platform smoke checks."""

import ctypes
import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from monitor.windows import (_ENUM_PAGE_FILE_INFORMATION, _FILETIME,
                             _PROCESSENTRY32W, _PROCESS_MEMORY_COUNTERS_EX,
                             WindowsSampler, _cpu_percent)


class WindowsSamplerTests(unittest.TestCase):
    def test_cpu_delta_arithmetic_rejects_invalid_intervals(self):
        self.assertEqual(_cpu_percent((100, 1_000), (130, 1_200)), 85.0)
        for previous, current in (((100, 1_000), (90, 1_100)),
                                  ((100, 1_000), (110, 1_000)),
                                  (None, (100, 1_000))):
            with self.subTest(previous=previous, current=current):
                self.assertIsNone(_cpu_percent(previous, current))

    def test_pagefiles_distinguish_disabled_from_api_failure(self):
        self.assertEqual(ctypes.sizeof(_ENUM_PAGE_FILE_INFORMATION),
                         8 + 3 * ctypes.sizeof(ctypes.c_size_t))
        sampler = object.__new__(WindowsSampler)
        sampler._pagefile_callback_type = lambda callback: callback
        sampler._page_size = 4096

        class PageFiles:
            def __init__(self, succeeds):
                self.succeeds = succeeds

            def EnumPageFilesW(self, _callback, _context):
                return self.succeeds

        sampler._psapi = PageFiles(False)
        self.assertEqual(sampler._pagefiles(), {
            "percent": None, "used": None, "total": None, "enabled": None,
        })
        sampler._psapi = PageFiles(True)
        self.assertEqual(sampler._pagefiles(), {
            "percent": 0.0, "used": 0, "total": 0, "enabled": False,
        })

    def test_cpu_is_unknown_when_windows_reports_multiple_processor_groups(self):
        sampler = object.__new__(WindowsSampler)
        sampler._cpu_times_supported = False
        sampler._kernel32 = SimpleNamespace(GetSystemTimes=unittest.TestCase.fail)
        self.assertIsNone(sampler._system_times())

    def test_disk_is_cached_for_ten_seconds(self):
        sampler = object.__new__(WindowsSampler)
        sampler._disk_path = "C:\\"
        sampler._disk_cache = None
        sampler._next_disk_due = 0.0
        with mock.patch("monitor.windows.shutil.disk_usage", side_effect=(
                SimpleNamespace(total=100, used=20, free=80),
                SimpleNamespace(total=100, used=30, free=70))) as usage:
            self.assertEqual(sampler._disk(10)["used"], 20)
            self.assertEqual(sampler._disk(19.9)["used"], 20)
            self.assertEqual(sampler._disk(20)["used"], 30)
        self.assertEqual(usage.call_count, 2)

    def test_process_union_is_bounded_and_snapshot_is_closed(self):
        sampler = object.__new__(WindowsSampler)

        class Kernel:
            rows = [(pid, f"p{pid}.exe") for pid in range(1, 7)]

            def __init__(self):
                self.index = 0
                self.closed = []

            def CreateToolhelp32Snapshot(self, _flags, _pid):
                return 99

            def GetSystemTimeAsFileTime(self, target):
                value = ctypes.cast(target, ctypes.POINTER(_FILETIME)).contents
                value.dwLowDateTime = 1

            def _write(self, target):
                entry = ctypes.cast(target, ctypes.POINTER(_PROCESSENTRY32W)).contents
                entry.th32ProcessID, entry.szExeFile = self.rows[self.index]

            def Process32FirstW(self, _snapshot, target):
                self.index = 0
                self._write(target)
                return True

            def Process32NextW(self, _snapshot, target):
                self.index += 1
                if self.index == len(self.rows):
                    return False
                self._write(target)
                return True

            def CloseHandle(self, handle):
                self.closed.append(handle)

        kernel = Kernel()
        sampler._kernel32 = kernel
        records = {
            pid: {"pid": pid, "name": f"p{pid}.exe", "cpu_percent": 7 - pid,
                  "memory_bytes": 100 if pid == 1 else pid * 100}
            for pid in range(1, 7)
        }
        sampler._process_record = lambda pid, _name, _now: records[pid]
        self.assertEqual([row["pid"] for row in sampler._processes()], [1, 2, 3, 4, 5, 6])
        self.assertEqual(kernel.closed, [99])

    def test_process_handle_is_closed_after_sampling(self):
        sampler = object.__new__(WindowsSampler)

        def set_time(target, value):
            result = ctypes.cast(target, ctypes.POINTER(_FILETIME)).contents
            result.dwLowDateTime = value
            result.dwHighDateTime = 0

        class Kernel:
            def __init__(self):
                self.closed = []

            def OpenProcess(self, _rights, _inherit, _pid):
                return 7

            def GetProcessTimes(self, _handle, created, exited, kernel, user):
                set_time(created, 0)
                set_time(exited, 0)
                set_time(kernel, 120)
                set_time(user, 80)
                return True

            def CloseHandle(self, handle):
                self.closed.append(handle)

        class Psapi:
            def GetProcessMemoryInfo(self, _handle, counters, _size):
                ctypes.cast(counters, ctypes.POINTER(_PROCESS_MEMORY_COUNTERS_EX)).contents.WorkingSetSize = 4321
                return True

        kernel = Kernel()
        sampler._kernel32, sampler._psapi = kernel, Psapi()
        self.assertEqual(sampler._process_record(42, "worker.exe", 1000), {
            "pid": 42, "name": "worker.exe", "cpu_percent": 20.0, "memory_bytes": 4321,
        })
        self.assertEqual(kernel.closed, [7])

    @unittest.skipUnless(os.name == "nt", "requires Windows APIs")
    def test_windows_sample_matches_shared_schema(self):
        sampler = WindowsSampler()
        first = sampler.sample()
        second = sampler.sample()
        self.assertIsNone(first["cpu"]["percent"])
        self.assertIsInstance(second["ts"], int)
        self.assertGreater(second["memory"]["total"], 0)
        self.assertEqual(second["traffic"], None)
        self.assertEqual(second["host"]["load"], None)
        self.assertIn("enabled", second["swap"])
        self.assertLessEqual(len(second["processes"] or []), 10)
        json.dumps(second, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
