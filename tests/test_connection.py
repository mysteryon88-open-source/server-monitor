import io
import tempfile
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from monitor.config import Config
from monitor.connection import SSHMonitor, build_ssh_command, iter_frames, describe_ssh_error, write_probe_script
from monitor.state import MonitorState


class ConnectionTests(unittest.TestCase):
    def test_linux_probe_keeps_lf_even_with_windows_text_pipe_translation(self):
        raw = io.BytesIO()
        # Model exactly the newline translation of subprocess text pipes on Windows.
        stream = io.TextIOWrapper(raw, encoding='utf-8', newline='\r\n')
        script = 'LANG=C\nprintf "café\\n"\n'
        write_probe_script(stream, script)
        self.assertEqual(raw.getvalue(), script.encode('utf-8'))
        stream.detach()

    def test_shell_free_command_preserves_alias_and_config_path(self):
        root = Path('C:/folder with spaces')
        cfg = Config(root, 'root-prod', ssh_config=root / 'my config')
        cmd = build_ssh_command(cfg, 'ssh', root / 'ssh.log')
        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd[-2:], ['root-prod', 'sh -s'])
        self.assertIn('StrictHostKeyChecking=ask', cmd)
        self.assertIn('ForwardAgent=no', cmd)
        self.assertIn('PermitLocalCommand=no', cmd)
        self.assertIn('ControlPath=none', cmd)
        self.assertIn('BatchMode=no', cmd)
        self.assertEqual(cmd[cmd.index('-F') + 1], str(root / 'my config'))

    def test_new_ssh_options_are_declared_optional_for_older_windows_openssh(self):
        cmd = build_ssh_command(Config(Path('.'), 'prod'), 'ssh', Path('ssh.log'))
        self.assertIn('IgnoreUnknown=StdinNull,SessionType,ForkAfterAuthentication', cmd)
        self.assertLess(cmd.index('IgnoreUnknown=StdinNull,SessionType,ForkAfterAuthentication'),
                        cmd.index('StdinNull=no'))
        self.assertIn('SessionType=default', cmd)
        self.assertIn('ForkAfterAuthentication=no', cmd)

    def test_framing_ignores_banners_and_never_joins_partial_samples(self):
        text = 'Welcome\n__SM_BEGIN__\nold\n__SM_BEGIN__\nreal\n__SM_END__\nnoise\n__SM_BEGIN__\npartial'
        self.assertEqual(list(iter_frames(io.StringIO(text))), ['real\n'])

    def test_framing_has_size_limit(self):
        with self.assertRaises(ValueError):
            list(iter_frames(io.StringIO('__SM_BEGIN__\n' + 'x' * 70000 + '\n__SM_END__\n')))

    def test_errors_have_actionable_messages_without_log_dump(self):
        self.assertIn('key', describe_ssh_error('Permission denied (publickey).').lower())
        self.assertIn('known_hosts', describe_ssh_error('Host key verification failed.'))
        self.assertIn('alias', describe_ssh_error('Could not resolve hostname x').lower())
        self.assertNotIn('secret/private/path', describe_ssh_error('weird secret/private/path text'))

    def test_thread_start_failure_terminates_spawned_ssh_and_releases_authentication(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = SSHMonitor(Config(Path(directory), 'fixture'), MonitorState('fixture', 2), 'unused')
            process = Mock()
            process.poll.return_value = None
            process.stdin.closed = False
            with patch('monitor.connection.subprocess.Popen', return_value=process), \
                    patch('monitor.connection.threading.Thread.start', side_effect=RuntimeError('cannot start thread')):
                with self.assertRaisesRegex(RuntimeError, 'cannot start thread'):
                    monitor._session()
            process.terminate.assert_called_once()
            process.wait.assert_called_once()
            process.stdout.close.assert_called_once()
            process.stdin.close.assert_called_once()
            self.assertIsNone(monitor._process)
            self.assertTrue(monitor._authentication_lock.acquire(timeout=0.1))
            monitor._authentication_lock.release()


if __name__ == '__main__':
    unittest.main()
