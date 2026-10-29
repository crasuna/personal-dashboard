"""Check the real OS permissions independently of the storage implementation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sync_bridge import SyncBridge, atomic_private


def assert_private(case, path, *, directory=False):
    if os.name != 'nt':
        case.assertEqual(path.stat().st_mode & 0o777, 0o700 if directory else 0o600)
        return
    # Independent reader: .NET Get-Acl, rather than the writer's ctypes helpers.
    script = r"""
        $ErrorActionPreference = 'Stop'
        [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
        # Do not inherit PowerShell 7 module paths into Windows PowerShell 5.1.
        $env:PSModulePath = "$PSHOME\Modules"
        $acl = Get-Acl -LiteralPath $env:DASHBOARD_ACL_TEST_PATH
        $rules = @($acl.Access | ForEach-Object {
            @{
                sid = $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
                type = [string]$_.AccessControlType
                rights = [int]$_.FileSystemRights
                inherited = $_.IsInherited
                inheritance = [int]$_.InheritanceFlags
                propagation = [int]$_.PropagationFlags
            }
        })
        @{
            user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            protected = $acl.AreAccessRulesProtected
            rules = $rules
        } | ConvertTo-Json -Depth 4 -Compress
    """
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
        env={**os.environ, 'DASHBOARD_ACL_TEST_PATH': str(path)},
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        creationflags=subprocess.CREATE_NO_WINDOW)
    case.assertEqual(result.returncode, 0, result.stderr)
    acl = json.loads(result.stdout)
    case.assertTrue(acl['protected'], 'Must not inherit broad parent permissions')
    expected = {acl['user'], 'S-1-5-18', 'S-1-5-32-544'}
    case.assertEqual({rule['sid'] for rule in acl['rules']}, expected)
    case.assertEqual(len(acl['rules']), len(expected))
    for rule in acl['rules']:
        case.assertEqual(rule['type'], 'Allow')
        case.assertEqual(rule['rights'], 0x1F01FF)  # FullControl
        case.assertFalse(rule['inherited'])
        case.assertEqual(rule['inheritance'], 3 if directory else 0)
        case.assertEqual(rule['propagation'], 0)


class PrivateFilesTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows filesystem capability check')
    def test_filesystem_without_acl_support_refuses_credentials(self):
        import ctypes
        load_library = ctypes.WinDLL
        kernel = Mock()
        kernel.GetVolumePathNameW.return_value = 1
        # Success, but the output flags remain zero: no FILE_PERSISTENT_ACLS.
        kernel.GetVolumeInformationW.return_value = 1

        def library(name, **kwargs):
            return kernel if name == 'kernel32' else load_library(name, **kwargs)

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'no-acl' / 'sync-config.json'
            with patch('ctypes.WinDLL', side_effect=library):
                with self.assertRaisesRegex(PermissionError, 'persistent Windows ACLs'):
                    atomic_private(path, {'password': 'synthetic-only'})
            self.assertFalse(path.exists())
            self.assertEqual(list(path.parent.iterdir()), [])

    def test_atomic_create_and_replace_protect_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'private-store' / 'sync-config.json'
            original_dump = json.dump

            def checked_dump(value, stream, **kwargs):
                assert_private(self, path.parent, directory=True)
                candidates = list(path.parent.glob('sync-config.json.*'))
                self.assertEqual(len(candidates), 1)
                self.assertEqual(candidates[0].stat().st_size, 0)
                assert_private(self, candidates[0])
                return original_dump(value, stream, **kwargs)

            for password in ('synthetic-first', 'synthetic-update'):
                with patch('sync_bridge.json.dump', side_effect=checked_dump):
                    atomic_private(path, {'password': password})
                self.assertEqual(json.loads(path.read_text(encoding='utf-8')),
                                 {'password': password})
                assert_private(self, path)
                self.assertEqual(list(path.parent.glob('sync-config.json.*')), [])

    def test_legacy_config_is_restricted_before_use(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / 'legacy'
            data.mkdir()
            path = data / 'sync-config.json'
            old = {'enabled': False, 'email': '', 'folder': 'old', 'password': 'synthetic'}
            path.write_text(json.dumps(old), encoding='utf-8')
            if os.name != 'nt':
                path.chmod(0o644)
            original = path.read_bytes()
            self.assertEqual(SyncBridge(data).config(), old)
            self.assertEqual(path.read_bytes(), original)
            assert_private(self, data, directory=True)
            assert_private(self, path)

    def test_protection_failure_preserves_old_config_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'private-store' / 'sync-config.json'
            atomic_private(path, {'password': 'synthetic-old'})
            original = path.read_bytes()

            def refuse_file(target, *, directory=False):
                if not directory:
                    raise PermissionError('Synthetic ACL failure')

            with patch('sync_bridge.protect_private', side_effect=refuse_file):
                with self.assertRaises(PermissionError):
                    atomic_private(path, {'password': 'synthetic-new'})
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(path.parent.glob('sync-config.json.*')), [])


if __name__ == '__main__':
    unittest.main()
