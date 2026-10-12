"""POSIX process integration using an explicitly local shell transport fixture.

This exercises the production process/stream/reconnect path and the real Linux
probe. It does NOT claim to test SSH authentication or a Windows console.
"""

import os
import tempfile
import time
import unittest
from pathlib import Path

from monitor.config import Config
from monitor.connection import SSHMonitor
from monitor.fleet import MonitorFleet
from monitor.state import MonitorState


def eventually(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.04)
    raise AssertionError('Expected state was not reached before timeout.')


@unittest.skipUnless(os.name == 'posix' and Path('/proc/stat').exists(), 'Requires local Linux procfs and sh')
class ProcessLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.fixture = self.root / 'local-shell-fixture'
        self.state = MonitorState('fixture', 1)
        self.monitor = SSHMonitor(Config(self.root, 'fixture', interval=1, batch_mode=True),
                                  self.state, str(self.fixture))

    def tearDown(self):
        if self.monitor._thread.ident is not None:
            self.monitor.stop()
        self.directory.cleanup()

    def write_fixture(self, script):
        self.fixture.write_text(script, encoding='utf-8')
        self.fixture.chmod(0o700)

    def test_real_probe_stream_reconnect_and_stop(self):
        self.write_fixture('#!/bin/sh\nexec /bin/sh -s\n')
        self.monitor.start()
        eventually(lambda: self.state.snapshot()['latest'] is not None
                   and self.state.snapshot()['latest']['cpu']['percent'] is not None)
        first = self.state.snapshot()
        self.assertGreater(first['latest']['memory']['total'], 0)
        self.assertIsNotNone(first['latest']['disk']['percent'])
        old_session = first['connected_since']
        self.monitor.reconnect()
        eventually(lambda: self.state.snapshot()['status'] == 'connected'
                   and (self.state.snapshot()['connected_since'] or 0) > old_session)
        second = self.state.snapshot()
        self.assertGreater(len(second['history']), len(first['history']))
        self.monitor.stop()
        self.assertEqual(self.state.snapshot()['status'], 'stopped')
        self.assertFalse(self.monitor._thread.is_alive())

    def test_two_collectors_keep_separate_history_and_reconnect_only_one(self):
        self.write_fixture('#!/bin/sh\nexec /bin/sh -s\n')
        fleet = MonitorFleet(Config(self.root, 'fixture-a', interval=1, batch_mode=True,
                                    servers={'A': 'fixture-a', 'B': 'fixture-b'}), str(self.fixture))
        try:
            fleet.start()
            eventually(lambda: all(state.snapshot()['latest'] is not None
                                   and state.snapshot()['latest']['cpu']['percent'] is not None
                                   for state in fleet.states.values()))
            before = {key: state.snapshot() for key, state in fleet.states.items()}
            pids = {key: monitor._process.pid for key, monitor in fleet.monitors.items()}
            self.assertNotEqual(pids['0'], pids['1'])
            fleet.reconnect('0')
            eventually(lambda: fleet.snapshot('0')['status'] == 'connected'
                       and (fleet.snapshot('0')['connected_since'] or 0) > before['0']['connected_since'])
            eventually(lambda: fleet.snapshot('1')['last_update'] > before['1']['last_update'])
            self.assertNotEqual(fleet.monitors['0']._process.pid, pids['0'])
            self.assertEqual(fleet.monitors['1']._process.pid, pids['1'])
            self.assertEqual(fleet.snapshot('1')['connected_since'], before['1']['connected_since'])
            self.assertGreater(len(fleet.snapshot('1')['history']), len(before['1']['history']))
        finally:
            fleet.stop()
        self.assertTrue(all(not monitor._thread.is_alive() for monitor in fleet.monitors.values()))
        self.assertTrue(all(monitor._process is None for monitor in fleet.monitors.values()))

    def test_all_invalid_frames_never_look_connected(self):
        self.write_fixture("#!/bin/sh\nfor i in 1 2 3; do printf '__SM_BEGIN__\\nversion\\t1\\nmeminfo\\tMemTotal: 0 kB\\n__SM_END__\\n'; done\n")
        with self.assertLogs('monitor.connection', level='WARNING'):
            self.monitor.start()
            eventually(lambda: 'Could not read' in self.state.snapshot()['message'])
        self.assertIsNone(self.state.snapshot()['latest'])
        self.assertEqual(self.state.snapshot()['history'], [])

    def test_authentication_error_is_explained_and_stop_is_fast(self):
        self.write_fixture("#!/bin/sh\nwhile [ $# -gt 0 ]; do if [ \"$1\" = '-E' ]; then shift; printf 'Permission denied (publickey).\\n' > \"$1\"; break; fi; shift; done\nexit 255\n")
        self.monitor.start()
        eventually(lambda: 'SSH authentication failed' in self.state.snapshot()['message'])
        start = time.monotonic()
        self.monitor.stop()
        self.assertLess(time.monotonic() - start, 3)
        self.assertIsNone(self.state.snapshot()['latest'])


if __name__ == '__main__':
    unittest.main()
