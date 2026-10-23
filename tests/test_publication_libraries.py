"""Same-library selection, safe refusal and historical preparation preservation."""
import copy
import unittest

from bind_publication_libraries import build, namespace_values
from build_multisource_case_context import digest
from build_operator_entry import _flatten
from build_prepared_binary_publication import build as publication_build
from test_prepared_binary_publication import fixture as publication_fixture
from test_prepared_closure_check import Expressions


SITE = 'https://example.invalid/site'
LIBRARIES = [
    {'libraryRoot': '/site/library-one', 'qualificationFolder': '/site/library-one/evidence',
     'libraryId': '00000000-0000-4000-8000-000000000001', 'evidenceSHA256': 'a' * 64},
    {'libraryRoot': '/site/library-two', 'qualificationFolder': '/site/library-two/evidence',
     'libraryId': '00000000-0000-4000-8000-000000000002', 'evidenceSHA256': 'b' * 64},
]


def publication():
    flow = publication_build(*publication_fixture())
    nodes = _flatten(flow['properties']['definition']['actions'])
    nodes['Native_prepared_revision']['inputs'] = {'preparationQualified': True,
        'preparedRevision': {'file': {'DocumentReference': "@body('Read_selected_case')?['evidenceDraftLink']"}}}
    return flow


def bind(flow, stage='publication', libraries=None):
    return build(flow, {'approvedDefinitionSHA256': digest(flow['properties']['definition']),
        'libraries': copy.deepcopy(LIBRARIES if libraries is None else libraries), 'stage': stage})


class PublicationLibraryTests(unittest.TestCase):
    def test_each_library_selects_its_own_complete_lookup_issued_and_proof_paths(self):
        flow = publication(); before = copy.deepcopy(flow); out = bind(flow)
        n = _flatten(out['properties']['definition']['actions'])
        for row in LIBRARIES:
            ev = Expressions(bodies={'Read_selected_case': {'evidenceDraftLink': 'https://example.invalid' + row['libraryRoot'] + '/draft.docx'},
                'Read_issued': {'UniqueId': 'issued-id', 'UIVersionLabel': '1.0'}})
            namespace = {k: ev.evaluate(v) for k, v in n['Native_prepared_revision']['inputs']['publicationNamespace'].items()}
            self.assertEqual(namespace, {'eligible': True, 'folder': row['qualificationFolder']})
            ev.outputs['Native_prepared_revision'] = {'publicationNamespace': namespace,
                'preparedRevision': {'file': {'UniqueId': 'draft-id', 'nativeVersion': '2.0'}}}
            issued = ev.evaluate(n['Issued_path']['inputs']); ev.outputs['Issued_path'] = issued
            self.assertEqual(issued, row['qualificationFolder'] + '/FICTIONAL-issued-draft-id-v2.0.docx')
            self.assertEqual(ev.evaluate(n['Binary_proof_path']['inputs']),
                row['qualificationFolder'] + '/PPG-binary-proof-issued-id-v1.0.json')
            lookup = ev.evaluate(n['Find_issued']['inputs']['parameters']['parameters/uri'])
            self.assertEqual(lookup, "_api/web/GetFolderByServerRelativePath(decodedurl='" + row['qualificationFolder']
                + "')/Files?$filter=Name eq 'FICTIONAL-issued-draft-id-v2.0.docx'&$select=Name,UniqueId,ETag,UIVersionLabel,Length,ServerRelativeUrl")
        self.assertEqual(flow, before)

    def test_unknown_external_similar_and_noncanonical_paths_cannot_open_destination_gate(self):
        n = _flatten(bind(publication())['properties']['definition']['actions'])
        values = n['Native_prepared_revision']['inputs']['publicationNamespace']
        for reference in (None, '', SITE + '/other/draft.docx',
                'https://evil.invalid/site/library-one/draft.docx',
                SITE + '/library-one-other/draft.docx', SITE + '/library-one/../other/draft.docx',
                SITE + '/library-one/draft.docx?x=1', SITE + '/library-one/%64raft.docx'):
            ev = Expressions(bodies={'Read_selected_case': {'evidenceDraftLink': reference}})
            namespace = {k: ev.evaluate(v) for k, v in values.items()}
            self.assertFalse(namespace['eligible'], reference)
            ev.outputs.update(Native_prepared_revision={'publicationNamespace': namespace},
                Verify_all_retained_purposes_check_0=True)
            self.assertFalse(ev.evaluate(n['Verify_all_retained_purposes']['expression']))

    def test_library_eligibility_never_substitutes_for_four_purpose_evidence(self):
        n = _flatten(bind(publication())['properties']['definition']['actions'])
        for purpose in (False, True):
            for eligible in (False, True):
                ev = Expressions(outputs={'Verify_all_retained_purposes_check_0': purpose,
                    'Native_prepared_revision': {'publicationNamespace': {'eligible': eligible}}})
                self.assertEqual(ev.evaluate(n['Verify_all_retained_purposes']['expression']), purpose and eligible)

    def test_every_other_action_and_all_writer_retry_content_guards_are_preserved(self):
        flow = publication(); old = _flatten(flow['properties']['definition']['actions'])
        new = _flatten(bind(flow)['properties']['definition']['actions'])
        changed = {'Native_prepared_revision', 'Issued_path', 'Find_issued', 'Binary_proof_path', 'Verify_all_retained_purposes'}
        self.assertEqual(old.keys(), new.keys())
        for name in old:
            if name in changed: continue
            # Containers carry changed descendants; compare their own behavior.
            own = lambda x: {k: v for k, v in x.items() if k not in ('actions', 'else')}
            self.assertEqual(own(old[name]), own(new[name]), name)
        self.assertEqual(flow['properties']['connectionReferences'], bind(flow)['properties']['connectionReferences'])

    def test_historical_closure_uses_resolved_old_preparation_not_later_case_pointer(self):
        frozen = {'preparationQualified': True, 'preparedRevision': {'file': {
            'DocumentReference': SITE + '/library-two/retained.docx'}}}
        current = {'preparationQualified': True, 'preparedRevision': {'file': {
            'DocumentReference': SITE + '/library-one/later-edit.docx'}}}
        flow = {'properties': {'state': 'Started', 'connectionReferences': {}, 'definition': {'actions': {
            'Read_selected_case': {'type': 'OpenApiConnection', 'runAfter': {}, 'inputs': {'parameters': {
                'parameters/method': 'GET', 'dataset': SITE}}},
            'History': {'type': 'Compose', 'runAfter': {}, 'inputs': True},
            'Historical_prepared': {'type': 'Compose', 'runAfter': {}, 'inputs': frozen},
            'Initial_prepared': {'type': 'Compose', 'runAfter': {}, 'inputs': current},
            'Native_prepared_revision': {'type': 'Compose', 'runAfter': {}, 'inputs':
                "@if(equals(outputs('History'),true),outputs('Historical_prepared'),outputs('Initial_prepared'))"},
            'Closure_selected_publication': {'type': 'Query', 'runAfter': {}, 'inputs': {}},
            'ClosureEntry_initial': {'type': 'If', 'runAfter': {}, 'actions': {}, 'else': {'actions': {}}, 'expression':
                "@and(true,startsWith(string(first(body('Closure_selected_publication'))?['EvidenceReference']),'https://example.invalid/site/qualification/'))"},
        }}}}
        out = bind(flow, 'closure'); n = _flatten(out['properties']['definition']['actions'])
        ev = Expressions(bodies={'Read_selected_case': {'evidenceDraftLink': current['preparedRevision']['file']['DocumentReference']},
            'Closure_selected_publication': [{'EvidenceReference': SITE + '/library-two/evidence/proof.json'}]},
            outputs={'History': True, 'Historical_prepared': frozen, 'Initial_prepared': current})
        resolved = ev.evaluate(n['Native_prepared_revision']['inputs'])
        self.assertEqual(resolved['preparedRevision'], frozen['preparedRevision'])
        self.assertEqual(resolved['publicationNamespace'], {'eligible': True, 'folder': '/site/library-two/evidence'})
        ev.outputs['Native_prepared_revision'] = resolved
        self.assertTrue(ev.evaluate(n['ClosureEntry_initial']['expression']))
        ev.bodies['Closure_selected_publication'][0]['EvidenceReference'] = SITE + '/library-one/evidence/proof.json'
        self.assertFalse(ev.evaluate(n['ClosureEntry_initial']['expression']))

    def test_changed_preimage_namespace_contract_and_unreviewed_bindings_refuse(self):
        for mutation in ('digest', 'folder', 'overlap', 'duplicate-id', 'changed-lookup'):
            flow = publication(); libraries = copy.deepcopy(LIBRARIES)
            binding = {'approvedDefinitionSHA256': digest(flow['properties']['definition']),
                'libraries': libraries, 'stage': 'publication'}
            if mutation == 'digest': binding['approvedDefinitionSHA256'] = '0' * 64
            elif mutation == 'folder': libraries[0]['qualificationFolder'] = '/site/library-two/wrong'
            elif mutation == 'overlap':
                libraries[1]['libraryRoot'] = '/site/library-one/nested'
                libraries[1]['qualificationFolder'] = '/site/library-one/nested/evidence'
            elif mutation == 'duplicate-id': libraries[1]['libraryId'] = libraries[0]['libraryId']
            else:
                _flatten(flow['properties']['definition']['actions'])['Find_issued']['inputs']['parameters']['parameters/uri'] += '&$top=1'
                binding['approvedDefinitionSHA256'] = digest(flow['properties']['definition'])
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): build(flow, binding)
        with self.assertRaises(ValueError): namespace_values(SITE, LIBRARIES, "triggerBody()?['path']")


if __name__ == '__main__': unittest.main()
