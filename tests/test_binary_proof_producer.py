"""Synthetic transport only: never authenticates or calls Microsoft 365."""
import copy
import importlib.util
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
import json
from urllib.parse import urlsplit

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'tools/policy-editions'))
import produce_binary_publication_proof as m


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026,10,18,12,tzinfo=timezone.utc).astimezone(tz)


def complete_fixture():
    from test_prepared_binary_publication import fixture
    from build_prepared_binary_publication import build
    p,target,publisher_binding=fixture()
    target['name']='33333333-3333-3333-3333-333333333333'
    definition=build(p,target,publisher_binding)['properties']['definition']
    site=p['properties']['definition']['actions']['Resolve_context']['actions']['Read_selected_case']['inputs']['parameters']['dataset']
    folder=urlsplit(site).path+'/qualification'
    raw=b'PK\x03\x04\x00\xff synthetic complete driver bytes'
    source=dict(UniqueId='11111111-1111-1111-1111-111111111111',ETag='"opaque-source"',nativeVersion='2.0',
                Length=len(raw),DocumentReference=site+'/prepared.docx')
    issued=dict(UniqueId='22222222-2222-2222-2222-222222222222',ETag='"opaque-issued"',nativeVersion='1.0',
                Length=len(raw),DocumentReference=urlsplit(site).scheme+'://'+urlsplit(site).netloc+folder+'/FICTIONAL-issued-local.docx')
    scope=dict(CaseUID='LC-FICTIONAL-LOCAL-PRODUCER',DocumentReference=source['DocumentReference'],
               ReviewedVersionRef='sharepoint:'+source['UniqueId']+':'+source['ETag'],DocumentSHA256=m.sha(raw))
    b=dict(qualificationOnly=True,site=site,scope=scope,source=source,issued=issued,qualificationFolder=folder,
           copy=dict(environment='LOCAL-environment',flowName=target['name'],runId='run1',definitionSHA256=m.digest(definition)),
           requestReference='LOCAL-only',fictionalRouteProfile=publisher_binding['fictionalRouteProfile'],
           requiredFictionalRoles=['FICTIONAL reviewer'],readinessDateTimeZone='Australia/Brisbane',readinessAssessmentDate='2026-10-18')
    def row(n,**fields):
        return dict(scope,Id=n,GUID='local-row-'+str(n),**{'odata.etag':'"row-'+str(n)+'"'},
                    FictionalTest=True,ConditionsState='None recorded',SupersedesEventUID=None,**fields)
    ready=row(1,EventUID='local-ready',Finding='Ready for decision',AssessorName='FICTIONAL assessor',
              FindingSummary='Synthetic DateOnly readiness',EvidenceReference='fictional://readiness',
              AssessedOn='2026-10-17T14:00:00Z',Created='2026-10-17T19:20:00Z')
    consultation=[row(2,EventUID='local-request',EventKind='Consultation',SubjectRole='FICTIONAL reviewer',
                     ParentEventUID=None,RecordState='Pending response',OccurredOn='2026-10-17T19:00:00Z',Created='2026-10-17T19:01:00Z'),
                  row(3,EventUID='local-response',EventKind='Consultation',SubjectRole='FICTIONAL reviewer',
                     ParentEventUID='local-request',RecordState='Responded',Summary='FICTIONAL response',
                     EvidenceReference='fictional://response',NextAction='Retain',OccurredOn='2026-10-17T19:10:00Z',Created='2026-10-17T19:11:00Z')]
    purposes=[]
    for i,code in enumerate(m.CODES):
        uid='LC03-PURPOSE-'+b['requestReference']+'-'+source['UniqueId']+'-v2.0-'+code
        purposes.append(row(4+i,EventUID=uid,Stage='Decision',RecordState='Recorded',
            DecisionOutcome='Approved (recorded)' if i==3 else 'Endorsed (recorded)',
            ReadinessEventUID=ready['EventUID'],ParentEventUID=purposes[-1]['EventUID'] if purposes else None,
            DecisionReference=b['fictionalRouteProfile']['reference']+'/1/'+m.digest(b['fictionalRouteProfile'])+'/'+code,
            ActorName='FICTIONAL actor',ConditionsNotes='Synthetic evidence',Summary='FICTIONAL '+m.LABELS[i]+': Synthetic evidence',
            EvidenceReference='fictional://'+code,NextAction='Retain',OccurredOn=f'2026-10-17T19:{21+i}:00Z',Created=f'2026-10-17T19:{21+i}:01Z'))
    case={k:'synthetic preserved '+k for k in m.CASE_FIELDS};case.update(CaseUID=scope['CaseUID'],evidenceDraftLink=source['DocumentReference'])
    frame={k:{'preserved':'local '+k} for k in m.FRAME}
    frame.update(case=case,readinessHistory={'value':[ready]},consultationHistory={'value':consultation},assuranceHistory={'value':purposes})
    b['frame']={}
    for i,name in enumerate(sorted(m.FRAME)):
        url=site+f"/_api/web/lists(guid'00000000-0000-0000-0000-{i+1:012d}')/items"
        if name not in m.COLLECTIONS:url+='(1)'
        b['frame'][name]={'url':url,'expected':frame[name]}
    return b,definition,frame,raw,(p,target,publisher_binding)


class CompleteTransport:
    """An in-memory store; every native observation comes through this fake."""
    def __init__(self,b,definition,frame,raw):
        self.b=b;self.definition=definition;self.frame=frame
        self.files={pin['DocumentReference']:raw for pin in (b['source'],b['issued'])}
        self.pins={pin['DocumentReference']:copy.deepcopy(pin) for pin in (b['source'],b['issued'])}
        self.permissions_value={'Inherited':True,'scope':'synthetic unchanged'}
        self.metadata_reads=0;self.frame_reads=0;self.drift=None
        self.rows=[dict(name=n,runName='run1',properties={'status':'Succeeded' if i<2 else 'Skipped'}) for i,n in enumerate(
            ('Copy_binary_absent_only','Native_binary_copy_observation','Create_binary_publication','Native_binary_publication_receipt'))]
    def flow(self,b):return {'name':b['copy']['flowName'],'properties':{'definition':self.definition,'lastModifiedTime':'2026-10-17T18:00:00Z'}}
    def run(self,b):return {'name':'run1','properties':{'status':'Succeeded','endTime':'2026-10-17T20:00:00Z'}}
    def actions(self,b):return {'value':self.rows}
    def action_content(self,row,kind):
        if kind=='inputs':return {'parameters':{'dataset':self.b['site'],'parameters/method':'POST','parameters/uri':
            "_api/web/GetFileById('"+self.b['source']['UniqueId']+"')/copyTo(strNewUrl='"+urlsplit(self.b['issued']['DocumentReference']).path+"',bOverWrite=false)"}}
        r=dict(runId='run1',preparedScope=self.b['scope'],copyCreatedCount=1,binaryOutputQualified=False,realPolicyEffects=False,
               issued=self.native(self.b['issued']),purposeAuthorisation=self.frame['assuranceHistory']['value'][-1])
        r.update({k:0 for k in ('publicationCreatedCount','caseWrites','sourceWrites','readinessWrites','purposeWrites','notifications')});return r
    def get_json(self,url):
        self.frame_reads+=1
        name=next(k for k,v in self.b['frame'].items() if v['url']==url)
        actual=copy.deepcopy(self.frame[name])
        if self.drift=='frame' and self.frame_reads>len(m.FRAME):actual['changed']='human edit'
        return actual
    @staticmethod
    def native(pin):return {**{k:pin[k] for k in ('UniqueId','ETag')},'UIVersionLabel':pin['nativeVersion'],
                           'Length':str(pin['Length']),'ServerRelativeUrl':urlsplit(pin['DocumentReference']).path}
    def file_metadata(self,site,ref):
        self.metadata_reads+=1;actual=self.native(self.pins[ref])
        if self.drift=='metadata' and self.metadata_reads>2:actual['ETag']='"changed"'
        return actual
    def download(self,site,ref):return self.files[ref]
    def permissions(self,site,ref):return self.permissions_value
    def create_only_simulated_storage(self,ref,raw):
        if ref in self.files:raise FileExistsError(ref)
        self.files[ref]=raw
        self.pins[ref]=dict(UniqueId='44444444-4444-4444-4444-444444444444',ETag='"storage-token"',nativeVersion='1.0',Length=len(raw),DocumentReference=ref)
        return {**self.pins[ref],'expectedPermissions':copy.deepcopy(self.permissions_value)}


class FakeTransport:
    def __init__(self, binding, definition):
        self.b = binding
        self.definition = definition
        names = ('Copy_binary_absent_only', 'Native_binary_copy_observation',
                 'Create_binary_publication', 'Native_binary_publication_receipt')
        self.rows = [dict(name=n, runName='run1', properties={'status': 'Succeeded' if i < 2 else 'Skipped'})
                     for i, n in enumerate(names)]
        self.inputs = {'parameters': {'dataset': binding['site'], 'parameters/method': 'POST',
            'parameters/uri': "_api/web/GetFileById('source')/copyTo(strNewUrl='/sites/test/isolated/FICTIONAL-issued.docx',bOverWrite=false)"}}
        self.receipt = dict(runId='run1', preparedScope=binding['scope'], copyCreatedCount=1,
            binaryOutputQualified=False, realPolicyEffects=False,
            issued=dict(UniqueId='22222222-2222-2222-2222-222222222222', ETag='"opaque"',
                        UIVersionLabel='1.0', Length='4', ServerRelativeUrl='/sites/test/isolated/FICTIONAL-issued.docx'))
        self.receipt.update({k: 0 for k in ('publicationCreatedCount','caseWrites','sourceWrites','readinessWrites','purposeWrites','notifications')})
    def flow(self, b): return dict(name=b['copy']['flowName'], properties={'definition': self.definition})
    def run(self, b): return dict(name='run1', properties={'status':'Succeeded','endTime':'2026-01-01T00:00:00Z'})
    def actions(self, b): return {'value': self.rows}
    def action_content(self, row, kind): return self.inputs if kind == 'inputs' else self.receipt


class ProducerTests(unittest.TestCase):
    def setUp(self):
        self.b = {'site':'https://example.invalid/sites/test', 'copy':{'flowName':'flow1','runId':'run1'},
            'scope':{'CaseUID':'LOCAL'}, 'source':{'UniqueId':'source'},
            'issued':dict(UniqueId='22222222-2222-2222-2222-222222222222',ETag='"opaque"',nativeVersion='1.0',Length=4,
                          DocumentReference='https://example.invalid/sites/test/isolated/FICTIONAL-issued.docx')}
        self.definition = {'actions':{n:{'type':'Compose','runAfter':{}} for n in
            ('Create_binary_publication','Native_binary_publication_receipt')}}
        self.t = FakeTransport(self.b, self.definition)
    def inspect(self):
        with tempfile.TemporaryDirectory() as folder:
            return m.inspect_copy(self.b,self.definition,self.t,m.Capture(Path(folder)/'capture'))
    def test_actual_terminal_copy_receipt_and_runtime_inputs(self):
        self.assertEqual(self.inspect()['copyCreatedCount'],1)
    def test_skipped_failed_missing_duplicate_or_foreign_actions_hold(self):
        original=copy.deepcopy(self.t.rows)
        variants=[]
        changed=copy.deepcopy(original);changed[0]['properties']['status']='Failed';variants.append(changed)
        changed=copy.deepcopy(original);changed[-1]['properties']['status']='Succeeded';variants.append(changed)
        changed=copy.deepcopy(original);changed[0]['runName']='other';variants.append(changed)
        variants += [original[:-1], original+[original[0]]]
        for rows in variants:
            self.t.rows=rows
            with self.assertRaises(ValueError): self.inspect()
    def test_body_overwrite_wrong_source_and_effect_counts_hold(self):
        original=copy.deepcopy(self.t.inputs)
        for key,value in [('parameters/body','bytes'),('parameters/method','GET'),('dataset','https://other.invalid')]:
            self.t.inputs=copy.deepcopy(original);self.t.inputs['parameters'][key]=value
            with self.assertRaises(ValueError): self.inspect()
        for value in ['bOverWrite=true', "GetFileById('other')"]:
            self.t.inputs=copy.deepcopy(original)
            self.t.inputs['parameters']['parameters/uri']=value
            with self.assertRaises(ValueError): self.inspect()
        self.t.inputs=original;self.t.receipt['publicationCreatedCount']=1
        with self.assertRaises(ValueError): self.inspect()
    def test_boolean_effect_counts_do_not_qualify_first_copy(self):
        original=copy.deepcopy(self.t.receipt)
        for key in ('copyCreatedCount','publicationCreatedCount','caseWrites','sourceWrites','readinessWrites','purposeWrites','notifications'):
            self.t.receipt=copy.deepcopy(original)
            self.t.receipt[key]=True if key=='copyCreatedCount' else False
            with self.subTest(key=key), self.assertRaises(ValueError):self.inspect()

    def test_complete_history_refuses_pagination(self):
        for marker in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink'):
            with self.subTest(marker=marker):
                self.t.actions=lambda b: {'value':self.t.rows,marker:'more'}
                with self.assertRaises(ValueError): self.inspect()
    def test_exclusive_evidence_and_changed_stage_refused_before_transport(self):
        with tempfile.TemporaryDirectory() as folder:
            capture=m.Capture(Path(folder)/'capture');capture.write('binary',b'\x00\xff')
            with self.assertRaises(FileExistsError): capture.write('binary',b'changed')
            with self.assertRaises(FileExistsError): m.Capture(capture.path)
            with self.assertRaises(ValueError): m.stage({}, {}, object(),Path(folder)/'new','wrong')
            self.assertFalse((Path(folder)/'new').exists())
    def test_transport_refuses_cross_site_encoded_and_traversal_paths(self):
        t=m.M365ReadOnly();site=self.b['site']
        for ref in ['https://other.invalid/sites/test/a','https://example.invalid/sites/else/a',
                    site+'/../a',site+'/%2e/a',site+'/a?x=y',site+'/a#fragment']:
            with self.assertRaises(ValueError): t.file_path(site,ref)
        self.assertEqual(t.file_path(site,site+'/file.docx'),'/sites/test/file.docx')
    def test_native_action_pagination_bound_to_exact_run_and_raw_pages_retained(self):
        t=m.M365ReadOnly();b={'copy':{'environment':'local','flowName':'flow','runId':'run'}}
        prefix=t.base(b)+'/runs/run/actions?'
        for marker in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink'):
            with self.subTest(marker=marker):
                seen=[]
                def read(url):
                    seen.append(url)
                    return {'value':[{'name':'first'}],marker:prefix+'skip=2'} if len(seen)==1 else {'value':[{'name':'second'}]}
                t.get_json=read
                result=t.actions(b);self.assertEqual([x['name'] for x in result['value']],['first','second'])
                self.assertEqual(len(result['nativePages']),2)
                self.assertEqual(seen,[prefix+'api-version=2016-11-01&$top=100',prefix+'skip=2'])
                self.assertEqual(result['nativePages'][0][marker],prefix+'skip=2')
                for link in ['https://foreign.invalid/actions?skip=2',prefix+'api-version=2016-11-01&$top=100']:
                    t.get_json=lambda url:{'value':[],marker:link}
                    with self.assertRaises(ValueError):t.actions(b)
        conflicting_reads=[]
        def conflicting(url):
            conflicting_reads.append(url)
            return {'value':[], 'nextLink':prefix+'skip=2', '@nextLink':prefix+'skip=3'}
        t.get_json=conflicting
        with self.assertRaises(ValueError):t.actions(b)
        self.assertEqual(len(conflicting_reads),1)
    def test_json_get_uses_raw_response_file_not_cli_display_escaping(self):
        t=m.M365ReadOnly();expected={'expression':"@equals('actual\nmultiline','actual\nmultiline')"}
        def command(args):
            self.assertEqual(args[args.index('--method')+1],'get')
            Path(args[args.index('--filePath')+1]).write_bytes(m.canonical(expected))
            return b'{"expression":"presentation is not the native response"}'
        t.command=command
        self.assertEqual(t.get_json('https://example.invalid/native-read'),expected)
    def test_action_content_observed_powerplatform_host_uses_no_redirect_opener(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return b'{"local":true}'
        class Opener:
            def open(self,url,timeout):return Response()
        action={'properties':{'outputsLink':{'uri':'https://synthetic.environment.api.powerplatformusercontent.com/run/content?sig=LOCAL'}}}
        with patch.object(m,'build_opener',return_value=Opener()) as opener:
            self.assertEqual(m.M365ReadOnly().action_content(action,'outputs'),{'local':True})
            with self.assertRaises(ValueError):opener.call_args.args[0].redirect_request(None,None,None,None,None,None)
        action['properties']['outputsLink']['uri']='https://environment.api.powerplatformusercontent.com.foreign.invalid/run'
        with self.assertRaises(ValueError):m.M365ReadOnly().action_content(action,'outputs')


    def test_signed_environment_api_action_content_route_is_bounded(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return b'{"native":true}'
        class Opener:
            def open(self, url, timeout): return Response()
        base = 'https://synthetic.environment.api.powerplatform.com'
        path = '/powerautomate/automations/direct/workflows/workflow1/runs/run1/actions/Native_receipt/contents/ActionOutputs'
        signed = '?sig=LOCAL&se=LOCAL&sp=LOCAL&sv=LOCAL'
        def action(url): return {'properties': {'outputsLink': {'uri': url}}}
        with patch.object(m, 'build_opener', return_value=Opener()) as opener:
            self.assertEqual(m.M365ReadOnly().action_content(action(base + path + signed), 'outputs'), {'native': True})
            with self.assertRaises(ValueError): opener.call_args.args[0].redirect_request(None, None, None, None, None, None)
            for url in (base + path, base + '/other' + signed,
                        base + path.replace('ActionOutputs', 'ActionInputs') + signed,
                        base + '.foreign.invalid' + path + signed,
                        base.replace('https://', 'https://user:secret@') + path + signed):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    m.M365ReadOnly().action_content(action(url), 'outputs')


class CompleteProducerTests(unittest.TestCase):
    def setUp(self):
        self.b,self.definition,self.frame,self.raw,self.publisher=complete_fixture()
        self.t=CompleteTransport(self.b,self.definition,self.frame,self.raw)
        self.clock=patch.object(m,'datetime',FixedClock);self.clock.start();self.addCleanup(self.clock.stop)
    def test_date_only_local_date_and_native_recording_order(self):
        # Local 18 October midnight is 17 October 14:00Z; it is not the
        # assessment time. Responses later that UTC evening are legitimate.
        m.validate_domain(self.frame,self.b,self.frame['assuranceHistory']['value'][-1])
    def test_wrong_future_non_date_only_and_late_response_refused(self):
        mutations=[lambda f:f['readinessHistory']['value'][0].update(AssessedOn='2026-10-16T14:00:00Z'),
            lambda f:f['readinessHistory']['value'][0].update(AssessedOn='2026-10-19T14:00:00Z'),
            lambda f:f['readinessHistory']['value'][0].update(AssessedOn='2026-10-17T15:00:00Z'),
            lambda f:f['readinessHistory']['value'][0].update(Created='2099-01-01T00:00:00Z'),
            lambda f:f['consultationHistory']['value'][1].update(Created='2026-10-17T19:30:00Z'),
            lambda f:f['consultationHistory']['value'][1].update(OccurredOn='2026-10-17T19:30:00Z'),
            lambda f:f['assuranceHistory']['value'][0].update(OccurredOn='2026-10-17T19:19:00Z')]
        for mutation in mutations:
            f=copy.deepcopy(self.frame);mutation(f)
            with self.assertRaises(ValueError):m.validate_domain(f,self.b,f['assuranceHistory']['value'][-1])
    def staged(self,folder):
        path=Path(folder)/'stage'
        result=m.stage(self.b,self.definition,self.t,path,m.digest(self.b))
        ref=urlsplit(self.b['site']).scheme+'://'+urlsplit(self.b['site']).netloc+self.b['qualificationFolder']+'/PPG-binary-proof-'+self.b['issued']['UniqueId']+'-v1.0.json'
        storage=self.t.create_only_simulated_storage(ref,(path/'binary-proof.json').read_bytes())
        return path,result,storage
    def test_complete_stage_storage_readback_finalize_and_existing_builder_contract(self):
        from build_prepared_binary_publication import build
        with tempfile.TemporaryDirectory() as folder:
            path,result,storage=self.staged(folder)
            with self.assertRaises(FileExistsError):self.t.create_only_simulated_storage(storage['DocumentReference'],b'overwrite')
            output=Path(folder)/'final'
            final=m.finalize(path,storage,self.t,output,result['stageManifestSHA256'])
            evidence=(output/'producer-evidence.json').read_bytes()
            self.assertEqual(m.sha(evidence),final['producerEvidenceSHA256'])
            self.assertEqual((output/'native-binary-proof.json').read_bytes(),(path/'binary-proof.json').read_bytes())
            p,target,b=self.publisher;b['reviewedBinaryProof']=final['reviewedBinaryProof']
            graph=build(p,target,b,producer_evidence=evidence)['properties']['definition']['actions']
            self.assertNotEqual(graph['Verify_record_producer_trust']['expression'],'@and(false)')
            with self.assertRaises(ValueError):build(p,target,b,producer_evidence=evidence+b' ')
            self.assertEqual(final['nativeWrites'],0)
            self.assertEqual((path/'source.docx').read_bytes(),self.raw)
            self.assertEqual((path/'issued.docx').read_bytes(),self.raw)
            provenance=json.loads((path/'producer-code-provenance.json').read_bytes())
            self.assertEqual(provenance['driverSHA256'],m.sha(Path(m.__file__).read_bytes()))
            self.assertEqual(final['reviewedBinaryProof']['content']['downloadEvidence']['producer']['driverSHA256'],provenance['driverSHA256'])
    def test_stage_download_metadata_frame_and_inventory_drift_hold(self):
        for drift in ('metadata','frame','bytes','inventory'):
            self.t=CompleteTransport(self.b,self.definition,self.frame,self.raw)
            self.t.drift=drift
            if drift=='bytes':self.t.files[self.b['issued']['DocumentReference']]=b'X'*len(self.raw)
            if drift=='inventory':self.t.rows.pop()
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'stage'
                with self.assertRaises(ValueError):m.stage(self.b,self.definition,self.t,path,m.digest(self.b))
                held=json.loads((path/'held.json').read_bytes());self.assertFalse(held['qualified'])
                self.assertFalse((path/'stage-manifest.json').exists())
    def test_complete_stage_accepts_proven_omitted_creator_and_retains_basis(self):
        self.t.rows=[r for r in self.t.rows if r['name']!='Create_binary_publication']
        self.t.rows.append({'name':'Ensure_publication','runName':'run1','properties':{'status':'Skipped'}})
        with tempfile.TemporaryDirectory() as folder:
            path,result,storage=self.staged(folder)
            observations=json.loads((path/'publication-action-ineligibility.json').read_bytes())
            self.assertEqual(observations[0]['classification'],'omitted-ineligible')
            self.assertEqual(observations[0]['barrier'],'Ensure_publication')
            self.assertIn('publication-action-ineligibility.json',json.loads((path/'stage-manifest.json').read_bytes())['files'])
            final=m.finalize(path,storage,self.t,Path(folder)/'final',result['stageManifestSHA256'])
            self.assertEqual(final['nativeWrites'],0)
    def test_staged_tamper_stored_bytes_pins_permissions_and_frame_changes_hold(self):
        for drift in ('stage','stored','pin','permissions','frame'):
            self.t=CompleteTransport(self.b,self.definition,self.frame,self.raw)
            with tempfile.TemporaryDirectory() as folder:
                path,result,storage=self.staged(folder)
                if drift=='stage':(path/'source.docx').write_bytes(b'tampered')
                elif drift=='stored':self.t.files[storage['DocumentReference']]+=b' '
                elif drift=='pin':self.t.pins[storage['DocumentReference']]['ETag']='"changed"'
                elif drift=='permissions':self.t.permissions_value={'scope':'changed'}
                else:self.t.frame['case']['nextAction']='human change'
                output=Path(folder)/'final'
                with self.assertRaises(ValueError):m.finalize(path,storage,self.t,output,result['stageManifestSHA256'])
                self.assertFalse((output/'reviewed-binary-proof-binding.json').exists())


class OmittedPublicationActionTests(unittest.TestCase):
    def setUp(self):
        # Minimal sanitized native-shaped rows. The retained decision review
        # distinguishes explicit Skipped ancestors from a missing container
        # blocked by Route_readiness_check's observed Skipped status.
        self.definition={'actions':{
            'Before':{'type':'Compose','runAfter':{}},
            'Ensure_publication':{'type':'If','runAfter':{'Before':['Succeeded']},
                'actions':{'Create_binary_publication':{'type':'OpenApiConnection','runAfter':{}}}},
            'Native_binary_publication_receipt':{'type':'Compose','runAfter':{'Ensure_publication':['Succeeded']}}}}
    def row(self,name,status,run='local-run'):
        return {'name':name,'runName':run,'type':'Microsoft.ProcessSimple/environments/flows/runs/actions',
                'properties':{'status':status,'code':'ActionSkipped' if status=='Skipped' else 'NotSpecified'}}
    def classify(self,rows,name='Create_binary_publication'):
        return m.publication_action_ineligibility(self.definition,rows,'local-run',name)
    def test_explicit_skipped_ancestor_proves_omitted_child_ineligible(self):
        result=self.classify([self.row('Ensure_publication','Skipped')])
        self.assertEqual(result['classification'],'omitted-ineligible')
        self.assertEqual(result['basis'],'observed-skipped-ancestor')
    def test_exact_terminal_dependency_barrier_for_missing_scope_and_receipt(self):
        result=self.classify([self.row('Before','Skipped')])
        self.assertEqual(result['barrier'],'Ensure_publication')
        self.assertEqual(result['basis'],'exact-terminal-runAfter-barrier')
        result=self.classify([self.row('Ensure_publication','Skipped')],'Native_binary_publication_receipt')
        self.assertEqual(result['dependencies'][0]['observedStatus'],'Skipped')
    def test_retained_decision_inventory_shape_uses_exact_allowed_statuses(self):
        definition={'actions':{
            'Route_readiness_check':{'type':'If','runAfter':{}},
            'Check_decision_prerequisites':{'type':'If',
                'runAfter':{'Route_readiness_check':['Succeeded','Failed','TimedOut']},
                'actions':{'Create_decision':{'type':'OpenApiConnection','runAfter':{}}}}}}
        rows=[self.row('Route_readiness_check','Skipped')]
        result=m.publication_action_ineligibility(definition,rows,'local-run','Create_decision')
        self.assertEqual(result['classification'],'omitted-ineligible')
        self.assertEqual(result['barrier'],'Check_decision_prerequisites')
        self.assertEqual(result['dependencies'][0]['allowedStatuses'],['Succeeded','Failed','TimedOut'])
        for eligible in ('Succeeded','Failed','TimedOut'):
            with self.assertRaises(ValueError):m.publication_action_ineligibility(definition,
                [self.row('Route_readiness_check',eligible)],'local-run','Create_decision')
    def test_eligible_unknown_running_mixed_and_foreign_observations_hold(self):
        variants=[[],[self.row('Before','Succeeded')],[self.row('Before','Running')],
            [self.row('Ensure_publication','Succeeded')],[self.row('Ensure_publication','Skipped','foreign')],
            [self.row('Ensure_publication','Skipped'),self.row('Create_binary_publication','Succeeded')],
            [self.row('Ensure_publication','Skipped'),self.row('Create_binary_publication','Running')],
            [self.row('Ensure_publication','Skipped'),self.row('Create_binary_publication','Failed')],
            [self.row('Ensure_publication','Skipped'),self.row('Ensure_publication','Succeeded')]]
        for rows in variants:
            with self.assertRaises(ValueError):self.classify(rows)
        self.definition['actions']['Ensure_publication']['runAfter']['Other']=['Succeeded']
        self.definition['actions']['Other']={'type':'Compose','runAfter':{}}
        with self.assertRaises(ValueError):self.classify([self.row('Before','Skipped'),self.row('Other','Succeeded')])
    def test_skipped_dependency_is_eligible_when_reviewed_runAfter_allows_it(self):
        self.definition['actions']['Ensure_publication']['runAfter']={'Before':['Skipped','Succeeded']}
        with self.assertRaises(ValueError):self.classify([self.row('Before','Skipped')])
    def test_omitted_predecessor_is_not_assumed_skipped(self):
        # Neither a successful termination elsewhere nor a wholly absent
        # predecessor supplies its runtime status.
        rows=[self.row('Copy_phase_finished','Succeeded')]
        with self.assertRaises(ValueError):self.classify(rows)


if __name__ == '__main__': unittest.main()
