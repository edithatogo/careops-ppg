/** Same-origin SharePoint register provisioning; supply the existing site path.
 * No auth/token export, retries, ACL edits, source writes or existing schema repairs.
 * Run through a qualified same-site browser/CLI transport and retain its journal.
 */
async function provisionReviewRegisters(sitePath, registers, journal) {
  if (!/^\/teams\/[A-Za-z0-9_-]+$/.test(sitePath)) throw Error('Unsupported site path');
  const base = sitePath + '/_api';
  const headers = {Accept: 'application/json;odata=nometadata'};
  async function read(path) {
    const response = await fetch(base + path, {headers, signal: AbortSignal.timeout(20000)});
    if (!response.ok) throw Error('Read status ' + response.status);
    const value = await response.json();
    if (value['odata.nextLink'] || value['@odata.nextLink'] || value.__next)
      throw Error('Paged inventory requires reconciliation before provisioning');
    return value;
  }
  const context = await fetch(base + '/contextinfo', {method:'POST', headers});
  if (!context.ok) throw Error('Context status ' + context.status);
  const digest = (await context.json()).FormDigestValue;
  async function write(path, payload) {
    const response = await fetch(base + path, {method:'POST', redirect:'error',
      headers:{...headers, 'Content-Type':'application/json;odata=nometadata', 'X-RequestDigest':digest},
      body:JSON.stringify(payload), signal:AbortSignal.timeout(20000)});
    if (!response.ok) throw Error('Write status ' + response.status + '; reconcile before rerun');
    return response.json();
  }
  const available = (await read('/web/lists?$select=Id,Title,EnableVersioning')).value;
  for (const register of registers) {
    if (!/^PPG [A-Za-z ]+$/.test(register.title)) throw Error('Unqualified register title');
    let matches = available.filter(x=>x.Title===register.title);
    if (matches.length>1) throw Error('Ambiguous register');
    const created = !matches.length;
    const list = created ? await write('/web/lists', {Title:register.title,
      Description:register.description, BaseTemplate:100, EnableVersioning:true}) : matches[0];
    journal.push({operation:'list', title:register.title, id:list.Id, created});
    if (!list.EnableVersioning) throw Error('Versioning drift');
    const route = "/web/lists(guid'" + list.Id + "')";
    const existing = (await read(route+'/fields?$select=InternalName,StaticName,TypeAsString,Required,SchemaXml')).value;
    for (const field of register.fields) {
      matches = existing.filter(f=>f.StaticName===field.name);
      if (matches.length>1) throw Error('Ambiguous field');
      if (!matches.length) {
        await write(route+'/fields/createfieldasxml', {parameters:{SchemaXml:field.schemaXml,Options:8}});
        journal.push({operation:'field',title:register.title,name:field.name,created:true});
      }
    }
    const fields = (await read(route+'/fields?$select=InternalName,StaticName,TypeAsString,Required,SchemaXml')).value;
    const binding = {};
    for (const field of register.fields) {
      const found = fields.filter(f=>f.StaticName===field.name);
      if (found.length!==1 || found[0].TypeAsString!==field.type || found[0].Required!==field.required)
        throw Error('Field readback drift');
      if (field.unique && !found[0].SchemaXml.includes('EnforceUniqueValues="TRUE"')) throw Error('Unique key missing');
      const validationParser = new DOMParser();
      const expectedValidation = validationParser.parseFromString(field.schemaXml, 'application/xml').querySelector('Validation');
      if (field.validationFormula && (!expectedValidation ||
          expectedValidation.textContent !== field.validationFormula ||
          expectedValidation.getAttribute('Message') !== field.validationMessage))
        throw Error('Inconsistent validation definition');
      if (expectedValidation) {
        const actualValidation = validationParser.parseFromString(found[0].SchemaXml, 'application/xml').querySelector('Validation');
        const expectedFormula = expectedValidation.textContent.replaceAll('['+field.name+']', found[0].InternalName);
        const actualFormula = actualValidation?.textContent.replaceAll('['+found[0].InternalName+']', found[0].InternalName);
        if (!actualValidation || actualFormula !== expectedFormula ||
            actualValidation.getAttribute('Message') !== expectedValidation.getAttribute('Message'))
          throw Error('Field validation drift');
      }
      if (field.type === 'Choice') {
        const parser = new DOMParser();
        const expected = parser.parseFromString(field.schemaXml, 'application/xml');
        const actual = parser.parseFromString(found[0].SchemaXml, 'application/xml');
        const choices = xml => [...xml.querySelectorAll('CHOICE')].map(x=>x.textContent);
        if (JSON.stringify(choices(expected)) !== JSON.stringify(choices(actual)) ||
            expected.querySelector('Default')?.textContent !== actual.querySelector('Default')?.textContent)
          throw Error('Choice/default drift');
      }
      binding[field.name]=found[0].InternalName;
    }
    journal.push({operation:'verified',title:register.title,id:list.Id,fields:binding});
  }
  return journal;
}
