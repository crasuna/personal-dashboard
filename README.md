# 日常面板 Personal Dashboard

一个简洁的个人日程、课程和记账工具。支持 **Windows / macOS / Linux 本地使用**，以及 **安卓离线使用 + 可选坚果云同步**。

**发布文件不包含作者的日程、账本、课程、云账号或密码。首次安装是空数据；每个人使用自己的数据和同步账号。**

## 下载与开始使用

👉 **[前往 Releases 下载](https://github.com/skc111/personal-dashboard/releases/latest)**

| 设备 | 下载什么 | 怎么打开 |
| --- | --- | --- |
| Windows 电脑 | `personal-dashboard-desktop-1.0.0.zip` | 解压完整文件夹，安装 Python 3.10+，双击 `Start-Dashboard.cmd` |
| macOS / Linux | 同一份电脑版 ZIP，或克隆源码 | 在文件夹里运行 `python3 launch.py` |
| 安卓手机 | `personal-dashboard-android-1.0.0.zip` | 解压，安装其中的 APK；需要 Android 8.0+ 及较新的系统 WebView |

Windows **不需要 WSL、Node.js 或数据库软件**。Python 可从 [官网](https://www.python.org/downloads/windows/) 安装；确保安装 Python 启动器或加入 PATH。

第一次启动成功后，可双击 `Start-Dashboard.vbs` 隐藏控制台启动。想放到桌面，请为它**创建快捷方式**，不要把 VBS 单独移出项目文件夹。

默认网址是 `http://127.0.0.1:8787`。启动器会等待服务就绪再打开浏览器；若端口属于另一个程序/另一份面板，会报错而不是结束它。可换端口：

```bash
python3 launch.py --port 8790
```

## 功能

- **今日仪表盘**：日程、收支、课程、近期 DDL、时钟。
- **日程**：日期选择、按时间排列、起止时间、优先级、重复安排、完成状态。
- **课程卡片**：考试要求、知识点、问题、复习资料链接。
- **记账**：收入/支出、分类统计、日支出图、按城市分开的旅行账本、CSV 导出。
- **DDL**：截止日期/时间、完成状态、首页提醒。
- **每日回顾 / 周报**：生成、编辑、保存回顾，查看统计。
- **深色模式、完整 JSON 备份与合并导入**。
- **可选双端同步**：两端前台约每 15 秒检查一次；离线先保存，联网后再合并；冲突保留版本待核对。

## 手机与电脑同步（可选）

不需要自购服务器。使用自己的坚果云账号提供 WebDAV 存储：

1. 在坚果云创建**应用密码**，不要使用登录密码。[官方教程](https://help.jianguoyun.com/?p=2064)
2. 电脑右上角「仅本地」或「设置 → 多设备同步」，填自己的邮箱和应用密码。
3. 手机填写**相同账号、相同文件夹**；两端可以使用各自的应用密码。
4. 等待「已同步」，用一条测试记录确认双向更新。

**不要与朋友共享同一个同步账号/文件夹，否则记录会被合并。** 朋友应注册自己的账号。

电脑关机不会影响手机。手机后台/锁屏时不保证即时同步，重新打开会补同步。坚果云免费版有流量和请求频率限制，以服务商当前规则为准。

## 数据与安全

- 电脑版运行时才创建 `data/db.json`；自动备份位于 `data/backups/`。
- 电脑凭据存于本地 `data/sync-config.json`，不进入网页 JSON 导出或公开发布包。Windows 上仍需保护好个人用户目录。
- 浏览器有 IndexedDB 离线缓存；安卓记录在应用私有目录，凭据由 Android Keystore 加密。
- 数据保留在设备/你自己的坚果云，不上传到本 GitHub 仓库，也没有作者运营的后台。
- **目前没有端到端加密**。不要公开分享同步目录。
- 卸载安卓应用、清除应用/浏览器数据前，先确认同步成功并导出备份。
- JSON 导入默认合并，不清空现有内容；同一记录并发修改会保留待核对版本。
- 一份同步文件最多 15MB。外部资料链接指向的附件不自动下载。
- 这是本机应用，**不要直接暴露 Python 服务到公网**；GitHub Pages 也不能替代 Python 后端。

更多说明：[使用与备份](docs/使用说明.md)、[发布隐私检查](docs/发布说明.md)。

## 开发与测试

电脑版后端只使用 Python 标准库。普通用户不需要安装 npm 依赖。

```bash
python3 server.py                 # 前台运行；Ctrl+C 停止
python3 -m unittest discover -s tests -p 'test_*.py'
node tests/sync-core.test.js

# 可选浏览器回归测试：使用临时空库和随机端口，不修改日常记录
npm ci
npx playwright install chromium
npm run test:browser
```

安卓源码和构建步骤在 [android/BUILD.md](android/BUILD.md)。安卓 ZIP 内的 APK 为同版本已签名安装包；签名私钥不公开。

首次公开分享版经过算法、API、空库启动和模拟双端测试；设备厂商 WebView、网络和真实 WebDAV 账号可能有差异，遇到问题请提交脱敏后的报错，**不要上传自己的 db.json 或密码**。

## 第三方组件

安卓使用 OkHttp、Okio、Kotlin 标准库及 JetBrains annotations，相关许可与通知见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 `licenses/`。该文件仅说明第三方组件许可，不替代本项目自身的许可证选择。
