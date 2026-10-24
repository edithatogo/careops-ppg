import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {persist} from '../tools/external-catalogue/records.mjs';
import {provisionViews,configureLinks} from '../tools/external-catalogue/native.mjs';
const row={Title:'Fictional',RecordKey:'pub:fixture',RecordKind:'Publication',PublicationKey:'pub:fixture',EditionKey:null,
 Issuer:'Fictional',SourceStatus:'Unknown',SourceRole:'Supporting',TrancheKey:'fictional',
 RecordJSON:JSON.stringify({key:'pub:fixture',kind:'Publication'}),PayloadSHA256:'',ReviewState:'Proposed',OfficialURL:'https://www.safetyandquality.gov.au/fixture',EvidenceURL:null,RelatedRecordsURL:null};
row.PayloadSHA256=createHash('sha256').update(row.RecordJSON).digest('hex');
test('create/readback and unchanged replay',async()=>{
 const stored=[],events=[];const options={rows:[row],read:async()=>structuredClone(stored),create:async x=>stored.push({...x,Id:1}),journal:async e=>events.push(e)};
 assert.equal((await persist(options)).created,1);assert.equal((await persist(options)).created,0);
 assert.equal(events.filter(e=>e.phase==='intent').length,1);
 assert.equal(events.filter(e=>e.phase==='verified').length,1);
});
test('human state conflict refuses every create',async()=>{
 let writes=0;await assert.rejects(persist({rows:[row],read:async()=>[{...row,ReviewState:'Accepted'}],create:async()=>writes++,journal:async()=>{}}),/PRESERVE_CHANGED/);assert.equal(writes,0);
});
test('uncertain creation is reconciled on next invocation without retry',async()=>{
 let stored=[],calls=0;const o={rows:[row],read:async()=>stored,create:async x=>{calls++;stored=[{...x,Id:1}];throw Error('response lost');},journal:async()=>{}};
 await assert.rejects(persist(o),/response lost/);assert.equal((await persist(o)).created,0);assert.equal(calls,1);
});
test('view creation uses modern string array and exact native query spelling',async()=>{
 const stored=[];let savedFields;const client={all:async()=>stored,call:async(method,route,data)=>{
  if(method==='GET')return {Items:savedFields};
  assert.equal(method,'POST');assert.ok(Array.isArray(data.parameters.ViewFields));
  assert.match(data.parameters.Query, /Name="RecordKind" \/>/);
  savedFields=data.parameters.ViewFields;
  stored.push({Title:data.parameters.Title,ViewQuery:data.parameters.Query,Id:String(stored.length+1),RowLimit:100,Paged:true,DefaultView:false,PersonalView:false});
 }};
 assert.equal((await provisionViews(client,'fictional',async()=>{})).length,5);
 assert.equal((await provisionViews(client,'fictional',async()=>{})).length,5);
 assert.equal(stored.length,5);
});
test('view conflict is preserved without a corrective mutation',async()=>{
 let calls=0;await assert.rejects(provisionViews({all:async()=>[{Title:'Publication catalogue',ViewQuery:'human query'}],call:async()=>calls++},'fictional',async()=>{}),/PRESERVE_CHANGED_VIEW/);assert.equal(calls,0);
});
test('link configuration supports absent direct capture and unchanged replay',async()=>{
 const formats=new Map(),columns=['LinkTitle'];let writes=0;
 const client={all:async()=>[{Id:'fixture',Title:'All Items'}],call:async(method,route,data)=>{
  const field=route.match(/getbyinternalnameortitle\('([^']+)'\)/)?.[1];
  if(field){if(method==='GET')return {CustomFormatter:formats.get(field)||''};formats.set(field,data.CustomFormatter);writes++;return {};}
  if(method==='GET')return {Items:[...columns]};
  columns.push(route.match(/AddViewField\('([^']+)'\)/)[1]);writes++;return {};
 }};
 assert.equal((await configureLinks(client,'fixture',async()=>{})).defaultFieldsVerified,11);
 assert.match(formats.get('EvidenceURL'),/Related evidence/);const count=writes;
 await configureLinks(client,'fixture',async()=>{});assert.equal(writes,count);
});
test('a human column formatter is never repaired implicitly',async()=>{
 let writes=0;await assert.rejects(configureLinks({call:async method=>{if(method==='GET')return {CustomFormatter:'human formatter'};writes++;},all:async()=>[]},'fixture',async()=>{}),/PRESERVE_CHANGED_COLUMN_FORMATTER/);assert.equal(writes,0);
});
test('native links cannot redirect to another site or executable scheme',async()=>{
 let creates=0;const o={site:'https://example.sharepoint.com/sites/fixture',read:async()=>[],create:async()=>creates++,journal:async()=>{}};
 await assert.rejects(persist({...o,rows:[{...row,EvidenceURL:'javascript:alert(1)'}]}),/STABLE_NATIVE_LINK/);
 await assert.rejects(persist({...o,rows:[{...row,EvidenceURL:'https://example.sharepoint.com/sites/other/file.pdf'}]}),/BOUND_NATIVE_LINK/);
 await assert.rejects(persist({...o,rows:[{...row,OfficialURL:'https://example.org/pretend-official'}]}),/OFFICIAL_SOURCE_URL/);
 assert.equal(creates,0);
});
