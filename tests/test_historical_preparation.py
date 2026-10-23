"""Historical closure uses each source's reviewed preparation namespace."""
import copy
import unittest

from bind_historical_preparation import build
from build_multisource_case_context import digest, _preparation_folder_fragments
from build_operator_entry import _flatten, _literal
from test_prepared_closure_check import Expressions

SITE = 'https://example.invalid/site'
UIDS = ['00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002']


def fixture():
    prefix = SITE + '/library-two/prepared/'
    guard = ("@and(equals(outputs('Read_prepared_case')?['headers']?['ETag'],outputs('Selected_case_context')?['caseETag']),"
        "equals(body('Read_prepared_case')?['CaseUID'],outputs('Selected_case_context')?['CaseUID']),"
        "startsWith(outputs('Prepared_document_reference')," + _literal(prefix) + "),"
        "endsWith(toLower(outputs('Prepared_document_reference')),'.docx'),"
        + ','.join("not(contains(outputs('Prepared_document_reference')," + _literal(x) + '))'
            for x in ["'", '..', '?', '#', '%']) + ')')
    lookup = "@concat(" + _literal("_api/web/GetFolderByServerRelativePath(decodedurl='/site/library-two/prepared')/Files?$filter=Name eq '") + ",body('Read_prepared_file_before')?['Name'])"
    receipt = "@concat(" + _literal(prefix) + ",body('Read_prepared_file_before')?['Name'])"
    folders = {'originalFolder': '/site/library-two/prepared', 'additionalFolder': '/site/library-one/prepared',
        'selectionGuardSHA256': digest(guard), 'receiptLookupSHA256': digest(lookup), 'receiptReferenceSHA256': digest(receipt)}
    fragments = _preparation_folder_fragments(SITE, UIDS[0], folders)
    hp = lambda s: s.replace("('Read_prepared_", "('HP_Read_prepared_").replace("('Prepared_document_reference'", "('HP_Prepared_document_reference'")
    compose = lambda value: {'type': 'Compose', 'runAfter': {}, 'inputs': value}
    actions = {name: compose({}) for name in ['Read_prepared_case', 'HP_Read_prepared_case',
        'Prepared_document_reference', 'HP_Prepared_document_reference', 'Read_prepared_file_before', 'HP_Read_prepared_file_before']}
    actions.update({
        'Read_selected_case': {'type': 'OpenApiConnection', 'runAfter': {}, 'inputs': {'parameters': {'dataset': SITE, 'parameters/method': 'GET'}}},
        'SourceProfiles_configured': compose([{'UniqueId': uid} for uid in UIDS]),
        'SourceProfiles_selected': compose({'UniqueId': UIDS[0]}),
        'Selected_case_context': compose({'limits': {'additionalPreparationContextSource': UIDS[0], 'additionalPreparationArtifactFolders': folders}}),
        'Verify_prepared_selection': {'type': 'If', 'runAfter': {}, 'expression': guard.replace(*fragments[0]), 'actions': {}, 'else': {'actions': {}}},
        'Find_prepared_receipt': {'type': 'OpenApiConnection', 'runAfter': {}, 'inputs': {'parameters': {'dataset': SITE, 'parameters/method': 'GET', 'parameters/uri': lookup.replace(*fragments[1])}}},
        'ClosureEntry_initial_prepared': compose({'preparedRevision': {'qualificationReceipt': {'DocumentReference': receipt.replace(*fragments[0])}}}),
        'HP_Verify_prepared_selection': {'type': 'If', 'runAfter': {}, 'expression': hp(guard), 'actions': {}, 'else': {'actions': {}}},
        'HP_Find_prepared_receipt': {'type': 'OpenApiConnection', 'runAfter': {}, 'inputs': {'parameters': {'dataset': SITE, 'parameters/method': 'GET', 'parameters/uri': hp(lookup)}}},
        'HP_Native_prepared_revision': compose({'preparedRevision': {'qualificationReceipt': {'DocumentReference': hp(receipt)}}}),
        'Existing_writer': {'type': 'OpenApiConnection', 'runAfter': {}, 'inputs': {'parameters': {'dataset': SITE, 'parameters/method': 'POST', 'parameters/body': 'retained conditional write'}}},
    })
    return {'name': 'retained-closure', 'properties': {'state': 'Started', 'connectionReferences': {'existing': 'unchanged'}, 'definition': {'triggers': {}, 'actions': actions}}}


def repair(flow):
    return build(flow, {'approvedDefinitionSHA256': digest(flow['properties']['definition'])})


def evaluator(uid, reference, token='case-token'):
    return Expressions(outputs={'SourceProfiles_selected': {'UniqueId': uid},
        'Selected_case_context': {'CaseUID': 'fictional-case', 'caseETag': 'case-token'},
        'HP_Read_prepared_case': {'headers': {'ETag': token}}, 'HP_Prepared_document_reference': reference},
        bodies={'HP_Read_prepared_case': {'CaseUID': 'fictional-case'}, 'HP_Read_prepared_file_before': {'Name': 'receipt-v3.json'}})


class HistoricalPreparationTests(unittest.TestCase):
    def test_regression_first_source_history_no_longer_requires_other_sources_folder(self):
        flow = fixture(); before = _flatten(flow['properties']['definition']['actions']); after = _flatten(repair(flow)['properties']['definition']['actions'])
        for uid, folder in zip(UIDS, ['library-one', 'library-two']):
            ev = evaluator(uid, SITE + '/' + folder + '/prepared/current.docx')
            self.assertEqual(ev.evaluate(before['HP_Verify_prepared_selection']['expression']), uid == UIDS[1])
            self.assertTrue(ev.evaluate(after['HP_Verify_prepared_selection']['expression']))
            self.assertIn('/' + folder + '/prepared', ev.evaluate(after['HP_Find_prepared_receipt']['inputs']['parameters']['parameters/uri']))
            self.assertEqual(ev.evaluate(after['HP_Native_prepared_revision']['inputs']['preparedRevision']['qualificationReceipt']['DocumentReference']), SITE + '/' + folder + '/prepared/receipt-v3.json')

    def test_wrong_source_folder_external_path_traversal_and_case_token_still_refuse(self):
        n = _flatten(repair(fixture())['properties']['definition']['actions'])
        for uid, own, wrong in [(UIDS[0], 'library-one', 'library-two'), (UIDS[1], 'library-two', 'library-one')]:
            for path in [SITE + '/' + wrong + '/prepared/a.docx', 'https://evil.invalid/a.docx',
                    SITE + '/' + own + '/prepared/../a.docx', SITE + '/' + own + '/prepared/a.docx?q=1',
                    SITE + '/' + own + '/prepared/%61.docx', SITE + '/' + own + '/prepared/a.txt']:
                self.assertFalse(evaluator(uid, path).evaluate(n['HP_Verify_prepared_selection']['expression']), path)
            self.assertFalse(evaluator(uid, SITE + '/' + own + '/prepared/a.docx', 'changed-token').evaluate(n['HP_Verify_prepared_selection']['expression']))

    def test_only_three_historical_leaves_change_with_writers_connections_and_input_untouched(self):
        flow = fixture(); original = copy.deepcopy(flow); out = repair(flow)
        before = _flatten(flow['properties']['definition']['actions']); after = _flatten(out['properties']['definition']['actions'])
        own = lambda node: {k: v for k, v in node.items() if k not in ['actions', 'else']}
        self.assertEqual({k for k in before if own(before[k]) != own(after[k])},
            {'HP_Verify_prepared_selection', 'HP_Find_prepared_receipt', 'HP_Native_prepared_revision'})
        self.assertEqual(flow, original)
        self.assertEqual(out['properties']['connectionReferences'], flow['properties']['connectionReferences'])
        self.assertEqual(out['properties']['definition']['triggers'], flow['properties']['definition']['triggers'])
        self.assertEqual(out['properties']['state'], 'Stopped')

    def test_changed_preimage_or_guard_or_lookup_or_reference_is_rejected(self):
        for mutation in ['digest', 'primary', 'historical', 'writer', 'reference']:
            flow = fixture(); n = _flatten(flow['properties']['definition']['actions'])
            if mutation == 'primary': n['Verify_prepared_selection']['expression'] = '@true'
            if mutation == 'historical': n['HP_Verify_prepared_selection']['expression'] += 'changed'
            if mutation == 'writer': n['HP_Find_prepared_receipt']['inputs']['parameters']['parameters/method'] = 'POST'
            if mutation == 'reference': n['HP_Native_prepared_revision']['inputs']['preparedRevision']['qualificationReceipt']['DocumentReference'] = '@true'
            binding = {'approvedDefinitionSHA256': '0' * 64 if mutation == 'digest' else digest(flow['properties']['definition'])}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): build(flow, binding)


if __name__ == '__main__': unittest.main()
