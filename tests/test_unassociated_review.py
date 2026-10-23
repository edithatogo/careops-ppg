import copy
import unittest
from scripts.ppg_unassociated_review import assess, digest, content_digest


class UnassociatedReview(unittest.TestCase):
    def fixture(self):
        original=b'original';text=b'Guidance\nRetained statement';subject=b'subject'
        screen=dict(corpus=[dict(sourceSha256=digest(original),textSha256=digest(text))],records=[dict(sourceIndexes=[])])
        inv=dict(sourceSha256=digest(subject),elements=[dict(sourceLocator='node',text='Subject purpose')])
        criteria=dict(criteriaVersion='1',criteria=[dict(criterionId='need')],decisionOptions=['retain','seek_further_evidence'])
        finding=dict(findingId='one',criterionId='need',suggestedAction='retain',claimType='inference',humanDecision=None,
                     statement='Distinct purpose',benefit='Preservation',effort='Low',dependencies='Current sources',uncertainty='Unverified authority',
                     citations=[dict(sourceId='subject-inspection',sourceSha256=digest(subject),locator='node',quote='Subject purpose'),
                                dict(sourceId='unassociated-text',sourceSha256=digest(text),locator='lines=1-2',quote='Guidance\nRetained statement')])
        return [screen,0,inv,subject,original,text,criteria,[finding]]

    def test_replay_preserves_inputs_and_never_assigns_identity(self):
        args=self.fixture();before=copy.deepcopy(args);report=assess(*args)
        self.assertEqual(report,assess(*args));self.assertEqual(args,before)
        self.assertFalse(report['catalogueIdentityAssigned']);self.assertFalse(report['currentAuthorityVerified'])
        self.assertEqual(report['contentSHA256'],content_digest(report))

    def test_empty_review_refused(self):
        args=self.fixture();args[7]=[]
        with self.assertRaises(ValueError):assess(*args)

    def test_associated_source_refused(self):
        args=self.fixture();args[0]['records'][0]['sourceIndexes']=[0]
        with self.assertRaises(ValueError):assess(*args)

    def test_changed_bytes_and_quote_refused(self):
        for field in ['original','text','subject','quote']:
            args=self.fixture()
            if field=='quote':args[7][0]['citations'][1]['quote']='fabricated'
            else:args[{'original':4,'text':5,'subject':3}[field]]+=b'changed'
            with self.assertRaises(ValueError):assess(*args)

    def test_decision_and_unknown_disposition_refused(self):
        for key,value in [('humanDecision','approved'),('claimType','unknown')]:
            args=self.fixture();args[7][0][key]=value
            with self.assertRaises(ValueError):assess(*args)

    def test_revision_and_duplicate_findings_refused(self):
        args=self.fixture();args[2]['elements'][0]['containsRevisions']=True
        with self.assertRaises(ValueError):assess(*args)
        args=self.fixture();args[7].append(copy.deepcopy(args[7][0]))
        with self.assertRaises(ValueError):assess(*args)


class CriterionResponses(unittest.TestCase):
    def fixture(self):
        args=UnassociatedReview().fixture()
        args[6]['responseOptions']=['supported_finding','no_issue_in_checked_scope',
                                    'not_applicable_with_rationale','unknown_missing_evidence']
        response=dict(criterionId='need',response='no_issue_in_checked_scope',
                      claimType='inference',scope='historical_retained_text_only',
                      statement='Distinct purpose within the retained pair only',
                      rationale='No overlap in the stated purposes; current sources remain unknown',
                      findingIds=[],humanDecision=None,
                      citations=copy.deepcopy(args[7][0]['citations']))
        args[7]=[]
        return args,[response]

    def test_complete_quiet_review_is_traceable_and_does_not_approve(self):
        args,responses=self.fixture();before=copy.deepcopy((args,responses))
        report=assess(*args,criterion_responses=responses)
        self.assertEqual(report,assess(*args,criterion_responses=responses))
        self.assertEqual((args,responses),before)
        self.assertEqual(report['findings'],[])
        self.assertEqual(report['criterionResponses'],responses)
        self.assertFalse(report['currentAuthorityVerified'])
        self.assertFalse(report['catalogueIdentityAssigned'])
        self.assertIsNone(report['humanDecision'])
        self.assertEqual(content_digest(report),report['contentSHA256'])

    def test_legacy_report_shape_and_hash_stay_unchanged(self):
        args=UnassociatedReview().fixture();report=assess(*args)
        self.assertNotIn('criterionResponses',report)
        self.assertNotIn('criterionResponseVersion',report)
        self.assertEqual(report,assess(*args,criterion_responses=None))

    def test_incomplete_duplicate_and_empty_criteria_cannot_hide_review(self):
        for kind in ['empty','missing','duplicate','no-criteria','duplicate-criteria']:
            args,responses=self.fixture()
            if kind=='empty':responses=[]
            if kind=='missing':args[6]['criteria'].append(dict(criterionId='currency'))
            if kind=='duplicate':responses.append(copy.deepcopy(responses[0]))
            if kind=='no-criteria':args[6]['criteria']=[];responses=[]
            if kind=='duplicate-criteria':args[6]['criteria'].append(dict(criterionId='need'))
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                assess(*args,criterion_responses=responses)

    def test_current_scope_approval_missing_rationale_and_false_unknown_refused(self):
        for key,value in [('scope','current-compliant'),('humanDecision','approved'),
                          ('rationale',''),('response','approved'),('claimType','evidence')]:
            args,responses=self.fixture();responses[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                assess(*args,criterion_responses=responses)
        args,responses=self.fixture();responses[0]['response']='unknown_missing_evidence'
        with self.assertRaises(ValueError):assess(*args,criterion_responses=responses)

    def test_fabricated_or_one_sided_response_evidence_refused(self):
        for kind in ['fabricated','one-sided']:
            args,responses=self.fixture()
            if kind=='fabricated':responses[0]['citations'][1]['quote']='Invented'
            else:responses[0]['citations']=responses[0]['citations'][:1]
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                assess(*args,criterion_responses=responses)

    def test_no_issue_cannot_conceal_a_finding_or_supplied_link(self):
        args,responses=self.fixture();args[7]=UnassociatedReview().fixture()[7]
        with self.assertRaises(ValueError):assess(*args,criterion_responses=responses)
        args,responses=self.fixture();responses[0]['findingIds']=['invented']
        with self.assertRaises(ValueError):assess(*args,criterion_responses=responses)

    def test_supported_response_requires_matching_supported_finding(self):
        args,responses=self.fixture();responses[0].update(response='supported_finding')
        with self.assertRaises(ValueError):assess(*args,criterion_responses=responses)
        args[7]=UnassociatedReview().fixture()[7];responses[0]['findingIds']=['one']
        self.assertEqual(assess(*args,criterion_responses=responses)['findings'][0]['findingId'],'one')
        args[7][0].update(claimType='unknown',suggestedAction='seek_further_evidence')
        with self.assertRaises(ValueError):assess(*args,criterion_responses=responses)

    def test_unknown_preserves_revision_uncertainty(self):
        args,responses=self.fixture();args[2]['elements'][0]['containsRevisions']=True
        with self.assertRaises(ValueError):assess(*args,criterion_responses=responses)
        responses[0].update(response='unknown_missing_evidence',claimType='unknown')
        report=assess(*args,criterion_responses=responses)
        self.assertEqual(report['criterionResponses'][0]['response'],'unknown_missing_evidence')

    def test_not_applicable_is_scoped_rationale_not_authority(self):
        args,responses=self.fixture();responses[0]['response']='not_applicable_with_rationale'
        report=assess(*args,criterion_responses=responses)
        self.assertFalse(report['currentAuthorityVerified'])
        self.assertIsNone(report['humanDecision'])
        responses[0]['rationale']=''
        with self.assertRaises(ValueError):assess(*args,criterion_responses=responses)
