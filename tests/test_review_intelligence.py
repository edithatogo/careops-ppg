import copy
import unittest
from scripts.ppg_review_intelligence import (
    validate_relationships, resolve_role, classify_source_standard, carry_annotations,
)


class ReviewContracts(unittest.TestCase):
    def test_cycle_across_relationship_types(self):
        rows = [dict(relationshipId='r1', fromDocumentUID='a', toDocumentUID='b',
                     type='governed_by', status='accepted'),
                dict(relationshipId='r2', fromDocumentUID='b', toDocumentUID='a',
                     type='local_variation_of', status='accepted')]
        with self.assertRaises(ValueError):
            validate_relationships(rows)
        rows[1]['status'] = 'proposed'
        self.assertTrue(validate_relationships(rows))
        rows[0]['type'] = rows[1]['type'] = 'references'
        rows[1]['status'] = 'accepted'
        self.assertTrue(validate_relationships(rows))

    def test_succession_preserves_past_and_refuses_overlap(self):
        first = dict(appointmentId='a1', roleId='r', holderId='fictional-one',
                     effectiveFrom='2026-01-01', effectiveUntil='2026-06-01',
                     status='accepted', evidenceRef='fictional://handover')
        second = dict(first, appointmentId='a2', holderId='fictional-two',
                      effectiveFrom='2026-06-01', effectiveUntil=None)
        rows = [first, second]
        original = copy.deepcopy(rows)
        self.assertEqual(resolve_role(rows, 'r', '2026-05-31')['holderId'], 'fictional-one')
        self.assertEqual(resolve_role(rows, 'r', '2026-06-01')['holderId'], 'fictional-two')
        self.assertEqual(rows, original)
        second['effectiveFrom'] = '2026-05-01'
        self.assertEqual(resolve_role(rows, 'r', '2026-05-31')['state'], 'ambiguous')
        self.assertEqual(resolve_role(rows, 'missing', '2026-05-31')['state'], 'unconfirmed')
        second['status'] = 'proposed'
        self.assertEqual(resolve_role(rows, 'r', '2026-06-01')['state'], 'unconfirmed')

    def test_vacancy_requires_explicit_accepted_evidence_not_absent_data(self):
        day='2026-06-01'
        row=dict(appointmentId='a',roleId='r',holderId=None,
                 appointmentKind='substantive',effectiveFrom='2026-01-01',
                 effectiveUntil=None,status='accepted',evidenceRef='fictional://appointment')
        self.assertEqual(resolve_role([], 'r', day)['state'],'unconfirmed')
        self.assertEqual(resolve_role([row], 'r', day)['state'],'unconfirmed')
        row['appointmentKind']='vacant'
        self.assertEqual(resolve_role([row], 'r', day)['state'],'vacant')
        row['status']='proposed'
        self.assertEqual(resolve_role([row], 'r', day)['state'],'unconfirmed')
        row.update(status='accepted',evidenceRef='')
        self.assertEqual(resolve_role([row], 'r', day)['state'],'unconfirmed')
        row.update(evidenceRef='fictional://appointment',holderId='fictional-holder')
        with self.assertRaises(ValueError):resolve_role([row], 'r', day)

    def test_source_standard_not_compliance_or_overwritten(self):
        framework = dict(frameworkEditionId='fictional-v2', requirements=[
            dict(code='1', requirementId='fictional-v2-1')])
        result = classify_source_standard(' 1 ', framework)
        self.assertEqual(result['sourceAssertion'], ' 1 ')
        self.assertEqual(result['status'], 'proposed')
        self.assertFalse(result['establishesCompliance'])
        self.assertEqual(classify_source_standard('9', framework)['status'], 'unresolved')

    def test_annotation_carry_forward_preserves_original(self):
        a = dict(annotationId='a', documentUID='d', documentVersion='1', sectionId='s',
                 status='accepted', originalText='Fictional suggestion')
        rows = [a]; original = copy.deepcopy(rows)
        self.assertTrue(carry_annotations(rows, 'd', '2', ['s'])[0]['requiresReconciliation'])
        self.assertTrue(carry_annotations(rows, 'd', '1', [])[0]['requiresReconciliation'])
        self.assertFalse(carry_annotations(rows, 'd', '1', ['s'])[0]['requiresReconciliation'])
        self.assertEqual(rows, original)
        a['status'] = 'incorporated'
        self.assertEqual(carry_annotations(rows, 'd', '2', []), [])


class CorpusAccounting(unittest.TestCase):
    def test_mentions_are_not_verified_content(self):
        from scripts.ppg_review_corpus_coverage import coverage
        candidate = {'inputCount': 2, 'sourceSha256': 'fictional', 'operations': [
            {'DocumentUID': 'd1', 'fields': {'sourceDocumentId': 'EXAMPLE-1', 'sourceTitle': 'One'}},
            {'DocumentUID': 'd2', 'fields': {'sourceDocumentId': 'EXAMPLE-2', 'sourceTitle': 'Two'}}]}
        report = coverage(candidate, [{'path': 'fictional.txt', 'sha256': 'fictional',
                                       'text': 'References\nEXAMPLE-1 is a related document.'}])
        self.assertEqual(len(report['records']), 2)
        self.assertEqual(report['matchingEntries'], 1)
        self.assertEqual(report['records'][0]['matches'][0]['line'], 2)
        self.assertFalse(report['records'][0]['documentVersionVerified'])
        self.assertEqual(report['records'][1]['coverage'], 'metadata_only')
        candidate['operations'][1]['DocumentUID'] = 'd1'
        with self.assertRaises(ValueError):
            coverage(candidate, [])


class ReviewEvidence(unittest.TestCase):
    def fixture(self):
        from pathlib import Path
        import json
        contract = json.loads(Path('templates/review-intelligence/v1.0.0/run-contract.json').read_text())
        run = {key: 'fictional' for key in contract['requiredRunFields']}
        for key in ['documentSha256', 'templateSha256', 'promptSha256']:
            run[key] = 'a' * 64
        run.update(status='completed', evidenceSnapshots=[dict(sourceId='s', sourceVersion='1', sourceSha256='b'*64)],
                   findings=[dict(findingId='f', claimType='inference', suggestedAction='minor_revision',
                                  sourceCitations=[dict(sourceId='s', sourceVersion='1', sourceSha256='b'*64, locator='p2')])],
                   runtimeIdentity=dict(executionMode='manual', provider=None, model=None,
                                        modelVersion=None, versionAvailability='not_applicable'),
                   policyApproved=False, publicationAuthorised=False, notificationsEnabled=False)
        return run

    def test_provenance_and_authority_refusal(self):
        from scripts.ppg_review_intelligence import validate_review_run
        run = self.fixture()
        self.assertTrue(validate_review_run(run))
        run['findings'][0]['sourceCitations'][0]['sourceVersion'] = '2'
        with self.assertRaises(ValueError): validate_review_run(run)
        run = self.fixture(); run['notificationsEnabled'] = True
        with self.assertRaises(ValueError): validate_review_run(run)
        run = self.fixture(); run['findings'][0]['sourceCitations'] = []
        with self.assertRaises(ValueError): validate_review_run(run)
        run['findings'][0]['claimType'] = 'unknown'
        with self.assertRaises(ValueError): validate_review_run(run)
        run['findings'][0]['suggestedAction'] = 'seek_further_evidence'
        self.assertTrue(validate_review_run(run))

    def test_change_is_not_applicability_and_retry_deduplicates(self):
        from scripts.ppg_review_intelligence import change_candidate
        baseline = dict(sourceId='s', sha256='a'*64)
        observation = dict(sourceId='s', sha256='b'*64, status='captured')
        first = change_candidate('s', baseline, observation)
        self.assertEqual(first, change_candidate('s', baseline, observation))
        self.assertFalse(first['notifyOwner'])
        self.assertFalse(first['applicabilityEstablished'])
        self.assertFalse(first['advanceBaseline'])
        failed = change_candidate('s', baseline, dict(sourceId='s', status='denied'))
        self.assertEqual(failed['state'], 'acquisition_exception')
        self.assertFalse(failed['advanceBaseline'])


if __name__ == '__main__':
    unittest.main()
