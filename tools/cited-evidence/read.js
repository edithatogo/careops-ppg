/* Run only in the current authenticated SharePoint page. GET-only selected reads.
   This is a Codex/browser retrieval adapter, not a SharePoint-native skill action. */
async function readCitedEvidence({sitePath, allowedFolder, sources, maximumBytes=100000}) {
  if (!Array.isArray(sources) || sources.length > 5) throw Error('Select at most five sources');
  if (!sitePath.startsWith('/') || sitePath.includes('..') || !allowedFolder.startsWith(sitePath+'/')) throw Error('Invalid qualified site/folder');
  if (!Number.isSafeInteger(maximumBytes) || maximumBytes > 100000 || maximumBytes < 1) throw Error('Invalid content limit');
  const utcTime=value=>typeof value==='string' &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$/.test(value) &&
    Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,19)===value.slice(0,19);
  const lengthOf=value=>(typeof value==='number' ||
    (typeof value==='string' && /^\d+$/.test(value))) ? Number(value) : NaN;
  const validMetadata=m=>m && typeof m==='object' && !Array.isArray(m) &&
    typeof m.Name==='string' && m.Name.trim().length>0 &&
    typeof m.UniqueId==='string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(m.UniqueId) &&
    !/^0{8}-0{4}-0{4}-0{4}-0{12}$/.test(m.UniqueId) &&
    typeof m.ETag==='string' && m.ETag.trim().length>0 &&
    [m.MajorVersion,m.MinorVersion].every(v=>Number.isSafeInteger(v) && v>=0) &&
    Number.isSafeInteger(lengthOf(m.Length)) && lengthOf(m.Length)>=0 && utcTime(m.TimeLastModified);
  const api=sitePath+'/_api/web';
  const headers={Accept:'application/json;odata=nometadata','Cache-Control':'no-cache'};
  const hash=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
  const results=[];
  for (const selected of sources) {
    const path=selected.path;
    if (typeof path!=='string' || !path.startsWith(allowedFolder.replace(/\/$/,'')+'/') || /[?#]|\.\./.test(decodeURIComponent(path))) throw Error('Source outside selected folder');
    const file=api+"/GetFileByServerRelativeUrl('"+path.replaceAll("'","''")+"')";
    const metadata=file+'?$select=UniqueId,Name,Length,ETag,MajorVersion,MinorVersion,TimeLastModified';
    const fail=(status)=>({sourceId:selected.sourceId,status});
    const read=await fetch(metadata,{headers,cache:'no-store'});
    if(!read.ok){results.push(fail(read.status===403||read.status===401?'denied':read.status===404?'missing':'unsupported'));continue;}
    let before;try{before=await read.json();}catch(_){results.push(fail('unsupported'));continue;}
    if(!validMetadata(before)){results.push(fail('unsupported'));continue;}
    if(!/\.(txt|md)$/i.test(before.Name)||lengthOf(before.Length)>maximumBytes){results.push(fail('unsupported'));continue;}
    const content=await fetch(file+'/$value',{headers:{'Cache-Control':'no-cache'},cache:'no-store'});
    if(!content.ok){results.push(fail(content.status===403||content.status===401?'denied':content.status===404?'missing':'unsupported'));continue;}
    const bytes=await content.arrayBuffer();
    if(bytes.byteLength>maximumBytes || bytes.byteLength!==lengthOf(before.Length)){results.push(fail('unsupported'));continue;}
    let text;try{text=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes);}catch(_){results.push(fail('unsupported'));continue;}
    const afterRead=await fetch(metadata,{headers,cache:'no-store'});
    if(!afterRead.ok){results.push(fail('changed-during-read'));continue;}
    let after;try{after=await afterRead.json();}catch(_){results.push(fail('changed-during-read'));continue;}
    if(!validMetadata(after)){results.push(fail('changed-during-read'));continue;}
    if(['UniqueId','Name','ETag','Length','MajorVersion','MinorVersion','TimeLastModified'].some(k=>String(before[k])!==String(after[k]))){results.push(fail('changed-during-read'));continue;}
    if(!['captured-reference-unconfirmed','draft-unapproved'].includes(selected.authorityLabel)) throw Error('Conservative authority label required');
    results.push({sourceId:selected.sourceId,status:'retrieved',canonicalUrl:location.origin+path,nativeUniqueId:before.UniqueId,
      nativeVersionRef:before.MajorVersion+'.'+before.MinorVersion+' '+before.ETag,
      retrievedAtUtc:new Date().toISOString(),sha256:await hash(bytes),authorityLabel:selected.authorityLabel,text});
  }
  return {sources:results,readBoundary:'Current browser principal; metadata/content denied reads return no content or metadata',writesPerformed:0};
}
