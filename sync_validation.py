"""Validate the atomic desktop mirror before allowing it to replace db.json.

Merging lives in shared sync-core.js. This boundary only verifies the snapshot
and its human-readable projection so a buggy client cannot silently save an
empty mirror while retaining a populated sync document (or vice versa).
"""
import copy
import json
import re

TABLES = ('todos','courses','subjects','deadlines','trips','transactions','studies')
SAFE = re.compile(r'[a-zA-Z0-9_-]{1,128}\Z')
FORBIDDEN = ('__proto__','constructor','prototype')


def identifier(value):
    return isinstance(value,str) and SAFE.fullmatch(value) and value not in FORBIDDEN


def validate_snapshot(data, defaults):
    doc = data.get('_sync')
    if not isinstance(doc,dict) or doc.get('format') != 1 or not isinstance(doc.get('records'),dict):
        raise ValueError('同步快照格式错误')
    if len(doc['records']) > 100000:
        raise ValueError('同步快照记录过多')
    expected = copy.deepcopy(defaults)
    for rawkey, register in sorted(doc['records'].items()):
        key = json.loads(rawkey)
        if not isinstance(key,list) or len(key)!=2 or key[0] not in (*TABLES,'reviews','settings') or not identifier(key[1]):
            raise ValueError('同步快照包含无效记录 ID')
        table, ident = key
        if not isinstance(register,dict) or not isinstance(register.get('seen'),dict) or not isinstance(register.get('values'),list) or not register['values']:
            raise ValueError('同步版本信息不完整')
        for actor, n in register['seen'].items():
            if not identifier(actor) or type(n) is not int or not 1 <= n <= 9007199254740991:
                raise ValueError('无效同步序号')
        dots=set()
        for v in register['values']:
            if not isinstance(v,dict) or not identifier(v.get('actor')) or type(v.get('n')) is not int or v['n'] < 1 or register['seen'].get(v['actor'],0)<v['n'] or not isinstance(v.get('at'),str) or 'value' not in v:
                raise ValueError('无效同步版本')
            dot=(v['actor'],v['n'])
            if dot in dots: raise ValueError('重复同步版本')
            dots.add(dot)
            value=v['value']
            if value is not None:
                if table in TABLES and (not isinstance(value,dict) or value.get('id')!=ident):
                    raise ValueError('记录与 ID 不匹配')
                if table=='reviews' and not isinstance(value,str): raise ValueError('回顾格式错误')
                if table=='settings' and ident in ('categories','incomeCategories') and (not isinstance(value,list) or not all(isinstance(x,str) for x in value)): raise ValueError('分类格式错误')
                if table=='settings' and ident=='theme' and value not in ('light','dark'): raise ValueError('主题格式错误')
        chosen=max(register['values'],key=lambda v:(v['value'] is not None,v['at'],v['actor']+':'+str(v['n'])))['value']
        if chosen is not None:
            if table in TABLES: expected[table].append(chosen)
            else: expected[table][ident]=chosen
    actual={k:v for k,v in data.items() if k!='_sync'}
    for table in TABLES:
        expected[table].sort(key=lambda item:item['id'])
        if not all(isinstance(v,dict) and identifier(v.get('id')) for v in actual[table]): raise ValueError('数据包含无效记录')
        actual[table]=sorted(actual[table],key=lambda item:item['id'])
    if actual != expected:
        raise ValueError('记录与同步快照不一致，已阻止覆盖原数据')
