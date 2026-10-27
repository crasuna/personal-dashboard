/* Record-level, observed-remove multi-value registers. No clocks are used to
 * discard edits. Concurrent versions are retained until explicitly resolved.
 * Pure JS: shared by desktop, Android and the Node test suite. */
(function(root) {
  'use strict';
  const TABLES = ['todos','courses','subjects','deadlines','trips','transactions','studies'];
  const clone = x => JSON.parse(JSON.stringify(x));
  function stable(x) {
    if (Array.isArray(x)) return '[' + x.map(stable).join(',') + ']';
    if (x && typeof x === 'object') return '{' + Object.keys(x).sort().map(k => JSON.stringify(k)+':'+stable(x[k])).join(',') + '}';
    return JSON.stringify(x);
  }
  const equal = (a,b) => stable(a) === stable(b);
  const compare = (a,b) => a < b ? -1 : a > b ? 1 : 0;
  function emptyDB() {
    const db = {version:1}; TABLES.forEach(k => db[k]=[]);
    db.reviews = {}; db.settings = {theme:'light',categories:['餐饮','交通','购物','书籍','娱乐','医疗','住房','其他'],incomeCategories:['奖学金','兼职','生活费','报销','工资','其他']};
    return db;
  }
  const empty = () => ({format:1,records:{}});
  const dict = x => x && typeof x === 'object' && !Array.isArray(x);
  const safeID = x => typeof x === 'string' && /^[a-zA-Z0-9_-]{1,128}$/.test(x);
  function flatten(db) {
    if (!dict(db)) throw Error('备份不是有效的数据对象');
    const out = Object.create(null);
    for (const table of TABLES) {
      if (db[table] !== undefined && !Array.isArray(db[table])) throw Error(table+' 格式不正确');
      for (const item of db[table] || []) {
        if (!dict(item) || !safeID(item.id)) throw Error(table+' 记录 ID 不正确，已停止导入');
        const key=JSON.stringify([table,item.id]);
        if (Object.hasOwn(out,key)) throw Error('存在重复记录 ID，已停止导入');
        out[key] = clone(item);
      }
    }
    for (const table of ['reviews','settings']) {
      if (db[table] !== undefined && !dict(db[table])) throw Error(table+' 格式不正确');
      for (const [id,value] of Object.entries(db[table] || {})) {
        if (!safeID(id) || ['__proto__','constructor','prototype'].includes(id)) throw Error('不安全的数据字段');
        out[JSON.stringify([table,id])] = clone(value);
      }
    }
    return out;
  }
  function validate(doc) {
    if (!dict(doc) || doc.format !== 1 || !dict(doc.records)) throw Error('同步文件版本或格式不正确；未覆盖本地数据');
    if (Object.keys(doc.records).length > 100000) throw Error('同步文件过大');
    for (const [key,r] of Object.entries(doc.records)) {
      const pair=JSON.parse(key);
      if (!Array.isArray(pair)||pair.length!==2||![...TABLES,'reviews','settings'].includes(pair[0])||!safeID(pair[1])||['__proto__','constructor','prototype'].includes(pair[1])) throw Error('同步文件包含无效记录');
      if (!dict(r)||!dict(r.seen)||!Array.isArray(r.values)||!r.values.length) throw Error('同步版本信息不完整');
      for (const [actor,n] of Object.entries(r.seen)) if (!safeID(actor)||!Number.isSafeInteger(n)||n<1||['__proto__','constructor','prototype'].includes(actor)) throw Error('无效同步序号');
      const dots = new Set();
      for (const v of r.values) {
        if (!dict(v)||!safeID(v.actor)||!Number.isSafeInteger(v.n)||v.n<1||(r.seen[v.actor]||0)<v.n||typeof v.at!=='string'||!Object.hasOwn(v,'value')) throw Error('无效同步版本');
        const d=dot(v); if(dots.has(d)) throw Error('重复同步版本'); dots.add(d);
        if(v.value!==null && TABLES.includes(pair[0]) && (!dict(v.value)||v.value.id!==pair[1])) throw Error('记录与 ID 不匹配');
        if(v.value!==null && pair[0]==='reviews' && typeof v.value!=='string') throw Error('回顾格式错误');
        if(v.value!==null && pair[0]==='settings') {
          if(['categories','incomeCategories'].includes(pair[1]) && (!Array.isArray(v.value)||!v.value.every(x=>typeof x==='string'))) throw Error('分类格式错误');
          if(pair[1]==='theme' && !['light','dark'].includes(v.value)) throw Error('主题格式错误');
        }
      }
    }
    return doc;
  }
  const dot = v => v.actor+':'+v.n;
  function mergeRegister(a,b) {
    if(!a) return clone(b); if(!b) return clone(a);
    const seen={...a.seen}; for(const [actor,n] of Object.entries(b.seen)) seen[actor]=Math.max(seen[actor]||0,n);
    const aa=new Map(a.values.map(v=>[dot(v),v])), bb=new Map(b.values.map(v=>[dot(v),v]));
    const values=[];
    for(const [id,v] of aa) {
      if(bb.has(id) && !equal(v,bb.get(id))) throw Error('检测到同序号不同内容，已暂停同步以保护数据');
      if(bb.has(id)||(b.seen[v.actor]||0)<v.n) values.push(clone(v));
    }
    for(const [id,v] of bb) if(!aa.has(id)&&(a.seen[v.actor]||0)<v.n) values.push(clone(v));
    if(!values.length) throw Error('同步记录无可用版本');
    values.sort((a,b)=>compare(dot(a),dot(b)));
    return {seen,values};
  }
  function merge(a,b) {
    validate(a); validate(b); const out=empty();
    for(const key of new Set([...Object.keys(a.records),...Object.keys(b.records)])) out.records[key]=mergeRegister(a.records[key],b.records[key]);
    return out;
  }
  // Non-deleted version is displayed when deletion and editing are concurrent.
  // Every alternative (including deletion) remains available in conflicts().
  function winner(r) {
    return r.values.slice().sort((a,b)=>(a.value===null)-(b.value===null)||compare(b.at,a.at)||compare(dot(b),dot(a)))[0];
  }
  function materialize(doc) {
    const db=emptyDB();
    for(const key of Object.keys(doc.records).sort()) {
      const [table,id]=JSON.parse(key), value=winner(doc.records[key]).value;
      if(value===null) continue;
      if(TABLES.includes(table)) db[table].push(clone(value)); else db[table][id]=clone(value);
    }
    return db;
  }
  async function seed(db) {
    const doc=empty();
    await Promise.all(Object.entries(flatten(db)).map(async ([key,value])=>{
      const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(key+'\n'+stable(value)));
      const actor='seed-'+Array.from(new Uint8Array(hash),x=>x.toString(16).padStart(2,'0')).join('');
      doc.records[key]={seen:{[actor]:1},values:[{actor,n:1,at:'1970-01-01T00:00:00.000Z',value}]};
    }));
    return doc;
  }
  function update(doc,key,value,actor,n,at=new Date().toISOString()) {
    const next=clone(doc), prev=next.records[key];
    if((prev?.seen[actor]||0)>=n) throw Error('同步序号必须递增');
    next.records[key]={seen:{...(prev?.seen||{}),[actor]:n},values:[{actor,n,at,value:clone(value)}]};
    return next;
  }
  function edit(viewDoc,db,actor,start) {
    const old=flatten(materialize(viewDoc)), next=flatten(db);
    let doc=viewDoc,n=start;
    for(const key of new Set([...Object.keys(old),...Object.keys(next)])) {
      const before=Object.hasOwn(old,key)?old[key]:null, after=Object.hasOwn(next,key)?next[key]:null;
      if(!equal(before,after)) doc=update(doc,key,after,actor,++n);
    }
    return {doc,n};
  }
  function conflicts(doc) {
    return Object.entries(doc.records).filter(([,r])=>new Set(r.values.map(v=>stable(v.value))).size>1).map(([key,r])=>({key,versions:clone(r.values)}));
  }
  const api={TABLES,clone,stable,equal,emptyDB,empty,flatten,validate,merge,materialize,seed,update,edit,conflicts,winner};
  if(typeof module!=='undefined'&&module.exports) module.exports=api;
  root.DashboardSyncCore=api;
})(typeof globalThis!=='undefined'?globalThis:this);
