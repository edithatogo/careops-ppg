"""Offline source/binding/refusal checks, with no native credentials or writes."""
import copy
import base64
import hashlib
import json
import re
import unittest

from scripts.ppg_cloud_observation import build,validate,API,PINS
from scripts.ppg_integrated_acquisition import build as build_integrated
from tests.test_integrated_acquisition import runtime
from tests.test_url_acquisition_qualification import profile,nodes


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def fixture():
    p=profile();r=runtime();site='https://example.sharepoint.com/sites/Fictional'
    folder='/sites/Fictional/Evidence/SourceReceipts'
    binding={'publicationKey':'pub:fictional','editionKey':'edition:fictional','captureKey':'capture:fictional',
             'requestedSourceURL':p['sourceURL'],'sha256':p['expectedSHA256']}
    key=hashlib.sha256(canonical(binding).encode()).hexdigest()
    records=[]
    for index,name in enumerate(('publicationKey','editionKey','captureKey')):
        text=canonical({'key':binding[name],'title':'Fictional café source'})
        records.append({'key':binding[name],'listId':'11111111-2222-4333-8444-555555555555',
                        'itemId':index+1,'recordJSON':text,'payloadSHA256':hashlib.sha256(text.encode()).hexdigest(),
                        'reviewState':'Unreviewed'})
    original_url=site+'/Evidence/retained.pdf'
    claim={'kind':'ppg-source-capture-replay-claim-v1','replayKey':key,'binding':binding,
           'selectedRecordSHA256':{row['key']:row['payloadSHA256'] for row in records},
           'existingRetainedOriginalURL':original_url,'catalogueSourceURL':p['sourceURL'],
           'publicationPromotionPerformed':False,'fullAcquisitionQualified':False}
    claim_text=canonical(claim);claim_name='source-replay-'+key+'.json'
    def pin(uid,path,length):return {'UniqueId':uid,'ETag':'"fictional,1"','Length':str(length),
                                   'UIVersionLabel':'1.0','ServerRelativeUrl':path}
    b={'site':site,'folder':folder,'connectionReference':{'id':API,'connectionName':'fictional-sharepoint','source':'Embedded'},
       'replayKey':key,'binding':binding,'retainedOriginalURL':original_url,
       'originalPin':pin('22222222-2222-4333-8444-555555555555','/sites/Fictional/Evidence/retained.pdf',p['expectedBytes']),
       'sourceMetadata':{'Id':'fictional-stage-id','ETag':'"fictional,1"','Size':p['expectedBytes'],'IsFolder':False},
       'sourceFile':{'uniqueId':'33333333-2222-4333-8444-555555555555','nativeVersion':'1.0','etag':'"fictional,1"',
                     'url':site+'/Staging/source.pdf','bytes':p['expectedBytes']},
       'records':records,'claimName':claim_name,'claimJSON':claim_text,
       'claimPin':pin('44444444-2222-4333-8444-555555555555',folder+'/'+claim_name,len(claim_text.encode())),
       'scriptPath':'/Fictional runtime/hash.osts','scriptMetadata':{'ETag':'"fictional-script,1"','Size':123,'IsFolder':False,'Name':'hash.osts'},
       'resumeRunIdDefault':''}
    return p,r,b


def persistence_actions(flow):
    return flow['properties']['definition']['actions']['Select_fixed_source']['actions']['Require_ready']['actions']['Require_expected_metadata']['actions']['Require_stable_metadata']['actions']['Require_integrated_integrity']['actions']


def evaluate(expression,bodies,outputs):
    """Test-only emitted predicate subset; no native transport or auth paths."""
    tokens=re.findall(r"'(?:[^']|'')*'|\?\[|[A-Za-z_][A-Za-z_0-9]*|-?\d+|[(),\]]",expression[1:]);index=0
    def parse():
        nonlocal index
        token=tokens[index];index+=1
        if token.startswith("'"):node=('literal',token[1:-1].replace("''","'"))
        elif re.fullmatch('-?\\d+',token):node=('literal',int(token))
        elif token in ('true','false','null'):node=('literal',{'true':True,'false':False,'null':None}[token])
        else:
            assert tokens[index]=='(';index+=1;args=[]
            while tokens[index]!=')':
                args.append(parse())
                if tokens[index]!=')':assert tokens[index]==',';index+=1
            index+=1;node=('call',token,args)
        while index<len(tokens) and tokens[index]=='?[':
            index+=1;key=parse();assert tokens[index]==']';index+=1;node=('get',node,key)
        return node
    tree=parse();assert index==len(tokens),tokens[index:]
    def run(node):
        if node[0]=='literal':return node[1]
        if node[0]=='get':
            value=run(node[1]);return value.get(run(node[2])) if isinstance(value,dict) else None
        name,args=node[1:]
        if name=='if':return run(args[1] if run(args[0]) else args[2])
        values=[run(a) for a in args]
        def text(v):return json.dumps(v,separators=(',',':'),ensure_ascii=False) if isinstance(v,(dict,list,bool)) else str(v)
        functions={'body':bodies.get,'outputs':outputs.get,'equals':lambda a,b:type(a)==type(b) and a==b,
                   'and':lambda *v:all(v),'or':lambda *v:any(v),'not':lambda v:not v,
                   'string':text,'int':int,'length':len,'empty':lambda v:v in (None,'',[],{}),
                   'concat':lambda *v:''.join(v),'base64':lambda v:base64.b64encode(v.encode()).decode(),
                   'base64ToString':lambda v:base64.b64decode(v).decode(),'json':json.loads,
                   'sub':lambda a,b:a-b,'div':lambda a,b:a//b,'mul':lambda a,b:a*b,
                   'endsWith':lambda a,b:a.endswith(b),'utcNow':lambda:'2026-10-24T12:00:00Z'}
        return functions[name](*values)
    return run(tree)


class CloudObservation(unittest.TestCase):
    def test_emitted_context_guard_accepts_exact_native_values_and_holds_changes(self):
        p,r,b=fixture();a=persistence_actions(build(p,r,b));bodies={}
        for index,row in enumerate(b['records']):
            bodies['Read_record_before_write_'+str(index)]={field:row[key] for field,key in [('RecordKey','key'),('RecordJSON','recordJSON'),('PayloadSHA256','payloadSHA256'),('ReviewState','reviewState')]}
        bodies['Read_original_before_write']=b['originalPin'];bodies['Read_claim_pin_before_write']=b['claimPin'];bodies['Read_stage_before_write']=b['sourceMetadata'];bodies['Read_engine_before_write']=b['scriptMetadata']
        expr=a['Require_context_before_write']['expression'];self.assertTrue(evaluate(expr,bodies,{}))
        for name,field in [('Read_record_before_write_0','ReviewState'),('Read_record_before_write_1','RecordJSON'),('Read_original_before_write','ETag'),('Read_claim_pin_before_write','UniqueId'),('Read_stage_before_write','Id'),('Read_engine_before_write','ETag')]:
            changed=copy.deepcopy(bodies);changed[name][field]='changed'
            with self.subTest(name=name,field=field):self.assertFalse(evaluate(expr,changed,{}))

    def test_emitted_resume_guard_refuses_missing_prior_receipt_and_unknown_read_errors(self):
        p,r,b=fixture();a=persistence_actions(build(p,r,b));expr=a['Require_observation_readable']['expression']
        for status,resume,expected in [(200,'earlier',True),(404,'',True),(404,'earlier',False),(403,'',False),(500,'',False)]:
            self.assertIs(evaluate(expr,{}, {'Read_observation_before':{'statusCode':status},'Observation_resume_input':resume}),expected)
        expr=a['Expected_observation']['inputs']['observedAtUtc']
        self.assertEqual(evaluate(expr,{}, {'Read_observation_before':{'statusCode':404}}),'2026-10-24T12:00:00Z')

    def test_emitted_final_guard_checks_utf8_byte_length_padding_and_stable_pins(self):
        p,r,b=fixture();a=persistence_actions(build(p,r,b));expr=a['Require_saved_observation']['expression']
        for text in ('café','é😃','a','ab','abc'):
            record={'observedAtUtc':'2026-10-24T00:00:00Z','note':text};raw=json.dumps(record,separators=(',',':'),ensure_ascii=False).encode()
            pin={'UniqueId':'fictional','ETag':'"fictional,1"','Length':str(len(raw)),'UIVersionLabel':'1.0','ServerRelativeUrl':b['folder']+'/source-native-run-Fictional.json'}
            bodies={'Read_saved_observation_content':{'$content':base64.b64encode(raw).decode()},'Read_saved_observation_pin':copy.deepcopy(pin),'Read_saved_observation_after':copy.deepcopy(pin)}
            outputs={'Expected_observation':record,'Observation_filename':'source-native-run-Fictional.json','Read_observation_before':{'statusCode':404}}
            self.assertTrue(evaluate(expr,bodies,outputs))
            for field in ('Length','ETag','UniqueId','UIVersionLabel'):
                changed=copy.deepcopy(bodies);changed['Read_saved_observation_after'][field]='2' if field=='Length' else 'changed'
                with self.subTest(text=text,field=field):self.assertFalse(evaluate(expr,changed,outputs))

    def test_existing_transport_hash_and_inputs_preserved_with_one_create_only_endpoint(self):
        p,r,b=fixture();before=copy.deepcopy((p,r,b));flow=build(p,r,b)
        self.assertEqual((p,r,b),before);self.assertEqual(validate(flow,p,r,b),[])
        original=persistence_actions(build_integrated(p,r))
        self.assertEqual(persistence_actions(flow)['Report_integrated_candidate'],original['Report_integrated_candidate'])
        mutations=[]
        for node in nodes(flow):
            if node['type']!='OpenApiConnection':continue
            self.assertEqual(node['inputs']['retryPolicy'],{'type':'none'})
            parameters=node['inputs']['parameters']
            if parameters.get('parameters/method')=='POST':mutations.append(node)
        self.assertEqual(len(mutations),1)
        self.assertIn('overwrite=false',mutations[0]['inputs']['parameters']['parameters/uri'])
        self.assertEqual(mutations[0]['inputs']['parameters']['parameters/body'],"@string(outputs('Expected_observation'))")

    def test_namespace_claim_endpoint_and_record_preimage_drift_refuse_preparation(self):
        for change in ('folder','claim','key','record','source','original','connection','resume'):
            p,r,b=fixture()
            if change=='folder':b['folder']='/sites/Other/Evidence'
            elif change=='claim':b['claimJSON']=b['claimJSON']+' '
            elif change=='key':b['replayKey']='0'*64;b['claimName']='source-replay-'+b['replayKey']+'.json'
            elif change=='record':b['records'][0]['recordJSON']='{"edited":true}'
            elif change=='source':b['sourceMetadata']['ETag']='"changed"'
            elif change=='original':b['originalPin']['ServerRelativeUrl']='/sites/Fictional/other.pdf'
            elif change=='connection':b['connectionReference']['source']='Invoker'
            else:b['resumeRunIdDefault']='../outside'
            with self.subTest(change=change),self.assertRaises((ValueError,KeyError)):build(p,r,b)

    def test_initial_prewrite_final_guards_bind_all_three_current_records_original_claim_and_stage(self):
        p,r,b=fixture();a=persistence_actions(build(p,r,b))
        for label in ('initial','before_write','final'):
            expression=a['Require_context_'+label]['expression']
            for index,row in enumerate(b['records']):
                self.assertIn(row['recordJSON'].replace("'","''"),expression)
                self.assertIn(row['reviewState'],expression)
                self.assertIn(str(row['itemId']),a['Read_record_'+label+'_'+str(index)]['inputs']['parameters']['parameters/uri'])
            for k in PINS:self.assertIn(k,expression)
            self.assertIn(b['sourceMetadata']['Id'],expression)

    def test_changed_native_script_is_held_before_execution_and_before_persistence(self):
        p,r,b=fixture();f=build(p,r,b)
        stable=f['properties']['definition']['actions']['Select_fixed_source']['actions']['Require_ready']['actions']['Require_expected_metadata']['actions']['Require_stable_metadata']['actions']
        self.assertEqual(stable['Run_hash']['runAfter'],{'Require_engine_before_hash':['Succeeded']})
        guard=stable['Require_engine_before_hash']['expression']
        self.assertTrue(evaluate(guard,{'Read_engine_before_hash':b['scriptMetadata']},{}))
        altered={**b['scriptMetadata'],'ETag':'"human-edit,2"'}
        self.assertFalse(evaluate(guard,{'Read_engine_before_hash':altered},{}))

    def test_resume_never_creates_a_missing_prior_observation_and_does_not_replace_saved_bytes(self):
        p,r,b=fixture();b['resumeRunIdDefault']='FictionalEarlierRun'
        a=persistence_actions(build(p,r,b))
        self.assertIn("empty(outputs('Observation_resume_input'))",a['Require_observation_readable']['expression'])
        self.assertEqual(a['Create_observation_if_missing']['else']['actions'],{})
        self.assertIn("outputs('Read_observation_before')?['statusCode'],404",a['Create_observation_if_missing']['expression'])
        self.assertIn("base64(string(outputs('Expected_observation')))",a['Require_existing_observation_exact']['expression'])
        self.assertIn("json(base64ToString(body('Read_existing_observation_content')?['$content']))?['observedAtUtc']",a['Expected_observation']['inputs']['observedAtUtc'])
        self.assertIn('Observation_resume_characters',a)

    def test_saved_byte_pin_version_and_late_context_checks_precede_completion(self):
        p,r,b=fixture();a=persistence_actions(build(p,r,b))
        self.assertEqual(a['Report_persisted_observation']['runAfter'],{'Require_saved_observation':['Succeeded']})
        self.assertEqual(a['Require_saved_observation']['runAfter'],{'Require_context_final':['Succeeded']})
        expression=a['Require_saved_observation']['expression']
        self.assertIn("['UIVersionLabel'],'1.0'",expression)
        for k in PINS:self.assertIn("Read_observation_before')?['"+k+"']",expression)
        self.assertIn('base64(string(outputs',expression)
        self.assertNotIn('length(base64ToBinary',expression)
        for key in ('checkpointAdvanced','fullAcquisitionQualified','clinicalApplicabilityAccepted'):
            self.assertIs(a['Report_persisted_observation']['inputs'][key],False)

    def test_exact_validator_rejects_indirect_paths_unsafe_writes_and_owner_alerts(self):
        p,r,b=fixture()
        for change in ('overwrite','extra','scope','alerts','state'):
            flow=build(p,r,b)
            if change=='overwrite':
                n=next(n for n in nodes(flow) if isinstance(n.get('inputs'),dict) and n['inputs'].get('parameters',{}).get('parameters/method')=='POST')
                n['inputs']['parameters']['parameters/uri']=n['inputs']['parameters']['parameters/uri'].replace('overwrite=false','overwrite=true')
            elif change=='extra':persistence_actions(flow)['Hidden']={'type':'Workflow','runAfter':{}}
            elif change=='scope':persistence_actions(flow)['Read_original_final']['inputs']['parameters']['dataset']='https://contoso.sharepoint.com/sites/Other'
            elif change=='alerts':flow['properties']['flowFailureAlertSubscribed']=True
            else:flow['properties']['state']='Started'
            with self.subTest(change=change):self.assertTrue(validate(flow,p,r,b))


if __name__=='__main__':unittest.main()
