/* Same-site PPG projection reads and additive non-default views; no item writes. */
async function captureProcessInputs({base, lists, sourceContext}) {
  const headers={Accept:'application/json;odata=nometadata'};
  const get=async url=>{const r=await fetch(url,{headers,cache:'no-store'});if(!r.ok)throw Error('Read '+r.status+' '+url);return r.json();};
  const sources={};
  const before={};
  const metadata=lp=>get(base+lp+'?$select=Id,ItemCount,LastItemModifiedDate');
  const readItems=async lp=>{
    let url=base+lp+'/items?$top=5000',items=[];
    const visited=new Set();
    while(url){
      const full=new URL(url,location.origin);
      if(full.origin!==location.origin||!full.pathname.startsWith(base+lp+'/items')||visited.has(full.href))throw Error('Unqualified pagination');
      visited.add(full.href);
      const data=await get(full.href);items.push(...data.value);
      url=data['odata.nextLink']||data['@odata.nextLink']||null;
    }
    return items.sort((a,b)=>a.Id-b.Id);
  };
  for(const [key,id] of Object.entries(lists)){
    const lp="/_api/web/lists(guid'"+id+"')";
    before[key]=await metadata(lp);
    const items=await readItems(lp);
    const after=await metadata(lp);
    if(JSON.stringify(before[key])!==JSON.stringify(after)||after.ItemCount!==items.length)throw Error('List changed or incomplete capture '+key);
    sources[key]={resourceRef:location.origin+base+lp,itemCount:items.length,complete:true,nextLink:null,
      modifiedUtc:after.LastItemModifiedDate,items};
  }
  // Final check spans all Lists, not just each individual read.
  for(const [key,id] of Object.entries(lists)){
    const after=await metadata("/_api/web/lists(guid'"+id+"')");
    const again=await readItems("/_api/web/lists(guid'"+id+"')");
    if(JSON.stringify(before[key])!==JSON.stringify(after)||JSON.stringify(again)!==JSON.stringify(sources[key].items))throw Error('Cross-list capture changed '+key);
    sources[key].repeatReadVerified=true;
  }
  return {schemaVersion:1,asOfUtc:new Date().toISOString(),sources,sourceContext};
}

async function provisionProcessViews({base, lists, config}) {
  const headers={Accept:'application/json;odata=nometadata'};
  const get=async path=>{const r=await fetch(base+path,{headers});if(!r.ok)throw Error('Read '+r.status+' '+path);return r.json();};
  const digest=(await (await fetch(base+'/_api/contextinfo',{method:'POST',headers})).json()).FormDigestValue;
  const write=async(path,body)=>{
    const r=await fetch(base+path,{method:'POST',headers:{...headers,'X-RequestDigest':digest,'Content-Type':'application/json;odata=nometadata'},body:JSON.stringify(body)});
    if(!r.ok)throw Error('Write '+r.status+' '+await r.text());const text=await r.text();return text?JSON.parse(text):null;
  };
  const normalise=query=>{
    const doc=new DOMParser().parseFromString('<Query>'+query+'</Query>','text/xml');
    if(doc.querySelector('parsererror'))throw Error('Invalid CAML');
    const node=e=>[e.nodeName,[...e.attributes].map(a=>[a.name,a.value]).sort(),[...e.childNodes].filter(n=>n.nodeType===1).map(node),[...e.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent.trim()).join('')];
    return JSON.stringify(node(doc.documentElement));
  };
  const result=[];
  for(const def of config.views){
    const lp="/_api/web/lists(guid'"+lists[def.resource]+"')";
    const fields=(await get(lp+'/fields?$select=InternalName')).value.map(f=>f.InternalName);
    if(def.fields.some(name=>!fields.includes(name)))throw Error('Missing view field '+def.key);
    const views=(await get(lp+'/views?$select=Id,Title,ViewQuery,DefaultView,ServerRelativeUrl')).value;
    const matches=views.filter(v=>v.Title===def.title);
    if(matches.length>1)throw Error('Duplicate managed view');
    let view=matches[0];
    if(view&&normalise(view.ViewQuery)!==normalise(def.query))throw Error('Managed view query drift '+def.title);
    if(!view)view=await write(lp+'/views',{Title:def.title,ViewQuery:def.query,RowLimit:100,PersonalView:false});
    const vp=lp+"/views(guid'"+view.Id+"')";
    const current=(await get(vp+'/ViewFields')).Items;
    for(const name of def.fields)if(!current.includes(name))await write(vp+'/ViewFields/addviewfield',{strField:name});
    const readback=await get(vp+'?$select=Id,Title,ViewQuery,DefaultView,ServerRelativeUrl');
    if(readback.DefaultView||normalise(readback.ViewQuery)!==normalise(def.query))throw Error('Unexpected view readback');
    result.push({key:def.key,adopted:!!matches.length,...readback,fields:(await get(vp+'/ViewFields')).Items});
  }
  return {views:result,itemWrites:0,permissionChanges:0};
}
