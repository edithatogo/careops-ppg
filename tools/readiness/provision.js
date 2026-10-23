/* Run inside an already qualified same-site browser context. No credentials. */
async function provisionReadiness({base, config}) {
  const headers={Accept:'application/json;odata=nometadata'};
  const get=async path=>{const r=await fetch(base+path,{headers});if(!r.ok)throw Error('Read '+r.status+' '+path);return r.json();};
  const digest=(await getDigest()).FormDigestValue;
  async function getDigest(){const r=await fetch(base+'/_api/contextinfo',{method:'POST',headers});if(!r.ok)throw Error('Digest '+r.status);return r.json();}
  const write=async(path,body,method='POST')=>{const r=await fetch(base+path,{method:'POST',headers:{...headers,'Content-Type':'application/json;odata=nometadata','X-RequestDigest':digest,...(method==='MERGE'?{'X-HTTP-Method':'MERGE','IF-MATCH':'*'}:{})},body:JSON.stringify(body)});if(!r.ok)throw Error('Write '+r.status+' '+await r.text());return r.status===204?null:r.json();};
  const matches=(await get('/_api/web/lists?$select=Id,Title&$filter='+encodeURIComponent("Title eq '"+config.listTitle+"'"))).value;
  if(matches.length>1)throw Error('Duplicate readiness lists');
  const created=!matches.length;
  const list=matches[0]||await write('/_api/web/lists',{Title:config.listTitle,Description:config.description,BaseTemplate:100});
  const path="/_api/web/lists(guid'"+list.Id+"')";
  const existing=(await get(path+'/fields?$select=InternalName,TypeAsString,Required,EnforceUniqueValues')).value;
  const xmlEscape=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
  const added=[];
  for(const f of config.fields){
    const found=existing.find(x=>x.InternalName===f.name);
    if(found){if(found.TypeAsString!==f.type||found.Required!==f.required)throw Error('Field drift '+f.name);continue;}
    const choices=config.choices[f.name];
    const xml='<Field Name="'+f.name+'" StaticName="'+f.name+'" DisplayName="'+f.name+'" Type="'+f.type+'" Required="'+(f.required?'TRUE':'FALSE')+'"'+(f.type==='Note'?' RichText="FALSE" NumLines="6"':'')+(f.type==='DateTime'?' Format="DateOnly"':'')+'>'+(choices?'<CHOICES>'+choices.map(x=>'<CHOICE>'+xmlEscape(x)+'</CHOICE>').join('')+'</CHOICES>':'')+(config.defaults[f.name]?'<Default>'+config.defaults[f.name]+'</Default>':'')+'</Field>';
    await write(path+'/fields/createfieldasxml',{parameters:{SchemaXml:xml,Options:0}});added.push(f.name);
  }
  await write(path+"/fields/getbyinternalnameortitle('EventUID')",{Indexed:true,EnforceUniqueValues:true},'MERGE');
  // Native validation supports length; exact bytes/hash correspondence is human evidence.
  const hexFormula='=LEN([DocumentSHA256])=64';
  await write(path+"/fields/getbyinternalnameortitle('DocumentSHA256')",{ValidationFormula:hexFormula,ValidationMessage:'Paste the exact 64-character SHA-256 of the reviewed document.'},'MERGE');
  const formula='=OR([Finding]="Not assessed",AND(NOT(ISBLANK([AssessorName])),NOT(ISBLANK([AssessedOn])),NOT(ISBLANK([FindingSummary])),NOT(ISBLANK([EvidenceReference]))))';
  await write(path,{EnableVersioning:true,ValidationFormula:formula,ValidationMessage:'A human finding needs assessor, date, summary and evidence. Not assessed remains valid pending work.'},'MERGE');
  const titleField=existing.find(x=>x.InternalName==='Title');if(titleField.Required)await write(path+"/fields/getbyinternalnameortitle('Title')",{Required:false},'MERGE');
  const views=[['All readiness events',null],['Needs assessment','<Eq><FieldRef Name="Finding"/><Value Type="Choice">Not assessed</Value></Eq>'],['Open conditions','<Eq><FieldRef Name="ConditionsState"/><Value Type="Choice">Open</Value></Eq>'],['Ready findings - version specific','<Eq><FieldRef Name="Finding"/><Value Type="Choice">Ready for decision</Value></Eq>']];
  const current=(await get(path+'/views?$select=Id,Title,ViewQuery')).value;
  for(const [title,where] of views){
    const query=(where?'<Where>'+where+'</Where>':'')+'<OrderBy><FieldRef Name="Created" Ascending="FALSE"/></OrderBy>';
    let v=current.find(x=>x.Title===title);
    if(v){if(v.ViewQuery.replace(/\s+\/>/g,'/>')!==query)throw Error('View drift '+title);}
    else v=await write(path+'/views',{Title:title,ViewQuery:query,RowLimit:50,PersonalView:false});
    const vp=path+"/views(guid'"+v.Id+"')";
    const fields=(await get(vp+'/ViewFields')).Items;
    for(const field of ['LinkTitle','EventUID','CaseUID','DocumentReference','ReviewedVersionRef','Finding','AssessorName','AssessedOn','ConditionsState','EvidenceReference'])
      if(!fields.includes(field))await write(vp+'/ViewFields/addviewfield',{strField:field});
    if(!where)await write(vp,{DefaultView:true},'MERGE');
  }
  return {created,added,list:await get(path+'?$select=Id,Title,EnableVersioning,HasUniqueRoleAssignments,ValidationFormula,DefaultViewUrl,ItemCount'),fields:(await get(path+'/fields?$select=InternalName,TypeAsString,Required,EnforceUniqueValues')).value.filter(x=>config.fields.some(f=>f.name===x.InternalName)),views:(await get(path+'/views?$select=Id,Title,ViewQuery,ServerRelativeUrl')).value};
}
