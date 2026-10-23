/* Read-only maintenance audit inside the existing authenticated SharePoint site.
   Matching objects are adopted without edits; missing objects/drift stop.
   This is not a provisioning command or an executable Teams button. */
function policyEditionQuery(base, config, definition) {
  const esc=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
  const join=(operator,terms)=>terms.length===1?terms[0]:'<'+operator+'>'+terms[0]+join(operator,terms.slice(1))+'</'+operator+'>';
  const extension=join('Or',config.supportedExtensions.map(value=>'<Eq><FieldRef Name="File_x0020_Type"/><Value Type="Text">'+esc(value)+'</Value></Eq>'));
  const archive='<And><BeginsWith><FieldRef Name="FileDirRef"/><Value Type="Text">'+esc(base+'/PPG Review Evidence/'+config.archiveFolderName)+'</Value></BeginsWith>'+extension+'</And>';
  const currencies=definition.currencies.map(value=>'<Eq><FieldRef Name="PPGCurrency"/><Value Type="Choice">'+esc(value)+'</Value></Eq>');
  if(definition.includeBlank)currencies.unshift('<IsNull><FieldRef Name="PPGCurrency"/></IsNull>');
  const sourceKind=config.excludeSupportingSourcePages?'<Or><IsNull><FieldRef Name="PPGCaptureKind"/></IsNull><Neq><FieldRef Name="PPGCaptureKind"/><Value Type="Choice">Supporting source page</Value></Neq></Or>':null;
  const scoped=sourceKind?'<And>'+archive+sourceKind+'</And>':archive;
  const predicate=currencies.length?'<And>'+scoped+join('Or',currencies)+'</And>':scoped;
  return '<Where>'+predicate+'</Where><GroupBy Collapse="TRUE"><FieldRef Name="'+config.identityField+'"/></GroupBy><OrderBy><FieldRef Name="FileLeafRef"/></OrderBy>';
}

async function maintainPolicyEditions({base,libraryId,fieldConfig,viewConfig}) {
  if(!base.startsWith('/')||!/^[-0-9a-f]{36}$/i.test(libraryId)||fieldConfig.schemaVersion!==1||viewConfig.schemaVersion!==1)throw Error('Unqualified binding/config');
  const lp="/_api/web/lists(guid'"+libraryId+"')",headers={Accept:'application/json;odata=nometadata'};
  const get=async path=>{const r=await fetch(base+path,{headers,cache:'no-store'});if(!r.ok)throw Error(r.status+' '+path);return r.json();};
  const normalise=xml=>{
    const doc=new DOMParser().parseFromString('<Query>'+xml+'</Query>','text/xml');if(doc.querySelector('parsererror'))throw Error('Invalid XML');
    const node=e=>[e.nodeName,[...e.attributes].map(a=>[a.name,a.value]).sort(),[...e.childNodes].filter(n=>n.nodeType===1).map(node),[...e.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent.trim()).join('')];
    return JSON.stringify(node(doc.documentElement));
  };
  const settings=()=>get(lp+'?$select=EnableVersioning,EnableMinorVersions,EnableModeration,ForceCheckout,MajorVersionLimit,HasUniqueRoleAssignments,DefaultViewUrl');
  const before=await settings();if(!before.EnableVersioning)throw Error('Native version history unavailable; no settings change attempted');
  const existing=(await get(lp+'/fields?$select=InternalName,Title,TypeAsString,Required,SchemaXml,CustomFormatter,Description')).value;
  const receipt={created:[],adopted:[],views:[],settings:before,itemWrites:0,permissionChanges:0};
  for(const def of fieldConfig.fields){
    let field=existing.find(f=>f.InternalName===def.name);
    if(!field)throw Error('Managed field missing '+def.name);
    receipt.adopted.push(def.name);
    if(field.TypeAsString!==def.type||field.Required||field.Title!==def.title||field.Description!==def.description)throw Error('Managed field drift '+def.name);
    if(def.choices){const choices=[...new DOMParser().parseFromString(field.SchemaXml,'text/xml').querySelectorAll('CHOICE')].map(n=>n.textContent);if(JSON.stringify(choices)!==JSON.stringify(def.choices))throw Error('Choice drift '+def.name);}
  }
  const currency=await get(lp+"/fields/getbyinternalnameortitle('PPGCurrency')?$select=CustomFormatter");
  if(!currency.CustomFormatter||JSON.parse(currency.CustomFormatter).txtContent!=="=if(@currentField == '', 'Unconfirmed', @currentField)")throw Error('Blank-currency display unqualified');
  const views=(await get(lp+'/views?$select=Id,Title,ViewQuery,Scope,DefaultView,ServerRelativeUrl')).value;
  for(const def of viewConfig.views){
    const query=policyEditionQuery(base,viewConfig,def),matches=views.filter(v=>v.Title===def.title);
    if(matches.length>1)throw Error('Duplicate managed view '+def.title);
    let view=matches[0];
    if(!view)throw Error('Managed view missing '+def.title);
    if(normalise(view.ViewQuery)!==normalise(query)||view.Scope!==viewConfig.scope||view.DefaultView)throw Error('Managed view drift '+def.title);
    const fields=(await get(lp+"/views(guid'"+view.Id+"')/ViewFields")).Items;
    if(viewConfig.viewFields.some(f=>!fields.includes(f)))throw Error('View columns missing '+def.title);
    receipt.views.push({...view,key:def.key,adopted:!!matches.length,fields});
  }
  for(const title of viewConfig.archiveNavigationViews){const view=views.find(v=>v.Title===title);if(!view)throw Error('Archive navigation view missing');const fields=(await get(lp+"/views(guid'"+view.Id+"')/ViewFields")).Items;if(['PPGPolicyEdition','PPGCurrency','_UIVersionString'].some(f=>!fields.includes(f)))throw Error('Archive navigation columns drift');}
  const after=await settings();if(JSON.stringify(before)!==JSON.stringify(after))throw Error('Library settings changed during verification');
  return receipt;
}
