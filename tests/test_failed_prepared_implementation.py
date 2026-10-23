"""Failure assertions retain unresolved work and cannot become verification parents."""
import copy
import unittest
from build_failed_prepared_implementation import build
from build_prepared_implementation import build as normal_build, digest
from build_prepared_verification import build as verification_build
from test_prepared_implementation import fixture, flatten
from test_prepared_verification import fixture as verification_fixture
from test_prepared_closure_check import Expressions
from test_selected_prepared_verification import fixture as selected_fixture, select
from build_selected_prepared_verification import build as selected_build


class FailedImplementationTests(unittest.TestCase):
    def test_failure_profile_preserves_input_and_upstream_checks_without_new_writers(self):
        args=fixture();before=copy.deepcopy(args);normal=normal_build(*args);failed=build(*args)
        self.assertEqual(args,before)
        a=failed['properties']['definition']['actions'];n=normal['properties']['definition']['actions']
        changed={key for key in a if a[key]!=n[key]}
        self.assertEqual(changed,{'Validate_implementation_input','Implementation_payload','Native_implementation_receipt'})
        self.assertEqual(failed['properties']['connectionReferences'],normal['properties']['connectionReferences'])
        self.assertEqual(failed['properties']['state'],'Stopped')
        writers={key for key,value in flatten(a).items() if value.get('type')=='OpenApiConnection' and value['inputs']['parameters'].get('parameters/method')!='GET'}
        self.assertEqual(writers,{'Create_implementation'})
        self.assertEqual(flatten(a)['Create_implementation']['inputs']['retryPolicy'],{'type':'none'})
        self.assertFalse(a['Native_implementation_receipt']['inputs']['implementationCompletionGranted'])
        self.assertFalse(a['Native_implementation_receipt']['inputs']['progressionGranted'])

    def test_failure_preserves_full_entered_actions_evidence_and_unresolved_work(self):
        source,target,binding=fixture()
        field={'InternalName':'ImplementationActionsNote','TypeAsString':'Note','RichText':False,'AppendOnly':False,'ReadOnlyField':False}
        binding.update(implementationActionsNoteField=field,approvedImplementationActionsNoteFieldSHA256=digest(field))
        payload=build(source,target,binding)['properties']['definition']['actions']['Implementation_payload']['inputs']
        self.assertEqual(payload['RecordState'],'Recorded')
        self.assertEqual(payload['ConditionsState'],'Open')
        values={'text_2':'FICTIONAL failed work: '+'x'*1000,'text_3':'fictional://failure/evidence','text_4':'FICTIONAL unresolved work: '+'y'*1000}
        evaluator=Expressions(outputs={'Test_trigger':values})
        for key,input_name in [('ImplementationActionsNote','text_2'),('EvidenceReference','text_3'),('NextAction','text_4')]:
            self.assertEqual(evaluator.evaluate(payload[key]),values[input_name])

        self.assertLessEqual(len(evaluator.evaluate(payload['ImplementationActions'])),255)
        self.assertIn('full action note',evaluator.evaluate(payload['ImplementationActions']))

    def test_existing_verification_builder_refuses_open_failure_parent(self):
        source,target,binding=verification_fixture()
        binding['retainedImplementation']['ConditionsState']='Open'
        with self.assertRaisesRegex(ValueError,'Exact recorded fictional implementation'):
            verification_build(source,target,binding)

    def test_runtime_selector_holds_actual_failure_payload_even_with_positive_sibling(self):
        source,target,binding,case,parent=selected_fixture()
        actions=selected_build(source,target,binding)['properties']['definition']['actions']
        payload=build(*fixture())['properties']['definition']['actions']['Implementation_payload']['inputs']
        failure={**parent, **{key:value for key,value in payload.items()
                             if isinstance(value,str) and not value.startswith('@')},
                 'EventUID':'LC04-IMPL-PREPARED-FAILED', 'Id':2, 'GUID':'failure-guid'}
        selected,held,_=select(actions,case,[failure])
        self.assertIsNone(selected)
        self.assertEqual(held,'SelectedVerification_parent_valid')
        # Do not silently choose a successful sibling around unresolved failure.
        selected,held,_=select(actions,case,[failure,parent])
        self.assertIsNone(selected)
        self.assertEqual(held,'SelectedVerification_unique')
