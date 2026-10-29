import {test} from 'node:test';
import assert from 'node:assert/strict';
import {decideOrderedHistory, matchesSourceHistories} from '../tools/accreditation/ordered-history-state.mjs';

test('source history comparison ignores only volatile OData and deferred URIs',()=>{
  const captured=[{VersionLabel:'1.0',Title:'Human',__metadata:{id:'one',uri:'one',type:'Version'},Author:{__deferred:{uri:'one'}}}];
  const fresh=structuredClone(captured);fresh[0].__metadata.id='two';fresh[0].__metadata.uri='two';fresh[0].Author.__deferred.uri='two';
  assert.equal(matchesSourceHistories(fresh,captured),true);
  fresh[0].Title='Changed';assert.equal(matchesSourceHistories(fresh,captured),false);
  fresh[0].Title='Human';fresh[0].__metadata.type='Changed';assert.equal(matchesSourceHistories(fresh,captured),false);
  assert.equal(matchesSourceHistories([captured[0],captured[0]],captured),false);
});

function fixture() {
  const firstValues={RequirementKey:'r',Title:'human text',SourceCaptureLink:null,RecoveryCopyURI:null};
  const currentValues={...firstValues,SourceCaptureLink:{Url:'https://example.test/copy#page=1',Description:'page'},RecoveryCopyURI:{Url:'https://example.test/copy',Description:'copy'}};
  const plan={key:'r',firstValues,currentValues};
  const first={...structuredClone(firstValues),VersionLabel:'1.0',IsCurrentVersion:true},second={...structuredClone(currentValues),VersionLabel:'2.0',IsCurrentVersion:true};
  const row={...structuredClone(firstValues),Id:7,OData__UIVersionString:'1.0',__metadata:{etag:'"2"'}};
  return {plan,first,second,row};
}

test('only absent, exact first version, and exact two-version states progress',()=>{
  const x=fixture();assert.deepEqual(decideOrderedHistory(null,[],x.plan),{action:'create'});
  assert.deepEqual(decideOrderedHistory(x.row,[x.first],x.plan),{action:'update',id:7,etag:'"2"'});
  const current={...structuredClone(x.plan.currentValues),Id:7,OData__UIVersionString:'2.0'};
  assert.deepEqual(decideOrderedHistory(current,[{...x.first,IsCurrentVersion:false},x.second],x.plan),{action:'noop',id:7});
});

test('conflicts, missing history, null substitutions and unsafe etags stop',()=>{
  const x=fixture();assert.throws(()=>decideOrderedHistory(null,[x.first],x.plan));
  assert.throws(()=>decideOrderedHistory({...x.row,__metadata:{etag:'*'}},[x.first],x.plan),/ETAG/);
  assert.throws(()=>decideOrderedHistory({...x.row,Title:'human change'},[x.first],x.plan));
  assert.throws(()=>decideOrderedHistory(x.row,[{...x.first,SourceCaptureLink:{}}],x.plan));
  assert.throws(()=>decideOrderedHistory(x.row,[x.first,x.first],x.plan));
  const current={...structuredClone(x.plan.currentValues),Id:7,OData__UIVersionString:'2.0'};
  assert.throws(()=>decideOrderedHistory(current,[x.second],x.plan));
});
