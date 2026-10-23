/** Narrow compatibility adapter: Toolkit-style MSAL interactive login in the CLI. */
import {writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import path from 'node:path';

const cliRoot = process.env.PPG_M365_CLI_ROOT;
const urlFile = process.env.PPG_AUTH_URL_FILE;
if (!cliRoot || !path.isAbsolute(cliRoot) || !urlFile || !path.isAbsolute(urlFile)) {
  throw new Error('Set absolute PPG_M365_CLI_ROOT and PPG_AUTH_URL_FILE paths.');
}
if (process.argv[2] !== 'login' || !process.argv.includes('--appId') ||
    !process.argv.includes('--tenant') || !process.argv.includes('--connectionName') ||
    process.argv[process.argv.indexOf('--authType') + 1] !== 'browser') {
  throw new Error('Use login with explicit --appId, --tenant, --connectionName and --authType browser.');
}
const {default: auth} = await import(pathToFileURL(path.join(cliRoot, 'dist/Auth.js')));
auth.ensureAccessTokenWithBrowser = async function(resource) {
  return this.clientApplication.acquireTokenInteractive({
    scopes: [`${resource}/.default`],
    responseMode: 'form_post',
    prompt: 'select_account',
    openBrowser: async url => {
      await writeFile(urlFile, url, {mode: 0o600});
      console.error('Open the generated sign-in URL in the authorised browser.');
    }
  });
};
// Installed CLI retains ownership of its MSAL cache and named connection.
await import(pathToFileURL(path.join(cliRoot, 'dist/index.js')));
