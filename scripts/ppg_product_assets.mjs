/* Create-only maintained assets; differing existing bytes are never overwritten. */
import fs from'node:fs';import{spawnSync}from'node:child_process';import path from'node:path';import{createHash}from'node:crypto';import{pathToFileURL,fileURLToPath}from'node:url';
const sha=b=>createHash('sha256').update(b).digest('hex'),q=s=>s.replaceAll("'","''");
export async function installAssets(c,folder,directory,manifest){
 if(!folder.startsWith('/')||folder.includes('..'))throw Error('BOUND_LIBRARY_REQUIRED');
 const existing=await c.all("GetFolderByServerRelativePath(decodedurl='"+q(folder)+"')/Files?$select=Name,ServerRelativeUrl");let created=0;const stamped=[];
 for(const a of manifest.assets){if(!/^[A-Za-z0-9_.-]+$/.test(a.name))throw Error('ASSET_NAME');const bytes=fs.readFileSync(path.join(directory,a.name));if(sha(bytes)!==a.sha256)throw Error('ASSET_HASH');
  const file="GetFileByServerRelativePath(decodedurl='"+q(folder+'/'+a.name)+"')/$value";
  if(!existing.some(x=>x.Name===a.name)){await c.authorizeFiles(folder);await c.send({key:'asset-'+sha(Buffer.from(a.name)).slice(0,20),route:"GetFolderByServerRelativePath(decodedurl='"+q(folder)+"')/Files/AddUsingPath(decodedurl='"+q(a.name)+"',overwrite=false)",payload:bytes,payloadSHA256:a.sha256});created++;}
  const native=await c.get(file,true);if(sha(native)!==a.sha256){
   if(!a.name.endsWith('.docx'))throw Error('NATIVE_ASSET_DIFFERS_'+a.name);
   const r=spawnSync(fileURLToPath(new URL('../.venv/bin/python',import.meta.url)),[fileURLToPath(new URL('./ppg_template_integrity.py',import.meta.url))],{input:JSON.stringify({source:bytes.toString('base64'),native:native.toString('base64')}),encoding:'utf8',timeout:10000});
   if(r.error||r.status!==0)throw Error('NATIVE_WORD_CONTENT_DIFFERS_'+a.name);stamped.push({name:a.name,...JSON.parse(r.stdout)});
  }
 }
 return{assets:manifest.assets.length,created,byteExactAssets:manifest.assets.length-stamped.length,stamped};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){const a=process.argv.slice(2),v=k=>a[a.indexOf(k)+1];for(const k of ['--adapter','--folder','--assets','--receipt'])if(!a.includes(k))throw Error(k+' required');const adapter=path.resolve(v('--adapter')),receipt=path.resolve(v('--receipt'));if(!adapter.split(path.sep).includes('.local')||!receipt.split(path.sep).includes('.local')||fs.existsSync(receipt))throw Error('PRIVATE_NEW_RECEIPT_REQUIRED');const c=await(await import(pathToFileURL(adapter))).connect();const r=await installAssets(c,v('--folder'),v('--assets'),JSON.parse(fs.readFileSync(path.join(v('--assets'),'assets.json'))));fs.writeFileSync(receipt,JSON.stringify(r),{flag:'wx',mode:0o600});console.log(r);}
