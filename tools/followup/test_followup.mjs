// Offline only; no auth, network or workbook access.
import fs from 'node:fs';import vm from 'node:vm';import {stripTypeScriptTypes} from 'node:module';
const source=stripTypeScriptTypes(fs.readFileSync(new URL('./followup.ts',import.meta.url),'utf8'));
const api=vm.runInNewContext('(()=>{'+source+';return {plan,main};})()',{}, {timeout:5000});
process.stdout.write(JSON.stringify(JSON.parse(fs.readFileSync(0,'utf8')).map(request=>{try{return {ok:true,value:JSON.parse(api.main({},JSON.stringify(request)))}}catch(e){return {ok:false,error:e.message}}})));
