/* Create-only source-copy publication. Original sources and native AI are untouched. */
'use strict';
const fs=require('node:fs/promises'),path=require('node:path');
const {read,sha}=require('../unattended-package/publish.cjs');
async function publishSources(directory,client,journal,verifyDifference){
 const root=await fs.realpath(directory),manifestBytes=await read(path.join(root,'manifest.json'),2_000_000),manifest=JSON.parse(manifestBytes);
 const valid=manifest.schemaVersion===1&&manifest.kind==='cli-assistant-source-preparation-v1'&&/^[a-z0-9][a-z0-9-]{0,63}$/.test(manifest.preparationId||'')&&
  manifest.originalSourceWrites===false&&manifest.wordBodyGenerationPerformed===false&&manifest.conversationalRetrievalQualified===false&&
  Array.isArray(manifest.sources)&&manifest.sources.length>0&&manifest.sources.length<=5&&new Set(manifest.sources.map(s=>s.sourceId)).size===manifest.sources.length;
 if(!valid)throw Error('INVALID_SOURCE_MANIFEST');
 const files=[];
 for(const s of manifest.sources){
  if(!/^[a-z0-9][a-z0-9-]{0,63}$/.test(s.sourceId||'')||!['captured-reference-unconfirmed','draft-unapproved'].includes(s.authorityLabel)||
     !s.name?.startsWith(manifest.preparationId+'-'+s.sourceId+'.')||!/^[-a-z0-9]+\.(txt|md|docx|pdf)$/.test(s.name)||
     !/^[a-f0-9]{64}$/.test(s.sha256||'')||!/^[a-f0-9]{64}$/.test(s.expectedTextSHA256||'')||
     !['exact-bytes','sharepoint-schema-attributes-v1'].includes(s.ingestionPolicy||'exact-bytes'))throw Error('INVALID_PREPARED_SOURCE');
  const bytes=await read(path.join(root,'sources',s.name),2_000_000);
  if(bytes.length!==s.bytes||sha(bytes)!==s.sha256)throw Error('PREPARED_SOURCE_CHANGED');
  files.push({name:s.name,bytes,source:s});
 }
 const receiptName=manifest.preparationId+'.sources.json',observed=[];
 const qualify=async(f,actual)=>{
  if(actual.bytes.equals(f.bytes))return {kind:'exact-bytes',originalSHA256:sha(f.bytes),nativeSHA256:sha(actual.bytes),changedParts:[]};
  if(f.source.ingestionPolicy!=='sharepoint-schema-attributes-v1'||!f.name.endsWith('.docx')||!verifyDifference)throw Error('REMOTE_REVISION_CONFLICT');
  const proof=await verifyDifference(f.bytes,actual.bytes,f.name,f.source.ingestionPolicy);
  if(proof.kind!=='sharepoint-schema-attributes-v1'||proof.originalSHA256!==sha(f.bytes)||proof.nativeSHA256!==sha(actual.bytes)||proof.supportedTextAndLocatorsEqual!==true||proof.otherPackagePartsByteExact!==true)throw Error('NATIVE_INGESTION_NOT_QUALIFIED');
  return proof;
 };
 await journal({event:'prepared',preparationId:manifest.preparationId,manifestSHA256:sha(manifestBytes)});
 // Reconcile all known artifacts before any mutation; never replace a conflicting receipt.
 for(const f of files){const existing=await client.get(f.name);observed.push(existing?{...existing,proof:await qualify(f,existing)}:null);}
 const existingReceipt=await client.get(receiptName);
 if(existingReceipt&&observed.some(x=>!x))throw Error('COMMITTED_RECEIPT_WITH_MISSING_SOURCE');
 let created=0;
 for(let i=0;i<files.length;i++){
  const f=files[i];if(!observed[i]){
   await journal({event:'create_attempt',name:f.name,originalSHA256:sha(f.bytes),bytes:f.bytes.length});
   await client.create(f.name,f.bytes);created++;
   const actual=await client.get(f.name);if(!actual)throw Error('NATIVE_SOURCE_NOT_READABLE');
   observed[i]={...actual,proof:await qualify(f,actual)};
  }
  await journal({event:'verified',name:f.name,pin:observed[i].pin,originalSHA256:sha(f.bytes),nativeSHA256:sha(observed[i].bytes),ingestion:observed[i].proof.kind});
 }
 const sourceIntegrity=files.map((f,i)=>({sourceId:f.source.sourceId,proof:observed[i].proof,pin:observed[i].pin}));
 const receipt={schemaVersion:1,kind:'cli-prepared-source-publication-v1',preparationId:manifest.preparationId,manifestSHA256:sha(manifestBytes),preparedManifest:manifest,sourceIntegrity,
  originalSourceWrites:false,conversationalRetrievalQualified:false};
 const receiptBytes=Buffer.from(JSON.stringify(receipt,null,2)+'\n');
 if(existingReceipt&&!existingReceipt.bytes.equals(receiptBytes))throw Error('REMOTE_REVISION_CONFLICT');
 if(!existingReceipt){await journal({event:'create_attempt',name:receiptName,sha256:sha(receiptBytes)});await client.create(receiptName,receiptBytes);created++;}
 const savedReceipt=await client.get(receiptName);
 if(!savedReceipt||!savedReceipt.bytes.equals(receiptBytes)||(existingReceipt&&JSON.stringify(existingReceipt.pin)!==JSON.stringify(savedReceipt.pin)))throw Error('NATIVE_RECEIPT_CHANGED');
 for(let i=0;i<files.length;i++){const actual=await client.get(files[i].name);if(!actual||!actual.bytes.equals(observed[i].bytes)||JSON.stringify(actual.pin)!==JSON.stringify(observed[i].pin))throw Error('FINAL_SOURCE_CHANGED');}
 const nativeFiles=files.map((f,i)=>({name:f.name,pin:observed[i].pin}));nativeFiles.push({name:receiptName,pin:savedReceipt.pin});
 const selected=manifest.sources.map((s,i)=>({sourceId:s.sourceId,path:nativeFiles[i].pin.ServerRelativeUrl,nativeUniqueId:nativeFiles[i].pin.UniqueId,authorityLabel:s.authorityLabel}));
 const result={schemaVersion:1,preparationId:manifest.preparationId,state:created?'published':'replayed',manifestSHA256:sha(manifestBytes),receiptSHA256:sha(receiptBytes),sourceIntegrity,
  files:nativeFiles,selected,originalSourceWrites:false,newFilesCreated:created,premiumConnectorsUsed:false,paidAIRuntimeUsed:false,conversationalRetrievalQualified:false};
 await journal({event:'complete',...result});return result;
}
module.exports={publishSources};
