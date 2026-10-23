/* Existing M365 SDK client only. No login, consent, token export, retry or redirect. */
import fs from 'node:fs/promises';
import {publish,read} from './publish.cjs';
import {connectSharePoint} from './sharepoint-client.mjs';
const [configFile,directory,journalFile]=process.argv.slice(2);
if(!configFile||!directory||!journalFile){console.error('Usage: node publish-sharepoint.mjs PRIVATE_CONFIG.json PACKAGE_DIRECTORY NEW_PRIVATE_JOURNAL.jsonl');process.exit(2);}
let journal;
try{
 const config=JSON.parse(await read(configFile,1024*1024));
 const client=await connectSharePoint(config);
 journal=await fs.open(journalFile,'wx',0o600);
 const record=async data=>{await journal.write(JSON.stringify({utc:new Date().toISOString(),...data})+'\n');await journal.sync();};
 const result=await publish(directory,client,record);console.log(JSON.stringify(result));
}catch(e){
 // Never log tokens, HTTP request headers, source bytes or SDK error objects.
 const error={event:'failed',code:e.isAxiosError?'NATIVE_REQUEST_FAILED':String(e.message),status:e.response?.status??null,reconcileBeforeRetry:true};
 if(journal){await journal.write(JSON.stringify(error)+'\n');await journal.sync();}
 console.error(JSON.stringify(error));process.exitCode=1;
}finally{if(journal)await journal.close();}
