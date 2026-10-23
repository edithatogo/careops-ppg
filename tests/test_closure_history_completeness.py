"""Incomplete native pages must refuse even when their visible rows match."""
import copy
import unittest

from build_operator_entry import _flatten
from build_prepared_closure_check import build_actions as observer
from build_prepared_closure_transition import build_actions as transition
import test_native_completed_review as completed_review_tests
from test_native_closure_entry import fixture as binding_fixture, collect
from test_prepared_closure_check import fixture as observer_fixture, Expressions, SCOPE
from test_prepared_closure_transition import fixture as transition_fixture

MARKERS = ('nextLink', 'odata.nextLink', '@odata.nextLink', '@nextLink')


def observed_chain(wrapper):
    context, binding, _ = observer_fixture(True)
    work = observer(context, binding)['Closure_check_chain']['actions']
    ev = Expressions({'Closure_assurance_before': wrapper,
                      'Closure_Readiness_scope': [{'AssessedOn': '2026-10-18T14:00:00Z'}]}, {
        'Native_prepared_revision': {'preparedRevision': {'scope': SCOPE}},
        'Closure_Native_readiness_observation': {'selectedEventUID': 'FICTIONAL-ready'}})
    for name, action in work.items():
        if name == 'Closure_assurance_before':
            continue
        if action['type'] in ('Select', 'Query'):
            rows = []
            for row in ev.evaluate(action['inputs']['from']):
                ev.current = row
                if action['type'] == 'Select':
                    rows.append(ev.evaluate(action['inputs']['select']))
                elif ev.evaluate(action['inputs']['where']):
                    rows.append(row)
            ev.bodies[name] = rows
        elif action['type'] == 'Compose':
            ev.outputs[name] = ev.evaluate(action['inputs'])
        else:
            raise AssertionError('Unexpected action before chain result')
        if name == 'Closure_chain_consistent':
            return ev.outputs[name]
    raise AssertionError('Missing actual chain expression')


class ClosureHistoryCompletenessTests(unittest.TestCase):
    def test_current_selector_refuses_every_continuation_marker(self):
        driver = completed_review_tests.CurrentClosureObserverTests()
        _, _, rows, _ = driver.fixture()
        self.assertIsNotNone(driver.select(wrapper={'value': rows})[2])
        for key in MARKERS:
            with self.subTest(marker=key):
                self.assertIsNone(driver.select(wrapper={'value': rows, key: 'more'})[2])

    def test_canonical_chain_refuses_every_continuation_marker(self):
        _, _, rows = observer_fixture(True)
        self.assertTrue(observed_chain({'value': rows}))
        for key in MARKERS:
            with self.subTest(marker=key):
                self.assertFalse(observed_chain({'value': rows, key: 'more'}))

    def test_matching_partial_binding_wrappers_never_become_complete(self):
        _, _, actions, ev = binding_fixture()
        self.assertTrue(collect(actions, ev))
        for key in MARKERS:
            with self.subTest(marker=key):
                _, _, actions, ev = binding_fixture()
                for phase in ('read', 'check'):
                    ev.bodies['ClosureEntry_' + phase + '_consultation'][key] = 'more'
                self.assertFalse(collect(actions, ev))

    def test_receipt_cardinality_does_not_hide_partial_result(self):
        reference, binding = transition_fixture()
        nodes = _flatten(transition(reference, binding))
        bodies = {'Cycle_case': {'CaseUID': binding['expectedCaseUID']},
                  **{'Cycle_find_' + k: {'value': []} for k in ('before', 'after', 'commit')}}
        outputs = {'Cycle_case': {'headers': {'ETag': '"3"'}},
                   'Cycle_current_complete': True,
                   'Cycle_current_snapshot': binding['expectedEvidence'],
                   'Cycle_expected_evidence': binding['expectedEvidence']}
        expression = nodes['Cycle_reads_valid']['inputs']
        self.assertTrue(Expressions(bodies, outputs).evaluate(expression))
        for key in MARKERS:
            with self.subTest(marker=key):
                partial = copy.deepcopy(bodies)
                partial['Cycle_find_after'][key] = 'more'
                self.assertFalse(Expressions(partial, outputs).evaluate(expression))


if __name__ == '__main__':
    unittest.main()
