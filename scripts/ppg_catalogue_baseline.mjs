/* Create-only retained baseline loading; the injected adapter owns authentication/journals. */
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
const fields=new Set('Title DocumentUID sourceDocumentId sourceTitle sourceCustodian sourceNextReviewDateRaw sourceNextReviewMonth sourceStatus sourceRisk sourceSnapshotRef sourceAsOfUtc sourceRowNumber rawSourceRecordRef sourceIdentityDecisionRef'.split(' '));
export async function install(c,plan,target,progress=()=>{}){
 if(plan.mode!=='create-only-retained-baseline'||!Array.isArray(plan.rows)||!plan.rows.length||!(/^[0-9a-f-]{36}$/i.test(target.id)))throw Error('BASELINE_TARGET_REQUIRED');
 const keys=new Set();for(const r of plan.rows){if(!/^[0-9a-f-]{36}$/i.test(r.DocumentUID)||keys.has(r.DocumentUID)||Object.keys(r).some(k=>!fields.has(k)))throw Error('BASELINE_IDENTITY_OR_FIELDS');keys.add(r.DocumentUID);}
 const route=`lists(guid'${target.id}')`,meta=await c.get(route+'?$select=Title');if(meta.Title!==target.title)throw Error('TARGET_CHANGED');
 const read=()=>c.all(route+'/items?$top=1000');const before=await read();const index=new Map(before.map(r=>[r.DocumentUID,r]));if(index.size!==before.length)throw Error('DUPLICATE_NATIVE_IDENTITY');
 const equal=(a,b)=>Object.entries(a).every(([k,v])=>v===b[k]||(v===null&&b[k]===''));
 const pending=plan.rows.filter(r=>{if(!index.has(r.DocumentUID))return true;if(!equal(r,index.get(r.DocumentUID)))throw Error('PRESERVE_CHANGED_NATIVE_ROW');return false;});
 for(let start=0;start<pending.length;start+=20){const rows=pending.slice(start,start+20),boundary='batch_'+randomUUID(),parts=[];
  for(const row of rows){const cs='changeset_'+randomUUID();parts.push('--'+boundary,'Content-Type: multipart/mixed; boundary='+cs,'','--'+cs,'Content-Type: application/http','Content-Transfer-Encoding: binary','',`POST ${c.c.siteUrl}/_api/web/${route}/items HTTP/1.1`,'Content-Type: application/json;odata=nometadata','Accept: application/json;odata=nometadata','',JSON.stringify(row),'--'+cs+'--');}
  parts.push('--'+boundary+'--','');const payload=Buffer.from(parts.join('\r\n')),digest=createHash('sha256').update(JSON.stringify(rows)).digest('hex');
  const response=await c.send({key:'baseline-'+digest,route:c.c.siteUrl+'/_api/$batch',payload,payloadSHA256:createHash('sha256').update(payload).digest('hex'),contentType:'multipart/mixed; boundary='+boundary});
  const statuses=[...String(response).matchAll(/HTTP\/1\.[01] (\d{3})/g)].map(m=>Number(m[1]));if(statuses.length!==rows.length||statuses.some(s=>s!==201))throw Error('PARTIAL_BATCH_RECONCILE_BEFORE_RESUME');
  progress({created:start+rows.length,total:pending.length});await new Promise(r=>setTimeout(r,10000));
 }
 const after=await read(),actual=new Map(after.map(r=>[r.DocumentUID,r]));if(actual.size!==after.length||plan.rows.some(r=>!actual.has(r.DocumentUID)||!equal(r,actual.get(r.DocumentUID))))throw Error('BASELINE_READBACK_MISMATCH');
 return {created:pending.length,verified:plan.rows.length,preservedOtherRows:after.length-plan.rows.length,active:plan.activeCount,retainedAbsent:plan.retainedAbsentCount,currentSourceReconciled:false};
}
if(process.argv[1]&&resolve(process.argv[1])===new URL(import.meta.url).pathname){
 const [adapter,planFile,targetFile,receipt]=process.argv.slice(2);if(!receipt||!resolve(receipt).split('/').includes('.local')||fs.existsSync(receipt))throw Error('NEW_PRIVATE_RECEIPT_REQUIRED');
 const c=await(await import(pathToFileURL(resolve(adapter)))).connect();const result=await install(c,JSON.parse(fs.readFileSync(planFile)),JSON.parse(fs.readFileSync(targetFile)),x=>console.log(JSON.stringify(x)));fs.writeFileSync(receipt,JSON.stringify(result,null,2),{flag:'wx',mode:0o600});console.log(result);
}
