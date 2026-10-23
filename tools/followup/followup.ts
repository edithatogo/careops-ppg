// Pure Office Script. The workbook hosts execution; no cell or external calls occur.
type J = string | number | boolean | null | J[] | { [key: string]: J };
type Row = { [key: string]: J };
const scopeKeys = ['CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256'];
function obj(value: J): Row { if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Object required'); return value as Row; }
function txt(value: J): string { return typeof value === 'string' ? value : ''; }
function stable(value: J): string { if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']'; if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + stable(value[k])).join(',') + '}'; return JSON.stringify(value); }
function utc(value: J): string { const v=txt(value); if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/.test(v) || (!Number.isFinite(Date.parse(v))||new Date(v).toISOString().slice(0,19)!==v.slice(0,19))) throw new Error('UTC timestamp required'); return v; }
function day(value: J): J { if (value===null || value===undefined || value==='') return null; const v=txt(value); if (!/^\d{4}-\d{2}-\d{2}$/.test(v) || v.slice(0,4)==='0000' || new Date(v+'T00:00:00Z').toISOString().slice(0,10)!==v) throw new Error('Invalid calendar date'); return v; }
function sameScope(a: Row,b: Row): boolean { return scopeKeys.every(k => a[k]===b[k]); }
function rows(envelope: J): Row[] { const e=obj(envelope); const d=e.d ? obj(e.d):e; if(e['@odata.nextLink']||e['odata.nextLink']||d.__next) throw new Error('Incomplete native page'); const result=d.value??d.results; if (!Array.isArray(result)||result.length>=5000) throw new Error('Missing or bounded-limit native collection'); return result.map(obj); }
function normalized(data:J, map:Row):Row[] { return rows(data).map(r=>{const out:Row={ID:r.Id??r.ID,Version:r.OData__UIVersionString??r.Version,Modified:r.Modified??null,Author:r.Author?{Title:obj(r.Author).Title??null}:null,Editor:r.Editor?{Title:obj(r.Editor).Title??null}:null};Object.keys(map).forEach(k=>out[k]=r[txt(map[k])]??null);return out;}); }
function required(row:Row,names:string[]):void {if(names.some(k=>!txt(row[k]).trim()))throw new Error('Missing required value');}
function append(history:Row[],event:Row,current:Row):string {
 required(event,['EventUID',...scopeKeys,'Stage','State','OccurredOn','Actor','Rationale']);
 if(!sameScope(event,current)||!(/^[0-9a-f]{64}$/.test(txt(event.DocumentSHA256))))throw new Error('Stale document scope');
 utc(event.OccurredOn);day(event.SourceDueDate);day(event.AgreedTargetDate);
 if(event.AgreedTargetDate&&!txt(event.TargetAgreementEvidence).trim())throw new Error('Agreed target requires evidence');
 if(!['Open','Completed','Declined','Superseded'].includes(txt(event.State)))throw new Error('Invalid follow-up state');
 const repeated=history.filter(x=>x.EventUID===event.EventUID);if(repeated.length){if(repeated.length===1&&stable(repeated[0])===stable(event))return 'unchanged';throw new Error('Conflicting event identity');}
 const prior=history.filter(x=>x.CaseUID===event.CaseUID).slice(-1)[0];
 if((event.PreviousEventUID??null)!==(prior?prior.EventUID:null))throw new Error('Stale follow-up head');
 if(prior&&Date.parse(txt(event.OccurredOn))<Date.parse(txt(prior.OccurredOn)))throw new Error('Event precedes current head');return 'appended';
}
function caseIsClosed(value:J):boolean {return ['closed','completed','declined','superseded','withdrawn','review closed','review closed - fictional'].includes(txt(value).trim().toLowerCase().replace(/[—–]/g,'-').replace(/\s+/g,' '));}
function accepted(owner:Row,history:Row[],current:Row,asOf:J):boolean {
 try { if (Date.parse(utc(owner.OccurredOn))>Date.parse(utc(asOf))) return false; } catch { return false; }
 if(!sameScope(owner,current)||owner.EventKind!=='Ownership handoff'||owner.RecordState!=='Accepted'||!['None recorded','Resolved'].includes(txt(owner.ConditionsState)))return false;
 if(history.filter(x=>x.EventUID===owner.EventUID).length!==1||history.some(x=>x.SupersedesEventUID===owner.EventUID))return false;
 if(['ActorName','OccurredOn','Summary','EvidenceReference','SubjectRole','FromRole','ParentEventUID'].some(k=>!txt(owner[k]).trim()))return false;
 const parents=history.filter(x=>x.EventUID===owner.ParentEventUID);if(parents.length!==1)return false;const p=parents[0];
 return sameScope(owner,p)&&p.EventKind===owner.EventKind&&p.SubjectRole===owner.SubjectRole&&p.FromRole===owner.FromRole&&p.RecordState==='Proposed'&&!history.some(x=>x.SupersedesEventUID===p.EventUID);
}
function plan(input:Row):Row {
 const native=obj(input.native),maps=obj(input.maps);const context=normalized(native.contexts,obj(maps.contexts)),requests=normalized(native.requests,obj(maps.requests)),eventRows=normalized(native.events,obj(maps.events)),snapshots=normalized(native.digests,obj(maps.digests));
 const owners=rows(native.ownership),cases=rows(native.cases);const requestRows=requests.filter(x=>String(x.ID)===String(input.requestId));if(requestRows.length!==1)throw new Error('Unknown request');const request=requestRows[0];
 required(request,['RequestKey','Version','AsOf']);utc(request.AsOf);if(!/^[a-zA-Z0-9._:-]{1,100}$/.test(txt(request.RequestKey)))throw new Error('Use a short safe request key');
 const runKey=txt(request.RequestKey)+':v'+txt(request.Version);
 const history:Row[]=[];
 for(const row of eventRows.sort((a,b)=>Number(a.ID)-Number(b.ID))){if(row.Version!=='1.0')throw new Error('Edited history row; reconcile versions');const event=obj(JSON.parse(txt(row.EventJSON)) as J);const commits=snapshots.filter(x=>x.SnapshotKey===txt(row.RequestKey)+'|complete');if(row.RequestKey!==runKey){if(commits.length!==1||commits[0].Version!=='1.0')throw new Error('Uncompleted follow-up run; reconcile before continuing');const commit=obj(JSON.parse(txt(commits[0].PayloadJSON)) as J);if(commit.state!=='recorded_followup'||commit.eventUID!==event.EventUID||commit.scope!==event.CaseUID)throw new Error('Follow-up completion mismatch');}if(row.EventUID!==event.EventUID||row.CaseUID!==event.CaseUID||row.Stage!==event.Stage||row.FollowupState!==event.State)throw new Error('History column/payload mismatch');if(append(history,event,event)!=='appended')throw new Error('Duplicate history');history.push(event);}
 if(new Set(context.map(x=>x.CaseUID)).size!==context.length)throw new Error('Ambiguous context');
 const pins=stable({request,context,cases:cases.filter(c=>context.some(x=>x.CaseUID===c.CaseUID)).map(c=>({ID:c.Id,CaseUID:c.CaseUID,Status:c.caseStatus,Version:c.OData__UIVersionString})),owners:owners.filter(o=>context.some(x=>x.CaseUID===o.CaseUID))});
 const writes:Row[]=[];let report:Row={runKey,notificationsEnabled:false,deliveryEligible:false};
 function save(target:string,logical:Row):void {const nativeRow:Row={Title:logical.Title};const map=obj(maps[target]);Object.keys(logical).filter(k=>k!=='Title').forEach(k=>{if(!map[k])throw new Error('Unknown native output field');nativeRow[txt(map[k])]=logical[k];});const identity=target==='events'?'EventUID':'SnapshotKey';const existing=(target==='events'?eventRows:snapshots).filter(x=>x[identity]===logical[identity]);if(existing.length>1)throw new Error('Duplicate output identity');if(existing.length){if(existing[0].Version!=='1.0'||Object.keys(logical).filter(k=>k!=='Title').some(k=>stable(existing[0][k]??null)!==stable(logical[k]??null)))throw new Error('Output conflict; preserve edits');}writes.push({target,key:logical[identity],payload:nativeRow,create:existing.length===0});}
 if(request.Operation==='Record follow-up'){
  required(request,['CaseUID','ContextVersion','EventUID','Stage','FollowupState','OccurredOn','Rationale']);const selected=context.filter(x=>x.CaseUID===request.CaseUID);if(selected.length!==1)throw new Error('Unknown context');const c=selected[0];if(c.Version!==request.ContextVersion)throw new Error('Stale context version');if(cases.filter(x=>x.CaseUID===c.CaseUID).length!==1)throw new Error('Unknown case');
  const author=obj(request.Editor??request.Author);required(author,['Title']);
  const event:Row={};scopeKeys.forEach(k=>event[k]=c[k]);Object.assign(event,{EventUID:request.EventUID,PreviousEventUID:request.PreviousEventUID??null,Stage:request.Stage,State:request.FollowupState,OccurredOn:request.OccurredOn,Actor:author.Title,Rationale:request.Rationale,Priority:request.Priority??null,NextAction:request.NextAction??null,WaitingReason:request.WaitingReason??null,SourceDueDate:day(c.SourceDueDate),AgreedTargetDate:day(request.AgreedTargetDate),TargetAgreementEvidence:request.TargetAgreementEvidence??null});
  if(Date.parse(txt(event.OccurredOn))>Date.parse(txt(request.AsOf)))throw new Error('Future event');const disposition=append(history,event,c);
  save('events',{Title:'Follow-up: '+txt(c.CaseUID),EventUID:event.EventUID,PredecessorKey:txt(c.CaseUID)+'|'+(txt(event.PreviousEventUID)||'ROOT'),CaseUID:c.CaseUID,Stage:event.Stage,FollowupState:event.State,OccurredOn:event.OccurredOn,RequestKey:runKey,DocumentReference:event.DocumentReference,ReviewedVersionRef:event.ReviewedVersionRef,DocumentSHA256:event.DocumentSHA256,Actor:event.Actor,Rationale:event.Rationale,Priority:event.Priority,NextAction:event.NextAction,WaitingReason:event.WaitingReason,SourceDueDate:event.SourceDueDate,AgreedTargetDate:event.AgreedTargetDate,TargetAgreementEvidence:event.TargetAgreementEvidence,EventJSON:stable(event)});
  report={...report,state:'recorded_followup',eventUID:event.EventUID,disposition:'recorded',scope:c.CaseUID};
 }else if(request.Operation==='Preview digest'){
  const priorKey=txt(request.PreviousPreviewKey),prior=snapshots.filter(x=>x.SnapshotKey===priorKey+'|complete');let previous:Row[]=[];if(priorKey){if(prior.length!==1||prior[0].Version!=='1.0')throw new Error('Missing or edited completed previous preview');const p=obj(JSON.parse(txt(prior[0].PayloadJSON)) as J);previous=(p.candidates as J[]).map(obj);}
  const latest:Row[]=[];for(const e of history){const i=latest.findIndex(x=>x.CaseUID===e.CaseUID);if(i<0)latest.push(e);else latest[i]=e;}
  const candidates:Row[]=[],exceptions:Row[]=[],suppressed:Row[]=[];
  for(const event of latest){const c=context.find(x=>x.CaseUID===event.CaseUID);const caseRows=cases.filter(x=>x.CaseUID===event.CaseUID);let reason='';
   if(!c||!sameScope(event,c))reason='stale_or_missing_document_scope';
   else if(Date.parse(txt(event.OccurredOn))>Date.parse(txt(request.AsOf)))reason='future_event';
   else if(caseRows.length!==1)reason='unknown_or_ambiguous_case';
   else if(event.State!=='Open'||caseIsClosed(caseRows[0].caseStatus)){suppressed.push({CaseUID:event.CaseUID,reason:event.State!=='Open'?event.State:'case_closed'});continue;}
   else if(!txt(event.NextAction).trim())reason='missing_next_action';
   else {try{if(c.SourceFreshness!=='Current'||Date.parse(utc(c.SourceAsOf))>Date.parse(utc(c.SourceCheckedAt))||Date.parse(utc(c.SourceCheckedAt))>Date.parse(txt(request.AsOf)))reason='source_freshness_unconfirmed';}catch{reason='source_freshness_unknown';}}
   const ownership=c?owners.filter(o=>accepted(o,owners,c,request.AsOf)):[];
   if(!reason&&ownership.length!==1)reason='ownership_unresolved';
   if(!reason&&(!c||c.RecipientEligibility!=='Verified'||c.RecipientRole!==ownership[0].SubjectRole||!(/^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(txt(c.RecipientAddress)))||!txt(c.RecipientEvidence).trim()))reason='recipient_unresolved';
   if(reason){exceptions.push({CaseUID:event.CaseUID,reason});continue;}
   let entered=event.OccurredOn;const chain=history.filter(x=>x.CaseUID===event.CaseUID);for(let i=chain.length-2;i>=0;i--){if(chain[i].Stage!==event.Stage||!sameScope(chain[i],event))break;entered=chain[i].OccurredOn;}
   const candidate:Row={CaseUID:event.CaseUID,event,stageEnteredOn:entered,acceptedRole:ownership[0].SubjectRole,recipient:{Role:c.RecipientRole,Address:c.RecipientAddress,Eligibility:c.RecipientEligibility,EvidenceReference:c.RecipientEvidence},sourceAsOf:c.SourceAsOf,sourceCheckedAt:c.SourceCheckedAt,sourceFreshness:c.SourceFreshness};
   const fingerprint=stable(candidate);candidates.push({...candidate,fingerprint,unchangedSincePrevious:previous.some(p=>p.fingerprint===fingerprint)});
  }
  report={...report,state:'completed_digest_preview',asOf:request.AsOf,candidates,exceptions,suppressed};
  for(const [kind,items] of [['Candidate',candidates],['Exception',exceptions],['Suppressed',suppressed]] as [string,Row[]][]){for(const item of items){const e=item.event?obj(item.event):{};save('digests',{Title:kind+': '+txt(item.CaseUID),SnapshotKey:runKey+'|'+kind+'|'+txt(item.CaseUID),RunKey:runKey,RowKind:kind,CaseUID:item.CaseUID,Stage:e.Stage??null,StageEnteredOn:item.stageEnteredOn??null,Priority:e.Priority??null,AcceptedRole:item.acceptedRole??null,NextAction:e.NextAction??null,WaitingReason:e.WaitingReason??null,AgreedTargetDate:e.AgreedTargetDate??null,SourceDueDate:e.SourceDueDate??null,SourceAsOf:item.sourceAsOf??null,SourceCheckedAt:item.sourceCheckedAt??null,Reason:item.reason??(item.unchangedSincePrevious?'Unchanged since previous preview':'New or changed candidate'),PayloadJSON:stable(item)});}}
 }else throw new Error('Unknown operation');
 const complete:Row={Title:'Completed '+txt(request.Operation),SnapshotKey:runKey+'|complete',RunKey:runKey,RowKind:'Completed preview',CandidateCount:String(((report.candidates??[]) as J[]).length),ExceptionCount:String(((report.exceptions??[]) as J[]).length),SuppressedCount:String(((report.suppressed??[]) as J[]).length),PayloadJSON:stable(report)};
 // Completion marker is persisted only after output readback and source recheck.
 const before=writes.length;save('digests',complete);const completion=writes.pop();if(writes.length!==before||!completion)throw new Error('Completion plan mismatch');
 for(const w of [...writes,completion])if(stable(w.payload).length>60000)throw new Error('Output exceeds bounded native shape');
 return {runKey,sourcePins:pins,historyPins:stable(eventRows),writes,completion,report,requestVersion:request.Version};
}
function main(workbook:ExcelScript.Workbook,requestJson:string):string {
 const input=obj(JSON.parse(requestJson) as J);const result=plan(input);
 if(input.phase==='verify'){
  const original=obj(input.originalPlan);if(result.sourcePins!==original.sourcePins)throw new Error('FollowupSourceChanged');
  const native=obj(input.native),maps=obj(input.maps);const events=normalized(native.events,obj(maps.events)),digests=normalized(native.digests,obj(maps.digests));
  const newEventKeys=(original.writes as J[]).map(obj).filter(w=>w.target==='events'&&w.create===true).map(w=>w.key);if(stable(events.filter(e=>!newEventKeys.includes(e.EventUID)))!==original.historyPins)throw new Error('FollowupHistoryChanged');
  for(const w of original.writes as J[]){const write=obj(w),rows=write.target==='events'?events:digests,map=obj(maps[txt(write.target)]),key=write.target==='events'?'EventUID':'SnapshotKey',matches=rows.filter(r=>r[key]===write.key);if(matches.length!==1||matches[0].Version!=='1.0')throw new Error('Saved output missing or edited');const payload=obj(write.payload);for(const k of Object.keys(map)){if(payload[txt(map[k])]!==undefined&&stable(matches[0][k]??null)!==stable(payload[txt(map[k])]??null))throw new Error('Saved output differs');}}
  if(input.verifyCompletion===true){const completion=obj(original.completion),payload=obj(completion.payload),map=obj(maps.digests),matches=digests.filter(r=>r.SnapshotKey===completion.key);if(matches.length!==1||matches[0].Version!=='1.0'||Object.keys(map).some(k=>payload[txt(map[k])]!==undefined&&stable(matches[0][k]??null)!==stable(payload[txt(map[k])]??null)))throw new Error('Completion marker differs');}
  return JSON.stringify({verified:true,completion:original.completion,report:original.report});
 }
 return JSON.stringify(result);
}
