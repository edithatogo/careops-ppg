/* Same-origin SharePoint deployment. Run in an authenticated site page.
   Inputs contain the private binding, immutable assets and expected native manifest.
   This writes only its evidence files, manifest and one managed hub block. */
async function deploySourceComparison(inputs) {
  const base = inputs.sitePath;
  const headers = {Accept: 'application/json;odata=nometadata'};
  const escape = value => value.replaceAll("'", "''");
  const equivalentHTML = (left, right) => {
    const canonical = text => {
      const body = new DOMParser().parseFromString(text, 'text/html').body;
      const node = element => element.nodeType === Node.TEXT_NODE ? element.textContent :
        [element.nodeName, Array.from(element.attributes || []).map(attribute => {
          if (attribute.name !== 'href') return [attribute.name, attribute.value];
          const url = new URL(attribute.value, location.origin);
          return ['href', url.origin, url.pathname, Array.from(url.searchParams.entries()).sort(), url.hash];
        }).sort(), Array.from(element.childNodes).map(node)];
      return JSON.stringify(Array.from(body.childNodes).map(node));
    };
    return canonical(left) === canonical(right);
  };
  const api = async (path, options = {}) => {
    const response = await fetch(base + '/_api/' + path, {...options,
      headers: {...headers, ...options.headers}});
    if (!response.ok) throw new Error(response.status + ' ' + path + ' ' + (await response.text()).slice(0, 200));
    const text = await response.text();
    return text ? JSON.parse(text) : null;
  };
  const hash = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)))
    .map(value => value.toString(16).padStart(2, '0')).join('');
  const bytesAt = async path => {
    const response = await fetch(base + "/_api/web/GetFileByServerRelativeUrl('" + escape(path) + "')/$value", {headers});
    if (response.status === 404) return null;
    if (!response.ok) throw new Error('file read ' + response.status);
    return new Uint8Array(await response.arrayBuffer());
  };
  const context = await api('contextinfo', {method:'POST'});
  const digest = context.FormDigestValue;
  const writes = {'X-RequestDigest':digest};
  const receipts = [];
  for (const asset of inputs.assets) {
    const bytes = Uint8Array.from(atob(asset.base64), character => character.charCodeAt(0));
    if (await hash(bytes) !== asset.sha256) throw new Error('payload hash mismatch');
    const path = asset.folder + '/' + asset.name;
    const before = await bytesAt(path);
    let adopted = false;
    if (before) {
      if (await hash(before) !== asset.sha256) throw new Error('existing asset differs: ' + asset.name);
      adopted = true;
    } else {
      await api("web/GetFolderByServerRelativeUrl('" + escape(asset.folder) + "')/Files/add(url='" + escape(asset.name) + "',overwrite=false)",
        {method:'POST',headers:{...writes,'Content-Type':'application/octet-stream'},body:bytes});
    }
    const after = await bytesAt(path);
    if (!after || await hash(after) !== asset.sha256) throw new Error('asset readback mismatch');
    receipts.push({name:asset.name,path,sha256:asset.sha256,size:after.length,adopted});
  }
  if (inputs.manifest) {
    const path=inputs.manifest.path;
    const before=await bytesAt(path);
    if (!before) throw new Error('canonical manifest missing');
    const beforeHash=await hash(before);
    const target=new TextEncoder().encode(inputs.manifest.text);
    if (beforeHash !== await hash(target)) {
      if (beforeHash !== inputs.manifest.expectedSHA256) throw new Error('manifest changed since read');
      const metadata=await api("web/GetFileByServerRelativeUrl('"+escape(path)+"')?$select=ETag");
      const fresh=await bytesAt(path);
      if (await hash(fresh)!==beforeHash) throw new Error('manifest concurrent change');
      await api("web/GetFileByServerRelativeUrl('"+escape(path)+"')/$value",{method:'POST',
        headers:{...writes,'X-HTTP-Method':'PUT','IF-MATCH':metadata.ETag,'Content-Type':'application/octet-stream'},body:target});
    }
    if(await hash(await bytesAt(path))!==await hash(target))throw new Error('manifest readback mismatch');
  }
  if (inputs.hub) {
    const route='sitepages/pages('+inputs.hub.pageId+')';
    const before=await api(route);
    const controls=JSON.parse(before.CanvasContent1);
    const matches=controls.filter(control=>control.id===inputs.hub.control.id);
    if(matches.length>1)throw new Error('duplicate managed hub block');
    const existing=matches[0];
    // Compare decoded URL semantics so SharePoint's URL normalisation doesn't
    // cause an identical deployment to publish another page version.
    if (!existing || !equivalentHTML(existing.innerHTML, inputs.hub.control.innerHTML)) {
      if(existing && existing.innerHTML!==inputs.hub.expectedHTML)throw new Error('managed block changed');
      if(existing) existing.innerHTML=inputs.hub.control.innerHTML;
      else {
        const positioned=controls.filter(c=>c.position);
        const next=Math.max(...positioned.map(c=>c.position.controlIndex))+1;
        const control=structuredClone(inputs.hub.control);control.position.controlIndex=next;
        controls.splice(controls.findIndex(c=>c.controlType===0),0,control);
      }
      const fresh=await api(route);
      if(fresh.CanvasContent1!==before.CanvasContent1)throw new Error('hub concurrent change');
      const file=await api("web/GetFileByServerRelativeUrl('"+escape(inputs.hub.path)+"')?$select=CheckOutType");
      if(file.CheckOutType!==2)throw new Error('hub checked out by another operation');
      await api(route+'/CheckoutPage',{method:'POST',headers:writes});
      await api(route+'/SavePageAsDraft',{method:'POST',headers:{...writes,'Content-Type':'application/json;odata=nometadata'},
        body:JSON.stringify({CanvasContent1:JSON.stringify(controls),Title:before.Title,Description:before.Description})});
      await api(route+'/Publish',{method:'POST',headers:writes});
    }
    const after=await api(route), actual=JSON.parse(after.CanvasContent1);
    if(actual.filter(c=>c.id===inputs.hub.control.id).length!==1)throw new Error('managed block not saved');
    const unrelated=controls.filter(c=>c.id!==inputs.hub.control.id);
    // Existing content is verified separately; don't accept missing IDs after save.
    if(unrelated.some(c=>c.id && !actual.some(a=>a.id===c.id)))throw new Error('unrelated control lost');
    receipts.push({hub:true,managedControl:inputs.hub.control.id,controlCount:actual.length,
      savedHTML:actual.find(c=>c.id===inputs.hub.control.id).innerHTML});
  }
  return {receipts,sourceWrites:0,caseWrites:0,permissionChanges:0,channelPosts:0};
}
