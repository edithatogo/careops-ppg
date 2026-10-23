import copy
import json
import unittest
from scripts.ppg_review_simplification import prepare, digest, reconcile_native, render


def fixture():
    source = dict(sourceSha256='a'*64, elements=[
        dict(elementId='F-clause', sourceLocator='fictional#1', text='Original clause'),
        dict(elementId='F-image', sourceLocator='fictional#2', text='')])
    template = dict(sourceSha256='b'*64, elements=[dict(elementId='F-heading', sourceLocator='fictional#template')])
    section = dict(sectionId='F-section', title='F <title>', text='Short <draft>',
                   sourceElements=['F-clause'], templateElements=['F-heading'], basis='editorial_paraphrase')
    proposal = dict(documentUID='F-document', revision='F-r1', guideVersion='F-guide1',
                    originalSourceSHA256='c'*64, sourceSHA256='a'*64, templateSHA256='b'*64,
                    status='unapproved_review_draft', clinicalApproval=False,
                    currentVersionVerified=False, notificationsEnabled=False,
                    sections=[section], retention={'F-image':'Original graphic retained'},
                    guideSections=[dict(sectionId='F-guide', title='Guide', text='F-doctor text',
                                        procedureSections=['F-section'], procedureHashes={'F-section':digest(section)})])
    return source, template, proposal


class SimplificationTests(unittest.TestCase):
    def test_complete_accounting_and_originals_preserved(self):
        s,t,p=fixture();before=copy.deepcopy((s,t,p));r=prepare(s,t,p)
        self.assertEqual(r['sourceElementCount'],2);self.assertEqual(r['templateElementCount'],1)
        self.assertEqual(r['coverage'][0]['sourceText'],'Original clause')
        self.assertEqual(r['coverage'][1]['retention'],'Original graphic retained')
        self.assertEqual((s,t,p),before);self.assertFalse(r['approval'])

    def test_missing_retention_unknown_evidence_and_wrong_pins_refused(self):
        for change in ['retention','source','template','evidence']:
            s,t,p=fixture()
            if change=='retention':p['retention']={}
            elif change=='source':p['sourceSHA256']='wrong'
            elif change=='template':p['templateSHA256']='wrong'
            else:p['sections'][0]['sourceElements']=['F-missing']
            with self.assertRaises(ValueError):prepare(s,t,p)

    def test_changed_procedure_requires_explicit_guide_reconciliation(self):
        s,t,p=fixture();p['sections'][0]['text']='Changed by reviewer'
        with self.assertRaisesRegex(ValueError,'alignment'):prepare(s,t,p)
        p['guideSections'][0]['procedureHashes']['F-section']=digest(p['sections'][0])
        self.assertEqual(prepare(s,t,p)['proposal']['sections'][0]['text'],'Changed by reviewer')

    def test_native_human_edit_or_scope_change_is_preserved_and_held(self):
        s,t,p=fixture();r=prepare(s,t,p);row=dict(DocumentUID='F-document',SectionId='F-section',ProposalRevision='F-r1',ProposedText=p['sections'][0]['text'],SectionJSON=json.dumps(p['sections'][0]))
        self.assertTrue(reconcile_native(r,[row]))
        for patch in [dict(ProposedText='Human edit'),dict(DocumentUID='F-other'),dict(SectionJSON='{}')]:
            edited={**row,**patch};before=copy.deepcopy(edited)
            with self.assertRaisesRegex(ValueError,'reconciliation'):reconcile_native(r,[edited])
            self.assertEqual(edited,before)

    def test_no_approval_currency_or_notifications_and_safe_html(self):
        for field in ['clinicalApproval','currentVersionVerified','notificationsEnabled']:
            s,t,p=fixture();p[field]=True
            with self.assertRaises(ValueError):prepare(s,t,p)
        r=prepare(*fixture());body=render(r,'procedure',{'Evidence':'https://example.invalid/evidence'})
        self.assertIn('&lt;draft&gt;',body);self.assertIn('UNAPPROVED',body)
        with self.assertRaises(ValueError):render(r,'guide',{'Bad':'javascript:alert(1)'})

    def test_duplicate_section_or_guide_or_partial_native_refused(self):
        s,t,p=fixture();p['sections']*=2
        with self.assertRaises(ValueError):prepare(s,t,p)
        s,t,p=fixture();p['guideSections']*=2
        with self.assertRaises(ValueError):prepare(s,t,p)
        with self.assertRaises(ValueError):reconcile_native(prepare(*fixture()),[])


class SuccessorTests(unittest.TestCase):
    def test_web_edit_requires_explicit_successor_and_preserves_inputs(self):
        from scripts.ppg_review_simplification import reconcile_successor
        s,t,p=fixture();previous=prepare(s,t,p)
        row=dict(DocumentUID=p['documentUID'],ProposalRevision=p['revision'],
                 SectionId='F-section',ProposedText='F edited in browser',
                 SectionJSON=json.dumps(p['sections'][0]))
        before=copy.deepcopy((previous,row))
        with self.assertRaises(ValueError):reconcile_native(previous,[row])
        result=reconcile_successor(s,t,previous,[row],'F-r2','F-guide2',
                                   {'F-guide':'F guide reconciled to edited text'},'Editorial test')
        self.assertEqual(result['proposal']['sections'][0]['text'],row['ProposedText'])
        self.assertEqual((previous,row),before)
        for revision,version,texts in [('F-r1','F-guide2',{'F-guide':'x'}),
                                       ('F-r2','F-guide1',{'F-guide':'x'}),
                                       ('F-r2','F-guide2',{})]:
            with self.assertRaises(ValueError):
                reconcile_successor(s,t,previous,[row],revision,version,texts,'Reason')

    def test_definition_edits_need_separate_reconciliation(self):
        from scripts.ppg_review_simplification import reconcile_successor
        s,t,p=fixture();previous=prepare(s,t,p)
        row=dict(DocumentUID=p['documentUID'],ProposalRevision=p['revision'],SectionId='F-section',
                 ProposedText='F change',SectionJSON='{}')
        with self.assertRaisesRegex(ValueError,'definition'):
            reconcile_successor(s,t,previous,[row],'F-r2','F-guide2',{'F-guide':'F guide'},'Reason')


class PresentationTests(unittest.TestCase):
    def test_reader_trace_uses_locations_and_headings_instead_of_internal_ids(self):
        prepared=prepare(*fixture())
        procedure=render(prepared,"procedure",{})
        guide=render(prepared,"guide",{})
        self.assertIn("fictional#1",procedure)
        self.assertNotIn("F-clause",procedure)
        self.assertIn("F &lt;title&gt;",guide)
        self.assertNotIn("F-section",guide)
