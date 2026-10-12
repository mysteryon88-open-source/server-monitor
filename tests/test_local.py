"""Local and WSL collector checks; WSL smoke testing never starts a stopped distro."""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from monitor.connection import iter_frames
from monitor.config import Config
from monitor.local import LOCAL_MESSAGES, LocalMonitor, _WSL_WRAPPER, _decode_wsl_names, _wsl_executable, discover_wsl
from monitor.state import MonitorState


def eventually(predicate, timeout: float = 8) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.04)
    raise AssertionError("expected state was not reached before timeout")


class WslDiscoveryTests(unittest.TestCase):
    def test_non_windows_does_not_attempt_wsl(self):
        with patch("monitor.local._is_windows", return_value=False), patch("monitor.local.subprocess.run") as run:
            self.assertEqual(discover_wsl(), [])
        run.assert_not_called()

    def test_running_names_decode_utf16_and_stay_bounded(self):
        output = "Ubuntu\r\nDebian\r\nUbuntu\r\n".encode("utf-16")
        result = subprocess.CompletedProcess(["wsl.exe"], 0, output, b"")
        with patch("monitor.local._is_windows", return_value=True), patch("monitor.local._wsl_executable", return_value="wsl.exe"), patch("monitor.local.subprocess.run", return_value=result) as run:
            self.assertEqual(discover_wsl(), ["Ubuntu", "Debian"])
        self.assertEqual(run.call_args.args[0], ["wsl.exe", "--list", "--running", "--quiet"])
        self.assertEqual(run.call_args.kwargs["timeout"], 2)
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_names_decode_bomless_utf16_for_non_ascii_and_utf8(self):
        self.assertEqual(_decode_wsl_names("Montréal\r\nデビアン\r\n".encode("utf-16-le")),
                         ["Montréal", "デビアン"])
        self.assertEqual(_decode_wsl_names("Ubuntu\r\n".encode("utf-8")), ["Ubuntu"])

    def test_discovery_failure_is_diagnostic_and_empty(self):
        with patch("monitor.local._is_windows", return_value=True), patch("monitor.local._wsl_executable", return_value="wsl.exe"), \
             patch("monitor.local.subprocess.run", side_effect=FileNotFoundError("wsl.exe")), \
             self.assertLogs("monitor.local", "WARNING"):
            self.assertEqual(discover_wsl(), [])

    def test_stopped_distro_is_never_started(self):
        config = Config(Path("."), "wsl", interval=1)
        state = MonitorState("Ubuntu", 1)
        monitor = LocalMonitor(config, state, distro="Ubuntu")
        monitor._collect_process = Mock()
        with patch("monitor.local._is_windows", return_value=True), patch("monitor.local.discover_wsl", return_value=[]):
            self.assertFalse(monitor._session())
        monitor._collect_process.assert_not_called()
        self.assertEqual(state.snapshot()["message"], LOCAL_MESSAGES["wsl_stopped"])

    def test_wsl_resolver_prefers_sysnative_before_system32(self):
        with patch("monitor.local._is_windows", return_value=True), \
             patch("monitor.local.os.path.isfile", side_effect=lambda path: "Sysnative" in path):
            self.assertTrue(_wsl_executable().endswith("Sysnative\\wsl.exe"))

    def test_windows_stop_wakes_a_long_sampling_wait(self):
        sample = {"ts": 1, "cpu": {"percent": None}, "processes": None, "traffic": None}

        class Sampler:
            def sample(self):
                return sample

        config = Config(Path("."), "self", interval=60)
        state = MonitorState("self", 60)
        monitor = LocalMonitor(config, state)
        with patch("monitor.local._is_windows", return_value=True), patch("monitor.windows.WindowsSampler", Sampler):
            monitor.start()
            eventually(lambda: state.snapshot()["latest"] is not None)
            started = time.monotonic()
            monitor.stop()
        self.assertLess(time.monotonic() - started, .5)
        self.assertFalse(monitor._thread.is_alive())


@unittest.skipUnless(os.name == "posix" and Path("/proc/stat").exists(), "requires local Linux procfs and sh")
class LinuxLocalMonitorTests(unittest.TestCase):
    def test_wsl_style_reconnect_and_stop_reap_owned_marker_group(self):
        probe = ("printf '__SM_BEGIN__\\ncpu\\t1 0 0 1\\nmeminfo\\tMemTotal: 1 kB\\n"
                 "hostname\\t%s\\n__SM_END__\\n' \"$$\"; while :; do sleep 60; done")
        for action_name in ("reconnect", "request_stop"):
            with self.subTest(action=action_name), tempfile.TemporaryDirectory() as directory:
                config = Config(Path(directory), "wsl", interval=1)
                state = MonitorState("wsl", 1)
                monitor = LocalMonitor(config, state, distro="fixture")
                worker = threading.Thread(
                    target=monitor._collect_process,
                    args=(["sh", "-c", _WSL_WRAPPER, "wrapper-test"],),
                    kwargs={"keep_stdin": True}, daemon=True,
                )
                with patch("monitor.local.build_probe", return_value=probe):
                    worker.start()
                    eventually(lambda: state.snapshot()["latest"] is not None)
                    child = int(state.snapshot()["latest"]["host"]["hostname"])
                    getattr(monitor, action_name)()
                    worker.join(5)
                self.assertFalse(worker.is_alive())
                self.assertIsNone(monitor._process)
                with self.assertRaises(ProcessLookupError):
                    os.kill(child, 0)

    def test_local_linux_probe_records_and_cleans_up_its_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(Path(directory), "self", interval=1, batch_mode=True)
            state = MonitorState("self", 1)
            monitor = LocalMonitor(config, state)
            try:
                monitor.start()
                eventually(lambda: state.snapshot()["latest"] is not None
                           and state.snapshot()["latest"]["memory"]["total"] is not None)
            finally:
                monitor.stop()
            self.assertEqual(state.snapshot()["status"], "stopped")
            self.assertFalse(monitor._thread.is_alive())
            self.assertIsNone(monitor._process)


@unittest.skipUnless(os.name == "nt", "requires Windows WSL")
class RunningWslSmokeTests(unittest.TestCase):
    @staticmethod
    def _linux_distro() -> str | None:
        distros = discover_wsl()
        return next((name for name in distros if not name.casefold().startswith("docker-")),
                    distros[0] if distros else None)

    @staticmethod
    def _wsl() -> str:
        executable = _wsl_executable()
        if not executable:
            raise AssertionError("running WSL was listed but wsl.exe cannot be resolved")
        return executable

    def test_wsl_wrapper_reaps_a_marked_collector_on_parent_eof(self):
        distro = self._linux_distro()
        if distro is None:
            self.skipTest("no running WSL distribution")
        probe = "printf '__SM_BEGIN__\\nmarker\\t%s\\n__SM_END__\\n' \"$$\"; while :; do sleep 60; done"
        process = subprocess.Popen(
            [self._wsl(), "-d", distro, "--exec", "sh", "-c", _WSL_WRAPPER,
             "wrapper-test"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        wire = (probe.rstrip("\n") + "\n__SM_PROBE_END__\n").encode("utf-8")
        process.stdin.buffer.write(wire)
        process.stdin.buffer.flush()
        self.assertNotIn(b"\r", wire, "WSL probe must retain exact UTF-8/LF bytes")
        frames: list[str] = []
        def read_frames():
            for frame in iter_frames(process.stdout):
                frames.append(frame)
        reader = threading.Thread(target=read_frames, daemon=True)
        reader.start()
        try:
            eventually(lambda: bool(frames) or process.poll() is not None, timeout=5)
            if not frames:
                if process.poll() is None:
                    process.stdin.close()
                    process.wait(timeout=3)
                detail = process.stderr.read(4096) if process.stderr else ""
                self.fail("running WSL could not execute the cleanup wrapper: " + detail)
            child = int(next(line.split("\t", 1)[1] for line in frames[0].splitlines()
                             if line.startswith("marker\t")))
            process.stdin.close()
            process.wait(timeout=4)
            check = subprocess.run(
                [self._wsl(), "-d", distro, "--exec", "sh", "-c",
                 "kill -0 \"$1\" 2>/dev/null", "marker-check", str(child)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=2, check=False,
            )
            self.assertNotEqual(check.returncode, 0, "owned WSL process group survived parent EOF")
        finally:
            if process.poll() is None:
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()
                process.kill()
                process.wait(timeout=3)
            reader.join(timeout=1)
            process.stdout.close()
            if process.stderr:
                process.stderr.close()

    def test_first_already_running_wsl_can_be_collected_and_stopped(self):
        distro = self._linux_distro()
        if distro is None:
            self.skipTest("no running WSL distribution")
        with tempfile.TemporaryDirectory() as directory:
            config = Config(Path(directory), "wsl", interval=1, batch_mode=True)
            state = MonitorState(distro, 1)
            monitor = LocalMonitor(config, state, distro=distro)
            try:
                monitor.start()
                eventually(lambda: state.snapshot()["latest"] is not None
                           or state.snapshot()["status"] == "error", timeout=12)
                self.assertIsNotNone(state.snapshot()["latest"], state.snapshot()["message"])
            finally:
                monitor.stop()
            self.assertIsNone(monitor._process)


if __name__ == "__main__":
    unittest.main()
