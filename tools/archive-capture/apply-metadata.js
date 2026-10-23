/* Explicit capture metadata only. Does not write policy identity/currency or replace bytes. */
async function applyCaptureMetadata(base, libraryId, rows, state) {
  const lp=base+"/_api/web/lists(guid'"+libraryId+"')",headers={Accept:'application/json;odata=nometadata'};
  const get=async url=>{const r=await fetch(url,{headers});if(!r.ok)throw Error('GET '+r.status+' '+url);const data=await r.json();data._receiptEtag=r.headers.get('ETag');return data};
  const hash=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(x=>x.toString(16).padStart(2,'0')).join('');
  state.state='running';state.receipts=[];
  try {
    for(const row of rows){
      const file=base+"/_api/web/GetFileByServerRelativePath(decodedurl='"+row.path.replaceAll("'","''")+"')";
      const before=await get(file+'?$select=UniqueId,Length');
      if(before.UniqueId.toLowerCase()!==row.uniqueId.toLowerCase()||Number(before.Length)!==row.bytes)throw Error('Capture pin mismatch '+row.path);
      const original=await fetch(file+'/$value');if(!original.ok)throw Error('Original download '+original.status);const originalBytes=await original.arrayBuffer();if(originalBytes.byteLength!==row.bytes||await hash(originalBytes)!==row.sha256)throw Error('Original bytes differ; no metadata write');
      const item=await get(file+'/ListItemAllFields');
      const patch={};
      for(const [key,value] of Object.entries(row.fields)){
        const old=item[key];
        const equal=key==='PPGCaptureDate'?old&&Date.parse(old)===Date.parse(value):old===value;
        if(equal)continue;
        if(old!==null&&old!==undefined&&old!=='')throw Error('Existing metadata differs; preserve human edit '+key+' '+row.path);
        patch[key]=value;
      }
      if(Object.keys(patch).length){
        if(!item._receiptEtag)throw Error('Missing exact item ETag');
        const c=await fetch(base+'/_api/contextinfo',{method:'POST',headers});if(!c.ok)throw Error('Context '+c.status);const digest=(await c.json()).FormDigestValue;
        const r=await fetch(lp+'/items('+item.Id+')',{method:'POST',headers:{...headers,'Content-Type':'application/json;odata=nometadata','X-RequestDigest':digest,'X-HTTP-Method':'MERGE','IF-MATCH':item._receiptEtag},body:JSON.stringify(patch)});
        if(!r.ok)throw Error('Metadata save '+r.status+' '+await r.text());
      }
      const after=await get(file+'/ListItemAllFields');
      for(const [key,value] of Object.entries(row.fields))if(key==='PPGCaptureDate'?Date.parse(after[key])!==Date.parse(value):after[key]!==value)throw Error('Metadata readback differs '+key);
      for(const key of ['PPGDocumentUID','PPGPolicyEdition','PPGCurrency','PPGReplacesEdition','PPGAuthorityLink','PPGCurrencyChecked','PPGCurrencyEvidence'])if(JSON.stringify(item[key])!==JSON.stringify(after[key]))throw Error('Business metadata changed '+key);
      const down=await fetch(file+'/$value');if(!down.ok)throw Error('Download '+down.status);const raw=await down.arrayBuffer();if(raw.byteLength!==row.bytes||await hash(raw)!==row.sha256)throw Error('Preserved bytes mismatch');
      const pin=await get(file+'?$select=UniqueId,ETag,Length,UIVersionLabel');
      state.receipts.push({path:row.path,sha256:row.sha256,bytes:row.bytes,pin,changedFields:Object.keys(patch),policyFieldsPreserved:true});
    }
    state.state='completed';state.completedAt=new Date().toISOString();
  }catch(e){state.state='failed';state.error=String(e)}
}
