#!/usr/bin/env python3
"""Run a local dashboard for SSH servers, WSL distributions and this computer."""

from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import webbrowser


if sys.version_info < (3, 11):
    print('Server Monitor requires Python 3.11 or newer. Use start.cmd on Windows.', file=sys.stderr)
    raise SystemExit(2)

from monitor.config import ConfigError, load_config
from monitor.fleet import MonitorFleet
from monitor.web import create_http_server


BASE_DIR = Path(__file__).resolve().parent


def find_ssh() -> str | None:
    """Use native Windows OpenSSH even when Git's ssh precedes it in PATH."""
    if os.name != 'nt':
        return shutil.which('ssh')
    windows = Path(os.environ.get('SystemRoot', r'C:\Windows'))
    candidates = [windows / 'Sysnative/OpenSSH/ssh.exe', windows / 'System32/OpenSSH/ssh.exe',
                  Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'OpenSSH/ssh.exe',
                  shutil.which('ssh')]
    candidates.extend(Path(folder) / 'ssh.exe' for folder in os.get_exec_path())
    seen = set()
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        key = os.path.normcase(os.path.abspath(candidate))
        if key in seen:
            continue
        seen.add(key)
        try:
            result = subprocess.run([str(candidate), '-V'], stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=10,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode == 0 and b'OpenSSH_for_Windows' in result.stdout + result.stderr:
                # ProxyJump starts another ssh.exe by name. Keep it on the
                # same native client and preserve Sysnative for embedded x86.
                native_dirs = [windows / 'Sysnative/OpenSSH', Path(candidate).parent]
                path = os.environ.get('PATH', '').split(os.pathsep)
                ordered, seen_dirs = [], set()
                for directory in native_dirs + [Path(item) for item in path if item]:
                    key = os.path.normcase(os.path.abspath(directory))
                    if key not in seen_dirs:
                        ordered.append(str(directory))
                        seen_dirs.add(key)
                os.environ['PATH'] = os.pathsep.join(ordered)
                return str(candidate)
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


def _arguments(argv=None):
    parser = argparse.ArgumentParser(description='Local resource dashboard. SSH, WSL and self sources are optional.')
    parser.add_argument('--demo', action='store_true', help='Show explicitly labelled demo data without SSH.')
    parser.add_argument('--no-browser', action='store_true', help='Do not open the browser automatically.')
    parser.add_argument('--check', action='store_true', help='Validate local setup without connecting to the server.')
    parser.add_argument('--env', type=Path, help='Read settings from a specific UTF-8 env file.')
    parser.add_argument('--servers', type=Path, help='Read the server name-to-alias mapping from a JSON file.')
    parser.add_argument('--port', type=int, help='Override the local port for this launch.')
    return parser.parse_args(argv)


def _logging():
    folder = BASE_DIR / 'logs'
    folder.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        folder.chmod(0o700)
    handler = RotatingFileHandler(folder / 'monitor.log', maxBytes=1_000_000, backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)


def main(argv=None) -> int:
    args = _arguments(argv)
    try:
        if args.env is not None and not args.env.is_file():
            raise ConfigError('--env does not point to an existing file.')
        config = load_config(BASE_DIR, args.env, demo=args.demo, port_override=args.port,
                             servers_path=args.servers)
        for relative in ('static/index.html', 'static/app.js', 'static/style.css', 'static/favicon.svg', 'monitor/probe.sh'):
            if not (BASE_DIR / relative).is_file():
                raise ConfigError('Missing ' + relative + '. Extract the complete ZIP before starting.')
        needs_ssh = bool(config.servers) and not config.demo
        ssh = find_ssh() if needs_ssh else None
        if needs_ssh and ssh is None:
            raise ConfigError('OpenSSH Client was not found. Enable it in Windows Optional Features, then run start.cmd again.')
        fleet = MonitorFleet(config, ssh)
    except ConfigError as exc:
        print('Configuration error: ' + str(exc), file=sys.stderr)
        return 2
    if args.check:
        print('Local setup OK. No SSH connection was made.')
        print('Python: ' + sys.version.split()[0])
        print('Mode: ' + ('DEMO' if config.demo else ' / '.join(sorted({state.source.upper() for state in fleet.states.values()}))))
        print('Servers: ' + str(len(fleet.states)))
        for item in fleet.list_servers()['servers']:
            print('  ' + item['name'] + ': ' + item['alias'])
        print('Language: ' + config.language)
        print(f'URL: http://127.0.0.1:{config.port}')
        print('OpenSSH: ' + (ssh or 'not required for these sources'))
        return 0
    try:
        _logging()
    except OSError as exc:
        print('Cannot write logs in this folder. Extract the ZIP to a writable folder. ' + str(exc), file=sys.stderr)
        return 2
    token = secrets.token_urlsafe(32)
    try:
        server = create_http_server(config.port, fleet, BASE_DIR / 'static', token)
    except OSError as exc:
        print(f'Cannot open 127.0.0.1:{config.port}: {exc}', file=sys.stderr)
        print('Close the previous Server Monitor window or change PORT in .env.', file=sys.stderr)
        return 2
    stop = threading.Event()
    def request_stop(signum=None, frame=None):
        stop.set()
    for name in ('SIGINT', 'SIGTERM', 'SIGBREAK'):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), request_stop)
    http_thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.25},
                                   name='local-http', daemon=True)
    http_thread.start()
    print('\nServer Monitor' + (' [DEMO DATA]' if config.demo else ''))
    print(f'Open: http://127.0.0.1:{config.port}')
    print('Keep this window open. Press Ctrl+C and wait for "Server Monitor stopped." Then type Y if CMD asks "Terminate batch job (Y/N)?".')
    if not config.demo:
        for item in fleet.list_servers()['servers']:
            print(item['source'].upper() + ': ' + item['name'] + ' (' + item['alias'] + ')')
        if needs_ssh:
            print('If SSH asks for a password, passphrase or host-key confirmation, use THIS window.')
            print('Your SSH password/key is never read by the application or sent to the browser.')
    print('', flush=True)
    if not args.no_browser:
        try:
            webbrowser.open(f'http://127.0.0.1:{config.port}', new=2)
        except Exception:
            logging.getLogger(__name__).exception('Cannot open browser automatically')
            print('Open the URL above in your browser.')
    try:
        fleet.start()
        while not stop.wait(0.5):
            pass
    finally:
        fleet.stop()
        server.shutdown()
        server.server_close()
        http_thread.join(timeout=3)
        logging.shutdown()
        print('Server Monitor stopped.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
