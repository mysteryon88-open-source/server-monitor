import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def test_help_works_from_another_directory(self):
        result = subprocess.run([sys.executable, str(ROOT / 'server.py'), '--help'],
                                cwd=tempfile.gettempdir(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--demo', result.stdout)

    def test_check_validates_locally_without_contacting_fake_server(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'test.env'
            config.write_text('LANGUAGE=en\n', encoding='utf-8')
            servers = Path(directory) / 'servers.json'
            servers.write_text('{"Test":"not-a-real-host.invalid", "Other":"other.invalid"}', encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT / 'server.py'), '--env', str(config),
                                     '--servers', str(servers), '--check'],
                                    cwd=directory, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('No SSH connection', result.stdout)
            self.assertIn('Servers: 2', result.stdout)
            self.assertIn('Language: en', result.stdout)

    def test_bad_alias_gives_useful_exit_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'test.env'
            config.write_text('', encoding='utf-8')
            servers = Path(directory) / 'servers.json'
            servers.write_text('{"Test":"-oBad"}', encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT / 'server.py'), '--env', str(config),
                                     '--servers', str(servers), '--check'],
                                    capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('SSH alias', result.stderr)
            self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
