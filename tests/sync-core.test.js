const {test}=require('node:test');
const assert=require('node:assert/strict');
const C=require('../static/sync-core.js');
const key=(table,id)=>JSON.stringify([table,id]);
const base=async()=>{const db=C.emptyDB();db.todos=[{id:'a',title:'原安排',date:'2026-10-02',done:false}];db.transactions=[{id:'t1',amount:18,note:'午饭',type:'expense',date:'2026-10-02'}];return C.seed(db);};
function edited(doc,actor,fn){const db=C.materialize(doc);fn(db);return C.edit(doc,db,actor,0).doc;}
test('migration preserves all real fields and legacy data; stable seed is idempotent',async()=>{
 const d=await base();assert(C.equal(d,await C.seed(C.materialize(d))));assert.equal(C.materialize(d).todos[0].title,'原安排');assert(C.equal(C.merge(d,d),d));
});
test('independent offline inserts/edits from two devices merge without loss',async()=>{
 const d=await base(),a=edited(d,'phone',db=>{db.todos[0].done=true;db.transactions.push({id:'t2',amount:6,note:'早餐'});}),b=edited(d,'desktop',db=>db.transactions[0].amount=20);
 const m=C.merge(a,b),db=C.materialize(m);assert.equal(db.todos[0].done,true);assert.equal(db.transactions.length,2);assert.equal(db.transactions.find(t=>t.id==='t1').amount,20);assert.equal(C.conflicts(m).length,0);assert(C.equal(m,C.merge(b,a)));
});
test('concurrent edits retain both complete versions; explicit resolution converges',async()=>{
 const d=await base(),a=edited(d,'phone',db=>db.todos[0].title='手机修改'),b=edited(d,'desktop',db=>db.todos[0].title='电脑修改'),m=C.merge(a,b);
 assert.equal(C.conflicts(m).length,1);assert.equal(m.records[key('todos','a')].values.length,2);
 const resolved=C.update(m,key('todos','a'),{id:'a',title:'合并后的安排'},'resolver',1);assert.equal(C.conflicts(C.merge(resolved,a)).length,0);assert.equal(C.materialize(C.merge(resolved,b)).todos[0].title,'合并后的安排');
});
test('deletion tombstone prevents resurrection by a long-offline device',async()=>{
 const d=await base(),deleted=edited(d,'phone',db=>db.todos=[]);assert.equal(C.materialize(C.merge(deleted,d)).todos.length,0);assert.equal(C.conflicts(C.merge(deleted,d)).length,0);
});
test('concurrent delete and edit keeps edited record plus deletion for review',async()=>{
 const d=await base(),deleted=edited(d,'phone',db=>db.todos=[]),edit=edited(d,'desktop',db=>db.todos[0].title='新内容'),m=C.merge(deleted,edit);
 assert.equal(C.materialize(m).todos[0].title,'新内容');assert.equal(C.conflicts(m)[0].versions.filter(v=>v.value===null).length,1);
});
test('stale editor never silently supersedes a newly received remote version',async()=>{
 const d=await base(),remote=edited(d,'phone',db=>db.todos[0].title='别人刚改的'),local=edited(d,'desktop',db=>db.todos[0].title='编辑框里的草稿');assert.equal(C.conflicts(C.merge(remote,local)).length,1);
});
test('review and settings are merged by key, not by whole database',async()=>{
 const d=await base(),a=edited(d,'phone',db=>{db.reviews['2026-10-02']='第一行\n第二行';db.settings.theme='dark';}),b=edited(d,'desktop',db=>db.reviews['2026-10-01']='昨天');
 const db=C.materialize(C.merge(a,b));assert.equal(db.reviews['2026-10-02'],'第一行\n第二行');assert.equal(db.reviews['2026-10-01'],'昨天');assert.equal(db.settings.theme,'dark');
});
test('merge is associative, commutative and idempotent across three replicas',async()=>{
 const d=await base();for(let i=0;i<80;i++){
  const aa=edited(d,'a'+i,db=>{db.todos[0].done=i%2===0;db.transactions[0].amount=i;}),bb=edited(d,'b'+i,db=>{db.todos[0].title='b'+i;if(i%3===0)db.transactions=[];}),cc=edited(d,'c'+i,db=>{db.todos.push({id:'new'+i,title:'c'+i});});
  const lhs=C.merge(C.merge(aa,bb),cc),rhs=C.merge(aa,C.merge(bb,cc));assert(C.equal(lhs,rhs));assert(C.equal(C.merge(lhs,lhs),lhs));assert(C.equal(C.merge(bb,aa),C.merge(aa,bb)));
 }
});
test('corrupt or unsupported cloud data is rejected instead of becoming empty data',async()=>{
 assert.throws(()=>C.validate({format:9,records:{}}));assert.throws(()=>C.validate({format:1,records:{bad:{}}}));const d=await base();d.records[key('todos','a')].values[0].n=900;assert.throws(()=>C.validate(d));
});
test('same version ID with different contents is rejected',async()=>{
 const d=await base(),bad=C.clone(d);bad.records[key('todos','a')].values[0].value.title='被篡改';assert.throws(()=>C.merge(d,bad));
});
test('export roundtrip includes unresolved versions and tombstones',async()=>{
 const d=await base(),a=edited(d,'phone',db=>db.todos[0].title='A'),b=edited(d,'desktop',db=>db.todos[0].title='B'),m=C.merge(a,b);assert(C.equal(C.merge(m,JSON.parse(JSON.stringify(m))),m));assert.equal(C.conflicts(m).length,1);
});
test('course nested contents and travel references survive merge',async()=>{
 const db=C.emptyDB();db.subjects=[{id:'s',name:'课程',points:[{id:'p',title:'知识点',detail:'多行\n记录'}],questions:[],materials:[]}];db.trips=[{id:'trip',city:'北京'}];db.transactions=[{id:'bill',amount:100,tripId:'trip'}];const doc=await C.seed(db);assert(C.equal(C.materialize(doc),db));
});
