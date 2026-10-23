/* Qualified same-client SharePoint transport shared by the bounded CLI publishers. */
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {validateRenewalIdentity} from '../lifecycle/validate_renewal_identity.mjs';
export async function connectSharePoint(config){
 const site=new URL(config.siteUrl),folder=config.folder,expected=config.identity;
 if(site.protocol!=='https:'||!site.hostname.endsWith('.sharepoint.com')||site.username||site.password||site.search||site.hash||site.pathname.endsWith('/')||
    !/^\/teams\/[^/]+$|^\/sites\/[^/]+$/.test(site.pathname)||typeof folder!=='string'||
    !folder.startsWith(site.pathname+'/')||/[\x00-\x1f?#%\\]/.test(folder)||folder.split('/').some(p=>p==='.'||p==='..')||
    !expected?.username||!expected?.tenantId||!expected?.appId||!expected?.objectId||!config.connectionName)throw Error('EXACT_PRIVATE_BINDING_REQUIRED');
 const sdk=path.resolve(config.sdkDirectory);
 const [{default:auth},{default:request}]=await Promise.all(['Auth.js','request.js'].map(f=>import(pathToFileURL(path.join(sdk,f)))));
 request.logger={log:async()=>{},logToStderr:async()=>{}};request.debug=false;
 await auth.restoreAuth();
 if(auth.connection.name!==config.connectionName||auth.connection.appId!==expected.appId||auth.connection.tenant!==expected.tenantId)throw Error('SAVED_CLIENT_MISMATCH');
 const app=await auth.getPublicClient(request.logger,false),accounts=await app.getTokenCache().getAllAccounts();
 const matches=accounts.filter(a=>a.localAccountId?.toLowerCase()===expected.objectId.toLowerCase()&&a.tenantId?.toLowerCase()===expected.tenantId.toLowerCase()&&a.username?.toLowerCase()===expected.username.toLowerCase());
 if(matches.length!==1)throw Error('UNIQUE_SAVED_ACCOUNT_REQUIRED');
 const token=await app.acquireTokenSilent({account:matches[0],scopes:[site.origin+'/.default'],forceRefresh:false});
 validateRenewalIdentity(token,expected);
 if(!token.accessToken||new Date(token.expiresOn).getTime()<Date.now()+60000)throw Error('UNEXPIRED_SAME_CLIENT_TOKEN_REQUIRED');
 const arg=s=>encodeURIComponent(s.replaceAll("'","''")).replaceAll("'",'%27');
 const base=site.href+'/_api/web/';
 async function requestOnce(method,url,extra={}){
  // Direct Axios instance avoids the CLI request.execute retry policy.
  return request.req.request({method,url,headers:{Authorization:'Bearer '+token.accessToken,Accept:'application/json;odata=nometadata',...(extra.data?{'Content-Type':'application/octet-stream'}:{})},
   family:4,maxRedirects:0,timeout:60000,signal:AbortSignal.timeout(60000),responseType:'arraybuffer',maxContentLength:128*1024*1024,maxBodyLength:128*1024*1024,...extra});
 }
 const folderEndpoint=base+"GetFolderByServerRelativePath(decodedurl='"+arg(folder)+"')";
 // Existing destination only: no folder, schema or permission creation.
 await requestOnce('GET',folderEndpoint+'?$select=ServerRelativeUrl');
 const client={
  async get(name){
   const endpoint=base+"GetFileByServerRelativePath(decodedurl='"+arg(folder+'/'+name)+"')";
   let a;try{a=await requestOnce('GET',endpoint+'?$select=UniqueId,ETag,UIVersionLabel,Length,ServerRelativeUrl');}
   catch(e){if(e.response?.status===404)return null;throw e;}
   const before=JSON.parse(Buffer.from(a.data).toString('utf8'));
   if(before.ServerRelativeUrl!==folder+'/'+name||!Number.isSafeInteger(Number(before.Length))||Number(before.Length)<0||Number(before.Length)>128*1024*1024)throw Error('NATIVE_FILE_BINDING_INVALID');
   const bytes=Buffer.from((await requestOnce('GET',endpoint+'/$value')).data);
   const after=JSON.parse(Buffer.from((await requestOnce('GET',endpoint+'?$select=UniqueId,ETag,UIVersionLabel,Length,ServerRelativeUrl')).data).toString('utf8'));
   const pin=x=>({UniqueId:x.UniqueId,ETag:x.ETag,UIVersionLabel:x.UIVersionLabel,Length:String(x.Length),ServerRelativeUrl:x.ServerRelativeUrl});
   if(!before.UniqueId||!before.ETag||!before.UIVersionLabel||JSON.stringify(pin(before))!==JSON.stringify(pin(after))||bytes.length!==Number(after.Length))throw Error('NATIVE_READ_NOT_STABLE');
   return {bytes,pin:pin(after)};
  },
  async create(name,bytes){await requestOnce('POST',folderEndpoint+"/Files/AddUsingPath(decodedurl='"+arg(name)+"',overwrite=false)",{data:bytes});}
 };
 return client;
}
