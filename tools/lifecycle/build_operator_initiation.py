"""Build a stopped native fictional operator-initiation pilot; no native I/O.

Private bindings select an already qualified source/list/connection. Operator
request and occurrence keys are distinct; role input remains explicitly proposed.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID


def build(reference, binding):
    source = binding['source']
    if (binding.get('qualificationOnly') is not True
            or not source.get('DocumentUID', '').startswith('FICTIONAL-')
            or hashlib.sha256(source['content'].encode('utf-8')).hexdigest() != source['sha256']):
        raise ValueError('An independently pinned fictional source is required')
    UUID(source['UniqueId'])
    site, folder, casebase = binding['siteUrl'], binding['evidenceFolder'], binding['caseListUri']
    def qualified_cases(node):
        if isinstance(node, dict):
            params = node.get('inputs', {}).get('parameters', {}) if isinstance(node.get('inputs'), dict) else {}
            if (params.get('dataset') == site
                    and str(params.get('parameters/uri', '')).startswith(casebase + '(')):
                yield params
            for value in node.values():
                yield from qualified_cases(value)
        elif isinstance(node, list):
            for value in node:
                yield from qualified_cases(value)
    if not list(qualified_cases(reference['properties']['definition'])):
        raise ValueError('Private target must match the qualified reference flow')
    if folder != urlsplit(site).path + '/PPG Review Evidence/Templates':
        raise ValueError('Use the existing qualification evidence folder')
    if not source['ETag'] or source['ETag'] == '*':
        raise ValueError('An exact source token is required')
    origin = urlsplit(site).scheme + '://' + urlsplit(site).netloc
    folder_url = origin + folder
    result = copy.deepcopy(reference)
    result = {'properties': {k: result['properties'][k] for k in ('definition', 'connectionReferences')}}
    props = result['properties']; props.update(displayName='PPG Lifecycle | FICTIONAL operator initiation', state='Stopped')
    props['connectionReferences'] = {'shared_sharepointonline': props['connectionReferences']['shared_sharepointonline']}
    definition = props['definition']
    fields = {'text': ('Request reference', 'LC02-OP- reference. Reuse only for the same complete request.'),
              'text_1': ('Review occurrence reference', 'OCC- reference. Identifies one fictional review occurrence.'),
              'text_2': ('Intended outcome', 'What this fictional review should prepare; no approval implied.'),
              'text_3': ('Next action', 'What should happen next; no assignment or notification is made.'),
              'text_4': ('Proposed review role', 'A proposal only. Ownership is not accepted by initiation.')}
    trigger = definition['triggers']['manual']
    trigger['inputs']['schema'] = {'type': 'object', 'properties': {
        k: {'type': 'string', 'title': title, 'description': desc,
            'x-ms-dynamically-added': True, 'x-ms-content-hint': 'TEXT'}
        for k, (title, desc) in fields.items()}, 'required': list(fields)}
    trigger['runtimeConfiguration'] = {'concurrency': {'runs': 1}}
    definition['triggers'] = {'manual': trigger}
    headers = {'Accept': 'application/json;odata=nometadata', 'Content-Type': 'application/json;odata=nometadata'}
    def http(uri, after=None, method='GET', body=None):
        params = {'dataset': site, 'parameters/method': method, 'parameters/uri': uri, 'parameters/headers': headers}
        if body is not None: params['parameters/body'] = body
        result = {'type': 'OpenApiConnection', 'inputs': {'host': {'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline', 'connectionName': 'shared_sharepointonline', 'operationId': 'HttpRequest'}, 'parameters': params}, 'runAfter': after or {}}
        if method != 'GET':
            result['inputs']['retryPolicy'] = {'type': 'none'}
        return result
    def comp(value, after=None): return {'type': 'Compose', 'inputs': value, 'runAfter': after or {}}
    def iff(expr, yes, no, after=None): return {'type': 'If', 'expression': expr, 'actions': yes, 'else': {'actions': no}, 'runAfter': after or {}}
    def fail(code): return {'type': 'Terminate', 'inputs': {'runStatus': 'Failed', 'runError': {'code': code, 'message': 'Fictional initiation held. Inspect request identity, source pins and retained case; do not overwrite.'}}, 'runAfter': {}}
    def quote(text): return text.replace("'", "''")
    def dynamic_uri(prefix, value, suffix): return "@concat('" + quote(prefix) + "'," + value + ",'" + quote(suffix) + "')"
    filebase = "_api/web/GetFolderByServerRelativePath(decodedurl='" + folder + "')/Files"
    findrequest = dynamic_uri(filebase + "?$filter=Name eq '", "outputs('Request_name')", "'")
    readrequest = dynamic_uri("_api/web/GetFileByServerRelativePath(decodedurl='" + folder + "/", "outputs('Request_name')", "')/$value")
    createrequest = dynamic_uri(filebase + "/add(overwrite=false,url='", "outputs('Request_name')", "')")
    findcase = dynamic_uri(casebase + "?$filter=CaseUID eq '", "outputs('Request')?['CaseUID']", "'")
    a = {'Request_name': comp("@concat('LC02-operator-request-',trim(triggerBody()?['text']),'.json')")}
    request = {'schemaVersion': 1, 'qualificationOnly': True,
               'requestReference': "@trim(triggerBody()?['text'])", 'occurrenceReference': "@trim(triggerBody()?['text_1'])",
               'CaseUID': "@concat('LC-FICTIONAL-OP-',trim(triggerBody()?['text_1']))",
               'DocumentUID': source['DocumentUID'], 'DocumentReference': source['DocumentReference'],
               'ReviewedVersionRef': source['ReviewedVersionRef'], 'DocumentSHA256': source['sha256'],
               'intendedOutcome': "@trim(triggerBody()?['text_2'])", 'nextAction': "@trim(triggerBody()?['text_3'])",
               'proposedRole': "@trim(triggerBody()?['text_4'])", 'realPolicyEffects': False}
    a['Request'] = comp(request, {'Request_name': ['Succeeded']})
    a['Read_source_before'] = http("_api/web/GetFileById('" + source['UniqueId'] + "')?$select=UniqueId,ETag", {'Request': ['Succeeded']})
    a['Read_source_content'] = http("_api/web/GetFileById('" + source['UniqueId'] + "')/$value", {'Read_source_before': ['Succeeded']})
    a['Read_source_after'] = http("_api/web/GetFileById('" + source['UniqueId'] + "')?$select=UniqueId,ETag", {'Read_source_content': ['Succeeded']})
    text = "if(contains(body('Read_source_content'),'$content'),base64ToString(body('Read_source_content')?['$content']),string(body('Read_source_content')))"
    sourceguard = "@and(equals(body('Read_source_before')?['ETag'],'" + quote(source['ETag']) + "'),equals(body('Read_source_after')?['ETag'],'" + quote(source['ETag']) + "'),equals(" + text + ",'" + quote(source['content']) + "'))"
    work = {'Find_request': http(findrequest)}
    prepared = {'kind': 'fictional-operator-initiation-request', 'request': "@outputs('Request')", 'preparedAtUtc': '@utcNow()', 'preparedByRun': "@workflow()?['run']?['name']"}
    work['Ensure_request'] = iff("@equals(length(body('Find_request')?['value']),0)", {'Prepared_request': comp(prepared), 'Create_request': http(createrequest, {'Prepared_request': ['Succeeded']}, 'POST', "@string(outputs('Prepared_request'))")}, {}, {'Find_request': ['Succeeded']})
    work['Read_request'] = http(readrequest, {'Ensure_request': ['Succeeded']})
    work['Retained_request'] = comp("@if(contains(body('Read_request'),'$content'),json(base64ToString(body('Read_request')?['$content'])),json(string(body('Read_request'))))", {'Read_request': ['Succeeded']})
    payload = {'Title': "@concat('FICTIONAL operator occurrence — ',outputs('Request')?['occurrenceReference'])", 'CaseUID': "@outputs('Request')?['CaseUID']",
               'linkedDocumentUIDs': json.dumps([source['DocumentUID']]),
               'sourceBaselineRef': "@concat('" + quote(folder_url) + "/',outputs('Request_name'))",
               'accountableRole': "@concat('UNACCEPTED — proposed fictional role: ',outputs('Request')?['proposedRole'])",
               'proposedOutcome': "@outputs('Request')?['intendedOutcome']", 'nextAction': "@outputs('Request')?['nextAction']",
               'targetDate': None, 'caseStatus': 'Initiated — FICTIONAL', 'evidenceDraftLink': source['DocumentReference']}
    create = {'Case_payload': comp(payload), 'Find_case': http(findcase, {'Case_payload': ['Succeeded']})}
    create['Ensure_case'] = iff("@equals(length(body('Find_case')?['value']),0)", {'Create_case': http(casebase, method='POST', body="@string(outputs('Case_payload'))")}, {}, {'Find_case': ['Succeeded']})
    create['Read_case'] = http(findcase, {'Ensure_case': ['Succeeded']})
    equal = ["equals(length(body('Read_case')?['value']),1)"] + ["equals(first(body('Read_case')?['value'])?['" + k + "'],outputs('Case_payload')?['" + k + "'])" for k in payload]
    checked = {'Recheck_source': http("_api/web/GetFileById('" + source['UniqueId'] + "')?$select=UniqueId,ETag")}
    receipt = {'CaseUID': "@outputs('Request')?['CaseUID']", 'caseItemId': "@first(body('Read_case')?['value'])?['Id']", 'requestReference': "@outputs('Request')?['requestReference']", 'occurrenceReference': "@outputs('Request')?['occurrenceReference']", 'caseCreatedCount': "@if(equals(length(body('Find_case')?['value']),0),1,0)", 'requestCreatedCount': "@if(equals(length(body('Find_request')?['value']),0),1,0)", 'ownershipAccepted': False, 'realPolicyEffects': False, 'sourceWrites': 0, 'catalogueWrites': 0, 'notifications': 0, 'actorAuthorityQualified': False, 'runId': "@workflow()?['run']?['name']", 'asOfUtc': '@utcNow()'}
    checked['Final_source_guard'] = iff("@equals(body('Recheck_source')?['ETag'],'" + quote(source['ETag']) + "')", {'Native_initiation_receipt': comp(receipt)}, {'Refuse_source_drift': fail('SourceChangedAfterInitiation')}, {'Recheck_source': ['Succeeded']})
    create['Verify_case'] = iff('@and(' + ','.join(equal) + ')', checked, {'Refuse_case_conflict': fail('CaseOccurrenceConflict')}, {'Read_case': ['Succeeded']})
    work['Verify_request'] = iff("@equals(string(outputs('Retained_request')?['request']),string(outputs('Request')))", create, {'Refuse_changed_request': fail('ChangedRequestIdentity')}, {'Retained_request': ['Succeeded']})
    a['Source_guard'] = iff(sourceguard, work, {'Refuse_source': fail('SourceChanged')}, {'Read_source_after': ['Succeeded']})
    checks = ["not(empty(trim(coalesce(triggerBody()?['" + k + "'],''))))" for k in fields]
    for key, prefix in [('text', 'LC02-OP-'), ('text_1', 'OCC-')]:
        val = "trim(triggerBody()?['" + key + "'])"
        checks += ["startsWith(" + val + ",'" + prefix + "')", "lessOrEquals(length(" + val + "),64)", "equals(encodeUriComponent(" + val + ")," + val + ")", "not(contains(" + val + ",decodeUriComponent('%27')))", "not(contains(" + val + ",'..'))"]
    checks += ["lessOrEquals(length(trim(triggerBody()?['" + k + "']))," + str(n) + ')' for k, n in [('text_2', 1000), ('text_3', 1000), ('text_4', 200)]]
    definition['actions'] = {'Validate_operator_input': iff('@and(' + ','.join(checks) + ')', a, {'Refuse_input': fail('InvalidOperatorInput')})}
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--reference', required=True); p.add_argument('--binding', required=True); p.add_argument('--output', required=True); args = p.parse_args()
    Path(args.output).write_text(json.dumps(build(json.loads(Path(args.reference).read_text()), json.loads(Path(args.binding).read_text())), indent=2) + '\n')
