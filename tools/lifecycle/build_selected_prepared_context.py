"""Embed the reviewed prepared-document reader in an event flow execution.

Local assembly only. The approved definition digest is a review pin, not evidence
of a native run. No consultation event is created by this prerequisite increment.
"""
import copy
import hashlib
import json
from build_selected_event_routes import audit_actions


def digest(definition):
    return hashlib.sha256(json.dumps(definition, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _context(definition, event=False):
    context = copy.deepcopy(definition['actions']['Resolve_context'])
    context['runAfter'] = {}
    if event:
        final = context['actions']['Verify_baseline_boundary']['actions']['Verify_request']['actions']['Verify_source_and_case']['actions']
        if set(final) != {'Selected_case_context', 'Route_ownership_event', 'Route_unbound_consultation'}:
            raise ValueError('Review changed event context contract')
        final.pop('Route_ownership_event'); final.pop('Route_unbound_consultation')
    return context


def build(kind, event_flow, prepared_flow, approved_definition_sha256):
    if kind not in ('request', 'response'):
        raise ValueError('Choose request or response')
    source = prepared_flow['properties']['definition']
    if digest(source) != approved_definition_sha256:
        raise ValueError('Exact reviewed prepared-reader definition required')
    props = event_flow['properties']; definition = props['definition']
    if props['connectionReferences'] != prepared_flow['properties']['connectionReferences']:
        raise ValueError('Retain the same qualified native connection references')
    if _context(definition, True) != _context(source):
        raise ValueError('Prepared reader must share the exact selected-case context')
    prerequisite = copy.deepcopy(source['actions']['Route_preparation_check'])
    old = "equals(triggerBody()?['text'],'Check preparation')"
    field, mode = ('text', 'Consultation request') if kind == 'request' else ('text_5', 'Consultation response')
    if prerequisite['expression'].count(old) != 1 or prerequisite.get('runAfter') != {'Resolve_context':['Succeeded']}:
        raise ValueError('Review changed preparation routing contract')
    prerequisite['expression'] = prerequisite['expression'].replace(old, "equals(triggerBody()?['"+field+"'],'"+mode+"')")
    # Copy only the independently reviewed GET-only preparation branch. The case
    # projection writer and other case-work modes must never enter this flow.
    count = 0
    def inspect(value):
        nonlocal count
        if isinstance(value, dict):
            if 'runAfter' in value and value.get('type') not in ('If', 'Scope', 'Compose', 'OpenApiConnection', 'Query', 'Select'):
                raise ValueError('Unsupported executable action in prepared prerequisite')
            if value.get('type') == 'OpenApiConnection':
                inputs = value['inputs']; parameters = inputs['parameters']; host = inputs['host']
                if (host.get('apiId') != '/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
                    or host.get('operationId') != 'HttpRequest'
                    or parameters.get('parameters/method') != 'GET'
                    or parameters.get('parameters/body')
                    or any(k.lower() in ('x-http-method', 'x-http-method-override') for k in parameters.get('parameters/headers', {}))):
                    raise ValueError('Prepared prerequisite must contain only qualified SharePoint GET reads')
                count += 1
            for child in value.values(): inspect(child)
        elif isinstance(value, list):
            for child in value: inspect(child)
    inspect(prerequisite)
    if not count:
        raise ValueError('A real prepared-artifact reader is required')
    out = copy.deepcopy(event_flow); out['properties']['state'] = 'Stopped'
    actions = out['properties']['definition']['actions']
    final = actions['Resolve_context']['actions']['Verify_baseline_boundary']['actions']['Verify_request']['actions']['Verify_source_and_case']['actions']
    final.pop('Route_unbound_consultation')
    actions['Route_consultation_prepared_context'] = prerequisite
    audit_actions(out['properties']['definition'])
    return out
