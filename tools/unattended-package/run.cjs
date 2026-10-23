/* Explicit local jobs only. No network, scheduler, source writes or submission. */
'use strict';
const fs=require('node:fs/promises'),syncFS=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),vm=require('node:vm');
const assemblerPath=path.resolve(__dirname,'../submission-package/assembler.js');
const assemblerSource=syncFS.readFileSync(assemblerPath),runnerSource=syncFS.readFileSync(__filename);
// Execute the exact assembler bytes included in the engine fingerprint, without require-cache drift.
const engineContext={crypto:crypto.webcrypto,TextEncoder,Uint8Array,DataView};
vm.runInNewContext(assemblerSource.toString('utf8'),engineContext,{filename:assemblerPath});
const A=engineContext.PPGSubmission;
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const failure=code=>{throw Error(code);};
async function readBounded(file,limit,code){
 // Check before open so a FIFO cannot wait indefinitely for a writer.
 const before=await fs.lstat(file);if(!before.isFile())failure('INPUT_NOT_FILE');
 const handle=await fs.open(file,syncFS.constants.O_RDONLY|syncFS.constants.O_NOFOLLOW|syncFS.constants.O_NONBLOCK);
 try{
  const stat=await handle.stat();if(!stat.isFile())failure('INPUT_NOT_FILE');
  if(stat.size>limit)failure(code);
  const chunks=[];let total=0;
  while(true){
   const chunk=Buffer.alloc(Math.min(65536,limit-total+1));
   const {bytesRead}=await handle.read(chunk,0,chunk.length,null);if(!bytesRead)break;
   total+=bytesRead;if(total>limit)failure(code);chunks.push(chunk.subarray(0,bytesRead));
  }
  return Buffer.concat(chunks,total);
 }finally{await handle.close();}
}
async function run(jobFile,inputDirectory,outputDirectory){
 const input=await fs.realpath(inputDirectory),output=await fs.realpath(outputDirectory);
 if(output===input||output.startsWith(input+path.sep)||input.startsWith(output+path.sep))failure('INPUT_OUTPUT_MUST_BE_DISJOINT');
 const raw=await readBounded(jobFile,1024*1024,'JOB_TOO_LARGE');
 const job=JSON.parse(raw);
 if(job.schemaVersion!==1||!/^job-[a-z0-9-]{1,64}$/.test(job.jobId||''))failure('INVALID_JOB');
 if(!Array.isArray(job.attachments)||job.attachments.length>200)failure('INVALID_ATTACHMENTS');
 if(sha(await fs.readFile(assemblerPath))!==sha(assemblerSource)||sha(await fs.readFile(__filename))!==sha(runnerSource))failure('ENGINE_CHANGED_RESTART_REQUIRED');
 const assemblerSHA256=sha(assemblerSource),runnerSHA256=sha(runnerSource);
 const engineSHA256=sha(Buffer.from(JSON.stringify({assemblerSHA256,runnerSHA256})));
 const fingerprint=sha(Buffer.concat([raw,Buffer.from(engineSHA256)]));
 const target=path.join(output,job.jobId),lock=path.join(output,'.'+job.jobId+'.lock');
 try{await fs.mkdir(lock);}catch(e){if(e.code==='EEXIST')failure('JOB_LOCKED');throw e;}
 let temporary;
 try{
  const files=[];let total=0,actualTotal=0;
  for(const f of job.attachments){
   if(typeof f.path!=='string'||path.isAbsolute(f.path)||f.path.split(/[\\/]/).some(x=>x==='..'||x===''))failure('UNSAFE_INPUT_PATH');
   const full=await fs.realpath(path.join(input,f.path));
   if(!full.startsWith(input+path.sep))failure('INPUT_OUTSIDE_ROOT');
   const stat=await fs.stat(full);if(!stat.isFile())failure('INPUT_NOT_FILE');
   total+=stat.size;if(total>100*1024*1024)failure('ATTACHMENTS_TOO_LARGE');
   const bytes=await readBounded(full,100*1024*1024-actualTotal,'ATTACHMENTS_TOO_LARGE');
   actualTotal+=bytes.length;if(actualTotal>100*1024*1024)failure('ATTACHMENTS_TOO_LARGE');
   if(!/^[0-9a-f]{64}$/.test(f.sha256||'')||sha(bytes)!==f.sha256)failure('SOURCE_HASH_MISMATCH');
   files.push({name:f.name||path.basename(full),role:f.role,sourceReference:f.sourceReference||'',bytes});
  }
  let existing=false;try{await fs.lstat(target);existing=true;}catch(e){if(e.code!=='ENOENT')throw e;}
  if(existing){
   const stat=await fs.lstat(target);if(!stat.isDirectory()||stat.isSymbolicLink())failure('OUTPUT_CONFLICT');
   const receipt=JSON.parse(await readBounded(path.join(target,'receipt.json'),2*1024*1024,'RECEIPT_TOO_LARGE'));
   if(!receipt||receipt.fingerprint!==fingerprint||receipt.engineSHA256!==engineSHA256||receipt.runnerSHA256!==runnerSHA256||receipt.assemblerSHA256!==assemblerSHA256)failure('JOB_REVISION_CONFLICT');
   const zip=await readBounded(path.join(target,'package.zip'),128*1024*1024,'OUTPUT_TOO_LARGE');
   if(sha(zip)!==receipt.packageSHA256)failure('OUTPUT_CHANGED_REQUIRES_NEW_JOB');
   return {state:'replayed',jobId:job.jobId,sourceWrites:false,sent:false};
  }
  const result=await A.assemble(job.metadata,files,{notApplicable:job.notApplicable||{}});
  temporary=await fs.mkdtemp(path.join(output,'.'+job.jobId+'.pending-'));
  const receipt={schemaVersion:1,jobId:job.jobId,fingerprint,engineSHA256,assemblerSHA256,runnerSHA256,packageSHA256:sha(result.bytes),packageID:result.manifest.packageID,generatedAt:result.manifest.generatedAt,status:result.report.status,missing:result.report.missing,sourceWrites:false,sent:false,inputs:job.attachments};
  await fs.writeFile(path.join(temporary,'package.zip'),result.bytes,{flag:'wx'});
  await fs.writeFile(path.join(temporary,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
  // Target is never removed or replaced. The per-job lock serializes cooperating runners.
  await fs.rename(temporary,target);temporary=null;
  return {state:'generated',jobId:job.jobId,missing:receipt.missing,status:receipt.status,sourceWrites:false,sent:false};
 }finally{
  if(temporary)await fs.rm(temporary,{recursive:true,force:true});
  await fs.rmdir(lock);
 }
}
module.exports={run};
if(require.main===module){
 const [job,input,output]=process.argv.slice(2);
 if(!job||!input||!output){process.stderr.write('Usage: node run.cjs JOB.json INPUT_DIRECTORY EXISTING_OUTPUT_DIRECTORY\n');process.exitCode=2;}
 else run(job,input,output).then(r=>process.stdout.write(JSON.stringify(r)+'\n')).catch(e=>{process.stderr.write('Package job failed: '+e.message+'\n');process.exitCode=1;});
}
