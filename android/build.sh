#!/usr/bin/env bash
# Reproducible, dependency-light APK build with official Android SDK tools.
set -euo pipefail
cd "$(dirname "$0")"
: "${JAVA_HOME:?Set JAVA_HOME to JDK 17}"
: "${ANDROID_HOME:?Set ANDROID_HOME to Android SDK}"
: "${ANDROID_LIBS:?Directory containing pinned OkHttp / Kotlin JAR dependencies}"
export PATH="$JAVA_HOME/bin:$PATH"
BT="$ANDROID_HOME/build-tools/35.0.0"
JAR="$ANDROID_HOME/platforms/android-35/android.jar"
VERSION=$(python3 - <<'VERSION_PY'
import json,re,xml.etree.ElementTree as ET
version=ET.parse('AndroidManifest.xml').getroot().get('{http://schemas.android.com/apk/res/android}versionName')
if not re.fullmatch(r'\d+\.\d+\.\d+',version or '') or version!=json.load(open('../package.json'))['version']:
    raise SystemExit('Manifest and package version must match (major.minor.patch).')
print(version)
VERSION_PY
)
APK="dist/personal-dashboard-$VERSION.apk"
OUT="$PWD/build"
mkdir -p "$OUT/classes" "$OUT/gen" "$OUT/dex" "$PWD/signing" "$PWD/dist"
chmod 700 "$PWD/signing"
if [ ! -f signing/release.jks ]; then
  if [ -f signing/password.txt ]; then echo 'Signing key missing; refusing to replace identity.' >&2; exit 1; fi
  python3 -c 'import secrets,pathlib; p=pathlib.Path("signing/password.txt");p.write_text(secrets.token_urlsafe(36));p.chmod(0o600)'
  keytool -genkeypair -keystore signing/release.jks -storetype JKS -alias dashboard -keyalg RSA -keysize 3072 -validity 36500 -dname 'CN=Personal Dashboard,OU=Personal,O=Local,C=CN' -storepass:file signing/password.txt -keypass:file signing/password.txt
  chmod 600 signing/release.jks
fi
"$BT/aapt2" compile --dir res -o "$OUT/resources.zip"
"$BT/aapt2" link -o "$OUT/base.apk" -I "$JAR" --manifest AndroidManifest.xml --java "$OUT/gen" -A ../static "$OUT/resources.zip"
CP=$(printf '%s:' "$ANDROID_LIBS"/*.jar); CP=${CP%:}
find src "$OUT/gen" -name '*.java' > "$OUT/sources.txt"
javac -encoding UTF-8 -source 8 -target 8 -bootclasspath "$BT/core-lambda-stubs.jar:$JAR" -classpath "$CP" -d "$OUT/classes" @"$OUT/sources.txt"
jar cf "$OUT/classes.jar" -C "$OUT/classes" .
"$BT/d8" --release --min-api 26 --lib "$JAR" --output "$OUT/dex" "$OUT/classes.jar" "$ANDROID_LIBS"/*.jar
python3 - "$OUT" <<'PY'
import sys,zipfile,pathlib,shutil
p=pathlib.Path(sys.argv[1]);shutil.copy2(p/'base.apk',p/'unsigned.apk')
with zipfile.ZipFile(p/'unsigned.apk','a',zipfile.ZIP_DEFLATED) as z:
    for f in (p/'dex').glob('*.dex'): z.write(f,f.name)
PY
"$BT/zipalign" -P 16 -f 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"
"$BT/apksigner" sign --ks signing/release.jks --ks-key-alias dashboard --ks-pass file:signing/password.txt --out "$APK" "$OUT/aligned.apk"
"$BT/apksigner" verify --verbose "$APK"
sha256sum "$APK" > dist/SHA256SUMS
echo "APK: $PWD/$APK"
