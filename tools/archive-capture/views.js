async function ensureArchiveCaptureViews(base,libraryId,config){
 const lp=base+"/_api/web/lists(guid'"+libraryId+"')",headers={Accept:'application/json;odata=nometadata'};
 const get=async url=>{const r=await fetch(url,{headers});if(!r.ok)throw Error('GET '+r.status);return r.json()};
 const c=await fetch(base+'/_api/contextinfo',{method:'POST',headers});if(!c.ok)throw Error('Context');const digest=(await c.json()).FormDigestValue;
 const post=async(url,data,merge=false)=>{const r=await fetch(url,{method:'POST',headers:{...headers,'Content-Type':'application/json;odata=nometadata','X-RequestDigest':digest,...(merge?{'X-HTTP-Method':'MERGE','IF-MATCH':'*'}:{})},body:JSON.stringify(data)});if(!r.ok)throw Error('Save view '+r.status+' '+await r.text());const t=await r.text();return t?JSON.parse(t):null};
 const before=(await get(lp+'/views?$select=Id,Title,ViewQuery,Scope,DefaultView')).value,receipts=[];
 for(const def of config.views){
  const query='<Where><And><IsNotNull><FieldRef Name="PPGCaptureSHA256"/></IsNotNull><And><BeginsWith><FieldRef Name="FileDirRef"/><Value Type="Text">'+base+'/PPG Review Evidence/Captured Policy Archive</Value></BeginsWith><Eq><FieldRef Name="FSObjType"/><Value Type="Integer">0</Value></Eq></And></And></Where>'+(def.groupBy?'<GroupBy Collapse="TRUE"><FieldRef Name="'+def.groupBy+'"/></GroupBy>':'')+'<OrderBy><FieldRef Name="FileLeafRef"/></OrderBy>';
  const matches=before.filter(v=>v.Title===def.title);if(matches.length>1)throw Error('Duplicate view');let v=matches[0];
  if(!v){v=await post(lp+'/views/add',{parameters:{Title:def.title,ViewFields:config.viewFields,Query:query,PersonalView:false,SetAsDefaultView:false,Paged:true,RowLimit:100}});await post(lp+"/views(guid'"+v.Id+"')",{Scope:1},true)}
  const actual=await get(lp+"/views(guid'"+v.Id+"')?$select=Id,Title,ViewQuery,Scope,DefaultView,ServerRelativeUrl");
  const fields=(await get(lp+"/views(guid'"+v.Id+"')/ViewFields")).Items;
  const normal=s=>s.replaceAll("'",'"').replace(/\s+\/>/g,'/>');
  if(normal(actual.ViewQuery)!==normal(query)||actual.Scope!==1||actual.DefaultView||JSON.stringify(fields)!==JSON.stringify(config.viewFields))throw Error('Native view drift '+def.title);
  receipts.push(actual);
 }
 const after=(await get(lp+'/views?$select=Id,Title,ViewQuery,Scope,DefaultView')).value;
 for(const v of before)if(!config.views.some(d=>d.title===v.Title)&&JSON.stringify(after.find(x=>x.Id===v.Id))!==JSON.stringify(v))throw Error('Unrelated view changed');
 return {views:receipts,otherViewsPreserved:before.filter(v=>!config.views.some(d=>d.title===v.Title)).length};
}
