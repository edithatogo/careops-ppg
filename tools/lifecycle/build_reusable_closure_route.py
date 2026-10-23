"""Bind the reviewed two-source closure to each source's own review route.

Pure composition of existing closure actions. No new writer, flow, lookup,
recovery protocol or date rule is introduced. Native qualification is separate.
"""
import copy
import json

from build_multisource_case_context import digest, validate_sources, _operation_expression, match_expression
from build_native_completed_review import _source_review_requirements
from build_native_closure_entry import _check_expression_lengths
from build_operator_entry import _flatten, _literal, action_references
from build_selected_event_routes import audit_actions


SOURCE = "toLower(string(coalesce(outputs('Selected_case_context')?['sourcePins']?['UniqueId'],'')))"
PURPOSES = ('committee', 'officer', 'coordinator', 'authorisation')


def choose(routes, value):
    expression = 'null'
    for uid, route in reversed(routes):
        expression = 'if(equals(' + SOURCE + ',' + _literal(uid) + '),' + value(route) + ',' + expression + ')'
    return expression


def role_record(role):
    record = 'json(' + _literal(json.dumps({'SubjectRole': role}, separators=(',', ':'))) + ')'
    for key, value in [('complete', "outputs('Closure_Ready_consultation_R0_Complete')"),
                       ('requestCount', "length(body('Closure_Ready_consultation_R0_Requests'))"),
                       ('responseCount', "length(body('Closure_Ready_consultation_R0_Responses'))")]:
        record = 'setProperty(' + record + ',' + _literal(key) + ',' + value + ')'
    return record


def replace_once(value, old, new):
    if not isinstance(value, str) or value.count(old) != 1:
        raise ValueError('Canonical source-specific closure expression changed')
    return value.replace(old, new)


def bind_review_routes(nodes, routes, seed_uid):
    """Keep one coverage group where each reviewed source requires one role."""
    if len(routes) != 2 or any(len(route['requiredFictionalRoles']) != 1 for _, route in routes):
        raise ValueError('Two reviewed single-role routes required; cardinality changes need separate qualification')
    seed = [(uid, route) for uid, route in routes if uid == seed_uid]
    if len(seed) != 1:
        raise ValueError('Exact original reviewed closure source required')
    old_routes = seed
    role = seed[0][1]['requiredFictionalRoles'][0]
    required = lambda route: 'createArray(' + _literal(route['requiredFictionalRoles'][0]) + ')'
    old_required, new_required = choose(old_routes, required), choose(routes, required)
    selected_role = choose(routes, lambda route: _literal(route['requiredFictionalRoles'][0]))
    problems = nodes['Closure_Ready_consultation_Problems']['inputs']
    problems['where'] = replace_once(problems['where'], old_required, new_required)
    rows = nodes['Closure_Ready_consultation_R0_Rows']['inputs']
    rows['where'] = replace_once(rows['where'], _literal(role), selected_role)
    complete = nodes['Closure_Ready_consultation_R0_Complete']
    complete['inputs'] = replace_once(complete['inputs'],
        '@if(contains(' + old_required + ',' + _literal(role) + '),',
        '@if(contains(' + new_required + ',' + selected_role + '),')
    receipt = nodes['Closure_Ready_consultation_Receipt']['inputs']
    original_receipt = '@' + choose(old_routes, lambda route: 'createArray(' + role_record(route['requiredFictionalRoles'][0]) + ')')
    if receipt['requiredRoleResults'] != original_receipt:
        raise ValueError('Canonical single-role closure receipt changed')
    receipt['requiredRoleResults'] = '@' + choose(routes, lambda route: 'createArray(' + role_record(route['requiredFictionalRoles'][0]) + ')')
    known = lambda entries: 'or(false,' + ','.join('equals(' + SOURCE + ',' + _literal(uid) + ')' for uid, _ in entries) + ')'
    guard = nodes['Closure_Ready_consultation_Runtime_guard']
    guard['expression'] = replace_once(guard['expression'], known(old_routes), known(routes))
    for purpose in PURPOSES:
        old_ref = seed[0][1]['purposeReferences'][purpose]
        reference = choose(routes, lambda route: _literal(route['purposeReferences'][purpose]))
        query = nodes['CurrentClosure_select_' + purpose]['inputs']
        query['where'] = replace_once(query['where'], _literal(old_ref), reference)
        valid = nodes['Closure_selected_' + purpose + '_valid']
        old_choice = choose(old_routes, lambda route: _literal(route['purposeReferences'][purpose]))
        valid['inputs'] = replace_once(valid['inputs'], old_choice, reference)


def build(reference, target, producer, binding):
    keys = {'approvedReferenceDefinitionSHA256', 'approvedTargetDefinitionSHA256', 'approvedProducerDefinitionSHA256'}
    if set(binding) != keys:
        raise ValueError('Exact reviewed closure reference, current target and routing producer required')
    for flow, key in ((reference, 'approvedReferenceDefinitionSHA256'), (target, 'approvedTargetDefinitionSHA256'),
                      (producer, 'approvedProducerDefinitionSHA256')):
        if digest(flow['properties']['definition']) != binding[key]:
            raise ValueError('Reviewed closure or routing definition changed')
    if (not target.get('name') or reference.get('name') != target['name']
            or reference['properties']['connectionReferences'] != target['properties']['connectionReferences']
            or producer['properties']['connectionReferences'] != target['properties']['connectionReferences']
            or reference['properties']['definition']['triggers'] != target['properties']['definition']['triggers']):
        raise ValueError('Retain the existing closure identity, native form and connection references')
    nodes = _flatten(reference['properties']['definition']['actions'])
    source_nodes = _flatten(producer['properties']['definition']['actions'])
    allowed = source_nodes['Origin_Completed_allowed_sources']['inputs']
    routes = _source_review_requirements({'allowedSources': allowed})
    if routes is None:
        raise ValueError('Existing producer must supply reviewed source-role-purpose requirements')
    site = nodes['Read_selected_case']['inputs']['parameters']['dataset']
    configured = validate_sources(nodes['SourceProfiles_configured']['inputs'], site)
    if configured != validate_sources(allowed, site):
        raise ValueError('Closure source identities must exactly match the qualified routing producer')
    limits = nodes['Selected_case_context']['inputs']['limits']
    if nodes['SourceProfiles_matches']['inputs']['where'] != match_expression():
        raise ValueError('Retain exact native request-source matching')
    operation = nodes['SourceProfiles_operation']['expression']
    seeds = [profile for profile in configured if operation == _operation_expression(profile,
        limits.get('additionalOwnershipProjectionSource'), limits.get('additionalPreparationContextSource'))]
    if len(seeds) != 1:
        raise ValueError('Exact original source-specific closure operation guard required')
    close = "@equals(triggerBody()?['text'],'Close review')"
    if nodes['Validate_closure_operation']['expression'] != close:
        raise ValueError('Retain the explicit closure-only entry guard')
    out = copy.deepcopy(target)
    out['properties']['definition'] = copy.deepcopy(reference['properties']['definition'])
    out['properties']['state'] = 'Stopped'
    updated = _flatten(out['properties']['definition']['actions'])
    bind_review_routes(updated, routes, seeds[0]['UniqueId'].lower())
    updated['SourceProfiles_operation']['expression'] = close
    updated['Selected_case_context']['inputs']['limits'].update(
        reusableClosureRoute=True, otherOperationsRetainOriginalSource=False, runtimeQualified=False)
    definition = out['properties']['definition']
    geometry = audit_actions(definition)
    if geometry['actionCount'] > 500 or geometry['maximumActionDepth'] > 8:
        raise ValueError('Reusable closure exceeds native geometry limits')
    _check_expression_lengths(definition)
    if action_references(definition['actions']) - updated.keys():
        raise ValueError('Unresolved reusable closure prerequisite')
    return out
