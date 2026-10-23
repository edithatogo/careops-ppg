import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_lifecycle_package_selection import reconcile, reconcile_initiated

class SelectionTests(unittest.TestCase):
 def fixture(self):
  uid='LC-FICTIONAL-selected';raw=b'fictional read-only candidate';h=hashlib.sha256(raw).hexdigest();ref='https://example.sharepoint.com/candidate.docx'
  scope={'CaseUID':uid,'DocumentReference':'https://example.sharepoint.com/source.txt','ReviewedVersionRef':'source-v1','DocumentSHA256':'a'*64}
  case={'CaseUID':uid,'evidenceDraftLink':ref,'linkedDocumentUIDs':json.dumps(['FICTIONAL-source']),'OData__UIVersionString':'5.0'}
  request={'request':{**scope,'qualificationOnly':True,'realPolicyEffects':False,'occurrenceReference':'fictional-occurrence','DocumentUID':'FICTIONAL-source'}}
  file={'DocumentReference':ref,'UniqueId':'fictional-id','ETag':'"2"','nativeVersion':'2.0','SHA256':h}
  prepared={'CaseUID':uid,'occurrenceReference':'fictional-occurrence','file':file,'originalSourceScope':scope}
  pin={'UniqueId':'fictional-id','ETag':'"2"','UIVersionLabel':'2.0'}
  row={'CaseUID':uid,'FictionalTest':True,'DocumentReference':ref,'ReviewedVersionRef':'sharepoint:fictional-id:"2"','DocumentSHA256':h}
  old={**row,'DocumentReference':'https://example.sharepoint.com/old.docx'}
  events={'readiness':{'value':[row,old]}}
  return [case,request,prepared,pin,raw,events]
 def test_exact_revision_only_and_no_next_occurrence_inheritance(self):
  args=self.fixture();r=reconcile(*args)
  self.assertEqual(len(r['includedEvents']['readiness']),1);self.assertEqual(len(r['otherRevisionEvents']['readiness']),1)
  self.assertFalse(r['currentPolicyClaim']);self.assertFalse(r['nextOccurrenceFindingsInherited']);self.assertFalse(r['caseWrites'])
 def test_drift_and_cross_occurrence_refused(self):
  for mutate in [lambda x:x[0].update(CaseUID='LC-FICTIONAL-next'),lambda x:x[3].update(ETag='"3"'),lambda x:x[5]['readiness']['value'][0].update(CaseUID='LC-FICTIONAL-next'),lambda x:x[5]['readiness'].update({'odata.nextLink':'unread-page'}),lambda x:x[1]['request'].update(qualificationOnly=False)]:
   args=copy.deepcopy(self.fixture());mutate(args)
   with self.assertRaises(ValueError):reconcile(*args)
 def test_initiated_case_uses_no_predecessor_findings(self):
  case,request,_,_,raw,_=self.fixture();pin={'UniqueId':'fictional-source','ETag':'"1"'}
  r=request['request'];r['ReviewedVersionRef']='sharepoint:fictional-source:"1"';r['DocumentSHA256']=hashlib.sha256(raw).hexdigest();r['completedReview']={'Finding':'must never inherit this finding'}
  case.update(caseStatus='Initiated — FICTIONAL',evidenceDraftLink=r['DocumentReference'])
  events={k:{'value':[]}for k in ['assurance','consultation','readiness']}
  result=reconcile_initiated(case,request,pin,raw,events)
  self.assertEqual(result['includedEvents'],{});self.assertFalse(result['reviewFindingsRecorded']);self.assertFalse(result['ownershipAcceptanceRecorded']);self.assertNotIn('must never inherit',json.dumps(result))
  events['readiness']['value']=[{'CaseUID':'predecessor'}]
  with self.assertRaisesRegex(ValueError,'new_occurrence_has_events'):reconcile_initiated(case,request,pin,raw,events)

if __name__=='__main__':unittest.main()
