"""Exercise source-specific closure requirements on canonical coverage/decision checks."""
import copy
import json
import unittest

from build_reusable_closure_route import bind_review_routes
from build_native_completed_review import _apply_source_review_requirements
from build_prepared_closure_check import build_actions
from build_operator_entry import _flatten
from test_prepared_closure_check import fixture as closure_fixture, Expressions, SCOPE


def fixture():
    context, binding, _ = closure_fixture()
    routes = []
    for number in (1, 2):
        routes.append(('00000000-0000-4000-8000-00000000000' + str(number), {
            'requiredFictionalRoles': ['FICTIONAL role ' + str(number)],
            'purposeReferences': {purpose: 'fictional://route' + str(number) + '/' + purpose
                for purpose in ('committee', 'officer', 'coordinator', 'authorisation')}}))
    seed = routes[1]
    binding['requiredFictionalRoles'] = seed[1]['requiredFictionalRoles']
    binding['purposeReferences'] = seed[1]['purposeReferences']
    graph = build_actions(context, binding)
    nodes = _flatten(graph)
    _apply_source_review_requirements(nodes, [seed], binding['requiredFictionalRoles'], binding['purposeReferences'])
    for purpose in seed[1]['purposeReferences']:
        graph['CurrentClosure_select_' + purpose] = {'type': 'Query', 'runAfter': {}, 'inputs': {
            'from': "@body('CurrentClosure_scoped')", 'where': "@and(equals(item()?['Stage'],'Decision'),equals(item()?['DecisionReference'],'"
                + seed[1]['purposeReferences'][purpose] + "'))"}}
    return graph, routes


class ReusableClosureTests(unittest.TestCase):
    def test_each_source_requires_its_own_role_and_decision_route(self):
        graph, routes = fixture(); nodes = _flatten(graph)
        bind_review_routes(nodes, routes, routes[1][0])
        for uid, plan in routes:
            ev = Expressions(outputs={'Selected_case_context': {'sourcePins': {'UniqueId': uid}},
                'Closure_Ready_consultation_R0_Complete': False}, bodies={
                'Closure_Ready_consultation_R0_Rows': [], 'Closure_Ready_consultation_R0_Requests': [],
                'Closure_Ready_consultation_R0_Responses': []})
            for _, other in routes:
                ev.current = {'SubjectRole': other['requiredFictionalRoles'][0]}
                self.assertEqual(ev.evaluate(nodes['Closure_Ready_consultation_R0_Rows']['inputs']['where']), other == plan)
                for purpose, reference in other['purposeReferences'].items():
                    ev.current = {'Stage': 'Decision', 'DecisionReference': reference}
                    self.assertEqual(ev.evaluate(nodes['CurrentClosure_select_' + purpose]['inputs']['where']), other == plan)
            # Missing consultation cannot become complete merely because a role
            # was required only by the other source in the historical profile.
            self.assertFalse(ev.evaluate(nodes['Closure_Ready_consultation_R0_Complete']['inputs']))
            receipt = ev.evaluate(nodes['Closure_Ready_consultation_Receipt']['inputs']['requiredRoleResults'])
            self.assertEqual(receipt, [{'SubjectRole': plan['requiredFictionalRoles'][0], 'complete': False,
                                      'requestCount': 0, 'responseCount': 0}])

    def test_unknown_source_is_refused_by_coverage_runtime_guard(self):
        graph, routes = fixture(); nodes = _flatten(graph); bind_review_routes(nodes, routes, routes[1][0])
        for uid in [routes[0][0], routes[1][0], 'unknown']:
            ev = Expressions(outputs={'Selected_case_context': {'sourcePins': {'UniqueId': uid}, 'CaseUID': SCOPE['CaseUID']},
                'Native_prepared_revision': {'preparationQualified': True, 'consultationOpenable': True,
                    'originalSourceIsPreparedRevision': False, 'preparedRevision': {'scope': SCOPE,
                        'originalSourceScope': {'DocumentReference': 'https://example.invalid/source'}}}})
            self.assertEqual(ev.evaluate(nodes['Closure_Ready_consultation_Runtime_guard']['expression']), uid != 'unknown')

    def test_existing_frame_writers_and_reads_are_unchanged(self):
        graph, routes = fixture(); before = copy.deepcopy(graph)
        nodes = _flatten(graph); original = _flatten(before)
        bind_review_routes(nodes, routes, routes[1][0])
        permitted = {'Closure_Ready_consultation_Problems', 'Closure_Ready_consultation_R0_Rows',
            'Closure_Ready_consultation_R0_Complete', 'Closure_Ready_consultation_Receipt', 'Closure_Ready_consultation_Runtime_guard'}
        permitted |= {'CurrentClosure_select_' + p for p in routes[1][1]['purposeReferences']}
        permitted |= {'Closure_selected_' + p + '_valid' for p in routes[1][1]['purposeReferences']}
        for name in nodes:
            if name in permitted: continue
            a = {k: v for k, v in nodes[name].items() if k not in ('actions', 'else')}
            b = {k: v for k, v in original[name].items() if k not in ('actions', 'else')}
            self.assertEqual(a, b, name)

    def test_unknown_seed_changed_cardinality_or_changed_canonical_guard_refuse(self):
        for mutation in ('seed', 'cardinality', 'guard'):
            graph, routes = fixture(); nodes = _flatten(graph)
            uid = routes[1][0]
            if mutation == 'seed': uid = 'unknown'
            elif mutation == 'cardinality': routes[0][1]['requiredFictionalRoles'].append('FICTIONAL extra')
            else: nodes['CurrentClosure_select_committee']['inputs']['where'] = '@true'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                bind_review_routes(nodes, routes, uid)


if __name__ == '__main__': unittest.main()
