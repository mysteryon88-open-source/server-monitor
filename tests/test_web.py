import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from monitor.config import Config
from monitor.fleet import MonitorFleet
from monitor.web import create_http_server


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        (cls.root / 'index.html').write_text('<meta name="monitor-token" content="__MONITOR_TOKEN__">'
                                           '<meta name="monitor-language" content="__MONITOR_LANGUAGE__">', encoding='utf-8')
        (cls.root / 'app.js').write_text('"use strict";', encoding='utf-8')
        cls.reconnects = []
        cls.fleet = MonitorFleet(Config(cls.root, 'test', language='en',
                                        servers={'First': 'test', 'Second': 'other'}), 'ssh')
        cls.fleet.reconnect = cls.reconnects.append
        cls.server = create_http_server(0, cls.fleet, cls.root, 'test-token')
        cls.port = cls.server.server_address[1]
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=3)
        cls.directory.cleanup()

    def request(self, path, method='GET', headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        code, headers, body = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return code, headers, body

    def test_entry_injects_token_and_safety_headers(self):
        code, headers, body = self.request('/')
        self.assertEqual(code, 200)
        self.assertIn(b'content="test-token"', body)
        self.assertIn(b'content="en"', body)
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_json_requires_token_and_has_real_empty_state(self):
        self.assertEqual(self.request('/api/snapshot')[0], 403)
        self.assertEqual(self.request('/api/snapshot', headers={'X-Monitor-Token': 'wrong'})[0], 403)
        code, _, body = self.request('/api/snapshot', headers={'X-Monitor-Token': 'test-token'})
        self.assertEqual(code, 200)
        self.assertIsNone(json.loads(body)['latest'])

    def test_host_rebinding_and_foreign_origin_are_rejected(self):
        for headers in ({'Host': 'evil.test'}, {'Host': f'127.0.0.1:{self.port}.evil.test'},
                        {'Origin': 'https://evil.test'}, {'Sec-Fetch-Site': 'cross-site'}):
            with self.subTest(headers=headers):
                headers['X-Monitor-Token'] = 'test-token'
                self.assertEqual(self.request('/api/snapshot', headers=headers)[0], 403)

    def test_explicit_same_origin_is_allowed(self):
        self.assertEqual(self.request('/api/snapshot', headers={
            'X-Monitor-Token': 'test-token', 'Origin': f'http://127.0.0.1:{self.port}'})[0], 200)

    def test_fixed_routes_do_not_serve_env_or_traversal(self):
        for path in ('/.env', '/servers.json', '/../../.env', '/%2e%2e/README.md', '/docs/DESIGN.md', '/logs/ssh.log'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)

    def test_reconnect_requires_post_and_token(self):
        self.assertEqual(self.request('/api/reconnect', 'POST')[0], 403)
        self.assertEqual(self.request('/api/reconnect', headers={'X-Monitor-Token': 'test-token'})[0], 405)
        before = len(self.reconnects)
        code, _, body = self.request('/api/reconnect', 'POST', {'X-Monitor-Token': 'test-token'})
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)['ok'])
        self.assertEqual(len(self.reconnects), before + 1)
        self.assertEqual(self.reconnects[-1], '0')

    def test_server_list_and_selected_snapshots_are_separate(self):
        headers = {'X-Monitor-Token': 'test-token'}
        self.assertEqual(self.request('/api/servers')[0], 403)
        code, _, body = self.request('/api/servers', headers=headers)
        data = json.loads(body)
        self.assertEqual(code, 200)
        self.assertEqual(data['language'], 'en')
        self.assertEqual([(s['id'], s['name']) for s in data['servers']], [('0', 'First'), ('1', 'Second')])
        self.fleet.states['1'].record({'ts': 123456, 'cpu': {'percent': 89}})
        code, _, body = self.request('/api/snapshot?server=1', headers=headers)
        selected = json.loads(body)
        self.assertEqual(code, 200)
        self.assertEqual(selected['alias'], 'other')
        self.assertEqual(selected['name'], 'Second')
        self.assertEqual(selected['latest']['cpu']['percent'], 89)
        self.assertIsNone(json.loads(self.request('/api/snapshot?server=0', headers=headers)[2])['latest'])
        self.request('/api/reconnect?server=1', 'POST', headers)
        self.assertEqual(self.reconnects[-1], '1')

    def test_server_selection_accepts_only_configured_ids(self):
        headers = {'X-Monitor-Token': 'test-token'}
        for query, expected in [('server=99', 404), ('server=-oBad', 404), ('server=', 404),
                                ('server=0&server=1', 400), ('cmd=id', 400),
                                ('server=0&a=1&b=2&c=3&d=4', 400)]:
            before = len(self.reconnects)
            for endpoint, method in [('/api/snapshot', 'GET'), ('/api/reconnect', 'POST')]:
                with self.subTest(query=query, endpoint=endpoint):
                    self.assertEqual(self.request(endpoint + '?' + query, method, headers)[0], expected)
            self.assertEqual(len(self.reconnects), before)

    def test_only_loopback_listening(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')


if __name__ == '__main__':
    unittest.main()
