import copy
import hashlib
import json
import unittest

from scripts.ppg_native_standards import context, validate_snapshot
from tests import test_standards_recovery as recovery_fixtures


class NativeStandards(unittest.TestCase):
    def setUp(self):
        self.source = recovery_fixtures.StandardsRecovery().fixture()
        self.inspection = b'fictional inspected historical document'
        self.sha = hashlib.sha256(self.inspection).hexdigest()
        self.set_row('frameworks', FrameworkKey='f', EditionStatus='Published')
        self.set_row('requirements', RequirementKey='r', FrameworkKey='f',
                     ParentRequirementKey=None)
        self.set_row('mappings', MappingKey='m', DocumentUID='a', DocumentVersion='V1',
            RequirementKey='r', MappingState='Proposed',
            EvidenceRef=json.dumps(dict(inspectedSourceSha256=self.sha, establishesCompliance=False)))
        self.set_row('relationships', RelationshipKey='link', FromDocumentUID='a',
            ToDocumentUID='b', FromVersion='V1', ToVersion='V2', RelationshipType='references',
            ReviewState='Proposed', EvidenceRef=json.dumps(dict(derivedPackageSha256=self.sha)))

    def set_row(self, slot, **fields):
        register = self.source['registers'][slot]
        register['items']['value'][0].update(fields)
        register['histories'][0]['versions']['value'][0].update(fields)

    def audit(self, known=None):
        return validate_snapshot(json.dumps(self.source).encode(), ['a', 'b'] if known is None else known)

    def test_current_native_records_proposals_and_provenance_are_preserved(self):
        before = copy.deepcopy(self.source)
        result = self.audit()
        self.assertEqual(result['summary']['recordCount'], 4)
        self.assertEqual(result['summary']['acceptedRelationships'], 0)
        self.assertFalse(result['actorAuthorityVerified'])
        self.assertFalse(result['evidenceReferencesVerified'])
        self.assertFalse(result['establishesCompliance'])
        self.assertEqual(self.source, before)
        self.assertEqual(self.audit(), result)

    def test_foreign_requirement_and_draft_obligation_are_refused(self):
        self.set_row('mappings', RequirementKey='missing')
        with self.assertRaises(ValueError): self.audit()
        self.set_row('mappings', RequirementKey='r', EvidenceRef=json.dumps(dict(currentObligation=True)))
        self.set_row('frameworks', EditionStatus='Draft')
        with self.assertRaises(ValueError): self.audit()

    def test_source_citations_are_not_review_decision_evidence(self):
        for value in [None, '', [], {'citation': 'fictional'}, '   ']:
            self.set_row('mappings', MappingState='Reviewed',
                EvidenceRef=json.dumps(dict(citations=['fictional source'], reviewEvidenceRef=value)))
            with self.subTest(value=value):
                with self.assertRaises(ValueError): self.audit()
        self.set_row('mappings', EvidenceRef=json.dumps(dict(reviewEvidenceRef='fictional://human-decision')))
        result = self.audit()
        self.assertEqual(result['summary']['reviewedMappings'], 1)
        self.assertFalse(result['actorAuthorityVerified'])

    def test_unresolved_proposed_document_is_visible_and_cannot_be_accepted(self):
        self.set_row('relationships', ToDocumentUID='unregistered')
        self.assertEqual(self.audit()['summary']['unresolvedDocumentReferences'], 1)
        self.set_row('relationships', ReviewState='Accepted',
                     EvidenceRef=json.dumps(dict(reviewEvidenceRef='fictional://decision')))
        with self.assertRaises(ValueError): self.audit()

    def test_unknown_choices_history_drift_and_partial_exports_are_refused(self):
        before = copy.deepcopy(self.source)
        for case in ['choice', 'history', 'page']:
            self.source = copy.deepcopy(before)
            if case == 'choice': self.set_row('mappings', MappingState='Approve')
            if case == 'history': self.source['registers']['mappings']['items']['value'][0]['Title'] = 'Human edit'
            if case == 'page': self.source['registers']['mappings']['items']['@odata.nextLink'] = 'more'
            with self.subTest(case=case):
                with self.assertRaises(ValueError): self.audit()

    def test_accepted_hierarchy_cycle_is_refused_but_reciprocal_references_work(self):
        self.set_row('relationships', RelationshipType='governed_by', ReviewState='Accepted',
                     EvidenceRef=json.dumps(dict(reviewEvidenceRef='fictional://decision')))
        register = self.source['registers']['relationships']
        other = copy.deepcopy(register['items']['value'][0])
        other.update(Id=2, RelationshipKey='reverse', FromDocumentUID='b', ToDocumentUID='a')
        register['items']['value'].append(other)
        history = copy.deepcopy(register['histories'][0])
        history['id'] = 2
        history['versions']['value'][0].update(RelationshipKey='reverse', FromDocumentUID='b', ToDocumentUID='a')
        register['histories'].append(history)
        with self.assertRaises(ValueError): self.audit()
        for row in register['items']['value']:
            row['RelationshipType'] = 'references'
        for h in register['histories']:
            h['versions']['value'][0]['RelationshipType'] = 'references'
        self.assertEqual(self.audit()['summary']['acceptedRelationships'], 2)

    def test_hash_grouping_preserves_labels_and_never_merges_accepted_graph(self):
        self.set_row('mappings', DocumentVersion='Historical inspection label')
        raw = json.dumps(self.source).encode()
        result = context(raw, ['a', 'b'], 'a', 'V1', self.inspection)
        self.assertEqual(result['mappings'], [])
        self.assertEqual(len(result['otherVersionMappings']), 1)
        self.assertEqual(len(result['directProposed']), 1)
        bound = result['inspectionBoundProposals']
        self.assertEqual(len(bound['mappings']), 1)
        self.assertEqual(len(bound['relationships']), 1)
        self.assertEqual(bound['mappings'][0]['DocumentVersion'], 'Historical inspection label')
        self.assertFalse(bound['versionLabelsMerged'])
        self.assertFalse(bound['appliesToRequestedEdition'])
        self.assertEqual(result['acceptedUpstream'], [])
        changed = context(raw, ['a', 'b'], 'a', 'V1', b'other inspection')
        self.assertEqual(changed['inspectionBoundProposals']['mappings'], [])
        self.assertEqual(changed['inspectionBoundProposals']['relationships'], [])
        self.set_row('relationships', EvidenceRef=json.dumps(dict(
            derivedPackageSha256=self.sha, subjectInspectionSHA256='b' * 64)))
        conflict = context(json.dumps(self.source).encode(), ['a', 'b'], 'a', 'V1', self.inspection)
        self.assertEqual(conflict['inspectionBoundProposals']['relationships'], [])
        self.assertEqual(len(conflict['directProposed']), 1)  # Original conflict is retained.

    def test_subject_and_identity_inventory_cannot_be_ambiguous(self):
        with self.assertRaises(ValueError): self.audit(['a', 'a'])
        raw = json.dumps(self.source).encode()
        with self.assertRaises(ValueError): context(raw, ['a', 'b'], 'missing', 'V1')
        with self.assertRaises(ValueError): context(raw, ['a', 'b'], 'a', '')

    def test_reviewed_crosswalk_needs_decision_and_known_target(self):
        register = self.source['registers']['crosswalks']
        row = dict(Title='Fictional correspondence', CrosswalkKey='cross',
            FromRequirementKey='r', ToRequirementKey='missing', Correspondence='Uncertain',
            ReviewState='Reviewed', Rationale='Fictional only', EvidenceRef='fictional source')
        register['items']['value'] = [dict(row, Id=1, GUID='fictional-cross', Attachments=False,
                                         OData__UIVersionString='1.0')]
        register['histories'] = [dict(id=1, versions={'value': [dict(row, VersionLabel='1.0')]})]
        with self.assertRaisesRegex(ValueError, 'separately recorded decision'): self.audit()
        self.set_row('crosswalks', EvidenceRef=json.dumps(dict(reviewEvidenceRef='fictional://decision')))
        with self.assertRaisesRegex(ValueError, 'requirement missing'): self.audit()
