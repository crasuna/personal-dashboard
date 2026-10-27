# Third-party notices

The desktop application uses the Python standard library. Python is a prerequisite and is not bundled with the desktop ZIP.

The prebuilt Android APK links the following libraries. Their licenses and any packaged notices are included under `licenses/` in the source and release ZIPs.

| Component | Version | Upstream | License |
| --- | --- | --- | --- |
| OkHttp | 4.12.0 | https://github.com/square/okhttp | Apache-2.0 |
| Okio JVM | 3.6.0 | https://github.com/square/okio | Apache-2.0 |
| Kotlin standard library | 1.9.10 | https://github.com/JetBrains/kotlin | Apache-2.0 |
| JetBrains annotations | 13.0 | https://github.com/JetBrains/java-annotations | Apache-2.0 |

These libraries are used without source modifications. Copyright and other notices remain with their respective owners. The Apache License text is in `licenses/Apache-2.0.txt`; additional notices extracted from the distributed JARs are preserved separately when present.

OkHttp's upstream JAR also carries a notice about the Public Suffix List (Mozilla Public License 2.0). That notice is retained in `licenses/okhttp-4.12.0-NOTICE`, with the MPL text in `licenses/MPL-2.0.txt`. The upstream list and its source are available at https://publicsuffix.org/list/ and https://github.com/publicsuffix/list. This notice does not change the license of OkHttp's own code.

Playwright is an optional development/test dependency installed through npm; it is not included in the application download. Its package includes its own license and notices.

These third-party license statements apply only to the listed components, not to a choice of license for the dashboard's own code.
