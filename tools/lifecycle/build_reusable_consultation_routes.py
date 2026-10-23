"""Compose two reviewed consultation profiles into each existing native route.

Pure, bounded composition of the existing request/response flows. No deployment,
new runtime, actor authority or native qualification is implied by this builder.
"""
import copy
import re

from build_multisource_case_context import with_eligible_sources, digest, validate_sources
from build_operator_entry import _flatten, _literal, action_references
from build_selected_event_routes import audit_actions
from build_native_closure_entry import _check_expression_lengths


FIELDS = {
    'request': ('text', ('Ownership offer', 'Consultation request')),
    'response': ('text_5', ('Ownership response', 'Consultation response')),
}
READS = ('Offer_source_before', 'Offer_source_after', 'Read_prepared_source_final')
BINDINGS = {
    'Consultation_payload': ('inputs', 'SubjectRole'),
    'Find_prepared_receipt': ('inputs', 'parameters', 'parameters/uri'),
    'Native_prepared_revision': ('inputs', 'preparedRevision', 'qualificationReceipt', 'DocumentReference'),
    'Verify_prepared_selection': ('expression',),
}
RESPONSE_BINDINGS = {
    'Consultation_before_checks_0': ('inputs',),
    'Consultation_coverage_Problems': ('inputs', 'where'),
    'Consultation_coverage_R0_Rows': ('inputs', 'where'),
    'Consultation_coverage_Receipt': ('inputs', 'requiredRoleResults'),
}


def _get(value, path):
    for key in path:
        value = value[key]
    return value


def _set(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


def _selected(left, right, condition):
    """Preserve object/array shape and select only differing scalar inputs."""
    if left == right:
        return copy.deepcopy(left)
    if isinstance(left, dict) and isinstance(right, dict) and left.keys() == right.keys():
        return {key: _selected(left[key], right[key], condition) for key in left}
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return [_selected(a, b, condition) for a, b in zip(left, right)]
    if not isinstance(left, str) or not isinstance(right, str):
        raise ValueError('Reviewed profile variants must preserve binding types and shapes')
    if left.startswith('@') and right.startswith('@'):
        # Most profile variants differ only in a role/route literal. Select that
        # literal, retaining one copy of every shared guard. Never turn action
        # references or property keys into dynamic expressions.
        literals = re.compile(r"'(?:[^']|'')*'")
        a, b = list(literals.finditer(left)), list(literals.finditer(right))
        if (len(a) == len(b) and literals.sub("''", left) == literals.sub("''", right)):
            parts = []; previous = 0; safe = True
            for x, y in zip(a, b):
                parts.append(left[previous:x.start()])
                if x.group() == y.group():
                    parts.append(x.group())
                elif (left[:x.start()].rstrip().endswith('[')
                      or re.search(r'(?:body|outputs|actions|result|triggerOutputs)\s*\(\s*$',
                                   left[:x.start()], re.I)):
                    safe = False; break
                else:
                    parts.append('if(' + condition + ',' + y.group() + ',' + x.group() + ')')
                previous = x.end()
            if safe:
                parts.append(left[previous:])
                return ''.join(parts)
    def operand(value):
        if value.startswith('@@') or '@{' in value:
            raise ValueError('Embedded interpolation is not a reviewed binding operand')
        return value[1:] if value.startswith('@') else _literal(value)
    return '@if(' + condition + ',' + operand(right) + ',' + operand(left) + ')'


def _local_nodes(flow):
    # Flattened containers include their children; compare each action only once.
    nodes = copy.deepcopy(_flatten(flow['properties']['definition']['actions']))
    for node in nodes.values():
        node.pop('actions', None)
        node.pop('else', None)
        inputs = node.get('inputs')
        if (node.get('type') == 'OpenApiConnection' and isinstance(inputs, dict)
                and inputs.get('authentication') == "@parameters('$authentication')"):
            del inputs['authentication']
    return nodes


def _locations(group, parent=()):
    result = {}
    for name, node in group.items():
        result[name] = parent
        result.update(_locations(node.get('actions', {}), parent + (name, 'actions')))
        result.update(_locations(node.get('else', {}).get('actions', {}), parent + (name, 'else')))
    return result


def build(original, additional, profiles, binding):
    required = {'stage', 'approvedOriginalDefinitionSHA256', 'approvedAdditionalDefinitionSHA256'}
    if set(binding) != required or binding['stage'] not in FIELDS:
        raise ValueError('Exact reviewed request or response binding required')
    for flow, pin in ((original, binding['approvedOriginalDefinitionSHA256']),
                      (additional, binding['approvedAdditionalDefinitionSHA256'])):
        if digest(flow['properties']['definition']) != pin:
            raise ValueError('Reviewed consultation definition changed')
    if (original.get('name') != additional.get('name')
            or not original.get('name')
            or original['properties']['connectionReferences'] != additional['properties']['connectionReferences']
            or original['properties']['definition']['triggers'] != additional['properties']['definition']['triggers']):
        raise ValueError('Retain the same existing flow, form and connection references')
    a = _local_nodes(original)
    b = _local_nodes(additional)
    if (a.keys() != b.keys() or _locations(original['properties']['definition']['actions'])
            != _locations(additional['properties']['definition']['actions'])):
        raise ValueError('Reviewed consultation variants must have identical action identities')
    site = a['Read_selected_case']['inputs']['parameters']['dataset']
    profiles = validate_sources(profiles, site)
    if len(profiles) != 2:
        raise ValueError('Exactly two reviewed fictional source configurations required')
    def source_index(nodes):
        ctx = nodes['Selected_case_context']['inputs']
        matches = [i for i, row in enumerate(profiles)
                   if all(ctx['sourcePins'].get(k) == row[k] for k in ('DocumentUID', 'UniqueId', 'ETag'))
                   and all(ctx['scope'].get(k) == row[s] for k, s in
                           [('DocumentReference', 'DocumentReference'), ('ReviewedVersionRef', 'ReviewedVersionRef'),
                            ('DocumentSHA256', 'sha256')])]
        if len(matches) != 1:
            raise ValueError('Each reviewed variant must retain an exact configured source')
        return matches[0]
    seed, extra = source_index(a), source_index(b)
    if seed == extra:
        raise ValueError('Additional consultation profile must select a different source')
    fields = {**BINDINGS, **(RESPONSE_BINDINGS if binding['stage'] == 'response' else {})}
    # No other creator, guard, history, recovery, dependency or transport may differ.
    for nodes in (a, b):
        for name, path in fields.items():
            _set(nodes[name], path, None)
        for name in (*READS, 'Read_source_before', 'Read_source_after', 'Read_source_content'):
            params = nodes[name]['inputs']['parameters']
            host = nodes[name]['inputs'].get('host', {})
            if (nodes[name].get('type') != 'OpenApiConnection'
                    or params.get('dataset') != site or params.get('parameters/method') != 'GET'
                    or 'parameters/body' in params
                    or host.get('operationId') != 'HttpRequest'
                    or host.get('apiId') != '/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
                    or host.get('connectionName') != 'shared_sharepointonline'
                    or any(key.lower() in ('x-http-method', 'x-http-method-override')
                           for key in params.get('parameters/headers', {}))):
                raise ValueError('Source readers must retain exact same-site GET transport')
            params['parameters/uri'] = None
        nodes['Selected_case_context']['inputs']['sourcePins'] = None
        nodes['Selected_case_context']['inputs']['scope'] = None
        nodes['Selected_case_context']['inputs']['limits'].pop('additionalPreparedArtifactFolders', None)
        nodes['Verify_request']['expression'] = None
        nodes['Verify_source_and_case']['expression'] = None
    if a != b:
        raise ValueError('Consultation variants differ outside reviewed source/role/artifact bindings')
    # Reuse the canonical source selector on the actual graph. Its two-field
    # interface is only a local compiler input; restore the complete native form.
    base = copy.deepcopy(original)
    schema = base['properties']['definition']['triggers']['manual']['inputs']['schema']
    saved_schema = copy.deepcopy(schema)
    schema['properties'] = {key: schema['properties'][key] for key in ('text', 'text_6')}
    schema['required'] = ['text', 'text_6']
    out = with_eligible_sources(base, profiles, digest(base['properties']['definition']))
    out['properties']['definition']['triggers']['manual']['inputs']['schema'] = saved_schema
    n = _flatten(out['properties']['definition']['actions'])
    condition = "equals(outputs('SourceProfiles_selected')?['UniqueId']," + _literal(profiles[extra]['UniqueId']) + ')'
    old_nodes = _flatten(original['properties']['definition']['actions'])
    new_nodes = _flatten(additional['properties']['definition']['actions'])
    for name, path in fields.items():
        _set(n[name], path, _selected(_get(old_nodes[name], path), _get(new_nodes[name], path), condition))
    for name in READS:
        n[name]['inputs']['parameters']['parameters/uri'] = (
            "@concat('_api/web/GetFileById(',decodeUriComponent('%27'),"
            "outputs('Selected_case_context')?['sourcePins']?['UniqueId'],"
            "decodeUriComponent('%27'),')?$select=UniqueId,ETag,Length')")
    operation_field, choices = FIELDS[binding['stage']]
    allowed = '@contains(createArray(' + ','.join(map(_literal, choices)) + "),triggerBody()?['" + operation_field + "'])"
    if n['Validate_event_operation']['expression'] != allowed:
        raise ValueError('Reviewed native operation allowlist changed')
    n['SourceProfiles_operation']['expression'] = allowed
    limits = n['Selected_case_context']['inputs']['limits']
    limits.pop('additionalPreparedArtifactFolders', None)
    limits.update(otherOperationsRetainOriginalSource=False,
                  reusableConsultationStage=binding['stage'], runtimeQualified=False)
    definition = out['properties']['definition']
    geometry = audit_actions(definition)
    if geometry['actionCount'] > 500 or geometry['maximumActionDepth'] > 8:
        raise ValueError('Reusable consultation exceeds native geometry limits')
    if action_references(definition['actions']) - n.keys():
        raise ValueError('Unresolved reusable consultation action reference')
    _check_expression_lengths(definition)
    return out
