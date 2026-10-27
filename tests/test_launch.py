"""Portable-launcher integration tests, always on a temporary empty store."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import launch
import server


class LaunchTests(unittest.TestCase):
    def test_start_empty_reuse_and_refuse_other_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / 'empty'
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1', 0))
                port = reservation.getsockname()[1]
            children = []
            original = subprocess.Popen

            def spawn(*args, **kwargs):
                child = original(*args, **kwargs)
                children.append(child)
                return child

            try:
                with patch.object(server, 'DATA_DIR', data), \
                     patch.dict(os.environ, {'DASHBOARD_DATA_DIR': str(data)}), \
                     patch.object(sys, 'argv', ['launch.py', '--port', str(port), '--no-browser']), \
                     patch.object(launch.subprocess, 'Popen', side_effect=spawn), \
                     redirect_stdout(io.StringIO()):
                    launch.main()
                    self.assertEqual(len(children), 1)
                    self.assertIsNone(children[0].poll())
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with opener.open(f'http://127.0.0.1:{port}/api/data', timeout=3) as r:
                        db = json.load(r)
                    for name in ('todos', 'courses', 'subjects', 'transactions', 'deadlines', 'trips', 'studies'):
                        self.assertEqual(db[name], [], name)
                    self.assertEqual(db['reviews'], {})
                    self.assertFalse((data / 'sync-config.json').exists())
                    original_db = (data / 'db.json').read_bytes()
                    launch.main()
                    self.assertEqual(len(children), 1, 'Same copy must reuse its existing service')
                    with patch.object(server, 'DATA_DIR', Path(temp) / 'different'):
                        with self.assertRaisesRegex(RuntimeError, 'another service or dashboard copy'):
                            launch.main()
                    self.assertEqual(len(children), 1)
                    self.assertIsNone(children[0].poll(), 'A port conflict must not kill the existing service')
                    self.assertEqual((data / 'db.json').read_bytes(), original_db)
            finally:
                for child in children:
                    if child.poll() is None:
                        child.terminate()
                        child.wait(timeout=8)

    def test_invalid_port(self):
        with patch.object(sys, 'argv', ['launch.py', '--port', '0', '--no-browser']):
            with self.assertRaisesRegex(RuntimeError, 'port from'):
                launch.main()


if __name__ == '__main__':
    unittest.main()
