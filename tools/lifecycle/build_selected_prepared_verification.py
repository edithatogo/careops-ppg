"""Resolve a verification parent from native case/file/history reads.

Local composition only. Reuses the existing verification writer and its complete
publication, readiness, parent-token and after-write checks. No new connection,
implementation creator or caller-supplied parent authority is introduced.
"""
import copy
import json
import re
from urllib.parse import urlsplit

from build_operator_entry import _flatten, _literal, action_references
from build_prepared_verification import build as retained_build
from build_selected_event_routes import audit_actions


def build(implementation, target, binding):
    if set(binding) != {'qualificationOnly', 'approvedImplementationDefinitionSHA256',
                       'approvedTargetDefinitionSHA256', 'caseListUri'}:
        raise ValueError('Static deployment configuration only; no supplied parent record')
    collection = binding.get('caseListUri', '')
    pattern = r"_api/web/lists\(guid'[0-9a-fA-F-]{36}'\)/items"
    if not re.fullmatch(pattern, collection):
        raise ValueError('Existing case collection required')
    nodes = _flatten(implementation['properties']['definition']['actions'])
    template = nodes['Read_selected_case']
    params = template['inputs']['parameters']
    if (params.get('parameters/method') != 'GET' or not
            params['parameters/uri'].startswith("@concat('" + collection.replace("'", "''") + "('")):
        raise ValueError('Existing case reader must match selected collection')
    site = params['dataset']; parsed = urlsplit(site)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('Existing canonical HTTPS site required')
    origin = parsed.scheme + '://' + parsed.netloc
    history_template = nodes['Purpose_before_assurance']
    history_uri = history_template['inputs']['parameters']['parameters/uri']
    if (history_template['inputs']['parameters']['dataset'] != site or
            history_template['inputs']['parameters']['parameters/method'] != 'GET' or
            not re.fullmatch(pattern, history_uri) or history_uri == collection):
        raise ValueError('Existing complete assurance reader required')

    # Satisfy the unchanged legacy compiler, then replace every template value.
    # None of these values may survive in the deployable graph.
    marker = 'COMPILER-RUNTIME-PARENT'
    parent = {key: marker + '-' + key for key in (
        'CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256',
        'ParentEventUID', 'ReadinessEventUID', 'PublicationURL', 'PublishedVersionRef', 'GUID')}
    parent.update(EventUID='LC04-IMPL-PREPARED-' + marker, Id=2147483001,
        Stage='Implementation', RecordState='Recorded', FictionalTest=True,
        ConditionsState='None recorded', SupersedesEventUID=None,
        ImplementationActions='FICTIONAL ' + marker + '-actions',
        EvidenceReference='fictional://' + marker + '/evidence',
        NextAction='FICTIONAL ' + marker + '-next', OccurredOn=marker + '-date',
        **{'odata.etag': '"' + marker + ',1"'})
    full_actions = 'ImplementationActionsNote' in nodes['Implementation_payload']['inputs']
    if full_actions:
        parent['ImplementationActionsNote'] = 'FICTIONAL ' + marker + '-full-actions'
    legacy_binding = {k: copy.deepcopy(v) for k, v in binding.items() if k != 'caseListUri'}
    legacy_binding['retainedImplementation'] = parent
    result = retained_build(implementation, target, legacy_binding)
    actions = result['properties']['definition']['actions']
    actions['Retained_implementation']['inputs'] = "@outputs('SelectedVerification_parent')"
    dynamic = {value: "outputs('SelectedVerification_parent')?['" + key + "']"
               for key, value in parent.items() if isinstance(value, str) and marker in value}

    def replace(value):
        if isinstance(value, dict): return {k: replace(v) for k, v in value.items()}
        if isinstance(value, list): return [replace(v) for v in value]
        if isinstance(value, str):
            if value in dynamic: return '@' + dynamic[value]
            if value.startswith('@'):
                for literal, expression in dynamic.items():
                    value = value.replace(_literal(literal), expression)
        return value
    actions = replace(actions)
    if marker in json.dumps(actions):
        raise ValueError('Compiler parent escaped runtime substitution')

    def comp(value, previous=None):
        return {'type': 'Compose', 'inputs': value,
                'runAfter': {previous: ['Succeeded']} if previous else {}}
    def get(uri, previous, reference=template):
        value = copy.deepcopy(reference)
        value['inputs']['parameters']['parameters/uri'] = uri
        value['runAfter'] = {previous: ['Succeeded']}
        return value
    def guard(checks, previous=None):
        return {'type': 'If', 'expression': '@and(' + ','.join(checks) + ')',
                'actions': {}, 'else': {'actions': {'SelectedVerification_stop_' + str(len(prefix)):
                    {'type': 'Terminate', 'runAfter': {}, 'inputs': {'runStatus': 'Failed',
                     'runError': {'code': 'SelectedVerificationParentUnresolved',
                      'message': 'No unique current native implementation parent; no write attempted.'}}}}},
                'runAfter': {previous: ['Succeeded']} if previous else {}}
    def complete(name):
        return ["empty(body('" + name + "')?['" + key + "'])"
                for key in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink')]
    prefix = {}
    # Validate operator input before any reads. The parent/child identity check
    # remains in the original validator after parent resolution.
    checks = actions['Validate_verification_input']['expression'][5:-1]
    parent_check = ",not(equals(triggerBody()?['text_1'],outputs('Retained_parent_uid')))"
    if not checks.endswith(parent_check): raise ValueError('Original verification input contract changed')
    prefix['SelectedVerification_input'] = guard([checks[:-len(parent_check)],
        "startsWith(string(coalesce(triggerBody()?['text_6'],'')),'LC-FICTIONAL-OP-')",
        "lessOrEquals(length(string(triggerBody()?['text_6'])),128)",
        "not(contains(string(triggerBody()?['text_6']),decodeUriComponent('%27')))",
        "equals(uriComponent(string(triggerBody()?['text_6'])),triggerBody()?['text_6'])"])
    prefix['SelectedVerification_cases'] = get('@concat(' + _literal(collection + "?$filter=CaseUID eq '")
        + ",triggerBody()?['text_6']," + _literal("'") + ')', 'SelectedVerification_input')
    prefix['SelectedVerification_one_case'] = guard(complete('SelectedVerification_cases') + [
        "equals(length(body('SelectedVerification_cases')?['value']),1)"], 'SelectedVerification_cases')
    prefix['SelectedVerification_case'] = comp("@first(body('SelectedVerification_cases')?['value'])", 'SelectedVerification_one_case')
    case = "outputs('SelectedVerification_case')"; link = case + "?['evidenceDraftLink']"
    prefix['SelectedVerification_link'] = guard([
        "equals(" + case + "?['CaseUID'],triggerBody()?['text_6'])",
        'startsWith(string(' + link + '),' + _literal(site + '/') + ')',
        'endsWith(toLower(string(' + link + ")),'.docx')"] +
        ['not(contains(string(' + link + '),' + _literal(char) + '))' for char in ("'", '..', '%', '?', '#', '\\')],
        'SelectedVerification_case')
    prefix['SelectedVerification_file'] = get('@concat(' + _literal("_api/web/GetFileByServerRelativePath(decodedurl='")
        + ',substring(' + link + ',' + str(len(origin)) + '),' + _literal("')?$select=UniqueId,ETag") + ')',
        'SelectedVerification_link')
    prefix['SelectedVerification_history'] = get(history_uri, 'SelectedVerification_file', history_template)
    version = "concat('sharepoint:',body('SelectedVerification_file')?['UniqueId'],':',body('SelectedVerification_file')?['ETag'])"
    prefix['SelectedVerification_candidates'] = {'type': 'Query', 'runAfter': {'SelectedVerification_history': ['Succeeded']},
        'inputs': {'from': "@body('SelectedVerification_history')?['value']", 'where': '@and(' + ','.join([
            "equals(item()?['CaseUID']," + case + "?['CaseUID'])",
            "equals(item()?['DocumentReference']," + link + ')',
            "equals(item()?['ReviewedVersionRef']," + version + ')',
            "equals(item()?['Stage'],'Implementation')"]) + ')'}}
    prefix['SelectedVerification_unique'] = guard(complete('SelectedVerification_history') + [
        "equals(length(body('SelectedVerification_candidates')),1)",
        "not(empty(body('SelectedVerification_file')?['UniqueId']))",
        "not(empty(body('SelectedVerification_file')?['ETag']))",
        "not(equals(body('SelectedVerification_file')?['ETag'],'*'))"], 'SelectedVerification_candidates')
    prefix['SelectedVerification_parent'] = comp("@union(first(body('SelectedVerification_candidates')),json('{\"odata.id\":null}'))", 'SelectedVerification_unique')
    chosen = "outputs('SelectedVerification_parent')"
    prefix['SelectedVerification_parent_valid'] = guard([
        "equals(" + chosen + "?['FictionalTest'],true)",
        "equals(" + chosen + "?['RecordState'],'Recorded')",
        "equals(" + chosen + "?['ConditionsState'],'None recorded')",
        "empty(" + chosen + "?['SupersedesEventUID'])",
        "greater(int(coalesce(" + chosen + "?['Id'],0)),0)",
        "not(equals(" + chosen + "?['odata.etag'],'*'))",
        "startsWith(string(" + chosen + "?['EventUID']),'LC04-IMPL-PREPARED-')",
        "equals(uriComponent(string(" + chosen + "?['EventUID']))," + chosen + "?['EventUID'])"] +
        ["not(empty(trim(string(coalesce(" + chosen + "?['" + key + "'],'')))))"
         for key in ('GUID', 'odata.etag', 'DocumentSHA256', 'ImplementationActions',
                     'EvidenceReference', 'NextAction', 'OccurredOn')] +
        (["startsWith(string(coalesce(" + chosen + "?['ImplementationActionsNote'],'')),'FICTIONAL')",
          "lessOrEquals(length(string(coalesce(" + chosen + "?['ImplementationActionsNote'],''))),2000)"]
         if full_actions else []), 'SelectedVerification_parent')
    actions['Retained_parent_uid']['runAfter'] = {'SelectedVerification_parent_valid': ['Succeeded']}
    result['properties']['definition']['actions'] = {**prefix, **actions}
    definition = result['properties']['definition']; flat = _flatten(definition['actions'])
    geometry = audit_actions(definition)
    if geometry['actionCount'] > 500 or geometry['maximumActionDepth'] > 8 or action_references(definition['actions']) - flat.keys():
        raise ValueError('Selected verification graph exceeds native limits or has unresolved references')
    return result
