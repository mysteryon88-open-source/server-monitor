"""Explicit demo-only data. Never used by the real SSH connection path."""

from datetime import datetime, timedelta
import math
import threading
import time

from .state import MonitorState


def demo_sample(timestamp: float, variant: int = 0) -> dict:
    variant %= 3
    phase = (timestamp + variant * 217) % 3600
    gib = 1024 ** 3
    cpu = round(35 + 9 * math.sin(phase / 17) + 5 * math.sin(phase / 3.8)
                + 18 * max(0, math.sin(phase / 51)) ** 12 + variant * 7, 1)
    memory_percent = 65 + 0.6 * math.sin(phase / 31) - variant * 6
    memory_total = round((1.93, 7.75, 15.6)[variant] * gib)
    memory_used = round(memory_total * memory_percent / 100)
    swap_total = 2 * gib
    swap_used = round(swap_total * (0.289 + 0.0004 * math.sin(phase / 40)))
    disk_total = round((24.53, 78.2, 156.4)[variant] * gib)
    disk_percent = (73.7, 48.3, 62.1)[variant]
    disk_used = round(disk_total * disk_percent / 100)
    processes = [
        {'pid': 1026 + variant * 200 + index, 'name': name,
         'cpu_percent': round(cpu * factor, 1),
         'memory_bytes': round(gib * rss * (variant + 1))}
        for index, (name, factor, rss) in enumerate((
            ('python3', .43, .23), ('postgres', .26, .31),
            ('nginx', .14, .08), ('redis-server', .07, .06),
            ('systemd-journal', .02, .02)))
    ]
    traffic = None
    if variant != 2:
        today = datetime.fromtimestamp(timestamp).date()
        interfaces = []
        for name, scale in (('ens3', 1), ('wg0', .12)):
            days = [{'date': (today - timedelta(days=offset)).isoformat(),
                     'rx': round(gib * (1.6 + (6 - offset) * .21) * scale * (variant + 1)),
                     'tx': round(gib * (.72 + (6 - offset) * .16) * scale * (variant + 1))}
                    for offset in range(6, -1, -1)]
            interfaces.append({'name': name, 'days': days,
                               'rx': sum(day['rx'] for day in days),
                               'tx': sum(day['tx'] for day in days)})
        traffic = {'updated_at': round(timestamp // 60 * 60000),
                   'default_interface': 'ens3', 'interfaces': interfaces}
    return {
        'ts': round(timestamp * 1000),
        'cpu': {'percent': cpu, 'cores': (2, 4, 8)[variant], 'mhz': 2590.0,
                'model': 'Virtual CPU', 'iowait': 0.2, 'steal': 0.0},
        'memory': {'percent': round(memory_percent, 1), 'used': memory_used,
                   'total': memory_total, 'available': memory_total - memory_used},
        'swap': {'percent': round(100 * swap_used / swap_total, 1),
                 'used': swap_used, 'total': swap_total, 'enabled': True},
        'disk': {'percent': disk_percent, 'used': disk_used, 'total': disk_total,
                 'available': disk_total - disk_used, 'path': '/', 'device': '/dev/vda1'},
        'processes': processes, 'traffic': traffic,
        'host': {'hostname': ('demo-server', 'demo-database', 'demo-worker')[variant], 'os': 'Ubuntu 24.04 LTS',
                 'kernel': '6.8.0-generic', 'arch': 'x86_64',
                 'uptime': 12 * 86400 + phase, 'load': [0.42, 0.36, 0.31]},
    }


class DemoMonitor:
    def __init__(self, state: MonitorState, variant: int = 0):
        self.state = state
        self.variant = variant
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name='demo-monitor', daemon=True)

    def start(self):
        now = time.time()
        for offset in range(900, 0, -self.state.interval):
            self.state.record(demo_sample(now - offset, self.variant))
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            self.state.record(demo_sample(time.time(), self.variant))
            self._stop.wait(self.state.interval)

    def reconnect(self):
        self.state.begin_session()
        self.state.record(demo_sample(time.time(), self.variant))

    def request_stop(self):
        self._stop.set()

    def stop(self):
        self.request_stop()
        self._thread.join(timeout=3)
        self.state.set_status('stopped', 'Demo stopped.')
