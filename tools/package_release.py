#!/usr/bin/env python3
"""Build source/desktop and Android ZIPs from the audited explicit allowlist."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import zipfile
from check_release import ROOT, scan_bytes, source_files


def verify_apk(apk, files):
    expected_assets = {'assets/' + Path(n).name: b for n, b in files.items() if n.startswith('static/')}
    with zipfile.ZipFile(apk) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or z.testzip() is not None:
            raise ValueError('Invalid/duplicate APK entries')
        fixed = {'AndroidManifest.xml', 'resources.arsc', 'res/drawable/app_icon.xml', 'META-INF/MANIFEST.MF'}
        for info in z.infolist():
            name = info.filename
            allowed = (name in fixed or name in expected_assets or
                       re.fullmatch(r'classes(?:[2-9][0-9]*)?\.dex', name) or
                       re.fullmatch(r'META-INF/[A-Z0-9_-]+\.(?:SF|RSA|DSA|EC)', name))
            if not allowed or info.file_size > 8 * 1024 * 1024:
                raise ValueError(f'Unreviewed APK entry: {name}')
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('APK contains a symlink')
            scan_bytes('APK/' + name, z.read(name), binary=True)
        if not {'AndroidManifest.xml', 'resources.arsc', 'classes.dex'} <= set(names):
            raise ValueError('APK is missing required Android entries')
        for name, expected in expected_assets.items():
            if name not in names or z.read(name) != expected:
                raise ValueError(f'APK frontend does not match audited source: {name}')
    # Integrity/entry checks are not a substitute for apksigner verification.


def write_zip(path, files):
    executable = {'start.sh', 'android/build.sh', '.githooks/pre-commit'}
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo('personal-dashboard/' + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | (0o755 if name in executable else 0o644)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--apk', type=Path, help='Already verified, signed APK; optional for desktop-only builds')
    args = parser.parse_args()
    files = source_files()
    version = json.loads(files['package.json'])['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid package version')
    if args.apk:
        verify_apk(args.apk, files)
    args.output.mkdir(parents=True, exist_ok=True)
    paths = [args.output / f'personal-dashboard-desktop-{version}.zip']
    write_zip(paths[0], files)
    if args.apk:
        android_files = {n: b for n, b in files.items()
                         if n in {'README.md', 'THIRD_PARTY_NOTICES.md', 'docs/使用说明.md'} or n.startswith('licenses/')}
        android_files[f'personal-dashboard-{version}.apk'] = args.apk.read_bytes()
        paths.append(args.output / f'personal-dashboard-android-{version}.zip')
        write_zip(paths[-1], android_files)
    sums = ''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in paths)
    (args.output / 'SHA256SUMS').write_text(sums, encoding='ascii')
    print(sums, end='')
    print('Ready: reviewed source only; each new installation starts with an empty database.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        raise SystemExit(f'Packaging FAILED: {error}')
