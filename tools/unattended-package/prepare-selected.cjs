/* Bridge the existing read-only native selection to the maintained assembler. */
'use strict';
const fs=require('node:fs/promises'),path=require('node:path');
const {read,sha}=require('./publish.cjs');
const required=(ok,code)=>{if(!ok)throw Error(code);};
async function prepare(selectionFile,metadataFile,jobFile,jobId){
 const raw=await read(selectionFile,2*1024*1024),selection=JSON.parse(raw),metadata=JSON.parse(await read(metadataFile,1024*1024));
 required(/^job-[a-z0-9-]{1,64}$/.test(jobId||''),'INVALID_JOB');
 required(selection.schemaVersion===1&&selection.kind==='existing-case-artifact-selection'&&selection.sourceWrites===false&&selection.caseWrites===false&&selection.wordGenerationPerformed===false,'UNQUALIFIED_SELECTION');
 const binding=selection.caseBinding,records=selection.catalogueBinding?.records;
 required(binding&&metadata.caseUID===binding.CaseUID&&metadata.sourceBaseline===binding.sourceBaselineRef&&typeof metadata.title==='string'&&metadata.title.trim()&&typeof metadata.version==='string'&&metadata.version.trim(),'RECORDED_METADATA_BINDING_MISMATCH');
 required(Array.isArray(records)&&records.length>0&&records.every(r=>typeof r.DocumentUID==='string'&&r.sourceSnapshotRef===binding.sourceBaselineRef),'CATALOGUE_BINDING_INVALID');
 required(Array.isArray(selection.sources)&&selection.sources.length===2&&new Set(selection.sources.map(s=>s.role)).size===2,'SELECTED_MEMBERS_INVALID');
 const input=await fs.realpath(path.dirname(selectionFile)),attachments=[];
 for(const s of selection.sources){
  required(['recorded-baseline','existing-manual-draft'].includes(s.role)&&typeof s.file==='string'&&path.basename(s.file)===s.file&&!['.','..'].includes(s.file),'SELECTED_PATH_INVALID');
  const pin=s.nativePin;
  required(pin&&typeof pin.UniqueId==='string'&&typeof pin.ETag==='string'&&pin.UIVersionLabel&&s.sourceReference&&s.zipCRCVerified===true,'NATIVE_SOURCE_PIN_MISSING');
  const b=await read(path.join(input,s.file),2*1024*1024);
  required(sha(b)===s.sha256&&b.length===s.bytes&&b.length===Number(pin.Length),'FROZEN_SOURCE_CHANGED');
  attachments.push({path:s.file,role:s.role==='existing-manual-draft'?'draft':'supporting',sha256:s.sha256,sourceReference:s.sourceReference,sourceVersionRef:pin.UIVersionLabel,sourceETag:pin.ETag,sourceUniqueId:pin.UniqueId});
 }
 const selectionName=path.basename(selectionFile);
 required(!attachments.some(a=>a.path===selectionName),'SELECTION_PATH_COLLISION');
 attachments.push({path:selectionName,role:'supporting',sha256:sha(raw),sourceReference:'Frozen native selection; historical authoring remains unknown'});
 const job={schemaVersion:1,jobId,metadata:{...metadata,includedRecordIDs:records.map(r=>r.DocumentUID),selectionSHA256:sha(raw),wordGenerationPerformed:false,authoringProvenance:selection.authoringProvenance},attachments};
 await fs.writeFile(jobFile,JSON.stringify(job,null,2)+'\n',{flag:'wx',mode:0o600});
 return {jobId,inputDirectory:input,selectedRecords:records.length,selectedFiles:attachments.length,sourceWrites:false,caseWrites:false,wordGenerationPerformed:false};
}
module.exports={prepare};
if(require.main===module){const args=process.argv.slice(2);if(args.length!==4){console.error('Usage: node prepare-selected.cjs SELECTION.json RECORDED_METADATA.json NEW_JOB.json JOB_ID');process.exitCode=2;}
 else prepare(...args).then(r=>console.log(JSON.stringify(r))).catch(e=>{console.error('Selection preparation failed: '+e.message);process.exitCode=1;});}
