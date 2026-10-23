'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os'),cp=require('node:child_process'),crypto=require('node:crypto');
const {run}=require('../tools/unattended-package/run.cjs');
(async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'ppg-package-'));
 try{
  const input=path.join(root,'input'),output=path.join(root,'output'),jobFile=path.join(root,'job.json');
  await fs.mkdir(input);await fs.mkdir(output);
  const bytes=Buffer.from('DRAFT fictional editable package document\n');await fs.writeFile(path.join(input,'draft.md'),bytes);
  const job={schemaVersion:1,jobId:'job-fictional-1',metadata:{caseUID:'fictional-case',title:'Fictional package',version:'DRAFT-1',sourceBaseline:'fictional snapshot'},attachments:[{path:'draft.md',role:'draft',sha256:crypto.createHash('sha256').update(bytes).digest('hex'),sourceReference:'fictional capture'}]};
  const save=()=>fs.writeFile(jobFile,JSON.stringify(job));await save();
  const first=await run(jobFile,input,output);assert.equal(first.state,'generated');assert.equal(first.sent,false);assert.ok(first.missing>0);
  const receiptPath=path.join(output,job.jobId,'receipt.json'),zipPath=path.join(output,job.jobId,'package.zip');
  const receipt=JSON.parse(await fs.readFile(receiptPath));assert.equal(receipt.status,'ASSEMBLED DRAFT / HUMAN CHECK REQUIRED');
  assert.equal((await run(jobFile,input,output)).state,'replayed');
  job.metadata.version='DRAFT-2';await save();await assert.rejects(run(jobFile,input,output),/JOB_REVISION_CONFLICT/);job.metadata.version='DRAFT-1';await save();
  await fs.writeFile(zipPath,'human edit');await assert.rejects(run(jobFile,input,output),/OUTPUT_CHANGED/);assert.equal(await fs.readFile(zipPath,'utf8'),'human edit');
  await fs.writeFile(path.join(input,'draft.md'),'changed');await assert.rejects(run(jobFile,input,output),/SOURCE_HASH_MISMATCH/);
  await fs.writeFile(path.join(input,'draft.md'),bytes);
  job.jobId='job-fictional-2';job.attachments[0].path='../job.json';await save();await assert.rejects(run(jobFile,input,output),/UNSAFE_INPUT_PATH/);
  await fs.symlink(jobFile,path.join(input,'escape.json'));job.attachments[0].path='escape.json';await save();await assert.rejects(run(jobFile,input,output),/INPUT_OUTSIDE_ROOT/);
  job.attachments[0].path='draft.md';await save();await fs.mkdir(path.join(output,'.'+job.jobId+'.lock'));await assert.rejects(run(jobFile,input,output),/JOB_LOCKED/);await fs.rmdir(path.join(output,'.'+job.jobId+'.lock'));
  await assert.rejects(run(jobFile,input,input),/DISJOINT/);
  const largeJob=path.join(root,'large-job.json');await fs.writeFile(largeJob,'');await fs.truncate(largeJob,1024*1024+1);
  await assert.rejects(run(largeJob,input,output),/JOB_TOO_LARGE/);
  // Simulate growth after stat: the actual read must enforce the cap too.
  const originalOpen=fs.open;
  fs.open=async function(file,...args){
   const handle=await originalOpen.call(this,file,...args);
   if(file===largeJob){const originalStat=handle.stat.bind(handle);handle.stat=async()=>{const stat=await originalStat();stat.size=0;return stat;};}
   return handle;
  };
  try{await assert.rejects(run(largeJob,input,output),/JOB_TOO_LARGE/);}finally{fs.open=originalOpen;}

  const largeAttachment=path.join(input,'large.bin');await fs.writeFile(largeAttachment,'');await fs.truncate(largeAttachment,100*1024*1024+1);
  job.attachments[0].path='large.bin';await save();await assert.rejects(run(jobFile,input,output),/ATTACHMENTS_TOO_LARGE/);
  job.attachments[0].path='draft.md';await save();
  // Qualify an isolated copied engine; never mutate the maintained runner/assembler.
  const engineRoot=path.join(root,'engine'),runnerDir=path.join(engineRoot,'unattended-package'),assemblerDir=path.join(engineRoot,'submission-package');
  await fs.mkdir(runnerDir,{recursive:true});await fs.mkdir(assemblerDir);
  const runnerCopy=path.join(runnerDir,'run.cjs'),assemblerCopy=path.join(assemblerDir,'assembler.js');
  await fs.copyFile(path.resolve(__dirname,'../tools/unattended-package/run.cjs'),runnerCopy);
  await fs.copyFile(path.resolve(__dirname,'../tools/submission-package/assembler.js'),assemblerCopy);
  const isolated=require(runnerCopy);job.jobId='job-engine-proof';await save();await isolated.run(jobFile,input,output);
  const engineReceipt=JSON.parse(await fs.readFile(path.join(output,job.jobId,'receipt.json')));
  assert.match(engineReceipt.runnerSHA256,/^[0-9a-f]{64}$/);assert.match(engineReceipt.assemblerSHA256,/^[0-9a-f]{64}$/);
  await fs.appendFile(runnerCopy,'\n// Changed runner behavior revision.\n');
  await assert.rejects(isolated.run(jobFile,input,output),/ENGINE_CHANGED_RESTART_REQUIRED/);
  const restarted=cp.spawnSync(process.execPath,[runnerCopy,jobFile,input,output],{encoding:'utf8'});
  assert.equal(restarted.status,1);assert.match(restarted.stderr,/JOB_REVISION_CONFLICT/);
  // Symlinked replay artifacts must never be followed, even with matching bytes.
  const engineZip=path.join(output,job.jobId,'package.zip'),outsideZip=path.join(root,'outside.zip');
  await fs.rename(engineZip,outsideZip);await fs.symlink(outsideZip,engineZip);
  await assert.rejects(run(jobFile,input,output),/INPUT_NOT_FILE/);
  const fifo=path.join(root,'job-fifo');const made=cp.spawnSync('mkfifo',[fifo],{encoding:'utf8'});assert.equal(made.status,0,made.stderr);
  const fifoRun=cp.spawnSync(process.execPath,[path.resolve(__dirname,'../tools/unattended-package/run.cjs'),fifo,input,output],{encoding:'utf8',timeout:3000});
  assert.equal(fifoRun.error,undefined,'FIFO job must fail before blocking open');assert.equal(fifoRun.status,1);assert.match(fifoRun.stderr,/INPUT_NOT_FILE/);

  console.log('Passed: actual generation/replay, changed job/input/output, traversal/symlink escape, lock/disjoint-root guards, bounded growing-file reads, exact engine revision and replay symlink refusal.');
 }finally{await fs.rm(root,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
