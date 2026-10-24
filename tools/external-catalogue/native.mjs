/* Bounded CLI adapter. Existing M365 SDK/session; no credential/profile changes. */
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {validateRenewalIdentity} from '../lifecycle/validate_renewal_identity.mjs';
import {fields,persist,difference} from './records.mjs';

export async function connect(config) {
 const site=new URL(config.siteUrl),expected=config.identity;
 if(site.protocol!=='https:'||!site.hostname.endsWith('.sharepoint.com')||site.username||site.password||site.search||site.hash||!/^\/(teams|sites)\/[^/]+$/.test(site.pathname)||!expected?.objectId||!config.connectionName)throw Error('EXACT_PRIVATE_BINDING_REQUIRED');
 const sdk=path.resolve(config.sdkDirectory);
 const [{default:auth},{default:request}]=await Promise.all(['Auth.js','request.js'].map(f=>import(pathToFileURL(path.join(sdk,f)))));
 request.logger={log:async()=>{},logToStderr:async()=>{}};request.debug=false;
 await auth.restoreAuth();
 if(auth.connection.name!==config.connectionName||auth.connection.appId!==expected.appId||auth.connection.tenant!==expected.tenantId)throw Error('SAVED_CLIENT_MISMATCH');
 const app=await auth.getPublicClient(request.logger,false),accounts=await app.getTokenCache().getAllAccounts();
 const matches=accounts.filter(a=>a.localAccountId?.toLowerCase()===expected.objectId.toLowerCase()&&a.tenantId?.toLowerCase()===expected.tenantId.toLowerCase()&&a.username?.toLowerCase()===expected.username.toLowerCase());
 if(matches.length!==1)throw Error('UNIQUE_SAVED_ACCOUNT_REQUIRED');
 const token=await app.acquireTokenSilent({account:matches[0],scopes:[site.origin+'/.default'],forceRefresh:false});
 validateRenewalIdentity(token,expected);
 if(!token.accessToken||new Date(token.expiresOn).getTime()<Date.now()+60000)throw Error('UNEXPIRED_SAME_CLIENT_TOKEN_REQUIRED');
 const base=site.href+'/_api/web/';
 async function call(method,relative,data) {
  const url=new URL(relative,base);
  if(url.origin!==site.origin||!url.pathname.startsWith(site.pathname+'/_api/web/'))throw Error('BOUND_NATIVE_ROUTE_REQUIRED');
  // Direct Axios instance: no CLI execute() retry wrapper or redirect replay.
  const result=await request.req.request({method,url:url.href,data,
   headers:{Authorization:'Bearer '+token.accessToken,Accept:'application/json;odata=nometadata',...(data?{'Content-Type':'application/json;odata=nometadata'}:{})},
   family:4,maxRedirects:0,timeout:30000,signal:AbortSignal.timeout(30000),responseType:'json',maxContentLength:16*1024*1024,maxBodyLength:16*1024*1024});
  return result.data;
 }
 async function all(route) {
  const result=[],seen=new Set();let next=route;
  while(next){if(seen.has(next)||seen.size>=100)throw Error('INCOMPLETE_NATIVE_PAGINATION');seen.add(next);const r=await call('GET',next);if(!Array.isArray(r.value))throw Error('EXPECTED_NATIVE_COLLECTION');result.push(...r.value);next=r['odata.nextLink']||r['@odata.nextLink']||null;}
  return result;
 }
 return {call,all};
}

export async function bootstrap(client,journal,title='PPG External Publications') {
 if(!['PPG External Publications','PPG External Publications Recovery'].includes(title))throw Error('BOUNDED_CATALOGUE_TARGET_REQUIRED');
 let rows=(await client.all('lists?$select=Id,Title,EnableVersioning')).filter(r=>r.Title===title);
 if(rows.length>1)throw Error('AMBIGUOUS_CATALOGUE');
 if(!rows.length){await journal({phase:'list-intent',title});const saved=await client.call('POST','lists',{Title:title,Description:'External publication, edition, source capture and reference provenance. Proposed records do not establish clinical applicability.',BaseTemplate:100,EnableVersioning:true});rows=[saved];await journal({phase:'list-created',id:saved.Id});}
 const list=rows[0];if(!list.EnableVersioning)throw Error('VERSION_HISTORY_REQUIRED');
 const route="lists(guid'"+list.Id+"')";
 const present=await client.all(route+'/fields?$select=InternalName,TypeAsString,Required,Indexed,EnforceUniqueValues');
 for(const name of fields.filter(n=>n!=='Title')) {
  const type=['RecordJSON','OfficialURL','EvidenceURL','RelatedRecordsURL'].includes(name)?'Note':'Text',required=['RecordKey','RecordKind','RecordJSON','PayloadSHA256','ReviewState'].includes(name);
  const match=present.filter(f=>f.InternalName===name);if(match.length>1)throw Error('AMBIGUOUS_FIELD');
  if(!match.length){
   const unique=name==='RecordKey',indexed=['RecordKey','RecordKind','PublicationKey','EditionKey','Issuer','SourceStatus','SourceRole','TrancheKey','ReviewState'].includes(name);
   const xml=`<Field Type="${type}" Name="${name}" StaticName="${name}" DisplayName="${name}" Required="${required?'TRUE':'FALSE'}" Indexed="${indexed?'TRUE':'FALSE'}" EnforceUniqueValues="${unique?'TRUE':'FALSE'}"${type==='Note'?' RichText="FALSE" AppendOnly="FALSE"':''}></Field>`;
   await journal({phase:'field-intent',name});await client.call('POST',route+'/fields/createfieldasxml',{parameters:{SchemaXml:xml,Options:8}});
  } else if(match[0].TypeAsString!==type||match[0].Required!==required)throw Error('PRESERVE_EXISTING_SCHEMA_DRIFT');
 }
 const verified=await client.all(route+'/fields?$select=InternalName,TypeAsString,Required,Indexed,EnforceUniqueValues');
 for(const name of fields.filter(n=>n!=='Title')){const f=verified.find(f=>f.InternalName===name);if(!f||f.TypeAsString!==(['RecordJSON','OfficialURL','EvidenceURL','RelatedRecordsURL'].includes(name)?'Note':'Text')||(name==='RecordKey'&&(!f.Indexed||!f.EnforceUniqueValues)))throw Error('SCHEMA_READBACK_MISMATCH');}
 await journal({phase:'schema-verified',listId:list.Id});return {listId:list.Id,route};
}

export async function provisionViews(client,listId,journal) {
 const route="lists(guid'"+listId+"')",result=[];
 const viewFields=['LinkTitle','RecordKind','Issuer','SourceStatus','SourceRole','ReviewState','OfficialURL','EvidenceURL','RelatedRecordsURL','PublicationKey','EditionKey'];
 const desired=[['Publication catalogue','Publication'],['Exact editions','Edition'],['Retained source captures','Capture'],['Reference occurrences','Reference'],['Source inventory and gaps','Collection']];
 const before=await client.all(route+'/views?$select=Id,Title,ViewQuery');
 for(const [title,kind] of desired){
  // Use the exact native empty-element spelling observed on readback.
  const query=`<Where><Eq><FieldRef Name="RecordKind" /><Value Type="Text">${kind}</Value></Eq></Where><OrderBy><FieldRef Name="Title" /></OrderBy>`;
  const matches=before.filter(v=>v.Title===title);if(matches.length>1)throw Error('AMBIGUOUS_NATIVE_VIEW');
  if(matches.length&&matches[0].ViewQuery!==query)throw Error('PRESERVE_CHANGED_VIEW');
  if(!matches.length){await journal({phase:'view-intent',title});await client.call('POST',route+'/views/add',{parameters:{Title:title,ViewFields:viewFields,Query:query,PersonalView:false,SetAsDefaultView:false,Paged:true,RowLimit:100}});}
  const checks=(await client.all(route+'/views?$select=Id,Title,ViewQuery,ServerRelativeUrl,RowLimit,Paged,DefaultView,PersonalView')).filter(v=>v.Title===title);
  if(checks.length!==1||checks[0].ViewQuery!==query||checks[0].RowLimit!==100||checks[0].Paged!==true||checks[0].DefaultView!==false||checks[0].PersonalView!==false)throw Error('VIEW_READBACK_MISMATCH');
  const actualFields=await client.call('GET',route+"/views(guid'"+checks[0].Id+"')/ViewFields");
  if(JSON.stringify(actualFields.Items)!==JSON.stringify(viewFields))throw Error('VIEW_FIELD_READBACK_MISMATCH');
  result.push(checks[0]);await journal({phase:'view-verified',title,id:checks[0].Id});
 }
 return result;
}

export async function configureLinks(client,listId,journal) {
 const route="lists(guid'"+listId+"')";
 for(const [name,label] of [['OfficialURL','Official source'],['EvidenceURL','Retained original'],['RelatedRecordsURL','Related records']]) {
  const path=route+"/fields/getbyinternalnameortitle('"+name+"')";
  const legacy=JSON.stringify({elmType:'div',children:[{elmType:'a',attributes:{href:'@currentField',target:'_blank',rel:'noopener noreferrer'},style:{display:"=if(@currentField == '', 'none', 'inline')"},txtContent:label},{elmType:'span',style:{display:"=if(@currentField == '', 'inline', 'none')"},txtContent:'None recorded'}]});
  const formatter=name==='EvidenceURL'?JSON.stringify({elmType:'div',children:[{elmType:'a',attributes:{href:"=if(@currentField == '', [$RelatedRecordsURL], @currentField)",target:'_blank',rel:'noopener noreferrer'},style:{display:"=if(@currentField == '' && [$RelatedRecordsURL] == '', 'none', 'inline')"},txtContent:"=if(@currentField == '', 'Related evidence', 'Retained original')"},{elmType:'span',style:{display:"=if(@currentField == '' && [$RelatedRecordsURL] == '', 'inline', 'none')"},txtContent:'No capture linked on this row'}]}):legacy;
  const before=await client.call('GET',path+'?$select=CustomFormatter');
  if(before.CustomFormatter&&![legacy,formatter].includes(before.CustomFormatter))throw Error('PRESERVE_CHANGED_COLUMN_FORMATTER');
  if(before.CustomFormatter!==formatter){await journal({phase:'formatter-intent',name});await client.call('PATCH',path,{CustomFormatter:formatter});}
  const after=await client.call('GET',path+'?$select=CustomFormatter');if(after.CustomFormatter!==formatter)throw Error('FORMATTER_READBACK_MISMATCH');
  await journal({phase:'formatter-verified',name});
 }
 const all=(await client.all(route+'/views?$select=Id,Title')).filter(v=>v.Title==='All Items');
 if(all.length!==1)throw Error('DEFAULT_VIEW_BINDING_DRIFT');
 const path=route+"/views(guid'"+all[0].Id+"')/ViewFields",before=await client.call('GET',path);
 const desired=['LinkTitle','RecordKind','Issuer','SourceStatus','SourceRole','ReviewState','OfficialURL','EvidenceURL','RelatedRecordsURL','PublicationKey','EditionKey'];
 if(JSON.stringify(before.Items)!==JSON.stringify(desired)){
  if(JSON.stringify(before.Items)!==JSON.stringify(['LinkTitle']))throw Error('PRESERVE_CHANGED_DEFAULT_VIEW_FIELDS');
  for(const name of desired.slice(1)){await journal({phase:'default-field-intent',name});await client.call('POST',path+"/AddViewField('"+name+"')");}
 }
 const actual=await client.call('GET',path);if(JSON.stringify(actual.Items)!==JSON.stringify(desired))throw Error('DEFAULT_VIEW_READBACK_MISMATCH');
 return {linkColumnsVerified:3,defaultFieldsVerified:desired.length};
}

async function main() {
 const [mode,configPath,inputPath,outputPath,journalPath]=process.argv.slice(2);
 if(!['bootstrap','persist','export','views','plan','configure'].includes(mode)||!outputPath||!journalPath)throw Error('Usage: MODE PRIVATE_CONFIG INPUT NEW_OUTPUT NEW_JOURNAL');
 if(fs.existsSync(outputPath))throw Error('NEW_OUTPUT_REQUIRED');
 const fd=fs.openSync(journalPath,'wx',0o600);
 const journal=async event=>{fs.writeSync(fd,JSON.stringify({at:new Date().toISOString(),...event})+'\n');fs.fsyncSync(fd);};
 try {
  const config=JSON.parse(fs.readFileSync(configPath)),client=await connect(config);
  if(mode==='bootstrap') {const binding=await bootstrap(client,journal,config.listTitle);fs.writeFileSync(outputPath,JSON.stringify(binding,null,2),{flag:'wx',mode:0o600});return;}
  if(!/^[a-f0-9-]{36}$/i.test(config.listId))throw Error('EXACT_LIST_BINDING_REQUIRED');
  const identity=await client.call('GET',"lists(guid'"+config.listId+"')?$select=Id,Title,EnableVersioning");
  if(identity.Title!==(config.listTitle||'PPG External Publications')||identity.EnableVersioning!==true)throw Error('NATIVE_CATALOGUE_IDENTITY_DRIFT');
  if(mode==='views'){const result=await provisionViews(client,config.listId,journal);fs.writeFileSync(outputPath,JSON.stringify(result,null,2),{flag:'wx',mode:0o600});return;}
  if(mode==='configure'){const result=await configureLinks(client,config.listId,journal);fs.writeFileSync(outputPath,JSON.stringify(result,null,2),{flag:'wx',mode:0o600});return;}
  const route="lists(guid'"+config.listId+"')";
  const read=()=>client.all(route+'/items?$select=Id,'+fields.join(',')+'&$top=500');
  const rows=mode==='export'?null:JSON.parse(fs.readFileSync(inputPath));
  const result=mode==='export'?await read():mode==='plan'?difference(rows,await read(),config.siteUrl):await persist({rows,read,site:config.siteUrl,
    readOne:key=>client.all(route+'/items?$select=Id,'+fields.join(',')+'&$filter='+encodeURIComponent("RecordKey eq '"+key.replaceAll("'","''")+"'")+'&$top=2'),
    create:row=>client.call('POST',route+'/items',row),journal});
  fs.writeFileSync(outputPath,JSON.stringify(result,null,2),{flag:'wx',mode:0o600});
 } catch(error) {await journal({phase:'failed-or-uncertain',status:error.response?.status??null,message:error.message,response:error.response?.data??null});throw error;
 } finally {fs.closeSync(fd);}
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(e=>{console.error(e.code||e.message);process.exitCode=1;});
