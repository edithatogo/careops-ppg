import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {read} from '../unattended-package/publish.cjs';
import {connectSharePoint} from '../unattended-package/sharepoint-client.mjs';
import {publishSources} from './publish-sources.cjs';
const [configFile,directory,journalFile,selectedFile]=process.argv.slice(2);
if(!configFile||!directory||!journalFile||!selectedFile){console.error('Usage: node publish-sources.mjs PRIVATE_CONFIG.json PREPARATION_DIRECTORY NEW_JOURNAL.jsonl NEW_SELECTED.json');process.exit(2);}
let journal;
try{
 try{await fs.lstat(selectedFile);throw Error('SELECTED_OUTPUT_ALREADY_EXISTS');}catch(e){if(e.code!=='ENOENT')throw e;}
 const config=JSON.parse(await read(configFile,1_000_000)),client=await connectSharePoint(config);
 journal=await fs.open(journalFile,'wx',0o600);
 const record=async data=>{await journal.write(JSON.stringify({utc:new Date().toISOString(),...data})+'\n');await journal.sync();};
 const verifyDifference=async(original,native,name,policy)=>{
  if(!config.pythonExecutable||!path.isAbsolute(config.pythonExecutable))throw Error('QUALIFIED_PYTHON_EXECUTABLE_REQUIRED');
  const tmp=await fs.mkdtemp(path.join(os.tmpdir(),'ppg-source-ingestion-'));
  try{
   const before=path.join(tmp,'original.docx'),after=path.join(tmp,'native.docx');
   await fs.writeFile(before,original,{flag:'wx',mode:0o600});await fs.writeFile(after,native,{flag:'wx',mode:0o600});
   const script=fileURLToPath(new URL('../../scripts/ppg_source_preparation.py',import.meta.url));
   const p=spawnSync(config.pythonExecutable,[script,'verify-ingestion','--original',before,'--native',after,'--name',name,'--policy',policy],{encoding:'utf8',timeout:20000,maxBuffer:2_000_000});
   if(p.status!==0||p.error)throw Error('NATIVE_INGESTION_NOT_QUALIFIED');
   return JSON.parse(p.stdout);
  }finally{await fs.rm(tmp,{recursive:true,force:true});}
 };
 const result=await publishSources(directory,client,record,verifyDifference);
 await fs.writeFile(selectedFile,JSON.stringify(result.selected,null,2)+'\n',{flag:'wx',mode:0o600});
 console.log(JSON.stringify(result));
}catch(e){const error={event:'failed',code:e.isAxiosError?'NATIVE_REQUEST_FAILED':String(e.message),status:e.response?.status??null,reconcileBeforeRetry:true};
 if(journal){await journal.write(JSON.stringify(error)+'\n');await journal.sync();}console.error(JSON.stringify(error));process.exitCode=1;
}finally{if(journal)await journal.close();}
