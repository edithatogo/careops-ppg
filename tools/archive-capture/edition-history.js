/* Native edition-history projection. Originals are read-only; run in an existing
 * authenticated SharePoint page. Private manifest and receipts stay outside Git. */
function compareNativeVersionLabels(left, right) {
  const parts = value => {
    if (typeof value !== 'string' || !/^\d+(?:\.\d+)*$/.test(value)) throw Error('Unknown native version label');
    const values = value.split('.').map(Number);
    if (values.some(v => !Number.isSafeInteger(v))) throw Error('Unknown native version label');
    return values;
  };
  const a = parts(left), b = parts(right);
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const difference = (a[i] || 0) - (b[i] || 0);
    if (difference) return difference;
  }
  return 0;
}
async function reconcileEditionHistory(base, manifest, state) {
  const h = {Accept:'application/json;odata=nometadata'};
  const quote = s => s.replaceAll("'", "''");
  const endpoint = path => base+"/_api/web/GetFileByServerRelativePath(decodedurl='"+quote(path)+"')";
  const hash = async raw => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw))).map(x=>x.toString(16).padStart(2,'0')).join('');
  const get = async url => {const r=await fetch(url,{headers:h});if(!r.ok)throw Error('Read '+r.status);return r.json()};
  const bytes = async url => {const r=await fetch(url);if(!r.ok)throw Error('Download '+r.status);return r.arrayBuffer()};
  const digest = async () => {const r=await fetch(base+'/_api/contextinfo',{method:'POST',headers:h});if(!r.ok)throw Error('Context '+r.status);return (await r.json()).FormDigestValue};
  state.state='running';state.writes=0;state.versions=[];
  try {
    const {targetPath,editions,libraryId}=manifest;
    const root=new URL(base).pathname+'/PPG Review Evidence/';
    if(!Array.isArray(editions)||editions.length<2||editions.length>500)throw Error('Require 2–500 explicitly ordered editions');
    if(!/^[a-f0-9-]{36}$/i.test(libraryId))throw Error('Invalid library binding');
    if(manifest.qualification===true) {
      if(!targetPath.startsWith(root+'Templates/Native edition history qualification/'))throw Error('Qualification target outside isolated folder');
    } else {
      if(!/^[a-f0-9-]{36}$/i.test(manifest.documentUID)||!manifest.identityEvidence)throw Error('Established family identity evidence required');
      if(targetPath!==root+'Policy Edition Histories/'+manifest.documentUID+'.captured')throw Error('Unexpected family target');
    }
    if(targetPath.includes('..')||new Set(editions.map(e=>e.sha256)).size!==editions.length)throw Error('Unsafe path or duplicate content');
    const settings=await get(base+"/_api/web/lists(guid'"+libraryId+"')?$select=EnableVersioning,MajorVersionLimit,ForceCheckout,EnableModeration");
    if(!settings.EnableVersioning||settings.MajorVersionLimit<editions.length||settings.ForceCheckout||settings.EnableModeration)throw Error('Library settings not qualified for direct append');
    const originals=[];
    for(const [index,e] of editions.entries()) {
      if(e.order!==index+1||!e.sourceEdition||!e.orderEvidence||!/^[a-f0-9]{64}$/.test(e.sha256)||!Number.isInteger(e.bytes)||e.bytes<1)throw Error('Incomplete edition/order evidence');
      if(!e.sourcePath.startsWith(root)||e.sourcePath.includes('..')||e.sourcePath===targetPath)throw Error('Unsafe source target overlap');
      const info=await get(endpoint(e.sourcePath)+'?$select=UniqueId,ETag,Length');
      const raw=await bytes(endpoint(e.sourcePath)+'/$value');
      if(raw.byteLength!==e.bytes||await hash(raw)!==e.sha256)throw Error('Original bytes differ');
      if(manifest.qualification!==true) {
        const item=await get(endpoint(e.sourcePath)+'/ListItemAllFields');
        if(item.PPGDocumentUID!==manifest.documentUID||item.PPGPolicyEdition!==e.sourceEdition||!item.PPGCaptureEditionEvidence||item.PPGCaptureSHA256!==e.sha256)throw Error('Native identity/edition evidence differs');
      }
      originals.push({e,info,raw});
    }
    const file=endpoint(targetPath);
    const inspect=async()=>{
      const r=await fetch(file+'?$select=UniqueId,ETag,Length,UIVersionLabel,CheckOutType',{headers:h});
      if(r.status===404)return null;if(!r.ok)throw Error('Target read '+r.status);
      const info=await r.json();if(info.CheckOutType!==2)throw Error('Target is checked out; explicit recovery required');const current=await hash(await bytes(file+'/$value'));
      const history=await get(file+'/Versions?$select=ID,VersionLabel,IsCurrentVersion&$top=5000');
      if(history['odata.nextLink']||history['@odata.nextLink'])throw Error('Incomplete native history');
      const versions=[];
      for(const v of history.value) {
        if(v.IsCurrentVersion)continue;
        const raw=await bytes(file+'/Versions('+v.ID+')/$value');versions.push({nativeVersion:v.VersionLabel,sha256:await hash(raw)});
      }
      for (const v of versions) compareNativeVersionLabels(v.nativeVersion, v.nativeVersion);
      compareNativeVersionLabels(info.UIVersionLabel, info.UIVersionLabel);
      versions.sort((a,b)=>compareNativeVersionLabels(a.nativeVersion,b.nativeVersion));
      versions.push({nativeVersion:info.UIVersionLabel,sha256:current});
      // Metadata may create repeated hashes, but no unknown or reordered content is adopted.
      const distinct=versions.filter((v,i)=>!i||v.sha256!==versions[i-1].sha256);
      if(distinct.length>editions.length||distinct.some((v,i)=>v.sha256!==editions[i].sha256))throw Error('Unknown or reordered native history; preserve target');
      return {info,versions,completed:distinct.length};
    };
    let target=await inspect();const originalTargetId=target?.info.UniqueId;
    for(let index=target?.completed||0;index<originals.length;index++) {
      const {e,raw}=originals[index];const token=await digest();let r;
      if(!target) {
        const folder=targetPath.slice(0,targetPath.lastIndexOf('/'));const name=targetPath.slice(targetPath.lastIndexOf('/')+1);
        r=await fetch(base+"/_api/web/GetFolderByServerRelativePath(decodedurl='"+quote(folder)+"')/Files/Add(url='"+quote(name)+"',overwrite=false)",{method:'POST',headers:{...h,'X-RequestDigest':token},body:raw});
      } else {
        if(!target.info.ETag)throw Error('Missing exact file ETag');
        // Native qualification found $value PUT ignores stale If-Match. Obtain
        // SharePoint's edit lock, then recheck content before the update instead.
        const lock=await fetch(file+'/CheckOut()',{method:'POST',headers:{...h,'X-RequestDigest':token}});
        if(!lock.ok)throw Error('Checkout '+lock.status);
        state.checkedOutTarget=targetPath;
        const locked=await get(file+'?$select=UniqueId,CheckOutType');
        const lockedHash=await hash(await bytes(file+'/$value'));
        if(locked.UniqueId!==target.info.UniqueId||locked.CheckOutType===2||lockedHash!==editions[index-1].sha256)throw Error('Target changed before checkout lock; recovery required');
        r=await fetch(file+'/$value',{method:'POST',headers:{...h,'X-RequestDigest':token,'X-HTTP-Method':'PUT','IF-MATCH':target.info.ETag},body:raw});
      }
      if(!r.ok)throw Error('Append '+r.status);state.writes++;
      if(state.checkedOutTarget) {
        if(await hash(await bytes(file+'/$value'))!==e.sha256)throw Error('Checked-out content differs; recovery required');
        const comment='Captured source edition '+e.sourceEdition+'; SHA256 '+e.sha256+'; imported history, authority unconfirmed';
        const checkin=await fetch(file+"/CheckIn(comment='"+quote(comment)+"',checkintype=1)",{method:'POST',headers:{...h,'X-RequestDigest':await digest()}});
        if(!checkin.ok)throw Error('Checkin '+checkin.status+'; recovery required');
        delete state.checkedOutTarget;
      }
      target=await inspect();
      if(target.completed!==index+1)throw Error('Append history readback differs');
      if(originalTargetId&&target.info.UniqueId!==originalTargetId)throw Error('Target identity changed');
    }
    for(const {e,info} of originals) {
      const after=await get(endpoint(e.sourcePath)+'?$select=UniqueId,ETag,Length');
      if(after.UniqueId!==info.UniqueId||after.ETag!==info.ETag||after.Length!==info.Length||await hash(await bytes(endpoint(e.sourcePath)+'/$value'))!==e.sha256)throw Error('Original capture changed');
    }
    state.targetPath=targetPath;state.uniqueId=target.info.UniqueId;state.versions=target.versions.map(v=>({...v,sourceEdition:editions.find(e=>e.sha256===v.sha256).sourceEdition}));
    state.originalsPreserved=true;state.qualification=manifest.qualification===true;state.state='completed';
  } catch(error) {state.state='failed';state.error=String(error)}
}
