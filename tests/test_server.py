import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from sync_bridge import SyncBridge
from sync_validation import validate_snapshot
from test_private_files import assert_private


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        server.DATA_DIR=Path(self.temp.name);server.DB_PATH=server.DATA_DIR/'db.json';server.BACKUP_DIR=server.DATA_DIR/'backups'
        server.SYNC_BRIDGE=SyncBridge(server.DATA_DIR)
        server._atomic_write(server.DB_PATH,server.DEFAULT_DB)
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        server.PORT=self.http.server_port
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.temp.cleanup()
    def request(self,path,method='GET',data=None,headers=None):
        h={'Content-Type':'application/json'};h.update(headers or {})
        request=urllib.request.Request(f'http://127.0.0.1:{server.PORT}'+path,method=method,data=None if data is None else json.dumps(data).encode(),headers=h)
        # Local API tests must not be routed through a machine-wide HTTP proxy.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:r=opener.open(request)
        except urllib.error.HTTPError as e:r=e
        with r:return r.status,json.loads(r.read())
    def snapshot(self):
        db=copy.deepcopy(server.DEFAULT_DB);db['_sync']={'format':1,'records':{}};return db
    def test_revision_and_old_page_protection(self):
        status,current=self.request('/api/data');self.assertEqual(status,200)
        status,_=self.request('/api/save','PUT',server.DEFAULT_DB,{'If-Match':current['_revision']});self.assertEqual(status,428)
        status,_=self.request('/api/save','PUT',self.snapshot());self.assertEqual(status,428)
        status,result=self.request('/api/save','PUT',self.snapshot(),{'If-Match':current['_revision']});self.assertEqual(status,200)
        # Identical retry succeeds even if the acknowledgement was lost.
        self.assertEqual(self.request('/api/save','PUT',self.snapshot(),{'If-Match':current['_revision']})[0],200)
    def test_stale_write_and_mirror_validation(self):
        _,current=self.request('/api/data');snap=self.snapshot()
        v={'id':'t','title':'测试','done':False}
        snap['todos']=[v];snap['_sync']['records'][json.dumps(['todos','t'],separators=(',',':'))]={'seen':{'test':1},'values':[{'actor':'test','n':1,'at':'2026-10-02T00:00:00.000Z','value':v}]}
        self.assertEqual(self.request('/api/save','PUT',snap,{'If-Match':current['_revision']})[0],200)
        self.assertEqual(self.request('/api/save','PUT',self.snapshot(),{'If-Match':current['_revision']})[0],409)
        broken=copy.deepcopy(snap);broken['todos']=[]
        self.assertEqual(self.request('/api/save','PUT',broken,{'If-Match':current['_revision']})[0],400)
        self.assertEqual(len(json.loads(server.DB_PATH.read_text(encoding='utf-8'))['todos']),1)
        self.assertEqual(len(list(server.BACKUP_DIR.glob('db-*.json'))),1)
    def test_corrupt_file_fails_closed_and_retains_bytes(self):
        server.DB_PATH.write_text('{broken')
        self.assertEqual(self.request('/api/data')[0],500)
        self.assertEqual(server.DB_PATH.read_text(),'{broken')
        self.assertTrue(list(server.DATA_DIR.glob('db-corrupt-*.json')))
    def test_cross_origin_and_missing_client_header_rejected(self):
        self.assertEqual(self.request('/api/sync/configGet','POST',{}, {'Origin':'https://evil.invalid','X-Dashboard-Client':'sync-v1'})[0],403)
        self.assertEqual(self.request('/api/sync/configGet','POST',{})[0],403)
        self.assertEqual(self.request('/api/data',headers={'Host':'evil.invalid'})[0],403)
    def test_password_only_local_private_file_never_api_export(self):
        headers={'X-Dashboard-Client':'sync-v1'}
        status,result=self.request('/api/sync/configSave','POST',{'email':'unit@example.invalid','password':'fake-app-secret','enabled':True},headers)
        self.assertEqual(status,200);self.assertNotIn('fake-app-secret',json.dumps(result))
        assert_private(self, server.DATA_DIR, directory=True)
        assert_private(self, server.DATA_DIR/'sync-config.json')
        for path in ['/api/data','/api/export']:
            self.assertNotIn('fake-app-secret',json.dumps(self.request(path)[1]))
        self.assertNotIn('fake-app-secret',json.dumps(self.request('/api/sync/configGet','POST',{},headers)[1]))
    def test_only_fixed_dav_path_is_allowed(self):
        bridge=server.SYNC_BRIDGE
        with self.assertRaises(ValueError):bridge.handle('configSave',{'enabled':True,'email':'test@example.invalid','password':'fake','folder':'../escape'})
        with self.assertRaises(ValueError):bridge.request({'folder':'safe','email':'e','password':'p'},'GET','https://example.invalid/steal')
        with self.assertRaises(ValueError):bridge.request({'folder':'safe','email':'e','password':'p'},'GET','../sync-config.json')

if __name__=='__main__':unittest.main(verbosity=2)
