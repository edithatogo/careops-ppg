"""Compose the two reviewed fictional decision routes into their existing flow.

Offline compiler only. Native save, actual human findings and runtime qualification
remain separate. Input route references never select the document or its authority.
"""
import copy
import re

from build_multisource_case_context import with_eligible_sources, validate_sources, digest
from build_operator_entry import _flatten, _literal, action_references
from build_selected_event_routes import audit_actions
from build_reusable_consultation_routes import _get, _set, _selected, _local_nodes, _locations
from build_native_closure_entry import _check_expression_lengths


BINDINGS = {
    'Find_prepared_receipt': ('inputs', 'parameters', 'parameters/uri'),
    'Native_prepared_revision': ('inputs', 'preparedRevision', 'qualificationReceipt', 'DocumentReference'),
    'Verify_prepared_selection': ('expression',),
    'Purpose_profile': ('inputs',),
    'Native_purpose_receipt': ('inputs', 'fictionalRouteProfile'),
    'Ready_consultation_Problems': ('inputs', 'where'),
    'Ready_consultation_R0_Rows': ('inputs', 'where'),
    'Ready_consultation_Receipt': ('inputs', 'requiredRoleResults'),
    **{f'Purpose_{phase}_valid_{purpose}': ('inputs',)
       for phase in ('before', 'after')
       for purpose in ('committee', 'officer', 'coordinator', 'authorisation')},
}
SOURCE_READS = ('Read_prepared_source_final', 'Read_source_before', 'Read_source_after', 'Read_source_content')


def build(original, additional, profiles, binding):
    required = {'approvedOriginalDefinitionSHA256', 'approvedAdditionalDefinitionSHA256'}
    if not required <= set(binding) or not set(binding) <= required | {'stage'}:
        raise ValueError('Exact reviewed purpose-route binding required')
    stage = binding.get('stage', 'purpose')
    if stage not in ('purpose', 'publication'):
        raise ValueError('Only the reviewed purpose/publication graph shapes are supported')
    fields = dict(BINDINGS)
    input_guard = 'Validate_purpose_input'
    if stage == 'publication':
        input_guard = 'Validate_publication_input'
        fields.pop('Native_purpose_receipt')
        for purpose in ('committee', 'officer', 'coordinator', 'authorisation'):
            fields.pop('Purpose_after_valid_' + purpose)
            for prefix in ('Copy_after', 'Before_event', 'After_event'):
                fields[prefix + '_Purpose_before_valid_' + purpose] = ('inputs',)
        fields.update({'Verify_target_cardinality': ('expression',),
                       'Verify_binary_proof_relations_check_0': ('inputs',),
                       'Verify_binary_proof_relations_check_1': ('inputs',)})
    for flow, key in ((original, 'approvedOriginalDefinitionSHA256'), (additional, 'approvedAdditionalDefinitionSHA256')):
        if digest(flow['properties']['definition']) != binding[key]:
            raise ValueError('Reviewed purpose definition changed')
    if (not original.get('name') or original.get('name') != additional.get('name')
            or original['properties']['connectionReferences'] != additional['properties']['connectionReferences']):
        raise ValueError('Same existing purpose flow and connection references required')
    first_trigger = copy.deepcopy(original['properties']['definition']['triggers'])
    second_trigger = copy.deepcopy(additional['properties']['definition']['triggers'])
    descriptions = []
    if stage == 'purpose':
        for trigger in (first_trigger, second_trigger):
            form_fields = trigger['manual']['inputs']['schema']['properties']
            descriptions.append(form_fields['text_7'].pop('description', ''))
    if first_trigger != second_trigger:
        raise ValueError('Preserve every purpose form field, wire and trigger behavior')
    a, b = _local_nodes(original), _local_nodes(additional)
    if (a.keys() != b.keys() or _locations(original['properties']['definition']['actions'])
            != _locations(additional['properties']['definition']['actions'])):
        raise ValueError('Purpose variants must retain exact action topology')
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
            raise ValueError('Exact reviewed source scope required for each purpose variant')
        return matches[0]
    seed, extra = source_index(a), source_index(b)
    if seed == extra:
        raise ValueError('Distinct configured purpose sources required')
    for nodes in (a, b):
        for name, path in fields.items():
            _set(nodes[name], path, None)
        for name in SOURCE_READS:
            node = nodes[name]
            params, host = node['inputs']['parameters'], node['inputs'].get('host', {})
            if (node.get('type') != 'OpenApiConnection' or params.get('parameters/method') != 'GET'
                    or params.get('dataset') != site or 'parameters/body' in params
                    or host.get('apiId') != '/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
                    or host.get('operationId') != 'HttpRequest' or host.get('connectionName') != 'shared_sharepointonline'
                    or any(k.lower() in ('x-http-method', 'x-http-method-override') for k in params.get('parameters/headers', {}))):
                raise ValueError('Retain same-site GET-only source readers')
            params['parameters/uri'] = None
        ctx = nodes['Selected_case_context']['inputs']
        ctx['sourcePins'], ctx['scope'] = None, None
        ctx['limits'].pop('additionalPreparedArtifactFolders', None)
        for name in ('Verify_request', 'Verify_source_and_case', input_guard):
            nodes[name]['expression'] = None
    if a != b:
        raise ValueError('Purpose variants differ outside reviewed source, role, route and artifact bindings')
    base = copy.deepcopy(original)
    d = base['properties']['definition']
    schema = d['triggers']['manual']['inputs']['schema']
    saved_schema = copy.deepcopy(schema)
    schema['properties'] = {key: schema['properties'][key] for key in ('text', 'text_6')}
    schema['required'] = ['text', 'text_6']
    out = with_eligible_sources(base, profiles, digest(d))
    out['properties']['definition']['triggers']['manual']['inputs']['schema'] = saved_schema
    n = _flatten(out['properties']['definition']['actions'])
    left = _flatten(original['properties']['definition']['actions'])
    right = _flatten(additional['properties']['definition']['actions'])
    condition = "equals(outputs('SourceProfiles_selected')?['UniqueId']," + _literal(profiles[extra]['UniqueId']) + ')'
    for name, path in fields.items():
        _set(n[name], path, _selected(_get(left[name], path), _get(right[name], path), condition))
    n['Read_prepared_source_final']['inputs']['parameters']['parameters/uri'] = (
        "@concat('_api/web/GetFileById(',decodeUriComponent('%27'),"
        "outputs('Selected_case_context')?['sourcePins']?['UniqueId'],"
        "decodeUriComponent('%27'),')?$select=UniqueId,ETag,Length')")
    first_guard = left[input_guard]['expression']
    second_guard = right[input_guard]['expression']
    if not first_guard.startswith('@') or not second_guard.startswith('@'):
        raise ValueError('Reviewed expression input guards required')
    # Initial validation accepts either shape; after native case/request lookup,
    # the original complete source-specific guard is mandatory before source GETs.
    if stage == 'publication' and second_guard != first_guard:
        # The separately qualified second-source trial restricted its input to
        # one literal case. Replace only that trial restriction with the native
        # case/request/source selector, preserving the entire original input guard.
        pattern = re.escape('@and(' + first_guard[1:] + ",equals(triggerBody()?['text_6'],")
        pattern += r"'LC-FICTIONAL-OP-[A-Za-z0-9_-]+'\)\)"
        if re.fullmatch(pattern, second_guard) is None:
            raise ValueError('Unexpected second-source publication trial restriction')
        second_guard = first_guard
    n[input_guard]['expression'] = '@or(' + first_guard[1:] + ',' + second_guard[1:] + ')'
    n['SourceProfiles_operation']['expression'] = _selected(first_guard, second_guard, condition)
    if stage == 'purpose':
        saved_schema['properties']['text_7']['description'] = (
            'Use the fictional route for the selected case. ' + ' / '.join(dict.fromkeys(descriptions)))
    limits = n['Selected_case_context']['inputs']['limits']
    limits.pop('additionalPreparedArtifactFolders', None)
    limits.update(otherOperationsRetainOriginalSource=False, reusablePurposeRoute=stage == 'purpose',
                  reusablePublicationContext=stage == 'publication', runtimeQualified=False)
    geometry = audit_actions(out['properties']['definition'])
    if geometry['actionCount'] > 500 or geometry['maximumActionDepth'] > 8:
        raise ValueError('Reusable purpose route exceeds native geometry limits')
    if action_references(out['properties']['definition']['actions']) - n.keys():
        raise ValueError('Unresolved reusable purpose action reference')
    if stage == 'purpose':
        _check_expression_lengths(out['properties']['definition'])
    return out
