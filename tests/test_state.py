import unittest

from monitor.state import MonitorState


class StateTests(unittest.TestCase):
    def setUp(self):
        self.now = 10000.0
        self.ticks = 500.0
        self.state = MonitorState('test', 2, clock=lambda: self.now, monotonic=lambda: self.ticks)

    def sample(self):
        return {'ts': round(self.now * 1000), 'cpu': {'percent': 42}}

    def test_startup_has_no_fabricated_latest(self):
        data = self.state.snapshot()
        self.assertIsNone(data['latest'])
        self.assertEqual(data['history'], [])
        self.assertEqual(data['status'], 'connecting')

    def test_records_real_sample_and_preserves_it_on_disconnect(self):
        self.state.record(self.sample())
        self.state.set_status('reconnecting', 'Disconnected')
        data = self.state.snapshot()
        self.assertEqual(data['status'], 'reconnecting')
        self.assertEqual(data['latest']['cpu']['percent'], 42)

    def test_staleness_uses_monotonic_time(self):
        self.state.record(self.sample())
        self.now -= 1000
        self.ticks += 30
        self.assertEqual(self.state.snapshot()['status'], 'reconnecting')
        self.assertEqual(self.state.status(), 'reconnecting')

    def test_optional_details_are_latest_only(self):
        sample = {**self.sample(), 'processes': [{'pid': 1}], 'traffic': {'interfaces': []}}
        self.state.record(sample)
        snapshot = self.state.snapshot()
        self.assertEqual(snapshot['latest'], sample)
        self.assertNotIn('traffic', snapshot['history'][0])
        self.assertNotIn('processes', snapshot['history'][0])

    def test_history_is_bounded_to_an_hour_and_to_a_count(self):
        for _ in range(4000):
            self.state.record(self.sample())
            self.now += 2
            self.ticks += 2
        samples = self.state.snapshot()['history']
        self.assertLessEqual(len(samples), 1801)
        self.assertLessEqual(samples[-1]['ts'] - samples[0]['ts'], 3600000)

    def test_reconnect_starts_new_session_time(self):
        self.state.record(self.sample())
        initial = self.state.snapshot()['connected_since']
        self.state.begin_session()
        self.now += 20
        self.ticks += 20
        self.state.record(self.sample())
        self.assertGreater(self.state.snapshot()['connected_since'], initial)


if __name__ == '__main__':
    unittest.main()
