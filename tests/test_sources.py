import json
import contextlib
import io
import os
import subprocess
import http.client
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from monitor.config import ConfigError, load_config
from monitor.connection import build_ssh_command
from monitor.fleet import MonitorFleet
from monitor.web import create_http_server


class SourceConfigTests(unittest.TestCase):
    def load(self, servers, env=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'servers.json').write_text(json.dumps(servers), encoding='utf-8')
            return load_config(root, environ=env or {})

    def test_local_sources_are_opt_in_and_allow_no_ssh(self):
        config = self.load({'Server': 'server'})
        self.assertFalse(config.monitor_self)
        self.assertFalse(config.wsl_autodetect)
        config = self.load({}, {'MONITOR_SELF': 'true', 'WSL_AUTODETECT': 'yes'})
        self.assertTrue(config.monitor_self)
        self.assertTrue(config.wsl_autodetect)
        self.assertEqual(config.servers, {})
        for key in ('MONITOR_SELF', 'WSL_AUTODETECT'):
            with self.subTest(key=key), self.assertRaises(ConfigError):
                self.load({}, {key: 'perhaps'})

    def test_jump_alias_is_one_argument_before_destination(self):
        config = self.load({'Private': {'alias': 'private', 'jump': 'gateway'}})
        self.assertEqual(config.alias, 'private')
        command = build_ssh_command(config, 'ssh', Path('ssh.log'))
        self.assertEqual(command[-4:], ['-J', 'gateway', 'private', 'sh -s'])
        self.assertIn('StrictHostKeyChecking=ask', command)
        direct = build_ssh_command(self.load({'Old': 'old'}), 'ssh', Path('ssh.log'))
        self.assertNotIn('-J', direct)

    def test_jump_validation_and_duplicate_routes(self):
        for value in ('-oProxyCommand=x', 'gate;id', 'gate other', '', None, ['gate']):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                self.load({'A': {'alias': 'private', 'jump': value}})
        for entry in ({'jump': 'gate'}, {'alias': 'x', 'command': 'id'}, {'alias': '-bad'}):
            with self.subTest(entry=entry), self.assertRaises(ConfigError):
                self.load({'A': entry})
        with self.assertRaises(ConfigError):
            self.load({'A': 'same', 'B': {'alias': 'same'}})
        self.load({'A': {'alias': 'same', 'jump': 'one'},
                   'B': {'alias': 'same', 'jump': 'two'}})

    def test_fleet_preserves_ssh_ids_and_keeps_local_sources_separate(self):
        config = self.load({'Private': {'alias': 'private', 'jump': 'gateway'}},
                           {'MONITOR_SELF': 'true', 'WSL_AUTODETECT': 'true'})
        with patch('monitor.fleet.discover_wsl', return_value=['Ubuntu', 'Other Linux']), \
                patch('monitor.fleet.LocalMonitor') as local:
            fleet = MonitorFleet(config, 'ssh')
        self.assertEqual(list(fleet.states), ['0', 'self', 'wsl-0', 'wsl-1'])
        self.assertEqual(fleet.monitors['0'].config.jump, 'gateway')
        self.assertEqual(local.call_count, 3)
        self.assertEqual([entry['source'] for entry in fleet.list_servers()['servers']],
                         ['ssh', 'self', 'wsl', 'wsl'])
        fleet.states['self'].record({'ts': 1000})
        self.assertNotIn('SSH', fleet.snapshot('self')['message'])
        self.assertIsNone(fleet.snapshot('wsl-0')['latest'])

    def test_no_sources_reports_configuration_error_and_demo_ignores_local_flags(self):
        config = self.load({}, {'WSL_AUTODETECT': 'true'})
        with patch('monitor.fleet.discover_wsl', return_value=[]), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ConfigError, 'No monitoring sources'):
            MonitorFleet(config, None)
        with tempfile.TemporaryDirectory() as directory:
            demo = load_config(Path(directory), demo=True, environ={
                'MONITOR_SELF': 'true', 'WSL_AUTODETECT': 'true'})
        with patch('monitor.fleet.discover_wsl') as discovery:
            fleet = MonitorFleet(demo, None)
        discovery.assert_not_called()
        self.assertEqual(len(fleet.states), 3)

    def test_self_only_cli_does_not_search_for_ssh(self):
        import server
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'servers.json').write_text('{}', encoding='utf-8')
            (root / 'test.env').write_text('MONITOR_SELF=true\nWSL_AUTODETECT=false\n', encoding='utf-8')
            with patch('server.find_ssh', side_effect=AssertionError('SSH must not be required')), \
                    patch.dict('os.environ', {}, clear=True), contextlib.redirect_stdout(io.StringIO()) as output:
                result = server.main(['--env', str(root / 'test.env'), '--servers',
                                      str(root / 'servers.json'), '--check'])
        self.assertEqual(result, 0)
        self.assertIn('self', output.getvalue())

    @unittest.skipUnless(os.name == 'nt', 'Windows native SSH discovery')
    def test_native_ssh_priority_timeouts_and_non_native_rejection(self):
        import server
        native = subprocess.CompletedProcess([], 0, b'', b'OpenSSH_for_Windows_9.5')
        other = subprocess.CompletedProcess([], 0, b'', b'OpenSSH_9.5')
        with patch('server.Path.is_file', return_value=True), \
                patch('server.shutil.which', return_value='git-ssh.exe'), \
                patch('server.subprocess.run', return_value=native):
            self.assertIn('Sysnative', server.find_ssh())
        with patch('server.Path.is_file', return_value=True), \
                patch('server.shutil.which', return_value='git-ssh.exe'), \
                patch('server.subprocess.run', side_effect=[subprocess.TimeoutExpired('ssh', 10), other, native]):
            self.assertIn('Program Files', server.find_ssh())
        with patch('server.Path.is_file', return_value=True), \
                patch('server.shutil.which', return_value='git-ssh.exe'), \
                patch('server.subprocess.run', return_value=other):
            self.assertIsNone(server.find_ssh())

    def test_local_only_http_list_snapshot_and_reconnect(self):
        from unittest.mock import Mock
        config = self.load({}, {'MONITOR_SELF': 'true'})
        fleet = MonitorFleet(config, None)
        fleet.monitors['self'].reconnect = Mock()
        fleet.states['self'].record({'ts': 1000, 'cpu': {'percent': 12}})
        server = create_http_server(0, fleet, Path('.'), 'test-token')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for path, method in [('/api/servers', 'GET'), ('/api/snapshot?server=self', 'GET'),
                                 ('/api/reconnect?server=self', 'POST')]:
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                try:
                    connection.request(method, path, headers={'X-Monitor-Token': 'test-token'})
                    response = connection.getresponse()
                    data = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                finally:
                    connection.close()
                if path == '/api/servers':
                    self.assertEqual(data['default_server'], 'self')
                    self.assertEqual(data['servers'][0]['source'], 'self')
                elif method == 'GET':
                    self.assertEqual(data['source'], 'self')
                    self.assertEqual(data['latest']['cpu']['percent'], 12)
                else:
                    fleet.monitors['self'].reconnect.assert_called_once()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)


if __name__ == '__main__':
    unittest.main()
