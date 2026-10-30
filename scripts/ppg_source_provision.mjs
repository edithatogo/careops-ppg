/* Provision versioned source destination schemas using an existing qualified adapter.
 * Adapter owns authentication, effect checks, exclusive send journals and target scope.
 * No records, permissions, subscriptions, flows or source libraries are modified.
 */
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
const hash=v=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
const quote=s=>s.replaceAll("'","''");
const xml=s=>s.replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;');
export async function provision(client, schemas, {apply=false}={}) {
 const result={lists:{},created:0,fieldsCreated:0,verified:!apply};
 if(!schemas||typeof schemas!=='object'||!Object.keys(schemas).length)throw Error('SCHEMAS_REQUIRED');
 for(const [key,s] of Object.entries(schemas)) {
  if(!/^[a-z][a-z0-9-]*$/.test(key)||typeof s.title!=='string'||!s.title.startsWith('PPG ')||s.baseTemplate!==100||s.enableVersioning!==true||s.enableAttachments!==false||!Array.isArray(s.fields))throw Error('SCHEMA_CONTRACT');
  const names=new Set();
  for(const f of s.fields){if(!/^[A-Za-z][A-Za-z0-9_]*$/.test(f.name)||names.has(f.name)||!['Text','Note','DateTime','Number','Boolean'].includes(f.type)||f.unique&&!f.indexed)throw Error('FIELD_CONTRACT');names.add(f.name);}
  let rows=await client.all('lists?$filter='+encodeURIComponent("Title eq '"+quote(s.title)+"'"));
  if(!rows.length){
   if(!apply)throw Error('MISSING_LIST_'+key);
   await client.authorizeSchema({title:s.title,operation:'create-list',baseTemplate:100});
   const payload={Title:s.title,BaseTemplate:100,EnableVersioning:true,EnableAttachments:false};
   await client.send({key:'install-'+key+'-list',route:'lists',payload,payloadSHA256:hash(payload)});
   rows=await client.all('lists?$filter='+encodeURIComponent("Title eq '"+quote(s.title)+"'"));result.created++;
  }
  if(rows.length!==1||rows[0].BaseTemplate!==100||rows[0].EnableVersioning!==true||rows[0].EnableAttachments!==false||!/^[a-f0-9-]{36}$/i.test(rows[0].Id))throw Error('INCOMPATIBLE_LIST_'+key);
  const id=rows[0].Id,base="lists(guid'"+id+"')";
  let fields=await client.all(base+'/fields');
  for(const f of s.fields){
   let a=fields.filter(x=>x.InternalName===f.name);
   if(!a.length){
    if(!apply)throw Error('MISSING_FIELD_'+key+'_'+f.name);
    await client.authorizeSchema({title:s.title,listId:id,operation:'create-field',baseTemplate:100});
    const attrs={Type:f.type,Name:f.name,StaticName:f.name,DisplayName:f.name,Required:'FALSE',
      ...(f.indexed?{Indexed:'TRUE'}:{}),...(f.unique?{EnforceUniqueValues:'TRUE'}:{}),
      ...(f.type==='Note'?{RichText:'FALSE',AppendOnly:'FALSE'}:{})};
    const payload={parameters:{SchemaXml:'<Field '+Object.entries(attrs).map(([k,v])=>k+'="'+xml(v)+'"').join(' ')+' />',Options:8}};
    await client.send({key:'install-'+key+'-field-'+f.name.toLowerCase(),route:base+'/fields/CreateFieldAsXml',payload,payloadSHA256:hash(payload)});
    fields=await client.all(base+'/fields');a=fields.filter(x=>x.InternalName===f.name);result.fieldsCreated++;
   }
   if(a.length!==1||a[0].TypeAsString!==f.type||f.indexed&&a[0].Indexed!==true||f.unique&&a[0].EnforceUniqueValues!==true)throw Error('INCOMPATIBLE_FIELD_'+key+'_'+f.name);
  }
  result.lists[key]=id;
 }
 result.verified=true;return result;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){
 const args=process.argv.slice(2),apply=args.includes('--apply');
 const option=name=>args[args.indexOf(name)+1];
 if(!args.includes('--adapter')||!args.includes('--schemas')||!args.includes('--receipt'))throw Error('--adapter --schemas --receipt required; --apply creates missing schema only');
 const adapter=path.resolve(option('--adapter')),receipt=path.resolve(option('--receipt'));
 if(!adapter.split(path.sep).includes('.local')||!receipt.split(path.sep).includes('.local')||fs.existsSync(receipt))throw Error('NEW_PRIVATE_RECEIPT_AND_QUALIFIED_ADAPTER_REQUIRED');
 const c=await(await import(pathToFileURL(adapter))).connect();
 const r=await provision(c,JSON.parse(fs.readFileSync(option('--schemas'))),{apply});
 fs.writeFileSync(receipt,JSON.stringify(r,null,2)+'\n',{flag:'wx',mode:0o600});
 console.log(JSON.stringify({lists:Object.keys(r.lists).length,created:r.created,fieldsCreated:r.fieldsCreated,verified:r.verified}));
}
