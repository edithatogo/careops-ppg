"""Compose a read-only manual owner-guide queue from qualified SharePoint bindings.

No case/source writes, approval, notifications or AI calls. An authorised agent
session consumes the native request and performs the qualified manual preparation.
"""
import copy
import re
from urllib.parse import urlsplit
from uuid import UUID


def build(reference, binding):
    site, source = binding['siteUrl'], binding['source']
    parsed = urlsplit(site)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.query or parsed.fragment
            or parsed.username is not None or parsed.password is not None):
        raise ValueError('exact_https_site_required')
    UUID(source['nativeId'])
    if not source['etag'] or source['etag'] == '*':
        raise ValueError('exact_source_token_required')
    for key in ('sha256', 'candidateSHA256'):
        if not re.fullmatch('[a-f0-9]{64}', binding[key] if key == 'candidateSHA256' else source[key]):
            raise ValueError('exact_hash_required')
    if binding['documentUID'] != 'PPG-WORKBENCH-OPERATOR-GUIDE':
        raise ValueError('guide_only_scope')
    props = reference['properties']
    if 'shared_sharepointonline' not in props['connectionReferences']:
        raise ValueError('qualified_sharepoint_connection_required')
    # The supplied reference must actually use this existing site's connector.
    def uses_site(node):
        if isinstance(node, dict):
            params = node.get('inputs', {}).get('parameters', {}) if isinstance(node.get('inputs'), dict) else {}
            return params.get('dataset') == site or any(uses_site(v) for v in node.values())
        return isinstance(node, list) and any(uses_site(v) for v in node)
    if not uses_site(props['definition']):
        raise ValueError('reference_site_mismatch')
    definition = copy.deepcopy(props['definition'])
    fields = {'text': ('Preparation reference', 'GUIDE- reference; reuse only for the same request.'),
              'text_1': ('Preparation purpose', 'Internal workbench draft only; no approval or issuance.'),
              'text_2': ('Planning review date (optional)', 'Explicit YYYY-MM-DD planning date, or leave blank. No automatic policy interval.')}
    definition['triggers'] = {'manual': {'type': 'Request', 'kind': 'Button',
        'inputs': {'schema': {'type': 'object', 'properties': {
            k: {'type': 'string', 'title': title, 'description': desc,
                'x-ms-dynamically-added': True, 'x-ms-content-hint': 'TEXT'}
            for k, (title, desc) in fields.items()}, 'required': ['text', 'text_1']}},
        'runtimeConfiguration': {'concurrency': {'runs': 1}}}}
    literal = lambda x: "'" + str(x).replace("'", "''") + "'"
    def read(after):
        return {'type': 'OpenApiConnection', 'runAfter': after, 'inputs': {
            'host': {'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline',
                     'connectionName': 'shared_sharepointonline', 'operationId': 'HttpRequest'},
            'parameters': {'dataset': site, 'parameters/method': 'GET',
                           'parameters/uri': "_api/web/GetFileById('"+source['nativeId']+"')?$select=UniqueId,ETag,UIVersionLabel,Length",
                           'parameters/headers': {'Accept': 'application/json;odata=nometadata'}},
            'retryPolicy': {'type': 'none'}, 'authentication': "@parameters('$authentication')"}}
    conditions = ["startsWith(trim(coalesce(triggerBody()?['text'],'')),'GUIDE-')",
                  "lessOrEquals(length(trim(coalesce(triggerBody()?['text'],''))),100)",
                  "not(empty(trim(coalesce(triggerBody()?['text_1'],''))))",
                  "lessOrEquals(length(trim(coalesce(triggerBody()?['text_1'],''))),1000)"]
    for name in ('Read_source', 'Read_source_after'):
        for key, value in [('UniqueId', source['nativeId']), ('ETag', source['etag']),
                           ('UIVersionLabel', source['nativeVersion'])]:
            conditions.append("equals(string(body('"+name+"')?['"+key+"']),"+literal(value)+")")
    request = {'kind': 'owner-guide-preparation-request', 'schemaVersion': 1,
               'documentUID': binding['documentUID'], 'proposedEdition': binding['proposedEdition'],
               'source': source, 'candidateSHA256': binding['candidateSHA256'],
               'requestUID': "@trim(triggerBody()?['text'])",
               'occurrenceUID': "@concat('OWNER-GUIDE-',trim(triggerBody()?['text']))",
               'purpose': "@trim(triggerBody()?['text_1'])",
               'planningReviewDate': "@trim(coalesce(triggerBody()?['text_2'],''))",
               'state': 'Awaiting agent review', 'scope': 'owner-approved-workbench',
               'agentSessionRequired': True, 'approvalRecorded': False, 'issued': False,
               'notificationsAllowed': False, 'nativeDataWrites': 0}
    definition['actions'] = {
        'Read_source': read({}), 'Read_source_after': read({'Read_source': ['Succeeded']}),
        'Verify_request_and_source': {'type': 'If', 'runAfter': {'Read_source_after': ['Succeeded']},
            'expression': '@and('+','.join(conditions)+')',
            'actions': {'Preparation_request': {'type': 'Compose', 'inputs': request, 'runAfter': {}}},
            'else': {'actions': {'Hold': {'type': 'Terminate', 'inputs': {'runStatus': 'Failed',
                'runError': {'code': 'OWNER_GUIDE_SOURCE_OR_INPUT_HELD',
                             'message': 'Source or request changed. No data writes or approval.'}}, 'runAfter': {}}}}}}
    definition['outputs'] = {}
    return {'properties': {'displayName': 'PPG | Owner guide | Prepare review (manual, no sends)',
            'definition': definition,
            'connectionReferences': {'shared_sharepointonline': copy.deepcopy(props['connectionReferences']['shared_sharepointonline'])},
            'state': 'Stopped', 'flowFailureAlertSubscribed': False}}
