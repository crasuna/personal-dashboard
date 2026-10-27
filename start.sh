#!/usr/bin/env bash
# 个人成长面板启动脚本：
# - 端口空闲 → 直接启动
# - 已运行且版本一致 → 跳过
# - 已运行但版本落后（磁盘代码更新过）→ 自动替换为新版本
cd "$(dirname "$0")" || exit 1

CODE_VER=$(grep -o 'SCHEMA_VERSION = [0-9]*' server.py 2>/dev/null | grep -o '[0-9]*$')
CODE_VER=${CODE_VER:-0}

if timeout 1 bash -c '</dev/tcp/127.0.0.1/8787' 2>/dev/null; then
  RUN_VER=$(timeout 1 curl -s http://127.0.0.1:8787/api/version 2>/dev/null | grep -o '[0-9]*' | head -1)
  RUN_VER=${RUN_VER:--1}
  if [ "$CODE_VER" = "$RUN_VER" ]; then
    exit 0  # 已是最新版本，无需启动
  fi
  python3 - <<'RESTART'
import os, signal
from pathlib import Path
root = Path.cwd().resolve()
for proc in Path("/proc").iterdir():
    if not proc.name.isdigit():
        continue
    try:
        argv = (proc / "cmdline").read_bytes().split(b"\0")
        if Path(os.readlink(proc / "cwd")).resolve() != root:
            continue
        if argv and Path(os.fsdecode(argv[0])).name.startswith("python") and any(a in (b"server.py", os.fsencode(root / "server.py")) for a in argv[1:]):
            os.kill(int(proc.name), signal.SIGTERM)
    except (OSError, ValueError):
        pass
RESTART
  sleep 1
fi

HOST=127.0.0.1  # 手机直连 WebDAV，无需暴露电脑 HTTP 服务
exec env HOST="$HOST" python3 server.py
