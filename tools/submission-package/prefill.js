/* Recorded metadata only. Never supply signatures, approvals or substantive findings. */
(function(root){
'use strict';
const requiredHeadings=['Intended result and next decision','Source baseline and preservation','Source and control comparison','Proposed amendments and change log','Ownership and implementation','Targeted consultation and decision','Readiness and measures'];
const metadataKeys=['caseUID','title','version','sourceBaseline','officialDocumentID','documentType','documentScope','custodianRole','decisionRoute','nextAction'];
const uidPattern=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const businessKeys=['reviewer_response','operative_confirmation','role_acceptance','review_findings','decision_evidence'];
const sourceKeys=['DocumentUID','sourceTitle','sourceDocumentId','sourceDocumentType','sourceCustodian','sourceNextReviewMonth','sourceNextReviewDateRaw','sourceStatus','sourceRisk','sourceSnapshotRef','sourceAsOfUtc','rawSourceRecordRef'];
const enc=new TextEncoder();const str=x=>String(x??'');const oneLine=x=>str(x).replace(/[\r\n]+/g,' ').trim();
const esc=s=>str(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
function importSource(meta,record){
 if(!record||typeof record!=='object'||Array.isArray(record)||typeof record.DocumentUID!=='string'||!uidPattern.test(record.DocumentUID))throw Error('Select one source record with its DocumentUID; no identity will be inferred');
 const fields=record.fields||record;const facts={DocumentUID:record.DocumentUID};
 for(const key of sourceKeys.filter(k=>k!=='DocumentUID'))if(fields[key]!==undefined){if(fields[key]!==null&&!['string','number'].includes(typeof fields[key]))throw Error('Invalid source scalar: '+key);facts[key]=fields[key];}
 const result={...meta},conflicts=[];for(const[key,value]of [['title',facts.sourceTitle],['sourceBaseline',facts.sourceSnapshotRef],['documentType',facts.sourceDocumentType]])if(str(value).trim()){
  if(!str(result[key]).trim())result[key]=str(value);else if(result[key]!==str(value))conflicts.push({field:key,kept:result[key],source:str(value)});
 }
 return {metadata:result,sourceFacts:facts,conflicts,notice:'Source assertions retained separately. Existing local values, version, official ID, roles and decisions are not overwritten.'};
}
function tableCell(v){return str(v).replace(/\|/g,'\\|').replace(/[\r\n]+/g,' ');}
function mapping(meta,sourceFacts={}){
 if(!meta||typeof meta!=='object'||Array.isArray(meta))throw Error('Metadata must be an object');
 for(const[k,v]of Object.entries(meta))if(!metadataKeys.includes(k)||typeof v!=='string')throw Error('Unsupported metadata field/value: '+k);
 if(!sourceFacts||typeof sourceFacts!=='object'||Array.isArray(sourceFacts))throw Error('Source facts must be an object');
 for(const[k,v]of Object.entries(sourceFacts))if(!sourceKeys.includes(k)||(v!==null&&!['string','number'].includes(typeof v)))throw Error('Unsupported source field/value: '+k);
 if('DocumentUID' in sourceFacts&&(typeof sourceFacts.DocumentUID!=='string'||!uidPattern.test(sourceFacts.DocumentUID)))throw Error('Invalid source DocumentUID');
 for(const key of ['caseUID','title','version','sourceBaseline'])if(!str(meta[key]).trim())throw Error('Metadata required: '+key);
 const pending='[NOT RECORDED — human input required]';
 const values={case_title:oneLine(meta.title),CaseUID:oneLine(meta.caseUID),source_snapshot:oneLine(meta.sourceBaseline),version:oneLine(meta.version),
 intended_result:pending,source_manifest:Object.entries(sourceFacts).length?'| Source assertion | Recorded value |\n|---|---|\n'+Object.entries(sourceFacts).map(([k,v])=>'| '+tableCell(k)+' | '+tableCell(v)+' |').join('\n'):pending,
 comparison_rows:'| Not recorded | Not recorded | Not assessed | Not proposed | Human comparison required |',draft_links_and_changes:pending,
 ownership_and_implementation:'Recorded/proposed custodian role: '+(meta.custodianRole||pending)+'\nAcceptance, capacity and implementation: '+pending,
 decision_route:meta.decisionRoute?'Recorded/proposed route (unverified): '+meta.decisionRoute:pending,
 consultation_rows:'| Not recorded | Human consultation required | '+tableCell(meta.version)+' | Not recorded |',candidate_reference:'Generated DRAFT; see package manifest for file hash',
 next_action:meta.nextAction?'Recorded next action (not an agreed commitment): '+meta.nextAction:pending,measures:pending};
 for(const key of businessKeys)values[key]=pending;
 return values;
}
function checkStructure(text,meta){
 const headings=Array.from(text.matchAll(/^##\s+(.+?)\s*$/gm)).map(m=>m[1].trim());const issues=[];
 for(const h of requiredHeadings){const count=headings.filter(x=>x===h).length;if(count!==1)issues.push({kind:count?'duplicate-section':'missing-section',field:h,count});}
 const order=requiredHeadings.map(h=>headings.indexOf(h));if(order.every(x=>x>=0)&&order.some((v,i)=>i&&v<order[i-1]))issues.push({kind:'section-order',field:'required sections'});
 const unresolved=Array.from(new Set(Array.from(text.matchAll(/\{\{([^{}]+)\}\}/g)).map(m=>m[1])));for(const field of unresolved)issues.push({kind:'unresolved-placeholder',field});
 if(!/^Status: DRAFT \/ AWAITING REVIEW$/m.test(text))issues.push({kind:'draft-status',field:'Status'});
 if(meta){const expected='Case: '+oneLine(meta.caseUID)+' | Source baseline: '+oneLine(meta.sourceBaseline)+' | Candidate: '+oneLine(meta.version);if(!text.split(/\r?\n/).includes(expected))issues.push({kind:'metadata-mismatch',field:'case/baseline/version header'});if(!text.split(/\r?\n/).includes('# Review package — '+oneLine(meta.title)))issues.push({kind:'metadata-mismatch',field:'title header'});}
 return {status:'STRUCTURAL CHECK ONLY / HUMAN REVIEW REQUIRED',passed:issues.length===0,issues,headings,contentReviewed:false,approved:false};
}
function render(template,meta,sourceFacts={}){
 const values=mapping(meta,sourceFacts);const keys=Array.from(new Set(Array.from(template.matchAll(/\{\{([^{}]+)\}\}/g)).map(m=>m[1])));
 if(!keys.length)throw Error('No template placeholders found; refusing to overwrite or repopulate an edited document');
 for(const key of keys)if(!(key in values))throw Error('Unsupported placeholder (no approval/signature inference): '+key);
 for(const v of Object.values(values))if(/\{\{|\}\}/.test(v))throw Error('Template markers in recorded values');
 const text=template.replace(/\{\{([^{}]+)\}\}/g,(_,k)=>str(values[k]));const report=checkStructure(text,meta);if(!report.passed)throw Error('Template structure needs correction: '+report.issues.map(x=>x.kind+': '+x.field).join('; '));
 return {text,report,businessFieldsPrefilled:false};
}
function cover(meta,sourceFacts={}){
 mapping(meta,sourceFacts);const p=(t,style='')=>'<w:p>'+(style?'<w:pPr><w:pStyle w:val="'+style+'"/></w:pPr>':'')+'<w:r><w:t xml:space="preserve">'+esc(t)+'</w:t></w:r></w:p>';
 const table=rows=>'<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblBorders>'+['top','left','bottom','right','insideH','insideV'].map(k=>'<w:'+k+' w:val="single" w:sz="4" w:color="B0B0B0"/>').join('')+'</w:tblBorders></w:tblPr>'+rows.map(row=>'<w:tr>'+row.map(cell=>'<w:tc><w:tcPr><w:tcW w:w="4600" w:type="dxa"/></w:tcPr>'+p(cell)+'</w:tc>').join('')+'</w:tr>').join('')+'</w:tbl>';
 const human=['Reviewer / actual response','Operative-version confirmation','Role acceptance / capacity','Findings / conditions','Actual endorsement / authority / date','Actual approval / authority / date','Signature'];
 const body=p('METADATA COVER — DRAFT','Title')+p('Local preparation aid. Not the official approval form. No submission, endorsement, approval or signature supplied.')+p('Recorded local metadata','Heading1')+table(Object.entries(meta).map(([k,v])=>[k,str(v)]))+p('Imported source assertions — unverified currency','Heading1')+(Object.keys(sourceFacts).length?table(Object.entries(sourceFacts).map(([k,v])=>[k,str(v)])):p('No source record imported.'))+p('Human decision fields — intentionally blank','Heading1')+table(human.map(x=>[x,'']))+p('Required human checks','Heading1')+p('Confirm the applicable official template/form, required sections, current source, route, roles, consultation, evidence adequacy and actual signatories/version. Structural checks do not establish readiness.');
 const files=[{name:'[Content_Types].xml',bytes:enc.encode('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')},
 {name:'_rels/.rels',bytes:enc.encode('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')},
 {name:'word/document.xml',bytes:enc.encode('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080"/></w:sectPr></w:body></w:document>')},
 {name:'word/_rels/document.xml.rels',bytes:enc.encode('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')},
 {name:'word/styles.xml',bytes:enc.encode('<?xml version="1.0"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style></w:styles>')}];
 return root.PPGSubmission.zip(files);
}
root.PPGPrefill={requiredHeadings,businessKeys,importSource,mapping,checkStructure,render,cover};
})(globalThis);
