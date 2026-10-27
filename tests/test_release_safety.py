"""The public package must never recursively copy a used installation."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from check_release import MANIFEST, safe_path, scan_bytes, source_files
from package_release import verify_apk, write_zip


class ReleaseSafetyTests(unittest.TestCase):
    def test_runtime_files_forbidden(self):
        for name in ('data/db.json', 'android/signing/release.jks', '.env',
                     'backup.csv', 'sync-config.json', '../escape', '/absolute', 'my-password.txt'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_path(name)

    def test_no_secret_value_in_error_message(self):
        token = 'gh' + 'p_' + 'z' * 36
        with self.assertRaises(ValueError) as caught:
            scan_bytes('demo.txt', token.encode())
        self.assertNotIn(token, str(caught.exception))

    def test_allowlist_only_and_actual_staged_content(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'tools').mkdir()
            (root / MANIFEST).write_text(MANIFEST + '\ndemo.txt\n')
            (root / 'demo.txt').write_text('clean example')
            (root / 'data').mkdir()
            (root / 'data/db.json').write_text('{"private":"do not publish"}')
            self.assertEqual(set(source_files(root)), {MANIFEST, 'demo.txt'})
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(['git', 'add', MANIFEST, 'demo.txt'], cwd=root, check=True)
            (root / 'demo.txt').write_text('working tree is different')
            self.assertEqual(source_files(root, staged=True)['demo.txt'], b'clean example')
            subprocess.run(['git', 'add', 'data/db.json'], cwd=root, check=True)
            with self.assertRaisesRegex(ValueError, 'Index differs'):
                source_files(root, staged=True)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'tools').mkdir()
            (root / MANIFEST).write_text(MANIFEST + '\ndemo.txt\n')
            (root / 'other.txt').write_text('outside allowlist')
            try:
                (root / 'demo.txt').symlink_to(root / 'other.txt')
            except OSError:
                self.skipTest('Symlinks unavailable for this user')
            with self.assertRaisesRegex(ValueError, 'Symlink'):
                source_files(root)

    def test_zip_is_source_only_and_apk_rejects_runtime_data(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'example.zip'
            write_zip(archive, {'README.md': b'empty installation'})
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(z.namelist(), ['personal-dashboard/README.md'])
            bad = Path(temp) / 'bad.apk'
            with zipfile.ZipFile(bad, 'w') as z:
                z.writestr('assets/db.json', '{}')
            with self.assertRaisesRegex(ValueError, 'Unreviewed APK entry'):
                verify_apk(bad, {})


if __name__ == '__main__':
    unittest.main()
