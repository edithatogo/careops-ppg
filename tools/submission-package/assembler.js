/* Local-only submission preparation. No network, source updates or approval decisions. */
(function(root) {
'use strict';
const requirements = [
 ['draft','Editable proposed document','Policy p8; Guideline pp7–10',false],
 ['approvalForm','Applicable approval form','Policy p7; Guideline p9',false],
 ['consultation','Consultation record and responses','Policy p7; Guideline pp6–9',false],
 ['endorsement','Recorded endorsement evidence','Policy p7; Guideline pp9–10',false],
 ['riskHra','Risk / HRA checklist where applicable','Guideline p9; operator confirms applicability',true],
 ['communication','Communication / implementation plan','Policy pp7–8; Guideline p10',false],
 ['evaluation','Audit / evaluation strategy','Policy p8; Guideline pp11–12',false],
 ['comparison','Source comparison / change log','Policy pp6,9; preserved versions',false]
];
const enc = new TextEncoder();
const text = value => String(value ?? '');
const escape = s => text(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const hash = async bytes => Array.from(new Uint8Array(await root.crypto.subtle.digest('SHA-256',bytes))).map(x=>x.toString(16).padStart(2,'0')).join('');
function safeName(name) {
 if (!name || name.length>180 || /[\\/:\x00-\x1f]/.test(name) || name==='.' || name==='..' || /[. ]$/.test(name)) throw Error('Unsafe attachment filename: '+name);
 return name;
}
function check(meta, attachments, notApplicable={}) {
 for (const key of ['caseUID','title','version','sourceBaseline']) if (!text(meta[key]).trim()) throw Error('Required package identity/provenance missing: '+key);
 const checks = requirements.map(([key,label,basis,optional])=>{
  const files=attachments.filter(f=>f.role===key);
  const reason=text(notApplicable[key]).trim();
  if (reason && !optional) throw Error('This evidence category cannot be bypassed: '+label);
  if (reason && files.length) throw Error('Choose attached evidence OR not applicable: '+label);
  const empty=files.some(f=>f.size===0||f.bytes?.length===0);
  const editable=key!=='draft'||files.some(f=>/\.(docx?|odt|rtf|md|txt)$/i.test(f.name));
  return {key,label,basis,files:files.map(f=>f.name),state:empty?'empty-attachment':files.length&&!editable?'editable-format-not-recognised':files.length?'attached-content-unchecked':reason?'operator-recorded-not-applicable':'missing',reason};
 });
 for (const key of ['custodianRole','documentType','documentScope','decisionRoute','nextAction']) checks.push({key,label:key,files:[],basis:'Recorded submission metadata; route to be checked against applicable matrix',state:text(meta[key]).trim()?'recorded-unverified':'missing'});
 for(const key of Object.keys(notApplicable)) if(!requirements.some(r=>r[0]===key&&r[3]) && text(notApplicable[key]).trim()) throw Error('Unknown or non-optional N/A category: '+key);
 return {status:'ASSEMBLED DRAFT / HUMAN CHECK REQUIRED',missing:checks.filter(x=>['missing','empty-attachment','editable-format-not-recognised'].includes(x.state)).length,checks,
 humanChecks:['Confirm current operative sources and correct document template.','Confirm applicable route and responsible roles against the approval matrix.','Check the applicable form and required sections, including HRA applicability.','Assess consultation coverage, responses and resolution.','Verify actual endorsement/signatures, authority, dates and the exact candidate version.','Assess content, risk, implementation and evaluation adequacy.','Confirm authorised submission channel; assembly does not send or approve anything.']};
}
const crcTable=Array.from({length:256},(_,i)=>{for(let k=0;k<8;k++)i=(i&1)?0xedb88320^(i>>>1):i>>>1;return i>>>0;});
function crc32(bytes){let c=0xffffffff;for(const x of bytes)c=crcTable[(c^x)&255]^(c>>>8);return (c^0xffffffff)>>>0;}
function zip(entries) {
 let offset=0;const chunks=[],directory=[];
 for(const entry of entries){const name=enc.encode(entry.name),bytes=entry.bytes,crc=crc32(bytes);const local=new Uint8Array(30+name.length),l=new DataView(local.buffer);
  l.setUint32(0,0x04034b50,true);l.setUint16(4,20,true);l.setUint16(6,0x800,true);l.setUint16(12,0x21,true);l.setUint32(14,crc,true);l.setUint32(18,bytes.length,true);l.setUint32(22,bytes.length,true);l.setUint16(26,name.length,true);local.set(name,30);
  const central=new Uint8Array(46+name.length),c=new DataView(central.buffer);c.setUint32(0,0x02014b50,true);c.setUint16(4,20,true);c.setUint16(6,20,true);c.setUint16(8,0x800,true);c.setUint16(14,0x21,true);c.setUint32(16,crc,true);c.setUint32(20,bytes.length,true);c.setUint32(24,bytes.length,true);c.setUint16(28,name.length,true);c.setUint32(42,offset,true);central.set(name,46);
  chunks.push(local,bytes);directory.push(central);offset+=local.length+bytes.length;
 }
 const size=directory.reduce((n,x)=>n+x.length,0),end=new Uint8Array(22),v=new DataView(end.buffer);v.setUint32(0,0x06054b50,true);v.setUint16(8,entries.length,true);v.setUint16(10,entries.length,true);v.setUint32(12,size,true);v.setUint32(16,offset,true);
 const all=[...chunks,...directory,end],result=new Uint8Array(offset+size+22);let cursor=0;for(const part of all){result.set(part,cursor);cursor+=part.length;}return result;
}
async function assemble(meta, files, options={}) {
 if(files.length>200)throw Error('Maximum 200 attachments per package');
 if(files.reduce((n,f)=>n+f.bytes.length,0)>100*1024*1024)throw Error('Maximum 100 MiB of attachments');
 const names=new Set();for(const f of files){safeName(f.name);const key=f.name.normalize('NFC').toLocaleLowerCase('en');if(names.has(key))throw Error('Duplicate attachment filename: '+f.name);names.add(key);if(!requirements.some(r=>r[0]===f.role)&&f.role!=='supporting')throw Error('Unknown evidence category');}
 const result=check(meta,files,options.notApplicable||{}),packageID=options.packageID||root.crypto.randomUUID(),generatedAt=options.generatedAt||new Date().toISOString();
 const entries=[],inventory=[];
 for(let i=0;i<files.length;i++){const f=files[i],path='attachments/'+String(i+1).padStart(3,'0')+'-'+f.name;entries.push({name:path,bytes:f.bytes});inventory.push({name:f.name,path,role:f.role,sourceReference:text(f.sourceReference),size:f.bytes.length,sha256:await hash(f.bytes)});}
 const report={...result,packageID,generatedAt,metadata:meta,attachments:inventory,scope:'File presence and recorded metadata only; no content, currency, endorsement or approval judgement.',sent:false,sourceWrites:false};
 const html='<!doctype html><meta charset="utf-8"><title>Submission package — DRAFT</title><style>body{font:16px system-ui;max-width:1100px;margin:3rem auto;padding:1rem}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:.5rem;text-align:left}h1{color:#17365d}.warning{background:#fff4ce;padding:1rem}</style>'+
 '<h1>'+escape(meta.title)+'</h1><p class="warning"><b>'+escape(result.status)+'</b><br>'+result.missing+' missing presence/metadata items. Attached files have not been substantively checked. No submission has been sent.</p>'+
 '<p>Package '+escape(packageID)+' · Generated '+escape(generatedAt)+'</p><h2>Recorded submission metadata</h2><table>'+Object.entries(meta).map(([k,v])=>'<tr><th>'+escape(k)+'</th><td>'+escape(v)+'</td></tr>').join('')+'</table>'+
 '<h2>Completeness report</h2><table><tr><th>Requirement</th><th>Mechanical result</th><th>Evidence / reason</th></tr>'+result.checks.map(c=>'<tr><td>'+escape(c.label)+'</td><td>'+escape(c.state)+'</td><td>'+escape(c.files.join('; ')||c.reason||'')+'</td></tr>').join('')+'</table>'+
 '<h2>Human checks still required</h2><ul>'+result.humanChecks.map(x=>'<li>'+escape(x)+'</li>').join('')+'</ul><h2>Attachment index</h2><table><tr><th>File</th><th>Category</th><th>Bytes / SHA256</th><th>Recorded source</th></tr>'+inventory.map(f=>'<tr><td><a href="'+f.path.split('/').map(encodeURIComponent).join('/')+'">'+escape(f.name)+'</a></td><td>'+escape(f.role)+'</td><td>'+f.size+'<br>'+f.sha256+'</td><td>'+escape(f.sourceReference)+'</td></tr>').join('')+'</table><p>Extract the ZIP before opening attachment links. Originals are unchanged; Office .captured copies retain their original bytes. Keep the extracted package in approved work storage. Applicable approval form sections and signatures need human checking.</p>';
 entries.unshift({name:'index.html',bytes:enc.encode(html)},{name:'completeness.json',bytes:enc.encode(JSON.stringify(report,null,2))});
 const manifest={packageID,generatedAt,status:result.status,metadata:meta,files:await Promise.all(entries.map(async f=>({path:f.name,size:f.bytes.length,sha256:await hash(f.bytes)})))};
 entries.push({name:'manifest.json',bytes:enc.encode(JSON.stringify(manifest,null,2))});
 return {bytes:zip(entries),report,manifest,filename:'PPG-submission-DRAFT-'+packageID+'.zip'};
}
root.PPGSubmission={requirements,check,assemble,hash,zip};
if(typeof module!=='undefined')module.exports=root.PPGSubmission;
})(globalThis);
