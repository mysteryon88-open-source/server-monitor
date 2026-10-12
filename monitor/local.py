"""Optional local and already-running WSL collectors.

This transport deliberately shares the Linux probe and metric parser with SSH.
It never invokes ``wsl --shutdown`` or ``wsl --terminate``: the only process it
stops is the ``wsl.exe`` (or local ``sh``) collector it started itself.
"""

from __future__ import annotations

import logging
import os
import queue
import signal
import shutil
import subprocess
import sys
import threading
import time
from typing import TextIO

from .connection import iter_frames, write_probe_script
from .metrics import MetricCalculator, build_probe, parse_frame


LOG = logging.getLogger(__name__)
_WSL_LIST_TIMEOUT = 2
# The probe arrives over stdin followed by a fixed sentinel. Stdin then stays
# open as a parent-liveness pipe. Closing our stdout after spawning the probe
# lets reader EOF track the real collector.
_WSL_WRAPPER = r'''sm_probe=
sm_complete=0
while IFS= read -r sm_line; do
    if [ "$sm_line" = '__SM_PROBE_END__' ]; then sm_complete=1; break; fi
    sm_probe="${sm_probe}${sm_line}
"
done
[ "$sm_complete" -eq 1 ] || exit 0
sm_child=
sm_cleanup() {
    [ -n "$sm_child" ] || return 0
    kill -TERM "-$sm_child" 2>/dev/null || true
    sm_wait=0
    while kill -0 "-$sm_child" 2>/dev/null && [ "$sm_wait" -lt 20 ]; do
        sleep 0.1 || break
        sm_wait=$((sm_wait + 1))
    done
    kill -KILL "-$sm_child" 2>/dev/null || true
    wait "$sm_child" 2>/dev/null || true
    sm_child=
}
trap 'sm_cleanup; exit 0' HUP INT TERM
if ! command -v setsid >/dev/null 2>&1; then
    printf '%s\n' 'Server Monitor: WSL needs setsid for safe collector cleanup.' >&2
    exit 127
fi
setsid sh -c "$sm_probe" </dev/null &
sm_child=$!
# The child inherited stdout. Closing ours makes its EOF observable by Python.
exec 1>&-
while IFS= read -r sm_input; do :; done
sm_cleanup
'''
LOCAL_MESSAGES = {
    "connecting": "Collecting metrics from this computer.",
    "connecting_wsl": "Collecting metrics from running WSL.",
    "reconnecting": "Restarting local metric collection.",
    "wsl_stopped": "The selected WSL distribution is not running. Start it and click Reconnect.",
    "wsl_missing": "wsl.exe was not found. Check the WSL installation in Windows.",
    "unsupported_wsl": "WSL is available only when the monitor runs on Windows.",
    "unsupported_platform": "Local monitoring supports Windows and Linux only.",
    "start_failed": "Could not start the local collector.",
    "bad_stream": "The local collector returned invalid data.",
    "bad_metrics": "Could not read local system metrics.",
    "stalled": "The local collector stopped sending data.",
    "ended": "The local collector exited.",
    "windows_retry": "Could not read Windows metrics; retrying.",
    "three_failures": "Three local collection attempts failed. Click Reconnect to try again.",
    "stopped": "Local monitoring stopped.",
}


def _is_windows() -> bool:
    return os.name == "nt"


def _wsl_executable() -> str | None:
    """Avoid WOW64 System32 redirection when launcher chose x86 Python."""
    if not _is_windows():
        return None
    root = os.environ.get("WINDIR", r"C:\Windows")
    for directory in ("Sysnative", "System32"):
        candidate = os.path.join(root, directory, "wsl.exe")
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("wsl.exe")


def _decode_wsl_names(data: bytes) -> list[str]:
    """Decode either WSL's UTF-16 output or the UTF-8 output of newer builds."""
    if not data:
        return []
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = data.decode("utf-16", errors="replace")
    elif (b"\n\0" in data or b"\r\0\n\0" in data
          or data.count(b"\0") > len(data) // 4):
        # ``wsl.exe`` historically writes UTF-16LE without a BOM when stdout
        # is redirected.  Distribution names are one item per line.
        text = data.decode("utf-16-le", errors="replace")
    else:
        text = data.decode("utf-8", errors="replace")
    result: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        name = line.strip().removesuffix("\0").strip()
        key = name.casefold()
        if (name and len(name) <= 255 and not any(ord(character) < 32 for character in name)
                and key not in seen):
            result.append(name)
            seen.add(key)
    return result


def discover_wsl() -> list[str]:
    """Return WSL distributions that are already running, without starting any."""
    if not _is_windows():
        return []
    executable = _wsl_executable()
    if not executable:
        LOG.warning("Cannot list running WSL distributions: wsl.exe was not found")
        return []
    try:
        completed = subprocess.run(
            [executable, "--list", "--running", "--quiet"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=_WSL_LIST_TIMEOUT, check=False, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        LOG.warning("Cannot list running WSL distributions: %s", exc)
        return []
    if completed.returncode:
        detail = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
        LOG.warning("Cannot list running WSL distributions (exit %s)%s", completed.returncode,
                    ": " + detail[:200] if detail else "")
        return []
    return _decode_wsl_names(completed.stdout or b"")


class LocalMonitor:
    """One local Windows, local Linux, or running-WSL collector."""

    def __init__(self, config, state, *, distro: str | None = None,
                 shutdown_event: threading.Event | None = None):
        self.config = config
        self.state = state
        self.distro = distro
        self._stop = threading.Event()
        self._shutdown = shutdown_event if shutdown_event is not None else threading.Event()
        self._reconnect = threading.Event()
        self._process_lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._wsl_pipe_process: subprocess.Popen | None = None
        self._wsl_probe_sent = threading.Event()
        self._thread = threading.Thread(target=self._run, name="local-monitor", daemon=True)

    def start(self):
        self._thread.start()

    def reconnect(self):
        self.state.set_status("reconnecting", LOCAL_MESSAGES["reconnecting"])
        self._reconnect.set()
        self._terminate()

    def request_stop(self):
        self._stop.set()
        self._reconnect.set()
        self._terminate()

    def stop(self):
        self.request_stop()
        if self._thread.ident is not None:
            self._thread.join(timeout=5)
        self.state.set_status("stopped", LOCAL_MESSAGES["stopped"])

    def _stopped(self) -> bool:
        return self._stop.is_set() or self._shutdown.is_set()

    def _running_distro(self) -> bool:
        if self.distro is None:
            return True
        return self.distro.casefold() in {name.casefold() for name in discover_wsl()}

    def _connecting_message(self) -> str:
        return LOCAL_MESSAGES["connecting_wsl" if self.distro is not None else "connecting"]

    def _run(self):
        delay = 2
        failures = 0
        while not self._stopped():
            self._reconnect.clear()
            self.state.begin_session()
            self.state.set_status("connecting" if self.state.snapshot()["latest"] is None else "reconnecting",
                                  self._connecting_message())
            try:
                success = self._session()
            except Exception:
                LOG.exception("Local collector session failed")
                success = False
                self.state.set_status("error", LOCAL_MESSAGES["start_failed"])
            if self._stopped():
                return
            if self._reconnect.is_set():
                failures, delay = 0, 2
                continue
            failures = 0 if success else failures + 1
            if failures >= 3:
                self.state.set_status("error", LOCAL_MESSAGES["three_failures"])
                while not self._reconnect.wait(0.2):
                    if self._stopped():
                        return
                failures, delay = 0, 2
                continue
            if self._reconnect.wait(delay):
                failures, delay = 0, 2
            else:
                delay = min(delay * 2, 30)

    def _session(self) -> bool:
        if self.distro is not None:
            if not _is_windows():
                self.state.set_status("error", LOCAL_MESSAGES["unsupported_wsl"])
                return False
            if not self._running_distro():
                self.state.set_status("error", LOCAL_MESSAGES["wsl_stopped"])
                return False
            if self._stopped():
                return False
            executable = _wsl_executable()
            if not executable:
                self.state.set_status("error", LOCAL_MESSAGES["wsl_missing"])
                return False
            return self._collect_process(
                [executable, "-d", self.distro, "--exec", "sh", "-c", _WSL_WRAPPER,
                 "server-monitor-wsl"],
                keep_stdin=True,
            )
        if _is_windows():
            return self._collect_windows()
        if sys.platform.startswith("linux"):
            return self._collect_process(["sh", "-s"])
        self.state.set_status("error", LOCAL_MESSAGES["unsupported_platform"])
        return False

    def _collect_windows(self) -> bool:
        from .windows import WindowsSampler

        sampler = WindowsSampler()
        received = False
        while not self._stopped() and not self._reconnect.is_set():
            try:
                self.state.record(sampler.sample())
                received = True
            except (OSError, ValueError, OverflowError):
                LOG.exception("Windows sample failed")
                self.state.set_status("reconnecting", LOCAL_MESSAGES["windows_retry"])
                return received
            self._reconnect.wait(self.config.interval)
        return received

    def _terminate(self):
        with self._process_lock:
            process = self._process
            graceful_wsl = self._wsl_pipe_process is process
        if process is None or process.poll() is not None:
            return
        try:
            if graceful_wsl:
                # EOF is the WSL wrapper's ownership signal; it terminates
                # and reaps its private Linux process group before wsl.exe.
                if self._wsl_probe_sent.is_set() and process.stdin and not process.stdin.closed:
                    try:
                        process.stdin.close()
                        return
                    except OSError:
                        # WSL may close its stdin handle while exiting. A
                        # broken pipe means the watchdog is already gone.
                        pass
                # If launch is still writing the script, interrupt wsl.exe;
                # the wrapper has not received its end marker and cannot spawn it.
                process.terminate()
                return
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except (OSError, ProcessLookupError):
            pass

    def _kill(self, process: subprocess.Popen):
        if process.poll() is not None:
            return
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except (OSError, ProcessLookupError):
            pass

    def _collect_process(self, command: list[str], *, keep_stdin: bool = False) -> bool:
        events: queue.Queue[tuple[str, str | None]] = queue.Queue(maxsize=8)
        cancelled = threading.Event()
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
            text=True, encoding="utf-8", errors="replace", bufsize=1, shell=False,
            start_new_session=os.name != "nt",
        )
        with self._process_lock:
            self._process = process
            self._wsl_pipe_process = process if keep_stdin else None
            self._wsl_probe_sent.clear()

        def emit(kind: str, value: str | None = None):
            while not cancelled.is_set():
                try:
                    events.put((kind, value), timeout=0.2)
                    return
                except queue.Full:
                    continue

        def read_output(stream: TextIO):
            try:
                for frame in iter_frames(stream):
                    if cancelled.is_set():
                        return
                    emit("frame", frame)
            except (OSError, ValueError) as exc:
                emit("error", str(exc))
            finally:
                emit("eof")

        def send_probe():
            try:
                script = build_probe(self.config.interval, self.config.disk_path)
                write_probe_script(process.stdin, script)
                if keep_stdin:
                    process.stdin.buffer.write(b'\n__SM_PROBE_END__\n')
                    process.stdin.buffer.flush()
                    self._wsl_probe_sent.set()
                else:
                    process.stdin.close()
            except (OSError, ValueError):
                # The reader reports the actual process failure when available.
                pass

        reader = writer = None
        calculator = MetricCalculator()
        received = False
        bad_frames = 0
        last_frame = time.monotonic()
        reason = ""
        try:
            reader = threading.Thread(target=read_output, args=(process.stdout,), name="local-reader", daemon=True)
            writer = threading.Thread(target=send_probe, name="local-writer", daemon=True)
            reader.start()
            writer.start()
            while not self._stopped() and not self._reconnect.is_set():
                try:
                    kind, value = events.get(timeout=0.25)
                except queue.Empty:
                    limit = max(20, self.config.interval * 4) if received else 20
                    if time.monotonic() - last_frame > limit:
                        reason = LOCAL_MESSAGES["stalled"]
                        break
                    continue
                if kind == "eof":
                    reason = LOCAL_MESSAGES["ended"]
                    break
                if kind == "error":
                    LOG.warning("Invalid local collector stream: %s", value)
                    reason = LOCAL_MESSAGES["bad_stream"]
                    break
                try:
                    raw = parse_frame(value or "")
                    if raw.get("cpu") is None and raw.get("meminfo", {}).get("MemTotal", 0) <= 0:
                        raise ValueError("Frame does not contain CPU or RAM counters.")
                    self.state.record(calculator.update(raw, timestamp=time.time()))
                except (ValueError, KeyError, TypeError, OverflowError):
                    bad_frames += 1
                    LOG.warning("Invalid local metric frame (%d)", bad_frames, exc_info=True)
                    if bad_frames >= 3:
                        reason = LOCAL_MESSAGES["bad_metrics"]
                        break
                    continue
                bad_frames = 0
                received = True
                last_frame = time.monotonic()
        finally:
            cancelled.set()
            self._terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._kill(process)
                process.wait(timeout=3)
            if writer is not None and writer.ident is not None:
                writer.join(timeout=1)
            if reader is not None and reader.ident is not None:
                reader.join(timeout=1)
            if process.stdout:
                process.stdout.close()
            if (process.stdin and not process.stdin.closed
                    and (writer is None or not writer.is_alive())):
                try:
                    process.stdin.close()
                except OSError:
                    pass
            with self._process_lock:
                if self._process is process:
                    self._process = None
                if self._wsl_pipe_process is process:
                    self._wsl_pipe_process = None
        if not self._stopped() and not self._reconnect.is_set():
            self.state.set_status("reconnecting", reason or LOCAL_MESSAGES["reconnecting"])
        return received
