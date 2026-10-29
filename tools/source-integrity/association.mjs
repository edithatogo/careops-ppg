/* Source acquisition receipts only. Inject qualified native reads/create-only writes. */
import {createHash} from 'node:crypto';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const hex=x=>typeof x==='string'&&/^[0-9a-f]{64}$/.test(x);
function canonical(value){
 if(value===null||typeof value==='string'||typeof value==='boolean')return JSON.stringify(value);
 if(typeof value==='number'&&Number.isFinite(value))return JSON.stringify(value);
 if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
 if(value&&typeof value==='object'&&[Object.prototype,null].includes(Object.getPrototypeOf(value)))return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
 throw Error('ASSOCIATION_JSON_VALUE_REQUIRED');
}
const bytes=value=>Buffer.from(canonical(value),'utf8');
const exact=(value,keys)=>value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join()===keys.slice().sort().join();
const key=x=>typeof x==='string'&&/^[a-z0-9][a-z0-9:._-]{0,199}$/.test(x);
const literal=x=>typeof x==='string'&&x.length>0&&x.length<=2048&&!/[\x00-\x1f]/.test(x);
function originalURL(value){
 if(!literal(value))throw Error('ASSOCIATION_ORIGINAL_URL_INVALID');
 const u=new URL(value);if(u.protocol!=='https:'||!u.hostname.endsWith('.sharepoint.com')||u.username||u.password||u.search||u.hash)throw Error('ASSOCIATION_ORIGINAL_URL_INVALID');
}
export function planAssociation(handoff){
 const h=structuredClone(handoff);
 if(h?.kind!=='ppg-acquisition-existing-capture-handoff-v1'||h.state!=='reuse-existing-capture'||
    !['nativeMutationAllowed','checkpointAllowed','fullAcquisitionQualified','providedEvidenceAuthenticated','clinicalApplicabilityAccepted'].every(k=>h[k]===false)||
    h.suppliedHashResultMatchesIndependentBytes!==true||!Array.isArray(h.catalogueEdits)||h.catalogueEdits.length||!Array.isArray(h.originalFilesToCreate)||h.originalFilesToCreate.length)throw Error('ASSOCIATION_PREPARATION_BOUNDARY_INVALID');
 const b=h.binding,o=h.observation;
 if(!exact(b,['publicationKey','editionKey','captureKey','requestedSourceURL','sha256'])||!['publicationKey','editionKey','captureKey'].every(k=>key(b[k]))||!hex(b.sha256)||!literal(b.requestedSourceURL))throw Error('ASSOCIATION_BINDING_INVALID');
 const u=new URL(b.requestedSourceURL);if(u.protocol!=='https:'||u.username||u.password||u.hash)throw Error('ASSOCIATION_SOURCE_URL_INVALID');
 if(!o||!literal(o.workflowId)||!literal(o.runId)||!literal(o.observedAt)||!hex(o.receiptSHA256)||!exact(o.sourceFile,['uniqueId','nativeVersion','etag','url','bytes'])||
    !['uniqueId','nativeVersion','etag'].every(k=>literal(o.sourceFile[k]))||o.sourceFile.etag==='*'||!Number.isSafeInteger(o.sourceFile.bytes)||o.sourceFile.bytes<=0||o.sourceFile.bytes>3*1024*1024)throw Error('ASSOCIATION_OCCURRENCE_INVALID');
 originalURL(o.sourceFile.url);originalURL(h.existingRetainedOriginalURL);
 const records=h.selectedRecords;
 if(!records?.publication||!records.edition||!records.capture||records.publication.key!==b.publicationKey||records.edition.key!==b.editionKey||records.capture.key!==b.captureKey||
    records.publication.kind!=='Publication'||records.edition.kind!=='Edition'||records.capture.kind!=='Capture'||records.edition.publicationKey!==b.publicationKey||records.capture.publicationKey!==b.publicationKey||records.capture.editionKey!==b.editionKey||
    records.capture.data?.sha256!==b.sha256||records.capture.data?.bytes!==o.sourceFile.bytes||records.capture.data?.nativeURL!==h.existingRetainedOriginalURL||records.capture.data?.sourceURL!==h.catalogueSourceURL)throw Error('ASSOCIATION_SELECTED_RECORDS_INVALID');
 if(!exact(h.selectedRecordSHA256,[b.publicationKey,b.editionKey,b.captureKey])||!Object.values(h.selectedRecordSHA256).every(hex))throw Error('ASSOCIATION_RECORD_HASHES_INVALID');
 if(sha(bytes(b))!==h.replayKey||sha(bytes({...b,workflowId:o.workflowId,runId:o.runId,sourceFile:o.sourceFile}))!==h.occurrenceKey)throw Error('ASSOCIATION_REPLAY_KEY_DRIFT');
 const claim={kind:'ppg-source-capture-replay-claim-v1',replayKey:h.replayKey,binding:b,
  selectedRecordSHA256:h.selectedRecordSHA256,existingRetainedOriginalURL:h.existingRetainedOriginalURL,
  catalogueSourceURL:h.catalogueSourceURL,publicationPromotionPerformed:false,fullAcquisitionQualified:false};
 const occurrence={kind:'ppg-source-acquisition-occurrence-v1',replayKey:h.replayKey,occurrenceKey:h.occurrenceKey,handoff:h};
 const claimBytes=bytes(claim),occurrenceBytes=bytes(occurrence);
 if(occurrenceBytes.length>1024*1024)throw Error('ASSOCIATION_RECEIPT_LIMIT');
 const files=[{name:'source-replay-'+h.replayKey+'.json',bytes:claimBytes},
  {name:'source-occurrence-'+h.occurrenceKey+'.json',bytes:occurrenceBytes}];
 files.push({name:'source-commit-'+h.occurrenceKey+'.json',bytes:bytes({kind:'ppg-source-association-commit-v1',
  replayKey:h.replayKey,occurrenceKey:h.occurrenceKey,members:files.map(f=>({name:f.name,sha256:sha(f.bytes),bytes:f.bytes.length})),
  cataloguePromotionPerformed:false,checkpointAdvanced:false,fullAcquisitionQualified:false})});
 return {handoff:h,files};
}
function checkNativeRead(read,wanted){
 if(!read||!Buffer.isBuffer(read.bytes)||!read.bytes.equals(wanted.bytes)||!read.pin||
    !literal(read.pin.UniqueId)||!literal(read.pin.ETag)||read.pin.ETag==='*'||!literal(read.pin.UIVersionLabel)||
    String(read.pin.Length)!==String(wanted.bytes.length)||!literal(read.pin.ServerRelativeUrl)||!read.pin.ServerRelativeUrl.endsWith('/'+wanted.name))throw Error('ASSOCIATION_NATIVE_READBACK_MISMATCH');
 return canonical(read.pin);
}
function checkNativeRecords(proof,handoff){
 const keys=Object.keys(handoff.selectedRecordSHA256);
 if(!exact(proof,['selectedRecordJSON'])||!exact(proof.selectedRecordJSON,keys))throw Error('ASSOCIATION_NATIVE_RECORD_PROOF_REQUIRED');
 for(const kind of ['publication','edition','capture']){
  const record=handoff.selectedRecords[kind];
  const raw=proof.selectedRecordJSON[record.key];
  if(typeof raw!=='string'||Buffer.byteLength(raw,'utf8')>1024*1024)throw Error('ASSOCIATION_NATIVE_RECORD_PROOF_REQUIRED');
  // Hash the actual native JSON, preserving its numeric and whitespace spelling.
  // Comparing parsed content separately binds the copied payload to those bytes.
  if(sha(Buffer.from(raw,'utf8'))!==handoff.selectedRecordSHA256[record.key])throw Error('ASSOCIATION_NATIVE_RECORD_HASH_MISMATCH');
  let current;try{current=JSON.parse(raw);}catch{throw Error('ASSOCIATION_NATIVE_RECORD_PROOF_REQUIRED');}
  if(canonical(current)!==canonical(record))throw Error('ASSOCIATION_NATIVE_RECORD_PAYLOAD_MISMATCH');
 }
}
export async function persistAssociation({handoff,client,verifyBindings,journal}){
 const plan=planAssociation(handoff);
 if(typeof verifyBindings!=='function'||typeof journal!=='function'||typeof client?.get!=='function'||typeof client?.create!=='function')throw Error('ASSOCIATION_QUALIFIED_TRANSPORT_REQUIRED');
 // The handoff is deliberately non-authorising. Qualified runtime code must check
 // current native records, original bytes/pins, allowed destination and ownership.
 const verify=async()=>checkNativeRecords(await verifyBindings(plan.handoff),plan.handoff);
 await verify();
 await journal({event:'association_prepared',replayKey:handoff.replayKey,occurrenceKey:handoff.occurrenceKey,files:plan.files.map(f=>({name:f.name,sha256:sha(f.bytes)}))});
 const pins=[];
 // Check all members before any mutation, including an existing commit marker.
 for(const f of plan.files){const old=await client.get(f.name);pins.push(old?checkNativeRead(old,f):null);}
 // A completed set with a missing member is corruption/deletion, not an
 // interrupted initial publish. Hold it for explicit recovery in a new namespace.
 if(pins[2]!==null&&(pins[0]===null||pins[1]===null))throw Error('ASSOCIATION_COMMITTED_SET_INCOMPLETE');
 let created=0;
 for(let i=0;i<plan.files.length;i++){
  const f=plan.files[i];
  if(pins[i]===null){
   await verify();
   await journal({event:'association_create_intent',name:f.name,sha256:sha(f.bytes)});
   try{await client.create(f.name,f.bytes);}catch(error){
    await journal({event:'association_create_uncertain',name:f.name,status:error.response?.status??error.status??null,reconcileBeforeRetry:true});
    const held=Error('ASSOCIATION_CREATE_UNCERTAIN');held.status=error.response?.status??error.status??null;throw held;
   }
   created++;
  }
  const pin=checkNativeRead(await client.get(f.name),f);
  if(pins[i]!==null&&pins[i]!==pin)throw Error('ASSOCIATION_NATIVE_PIN_CHANGED');
  pins[i]=pin;await journal({event:'association_member_verified',name:f.name,pin:JSON.parse(pin),sha256:sha(f.bytes)});
 }
 await verify();
 for(let i=0;i<plan.files.length;i++)if(checkNativeRead(await client.get(plan.files[i].name),plan.files[i])!==pins[i])throw Error('ASSOCIATION_FINAL_MEMBER_CHANGED');
 const result={kind:'ppg-source-association-persistence-v1',state:created?'persisted':'replayed',created,
  replayKey:handoff.replayKey,occurrenceKey:handoff.occurrenceKey,
  files:plan.files.map((f,i)=>({name:f.name,sha256:sha(f.bytes),pin:JSON.parse(pins[i])})),
  associationCommitVerified:true,catalogueRowsChanged:0,originalCapturesCreated:0,originalsChanged:false,
  checkpointAdvanced:false,fullAcquisitionQualified:false,clinicalApplicabilityAccepted:false};
 await journal({event:'association_complete',...result});return result;
}
