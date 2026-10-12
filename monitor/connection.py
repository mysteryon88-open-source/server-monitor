"""One native OpenSSH process, bounded framed input and automatic recovery."""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Iterator, TextIO

from .config import Config
from .metrics import MetricCalculator, build_probe, parse_frame
from .state import MonitorState


LOG = logging.getLogger(__name__)


def build_ssh_command(config: Config, executable: str, log_path: Path) -> list[str]:
    command = [
        executable, '-T', '-E', str(log_path),
        '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=5',
        '-o', 'ServerAliveCountMax=2', '-o', 'StrictHostKeyChecking=ask',
        '-o', 'ForwardAgent=no', '-o', 'ClearAllForwardings=yes',
        '-o', 'PermitLocalCommand=no', '-o', 'LogLevel=ERROR',
        '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
        '-o', 'RemoteCommand=none',
        # These config counterparts to CLI behavior arrived in OpenSSH 8.7.
        # Older Windows clients must ignore only these known newer directives.
        '-o', 'IgnoreUnknown=StdinNull,SessionType,ForkAfterAuthentication',
        '-o', 'StdinNull=no', '-o', 'SessionType=default',
        '-o', 'ForkAfterAuthentication=no',
        '-o', 'BatchMode=' + ('yes' if config.batch_mode else 'no'),
    ]
    if config.ssh_config:
        command.extend(['-F', str(config.ssh_config)])
    if config.jump:
        command.extend(['-J', config.jump])
    # The login shell may be csh/tcsh. The probe sets its own locale in sh.
    command.extend([config.alias, 'sh -s'])
    return command


def iter_frames(stream: TextIO) -> Iterator[str]:
    parts: list[str] | None = None
    size = 0
    while True:
        line = stream.readline(65537)
        if not line:
            return
        if len(line) > 65536:
            raise ValueError('SSH output line exceeds the 64 KiB limit.')
        marker = line.rstrip('\r\n')
        if marker == '__SM_BEGIN__':
            parts, size = [], 0
        elif marker == '__SM_END__':
            if parts is not None:
                yield ''.join(parts)
            parts, size = None, 0
        elif parts is not None:
            size += len(line)
            if size > 262144:
                raise ValueError('SSH sample exceeds the 256 KiB limit.')
            parts.append(line)


def write_probe_script(stream: TextIO, script: str) -> None:
    """Send exact UTF-8/LF bytes, bypassing Windows TextIOWrapper CRLF conversion."""
    stream.buffer.write(script.encode('utf-8'))
    stream.buffer.flush()


def describe_ssh_error(detail: str) -> str:
    """Map SSH errors to help without reflecting arbitrary remote strings to UI."""
    lower = detail.lower()
    if 'permission denied' in lower or 'authentication failed' in lower:
        return 'SSH authentication failed. Check the user, key or ssh-agent. Enter passwords in the launch window.'
    if 'host key verification failed' in lower or 'remote host identification has changed' in lower:
        return 'Check the server key and known_hosts using regular ssh. Verify the old key before removing it.'
    if 'could not resolve hostname' in lower or 'bad configuration option' in lower:
        return 'Check the SSH alias and Windows OpenSSH config. Details are in logs/ssh-*.log.'
    if 'connection refused' in lower:
        return 'The server refused the SSH connection. Check the address, port and sshd availability.'
    if 'timed out' in lower or 'no route to host' in lower or 'network is unreachable' in lower:
        return 'The SSH server is unreachable. Check the network, VPN and connection settings.'
    if 'linux' in lower or 'proc' in lower or 'awk' in lower:
        return 'The collector requires Linux with /proc, sh, awk and df. Check the launch window message.'
    return 'The SSH connection ended. Check the launch window and logs/ssh-*.log; reconnecting.'


class SSHMonitor:
    def __init__(self, config: Config, state: MonitorState, executable: str, *,
                 authentication_lock=None, log_path: Path | None = None,
                 shutdown_event: threading.Event | None = None):
        self.config = config
        self.state = state
        self.executable = executable
        self._stop = threading.Event()
        self._shutdown = shutdown_event if shutdown_event is not None else threading.Event()
        self._reconnect = threading.Event()
        self._process_lock = threading.Lock()
        self._authentication_lock = authentication_lock if authentication_lock is not None else threading.Lock()
        self._process: subprocess.Popen | None = None
        self._thread = threading.Thread(target=self._run, name='ssh-monitor', daemon=True)
        self._log_path = log_path if log_path is not None else config.base_dir / 'logs' / 'ssh.log'

    def start(self):
        self._thread.start()

    def reconnect(self):
        self.state.set_status('reconnecting', 'Reconnecting. Check the launch window if a password is needed.')
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
        self.state.set_status('stopped', 'Monitoring stopped.')

    def _terminate(self):
        with self._process_lock:
            process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def _error_detail(self) -> str:
        try:
            with self._log_path.open('rb') as source:
                source.seek(0, os.SEEK_END)
                source.seek(max(0, source.tell() - 8192))
                return source.read().decode('utf-8', errors='replace')
        except OSError:
            return ''

    def _prepare_log(self):
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        # One small log per connection, rather than indefinite disk growth.
        self._log_path.write_text('', encoding='utf-8')
        if os.name != 'nt':
            self._log_path.chmod(0o600)

    def _run(self):
        delay = 2
        failures = 0
        while not self._stop.is_set() and not self._shutdown.is_set():
            self._reconnect.clear()
            self.state.begin_session()
            self.state.set_status('connecting' if self.state.snapshot()['latest'] is None else 'reconnecting',
                                  'Connecting through SSH. Password or host key prompts appear in the launch window.')
            success = False
            try:
                success = self._session()
            except Exception:
                LOG.exception('SSH session failed')
                self.state.set_status('error', 'Could not start SSH. Check logs/monitor.log and the launch window.')
            if self._stop.is_set() or self._shutdown.is_set():
                return
            if self._reconnect.is_set():
                failures = 0
                delay = 2
                continue
            failures = 0 if success else failures + 1
            if failures >= 3:
                self.state.set_status('error', 'Three connection attempts failed. Click Reconnect to try again.')
                while not self._reconnect.wait(0.2):
                    if self._stop.is_set() or self._shutdown.is_set():
                        return
                failures = 0
                delay = 2
                continue
            delay = 2 if success else min(delay, 30)
            # Wake early for manual reconnect; every wait remains cancellable.
            if self._reconnect.wait(delay):
                failures = 0
                delay = 2
            else:
                delay = min(delay * 2, 30)

    def _session(self) -> bool:
        # Native SSH owns interactive console input. Only one authentication
        # may prompt at a time; connected collectors continue independently.
        with ExitStack() as authentication:
            while not self._stop.is_set() and not self._shutdown.is_set() and not self._reconnect.is_set():
                if self._authentication_lock.acquire(timeout=0.2):
                    break
            else:
                return False
            authentication.callback(self._authentication_lock.release)
            if self._stop.is_set() or self._shutdown.is_set() or self._reconnect.is_set():
                return False
            print('\nSSH: ' + self.config.alias, flush=True)
            return self._collect_session(authentication)

    def _collect_session(self, authentication: ExitStack) -> bool:
        self._prepare_log()
        command = build_ssh_command(self.config, self.executable, self._log_path)
        events: queue.Queue[tuple[str, str | None]] = queue.Queue(maxsize=8)
        cancelled = threading.Event()
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=None, text=True, encoding='utf-8', errors='replace',
                                   bufsize=1, shell=False)
        with self._process_lock:
            self._process = process

        def emit(kind: str, value: str | None = None):
            while not cancelled.is_set():
                try:
                    events.put((kind, value), timeout=0.2)
                    return
                except queue.Full:
                    continue

        def read_output():
            try:
                for frame in iter_frames(process.stdout):
                    if cancelled.is_set():
                        return
                    emit('frame', frame)
            except (OSError, ValueError) as exc:
                emit('error', str(exc))
            finally:
                emit('eof')

        def send_probe():
            try:
                write_probe_script(process.stdin, build_probe(self.config.interval, self.config.disk_path))
                process.stdin.close()
            except (OSError, ValueError):
                # Authentication/connection errors are reported by the reader.
                pass

        reader = writer = None
        calculator = MetricCalculator()
        last_frame = time.monotonic()
        received = False
        reason = ''
        bad_frames = 0
        try:
            reader = threading.Thread(target=read_output, name='ssh-reader', daemon=True)
            writer = threading.Thread(target=send_probe, name='ssh-writer', daemon=True)
            reader.start()
            writer.start()
            while not self._stop.is_set() and not self._reconnect.is_set():
                try:
                    kind, value = events.get(timeout=0.25)
                except queue.Empty:
                    # Initial auth may be interactive. Never loop forever on a stuck probe.
                    limit = max(20, self.config.interval * 4) if received else 180
                    if time.monotonic() - last_frame > limit:
                        reason = ('Data stopped arriving; restoring the SSH connection.' if received else
                                  'No data. Check the password, host key confirmation and Linux access in the launch window.')
                        break
                    continue
                if kind == 'eof':
                    break
                if kind == 'error':
                    LOG.warning('Invalid SSH stream: %s', value)
                    reason = 'SSH returned invalid data. Check Linux and the user\'s shell.'
                    break
                try:
                    raw = parse_frame(value or '')
                    if raw.get('cpu') is None and raw.get('meminfo', {}).get('MemTotal', 0) <= 0:
                        raise ValueError('Frame does not contain CPU or RAM counters.')
                    sample = calculator.update(raw, timestamp=time.time())
                except (ValueError, KeyError, TypeError, OverflowError):
                    bad_frames += 1
                    LOG.warning('Invalid metric frame (%d)', bad_frames, exc_info=True)
                    if bad_frames >= 3:
                        reason = 'Could not read system metrics. Check /proc and Linux commands.'
                        break
                    continue
                bad_frames = 0
                self.state.record(sample)
                authentication.close()
                received = True
                last_frame = time.monotonic()
        finally:
            cancelled.set()
            self._terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            # Wait for the writer before closing its stream from another thread.
            if writer is not None and writer.ident is not None:
                writer.join(timeout=1)
            if reader is not None and reader.ident is not None:
                reader.join(timeout=1)
            if process.stdout:
                process.stdout.close()
            if (process.stdin and not process.stdin.closed
                    and (writer is None or not writer.is_alive())):
                process.stdin.close()
            with self._process_lock:
                if self._process is process:
                    self._process = None
        if not self._stop.is_set() and not self._reconnect.is_set():
            self.state.set_status('reconnecting', reason or describe_ssh_error(self._error_detail()))
        return received
