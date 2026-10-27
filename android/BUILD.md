# 安卓构建

安卓界面来自 `../static/`，以本地 WebView 运行。网络同步由原生 WebDAV 桥访问用户自己的坚果云，不需要电脑或 Python 服务。

需要：JDK 17、Android platform 35、build-tools 35.0.0；脚本使用 aapt2、javac、d8、zipalign、apksigner，不依赖 Gradle。

准备以下 Maven Central 依赖的 JAR，放进同一个本地目录：

- `com.squareup.okhttp3:okhttp:4.12.0`
- `com.squareup.okio:okio-jvm:3.6.0`
- `org.jetbrains.kotlin:kotlin-stdlib:1.9.10`
- `org.jetbrains:annotations:13.0`

```bash
JAVA_HOME=/path/to/jdk-17 \
ANDROID_HOME=/path/to/android-sdk \
ANDROID_LIBS=/path/to/jars \
bash android/build.sh
```

输出 `android/dist/personal-dashboard-1.0.0.apk`。最低 Android 8.0，目标 API 35，签名 v2/v3。

首次自行编译会生成自己的私密签名文件；`android/signing/` 必须留在本机。使用自己的密钥签名后不能直接覆盖他人签名的安装包，请先导出数据再迁移。

维护者升级版本时沿用原签名密钥并递增 Manifest 的 `versionCode`。将 APK 连同第三方许可打成安卓发布 ZIP：

```bash
python3 tools/package_release.py --output ../release-artifacts \
  --apk android/dist/personal-dashboard-1.0.0.apk
```

不要把编译目录、签名目录、用户 `data/` 放入仓库或发布包。第三方许可见仓库 `THIRD_PARTY_NOTICES.md` 和 `licenses/`。
