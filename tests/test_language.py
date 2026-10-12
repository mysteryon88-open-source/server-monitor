"""Publication text stays English outside the interface localization."""

from pathlib import Path
import unittest


class PublicationLanguageTests(unittest.TestCase):
    def test_cyrillic_is_confined_to_frontend_localization(self):
        root = Path(__file__).resolve().parent.parent
        files = [root / name for name in (
            'README.md', 'AGENTS.md', 'server.py', 'start.cmd', 'start.ps1',
            '.env.example', 'servers.json.example',
        )]
        for pattern in ('docs/**/*.md', 'monitor/*.py', 'monitor/*.sh',
                        'tests/*.py', 'tests/*.cjs', 'static/*.html',
                        'static/*.css', 'static/*.svg'):
            files.extend(root.glob(pattern))
        for path in files:
            with self.subTest(file=str(path.relative_to(root))):
                self.assertNotRegex(path.read_text(encoding='utf-8'),
                                    r'[\u0400-\u052f]')


if __name__ == '__main__':
    unittest.main()
