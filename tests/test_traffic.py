"""Optional process/vnStat data stays bounded and never invents missing days."""

from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import unittest

from monitor.demo import demo_sample
from monitor.metrics import MetricCalculator, build_probe, parse_frame


def vnstat_frame(interfaces=None, today="2024-03-02", version="2"):
    if interfaces is None:
        interfaces = [{"name": "eth0", "traffic": {"day": [
            {"date": {"year": 2024, "month": 3, "day": 2}, "rx": 100, "tx": 50},
            {"date": {"year": 2024, "month": 2, "day": 29}, "rx": 20, "tx": 10},
            {"date": {"year": 2024, "month": 2, "day": 24}, "rx": 999, "tx": 999},
        ]}}]
    return ("traffic_refresh\t1\ntraffic_date\t" + today + "\ndefault_interface\teth0\nvnstat\t"
            + json.dumps({"jsonversion": version, "interfaces": interfaces}))


class OptionalMetricTests(unittest.TestCase):
    def test_processes_are_optional_and_bounded_without_clamping_cpu(self):
        calc = MetricCalculator()
        self.assertIsNone(calc.update(parse_frame(""), 1)["processes"])
        source = "processes_available\t1\nprocess\t42\t240.5\t2048\tworker with spaces\n"
        source += "process\t43\tNaN\t-1\tunknown\n"
        source += "process\t-1\t10\t10\tbad-pid\n"
        source += "process\t44\t1\t1\tbad\x00name\n"
        source += "".join(f"process\t{pid}\t1\t1\tprocess-{pid}\n" for pid in range(50, 60))
        processes = calc.update(parse_frame(source), 2)["processes"]
        self.assertEqual(len(processes), 10)
        self.assertEqual(processes[0], {"pid": 42, "name": "worker with spaces",
                                      "cpu_percent": 240.5, "memory_bytes": 2097152})
        self.assertEqual(processes[1], {"pid": 43, "name": "unknown",
                                      "cpu_percent": None, "memory_bytes": None})
        self.assertEqual(calc.update(parse_frame("processes_available\t1"), 3)["processes"], [])
        self.assertIsNone(calc.update(parse_frame("processes_available\t0"), 4)["processes"])

    def test_calendar_window_bytes_and_missing_days(self):
        sample = MetricCalculator().update(parse_frame(vnstat_frame()), 123.456)
        traffic = sample["traffic"]
        self.assertEqual(traffic["updated_at"], 123456)
        self.assertEqual(traffic["default_interface"], "eth0")
        interface = traffic["interfaces"][0]
        self.assertEqual([item["date"] for item in interface["days"]], [
            "2024-02-25", "2024-02-26", "2024-02-27", "2024-02-28", "2024-02-29", "2024-03-01", "2024-03-02"])
        self.assertIsNone(interface["days"][0]["rx"])
        self.assertEqual(interface["days"][-1]["rx"], 100, "JSON v2 counters are bytes")
        self.assertEqual((interface["rx"], interface["tx"]), (120, 60))

    def test_preserves_interfaces_and_falls_back_when_default_is_not_monitored(self):
        interfaces = [{"name": name, "traffic": {"day": []}} for name in ("wg0", "eth0")]
        interfaces[1]["traffic"]["day"] = [
            {"date": {"year": 2024, "month": 3, "day": 2}, "rx": 0, "tx": 0}]
        source = vnstat_frame(interfaces)
        traffic = MetricCalculator().update(parse_frame(source), 1)["traffic"]
        self.assertEqual([item["name"] for item in traffic["interfaces"]], ["wg0", "eth0"])
        self.assertEqual(traffic["default_interface"], "eth0")
        self.assertIsNone(traffic["interfaces"][0]["rx"])
        self.assertIsNone(traffic["interfaces"][0]["tx"])
        self.assertEqual(traffic["interfaces"][1]["rx"], 0)
        self.assertEqual(traffic["interfaces"][1]["tx"], 0)
        source = source.replace("default_interface\teth0", "default_interface\tunmonitored")
        self.assertEqual(MetricCalculator().update(parse_frame(source), 1)["traffic"]["default_interface"], "wg0")

    def test_all_unknown_recent_traffic_hides_but_measured_zero_is_available(self):
        for interfaces in ([{"name": "eth0", "traffic": {"day": []}}],
                           [{"name": "eth0", "traffic": {"day": [
                               {"date": {"year": 2024, "month": 2, "day": 24}, "rx": 100, "tx": 200}]}}],
                           [{"name": "eth0", "traffic": {"day": [
                               {"date": {"year": 2024, "month": 3, "day": 2}, "rx": True, "tx": -1}]}}]):
            self.assertIsNone(MetricCalculator().update(parse_frame(vnstat_frame(interfaces)), 1)["traffic"])
        source = vnstat_frame([{"name": "eth0", "traffic": {"day": [
            {"date": {"year": 2024, "month": 3, "day": 2}, "rx": None, "tx": 0}]}}])
        interface = MetricCalculator().update(parse_frame(source), 1)["traffic"]["interfaces"][0]
        self.assertIsNone(interface["rx"])
        self.assertEqual(interface["tx"], 0)

    def test_traffic_is_cached_between_reads_and_failure_clears_it(self):
        calc = MetricCalculator()
        first = calc.update(parse_frame(vnstat_frame()), 10)["traffic"]
        self.assertEqual(calc.update(parse_frame("cpu\t1 2 3 4"), 12)["traffic"], first)
        refreshed = calc.update(parse_frame(vnstat_frame()), 70)["traffic"]
        self.assertEqual(refreshed["updated_at"], 70000)
        self.assertIsNone(calc.update(parse_frame("traffic_refresh\t1"), 130)["traffic"])
        self.assertIsNone(calc.update(parse_frame(""), 132)["traffic"])

    def test_unknown_versions_invalid_dates_and_oversized_data_are_unavailable(self):
        for source in (vnstat_frame(version="1"), vnstat_frame(version="3"),
                       vnstat_frame(today="2024-02-30"), vnstat_frame(today="20240302"),
                       vnstat_frame(today="0001-01-01"), "traffic_refresh\t1\nvnstat\t{",
                       "traffic_date\t2024-03-02\nvnstat\t" + " " * 49153,
                       "traffic_date\t2024-03-02\nvnstat\t" + "[" * 2000 + "]" * 2000,
                       vnstat_frame([{"name": f"eth{i}", "traffic": {"day": []}} for i in range(33)]),
                       vnstat_frame([{"name": "bad\nname", "traffic": {"day": []}}])):
            with self.subTest(source=source[:80]):
                self.assertIsNone(MetricCalculator().update(parse_frame(source), 1)["traffic"])

    def test_counters_are_unsigned_integers_and_invalid_entries_do_not_create_zero(self):
        for invalid in (-1, True, 1.5, "25", 1 << 64, None):
            with self.subTest(invalid=invalid):
                source = vnstat_frame([{"name": "eth0", "traffic": {"day": [
                    {"date": {"year": 2024, "month": 3, "day": 2}, "rx": invalid, "tx": 0}]}}])
                daily = MetricCalculator().update(parse_frame(source), 1)["traffic"]["interfaces"][0]["days"][-1]
                self.assertIsNone(daily["rx"])
                self.assertEqual(daily["tx"], 0)
        day = {"date": {"year": 2024, "month": 3, "day": 2}, "rx": 1, "tx": 1}
        for entries in ([day, day], [day] * 8,
                        [{"date": {"year": 2024, "month": 2, "day": 30}, "rx": 1, "tx": 1}]):
            self.assertIsNone(MetricCalculator().update(parse_frame(vnstat_frame([
                {"name": "eth0", "traffic": {"day": entries}}])), 1)["traffic"])

    def test_demo_variants_keep_defaults_and_can_hide_traffic(self):
        now = datetime(2024, 3, 2, 12).timestamp()
        samples = [demo_sample(now, variant) for variant in range(3)]
        self.assertEqual(demo_sample(now), samples[0])
        self.assertEqual(len({sample["host"]["hostname"] for sample in samples}), 3)
        self.assertEqual(len({sample["memory"]["total"] for sample in samples}), 3)
        self.assertTrue(all(len(sample["processes"]) == 5 for sample in samples))
        self.assertTrue(all(sample["cpu"]["temperature_c"] is None for sample in samples))
        self.assertEqual(samples[0]["traffic"]["interfaces"][0]["days"][-1]["date"], "2024-03-02")
        self.assertIsNone(samples[2]["traffic"])


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("sh") and Path("/proc/stat").exists(),
                     "live probe requires Linux procfs and sh")
class OptionalProbeTests(unittest.TestCase):
    def run_probe(self, directory, seconds):
        environment = dict(os.environ, PATH=str(directory))
        process = subprocess.Popen([shutil.which("sh"), "-s"], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True, env=environment)
        try:
            stdout, stderr = process.communicate(input=build_probe(1, "/"), timeout=seconds)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate(timeout=5)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=5)
        sections = stdout.split("__SM_BEGIN__\n")[1:]
        return [parse_frame(section.split("__SM_END__", 1)[0])
                for section in sections if "__SM_END__" in section], stderr

    def native_commands(self, directory, timeout=True):
        for command in ("awk", "cat", "uname", "sleep", "df", "date", "ps") + (("timeout",) if timeout else ()):
            (directory / command).symlink_to(shutil.which(command))

    def test_vnstat_is_read_once_and_failures_do_not_stop_other_metrics(self):
        for success in (True, False):
            with self.subTest(success=success), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                self.native_commands(directory)
                if not success:
                    (directory / "ps").unlink()
                    (directory / "ps").write_text("#!/bin/sh\nprintf '42 100 200 partial-output\\n'\nexit 1\n", encoding="utf-8")
                    (directory / "ps").chmod(0o755)
                marker = directory / "reads"
                today = datetime.now().date()
                payload = vnstat_frame([{"name": "eth0", "traffic": {"day": [
                    {"date": {"year": today.year, "month": today.month, "day": today.day},
                     "rx": 0, "tx": 0}]}}]).split("vnstat\t", 1)[1]
                command = directory / "vnstat"
                command.write_text("#!/bin/sh\n[ \"$*\" = '--json d 7' ] || exit 2\n"
                                   + "printf 'read\\n' >> " + shlex.quote(str(marker)) + "\n"
                                   + "printf '%s\\n' " + shlex.quote(payload) + "\n"
                                   + ("exit 0\n" if success else "exit 1\n"), encoding="utf-8")
                command.chmod(0o755)
                frames, stderr = self.run_probe(directory, 2.6)
                self.assertGreaterEqual(len(frames), 2, stderr)
                self.assertEqual(marker.read_text().count("read"), 1)
                calc = MetricCalculator()
                samples = [calc.update(raw, index + 1) for index, raw in enumerate(frames)]
                self.assertGreater(samples[-1]["memory"]["total"], 0)
                self.assertIsNotNone(samples[-1]["cpu"]["percent"])
                self.assertEqual(samples[-1]["processes"] is not None, success)
                if success:
                    self.assertTrue(1 <= len(samples[-1]["processes"]) <= 10)
                self.assertEqual(samples[0]["traffic"] is not None, success)
                self.assertEqual(samples[-1]["traffic"], samples[0]["traffic"])

    def test_hung_vnstat_without_timeout_is_killed_and_frames_continue(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.native_commands(directory, timeout=False)
            marker = directory / "vnstat-pid"
            command = directory / "vnstat"
            command.write_text("#!/bin/sh\nprintf '%s' \"$$\" > " + shlex.quote(str(marker))
                               + "\nexec sleep 60\n", encoding="utf-8")
            command.chmod(0o755)
            frames, stderr = self.run_probe(directory, 4.8)
            self.assertGreaterEqual(len(frames), 2, stderr)
            self.assertIsNone(MetricCalculator().update(frames[0], 1)["traffic"])
            with self.assertRaises(ProcessLookupError):
                os.kill(int(marker.read_text()), 0)

    def test_finished_watchdogs_reap_their_sleep_children(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.native_commands(directory, timeout=False)
            native_sleep = shutil.which("sleep")
            native_df = shutil.which("df")
            marker = directory / "sleep-pids"
            (directory / "sleep").unlink()
            (directory / "sleep").write_text(
                "#!/bin/sh\nprintf '%s %s\\n' \"$$\" \"$1\" >> " + shlex.quote(str(marker))
                + "\nexec " + shlex.quote(native_sleep) + ' "$@"\n', encoding="utf-8")
            (directory / "sleep").chmod(0o755)
            (directory / "df").unlink()
            (directory / "df").write_text("#!/bin/sh\n" + shlex.quote(native_sleep) + " 0.2\nexec "
                                           + shlex.quote(native_df) + ' "$@"\n', encoding="utf-8")
            (directory / "df").chmod(0o755)
            process = subprocess.Popen([shutil.which("sh"), "-s"], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                       start_new_session=True, env=dict(os.environ, PATH=str(directory)))
            complete = threading.Event()
            def read_first_frame():
                for line in process.stdout:
                    if line.strip() == "__SM_END__":
                        complete.set()
                        return
            reader = threading.Thread(target=read_first_frame, daemon=True)
            try:
                process.stdin.write(build_probe(1, "/"))
                process.stdin.close()
                reader.start()
                self.assertTrue(complete.wait(5), "first frame did not arrive")
                reader.join(timeout=1)
                watchdogs = [int(line.split()[0]) for line in marker.read_text().splitlines()
                             if line.split()[1] in ("2", "3")]
                self.assertTrue(watchdogs, "watchdog sleeps were not observed")
                for pid in watchdogs:
                    with self.assertRaises(ProcessLookupError):
                        os.kill(pid, 0)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                reader.join(timeout=1)
                process.stdout.close()
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
