import copy,json,subprocess,unittest
from pathlib import Path
from xml.etree import ElementTree as ET


def fixture():
    native={k:{'value':[]} for k in ['frameworks','requirements','mappings','crosswalks','relationships','catalogue']}
    spec=json.loads(Path('config/standards-registers.json').read_text())
    def row(slot):
        reg=spec['registers'][list(native).index(slot)]
        return {f['name']:(ET.fromstring(f['schemaXml']).findtext('.//CHOICE') if f['type']=='Choice' else 'fictional' if f['required'] else None) for f in reg['fields']}
    f=row('frameworks');f.update(FrameworkKey='f',EditionStatus='Published');native['frameworks']['value']=[f]
    q=row('requirements');q.update(RequirementKey='r',FrameworkKey='f',ParentRequirementKey=None);native['requirements']['value']=[q]
    m=row('mappings');m.update(MappingKey='m',DocumentUID='a',DocumentVersion='1',RequirementKey='r',MappingState='Proposed');native['mappings']['value']=[m]
    native['catalogue']['value']=[{'DocumentUID':'a'},{'DocumentUID':'b'}]
    link=row('relationships');link.update(RelationshipKey='l',FromDocumentUID='a',FromVersion='1',ToDocumentUID='b',ToVersion='1',RelationshipType='governed_by',ReviewState='Accepted',EvidenceRef=json.dumps({'reviewEvidenceRef':'fictional-decision'}));native['relationships']['value']=[link]
    return dict(native=native,documentUID='a',documentVersion='1')


def run_cases(cases):
    p=subprocess.run(['node','tools/standards/test_context.mjs'],input=json.dumps(cases),text=True,capture_output=True,check=True)
    return json.loads(p.stdout)


class StandardsWeb(unittest.TestCase):
    def test_exact_version_graph_and_no_writes(self):
        x=fixture();before=copy.deepcopy(x);other=copy.deepcopy(x);other['documentVersion']='2'
        a,b=run_cases([x,other]);self.assertTrue(a['ok']);self.assertTrue(b['ok']);v=a['value']
        self.assertEqual(v['acceptedUpstream'],[dict(documentUID='b',documentVersion='1',viaRelationshipId='l')])
        self.assertEqual(b['value']['acceptedUpstream'],[]);self.assertEqual(b['value']['mappings'],[])
        self.assertEqual(v['nativeWrites'],0);self.assertFalse(v['historyValidated']);self.assertFalse(v['actorAuthorityVerified']);self.assertEqual(x,before)

    def test_missing_partial_cycle_draft_and_decision_hold(self):
        cases=[]
        for mutation in ['partial','duplicate','parent','requirement_cycle','draft','no_decision','unknown_reviewed_document','missing_version','self_link','bad_choice','cycle']:
            x=fixture();n=x['native'];r=n['relationships']['value'][0]
            if mutation=='partial':n['catalogue']['@odata.nextLink']='next'
            elif mutation=='duplicate':n['frameworks']['value']*=2
            elif mutation=='parent':n['requirements']['value'][0]['ParentRequirementKey']='absent'
            elif mutation=='requirement_cycle':n['requirements']['value'][0]['ParentRequirementKey']='r'
            elif mutation=='draft':n['frameworks']['value'][0]['EditionStatus']='Draft';n['mappings']['value'][0]['EvidenceRef']='{"currentObligation":true}'
            elif mutation=='no_decision':r['EvidenceRef']='Source citation only'
            elif mutation=='unknown_reviewed_document':r['ToDocumentUID']='missing'
            elif mutation=='missing_version':r['ToVersion']=''
            elif mutation=='self_link':r['ToDocumentUID']='a'
            elif mutation=='bad_choice':r['ReviewState']='Approved'
            elif mutation=='cycle':n['relationships']['value'].append(dict(r,RelationshipKey='l2',FromDocumentUID='b',ToDocumentUID='a'))
            cases.append(x)
        self.assertEqual([r['ok'] for r in run_cases(cases)],[False]*len(cases))

    def test_reciprocal_references_and_unresolved_proposals_are_allowed(self):
        x=fixture();r=x['native']['relationships']['value'][0];r['RelationshipType']='references'
        x['native']['relationships']['value'].append(dict(r,RelationshipKey='l2',FromDocumentUID='b',ToDocumentUID='a'))
        y=fixture();y['native']['relationships']['value'][0].update(ReviewState='Proposed',ToDocumentUID='unknown',EvidenceRef=None)
        a,b=run_cases([x,y]);self.assertTrue(a['ok']);self.assertTrue(b['ok']);self.assertEqual(len(b['value']['unresolved']),1)

    def test_flow_is_manual_read_only_and_holds_changed_inputs(self):
        from scripts.ppg_standards_web_flow import build,SLOTS
        bindings=dict(site='https://example.test/site',registers={s:'fictional-'+s for s in SLOTS},connectionReferences={s:{'source':'Embedded'} for s in ['shared_sharepointonline','shared_excelonlinebusiness']},scriptParameters={s:'fictional' for s in ['source','drive','file','scriptSource','scriptDrive','scriptId']},scriptSHA256='a'*64,contractSHA256='b'*64)
        value=build(bindings);d=value['properties']['definition']
        self.assertEqual(list(d['triggers']),['manual']);self.assertEqual(d['triggers']['manual']['kind'],'Button')
        reads=[a for a in d['actions'].values() if isinstance(a.get('inputs'),dict) and a['inputs'].get('host',{}).get('connectionName')=='shared_sharepointonline']
        self.assertEqual(len(reads),12);self.assertTrue(all(a['inputs']['parameters']['parameters/method']=='GET' for a in reads))
        guard=d['actions']['Source_snapshot_stable'];self.assertEqual(guard['else']['actions']['Hold_changed_source']['inputs']['runError']['code'],'StandardsSourceChanged')
        self.assertEqual(guard['actions']['Report_context']['inputs']['nativeWrites'],0)
        bindings['connectionReferences']['premium']={'source':'Embedded'}
        with self.assertRaises(ValueError):build(bindings)
