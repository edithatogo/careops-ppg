const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const adapter=path.resolve(__dirname,'../tools/autofill/cli-msal.mjs');
test('requires explicit private paths and authentication arguments',()=>{
 const env={...process.env};delete env.PPG_M365_CLI_ROOT;delete env.PPG_AUTH_URL_FILE;
 const r=spawnSync(process.execPath,[adapter],{env,encoding:'utf8'});
 assert.notEqual(r.status,0);assert.match(r.stderr,/absolute/);
});
test('uses CLI-owned MSAL interactive PKCE API, resource scope and form_post',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'ppg-autofill-auth-'));
 try {
  fs.mkdirSync(path.join(root,'dist'));fs.writeFileSync(path.join(root,'package.json'),'{"type":"module"}');
  fs.writeFileSync(path.join(root,'dist/Auth.js'),`export default {clientApplication:{async acquireTokenInteractive(options){console.log(JSON.stringify({scopes:options.scopes,responseMode:options.responseMode,prompt:options.prompt}));await options.openBrowser('https://login.microsoftonline.com/fictional');return {fixture:true};}}};`);
  fs.writeFileSync(path.join(root,'dist/index.js'),`import auth from './Auth.js'; await auth.ensureAccessTokenWithBrowser('https://example.sharepoint.com');`);
  const urlFile=path.join(root,'url.txt');
  const r=spawnSync(process.execPath,[adapter,'login','--appId','fictional-app','--tenant','fictional-tenant','--connectionName','fixture','--authType','browser'],{encoding:'utf8',env:{...process.env,PPG_M365_CLI_ROOT:root,PPG_AUTH_URL_FILE:urlFile}});
  assert.equal(r.status,0,r.stderr);
  assert.deepEqual(JSON.parse(r.stdout),{scopes:['https://example.sharepoint.com/.default'],responseMode:'form_post',prompt:'select_account'});
  assert.equal(fs.readFileSync(urlFile,'utf8'),'https://login.microsoftonline.com/fictional');
  assert.equal(fs.statSync(urlFile).mode & 0o777,0o600);
 }finally {fs.rmSync(root,{recursive:true,force:true});}
});
