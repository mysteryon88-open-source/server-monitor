import tempfile
import unittest
from pathlib import Path

from monitor.config import ConfigError, load_config, load_servers, parse_env


class ConfigTests(unittest.TestCase):
    def test_bom_quotes_comments_and_literal_backslashes(self):
        values = parse_env('\ufeff# header\nSSH_ALIAS="my-server" # comment\nSSH_CONFIG="C:\\Users\\Me\\.ssh\\config"\nDISK_PATH=\'/data path\'\n')
        self.assertEqual(values['SSH_ALIAS'], 'my-server')
        self.assertEqual(values['SSH_CONFIG'], 'C:\\Users\\Me\\.ssh\\config')
        self.assertEqual(values['DISK_PATH'], '/data path')

    def test_duplicate_and_malformed_lines_fail_clearly(self):
        for content in ('SSH_ALIAS=a\nSSH_ALIAS=b', 'bad line', 'SSH_ALIAS="unterminated'):
            with self.subTest(content=content), self.assertRaises(ConfigError):
                parse_env(content)

    def test_alias_only_produces_valid_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'servers.json').write_text('{"Production": "production"}', encoding='utf-8')
            c = load_config(root, environ={})
            self.assertEqual((c.alias, c.port, c.interval, c.disk_path, c.batch_mode),
                             ('production', 8765, 2, '/', False))
            self.assertEqual(c.servers, {'Production': 'production'})
            self.assertEqual(c.language, 'ru')

    def test_rejects_injection_invalid_range_and_control_characters(self):
        cases = [('PORT', '0'), ('PORT', '65536'),
                 ('INTERVAL', '0'), ('INTERVAL', '1.5'), ('INTERVAL', '61'),
                 ('DISK_PATH', 'relative'), ('DISK_PATH', '/a\x00b'),
                 ('SSH_BATCH_MODE', 'perhaps'), ('LANGUAGE', 'de')]
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'servers.json').write_text('{"Good": "good"}', encoding='utf-8')
            for key, value in cases:
                env = {key: value}
                with self.subTest(key=key, value=value), self.assertRaises(ConfigError):
                    load_config(Path(directory), environ=env)

    def test_demo_does_not_need_alias_or_config_file(self):
        with tempfile.TemporaryDirectory() as directory:
            c = load_config(Path(directory), environ={}, demo=True)
            self.assertTrue(c.demo)

    def test_explicit_missing_config_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'servers.json').write_text('{"Test":"test"}', encoding='utf-8')
            with self.assertRaisesRegex(ConfigError, 'SSH_CONFIG'):
                load_config(Path(directory), environ={'SSH_CONFIG': 'absent'})

    def test_utf8_bom_names_and_env_language(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'servers.json').write_text('\ufeff{"Montréal": "nl", "Backup": "backup"}', encoding='utf-8')
            (root / '.env').write_text('LANGUAGE=ru', encoding='utf-8')
            config = load_config(root, environ={'LANGUAGE': 'en'})
            self.assertEqual(list(config.servers), ['Montréal', 'Backup'])
            self.assertEqual(config.language, 'en')

    def test_server_mapping_rejects_malformed_or_unsafe_data(self):
        cases = ['{}', '[]', 'null', '{"Name":"-oBad"}', '{"Name":"a; echo bad"}',
                 '{"Name":"a b"}', '{"Name":12}', '{"": "good"}',
                 '{"Name":"a", "Name":"b"}', '{"A":"same", "B":"same"}',
                 '{"Bad\\u0000name":"good"}', '{"Bad\\u0085name":"good"}',
                 '{"Bad\\ud800name":"good"}', '{"Bad\\ud800":"a", "Bad\\ud800":"b"}',
                 '{"Name":{"nested":true}}',
                 '{"Name":"good",}', '[' * 2000 + ']' * 2000]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'servers.json'
            for content in cases:
                path.write_text(content, encoding='utf-8')
                with self.subTest(content=content[:80]), self.assertRaises(ConfigError):
                    load_servers(path)
            path.write_text(' ' * 65537, encoding='utf-8')
            with self.assertRaises(ConfigError):
                load_servers(path)

    def test_old_env_alias_has_migration_message(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env').write_text('SSH_ALIAS=old', encoding='utf-8')
            with self.assertRaisesRegex(ConfigError, 'servers.json'):
                load_config(root, environ={})


if __name__ == '__main__':
    unittest.main()
