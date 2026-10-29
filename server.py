#!/usr/bin/env python3
"""个人成长面板 - 本地服务（仅使用 Python 标准库，无第三方依赖）

启动后访问: http://127.0.0.1:8787
数据保存于 personal-dashboard/data/db.json，每次修改前保留备份。
"""
import copy
import hashlib
import io
import json
import os
import shutil
import threading
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from sync_bridge import SyncBridge
from sync_validation import validate_snapshot
from private_files import protect_private

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_DIR = Path(os.environ.get("DASHBOARD_DATA_DIR", str(ROOT / "data"))).resolve()
DB_PATH = DATA_DIR / "db.json"
BACKUP_DIR = DATA_DIR / "backups"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8787"))
MAX_UPLOAD = 15 * 1024 * 1024  # 15MB
SCHEMA_VERSION = 5  # 前端数据结构版本（新增字段时 +1，启动脚本据此替换旧进程）

_LOCK = threading.Lock()
SYNC_BRIDGE = SyncBridge(DATA_DIR)

DEFAULT_DB = {
    "version": 1,
    "todos": [],
    "courses": [],
    "subjects": [],
    "deadlines": [],
    "trips": [],
    "transactions": [],
    "studies": [],
    "reviews": {},
    "settings": {
        "theme": "light",
        "categories": ["餐饮", "交通", "购物", "书籍", "娱乐", "医疗", "住房", "其他"],
        "incomeCategories": ["奖学金", "兼职", "生活费", "报销", "工资", "其他"],
    },
}


def _atomic_write(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2))
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def _normalize(data: dict) -> dict:
    """补齐缺失字段，保证结构稳定。"""
    out = copy.deepcopy(DEFAULT_DB)
    if not isinstance(data, dict):
        return out
    for key in ("todos", "courses", "subjects", "deadlines", "trips", "transactions", "studies"):
        if isinstance(data.get(key), list):
            out[key] = data[key]
    if isinstance(data.get("reviews"), dict):
        out["reviews"] = data["reviews"]
    if isinstance(data.get("settings"), dict):
        out["settings"].update(data["settings"])
    if isinstance(data.get("_sync"), dict):
        out["_sync"] = data["_sync"]
    out["version"] = 1
    return out


def db_revision(data: dict) -> str:
    body = json.dumps(_normalize(data), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def load_db() -> dict:
    with _LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not DB_PATH.exists():
            _atomic_write(DB_PATH, DEFAULT_DB)
            return copy.deepcopy(DEFAULT_DB)
        try:
            raw = json.loads(DB_PATH.read_text(encoding="utf-8"))
            if not isinstance(raw,dict) or not isinstance(raw.get("todos"),list) or not isinstance(raw.get("transactions"),list):
                raise ValueError("数据库主体格式错误")
            for field in ("courses","subjects","deadlines","trips","studies"):
                if field in raw and not isinstance(raw[field],list): raise ValueError("数据库列表格式错误")
            for field in ("reviews","settings","_sync"):
                if field in raw and not isinstance(raw[field],dict): raise ValueError("数据库字段格式错误")
            data=_normalize(raw)
            if "_sync" in data: validate_snapshot(data,DEFAULT_DB)
            return data
        except Exception:
            # 数据文件损坏时保留现场，绝不以空库代替
            corrupt = DATA_DIR / f"db-corrupt-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
            shutil.copy2(DB_PATH, corrupt)
            raise ValueError("数据文件无法读取，已停止保存并保留现场；请使用备份恢复，勿新建空库")


def instance_id():
    """Identify this installation without exposing its local filesystem path."""
    identity = str(ROOT.resolve()) + "\0" + str(DATA_DIR.resolve())
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-src 'none'; base-uri 'none'")
        super().end_headers()

    # ---------- 工具 ----------
    def _json(self, obj, status=200, download_name=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _same_origin(self):
        host = self.headers.get("Host", "")
        if host not in (f"127.0.0.1:{PORT}", f"localhost:{PORT}", f"[::1]:{PORT}"):
            self._json({"ok": False, "error": "仅允许本机访问"}, 403)
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://{host}", f"https://{host}"):
            self._json({"ok": False, "error": "已阻止跨站请求"}, 403)
            return False
        return True

    # ---------- 接口 ----------
    def do_GET(self):
        if not self._same_origin(): return
        path = urlparse(self.path).path
        if path == "/api/data":
            try:
                data = load_db()
            except Exception as exc:
                return self._json({"ok":False,"error":str(exc)},500)
            data["_revision"] = db_revision(data)
            data["_schema"] = SCHEMA_VERSION
            return self._json(data)
        if path == "/api/version":
            return self._json({"version": SCHEMA_VERSION, "app": "personal-dashboard", "instance": instance_id()})
        if path == "/api/export":
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            try:
                return self._json(load_db(), download_name=f"personal-dashboard-{stamp}.json")
            except Exception as exc:
                return self._json({"ok":False,"error":str(exc)},500)
        return super().do_GET()

    def do_PUT(self):
        if not self._same_origin(): return
        path = urlparse(self.path).path
        if path != "/api/save":
            return self._json({"ok": False, "error": "not found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > MAX_UPLOAD:
                raise ValueError("数据大小无效（最多 15MB）")
            raw = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(raw, dict) or not isinstance(raw.get("_sync"), dict) or raw["_sync"].get("format") != 1:
                return self._json({"ok":False,"error":"旧版页面已停止保存，请先导出本页数据，再 Ctrl+F5 刷新。"},428)
            data = _normalize(raw)
            validate_snapshot(data, DEFAULT_DB)
        except Exception as exc:
            return self._json({"ok": False, "error": f"数据格式错误: {exc}"}, 400)
        with _LOCK:
            try:
                raw_current=json.loads(DB_PATH.read_text(encoding="utf-8"))
                if not isinstance(raw_current,dict) or not isinstance(raw_current.get("todos"),list) or not isinstance(raw_current.get("transactions"),list):
                    raise ValueError("数据库主体格式错误")
                current = _normalize(raw_current)
                if "_sync" in current: validate_snapshot(current,DEFAULT_DB)
            except Exception:
                return self._json({"ok": False, "error": "无法读取当前数据，已停止保存以保护原文件"}, 500)
            expected = self.headers.get("If-Match")
            if not expected:
                return self._json({"ok": False, "error": "页面版本过旧，已阻止覆盖。请先导出本页未保存内容，再刷新页面。"}, 428)
            current_revision = db_revision(current)
            next_revision = db_revision(data)
            if expected != current_revision and next_revision != current_revision:
                return self._json({"ok": False, "error": "其他页面已更新数据，已阻止旧页面覆盖。请保留本页未保存内容后刷新。"}, 409)
            if next_revision != current_revision:
                # 每次成功修改前保留快照，便于恢复到最近一次保存。
                BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                shutil.copy2(DB_PATH, BACKUP_DIR / f"db-{stamp}.json")
                _atomic_write(DB_PATH, data)
                for old in sorted(BACKUP_DIR.glob("db-*.json"))[:-200]:
                    old.unlink(missing_ok=True)
        return self._json({"ok": True, "revision": next_revision})

    def do_POST(self):
        if not self._same_origin(): return
        path = urlparse(self.path).path
        if path.startswith("/api/sync/"):
            if self.headers.get("X-Dashboard-Client") != "sync-v1":
                return self._json({"ok":False,"error":"缺少本机客户端标识"},403)
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length <= 0 or length > MAX_UPLOAD:
                    raise ValueError("请求大小无效")
                args = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(args,dict): raise ValueError("请求格式错误")
                result = SYNC_BRIDGE.handle(path.rsplit("/",1)[-1],args)
                return self._json({"ok":True,"value":result})
            except Exception as exc:
                return self._json({"ok":False,"error":str(exc)},400)
        if path != "/api/extract":
            return self._json({"ok": False, "error": "not found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                raise ValueError("文件为空")
            if length > MAX_UPLOAD:
                raise ValueError("文件过大（超过 15MB）")
            data = self.rfile.read(length)
            filename = unquote(self.headers.get("X-Filename", "notes.txt"))
            text = extract_text(filename, data)
            return self._json({"ok": True, "text": text[:500000], "filename": filename})
        except Exception as exc:
            return self._json({"ok": False, "error": str(exc)}, 400)

    def log_message(self, *args):
        pass  # 静默访问日志


def extract_text(filename: str, data: bytes) -> str:
    """从 md / txt / docx 中提取纯文本（仅标准库）。"""
    name = filename.lower()
    if name.endswith(".docx"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml")
        root = ET.fromstring(xml)
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paras = []
        for p in root.iter(ns + "p"):
            text = "".join(t.text or "" for t in p.iter(ns + "t"))
            if text.strip():
                paras.append(text)
        return "\n".join(paras)
    # md / markdown / txt 等纯文本
    return data.decode("utf-8", errors="replace")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    protect_private(DATA_DIR, directory=True)
    if SYNC_BRIDGE.path.exists():
        protect_private(SYNC_BRIDGE.path)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    load_db()  # 初始化数据文件
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        print(f"端口 {PORT} 已被占用，面板可能已经在运行: http://{HOST}:{PORT}")
        return
    print(f"个人成长面板已启动: http://{HOST}:{PORT}  (按 Ctrl+C 退出)")
    print(f"数据文件: {DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()
