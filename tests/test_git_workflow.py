"""Exercise ignore rules and the real commit hook with synthetic private files."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from check_release import source_files


class GitWorkflowTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('git'), 'Git is needed to test commit protection')
    def test_add_all_excludes_runtime_files_and_hook_blocks_forced_add(self):
        with tempfile.TemporaryDirectory(prefix='dashboard-git-test-') as temp:
            root = Path(temp)
            for name, data in source_files(ROOT).items():
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            (root / '.githooks/pre-commit').chmod(0o755)

            def git(*args, check=True):
                return subprocess.run(['git', *args], cwd=root, check=check,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            git('init', '-q')
            git('config', 'user.name', 'Synthetic Test')
            git('config', 'user.email', 'test@example.invalid')
            git('config', 'core.hooksPath', '.githooks')
            git('config', 'commit.gpgsign', 'false')
            private = ['data/db.json', 'data/sync-config.json', 'data/backups/snapshot.json',
                       'android/signing/release.jks', 'android/signing/password.txt',
                       'android/dist/example.apk', '.env', 'notes.csv', 'export.json',
                       '启动面板.vbs', '手机与电脑同步使用说明.md', '.local/notes.txt']
            for name in private:
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b'synthetic private fixture, not real user data')
                self.assertEqual(git('check-ignore', '--quiet', '--', name, check=False).returncode, 0, name)
            git('add', '.')
            tracked = set(git('ls-files', '-z').stdout.decode().split('\0')) - {''}
            self.assertTrue(set(private).isdisjoint(tracked))
            self.assertIn('package.json', tracked)
            self.assertIn('package-lock.json', tracked)
            git('commit', '-qm', 'Synthetic clean source')
            self.assertTrue(all((root / name).is_file() for name in private))

            # A forced add must be stopped by the hook, not silently published.
            git('add', '-f', '--', 'data/db.json')
            blocked = git('commit', '-qm', 'Must be rejected', check=False)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn(b'Index differs', blocked.stdout + blocked.stderr)
            self.assertEqual(git('rev-list', '--count', 'HEAD').stdout.strip(), b'1')
            self.assertTrue((root / 'data/db.json').is_file())


if __name__ == '__main__':
    unittest.main()
