/* Same-site authenticated browser only. Additive consultation/handoff storage, no case writes. */
async function provisionConsultation({base, config}) {
  const headers={Accept:'application/json;odata=nometadata'};
  const get=async p=>{const r=await fetch(base+p,{headers});if(!r.ok)throw Error('Read '+r.status+' '+p);return r.json();};
  const dr=await fetch(base+'/_api/contextinfo',{method:'POST',headers});if(!dr.ok)throw Error('Digest '+dr.status);
  const digest=(await dr.json()).FormDigestValue;
  const write=async(p,body,merge=false)=>{const r=await fetch(base+p,{method:'POST',headers:{...headers,'Content-Type':'application/json;odata=nometadata','X-RequestDigest':digest,...(merge?{'X-HTTP-Method':'MERGE','IF-MATCH':'*'}:{})},body:JSON.stringify(body)});if(!r.ok)throw Error('Write '+r.status+' '+await r.text());return r.status===204?null:r.json();};
  const matches=(await get('/_api/web/lists?$select=Id,Title&$filter='+encodeURIComponent("Title eq '"+config.listTitle+"'"))).value;
  if(matches.length>1)throw Error('Duplicate consultation lists');
  const list=matches[0]||await write('/_api/web/lists',{Title:config.listTitle,Description:config.description,BaseTemplate:100});
  const lp="/_api/web/lists(guid'"+list.Id+"')";
  const before=await get(lp+'?$select=HasUniqueRoleAssignments');if(before.HasUniqueRoleAssignments)throw Error('Unexpected permission boundary; no access change attempted');
  const fields=(await get(lp+'/fields?$select=InternalName,TypeAsString,Required,SchemaXml')).value;
  const escape=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
  const added=[];
  for(const f of config.fields){
    const existing=fields.find(x=>x.InternalName===f.name);
    if(existing){
      if(existing.TypeAsString!==f.type||existing.Required!==f.required)throw Error('Field drift '+f.name);
      if(config.choices[f.name]){const xml=new DOMParser().parseFromString(existing.SchemaXml,'text/xml');if(JSON.stringify([...xml.querySelectorAll('CHOICE')].map(x=>x.textContent))!==JSON.stringify(config.choices[f.name]))throw Error('Choice drift '+f.name);}
      continue;
    }
    const xml='<Field Name="'+f.name+'" StaticName="'+f.name+'" DisplayName="'+f.name+'" Type="'+f.type+'" Required="'+(f.required?'TRUE':'FALSE')+'"'+(f.type==='Note'?' RichText="FALSE" NumLines="4"':'')+(f.type==='DateTime'?' Format="DateOnly"':'')+'>'+(config.choices[f.name]?'<CHOICES>'+config.choices[f.name].map(c=>'<CHOICE>'+escape(c)+'</CHOICE>').join('')+'</CHOICES>':'')+(config.defaults[f.name]?'<Default>'+escape(config.defaults[f.name])+'</Default>':'')+'</Field>';
    await write(lp+'/fields/createfieldasxml',{parameters:{SchemaXml:xml,Options:0}});added.push(f.name);
  }
  await write(lp+"/fields/getbyinternalnameortitle('EventUID')",{Indexed:true,EnforceUniqueValues:true},true);
  await write(lp+"/fields/getbyinternalnameortitle('DocumentSHA256')",{ValidationFormula:'=LEN([DocumentSHA256])=64',ValidationMessage:'Record the 64-character hash of the exact document version.'},true);
  await write(lp+"/fields/getbyinternalnameortitle('Title')",{Required:false},true);
  await write(lp,{EnableVersioning:true,ValidationFormula:config.validationFormula,ValidationMessage:config.validationMessage},true);
  const views=(await get(lp+'/views?$select=Id,Title,ViewQuery')).value;
  const result=[];
  for(const view of config.views){
    const existing=views.filter(v=>v.Title===view.title);if(existing.length>1)throw Error('Duplicate view '+view.title);
    let v=existing[0];
    if(v&&v.ViewQuery.replace(/\s+\/>/g,'/>')!==view.query)throw Error('View drift '+view.title);
    if(!v)v=await write(lp+'/views',{Title:view.title,ViewQuery:view.query,RowLimit:50,PersonalView:false});
    const vp=lp+"/views(guid'"+v.Id+"')";
    const current=(await get(vp+'/ViewFields')).Items;
    for(const name of config.viewFields)if(!current.includes(name))await write(vp+'/ViewFields/addviewfield',{strField:name});
    if(view.title==='All consultation and handoff events')await write(vp,{DefaultView:true},true);
    result.push({title:view.title,id:v.Id,adopted:!!existing.length});
  }
  return {created:!matches.length,added,list:await get(lp+'?$select=Id,Title,EnableVersioning,HasUniqueRoleAssignments,ValidationFormula,DefaultViewUrl,ItemCount'),fields:(await get(lp+'/fields?$select=InternalName,TypeAsString,Required,EnforceUniqueValues')).value.filter(x=>config.fields.some(f=>f.name===x.InternalName)),views:(await get(lp+'/views?$select=Id,Title,ViewQuery,ServerRelativeUrl')).value,adoption:result};
}
