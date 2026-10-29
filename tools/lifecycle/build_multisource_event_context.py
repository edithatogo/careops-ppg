"""Compose reviewed source lookup into the existing fictional event adapters.

Pure authoring only. Case references remain untrusted lookup keys; event payload,
parent/stage/token/replay guards and the qualified event destination stay intact.
"""
import copy

from build_multisource_case_context import with_eligible_sources, digest, _check_context_shape
from build_operator_entry import _flatten, action_references
from build_selected_event_routes import audit_actions


def build(flow, profiles, approved_definition_sha256, kind):
    source = flow['properties']['definition']
    if kind not in ('request', 'response') or digest(source) != approved_definition_sha256:
        raise ValueError('Exact reviewed request/response adapter required')
    mode = 'text' if kind == 'request' else 'text_5'
    operations = (('Ownership offer', 'Consultation request') if kind == 'request'
                  else ('Ownership response', 'Consultation response'))
    expression = "@contains(createArray('" + "','".join(operations) + "'),triggerBody()?['" + mode + "'])"
    expected_roots = {'Resolve_context', 'Held_unverified_read', 'Validate_event_operation'}
    if kind == 'response':
        expected_roots.add('Validate_response_input')
    roots = source['actions']; guard = roots.get('Validate_event_operation', {})
    if (set(roots) != expected_roots or guard.get('type') != 'If'
            or guard.get('expression') != expression or guard.get('runAfter') != {}
            or guard.get('actions') != {'Event_operation_valid': {'type': 'Compose', 'inputs': True, 'runAfter': {}}}
            or guard.get('else', {}).get('actions', {}).get('Stop_unsupported_event_operation') != {
                'type': 'Terminate', 'inputs': {'runStatus': 'Succeeded'},
                'runAfter': {'Held_unsupported_event_operation': ['Succeeded']}}):
        raise ValueError('Retain explicit native event-operation gate and unsupported-mode termination')
    dependency = 'Validate_event_operation' if kind == 'request' else 'Validate_response_input'
    if (roots['Resolve_context'].get('runAfter') != {dependency: ['Succeeded']}
            or (kind == 'response' and roots['Validate_response_input'].get('runAfter') != {
                'Validate_event_operation': ['Succeeded']})):
        raise ValueError('Retain operation and response validation before native context lookup')
    prior = _flatten(roots)
    writers = {n: a for n, a in prior.items() if a.get('type') == 'OpenApiConnection'
               and a['inputs']['parameters'].get('parameters/method') != 'GET'}
    if (set(writers) != {'Create_offer'}
            or writers['Create_offer']['inputs'].get('retryPolicy') != {'type': 'none'}
            or prior['Offer_payload']['inputs'].get('FictionalTest') is not True):
        raise ValueError('Existing single fictional event writer with retries disabled required')
    trigger = source['triggers']['manual']
    schema = trigger.get('inputs', {}).get('schema', {})
    fields = schema.get('properties', {})
    expected_fields = {'text', 'text_6'} if kind == 'request' else {'text', 'text_1', 'text_2', 'text_3', 'text_4', 'text_5', 'text_6'}
    if (trigger.get('kind') != 'Button' or trigger.get('type') != 'Request'
            or set(fields) != expected_fields or not {'text_6', mode} <= set(schema.get('required', []))
            or any(f.get('type') != 'string' for f in fields.values())
            or trigger.get('runtimeConfiguration') != {'concurrency': {'runs': 1}}):
        raise ValueError('Existing manual event fields and server-resolved case reference required')
    # Reuse the maintained exact source/context transformer. Its two-field
    # construction check is temporary local input, never the emitted native form.
    shadow = copy.deepcopy(flow)
    shadow['properties']['definition']['triggers']['manual']['inputs']['schema'] = {
        'type': 'object', 'properties': {k: copy.deepcopy(fields[k]) for k in ('text', 'text_6')},
        'required': ['text', 'text_6']}
    out = with_eligible_sources(shadow, profiles, digest(shadow['properties']['definition']))
    definition = out['properties']['definition']
    definition['triggers']['manual'] = copy.deepcopy(trigger)
    nodes = _flatten(definition['actions'])
    original_operation = nodes['SourceProfiles_operation']['expression']
    # The outer event gate and the source gate use precisely the same predicate.
    # Check context is not an event operation and cannot silently create an offer.
    nodes['SourceProfiles_operation']['expression'] = expression
    old_reader = prior['Read_source_after']['inputs']
    selected_uri = nodes['Read_source_after']['inputs']['parameters']['parameters/uri']
    for name in ('Offer_source_before', 'Offer_source_after'):
        if prior[name]['inputs'] != old_reader:
            raise ValueError('Retain exact copied source refresh readers')
        nodes[name]['inputs']['parameters']['parameters/uri'] = selected_uri
    def complete_reads(names):
        return ["empty(body('" + name + "')?['" + marker + "'])"
                for name in names for marker in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink')]
    before_reads = ['Find_offer'] + (['Read_current_offer', 'Read_response_history'] if kind == 'response' else [])
    for name, readers in [('Verify_offer_before', before_reads), ('Verify_offer', ['Read_offer'])]:
        original = nodes[name]['expression']
        if not isinstance(original, str) or not original.startswith('@'):
            raise ValueError('Retain reviewed event guard expressions')
        nodes[name]['expression'] = '@and(' + ','.join([original[1:]] + complete_reads(readers)) + ')'
    # Reconstruct the canonical lookup contract for independent structural checks;
    # the emitted consumer retains the explicit event-mode predicate above.
    checked = copy.deepcopy(definition)
    _flatten(checked['actions'])['SourceProfiles_operation']['expression'] = original_operation
    _check_context_shape(checked)
    limits = nodes['Selected_case_context']['inputs']['limits']
    limits.pop('otherOperationsRetainOriginalSource', None)
    limits.update(eligibleEventOperations=list(operations), eventOperationField=mode)
    if (nodes['Create_offer'] != prior['Create_offer']
            or definition['triggers']['manual'] != trigger
            or out['properties']['connectionReferences'] != flow['properties']['connectionReferences']):
        raise ValueError('Event writer, complete form and native references must remain exact')
    geometry = audit_actions(definition)
    if (geometry['actionCount'] > 500 or geometry['maximumActionDepth'] > 8
            or action_references(definition['actions']) - nodes.keys()):
        raise ValueError('Retain bounded native geometry and resolved action references')
    out['properties']['state'] = 'Stopped'
    return out
