"""Fixed-endpoint Nutstore bridge. Secrets are local-only, never in db.json.

The browser cannot supply a host or a URL. This is deliberately NOT a generic
proxy. HTTPS certificates are verified; redirects never receive credentials.
"""
import base64
import json
import os
import re
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = 'https://dav.jianguoyun.com/dav/'
LIMIT = 15 * 1024 * 1024
NAME = re.compile(r'device-[a-f0-9]{32}\.json\Z')
FOLDER = re.compile(r'[a-zA-Z0-9_-]{1,64}\Z')


def atomic_private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name+'.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SyncBridge:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / 'sync-config.json'
        self.lock = threading.RLock()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def config(self):
        if not self.path.exists():
            return {'enabled': False, 'email': '', 'folder': 'personal-dashboard-v1', 'password': ''}
        return json.loads(self.path.read_text(encoding='utf-8'))

    @staticmethod
    def public(c):
        return {k: c[k] for k in ('enabled', 'email', 'folder')} | {'hasPassword': bool(c.get('password'))}

    def handle(self, action, args):
        with self.lock:
            if action == 'configGet':
                return self.public(self.config())
            if action == 'configSave':
                old = self.config()
                enabled = bool(args.get('enabled'))
                email = str(args.get('email', old['email'])).strip()
                folder = str(args.get('folder', old['folder'])).strip()
                password = str(args.get('password') or old.get('password', ''))
                if args.get('forget'):
                    password, enabled = '', False
                if not FOLDER.fullmatch(folder):
                    raise ValueError('同步目录仅可使用英文、数字、横线和下划线（最多 64 字）')
                if enabled and ('@' not in email or ':' in email or not password):
                    raise ValueError('请填写坚果云邮箱和应用密码（不是登录密码）')
                if email != old['email'] and not args.get('password') and enabled:
                    raise ValueError('更换账号时请重新填写应用密码')
                new = {'enabled': enabled, 'email': email, 'folder': folder, 'password': password}
                atomic_private(self.path, new)
                return self.public(new)
            if action != 'dav':
                raise ValueError('不支持的同步操作')
            c = self.config()
            if not c['enabled'] or not c.get('password'):
                raise ValueError('尚未开启坚果云同步')
            return self.dav(c, args)

    def request(self, config, method, name='', body=None):
        if not FOLDER.fullmatch(config['folder']):
            raise ValueError('无效同步目录')
        if name and not NAME.fullmatch(name):
            raise ValueError('无效同步文件名')
        url = BASE + config['folder'] + '/' + name
        token = base64.b64encode((config['email']+':'+config['password']).encode()).decode()
        headers = {'Authorization': 'Basic '+token, 'User-Agent': 'PersonalDashboard/1.0', 'Cache-Control': 'no-cache'}
        if method == 'PROPFIND':
            headers.update({'Depth': '1', 'Content-Type': 'application/xml; charset=utf-8'})
            body = b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getetag/><d:resourcetype/></d:prop></d:propfind>'
        elif method == 'PUT':
            headers['Content-Type'] = 'application/json; charset=utf-8'
        if isinstance(body, str):
            body = body.encode('utf-8')
        if body and len(body) > LIMIT:
            raise ValueError('单个同步文件超过 15MB，已保留本地数据')
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=25) as response:
                data = response.read(LIMIT+1)
                if len(data) > LIMIT:
                    raise ValueError('远端同步文件超过大小限制，未导入')
                return response.status, data, response.headers.get('ETag', '')
        except urllib.error.HTTPError as e:
            if method == 'MKCOL' and e.code == 405:
                return 405, b'', ''
            messages = {401:'坚果云邮箱或应用密码不正确', 403:'坚果云拒绝访问，请检查应用授权或流量额度', 404:'同步目录或文件不存在', 429:'坚果云请求频率受限，稍后会自动重试', 507:'坚果云空间或流量额度不足'}
            raise ValueError(messages.get(e.code, f'坚果云响应 HTTP {e.code}，稍后自动重试')) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ValueError('暂时无法连接坚果云；本地数据已保留，稍后自动重试') from None

    def dav(self, config, args):
        op = args.get('op')
        if op == 'mkdir':
            status, _, _ = self.request(config, 'MKCOL')
            if status not in (200,201,204,405):
                raise ValueError('无法创建同步目录')
            return {}
        if op == 'list':
            status, body, _ = self.request(config, 'PROPFIND')
            if status != 207:
                raise ValueError('坚果云未返回有效目录列表')
            root = ET.fromstring(body)
            if root.tag != '{DAV:}multistatus':
                raise ValueError('无效 WebDAV 目录列表')
            result = []
            prefix = '/dav/'+config['folder']+'/'
            for item in root.findall('{DAV:}response'):
                href = urllib.parse.unquote(urllib.parse.urlparse(item.findtext('{DAV:}href', '')).path)
                if not href.startswith(prefix):
                    continue
                name = href[len(prefix):]
                if NAME.fullmatch(name):
                    props = [p for p in item.findall('{DAV:}propstat') if ' 200 ' in p.findtext('{DAV:}status','')]
                    if not props:
                        raise ValueError('无法读取同步文件属性')
                    etag = next((p.findtext('{DAV:}prop/{DAV:}getetag','') for p in props), '')
                    result.append({'name':name,'etag':etag})
            return result
        if op == 'get':
            status, body, etag = self.request(config, 'GET', args.get('name',''))
            if status != 200:
                raise ValueError('同步文件读取失败')
            return {'body': body.decode('utf-8'), 'etag': etag}
        if op == 'put':
            body = args.get('body')
            if not isinstance(body, str):
                raise ValueError('同步内容格式错误')
            envelope = json.loads(body)
            if envelope.get('app') != 'personal-dashboard' or envelope.get('protocol') != 1:
                raise ValueError('不是面板同步文件')
            status, _, etag = self.request(config, 'PUT', args.get('name',''), body)
            if status not in (200,201,204):
                raise ValueError('同步写入未得到确认')
            return {'etag':etag}
        raise ValueError('不支持的 WebDAV 操作')
