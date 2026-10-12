import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

from monitor.config import Config
from monitor.connection import SSHMonitor
from monitor.fleet import MonitorFleet
from monitor.state import MonitorState


class FleetTests(unittest.TestCase):
    def test_independent_history_reconnect_logs_and_collectors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fleet = MonitorFleet(Config(root, 'nl', servers={'NL': 'nl', 'RU': 'ru'}), 'ssh')
            shutdown = []
            for key, monitor in fleet.monitors.items():
                monitor.start = Mock()
                monitor.request_stop = Mock(side_effect=lambda key=key: shutdown.append(('cancel', key)))
                monitor.stop = Mock(side_effect=lambda key=key: shutdown.append(('join', key)))
                monitor.reconnect = Mock()
            fleet.start()
            for monitor in fleet.monitors.values():
                monitor.start.assert_called_once()
            fleet.states['0'].record({'ts': 1000, 'cpu': {'percent': 15}})
            fleet.states['1'].record({'ts': 2000, 'cpu': {'percent': 80}})
            self.assertEqual(fleet.snapshot('0')['history'][0]['cpu']['percent'], 15)
            self.assertEqual(fleet.snapshot('1')['history'][0]['cpu']['percent'], 80)
            fleet.reconnect('1')
            fleet.monitors['1'].reconnect.assert_called_once()
            fleet.monitors['0'].reconnect.assert_not_called()
            self.assertNotEqual(fleet.monitors['0']._log_path, fleet.monitors['1']._log_path)
            self.assertIs(fleet.monitors['0']._authentication_lock, fleet.monitors['1']._authentication_lock)
            self.assertIs(fleet.monitors['0']._shutdown, fleet.monitors['1']._shutdown)
            fleet.stop()
            self.assertTrue(fleet._shutdown.is_set())
            self.assertEqual(shutdown, [('cancel', '0'), ('cancel', '1'), ('join', '0'), ('join', '1')])
            for monitor in fleet.monitors.values():
                monitor.stop.assert_called_once()

    def test_authentication_is_serial_but_connected_sessions_overlap(self):
        gate = threading.Lock()

        class Session(SSHMonitor):
            def __init__(self):
                super().__init__(Config(Path('.'), 'fixture'), MonitorState('fixture', 2),
                                 'unused', authentication_lock=gate)
                self.entered = threading.Event()
                self.authenticated = threading.Event()
                self.finish = threading.Event()

            def _collect_session(self, authentication):
                self.entered.set()
                self.authenticated.wait(3)
                authentication.close()
                self.finish.wait(3)
                return True

        first, second = Session(), Session()
        threads = [threading.Thread(target=session._session) for session in (first, second)]
        try:
            threads[0].start()
            self.assertTrue(first.entered.wait(1))
            threads[1].start()
            self.assertFalse(second.entered.wait(0.1))
            first.authenticated.set()
            self.assertTrue(second.entered.wait(1))
            self.assertTrue(threads[0].is_alive(), 'First collector should continue while second authenticates.')
        finally:
            for session in (first, second):
                session.authenticated.set()
                session.finish.set()
            for thread in threads:
                if thread.ident is not None:
                    thread.join(4)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertTrue(gate.acquire(timeout=0.1))
        gate.release()

    def test_failed_and_cancelled_authentication_release_the_queue(self):
        gate = threading.Lock()
        shutdown = threading.Event()
        monitor = SSHMonitor(Config(Path('.'), 'fixture'), MonitorState('fixture', 2),
                             'unused', authentication_lock=gate, shutdown_event=shutdown)
        monitor._collect_session = Mock(side_effect=OSError('fixture failure'))
        with self.assertRaises(OSError):
            monitor._session()
        self.assertTrue(gate.acquire(timeout=0.1))
        result = []
        thread = threading.Thread(target=lambda: result.append(monitor._session()))
        try:
            thread.start()
            shutdown.set()
            thread.join(1)
            self.assertEqual(result, [False])
            self.assertFalse(monitor._stop.is_set(), 'Fleet cancellation must work before individual stop().')
        finally:
            gate.release()
            thread.join(1)


if __name__ == '__main__':
    unittest.main()
