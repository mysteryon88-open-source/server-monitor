"""One independent state and persistent collector per configured server."""

from dataclasses import replace
import threading

from .config import Config, ConfigError
from .connection import SSHMonitor
from .demo import DemoMonitor
from .state import MonitorState
from .local import LocalMonitor, discover_wsl


class MonitorFleet:
    def __init__(self, config: Config, executable: str | None):
        self.config = config
        self.states = {}
        self.monitors = {}
        self.names = {}
        self._started = []
        self._shutdown = threading.Event()
        authentication_lock = threading.Lock()
        for index, (name, entry) in enumerate(config.servers.items()):
            alias = entry['alias'] if isinstance(entry, dict) else entry
            jump = entry.get('jump') if isinstance(entry, dict) else None
            server_id = str(index)
            state = MonitorState(alias, config.interval, config.demo)
            self.names[server_id] = name
            self.states[server_id] = state
            self.monitors[server_id] = (
                DemoMonitor(state, variant=index) if config.demo else
                SSHMonitor(replace(config, alias=alias, jump=jump), state, executable,
                           authentication_lock=authentication_lock,
                           shutdown_event=self._shutdown,
                           log_path=config.base_dir / 'logs' / f'ssh-{index + 1}.log')
            )
        if config.monitor_self and not config.demo:
            self._add_local('self', 'self', 'self', None)
        if config.wsl_autodetect and not config.demo:
            distros = discover_wsl()
            if not distros:
                print('WSL: no running distributions found. Start a distribution and restart the monitor.')
            for index, distro in enumerate(distros):
                self._add_local(f'wsl-{index}', 'WSL: ' + distro, 'wsl', distro)
        if not self.states:
            raise ConfigError('No monitoring sources: configure SSH servers, enable MONITOR_SELF, or start a WSL distribution with WSL_AUTODETECT enabled.')

    def _add_local(self, server_id, name, source, distro):
        state = MonitorState(distro or 'self', self.config.interval, source=source)
        self.names[server_id] = name
        self.states[server_id] = state
        self.monitors[server_id] = LocalMonitor(self.config, state, distro=distro,
                                              shutdown_event=self._shutdown)

    def start(self):
        for monitor in self.monitors.values():
            monitor.start()
            self._started.append(monitor)

    def stop(self):
        self._shutdown.set()
        for monitor in self._started:
            monitor.request_stop()
        for monitor in self._started:
            monitor.stop()

    def list_servers(self) -> dict:
        return {
            'language': self.config.language,
            'default_server': next(iter(self.states)),
            'servers': [
                {'id': server_id, 'name': self.names[server_id], 'alias': state.alias,
                 'status': state.status(), 'demo': state.demo, 'source': state.source}
                for server_id, state in self.states.items()
            ],
        }

    def snapshot(self, server_id: str) -> dict:
        return {**self.states[server_id].snapshot(), 'server_id': server_id,
                'name': self.names[server_id], **self.list_servers()}

    def reconnect(self, server_id: str):
        self.monitors[server_id].reconnect()
