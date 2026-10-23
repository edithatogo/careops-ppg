// Offline parity harness only. No authentication, network or workbook access.
import fs from 'node:fs';
import vm from 'node:vm';
import { stripTypeScriptTypes } from 'node:module';
const source = stripTypeScriptTypes(fs.readFileSync(new URL('./role_projection.ts', import.meta.url), 'utf8'));
const api = vm.runInNewContext('(()=>{' + source + ';return {projectModel,fromNative,main};})()', {}, {timeout:5000});
const requests = JSON.parse(fs.readFileSync(0,'utf8'));
const results = requests.map(input => {
  try { return {ok:true, value: input.operation === 'main' ? JSON.parse(api.main({},JSON.stringify(input.request))) : input.native ? api.projectModel(api.fromNative(input.native),input.asOf) : api.projectModel(input.model,input.asOf)}; }
  catch { return {ok:false}; }
});
process.stdout.write(JSON.stringify(results));
