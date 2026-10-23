/* Run in the authenticated existing SharePoint page; no credentials or settings changes. */
async function ensureArchiveCaptureFields(base, libraryId, config) {
  if (!base.startsWith('/') || !/^[-a-f0-9]{36}$/i.test(libraryId) || config.schemaVersion !== 1) throw Error('Invalid binding');
  const lp = base+"/_api/web/lists(guid'"+libraryId+"')";
  const headers = {Accept:'application/json;odata=nometadata'};
  const get = async url => {const r=await fetch(url,{headers});if(!r.ok)throw Error('GET '+r.status);return r.json()};
  const settings = await get(lp+'?$select=EnableVersioning,MajorVersionLimit,EnableModeration,ForceCheckout,HasUniqueRoleAssignments');
  if(!settings.EnableVersioning)throw Error('Versioning unavailable');
  const before=await get(lp+'/fields?$select=InternalName,Title,TypeAsString,Required,SchemaXml,Description');
  const cx=await fetch(base+'/_api/contextinfo',{method:'POST',headers});if(!cx.ok)throw Error('Context '+cx.status);
  const digest=(await cx.json()).FormDigestValue;
  const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;');
  const receipt={created:[],adopted:[],settings};
  for(const f of config.fields){
    let field=before.value.find(x=>x.InternalName===f.name);
    if(!field){
      const choices=f.choices?'<CHOICES>'+f.choices.map(c=>'<CHOICE>'+esc(c)+'</CHOICE>').join('')+'</CHOICES>':'';
      const xml='<Field Name="'+esc(f.name)+'" StaticName="'+esc(f.name)+'" DisplayName="'+esc(f.title)+'" Type="'+esc(f.type)+'" Required="FALSE" Description="'+esc(f.description)+'"'+(f.type==='Note'?' RichText="FALSE" NumLines="6"':'')+'>'+choices+'</Field>';
      const r=await fetch(lp+'/fields/createfieldasxml',{method:'POST',headers:{...headers,'Content-Type':'application/json;odata=nometadata','X-RequestDigest':digest},body:JSON.stringify({parameters:{SchemaXml:xml,Options:8}})});
      if(!r.ok)throw Error('Create field '+f.name+' '+r.status+' '+await r.text());
      receipt.created.push(f.name);
    }else receipt.adopted.push(f.name);
    field=await get(lp+"/fields/getbyinternalnameortitle('"+f.name+"')?$select=InternalName,Title,TypeAsString,Required,SchemaXml,Description");
    if(field.InternalName!==f.name||field.Title!==f.title||field.TypeAsString!==f.type||field.Required||field.Description!==f.description)throw Error('Field readback drift '+f.name);
    if(f.choices){const actual=[...new DOMParser().parseFromString(field.SchemaXml,'text/xml').querySelectorAll('CHOICE')].map(x=>x.textContent);if(JSON.stringify(actual)!==JSON.stringify(f.choices))throw Error('Choice drift')}
  }
  const after=await get(lp+'?$select=EnableVersioning,MajorVersionLimit,EnableModeration,ForceCheckout,HasUniqueRoleAssignments');
  if(JSON.stringify(after)!==JSON.stringify(settings))throw Error('Settings drift');
  return receipt;
}
