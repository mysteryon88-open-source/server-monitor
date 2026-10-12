"""Independent metric arithmetic and Linux probe contract checks."""

import copy
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

from monitor.metrics import MetricCalculator, build_probe, parse_frame


def frame(
    cpu="100 20 30 400 50 10 20 5 25 2",
    uptime="100.00",
    boot="boot-one",
    cores=2,
    available="400",
    swap_total="200",
    swap_free="150",
    disk="/dev/vda1 1000 600 300 67% /srv/data archive",
):
    lines = [
        "__SM_BEGIN__",
        "version\t1",
        "cpu\t" + "\t".join(cpu.split()),
        "uptime\t" + uptime,
        "boot_id\t" + boot,
        "btime\t12345",
        "cores\t" + str(cores),
        "mhz\t2590.5",
        "model\tExample CPU",
        "hostname\tserver.example",
        "kernel\t6.8.0-test",
        "arch\tx86_64",
        "load\t0.4\t0.3\t0.2",
        'os_release\tNAME="Example Linux"',
        'os_release\tPRETTY_NAME="Example Linux 1.0"',
        "meminfo\tMemTotal: 1000 kB",
        "meminfo\tMemFree: 100 kB",
        "meminfo\tBuffers: 20 kB",
        "meminfo\tCached: 200 kB",
        "meminfo\tSReclaimable: 80 kB",
        "meminfo\tShmem: 30 kB",
        "meminfo\tSwapTotal: " + swap_total + " kB",
        "meminfo\tSwapFree: " + swap_free + " kB",
        "disk_path\t/srv/data archive",
    ]
    if available is not None:
        lines.append("meminfo\tMemAvailable: " + available + " kB")
    if disk is not None:
        lines.append("df\t" + disk)
    lines.append("__SM_END__")
    return "\n".join(lines)


class ParseFrameTests(unittest.TestCase):
    def test_reads_sample_with_or_without_markers(self):
        source = frame()
        self.assertEqual(parse_frame(source), parse_frame(source.split("\n", 1)[1].rsplit("\n", 1)[0]))
        sample = MetricCalculator().update(parse_frame(source), timestamp=123.456)
        self.assertEqual(sample["ts"], 123456)
        self.assertEqual(sample["cpu"]["cores"], 2)
        self.assertEqual(sample["cpu"]["mhz"], 2590.5)
        self.assertEqual(sample["cpu"]["model"], "Example CPU")
        self.assertEqual(sample["host"], {
            "hostname": "server.example", "os": "Example Linux 1.0",
            "kernel": "6.8.0-test", "arch": "x86_64", "uptime": 100.0,
            "load": [0.4, 0.3, 0.2],
        })

    def test_does_not_evaluate_os_release_contents(self):
        source = frame().replace('PRETTY_NAME="Example Linux 1.0"', 'PRETTY_NAME="$(echo EXECUTED) `uname`"')
        sample = MetricCalculator().update(parse_frame(source), timestamp=1)
        self.assertEqual(sample["host"]["os"], "$(echo EXECUTED) `uname`")

    def test_unicode_line_separator_in_path_is_data(self):
        path = "/srv/archive\u2028folder"
        source = frame().replace("disk_path\t/srv/data archive", "disk_path\t" + path)
        sample = MetricCalculator().update(parse_frame(source), timestamp=1)
        self.assertEqual(sample["disk"]["path"], path)

    def test_malformed_optional_records_do_not_become_zero_or_nan(self):
        source = frame().replace("mhz\t2590.5", "mhz\tNaN").replace("load\t0.4\t0.3\t0.2", "load\tbad\t0.3\t0.2")
        source = source.replace("df\t/dev/vda1 1000 600 300 67% /srv/data archive", "df\tmalformed disk output")
        sample = MetricCalculator().update(parse_frame(source), timestamp=1)
        self.assertIsNone(sample["cpu"]["mhz"])
        self.assertIsNone(sample["host"]["load"])
        self.assertIsNone(sample["disk"]["percent"])
        self.assertIsNone(sample["disk"]["total"])
        json.dumps(sample, allow_nan=False)

    def test_incomplete_cpu_row_does_not_reuse_old_counters(self):
        calc = MetricCalculator()
        calc.update(parse_frame(frame()), timestamp=1)
        sample = calc.update(parse_frame(frame(cpu="7 8", uptime="102")), timestamp=3)
        self.assertIsNone(sample["cpu"]["percent"])

    def test_unrelated_lines_do_not_create_metrics(self):
        sample = MetricCalculator().update(parse_frame("banner\nunknown\tvalue\n"), timestamp=1)
        for metric in ("cpu", "memory", "swap", "disk"):
            self.assertIsNone(sample[metric]["percent"])
        self.assertIsNone(sample["swap"]["enabled"])


class MetricCalculatorTests(unittest.TestCase):
    def test_first_cpu_sample_is_unknown(self):
        sample = MetricCalculator().update(parse_frame(frame()), timestamp=1)
        self.assertIsNone(sample["cpu"]["percent"])
        self.assertIsNone(sample["cpu"]["iowait"])
        self.assertIsNone(sample["cpu"]["steal"])

    def test_cpu_uses_deltas_and_never_double_counts_guest(self):
        calc = MetricCalculator()
        calc.update(parse_frame(frame()), timestamp=1)
        # First 8 counters increased by [20, 0, 10, 50, 5, 5, 5, 5].
        # 100 ticks total, of which idle+iowait = 55, iowait = 5, steal = 5.
        # Guest grows by 20 and guest_nice by 9: both must be ignored.
        sample = calc.update(parse_frame(frame(cpu="120 20 40 450 55 15 25 10 45 11", uptime="102")), timestamp=3)
        self.assertEqual(sample["cpu"]["percent"], 45.0)
        self.assertEqual(sample["cpu"]["iowait"], 5.0)
        self.assertEqual(sample["cpu"]["steal"], 5.0)

    def test_older_kernel_four_counter_cpu_rows_are_supported(self):
        calc = MetricCalculator()
        calc.update(parse_frame(frame(cpu="100 20 30 400")), timestamp=1)
        sample = calc.update(parse_frame(frame(cpu="110 20 40 430", uptime="102")), timestamp=3)
        self.assertEqual(sample["cpu"]["percent"], 40.0)

    def test_cpu_baseline_resets_on_reboot_counter_rollback_and_hotplug(self):
        for changes in (
            {"boot": "boot-two"},
            {"uptime": "99"},
            {"cpu": "99 20 40 450 55 15 25 10 45 11"},
            {"cores": 3},
        ):
            with self.subTest(changes=changes):
                calc = MetricCalculator()
                calc.update(parse_frame(frame()), timestamp=1)
                args = {"cpu": "120 20 40 450 55 15 25 10 45 11", "uptime": "102"}
                args.update(changes)
                self.assertIsNone(calc.update(parse_frame(frame(**args)), timestamp=3)["cpu"]["percent"])

    def test_nonpositive_time_or_counter_delta_is_unknown(self):
        for uptime, timestamp, counters in (
            ("100", 3, "120 20 40 450 55 15 25 10 45 11"),
            ("102", 1, "120 20 40 450 55 15 25 10 45 11"),
            ("102", 3, "100 20 30 400 50 10 20 5 25 2"),
        ):
            with self.subTest(uptime=uptime, timestamp=timestamp):
                calc = MetricCalculator()
                calc.update(parse_frame(frame()), timestamp=1)
                self.assertIsNone(calc.update(parse_frame(frame(cpu=counters, uptime=uptime)), timestamp=timestamp)["cpu"]["percent"])

    def test_memory_uses_memavailable_instead_of_free(self):
        sample = MetricCalculator().update(parse_frame(frame()), timestamp=1)
        self.assertEqual(sample["memory"], {"percent": 60.0, "used": 600 * 1024, "total": 1000 * 1024, "available": 400 * 1024})

    def test_memory_fallback_subtracts_shared_cache_once(self):
        # Fallback available = free+buffers+cached+SReclaimable-Shmem = 370 KiB.
        sample = MetricCalculator().update(parse_frame(frame(available=None)), timestamp=1)
        self.assertEqual(sample["memory"]["available"], 370 * 1024)
        self.assertEqual(sample["memory"]["percent"], 63.0)

    def test_memory_races_are_clamped_and_zero_total_is_unknown(self):
        sample = MetricCalculator().update(parse_frame(frame(available="1001")), timestamp=1)
        self.assertEqual(sample["memory"]["percent"], 0.0)
        source = frame().replace("MemTotal: 1000 kB", "MemTotal: 0 kB")
        self.assertIsNone(MetricCalculator().update(parse_frame(source), timestamp=1)["memory"]["percent"])

    def test_swap_usage_and_disabled_swap_are_distinct_from_missing(self):
        sample = MetricCalculator().update(parse_frame(frame()), timestamp=1)
        self.assertEqual(sample["swap"], {"percent": 25.0, "used": 50 * 1024, "total": 200 * 1024, "enabled": True})
        disabled = MetricCalculator().update(parse_frame(frame(swap_total="0", swap_free="0")), timestamp=1)
        self.assertEqual(disabled["swap"], {"percent": 0.0, "used": 0, "total": 0, "enabled": False})
        missing = MetricCalculator().update(parse_frame(""), timestamp=1)
        self.assertIsNone(missing["swap"]["enabled"])

    def test_df_uses_available_plus_used_and_preserves_space_in_paths(self):
        sample = MetricCalculator().update(parse_frame(frame()), timestamp=1)
        self.assertEqual(sample["disk"], {
            "percent": 66.7, "used": 600 * 1024, "total": 1000 * 1024,
            "available": 300 * 1024, "path": "/srv/data archive", "device": "/dev/vda1",
        })

    def test_df_negative_available_can_exceed_100_percent(self):
        sample = MetricCalculator().update(parse_frame(frame(disk="/dev/vda1 1000 950 -10 102% /")), timestamp=1)
        self.assertEqual(sample["disk"]["percent"], 101.1)
        self.assertEqual(sample["disk"]["available"], -10 * 1024)

    def test_df_failure_leaves_other_metrics_available(self):
        sample = MetricCalculator().update(parse_frame(frame(disk=None)), timestamp=1)
        self.assertIsNone(sample["disk"]["percent"])
        self.assertEqual(sample["disk"]["path"], "/srv/data archive")
        self.assertEqual(sample["memory"]["percent"], 60.0)

    def test_does_not_modify_raw_inputs(self):
        calc = MetricCalculator()
        raw = parse_frame(frame())
        original = copy.deepcopy(raw)
        calc.update(raw, timestamp=1)
        self.assertEqual(raw, original)


class ProbeTests(unittest.TestCase):
    def test_probe_rejects_nonabsolute_and_control_character_paths(self):
        for path in ("relative", "-help", "", "/bad\npath", "/bad\x00path", "/bad\tpath", "/bad\rpath"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    build_probe(2, path)

    def test_probe_rejects_invalid_intervals(self):
        for interval in (0, -1, True, 1.5, "2"):
            with self.subTest(interval=interval):
                with self.assertRaises(ValueError):
                    build_probe(interval, "/")

    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("sh") and Path("/proc/stat").exists(), "live probe requires Linux procfs and sh")
    def test_remote_script_quotes_metacharacters_and_survives_df_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "should-not-exist"
            path = "/nonexistent path'; touch '" + str(marker) + "'; # $(printf escaped)"
            script = build_probe(1, path)
            syntax = subprocess.run(["sh", "-n"], input=script, text=True, capture_output=True, timeout=5)
            self.assertEqual(syntax.returncode, 0, syntax.stderr)
            process = subprocess.Popen(["sh", "-s"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            try:
                stdout, stderr = process.communicate(input=script, timeout=2.6)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=5)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate(timeout=5)
            self.assertFalse(marker.exists(), "disk path was executed as shell input")
            sections = stdout.split("__SM_BEGIN__\n")[1:]
            frames = [section.split("__SM_END__", 1)[0] for section in sections if "__SM_END__" in section]
            self.assertGreaterEqual(len(frames), 2, stdout + stderr)
            calc = MetricCalculator()
            samples = [calc.update(parse_frame(item), timestamp=10 + i) for i, item in enumerate(frames)]
            self.assertGreater(samples[-1]["memory"]["total"], 0)
            self.assertTrue(math.isfinite(samples[-1]["cpu"]["percent"]))
            self.assertIsNone(samples[-1]["disk"]["percent"])
            self.assertEqual(samples[-1]["disk"]["path"], path)
            self.assertIn("disk", stderr.lower())

    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("sh") and Path("/proc/stat").exists(), "live probe requires Linux procfs and sh")
    def test_hung_df_without_timeout_does_not_stop_other_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            bin_path = Path(directory)
            for command in ("awk", "cat", "uname", "sleep"):
                (bin_path / command).symlink_to(shutil.which(command))
            # Native sleep replaces df itself; this models a stuck syscall
            # without making an unrelated descendant own stdout forever.
            fake_df = bin_path / "df"
            fake_df.write_text("#!/bin/sh\nprintf 'DF_PID=%s\\n' \"$$\" >&2\nexec sleep 60\n", encoding="utf-8")
            fake_df.chmod(0o755)
            environment = dict(os.environ, PATH=str(bin_path))
            process = subprocess.Popen([shutil.which("sh"), "-s"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, start_new_session=True, env=environment)
            try:
                stdout, stderr = process.communicate(input=build_probe(1, "/"), timeout=4.6)
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
            self.assertGreaterEqual(stdout.count("__SM_END__"), 2, stdout + stderr)
            self.assertIn("disk data unavailable", stderr)
            self.assertEqual(stderr.count("DF_PID="), 1, "df was retried excessively")
            pid = int(next(line.split("=", 1)[1] for line in stderr.splitlines() if line.startswith("DF_PID=")))
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("sh") and Path("/proc/stat").exists(), "live probe requires Linux procfs and sh")
    def test_sampler_exits_when_the_ssh_stdout_pipe_closes(self):
        process = subprocess.Popen(["sh", "-s"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
        try:
            process.stdin.write(build_probe(1, "/"))
            process.stdin.close()
            for line in process.stdout:
                if line.strip() == "__SM_END__":
                    break
            process.stdout.close()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.fail("sampler kept running after its stdout pipe closed")
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()


if __name__ == "__main__":
    unittest.main()
