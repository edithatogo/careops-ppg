import copy
import unittest
from scripts.ppg_source_association import hold_title_conflict
from tests import test_pair_review


class SourceAssociation(unittest.TestCase):
    def setUp(self):
        self.fixture = test_pair_review.PairReview()
        self.fixture.setUp()
        self.fixture.prep['comparisonMatrix'][1]['title'] = 'Fictional radio procedure'

    def hold(self, prep=None, title='A distinct purpose', locator='lines=2-2', ref='fictional://evidence'):
        f = self.fixture
        return hold_title_conflict(prep or f.prep, 'c', f.original, f.text,
                                   'ID-1', title, locator, ref)

    def test_hold_preserves_inputs_prior_assertions_and_exact_replay(self):
        before = copy.deepcopy(self.fixture.prep)
        held = self.hold()
        self.assertEqual(self.fixture.prep, before)
        self.assertEqual(held['comparisonMatrix'][0], before['comparisonMatrix'][0])
        self.assertEqual({k: v for k, v in held['comparisonMatrix'][1].items()
                          if k != 'sourceAssociationHolds'}, before['comparisonMatrix'][1])
        self.assertEqual(self.hold(held), held)
        changed = copy.deepcopy(held)
        changed['comparisonMatrix'][1]['sourceAssociationHolds'][0]['resolution'] = 'Human note'
        with self.assertRaises(ValueError):
            self.hold(changed)

    def test_held_original_cannot_be_compared_as_catalogue_document(self):
        self.fixture.prep = self.hold()
        with self.assertRaisesRegex(ValueError, 'association held'):
            self.fixture.run_review()

    def test_missing_and_fabricated_evidence_refused(self):
        for kwargs in [dict(title='Invented title'), dict(locator='lines=200-201'), dict(ref='')]:
            with self.assertRaises(ValueError):
                self.hold(**kwargs)

    def test_matching_title_is_not_a_conflict(self):
        self.fixture.prep['comparisonMatrix'][1]['title'] = 'A distinct purpose'
        with self.assertRaises(ValueError):
            self.hold()

    def test_duplicate_other_catalogue_identity_refused(self):
        self.fixture.prep['comparisonMatrix'].append(
            copy.deepcopy(self.fixture.prep['comparisonMatrix'][0]))
        self.fixture.prep['catalogueCount'] = 3
        with self.assertRaises(ValueError):
            self.hold()

    def test_unrelated_original_is_not_globally_blocked(self):
        held = self.hold()
        held['comparisonMatrix'][1]['sourceAssociationHolds'][0]['originalSha256'] = 'another-source'
        self.fixture.prep = held
        self.assertEqual(self.fixture.run_review()['retainedTextPairsAssessed'], 1)


class IdentifierVariantRetrieval(unittest.TestCase):
    def setUp(self):
        import hashlib
        self.original = b'fictional-original-pdf'
        self.text = (b'Document Number: TEST-Proc-1234- 01/25\nVersion No. 2.0\n'
                     b'Fictional Shared Care\nUnrelated body text')
        sha = lambda b: hashlib.sha256(b).hexdigest()
        row = dict(documentUID='fictional', sourceDocumentId='TEST-Proc-1234-V2-01/25',
                   title='Fictional Shared Care Procedure', sourceIndexes=[],
                   otherEditionSourceIndexes=[], matchingIdentifierSourceIndexes=[],
                   coverage='metadata_only')
        self.screen = dict(catalogueCount=1, sourceCount=1, records=[row],
                           corpus=[dict(sourceSha256=sha(self.original),
                                        textSha256=sha(self.text))])
        self.ledger = dict(catalogueCount=1, comparisonMatrix=[copy.deepcopy(row)])

    def run_lead(self, screen=None, ledger=None, **changes):
        from scripts.ppg_source_association import propose_identifier_variant
        args = dict(source_index=0, document_uid='fictional',
                    original_bytes=self.original, text_bytes=self.text,
                    recorded_identifier='TEST-Proc-1234- 01/25',
                    printed_title='Fictional Shared Care', title_locator='lines=3-3',
                    document_code='1234', evidence_ref='fictional://source-proof')
        args.update(changes)
        return propose_identifier_variant(screen or self.screen, ledger or self.ledger, **args)

    def test_additive_unverified_retrieval_preserves_truth_and_replay(self):
        before = copy.deepcopy((self.screen, self.ledger))
        result = self.run_lead()
        self.assertEqual((self.screen, self.ledger), before)
        self.assertEqual(self.run_lead(result['screen']), result)
        row = result['screen']['records'][0]
        self.assertEqual(row['sourceDocumentId'], self.screen['records'][0]['sourceDocumentId'])
        self.assertEqual(row['sourceIndexes'], [0])
        self.assertEqual(row['coverage'], 'other_edition_candidate')
        self.assertFalse(result['candidate']['identityAssigned'])
        self.assertFalse(result['candidate']['currentAuthorityVerified'])
        self.assertIsNone(result['candidate']['humanDecision'])
        self.assertEqual(result['newAssessments'], 0)
        self.assertNotIn('retainedTextPairAssessment', row)

    def test_bad_bytes_passages_identifiers_and_context_refused(self):
        for changes in [dict(original_bytes=b'changed'), dict(text_bytes=self.text+b'changed'),
                        dict(printed_title='Invented'), dict(title_locator='lines=99-100'),
                        dict(recorded_identifier='NOT-1234'), dict(document_code='9999'),
                        dict(evidence_ref=''), dict(source_index=True)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.run_lead(**changes)

    def test_same_code_with_conflicting_title_or_version_refused(self):
        for key, value in [('title','Fictional Gift Register'),
                           ('sourceDocumentId','TEST-Proc-1234-V3-01/25'),
                           ('sourceDocumentId','OTHER-Proc-1234-V2-01/25')]:
            screen, ledger=copy.deepcopy((self.screen,self.ledger))
            screen['records'][0][key]=value;ledger['comparisonMatrix'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                self.run_lead(screen,ledger)

    def test_nonunique_code_family_and_incomplete_catalogue_refused(self):
        for duplicate_uid in [False, True]:
            screen, ledger=copy.deepcopy((self.screen,self.ledger))
            other=copy.deepcopy(screen['records'][0]);other['documentUID']='fictional' if duplicate_uid else 'another'
            screen['records'].append(other);ledger['comparisonMatrix'].append(copy.deepcopy(other))
            screen['catalogueCount']=ledger['catalogueCount']=2
            with self.assertRaises(ValueError):self.run_lead(screen,ledger)
        ledger=copy.deepcopy(self.ledger);ledger['catalogueCount']=2
        with self.assertRaises(ValueError):self.run_lead(ledger=ledger)

    def test_existing_hold_prior_link_and_edited_lead_refused(self):
        ledger=copy.deepcopy(self.ledger)
        ledger['comparisonMatrix'][0]['sourceAssociationHolds']=[dict(
            state='held',originalSha256=self.screen['corpus'][0]['sourceSha256'])]
        with self.assertRaisesRegex(ValueError,'held'):self.run_lead(ledger=ledger)
        screen=copy.deepcopy(self.screen);screen['records'][0]['sourceIndexes']=[0]
        with self.assertRaises(ValueError):self.run_lead(screen)
        screen=self.run_lead()['screen']
        screen['records'][0]['retrievalCandidateEvidence'][0]['humanDecision']='accepted'
        with self.assertRaises(ValueError):self.run_lead(screen)

    def test_changed_catalogue_assertion_between_snapshots_refused(self):
        ledger=copy.deepcopy(self.ledger);ledger['comparisonMatrix'][0]['title']='Other'
        with self.assertRaises(ValueError):self.run_lead(ledger=ledger)

    def test_disagreeing_printed_identifier_and_header_version_refused(self):
        import hashlib
        screen=copy.deepcopy(self.screen)
        text=self.text.replace(b'TEST-Proc-1234- 01/25',b'TEST-Proc-1234-V3-01/25')
        screen['corpus'][0]['textSha256']=hashlib.sha256(text).hexdigest()
        with self.assertRaisesRegex(ValueError,'identifier and version'):
            self.run_lead(screen,text_bytes=text,recorded_identifier='TEST-Proc-1234-V3-01/25')

    def test_duplicate_and_invalid_existing_source_indexes_refused(self):
        for indexes in [[0,0],[99],[True]]:
            screen=copy.deepcopy(self.screen);screen['records'][0]['sourceIndexes']=indexes
            with self.subTest(indexes=indexes),self.assertRaises(ValueError):self.run_lead(screen)

    def test_replay_refuses_ghost_metadata_only_coverage(self):
        screen=self.run_lead()['screen']
        screen['records'][0]['coverage']='metadata_only'
        with self.assertRaises(ValueError):self.run_lead(screen)

    def short_identifier_fixture(self, matching=True):
        import hashlib
        screen, ledger = copy.deepcopy((self.screen, self.ledger))
        identifier = 'TEST-Proc-4-V2-01/25' if matching else 'TEST-Proc-4- 01/25'
        text = self.text.replace(b'TEST-Proc-1234- 01/25', identifier.encode())
        screen['corpus'][0]['textSha256'] = hashlib.sha256(text).hexdigest()
        for row in [screen['records'][0], ledger['comparisonMatrix'][0]]:
            row['sourceDocumentId'] = 'TEST-Proc-4-V2-01/25'
        return screen, ledger, dict(text_bytes=text, recorded_identifier=identifier,
                                   document_code='4', matching_identifier=matching)

    def test_short_exact_identifier_preserves_truth_and_replays(self):
        screen, ledger, args = self.short_identifier_fixture()
        before = copy.deepcopy((screen, ledger))
        result = self.run_lead(screen, ledger, **args)
        self.assertEqual((screen, ledger), before)
        row = result['screen']['records'][0]
        self.assertEqual(row['matchingIdentifierSourceIndexes'], [0])
        self.assertEqual(row['otherEditionSourceIndexes'], [])
        self.assertEqual(row['coverage'], 'matching_catalogue_identifier')
        self.assertEqual(result['candidate']['status'], 'unverified_matching_identifier')
        self.assertFalse(result['candidate']['currentAuthorityVerified'])
        self.assertEqual(self.run_lead(result['screen'], ledger, **args), result)
        row['matchingIdentifierSourceIndexes'] = []
        with self.assertRaises(ValueError): self.run_lead(result['screen'], ledger, **args)

    def test_case_only_match_and_short_variant_have_distinct_buckets(self):
        import hashlib
        screen, ledger, args = self.short_identifier_fixture()
        args['text_bytes'] = args['text_bytes'].replace(b'TEST-Proc', b'TEST-proc')
        args['recorded_identifier'] = args['recorded_identifier'].replace('TEST-Proc', 'TEST-proc')
        screen['corpus'][0]['textSha256'] = hashlib.sha256(args['text_bytes']).hexdigest()
        self.assertEqual(self.run_lead(screen, ledger, **args)['candidate']['kind'],
                         'matching_identifier_retrieval_lead')
        screen, ledger, args = self.short_identifier_fixture(False)
        self.assertEqual(self.run_lead(screen, ledger, **args)['screen']['records'][0]
                         ['otherEditionSourceIndexes'], [0])

    def test_exact_mode_refuses_variant_title_version_and_nonboolean_mode(self):
        screen, ledger, args = self.short_identifier_fixture(False)
        args['matching_identifier'] = True
        with self.assertRaises(ValueError): self.run_lead(screen, ledger, **args)

        screen, ledger, args = self.short_identifier_fixture()
        for changes in [dict(printed_title='Other title'), dict(matching_identifier=1)]:
            with self.assertRaises(ValueError): self.run_lead(screen, ledger, **(args | changes))
        screen['records'][0]['sourceDocumentId'] = ledger['comparisonMatrix'][0]['sourceDocumentId'] = 'TEST-Proc-4-V3-01/25'
        with self.assertRaises(ValueError): self.run_lead(screen, ledger, **args)

    def test_unique_complete_id_does_not_depend_on_unrelated_numeric_code(self):
        screen, ledger, args = self.short_identifier_fixture()
        other = copy.deepcopy(screen['records'][0])
        other.update(documentUID='unrelated', sourceDocumentId='TEST-Clin-4-V7-01/25')
        screen['records'].append(other)
        ledger['comparisonMatrix'].append(copy.deepcopy(other))
        screen['catalogueCount'] = ledger['catalogueCount'] = 2
        self.assertEqual(self.run_lead(screen, ledger, **args)['candidate']['documentUID'], 'fictional')
        screen['records'][1]['sourceDocumentId'] = ledger['comparisonMatrix'][1]['sourceDocumentId'] = args['recorded_identifier']
        with self.assertRaises(ValueError): self.run_lead(screen, ledger, **args)


class HeaderDiscovery(unittest.TestCase):
    def fixture(self):
        import hashlib
        rows=[dict(documentUID='one',title='Fictional first procedure',
                   sourceDocumentId='TEST-Proc-44-V2-01/25',sourceIndexes=[]),
              dict(documentUID='two',title='Fictional clinical discharge',
                   sourceDocumentId='TEST-Clin-4-V7-01/25',sourceIndexes=[])]
        texts={0:b'Document Number: TEST-Proc-44-V2-01/25\nTitle',
               1:b'Document Number: TEST-Pol-Fin-4-V2-01/25\nOther policy',
               2:b'A supporting leaflet with no printed identifier'}
        sources=[dict(sourceSha256='fictional-original-'+str(i),
                      textSha256=hashlib.sha256(texts[i]).hexdigest()) for i in texts]
        screen=dict(catalogueCount=2,sourceCount=3,records=rows,corpus=sources)
        status=dict(sources=[dict(sourceIndex=i,state='unassociated_unassessed',
                                 retrievalAssociations=[]) for i in texts])
        return screen,status,texts

    def run_discovery(self,*args):
        from scripts.ppg_source_association import discover_printed_identifier_leads
        return discover_printed_identifier_leads(*(args or self.fixture()))

    def test_accounts_all_sources_without_binding_or_excluding_leaflets(self):
        args=self.fixture();before=copy.deepcopy(args);r=self.run_discovery(*args)
        self.assertEqual(args,before);self.assertEqual(r,self.run_discovery(*args))
        self.assertEqual(r['unassociatedSourcesAccounted'],3)
        self.assertEqual(r['discoveryCounts'],dict(case_insensitive_printed_id_match=1,
             numeric_code_collision_different_family=1,no_printed_header_in_checked_prefix=1))
        self.assertEqual(r['newRetrievalLinks'],0);self.assertEqual(r['newSemanticAssessments'],0)
        self.assertTrue(r['noHeaderDoesNotExcludeCatalogueMembership'])
        self.assertFalse(any(x['catalogueIdentityAssigned'] for x in r['sources']))
        self.assertIsNone(r['humanDecision'])

    def test_changed_bytes_incomplete_inputs_or_false_link_refused(self):
        for kind in ['bytes','missing-text','count','linked-state','linked-row']:
            s,status,texts=self.fixture()
            if kind=='bytes':texts[0]+=b'changed'
            if kind=='missing-text':del texts[2]
            if kind=='count':s['catalogueCount']=99
            if kind=='linked-state':status['sources'][0]['retrievalAssociations']=['already-linked']
            if kind=='linked-row':s['records'][0]['sourceIndexes']=[0]
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                self.run_discovery(s,status,texts)

    def test_other_version_is_only_a_family_lead(self):
        import hashlib
        s,status,texts=self.fixture();texts[0]=b'Document Number: TEST-Proc-44-V1-0124\nTitle'
        s['corpus'][0]['textSha256']=hashlib.sha256(texts[0]).hexdigest()
        r=self.run_discovery(s,status,texts)
        self.assertEqual(r['sources'][0]['discoveryState'],'unique_identifier_family_lead')
        self.assertFalse(r['sources'][0]['currentAuthorityVerified'])

    def test_second_page_identifier_not_promoted_and_no_header_not_absence(self):
        import hashlib
        s,status,texts=self.fixture();texts[0]=b'Cover only\fDocument Number: TEST-Proc-44-V2-01/25'
        s['corpus'][0]['textSha256']=hashlib.sha256(texts[0]).hexdigest()
        r=self.run_discovery(s,status,texts)
        self.assertEqual(r['sources'][0]['discoveryState'],'no_printed_header_in_checked_prefix')
        self.assertTrue(r['noHeaderDoesNotExcludeCatalogueMembership'])

    def test_ambiguous_identifier_never_selects_a_catalogue_entry(self):
        s,status,texts=self.fixture();s['records'][1]['sourceDocumentId']=s['records'][0]['sourceDocumentId']
        r=self.run_discovery(s,status,texts)
        self.assertEqual(r['sources'][0]['discoveryState'],'ambiguous_catalogue_identifier_lead')
        self.assertEqual(len(r['sources'][0]['observedHeaders'][0]['candidateCatalogueAssertions']),2)
        self.assertEqual(r['newRetrievalLinks'],0)
