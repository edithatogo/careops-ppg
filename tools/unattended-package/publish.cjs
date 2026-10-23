/* CLI publication of existing package bytes; no document generation or connectors. */
'use strict';
const fs=require('node:fs/promises'),nativeFS=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const fail=code=>{throw Error(code);};
async function read(file,limit){
 const st=await fs.lstat(file);if(!st.isFile()||st.size>limit)fail('ARTIFACT_NOT_BOUNDED_REGULAR_FILE');
 const h=await fs.open(file,nativeFS.constants.O_RDONLY|nativeFS.constants.O_NOFOLLOW|nativeFS.constants.O_NONBLOCK);
 try{if(!(await h.stat()).isFile())fail('ARTIFACT_NOT_REGULAR_FILE');let size=0;const chunks=[];
  for(;;){const b=Buffer.alloc(Math.min(65536,limit-size+1)),r=await h.read(b,0,b.length,null);if(!r.bytesRead)break;
   size+=r.bytesRead;if(size>limit)fail('ARTIFACT_TOO_LARGE');chunks.push(b.subarray(0,r.bytesRead));}
  return Buffer.concat(chunks);
 }finally{await h.close();}
}
async function publish(directory,client,journal){
 const root=await fs.realpath(directory),receiptBytes=await read(path.join(root,'receipt.json'),2*1024*1024);
 const receipt=JSON.parse(receiptBytes),zip=await read(path.join(root,'package.zip'),128*1024*1024);
 if(receipt.schemaVersion!==1||!/^job-[a-z0-9-]{1,64}$/.test(receipt.jobId||'')||
    path.basename(root)!==receipt.jobId||receipt.sourceWrites!==false||receipt.sent!==false||
    receipt.status!=='ASSEMBLED DRAFT / HUMAN CHECK REQUIRED'||!Array.isArray(receipt.inputs)||
    !receipt.inputs.length||sha(zip)!==receipt.packageSHA256||
    !['engineSHA256','runnerSHA256','assemblerSHA256','fingerprint'].every(k=>/^[a-f0-9]{64}$/.test(receipt[k]||'')))fail('LOCAL_PACKAGE_CONTRACT_INVALID');
 const files=[{name:receipt.jobId+'.zip',bytes:zip},{name:receipt.jobId+'.receipt.json',bytes:receiptBytes}];
 const pins=[];let created=0;
 await journal({event:'prepared',jobId:receipt.jobId,files:files.map(f=>({name:f.name,sha256:sha(f.bytes),bytes:f.bytes.length})),wordGenerationPerformed:false,sourceWrites:false,sent:false});
 // Preflight both members before any write; a conflicting receipt never permits a package write.
 for(const f of files){const existing=await client.get(f.name);if(existing){if(!existing.bytes.equals(f.bytes))fail('REMOTE_REVISION_CONFLICT');pins.push(existing.pin);}else pins.push(null);}
 for(let i=0;i<files.length;i++){
  const f=files[i];if(!pins[i]){
   await journal({event:'create_attempt',name:f.name,sha256:sha(f.bytes),bytes:f.bytes.length});
   // No blind retry after an uncertain result. Next invocation reconciles native bytes first.
   await client.create(f.name,f.bytes);created++;
  }
  const after=await client.get(f.name);if(!after||!after.bytes.equals(f.bytes))fail('REMOTE_READBACK_MISMATCH');
  if(pins[i]&&JSON.stringify(after.pin)!==JSON.stringify(pins[i]))fail('REMOTE_PIN_CHANGED');
  pins[i]=after.pin;
  await journal({event:'verified',name:f.name,pin:after.pin,sha256:sha(after.bytes),bytes:after.bytes.length});
 }
 // Receipt is the last native write. Re-read the complete pair before reporting success.
 for(let i=0;i<files.length;i++){const r=await client.get(files[i].name);
  if(!r||!r.bytes.equals(files[i].bytes)||JSON.stringify(r.pin)!==JSON.stringify(pins[i]))fail('FINAL_PAIR_CHANGED');}
 const result={schemaVersion:1,state:created?'published':'replayed',jobId:receipt.jobId,
  packageSHA256:sha(zip),receiptSHA256:sha(receiptBytes),files:files.map((f,i)=>({name:f.name,pin:pins[i]})),
  status:receipt.status,wordGenerationPerformed:false,sourceWrites:false,caseWrites:false,sent:false,premiumConnectorsUsed:false};
 await journal({event:'complete',...result});return result;
}
module.exports={publish,read,sha};
