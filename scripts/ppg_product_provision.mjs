/* Whole-product schema installation through a qualified, private CLI adapter. */
import fs from 'node:fs';
import {sameViewQuery} from './ppg_source_provision.mjs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const hash=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
const quote=x=>x.replaceAll("'","''");
export async function installProductViews(client,contract,objects,{apply=false}={}) {
 let created=0;
 for(const s of contract.objects){const t=objects[s.key],base="lists(guid'"+t.id+"')",fields=[s.baseTemplate===101?'FileLeafRef':'Title',...s.fields.map(f=>f.name).filter(n=>n!=='Title'&&!n.startsWith('_')).slice(0,7)];
  const query=(s.key==='hospital-busyness-trends'?'<Where><Eq><FieldRef Name="DayOfWeekNo"/><Value Type="Number">1</Value></Eq></Where>':'')+'<OrderBy><FieldRef Name="ID" Ascending="FALSE"/></OrderBy>';
  let views=(await client.all(base+'/views')).filter(v=>v.Title==='PPG workbench');
  if(!views.length){if(!apply)throw Error('MISSING_PRODUCT_VIEW_'+s.key);await client.authorizeSchema({title:t.title,listId:t.id,baseTemplate:s.baseTemplate});const payload={parameters:{Title:'PPG workbench',ViewFields:fields,Query:query,PersonalView:false,SetAsDefaultView:true,Paged:true,RowLimit:100}};await client.send({key:'product-view-'+s.key,route:base+'/views/add',payload,payloadSHA256:hash(payload)});created++;views=(await client.all(base+'/views')).filter(v=>v.Title==='PPG workbench');}
  if(views.length!==1||!sameViewQuery(views[0].ViewQuery,query)||views[0].RowLimit!==100||!views[0].Paged)throw Error('PRODUCT_VIEW_DRIFT_'+s.key);
  if(JSON.stringify((await client.get(base+"/views(guid'"+views[0].Id+"')/ViewFields")).Items)!==JSON.stringify(fields))throw Error('PRODUCT_VIEW_FIELDS_'+s.key);
 }
 return{views:contract.objects.length,created};
}
export async function provisionProduct(client, contract, suffix, {apply=false, progress=()=>{}}={}) {
 if(contract.schemaVersion!==1||!Array.isArray(contract.objects)||!/^[A-Za-z0-9][A-Za-z0-9 -]{0,45}$/.test(suffix))throw Error('EXPLICIT_ISOLATED_CONTRACT_REQUIRED');
 const keys=new Set(),titles=new Set();
 for(const s of contract.objects){if(!/^[a-z0-9-]+$/.test(s.key)||keys.has(s.key)||titles.has(s.title)||!s.title.startsWith('PPG ')||![100,101].includes(s.baseTemplate))throw Error('OBJECT_CONTRACT');keys.add(s.key);titles.add(s.title);}
 const result={schemaVersion:1,version:contract.version,objects:{},created:0,fieldsCreated:0};
 const send=async(key,route,payload,merge=false)=>client.send({key,route,payload,payloadSHA256:hash(payload),merge});
 for(const s of contract.objects){
  const title=s.title+' - '+suffix;
  let found=await client.all('lists?$select=Id,Title,BaseTemplate,EnableVersioning,EnableAttachments,RootFolder/ServerRelativeUrl&$expand=RootFolder&$filter='+encodeURIComponent("Title eq '"+quote(title)+"'"));
  if(!found.length){if(!apply)throw Error('MISSING_OBJECT_'+s.key);await client.authorizeSchema({title,baseTemplate:s.baseTemplate});await send('product-'+s.key+'-list','lists',{Title:title,BaseTemplate:s.baseTemplate,EnableVersioning:true,EnableAttachments:s.enableAttachments});found=await client.all('lists?$select=Id,Title,BaseTemplate,EnableVersioning,EnableAttachments,RootFolder/ServerRelativeUrl&$expand=RootFolder&$filter='+encodeURIComponent("Title eq '"+quote(title)+"'"));result.created++;}
  if(found.length!==1||found[0].BaseTemplate!==s.baseTemplate||!found[0].EnableVersioning||found[0].EnableAttachments!==s.enableAttachments)throw Error('OBJECT_DRIFT_'+s.key);
  result.objects[s.key]={id:found[0].Id,path:found[0].RootFolder.ServerRelativeUrl,title};progress({phase:'objects',key:s.key});
 }
 // Create scalar fields before lookups, including references to later objects.
 for(const lookup of [false,true])for(const s of contract.objects){
  const target=result.objects[s.key],base="lists(guid'"+target.id+"')";
  await client.authorizeSchema({title:target.title,listId:target.id,baseTemplate:s.baseTemplate});
  let fields=await client.all(base+'/fields?$select=InternalName,TypeAsString,Required,Indexed,EnforceUniqueValues,SchemaXml');
  for(const f of s.fields.filter(f=>Boolean(f.lookup)===lookup)){
   if(!/^[A-Za-z_][A-Za-z0-9_]*$/.test(f.name)||!f.xml.startsWith('<Field ')||f.lookup&&!keys.has(f.lookup))throw Error('FIELD_CONTRACT');
   let existing=fields.find(x=>x.InternalName===f.name);
   const xml=f.lookup?f.xml.replace('__LIST_'+f.lookup+'__','{'+result.objects[f.lookup].id+'}'):f.xml;
   if(!existing){if(!apply)throw Error('MISSING_FIELD_'+s.key+'_'+f.name);await send('product-'+s.key+'-'+f.name.toLowerCase().replaceAll('_','-'),base+'/fields/CreateFieldAsXml',{parameters:{SchemaXml:xml,Options:8}});result.fieldsCreated++;}
   else if(existing.TypeAsString!==f.type||existing.Required!==f.required||f.indexed&&!existing.Indexed||f.unique&&!existing.EnforceUniqueValues)throw Error('FIELD_DRIFT_'+s.key+'_'+f.name);
  }
  fields=await client.all(base+'/fields?$select=InternalName,TypeAsString,Required,Indexed,EnforceUniqueValues,SchemaXml');
  for(const f of s.fields.filter(f=>Boolean(f.lookup)===lookup)){const a=fields.find(x=>x.InternalName===f.name);if(!a||a.TypeAsString!==f.type||a.Required!==f.required||f.indexed&&!a.Indexed||f.unique&&!a.EnforceUniqueValues||f.lookup&&!a.SchemaXml.toLowerCase().includes(result.objects[f.lookup].id.toLowerCase()))throw Error('FIELD_READBACK_'+s.key+'_'+f.name);}
  if(!lookup){const t=fields.find(f=>f.InternalName==='Title');if(t.Required!==s.titleRequired){if(!apply)throw Error('TITLE_DRIFT_'+s.key);await send('product-'+s.key+'-title',base+"/fields/getbyinternalnameortitle('Title')",{Required:s.titleRequired},true);}}
  else {const l=await client.get(base+'?$select=ValidationFormula,ValidationMessage');if((l.ValidationFormula??'')!==(s.validationFormula??'')||(l.ValidationMessage??'')!==(s.validationMessage??'')){if(!apply||l.ValidationFormula)throw Error('VALIDATION_DRIFT_'+s.key);await send('product-'+s.key+'-validation',base,{ValidationFormula:s.validationFormula??'',ValidationMessage:s.validationMessage??''},true);}}
  progress({phase:lookup?'lookups':'fields',key:s.key,fieldsCreated:result.fieldsCreated});
 }
 result.views=await installProductViews(client,contract,result.objects,{apply});
 return result;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){
 const a=process.argv.slice(2),arg=k=>a[a.indexOf(k)+1];for(const k of ['--adapter','--contract','--suffix','--receipt'])if(!a.includes(k))throw Error('Missing '+k);
 const receipt=path.resolve(arg('--receipt')),adapter=path.resolve(arg('--adapter'));if(!receipt.split(path.sep).includes('.local')||!adapter.split(path.sep).includes('.local')||fs.existsSync(receipt))throw Error('NEW_PRIVATE_RECEIPT_REQUIRED');
 const c=await(await import(pathToFileURL(adapter))).connect();const r=await provisionProduct(c,JSON.parse(fs.readFileSync(arg('--contract'))),arg('--suffix'),{apply:a.includes('--apply'),progress:x=>console.log(JSON.stringify(x))});fs.writeFileSync(receipt,JSON.stringify(r,null,2),{flag:'wx',mode:0o600});console.log(JSON.stringify({objects:Object.keys(r.objects).length,created:r.created,fieldsCreated:r.fieldsCreated}));
}
