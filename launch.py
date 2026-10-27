#!/usr/bin/env python3
"""Portable local launcher. Never stop or reuse another project's service."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent


def version_info(port):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f'http://127.0.0.1:{port}/api/version', timeout=1) as response:
            data = json.load(response)
            return data if isinstance(data, dict) else None
    except (OSError, ValueError, urllib.error.URLError):
        return None


def port_busy(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.3):
            return True
    except OSError:
        return False


def main():
    if sys.version_info < (3, 10):
        raise RuntimeError('Python 3.10 or newer is required. Please install it from python.org.')
    parser = argparse.ArgumentParser(description='Start the local personal dashboard')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8787')))
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise RuntimeError('Please choose a port from 1024 to 65535.')
    import server
    identity = server.instance_id()
    running = version_info(args.port)
    if running or port_busy(args.port):
        if not running or running.get('app') != 'personal-dashboard' or running.get('instance') != identity:
            raise RuntimeError(f'Port {args.port} belongs to another service or dashboard copy. '
                               'It has NOT been stopped. Use: python launch.py --port 8790')
        if running.get('version') != server.SCHEMA_VERSION:
            raise RuntimeError('An older server is running. Save/export your edits and restart it first.')
    else:
        server.DATA_DIR.mkdir(parents=True, exist_ok=True)
        environment = {**os.environ, 'HOST':'127.0.0.1', 'PORT':str(args.port)}
        kwargs = {'cwd': str(ROOT), 'env': environment, 'stdin':subprocess.DEVNULL}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs['start_new_session'] = True
        with (server.DATA_DIR / 'server.log').open('ab') as log:
            process = subprocess.Popen([sys.executable, '-u', str(ROOT / 'server.py')],
                                       stdout=log, stderr=log, **kwargs)
        for _ in range(50):
            running = version_info(args.port)
            if running and running.get('app') == 'personal-dashboard' and running.get('instance') == identity:
                break
            if process.poll() is not None:
                raise RuntimeError('The server exited. Check data/server.log; your records were not cleared.')
            time.sleep(.2)
        else:
            raise RuntimeError('The server did not become ready. Check data/server.log.')
    url = f'http://127.0.0.1:{args.port}'
    if not args.no_browser:
        webbrowser.open(url)
    print('Dashboard ready:', url)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        message = 'Personal Dashboard\n\n' + str(error)
        print(message, file=sys.stderr)
        if os.name == 'nt':
            ctypes.windll.user32.MessageBoxW(None, message, 'Personal Dashboard', 0x10)
        sys.exit(1)
