"""Build a constrained fictional native guard; no network, approval or case writes."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit


def build(request, reference, source_text):
    if not isinstance(request.get('occurredOn'), str) or not request['occurredOn'].endswith('Z'):
        raise ValueError('Frozen UTC occurrence required')
    datetime.fromisoformat(request['occurredOn'].replace('Z', '+00:00'))
    if request.get('FictionalTest') is not True:
        raise ValueError('Fictional request required')
    if hashlib.sha256(source_text.encode()).hexdigest() != request['scope']['DocumentSHA256']:
        raise ValueError('Source hash mismatch')
    site = request['site'].rstrip('/')
    parsed_site = urlsplit(site)
    origin = parsed_site.scheme + '://' + parsed_site.netloc
    if parsed_site.scheme != 'https' or not parsed_site.netloc:
        raise ValueError('HTTPS site required')
    path = request['targetPath']
    if not path.startswith(request['qualificationFolder'] + '/FICTIONAL-') or '..' in path:
        raise ValueError('Target outside fictional qualification folder')
    if not request['EventUID'].startswith('LC04-PUBLICATION-'):
        raise ValueError('Publication event reservation required')
    decision = request['decision']
    scope = request['scope']
    for k, v in scope.items():
        if decision.get(k) != v:
            raise ValueError('Decision scope mismatch: ' + k)
    if (decision.get('FictionalTest') is not True or decision.get('DecisionOutcome') != 'Approved (recorded)'
            or decision.get('Stage') != 'Decision' or decision.get('RecordState') != 'Recorded'
            or decision.get('ConditionsState') not in ('None recorded', 'Resolved')
            or not decision.get('ReadinessEventUID') or not decision.get('DecisionReference')):
        raise ValueError('Exact fictional authorisation required')
    def lit(v):
        return 'true' if v is True else "'" + str(v).replace("'", "''") + "'"
    def http(uri, after=None, method='GET', body=None):
        params = {'dataset': site, 'parameters/method': method, 'parameters/uri': uri,
                  'parameters/headers': {'Accept': 'application/json;odata=nometadata', 'Content-Type': 'application/json;odata=nometadata'}}
        if body is not None:
            params['parameters/body'] = body
        return {'type': 'OpenApiConnection', 'inputs': {'host': {'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline', 'connectionName': 'shared_sharepointonline', 'operationId': 'HttpRequest'}, 'parameters': params}, 'runAfter': after or {}}
    def comp(value, after=None):
        return {'type': 'Compose', 'inputs': value, 'runAfter': after or {}}
    def fail(code):
        return {'type': 'Terminate', 'inputs': {'runStatus': 'Failed', 'runError': {'code': code, 'message': 'Fictional publication held; no real policy effect'}}, 'runAfter': {}}
    def guard(expr, yes, code, after=None):
        return {'type': 'If', 'expression': expr, 'actions': yes, 'else': {'actions': {'Refuse_' + code: fail(code)}}, 'runAfter': after or {}}
    def text(action):
        return "if(contains(body('" + action + "'),'$content'),base64ToString(body('" + action + "')?['$content']),string(body('" + action + "')))"
    def match(action, expected):
        return '@and(' + ','.join("equals(first(body('" + action + "')?['value'])?['" + k + "']," + lit(v) + ')' for k, v in expected.items()) + ')'
    src = "_api/web/GetFileById('" + request['sourceUniqueId'] + "')"
    target = "_api/web/GetFileByServerRelativePath(decodedurl=" + lit(path) + ')'
    events = "_api/web/lists/getbytitle('PPG Assurance Events')/items"
    decision_query = events + '?$filter=EventUID eq ' + lit(decision['EventUID'])
    publication_query = events + '?$filter=EventUID eq ' + lit(request['EventUID'])
    a = {'Read_decision': http(decision_query)}
    source = {'Read_source_before': http(src + '?$select=ETag,UniqueId'),
              'Read_source_bytes': http(src + '/$value', {'Read_source_before': ['Succeeded']}),
              'Read_source_after': http(src + '?$select=ETag,UniqueId', {'Read_source_bytes': ['Succeeded']})}
    work = {'Find_target': http("_api/web/GetFolderByServerRelativePath(decodedurl=" + lit(request['qualificationFolder']) + ")/Files?$filter=Name eq " + lit(path.rsplit('/', 1)[1]))}
    create = http("_api/web/GetFolderByServerRelativePath(decodedurl=" + lit(request['qualificationFolder']) + ")/Files/add(overwrite=false,url=" + lit(path.rsplit('/', 1)[1]) + ')', method='POST', body=source_text)
    work['Ensure_target'] = {'type': 'If', 'expression': "@equals(length(body('Find_target')?['value']),0)", 'actions': {'Create_fictional_copy': create}, 'else': {'actions': {}}, 'runAfter': {'Find_target': ['Succeeded']}}
    work['Read_target'] = http(target + '?$select=UniqueId,ETag,UIVersionLabel,Length', {'Ensure_target': ['Succeeded']})
    work['Read_target_bytes'] = http(target + '/$value', {'Read_target': ['Succeeded']})
    work['Read_target_after'] = http(target + '?$select=UniqueId,ETag,UIVersionLabel', {'Read_target_bytes': ['Succeeded']})
    payload = dict(scope, EventUID=request['EventUID'], Title='FICTIONAL publication representation only', Stage='Publication', RecordState='Recorded', ConditionsState='None recorded', DecisionOutcome='Unknown', VerificationResult='Not verified', OccurredOn=request['occurredOn'], FictionalTest=True, ActorName='Technical qualification; no real publisher authority', Summary='FICTIONAL exact-byte publication representation; no actual controlled publication', EvidenceReference=origin + path, ParentEventUID=decision['EventUID'], PublicationURL=origin + path, PublishedVersionRef="@body('Read_target')?['UIVersionLabel']")
    append = {'Payload': comp(payload), 'Find_publication': http(publication_query, {'Payload': ['Succeeded']})}
    append['Ensure_publication'] = {'type': 'If', 'expression': "@equals(length(body('Find_publication')?['value']),0)", 'actions': {'Create_publication': http(events, method='POST', body="@string(outputs('Payload'))")}, 'else': {'actions': {}}, 'runAfter': {'Find_publication': ['Succeeded']}}
    append['Read_publication'] = http(publication_query, {'Ensure_publication': ['Succeeded']})
    comparisons = ["equals(length(body('Read_publication')?['value']),1)"]
    for k in payload:
        comparisons.append("equals(first(body('Read_publication')?['value'])?['" + k + "'],outputs('Payload')?['" + k + "'])")
    append['Verify_publication'] = guard('@and(' + ','.join(comparisons) + ')', {'Native_receipt': comp({'requestId': request['requestId'], 'EventUID': request['EventUID'], 'nativeEventId': "@first(body('Read_publication')?['value'])?['Id']", 'targetUniqueId': "@body('Read_target')?['UniqueId']", 'nativeVersion': "@body('Read_target')?['UIVersionLabel']", 'runId': "@workflow()?['run']?['name']", 'createdEvents': "@if(equals(length(body('Find_publication')?['value']),0),1,0)", 'createdCopies': "@if(equals(length(body('Find_target')?['value']),0),1,0)", 'caseWrites': 0, 'realPolicyEffects': False, 'actorAuthorityQualified': False, 'guardProfile': 'fixed-fictional-exact-byte-and-event-pins', 'asOfUtc': '@utcNow()'})}, 'PublicationConflict', {'Read_publication': ['Succeeded']})
    # Re-read selected decision and its supersession evidence immediately before event append.
    final_checks = {'Recheck_decision': http(decision_query),
                    'Find_superseders': http(events + '?$filter=SupersedesEventUID eq ' + lit(decision['EventUID']), {'Recheck_decision': ['Succeeded']}),
                    'Recheck_source': http(src + '?$select=ETag,UniqueId', {'Find_superseders': ['Succeeded']})}
    final_checks['Selected_decision_guard'] = guard("@and(equals(length(body('Recheck_decision')?['value']),1),equals(length(body('Find_superseders')?['value']),0),empty(body('Find_superseders')?['odata.nextLink']),empty(body('Find_superseders')?['@odata.nextLink']),equals(body('Recheck_source')?['ETag']," + lit(request['sourceETag']) + '))', {'Frozen_decision_guard': guard(match('Recheck_decision', decision), append, 'DecisionChanged')}, 'DecisionSupersededOrSourceChanged', {'Recheck_source': ['Succeeded']})
    work['Target_guard'] = guard("@and(equals(" + text('Read_target_bytes') + ',' + lit(source_text) + "),equals(body('Read_target')?['ETag'],body('Read_target_after')?['ETag']),equals(body('Read_target')?['UniqueId'],body('Read_target_after')?['UniqueId']))", final_checks, 'TargetChanged', {'Read_target_after': ['Succeeded']})
    source['Source_guard'] = guard("@and(equals(body('Read_source_before')?['ETag']," + lit(request['sourceETag']) + "),equals(body('Read_source_after')?['ETag']," + lit(request['sourceETag']) + '),equals(' + text('Read_source_bytes') + ',' + lit(source_text) + '))', work, 'SourceChanged', {'Read_source_after': ['Succeeded']})
    # Check cardinality separately so an absent decision never reaches first().
    exact = guard(match('Read_decision', decision), source, 'DecisionMismatch')
    a['Decision_exists'] = guard("@equals(length(body('Read_decision')?['value']),1)", {'Decision_guard': exact}, 'DecisionUnavailable', {'Read_decision': ['Succeeded']})
    definition = dict(reference['properties']['definition'])
    definition['actions'] = a
    definition['triggers'] = {'manual': {'type': 'Request', 'kind': 'Button', 'inputs': {'schema': {'type': 'object', 'properties': {}, 'required': []}}, 'runtimeConfiguration': {'concurrency': {'runs': 1}}}}
    return {'properties': {'displayName': 'PPG Lifecycle | FICTIONAL publication evidence qualification', 'definition': definition, 'connectionReferences': {'shared_sharepointonline': reference['properties']['connectionReferences']['shared_sharepointonline']}, 'state': 'Stopped'}}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for flag in ['request', 'reference-flow', 'source-text', 'output']:
        parser.add_argument('--' + flag, required=True)
    args = parser.parse_args()
    result = build(json.loads(Path(args.request).read_text()), json.loads(Path(args.reference_flow).read_text()), Path(args.source_text).read_text())
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
