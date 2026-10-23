/* Apply only exact, freshly evidenced links to existing identities; no identity minting or currency edits. */
async function applyEditionLinks(base,libraryId,catalogueId,rows,state){
 const h={Accept:'application/json;odata=nometadata'},lp=base+"/_api/web/lists(guid'"+libraryId+"')";
 const get=async u=>{const r=await fetch(u,{headers:h});if(!r.ok)throw Error('GET '+r.status);const data=await r.json();data._receiptEtag=r.headers.get('ETag');return data};
 const hash=async raw=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw))).map(x=>x.toString(16).padStart(2,'0')).join('');
 state.state='running';state.receipts=[];
 try{for(const row of rows){
  // SharePoint sourceDocumentId is Note and cannot be filtered server-side.
  // Read the complete bounded projection and compare exact aliases locally.
  const catalogue=await get(base+"/_api/web/lists(guid'"+catalogueId+"')/items?$select=Id,DocumentUID,sourceDocumentId&$top=5000");
  if(catalogue['odata.nextLink']||catalogue['@odata.nextLink'])throw Error('Incomplete catalogue projection; no uniqueness claim');
  const found={value:catalogue.value.filter(r=>r.sourceDocumentId===row.sourceAlias)};
  if(found.value.length!==1||found.value[0].DocumentUID!==row.existingDocumentUID||found.value[0].Id!==row.catalogueItemId)throw Error('Existing catalogue link changed');
  const file=base+"/_api/web/GetFileByServerRelativePath(decodedurl='"+row.path.replaceAll("'","''")+"')";
  const before=await get(file+'/ListItemAllFields');
  if(before.PPGCaptureSHA256!==row.sha256)throw Error('Capture hash metadata differs');
  const download=await fetch(file+'/$value');if(!download.ok)throw Error('Download');const raw=await download.arrayBuffer();if(await hash(raw)!==row.sha256||raw.byteLength!==row.bytes)throw Error('Source byte hash differs');
  const evidence=JSON.stringify({sourceAlias:row.sourceAlias,sourceEdition:row.sourceEdition,existingDocumentUID:row.existingDocumentUID,catalogueItemId:row.catalogueItemId,headerTextSHA256:row.headerTextSHA256,sourceSHA256:row.sha256,method:'Fresh first-page Document Number and printed Version; exact unique native catalogue alias; not currency verification'});
  const target={PPGDocumentUID:row.existingDocumentUID,PPGPolicyEdition:row.sourceEdition,PPGCaptureEditionEvidence:evidence},patch={};
  for(const [key,value]of Object.entries(target)){if(before[key]===value)continue;if(before[key])throw Error('Preserve existing edition finding '+key);patch[key]=value}
  if(Object.keys(patch).length){if(!before._receiptEtag)throw Error('Missing ETag');const c=await fetch(base+'/_api/contextinfo',{method:'POST',headers:h});if(!c.ok)throw Error('Context');const digest=(await c.json()).FormDigestValue;const save=await fetch(lp+'/items('+before.Id+')',{method:'POST',headers:{...h,'Content-Type':'application/json;odata=nometadata','X-RequestDigest':digest,'X-HTTP-Method':'MERGE','IF-MATCH':before._receiptEtag},body:JSON.stringify(patch)});if(!save.ok)throw Error('Save '+save.status)}
  const after=await get(file+'/ListItemAllFields');for(const [key,value]of Object.entries(target))if(after[key]!==value)throw Error('Edition readback mismatch');
  for(const key of ['PPGCurrency','PPGReplacesEdition','PPGAuthorityLink','PPGCurrencyChecked','PPGCurrencyEvidence','PPGCaptureSHA256'])if(JSON.stringify(before[key])!==JSON.stringify(after[key]))throw Error('Unrelated finding changed');
  const pin=await get(file+'?$select=UniqueId,ETag,Length,UIVersionLabel');state.receipts.push({path:row.path,sha256:row.sha256,existingDocumentUID:row.existingDocumentUID,sourceEdition:row.sourceEdition,changedFields:Object.keys(patch),pin,currencyPreserved:true});
 }state.state='completed'}catch(e){state.state='failed';state.error=String(e)}
}
