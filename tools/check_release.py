#!/usr/bin/env python3
"""Check only explicitly reviewed source files; never print matched secrets."""
import argparse
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'tools/release-files.txt'
PRIVATE_DIRS = {'data', 'backups', 'recovery', 'signing', '.git', 'node_modules',
                '__pycache__', '.venv', 'venv', 'dist', 'artifacts', 'build'}
PRIVATE_SUFFIXES = {'.apk', '.zip', '.jks', '.keystore', '.pem', '.key', '.p12',
                    '.pfx', '.db', '.sqlite', '.sqlite3', '.csv', '.log', '.bak'}
PATTERNS = {
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
    'GitHub token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'cloud access key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'personal home path': re.compile(r'/(?:home|Users)/[\w.-]+/|[A-Za-z]:[\\/]Users[\\/][\w.-]+[\\/]'),
    'credential in URL': re.compile(r'https?://[^\s/:@]+:[^\s/@]+@'),
}


def safe_path(name):
    p = PurePosixPath(name)
    if not name or '\\' in name or p.is_absolute() or '..' in p.parts or str(p) != name:
        raise ValueError('Unsafe release path')
    if any(part.lower() in PRIVATE_DIRS for part in p.parts):
        raise ValueError(f'Runtime/private directory is forbidden: {name}')
    if p.suffix.lower() in PRIVATE_SUFFIXES or p.name.lower().startswith('.env'):
        raise ValueError(f'Runtime/private file is forbidden: {name}')
    if p.suffix.lower() == '.json' and name not in {'package.json', 'package-lock.json'}:
        raise ValueError(f'Unapproved JSON file: {name}')
    if any(word in p.name.lower() for word in ('password', 'credential', 'secret')):
        raise ValueError(f'Potential credential file: {name}')


def scan_bytes(name, data, binary=False):
    if len(data) > 8 * 1024 * 1024:
        raise ValueError(f'Unexpectedly large file: {name}')
    text = data.decode('utf-8', errors='ignore' if binary else 'strict')
    for kind, pattern in PATTERNS.items():
        if pattern.search(text):
            raise ValueError(f'{kind} detected in {name}; value deliberately not printed')


def source_files(root=ROOT, staged=False):
    root = Path(root)
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE)
    if staged:
        modes = {}
        for entry in git('ls-files', '--stage', '-z').split(b'\0'):
            if not entry:
                continue
            info, name = entry.split(b'\t', 1)
            mode, _sha, stage = info.decode().split()
            name = name.decode('utf-8')
            if stage != '0' or mode not in {'100644', '100755'}:
                raise ValueError(f'Non-regular/unmerged staged file: {name}')
            modes[name] = mode
        read = lambda name: git('show', ':' + name)
    else:
        def read(name):
            p = root / name
            if p.is_symlink() or any(parent.is_symlink() for parent in p.parents if parent != root):
                raise ValueError(f'Symlink is not permitted: {name}')
            return p.read_bytes()
    names = [line.strip() for line in read(MANIFEST).decode('utf-8').splitlines()
             if line.strip() and not line.startswith('#')]
    if MANIFEST not in names or len(set(names)) != len(names):
        raise ValueError('Invalid or duplicate source manifest')
    if staged and set(modes) != set(names):
        extra = sorted(set(modes) - set(names))
        missing = sorted(set(names) - set(modes))
        raise ValueError(f'Index differs from reviewed allowlist. Extra: {extra}; missing: {missing}')
    result = {}
    for name in names:
        safe_path(name)
        data = read(name)
        scan_bytes(name, data)
        result[name] = data
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='Check actual Git index blobs, not working files')
    args = parser.parse_args()
    files = source_files(staged=args.staged)
    print(f'PASS: {len(files)} allowlisted source files; no runtime data or recognized secret patterns.')
    print('Only these files may be published. Manual privacy review is still required.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Release check FAILED: {error}')
