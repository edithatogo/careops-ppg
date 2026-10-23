import fs from 'node:fs';import vm from 'node:vm';import {stripTypeScriptTypes} from 'node:module';
const source=stripTypeScriptTypes(fs.readFileSync(new URL('./standards_context.ts',import.meta.url),'utf8'));
const api=vm.runInNewContext('(()=>{'+source+';return {validateCurrent,main};})()',{}, {timeout:5000});
const inputs=JSON.parse(fs.readFileSync(0,'utf8'));const out=inputs.map(r=>{try{return {ok:true,value:api.validateCurrent(r.native,r.documentUID,r.documentVersion)};}catch{return {ok:false};}});process.stdout.write(JSON.stringify(out));
