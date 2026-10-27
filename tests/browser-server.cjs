// Every browser test owns a new port and an empty temporary database.
// Never point mutation tests at someone's running dashboard.
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const net=require('node:net');
const {spawn}=require('node:child_process');
async function startTestServer(){
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'personal-dashboard-test-'));
  const port=await new Promise((resolve,reject)=>{const s=net.createServer();s.once('error',reject);s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p));});});
  const root=path.resolve(__dirname,'..');
  const child=spawn(process.env.PYTHON || (process.platform==='win32'?'python':'python3'),['-u',path.join(root,'server.py')],{cwd:root,env:{...process.env,HOST:'127.0.0.1',PORT:String(port),DASHBOARD_DATA_DIR:dir},stdio:['ignore','pipe','pipe']});
  let logs='',failure;child.stdout.on('data',b=>logs+=b);child.stderr.on('data',b=>logs+=b);child.on('error',e=>failure=e);
  async function close(){
    if(child.exitCode===null && !failure){child.kill('SIGTERM');await new Promise(r=>{child.once('exit',r);setTimeout(r,3000).unref();});}
    fs.rmSync(dir,{recursive:true,force:true});
  }
  const url=`http://127.0.0.1:${port}`;
  for(let i=0;i<70;i++){
    if(failure||child.exitCode!==null){await close();throw failure||Error('Test server exited: '+logs);}
    try{const r=await fetch(url+'/api/version');const j=await r.json();if(r.ok&&j.app==='personal-dashboard')return{url,dir,close};}catch{}
    await new Promise(r=>setTimeout(r,100));
  }
  await close();throw Error('Test server failed to start: '+logs);
}
module.exports={startTestServer};
