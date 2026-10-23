// BrowserOS Neo saved-helper body. Run only with an explicitly selected HTTPS family.
async (browser, page, inputs = {}) => {
  if (!Array.isArray(inputs.sources) || inputs.sources.length !== 1)
    throw Error('read_one_selected_source_per_call');
  return await browser.page(page).evaluate(async ({sources}) => {
    const observations = [];
    for (const source of sources) {
      const url = new URL(source.canonicalUrl);
      if (url.protocol !== 'https:' || url.origin !== location.origin || url.search || url.hash || url.username || url.password)
        throw Error('exact_same_origin_https_source_required');
      const failure = status => ({sourceKey:source.sourceKey,status,capturedAtUtc:new Date().toISOString()});
      let response;
      try { response = await fetch(url.href,{cache:'no-store',credentials:'same-origin',redirect:'manual',signal:AbortSignal.timeout(8000)}); }
      catch { observations.push(failure('error')); continue; }
      if (response.status === 401 || response.status === 403) { observations.push(failure('denied')); continue; }
      if (response.status === 404 || response.status === 410) { observations.push(failure('missing')); continue; }
      if (!response.ok || response.type === 'opaqueredirect' || response.url !== url.href) { observations.push(failure('error')); continue; }
      if (!response.headers.get('content-type')?.includes('text/html')) { observations.push(failure('unsupported')); continue; }
      const reader=response.body.getReader(), chunks=[];let size=0, failed=false;
      try {
        while (true) {
          const {done,value}=await reader.read();if(done)break;
          size+=value.length;if(size>10*1024*1024){await reader.cancel();failed=true;break;}chunks.push(value);
        }
      } catch { failed=true; await reader.cancel().catch(()=>{}); }
      if(failed || !size){observations.push(failure('error'));continue;}
      const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
      const doc=new DOMParser().parseFromString(new TextDecoder('utf-8',{fatal:true}).decode(bytes),'text/html');
      const text=doc.querySelector('main')?.textContent || doc.querySelector('#content')?.textContent || '';
      // Identification/format checks only; no semantic, applicability or currency judgement.
      if(typeof source.expectedIdentifier!=='string' || !source.expectedIdentifier || !text.includes(source.expectedIdentifier) ||
         typeof source.expectedTitle!=='string' || !source.expectedTitle || !text.includes(source.expectedTitle) ||
         doc.querySelector('input[type="password"]')) {observations.push(failure('unsupported'));continue;}
      const sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(x=>x.toString(16).padStart(2,'0')).join('');
      let binary='';for(let i=0;i<bytes.length;i+=16384)binary+=String.fromCharCode(...bytes.subarray(i,i+16384));
      const etag=response.headers.get('etag'),modified=response.headers.get('last-modified');
      observations.push({sourceKey:source.sourceKey,status:'captured',canonicalUrl:url.href,capturedAtUtc:new Date().toISOString(),
        sha256,size,base64:btoa(binary),nativeVersionRef:etag || modified || null,
        responseHeaders:{contentType:response.headers.get('content-type'),etag,lastModified:modified},
        acquisitionRoute:'BrowserOS Neo same-origin no-store GET; exact title/identifier checked; public source; no semantic determination'});
    }
    return {observations,sourceWrites:false,credentialsTransferred:false};
  },inputs);
}
