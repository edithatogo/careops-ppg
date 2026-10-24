/* External-publication rows: inject a qualified, exactly-once native transport. */
import {createHash} from 'node:crypto';
export const fields = ['Title','RecordKey','RecordKind','PublicationKey','EditionKey','Issuer',
 'SourceStatus','SourceRole','TrancheKey','RecordJSON','PayloadSHA256','ReviewState','OfficialURL','EvidenceURL','RelatedRecordsURL'];
export function checkRows(rows,site) {
 if (!Array.isArray(rows) || !rows.length || new Set(rows.map(r=>r.RecordKey)).size!==rows.length) throw Error('UNIQUE_NONEMPTY_RECORDS_REQUIRED');
 for (const row of rows) {
  if (Object.keys(row).some(k=>!fields.includes(k)) || fields.some(k=>!(k in row)) ||
      row.ReviewState!=='Proposed' || !/^[a-z0-9][a-z0-9:._-]{0,199}$/.test(row.RecordKey) ||
      !/^[a-f0-9]{64}$/.test(row.PayloadSHA256)) throw Error('INVALID_EXTERNAL_PAYLOAD');
  const record=JSON.parse(row.RecordJSON);
  if (record.key!==row.RecordKey || record.kind!==row.RecordKind ||
      !['Publication','Edition','Capture','Reference','Resolution','Collection'].includes(record.kind) ||
      record.data?.clinicalApplicabilityAccepted===true ||
      createHash('sha256').update(row.RecordJSON).digest('hex')!==row.PayloadSHA256) throw Error('PAYLOAD_IDENTITY_DRIFT');
  const official=new URL(row.OfficialURL);
  if(official.protocol!=='https:'||official.hostname!=='www.safetyandquality.gov.au'||official.username||official.password)throw Error('OFFICIAL_SOURCE_URL_REQUIRED');
  for(const key of ['EvidenceURL','RelatedRecordsURL']){
   if(row[key]===null)continue;
   const target=new URL(row[key]);
   if(target.protocol!=='https:'||!target.hostname.endsWith('.sharepoint.com')||target.username||target.password||target.hash)throw Error('STABLE_NATIVE_LINK_REQUIRED');
   if(site){const bound=new URL(site);if(target.origin!==bound.origin||!target.pathname.startsWith(bound.pathname+'/'))throw Error('BOUND_NATIVE_LINK_REQUIRED');}
   if(key==='EvidenceURL'&&target.search)throw Error('STABLE_NATIVE_LINK_REQUIRED');
   if(key==='RelatedRecordsURL'&&(!target.pathname.includes('/Lists/')||!target.pathname.endsWith('.aspx')||target.searchParams.get('FilterField1')!=='PublicationKey'||target.searchParams.get('FilterValue1')!==row.PublicationKey||[...target.searchParams].length!==2))throw Error('EXACT_PUBLICATION_NAVIGATION_REQUIRED');
  }
 }
}
export function difference(rows,existing,site) {
 checkRows(rows,site);
 if (new Set(existing.map(r=>r.RecordKey)).size!==existing.length) throw Error('AMBIGUOUS_NATIVE_KEYS');
 const index=new Map(existing.map(r=>[r.RecordKey,r]));
 // Validate the complete difference before creating the first item.
 const pending=[];
 for (const row of rows) {
  const old=index.get(row.RecordKey);
  if (!old) pending.push(row);
  else if (fields.some(k=>(old[k]??null)!==(row[k]??null))) throw Error('PRESERVE_CHANGED_NATIVE_RECORD');
 }
 return {expected:rows.length,pending,preserved:rows.length-pending.length};
}
export async function persist({rows,read,readOne,create,journal,site}) {
 const {pending,preserved}=difference(rows,await read(),site);
 await journal({phase:'difference-verified',expected:rows.length,pending:pending.map(r=>r.RecordKey),preserved});
 let created=0;
 for (const row of pending) {
  await journal({phase:'intent',key:row.RecordKey,hash:row.PayloadSHA256});
  await create(row); // No mutation retry. Uncertain effects require a new read/reconcile.
  const actual=(readOne?await readOne(row.RecordKey):await read()).filter(r=>r.RecordKey===row.RecordKey);
  if (actual.length!==1 || fields.some(k=>(actual[0][k]??null)!==(row[k]??null))) throw Error('NATIVE_READBACK_MISMATCH');
  await journal({phase:'verified',key:row.RecordKey,id:actual[0].Id,hash:row.PayloadSHA256});
  created++;
 }
 return {expected:rows.length,created,preserved:rows.length-pending.length};
}
