/** Create-only seeds with exact readback; differences preserve the existing row. */
async function seedReviewRecords(sitePath, records, journal) {
  if (!/^\/teams\/[A-Za-z0-9_-]+$/.test(sitePath)) throw Error('Unsupported site path');
  const base = sitePath + '/_api';
  const headers = {Accept:'application/json;odata=nometadata'};
  const context = await fetch(base+'/contextinfo',{method:'POST',headers});
  if (!context.ok) throw Error('Context status '+context.status);
  const digest = (await context.json()).FormDigestValue;
  for (const row of records) {
    if (!/^PPG [A-Za-z ]+$/.test(row.list) || !/^[A-Za-z]+Key$/.test(row.key)) throw Error('Unqualified seed target');
    const route = base+"/web/lists/getbytitle('"+row.list+"')/items";
    const literal = String(row.record[row.key]).replace(/'/g,"''");
    const response = await fetch(route+'?$filter='+encodeURIComponent(row.key+" eq '"+literal+"'"),{headers,signal:AbortSignal.timeout(60000)});
    if (!response.ok) throw Error('Read status '+response.status);
    const data = await response.json();
    if (data['odata.nextLink'] || data['@odata.nextLink'] || data.value.length>1) throw Error('Ambiguous seed key');
    let item = data.value[0];
    const created = !item;
    if (!item) {
      const saved = await fetch(route,{method:'POST',redirect:'error',signal:AbortSignal.timeout(60000),
        headers:{...headers,'Content-Type':'application/json;odata=nometadata','X-RequestDigest':digest},body:JSON.stringify(row.record)});
      if (!saved.ok) throw Error('Save status '+saved.status+'; reconcile before retry');
      item = await saved.json();
    }
    const check = await fetch(route+'('+item.Id+')',{headers,signal:AbortSignal.timeout(60000)});
    if (!check.ok) throw Error('Readback status '+check.status);
    const actual = await check.json();
    for (const [key,value] of Object.entries(row.record)) if (actual[key]!==value) throw Error('Existing seed differs; preserve human edits');
    journal.push({list:row.list,key:row.record[row.key],id:item.Id,created,verified:true});
  }
}
